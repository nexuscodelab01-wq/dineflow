"""Validate and optimise uploaded images.

We never trust the browser's claimed type: the file's own bytes decide. With Pillow installed the
image is decoded, orientation-corrected, stripped of metadata (GPS, camera info), scaled down and
re-encoded as WebP, which also neutralises files crafted to exploit viewers. Without Pillow (a bare
development container) we still verify the signature and store the original untouched.
"""

import io
import logging
import warnings
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MAX_PIXELS = 50_000_000  # ~7000x7000: bigger is almost certainly a decompression bomb
THUMB_SIDE = 400

_SIGNATURES: list[tuple[str, bytes]] = [
    ("jpeg", b"\xff\xd8\xff"),
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("gif", b"GIF87a"),
    ("gif", b"GIF89a"),
]
_MIME = {"jpeg": "image/jpeg", "png": "image/png", "gif": "image/gif", "webp": "image/webp"}
_EXT = {"jpeg": ".jpg", "png": ".png", "gif": ".gif", "webp": ".webp"}


class InvalidImage(ValueError):
    """The upload isn't an acceptable image; the message is safe to show the user."""


@dataclass
class ProcessedImage:
    main: bytes
    thumb: bytes | None
    content_type: str
    extension: str
    width: int
    height: int
    optimised: bool  # False when Pillow was unavailable and the original was kept


def sniff(data: bytes) -> str | None:
    for kind, magic in _SIGNATURES:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    return Image, ImageOps


def process_image(data: bytes, *, max_side: int, thumb_side: int | None = THUMB_SIDE, max_bytes: int | None = None) -> ProcessedImage:
    if not data:
        raise InvalidImage("The file is empty")
    if max_bytes is not None and len(data) > max_bytes:
        raise InvalidImage(f"Image must be {max_bytes // (1024 * 1024)}MB or smaller")
    kind = sniff(data)
    if kind is None:
        raise InvalidImage("Only JPEG, PNG, WebP or GIF images are allowed")

    pillow = _pillow()
    if pillow is None:
        logger.warning("Pillow is not installed: storing the original image without resizing")
        return ProcessedImage(data, None, _MIME[kind], _EXT[kind], 0, 0, optimised=False)
    Image, ImageOps = pillow

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.width * image.height > MAX_PIXELS:  # header only — nothing decoded yet
                raise InvalidImage("That image's dimensions are too large")
            image.seek(0)  # animated GIF/WebP: keep the first frame
            image.load()
    except InvalidImage:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise InvalidImage("That image's dimensions are too large") from None
    except (OSError, SyntaxError, ValueError):
        raise InvalidImage("That file isn't a valid image") from None

    image = ImageOps.exif_transpose(image)  # respect the phone's rotation, then drop the metadata
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")

    def encode(side: int) -> tuple[bytes, tuple[int, int]]:
        copy = image.copy()
        copy.thumbnail((side, side), Image.Resampling.LANCZOS)  # only ever shrinks
        buffer = io.BytesIO()
        copy.save(buffer, format="WEBP", quality=82, method=4)  # no exif= argument: metadata is not carried over
        return buffer.getvalue(), copy.size

    main, size = encode(max_side)
    thumb = encode(thumb_side)[0] if thumb_side else None
    return ProcessedImage(main, thumb, "image/webp", ".webp", size[0], size[1], optimised=True)
