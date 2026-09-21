"""Job handlers: what each job type actually does. Register new ones with @job_handler("name")."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.core.email import EmailMessage, get_email_backend

logger = logging.getLogger(__name__)


@dataclass
class JobContext:
    job_id: int
    attempt: int
    restaurant_id: int | None


Handler = Callable[[dict[str, Any], JobContext], None]
HANDLERS: dict[str, Handler] = {}


def job_handler(name: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn

    return register


@job_handler("send_email")
def send_email(payload: dict[str, Any], ctx: JobContext) -> None:
    """Payload: {to, subject, text, html?, from_name?, reply_to?}. Raising makes the queue retry with backoff."""
    get_email_backend().send(
        EmailMessage(
            to=payload["to"],
            subject=payload["subject"],
            text=payload["text"],
            html=payload.get("html"),
            from_name=payload.get("from_name"),
            reply_to=payload.get("reply_to"),
        )
    )
