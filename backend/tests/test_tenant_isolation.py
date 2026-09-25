"""Tenant isolation: one restaurant must never see or change another's data.

This suite runs forever in CI. It has four layers:
  1. a route registry — every API route must be classified, so a new endpoint can't ship without a
     decision about isolation;
  2. a generic sweep of every /admin route with the wrong tenant's credentials;
  3. an IDOR table — tenant A's admin using tenant B's object ids on every route that takes one;
  4. customer-facing attacks, plus proof that tenant B's data is untouched afterwards.
"""

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import text

from app.db.session import get_db
from app.main import app
from app.models.enums import RoleName
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user, place_order

API = "/api/v1"


@pytest.fixture
def two(client, db):
    """Tenants Alpha and Bravo, each with one order. `two.a` / `two.b`."""
    app.dependency_overrides[get_db] = override_get_db(db)
    a, b = make_tenant(db, "Alpha"), make_tenant(db, "Bravo")
    for t in (a, b):
        r = place_order(client, t)
        assert r.status_code == 201, r.text
        t.order_id = r.json()["id"]
    superadmin = make_user(db, "platform@iso-demo.com", RoleName.SUPER_ADMIN)
    yield type("Two", (), {"client": client, "db": db, "a": a, "b": b, "superadmin": superadmin})
    app.dependency_overrides.clear()


# ============================================================================ 1. route registry

# Routes that intentionally serve any visitor. Nothing here may return another tenant's PRIVATE data;
# each one is covered by a test below or reads only public storefront data.
PUBLIC = {
    ("GET", "/t/{token}"), ("POST", "/t/{token}/join"),
    ("GET", "/health"), ("GET", "/health/ready"),
    ("GET", "/categories"), ("GET", "/menu"), ("GET", "/menu/{item_id}"),
    ("GET", "/restaurants/{identifier}"), ("GET", "/restaurants/{identifier}/tables"),
    ("GET", "/restaurants/{identifier}/reservations/availability"),
    ("GET", "/restaurants/{identifier}/reviews"),
    ("GET", "/restaurants/{identifier}/pickup-slots"),
    ("GET", "/tenant"),
    ("GET", "/reservations/actions/{token}"), ("POST", "/reservations/actions/{token}/confirm"), ("POST", "/reservations/actions/{token}/cancel"),
}
# Identity routes: tenant comes from the credentials / an explicit restaurant, see test_tenancy_auth.py.
AUTH = {("POST", "/auth/register"), ("POST", "/auth/login"), ("POST", "/auth/refresh"), ("POST", "/auth/logout"), ("GET", "/auth/me"), ("GET", "/auth/my-restaurants"),
        ("POST", "/auth/forgot-password"), ("POST", "/auth/reset-password"), ("POST", "/auth/change-password")}
# Signed-in customer routes, always scoped to the caller's own tenant and rows.
CUSTOMER = {
    ("GET", "/orders"), ("POST", "/orders"), ("GET", "/orders/{order_id}"), ("GET", "/orders/{order_id}/stream"),
    ("GET", "/reservations/me"), ("POST", "/reservations/{reservation_id}/confirm"),
    ("POST", "/reservations/{reservation_id}/cancel"), ("POST", "/restaurants/{identifier}/reservations"),
    ("GET", "/reviews"), ("POST", "/reviews"), ("GET", "/reviews/eligible"),
    ("GET", "/loyalty"),
    ("POST", "/coupons/preview"),
}
# Guests at a table: a table pass (not an account) bound to one restaurant's open session; see test_table_ordering.py.
GUEST = {("GET", "/table-session"), ("POST", "/table-session/orders"), ("GET", "/table-session/stream"), ("POST", "/table-session/requests")}
# Platform-only.
PLATFORM = {
    ("GET", "/restaurants"),
    ("GET", "/platform/restaurants/{restaurant_id}/features"),
    ("PUT", "/platform/restaurants/{restaurant_id}/features/{key}"),
    ("DELETE", "/platform/restaurants/{restaurant_id}/features/{key}"),
    ("GET", "/platform/audit-log"),
    ("POST", "/platform/restaurants"), ("GET", "/platform/restaurants/templates"), ("POST", "/platform/restaurants/{restaurant_id}/verify-domain"),
}


def all_routes():
    out = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith(API):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                out.append((method, route.path[len(API):]))
    return sorted(out)


def test_every_route_is_classified_for_isolation():
    known = PUBLIC | AUTH | CUSTOMER | GUEST | PLATFORM
    unclassified = [(m, p) for m, p in all_routes() if not p.startswith("/admin") and (m, p) not in known]
    assert not unclassified, (
        f"New API route(s) without an isolation decision: {unclassified}. Add each to PUBLIC, AUTH, CUSTOMER or "
        "PLATFORM in tests/test_tenant_isolation.py and add a test proving it can't cross tenants."
    )
    stale = [r for r in known if r not in set(all_routes())]
    assert not stale, f"Classified routes that no longer exist: {stale}"


# ============================================================================ 2. generic /admin sweep

def admin_routes():
    return [(m, p) for m, p in all_routes() if p.startswith("/admin")]


def call(client, method, path, headers, restaurant_id):
    concrete = path.replace("{", "").replace("}", "")           # {item_id} -> item_id ... replaced below
    for name in [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]:
        concrete = concrete.replace(name, "1")
    url = f"{API}{concrete}" + (f"?restaurant_id={restaurant_id}" if restaurant_id is not None else "")
    kwargs = {"headers": headers}
    if path.startswith("/admin/uploads/"):
        kwargs["files"] = {"file": ("a.png", b"x", "image/png")}
    elif method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}
    return client.request(method, url, **kwargs)


@pytest.mark.parametrize("method,path", admin_routes(), ids=lambda v: str(v))
def test_admin_routes_refuse_everyone_but_the_restaurants_own_staff(two, method, path):
    c, a, b = two.client, two.a, two.b
    assert call(c, method, path, {}, b.rid).status_code == 401, "signed-out visitors must be refused"
    assert call(c, method, path, header(b.customer), b.rid).status_code == 403, "customers are not staff"
    assert call(c, method, path, header(a.customer), a.rid).status_code == 403, "customers of the same restaurant neither"
    # Alpha's staff/admin against Bravo: refused before any data is touched.
    assert call(c, method, path, header(a.admin), b.rid).status_code == 403
    assert call(c, method, path, header(a.staff), b.rid).status_code == 403
    # A restaurant id is mandatory: no default tenant to fall back to.
    assert call(c, method, path, header(a.admin), None).status_code in (403, 422)


# ============================================================================ 3. IDOR table (admin)

def A_url(two, path, **query):
    extra = "".join(f"&{k}={v}" for k, v in query.items())
    return f"{API}/admin{path}?restaurant_id={two.a.rid}{extra}"


# (name, method, path, body)  — every call is made as Alpha's ADMIN against Alpha's restaurant id, but
# naming one of BRAVO's objects. The server must answer "not found" (or reject the reference) — never 2xx.
IDOR = [
    ("update category", "PUT", lambda t: f"/categories/{t.b.category.id}", lambda t: {"name": "pwned"}),
    ("delete category", "DELETE", lambda t: f"/categories/{t.b.category.id}", None),
    ("reorder categories", "PATCH", lambda t: "/categories/reorder", lambda t: {"items": [{"id": t.b.category.id, "sort_order": 9}]}),
    ("update menu item", "PUT", lambda t: f"/menu/{t.b.item.id}", lambda t: {"name": "pwned"}),
    ("delete menu item", "DELETE", lambda t: f"/menu/{t.b.item.id}", None),
    ("create item in their category", "POST", lambda t: "/menu", lambda t: {"restaurant_id": t.a.rid, "category_id": t.b.category.id, "name": "x", "price": "5"}),
    ("move own item into their category", "PUT", lambda t: f"/menu/{t.a.item.id}", lambda t: {"category_id": t.b.category.id}),
    ("attach their modifier to own item", "PUT", lambda t: f"/menu/{t.a.item.id}", lambda t: {"modifier_ids": [t.b.modifier.id]}),
    ("update modifier", "PUT", lambda t: f"/modifiers/{t.b.modifier.id}", lambda t: {"name": "pwned"}),
    ("delete modifier", "DELETE", lambda t: f"/modifiers/{t.b.modifier.id}", None),
    ("add option to their modifier", "POST", lambda t: f"/modifiers/{t.b.modifier.id}/options", lambda t: {"name": "pwned"}),
    ("update their option", "PUT", lambda t: f"/modifier-options/{t.b.option.id}", lambda t: {"name": "pwned"}),
    ("delete their option", "DELETE", lambda t: f"/modifier-options/{t.b.option.id}", None),
    ("read their order", "GET", lambda t: f"/orders/{t.b.order_id}", None),
    ("change their order status", "PATCH", lambda t: f"/orders/{t.b.order_id}/status", lambda t: {"status": "CANCELLED"}),
    ("read their customer", "GET", lambda t: f"/customers/{t.b.customer.id}", None),
    ("update their table", "PUT", lambda t: f"/tables/{t.b.table.id}", lambda t: {"table_number": "pwned"}),
    ("delete their table", "DELETE", lambda t: f"/tables/{t.b.table.id}", None),
    ("set their table status", "PATCH", lambda t: f"/tables/{t.b.table.id}/status", lambda t: {"status": "OCCUPIED", "force": True}),
    ("move their table on the plan", "PUT", lambda t: "/tables/layout", lambda t: {"items": [{"id": t.b.table.id, "pos_x": 1, "pos_y": 1}]}),
    ("book their table", "POST", lambda t: "/reservations", lambda t: {"table_id": t.b.table.id, "party_size": 2, "starts_at": "2030-01-01T18:00:00Z", "guest_name": "x"}),
    ("edit their reservation", "PATCH", lambda t: f"/reservations/{t.b.reservation.id}", lambda t: {"guest_name": "pwned"}),
    ("cancel their reservation", "PATCH", lambda t: f"/reservations/{t.b.reservation.id}/status", lambda t: {"status": "CANCELLED"}),
    ("extend their reservation", "POST", lambda t: f"/reservations/{t.b.reservation.id}/extend", lambda t: {"minutes": 30}),
    ("move own reservation onto their table", "PATCH", lambda t: f"/reservations/{t.a.reservation.id}", lambda t: {"table_id": t.b.table.id}),
    ("combine own reservation with their table", "PATCH", lambda t: f"/reservations/{t.a.reservation.id}", lambda t: {"extra_table_ids": [t.b.table.id]}),
    ("book combined with their table", "POST", lambda t: "/reservations", lambda t: {"table_id": t.a.table.id, "extra_table_ids": [t.b.table.id], "party_size": 2, "starts_at": "2030-01-01T18:00:00Z", "guest_name": "x"}),
    ("notify their waitlist entry", "POST", lambda t: f"/waitlist/{t.b.waitlist_entry.id}/notify", None),
    ("seat their waitlist entry", "POST", lambda t: f"/waitlist/{t.b.waitlist_entry.id}/seat", lambda t: {"table_id": t.a.table.id}),
    ("seat own waitlist entry onto their table", "POST", lambda t: f"/waitlist/{t.a.waitlist_entry.id}/seat", lambda t: {"table_id": t.b.table.id}),
    ("cancel their waitlist entry", "POST", lambda t: f"/waitlist/{t.b.waitlist_entry.id}/cancel", None),
]


@pytest.mark.parametrize("name,method,path,body", IDOR, ids=[c[0] for c in IDOR])
def test_alphas_admin_cannot_touch_bravos_objects(two, name, method, path, body):
    r = two.client.request(method, A_url(two, path(two)), headers=header(two.a.admin), json=body(two) if body else None)
    assert r.status_code in (400, 403, 404), f"{name}: expected a refusal, got {r.status_code} {r.text[:200]}"
    # And nothing of Bravo's may appear in the response either.
    assert "Bravo" not in r.text, f"{name}: response leaked Bravo data: {r.text[:200]}"


def test_alphas_lists_contain_only_alphas_rows(two):
    c, h = two.client, header(two.a.admin)
    for path in ("/categories", "/menu", "/modifiers", "/orders", "/tables", "/reservations", "/customers", "/settings", "/dashboard", "/kitchen"):
        r = c.get(A_url(two, path), headers=h)
        assert r.status_code == 200, (path, r.text[:200])
        assert "Bravo" not in r.text and "bravo" not in r.text, f"{path} leaked Bravo data"
    assert "Alpha" in c.get(A_url(two, "/menu"), headers=h).text                        # ...but does show its own


def test_platform_admin_can_reach_any_tenant_but_only_by_naming_it(two):
    c, s = two.client, header(two.superadmin)
    assert "Alpha" in c.get(f"{API}/admin/menu?restaurant_id={two.a.rid}", headers=s).text
    assert "Bravo" in c.get(f"{API}/admin/menu?restaurant_id={two.b.rid}", headers=s).text
    assert "Bravo" not in c.get(f"{API}/admin/menu?restaurant_id={two.a.rid}", headers=s).text     # no blending
    assert c.get(f"{API}/admin/menu?restaurant_id=99999999", headers=s).status_code == 404


# ============================================================================ 4. customer-facing attacks

def test_a_customer_cannot_order_from_another_restaurant(two):
    a, b = two.a, two.b
    body = {"order_type": "PICKUP", "customer_name": "x", "customer_email": a.customer.email,
            "items": [{"menu_item_id": b.item.id, "quantity": 1, "modifier_option_ids": []}]}
    assert two.client.post(f"{API}/orders", headers=header(a.customer), json={**body, "restaurant_id": b.rid}).status_code == 403
    # Own restaurant, but naming Bravo's menu item:
    r = two.client.post(f"{API}/orders", headers=header(a.customer), json={**body, "restaurant_id": a.rid})
    assert r.status_code == 400 and "invalid for this restaurant" in r.json()["detail"]


def test_a_customer_cannot_read_or_touch_another_restaurants_orders_and_bookings(two):
    c, a, b = two.client, two.a, two.b
    assert c.get(f"{API}/orders/{b.order_id}", headers=header(a.customer)).status_code == 404
    mine = c.get(f"{API}/orders", headers=header(a.customer)).json()
    assert {o["id"] for o in mine["items"]} == {a.order_id}
    assert c.get(f"{API}/reservations/me", headers=header(a.customer)).json() and \
        all(r["restaurant_id"] == a.rid for r in c.get(f"{API}/reservations/me", headers=header(a.customer)).json())
    for action in ("cancel", "confirm"):
        r = c.post(f"{API}/reservations/{b.reservation.id}/{action}", headers=header(a.customer))
        assert r.status_code in (400, 403, 404), (action, r.status_code)
    # Dine-in at own restaurant using Bravo's reservation.
    r = c.post(f"{API}/orders", headers=header(a.customer), json={
        "restaurant_id": a.rid, "order_type": "DINE_IN", "reservation_id": b.reservation.id, "customer_name": "x",
        "customer_email": a.customer.email, "items": [{"menu_item_id": a.item.id, "quantity": 1, "modifier_option_ids": []}]})
    assert r.status_code in (400, 404)


def test_a_customer_cannot_book_a_table_at_another_restaurant(two):
    a, b = two.a, two.b
    body = {"table_id": b.table.id, "party_size": 2, "starts_at": "2030-06-01T18:00:00Z", "guest_name": "x"}
    assert two.client.post(f"{API}/restaurants/{b.slug}/reservations", headers=header(a.customer), json=body).status_code == 403
    assert two.client.post(f"{API}/restaurants/{a.slug}/reservations", headers=header(a.customer), json=body).status_code in (400, 404)


def test_menu_items_are_only_served_within_their_own_restaurant(two):
    c, a, b = two.client, two.a, two.b
    assert c.get(f"{API}/menu/{a.item.id}?restaurant_id={a.rid}").status_code == 200
    assert c.get(f"{API}/menu/{b.item.id}?restaurant_id={a.rid}").status_code == 404      # can't enumerate across tenants
    assert c.get(f"{API}/menu/{a.item.id}").status_code == 422                            # tenant context is mandatory


def test_the_restaurant_directory_is_platform_only(two):
    c = two.client
    assert c.get(f"{API}/restaurants").status_code == 401
    assert c.get(f"{API}/restaurants", headers=header(two.a.customer)).status_code == 403
    assert c.get(f"{API}/restaurants", headers=header(two.a.admin)).status_code == 403     # even a restaurant admin can't list rivals
    slugs = {r["slug"] for r in c.get(f"{API}/restaurants", headers=header(two.superadmin)).json()}
    assert {two.a.slug, two.b.slug} <= slugs


def test_tokens_are_bound_to_the_tenant_they_were_issued_for(two):
    from app.core.security import create_access_token
    a, b = two.a, two.b
    good = header(a.customer)
    assert two.client.get(f"{API}/auth/me", headers=good).status_code == 200
    no_claim = {"Authorization": "Bearer " + create_access_token(str(a.customer.id), claims={"role": "CUSTOMER"})}
    wrong_claim = {"Authorization": "Bearer " + create_access_token(str(a.customer.id), claims={"role": "CUSTOMER", "tenant": b.rid})}
    assert two.client.get(f"{API}/auth/me", headers=no_claim).status_code == 401
    assert two.client.get(f"{API}/auth/me", headers=wrong_claim).status_code == 401


def snapshot(db, rid):
    """A fingerprint of everything a restaurant owns, to prove attacks changed nothing."""
    q = lambda sql: [tuple(r) for r in db.execute(text(sql), {"r": rid}).all()]
    return {
        "restaurant": q("SELECT name, description, tax_rate, delivery_fee, logo_url, is_active FROM restaurants WHERE id = :r"),
        "categories": q("SELECT id, name, slug, sort_order FROM categories WHERE restaurant_id = :r ORDER BY id"),
        "items": q("SELECT id, name, price, category_id, image_url, is_available FROM menu_items WHERE restaurant_id = :r ORDER BY id"),
        "modifiers": q("SELECT id, name FROM menu_modifiers WHERE restaurant_id = :r ORDER BY id"),
        "options": q("SELECT o.id, o.name, o.price_adjustment FROM menu_modifier_options o JOIN menu_modifiers m ON m.id = o.modifier_id WHERE m.restaurant_id = :r ORDER BY o.id"),
        "item_modifiers": q("SELECT l.menu_item_id, l.modifier_id FROM menu_item_modifiers l JOIN menu_items i ON i.id = l.menu_item_id WHERE i.restaurant_id = :r ORDER BY l.id"),
        "tables": q("SELECT id, table_number, capacity, status, pos_x, pos_y, is_active FROM restaurant_tables WHERE restaurant_id = :r ORDER BY id"),
        "orders": q("SELECT id, order_number, status, total FROM orders WHERE restaurant_id = :r ORDER BY id"),
        "reservations": q("SELECT id, table_id, status, guest_name, starts_at, ends_at FROM reservations WHERE restaurant_id = :r ORDER BY id"),
        "users": q("SELECT id, email, restaurant_id, is_active FROM users WHERE restaurant_id = :r ORDER BY id"),
    }


def test_after_every_attack_bravos_data_is_exactly_as_it_was(two):
    """Run every cross-tenant attempt above, then compare a full fingerprint of Bravo's data."""
    c, db = two.client, two.db
    before, before_a = snapshot(db, two.b.rid), snapshot(db, two.a.rid)

    for _name, method, path, body in IDOR:
        c.request(method, A_url(two, path(two)), headers=header(two.a.admin), json=body(two) if body else None)
    for role in (two.a.admin, two.a.staff, two.a.customer):
        for method, path in admin_routes():
            call(c, method, path, header(role), two.b.rid)
    two.client.post(f"{API}/orders", headers=header(two.a.customer), json={
        "restaurant_id": two.b.rid, "order_type": "PICKUP", "customer_name": "x", "customer_email": "x@x.com",
        "items": [{"menu_item_id": two.b.item.id, "quantity": 5, "modifier_option_ids": []}]})
    c.post(f"{API}/reservations/{two.b.reservation.id}/cancel", headers=header(two.a.customer))

    after = snapshot(db, two.b.rid)
    assert after == before, {k: (before[k], after[k]) for k in before if before[k] != after[k]}
    # Alpha must not have been altered by its own failed attempts either (other than legitimately created rows).
    assert snapshot(db, two.a.rid)["orders"] == before_a["orders"]
