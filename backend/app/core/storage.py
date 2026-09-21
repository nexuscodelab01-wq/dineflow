"""File storage behind one small interface: local disk for development, S3-compatible for production.

Every tenant's files live under `tenants/<restaurant_id>/…`, so one tenant can never overwrite or
delete another's (see `delete_owned_url`). Keys are validated so they can't escape the storage root.
"""

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

UPLOADS_ROOT = Path(__file__).resolve().parents[2] / "uploads"
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,250}$")
CACHE_CONTROL = "public, max-age=31536000, immutable"  # keys are unique, so files never change


def validate_key(key: str) -> str:
    if not _KEY_RE.match(key) or ".." in key.split("/") or "//" in key:
        raise ValueError(f"Unsafe storage key: {key!r}")
    return key


class Storage(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> str: ...
    def delete(self, key: str) -> None: ...
    def url_for(self, key: str) -> str: ...
    def key_from_url(self, url: str) -> str | None: ...


class _UrlMixin:
    public_base: str

    def url_for(self, key: str) -> str:
        return f"{self.public_base}/{validate_key(key)}"

    def key_from_url(self, url: str) -> str | None:
        prefix = self.public_base + "/"
        return url[len(prefix):] if url and url.startswith(prefix) else None


class LocalStorage(_UrlMixin):
    def __init__(self, root: Path = UPLOADS_ROOT, public_base: str = "/uploads") -> None:
        self.root = Path(root).resolve()
        self.public_base = public_base.rstrip("/")

    def _path(self, key: str) -> Path:
        path = (self.root / validate_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError(f"Unsafe storage key: {key!r}")
        return path

    def save(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")  # write then rename: never a half-written file
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return self.url_for(key)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage(_UrlMixin):
    def __init__(self, bucket: str, public_base: str, client=None) -> None:
        if not bucket or not public_base:
            raise RuntimeError("STORAGE_BACKEND=s3 needs S3_BUCKET and STORAGE_PUBLIC_URL")
        self.bucket = bucket
        self.public_base = public_base.rstrip("/")
        self.client = client or self._make_client()

    @staticmethod
    def _make_client():
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover — depends on the image
            raise RuntimeError("STORAGE_BACKEND=s3 needs the 'boto3' package (see requirements.txt)") from exc
        return boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY or None,
        )

    def save(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.bucket, Key=validate_key(key), Body=data, ContentType=content_type, CacheControl=CACHE_CONTROL
        )
        return self.url_for(key)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=validate_key(key))


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        if settings.STORAGE_BACKEND.lower() == "s3":
            _storage = S3Storage(settings.S3_BUCKET, settings.STORAGE_PUBLIC_URL)
        else:
            if settings.is_production:
                logger.warning(
                    "STORAGE_BACKEND=local in production: uploads live on this server's disk and are lost "
                    "on redeploy or when running several servers. Use STORAGE_BACKEND=s3."
                )
            _storage = LocalStorage(public_base=settings.STORAGE_PUBLIC_URL or "/uploads")
    return _storage


def set_storage(storage: Storage | None) -> None:
    """Swap the backend (tests, or an explicit override at startup)."""
    global _storage
    _storage = storage


# ---- tenant ownership -----------------------------------------------------------------------------

def tenant_prefix(restaurant_id: int, kind: str) -> str:
    return f"tenants/{restaurant_id}/{kind}"


def belongs_to_tenant(key: str, restaurant_id: int) -> bool:
    return key.startswith(f"tenants/{restaurant_id}/") or key.startswith(f"menu/r{restaurant_id}-")  # legacy layout


def thumb_key(key: str) -> str | None:
    return key[: -len(".webp")] + "-thumb.webp" if key.endswith(".webp") and not key.endswith("-thumb.webp") else None


def delete_owned_url(url: str | None, restaurant_id: int) -> None:
    """Best-effort removal of a file we stored for this tenant. Anything else is left alone — an
    admin can type any URL into an image field, and must not be able to delete other tenants' files."""
    if not url:
        return
    try:
        storage = get_storage()
        key = storage.key_from_url(url)
        if key is None or not belongs_to_tenant(key, restaurant_id):
            return
        storage.delete(key)
        if (sibling := thumb_key(key)) is not None:
            storage.delete(sibling)
    except Exception:  # noqa: BLE001 — cleanup must never break the request that triggered it
        logger.warning("Could not delete stored file %s", url, exc_info=True)
