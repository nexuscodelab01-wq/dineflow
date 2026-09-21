"""Application entrypoint."""

import logging
import mimetypes
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import request_id_var, setup_logging
from app.core.realtime import install_shutdown_hook, start_listener, stop_listener
from app.core.storage import UPLOADS_ROOT

setup_logging()
logger = logging.getLogger(__name__)

# Fail fast: never boot in production with placeholder secrets.
settings.assert_production_ready()


def _init_sentry() -> None:
    """Report unhandled errors to Sentry when SENTRY_DSN is set. Optional dependency."""
    if not settings.SENTRY_DSN:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; error reporting is off")
        return
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )
    logger.info("Sentry error reporting enabled")


_init_sentry()



@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    (UPLOADS_ROOT / "menu").mkdir(parents=True, exist_ok=True)
    logger.info("Starting DineFlow API (env=%s)", settings.ENVIRONMENT)
    install_shutdown_hook()  # so open live streams never block a restart
    start_listener()  # live updates: one LISTEN connection per worker
    yield
    stop_listener()
    logger.info("Shutting down DineFlow API")


app = FastAPI(
    title="DineFlow API",
    description="Restaurant ordering and management platform",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    headers = {"Retry-After": str(exc.retry_after)} if hasattr(exc, "retry_after") else None
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message}, headers=headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never leak internals; give the client an id support can look up in the logs."""
    request_id = getattr(request.state, "request_id", "-")
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side.", "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = []
    for err in exc.errors():
        loc = err.get("loc", ())
        field = ".".join(str(part) for part in loc if part != "body")
        errors.append({"field": field or "body", "message": err.get("msg", "Invalid value")})
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation failed", "errors": errors},
    )


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_QUIET_PATHS = {"/api/v1/health", "/api/v1/health/ready"}


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id, log the request, and add baseline security headers."""
    incoming = request.headers.get("x-request-id", "")
    request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex[:16]
    request.state.request_id = request_id
    request_id_var.set(request_id)
    started = time.perf_counter()

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - started) * 1000
    if request.url.path not in _QUIET_PATHS:
        logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

class UploadsFiles(StaticFiles):
    """Serves uploaded files. Tenant uploads have unique names and never change, so browsers and CDNs
    may cache them for a year; without this every menu image would be re-validated on each visit."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200 and path.startswith("tenants/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# Slim containers ship no system MIME table and Python's built-in one doesn't know WebP, so files
# were served as text/plain — which browsers refuse to render as images under `nosniff`.
mimetypes.add_type("image/webp", ".webp")

app.mount("/uploads", UploadsFiles(directory=str(UPLOADS_ROOT)), name="uploads")
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
