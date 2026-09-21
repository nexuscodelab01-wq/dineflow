"""File storage and the image pipeline."""

import io
import struct
import zlib

import pytest

from app.core import images, storage
from app.core.storage import LocalStorage, S3Storage, belongs_to_tenant, delete_owned_url, thumb_key, validate_key

PIL = pytest.importorskip("PIL", reason="Pillow not installed") if False else None  # per-test skips below
try:
    import PIL as _pil  # noqa: F401
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
needs_pillow = pytest.mark.skipif(not HAS_PILLOW, reason="Pillow not installed in this environment")


def tiny_png(width=1, height=1) -> bytes:
    """A valid PNG built by hand, so tests don't need Pillow to create fixtures."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


# ---------------------------------------------------------------- keys & local storage

@pytest.mark.parametrize("key", ["../etc/passwd", "/abs/path", "a/../../b", "a//b", "a\\b", "", ".hidden", "x" * 300, "a b"])
def test_unsafe_keys_are_rejected(key):
    with pytest.raises(ValueError):
        validate_key(key)


def test_local_storage_round_trip_and_containment(tmp_path):
    s = LocalStorage(tmp_path, "/uploads")
    url = s.save("tenants/7/menu/abc.webp", b"data", "image/webp")
    assert url == "/uploads/tenants/7/menu/abc.webp"
    assert (tmp_path / "tenants/7/menu/abc.webp").read_bytes() == b"data"
    assert s.key_from_url(url) == "tenants/7/menu/abc.webp" and s.key_from_url("https://elsewhere/x.png") is None
    assert list(tmp_path.rglob("*.part")) == []                    # atomic write leaves no temp files
    s.delete("tenants/7/menu/abc.webp")
    s.delete("tenants/7/menu/abc.webp")                           # deleting twice is fine
    assert not (tmp_path / "tenants/7/menu/abc.webp").exists()
    with pytest.raises(ValueError):
        s.save("../escape.txt", b"x", "text/plain")


def test_s3_storage_uploads_with_immutable_caching_and_public_urls():
    class FakeS3:
        def __init__(self): self.calls = []
        def put_object(self, **kw): self.calls.append(("put", kw))
        def delete_object(self, **kw): self.calls.append(("delete", kw))
    fake = FakeS3()
    s = S3Storage("my-bucket", "https://cdn.example.com/", client=fake)
    assert s.save("tenants/1/menu/a.webp", b"x", "image/webp") == "https://cdn.example.com/tenants/1/menu/a.webp"
    kind, kw = fake.calls[0]
    assert kw["Bucket"] == "my-bucket" and kw["Key"] == "tenants/1/menu/a.webp" and kw["ContentType"] == "image/webp"
    assert "immutable" in kw["CacheControl"]
    s.delete("tenants/1/menu/a.webp")
    assert fake.calls[1] == ("delete", {"Bucket": "my-bucket", "Key": "tenants/1/menu/a.webp"})
    assert s.key_from_url("https://cdn.example.com/tenants/1/menu/a.webp") == "tenants/1/menu/a.webp"
    with pytest.raises(RuntimeError):
        S3Storage("", "https://cdn", client=fake)


# ---------------------------------------------------------------- tenant ownership

def test_tenants_can_only_delete_their_own_files(tmp_path):
    s = LocalStorage(tmp_path)
    storage.set_storage(s)
    try:
        a = s.save("tenants/1/menu/a.webp", b"a", "image/webp"); s.save("tenants/1/menu/a-thumb.webp", b"t", "image/webp")
        b = s.save("tenants/2/menu/b.webp", b"b", "image/webp")
        legacy = s.save("menu/r1-oldfile.png", b"l", "image/png")

        delete_owned_url(b, restaurant_id=1)                       # tenant 1 pointing at tenant 2's file: ignored
        assert (tmp_path / "tenants/2/menu/b.webp").exists()
        delete_owned_url("https://example.com/whatever.png", 1)     # external URLs: ignored
        delete_owned_url(None, 1)

        delete_owned_url(a, 1)                                     # own file (and its thumbnail): removed
        assert not (tmp_path / "tenants/1/menu/a.webp").exists() and not (tmp_path / "tenants/1/menu/a-thumb.webp").exists()
        delete_owned_url(legacy, 1)                                # legacy layout still recognised
        assert not (tmp_path / "menu/r1-oldfile.png").exists()
        assert belongs_to_tenant("menu/r1-x.png", 1) and not belongs_to_tenant("menu/r10-x.png", 1)
        assert thumb_key("tenants/1/menu/a.webp") == "tenants/1/menu/a-thumb.webp" and thumb_key("a.png") is None
    finally:
        storage.set_storage(None)


# ---------------------------------------------------------------- image validation (works with or without Pillow)

def test_the_files_content_decides_not_its_claimed_type():
    for bad, why in [(b"", "empty"), (b"just some text", "text"), (b"MZ\x90\x00 fake exe", "exe"),
                     (b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "svg"),
                     (b"%PDF-1.7", "pdf")]:
        with pytest.raises(images.InvalidImage):
            images.process_image(bad, max_side=800)
    assert images.sniff(tiny_png()) == "png"
    assert images.sniff(b"\xff\xd8\xff\xe0" + b"0" * 10) == "jpeg" and images.sniff(b"GIF89a....") == "gif"
    assert images.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp"


def test_size_limit_is_enforced():
    with pytest.raises(images.InvalidImage, match="5MB"):
        images.process_image(tiny_png() + b"0" * (5 * 1024 * 1024), max_side=800, max_bytes=5 * 1024 * 1024)


# ---------------------------------------------------------------- Pillow pipeline

@needs_pillow
def test_large_photos_are_scaled_down_and_converted_to_webp():
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (3000, 2000), (200, 30, 30)).save(buf, "JPEG")
    out = images.process_image(buf.getvalue(), max_side=1600)
    assert out.optimised and out.content_type == "image/webp" and out.extension == ".webp"
    assert max(out.width, out.height) == 1600 and out.width > out.height          # aspect ratio kept
    main, thumb = Image.open(io.BytesIO(out.main)), Image.open(io.BytesIO(out.thumb))
    assert main.format == "WEBP" and thumb.format == "WEBP" and max(thumb.size) == images.THUMB_SIDE
    assert len(out.main) < len(buf.getvalue())


@needs_pillow
def test_small_images_are_never_enlarged():
    out = images.process_image(tiny_png(50, 30), max_side=1600)
    assert (out.width, out.height) == (50, 30)


@needs_pillow
def test_location_and_camera_metadata_is_stripped():
    from PIL import Image
    exif = Image.Exif(); exif[0x010F] = "SecretCameraCo"; exif[0x8825] = {1: "N", 2: (37.0, 46.0, 30.0)}
    buf = io.BytesIO(); Image.new("RGB", (64, 64), "white").save(buf, "JPEG", exif=exif)
    assert b"SecretCameraCo" in buf.getvalue()                                    # the source really had metadata
    out = images.process_image(buf.getvalue(), max_side=800)
    assert b"SecretCameraCo" not in out.main and not Image.open(io.BytesIO(out.main)).getexif()


@needs_pillow
def test_transparency_is_preserved_for_logos():
    from PIL import Image
    buf = io.BytesIO(); Image.new("RGBA", (40, 40), (255, 0, 0, 0)).save(buf, "PNG")
    out = images.process_image(buf.getvalue(), max_side=800, thumb_side=None)
    assert Image.open(io.BytesIO(out.main)).mode == "RGBA" and out.thumb is None


@needs_pillow
def test_animated_gifs_keep_their_first_frame():
    from PIL import Image
    frames = [Image.new("RGB", (20, 20), c) for c in ("red", "blue")]
    buf = io.BytesIO(); frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    out = images.process_image(buf.getvalue(), max_side=800)
    assert Image.open(io.BytesIO(out.main)).convert("RGB").getpixel((5, 5))[0] > 200   # red, not blue


@needs_pillow
def test_corrupt_and_bomb_images_are_rejected():
    with pytest.raises(images.InvalidImage, match="valid image"):
        images.process_image(tiny_png()[:40], max_side=800)                          # truncated PNG
    with pytest.raises(images.InvalidImage, match="valid image"):
        images.process_image(b"\xff\xd8\xff\xe0" + b"garbage" * 50, max_side=800)    # JPEG signature, junk body
    with pytest.raises(images.InvalidImage, match="too large"):
        images.process_image(tiny_png(9000, 9000), max_side=800)                      # 81 MP, tiny on disk (compresses ~1000x)
