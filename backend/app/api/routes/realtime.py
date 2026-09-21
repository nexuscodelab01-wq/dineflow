"""Server-Sent Events stream for staff screens."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.realtime import broker, kitchen_topic
from app.dependencies.restaurant import RestaurantId, StaffUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

HEARTBEAT_SECONDS = 15


async def _event_stream(request: Request, topic: str) -> AsyncIterator[str]:
    # Subscribe *inside* the generator so the subscription lives exactly as long as the stream:
    # if the client disconnects before streaming starts, nothing was registered and nothing leaks.
    sub = broker.subscribe(topic)
    try:
        # `retry` tells the browser how long to wait before reconnecting; `ready` lets the client
        # refetch its state now that it is guaranteed to hear about every later change.
        yield 'retry: 3000\n\nevent: ready\ndata: {"type":"ready"}\n\n'
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    break
                yield ": ping\n\n"  # keeps proxies and load balancers from closing an idle stream
                continue
            yield f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
    finally:
        broker.unsubscribe(sub)


@router.get("/kitchen/stream", summary="Live kitchen events (text/event-stream)")
async def kitchen_stream(request: Request, _: StaffUser, restaurant_id: RestaurantId) -> StreamingResponse:
    """Streams `order.created`, `order.status` and `resync` events for this restaurant's kitchen."""
    if broker.count() >= settings.REALTIME_MAX_STREAMS:
        raise HTTPException(status_code=503, detail="Too many live connections right now. Retrying shortly is fine.")
    return StreamingResponse(
        _event_stream(request, kitchen_topic(restaurant_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # tell nginx not to buffer the stream
            "Connection": "keep-alive",
        },
    )
