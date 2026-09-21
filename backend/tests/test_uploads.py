"""Uploads through the API: content validation, tenant-scoped storage, cleanup, URL validation."""

import pytest

from app.core import storage
from app.core.storage import LocalStorage
from tests.test_admin_management import url, world  # noqa: F401  (world is a fixture)
from tests.test_storage import HAS_PILLOW, tiny_png


@pytest.fixture(autouse=True)
def local_tmp_storage(tmp_path):
    s = LocalStorage(tmp_path, "/uploads")
    storage.set_storage(s)
    yield tmp_path
    storage.set_storage(None)


def upload(w, path, headers, data=None, name="photo.png", ctype="image/png"):
    return w.client.post(url(w, path), headers=headers, files={"file": (name, tiny_png() if data is None else data, ctype)})


def stored(tmp_path, rel):
    return (tmp_path / rel.removeprefix("/uploads/")).exists()


def test_menu_image_is_stored_under_the_tenants_prefix(world, local_tmp_storage):
    w = world
    r = upload(w, "/uploads/menu-image", w.admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith(f"/uploads/tenants/{w.a.id}/menu/")
    assert stored(local_tmp_storage, body["url"])
    if HAS_PILLOW:
        assert body["url"].endswith(".webp") and body["thumb_url"].endswith("-thumb.webp") and stored(local_tmp_storage, body["thumb_url"])
    else:
        assert body["url"].endswith(".png") and body["thumb_url"] is None      # original kept when Pillow is missing


def test_uploads_are_checked_by_content_not_by_claimed_type(world):
    w = world
    for name, data, ctype in [
        ("evil.png", b"<html><script>alert(1)</script></html>", "image/png"),            # HTML claiming to be a PNG
        ("logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>', "image/svg+xml"),
        ("run.exe", b"MZ\x90\x00", "application/octet-stream"),
        ("empty.png", b"", "image/png"),
    ]:
        r = upload(w, "/uploads/menu-image", w.admin, data, name, ctype)
        assert r.status_code == 400, (name, r.text)
    assert "JPEG, PNG, WebP or GIF" in upload(w, "/uploads/menu-image", w.admin, b"plain text", "a.png").json()["detail"]


def test_oversized_uploads_are_refused(world, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 2048)
    r = upload(w := world, "/uploads/menu-image", w.admin, tiny_png() + b"0" * 4096)
    assert r.status_code == 400 and "smaller" in r.json()["detail"]


def test_only_admins_can_upload(world):
    w = world
    assert upload(w, "/uploads/menu-image", w.staff).status_code == 403
    assert upload(w, "/uploads/logo", w.customer).status_code == 403
    assert w.client.post(url(w, "/uploads/menu-image"), files={"file": ("a.png", tiny_png(), "image/png")}).status_code == 401
    assert upload(w, "/uploads/menu-image", w.admin_b).status_code == 403          # another restaurant's admin


def test_logo_upload_and_replacement_removes_the_old_file(world, local_tmp_storage):
    w = world
    first = upload(w, "/uploads/logo", w.admin).json()["url"]
    assert first.startswith(f"/uploads/tenants/{w.a.id}/branding/")
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"logo_url": first}).json()["logo_url"] == first
    assert stored(local_tmp_storage, first)

    second = upload(w, "/uploads/logo", w.admin).json()["url"]
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"logo_url": second}).status_code == 200
    assert not stored(local_tmp_storage, first) and stored(local_tmp_storage, second)       # old logo cleaned up

    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"logo_url": None}).json()["logo_url"] is None
    assert not stored(local_tmp_storage, second)


def test_replacing_or_deleting_a_menu_item_removes_its_uploaded_photo(world, local_tmp_storage):
    w = world
    a = upload(w, "/uploads/menu-image", w.admin).json()
    r = w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": a["url"]})
    assert r.status_code == 200 and r.json()["image_url"] == a["url"]

    b = upload(w, "/uploads/menu-image", w.admin).json()
    w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": b["url"]})
    assert not stored(local_tmp_storage, a["url"]) and stored(local_tmp_storage, b["url"])
    if a["thumb_url"]:
        assert not stored(local_tmp_storage, a["thumb_url"])

    assert w.client.delete(url(w, f"/menu/{w.item.id}"), headers=w.admin).status_code == 204
    assert not stored(local_tmp_storage, b["url"])


def test_an_admin_cannot_delete_another_tenants_file_by_pointing_an_item_at_it(world, local_tmp_storage):
    w = world
    victim = upload(w, "/uploads/menu-image", w.admin_b, ) if False else None   # (upload as B via its own restaurant id)
    victim = w.client.post(url(w, "/uploads/menu-image", restaurant=w.b), headers=w.admin_b,
                           files={"file": ("a.png", tiny_png(), "image/png")}).json()["url"]
    assert victim.startswith(f"/uploads/tenants/{w.b.id}/") and stored(local_tmp_storage, victim)

    # Tenant A stores B's URL on its item, then replaces and deletes it: B's file must survive.
    w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": victim})
    w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": "https://example.com/x.jpg"})
    w.client.delete(url(w, f"/menu/{w.item.id}"), headers=w.admin)
    assert stored(local_tmp_storage, victim)


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "ftp://x/y.png", "//evil.com/x.png",
                                 "/etc/passwd", "http://a b.com/x.png", "https://x.com/" + "a" * 600])
def test_image_fields_only_accept_uploads_or_http_links(world, bad):
    w = world
    assert w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": bad}).status_code == 422
    assert w.client.patch(url(w, "/settings"), headers=w.admin, json={"logo_url": bad}).status_code == 422
    assert w.client.post(url(w, "/menu"), headers=w.admin, json={
        "restaurant_id": w.a.id, "category_id": w.cat.id, "name": "X", "price": "5", "image_url": bad}).status_code == 422


@pytest.mark.parametrize("good", ["/uploads/tenants/1/menu/a.webp", "https://images.unsplash.com/photo-1?w=800", "http://localhost:9000/a.png"])
def test_valid_image_links_are_accepted(world, good):
    w = world
    assert w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": good}).status_code == 200
    assert w.client.put(url(w, f"/menu/{w.item.id}"), headers=w.admin, json={"image_url": ""}).json()["image_url"] is None   # blank clears it


# ---------------------------------------------------------------- serving uploaded files

def test_uploaded_webp_is_served_as_an_image_with_long_lived_caching(client):
    """Regression: WebP was served as text/plain (unknown extension), which `nosniff` turns into a broken image."""
    from app.core.storage import UPLOADS_ROOT

    folder = UPLOADS_ROOT / "tenants" / "999999" / "test"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        (folder / "a.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
        (folder / "b.png").write_bytes(tiny_png())
        webp = client.get("/uploads/tenants/999999/test/a.webp")
        assert webp.status_code == 200 and webp.headers["content-type"] == "image/webp"
        assert "immutable" in webp.headers["cache-control"] and "max-age=31536000" in webp.headers["cache-control"]
        assert webp.headers["x-content-type-options"] == "nosniff"
        assert client.get("/uploads/tenants/999999/test/b.png").headers["content-type"] == "image/png"
        assert client.get("/uploads/tenants/999999/test/missing.webp").status_code == 404
        assert client.get("/uploads/../app/main.py").status_code in (404, 400)          # no path traversal out of uploads
    finally:
        import shutil
        shutil.rmtree(UPLOADS_ROOT / "tenants" / "999999", ignore_errors=True)
