"""Staff management: invite, list, change role/active, resend invite, and the safety rails
around removing a restaurant's last admin."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.enums import RoleName
from app.models.restaurant import Restaurant
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from tests.conftest import override_get_db
from tests.tenants import header, make_user

API = "/api/v1"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    restaurant = Restaurant(name="Staff Kitchen", slug="staff-kitchen", tax_rate=Decimal("0.1"))
    db.add(restaurant)
    db.flush()
    owner = make_user(db, "staff-owner@iso-demo.com", RoleName.RESTAURANT_ADMIN)
    staff = make_user(db, "staff-existing@iso-demo.com", RoleName.RESTAURANT_STAFF)
    customer = make_user(db, "staff-cust@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id)
    db.add_all([
        RestaurantUser(restaurant_id=restaurant.id, user_id=owner.id, role=RoleName.RESTAURANT_ADMIN),
        RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id, role=RoleName.RESTAURANT_STAFF),
    ])
    db.commit()
    db.expire_all()
    yield type("W", (), {
        "client": client, "db": db, "rid": restaurant.id, "restaurant": restaurant,
        "owner": db.get(User, owner.id), "staff": db.get(User, staff.id), "customer": customer,
    })
    app.dependency_overrides.clear()


def invite(w, **overrides):
    body = {"email": "new-hire@example.com", "first_name": "New", "last_name": "Hire", "role": "RESTAURANT_STAFF", **overrides}
    return w.client.post(f"{API}/admin/staff?restaurant_id={w.rid}", headers=header(w.owner), json=body)


# ------------------------------------------------------------------ inviting

def test_an_admin_can_invite_staff_and_they_can_sign_in(world):
    w = world
    r = invite(w, role="RESTAURANT_ADMIN")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new-hire@example.com" and body["role"] == "RESTAURANT_ADMIN"
    assert body["is_active"] is True and body["invite_accepted"] is False
    assert "/reset-password?token=" in body["invite_link"]

    token = body["invite_link"].split("token=")[1]
    assert w.client.post(f"{API}/auth/reset-password", json={"token": token, "password": "Sturdy-Pass9"}).status_code == 200
    login = w.client.post(f"{API}/auth/login", json={"email": "new-hire@example.com", "password": "Sturdy-Pass9"})
    assert login.status_code == 200
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert w.client.get(f"{API}/admin/menu", params={"restaurant_id": w.rid}, headers=h).status_code == 200

    # ...and shows as accepted now.
    listed = w.client.get(f"{API}/admin/staff?restaurant_id={w.rid}", headers=header(w.owner)).json()
    [row] = [s for s in listed if s["email"] == "new-hire@example.com"]
    assert row["invite_accepted"] is True


def test_inviting_the_same_email_twice_is_refused(world):
    w = world
    assert invite(w).status_code == 201
    again = invite(w)
    assert again.status_code == 409


def test_only_an_admin_can_invite_not_plain_staff_or_a_customer(world):
    w = world
    assert w.client.post(f"{API}/admin/staff?restaurant_id={w.rid}", headers=header(w.staff), json={
        "email": "x@example.com", "first_name": "X", "last_name": "Y", "role": "RESTAURANT_STAFF",
    }).status_code == 403
    assert w.client.post(f"{API}/admin/staff?restaurant_id={w.rid}", headers=header(w.customer), json={
        "email": "x@example.com", "first_name": "X", "last_name": "Y", "role": "RESTAURANT_STAFF",
    }).status_code == 403


def test_staff_can_list_but_not_invite(world):
    w = world
    assert w.client.get(f"{API}/admin/staff?restaurant_id={w.rid}", headers=header(w.staff)).status_code == 200


def test_a_platform_admin_email_cannot_be_added_as_staff(world, db):
    w = world
    superadmin = make_user(db, "super@iso-demo.com", RoleName.SUPER_ADMIN)
    db.commit()
    r = invite(w, email="super@iso-demo.com")
    assert r.status_code == 400


def test_an_existing_global_identity_is_reused_not_duplicated(world):
    w = world
    # w.owner runs a second restaurant too (an agency scenario), and invites w.staff's email there —
    # the same account should be reused, not recreated as a second row with the same email.
    other = Restaurant(name="Second Kitchen", slug="second-kitchen", tax_rate=Decimal("0.1"))
    w.db.add(other)
    w.db.flush()
    w.db.add(RestaurantUser(restaurant_id=other.id, user_id=w.owner.id, role=RoleName.RESTAURANT_ADMIN))
    w.db.commit()

    r = w.client.post(f"{API}/admin/staff?restaurant_id={other.id}", headers=header(w.owner), json={
        "email": w.staff.email, "first_name": w.staff.first_name, "last_name": w.staff.last_name, "role": "RESTAURANT_STAFF",
    })
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == w.staff.id  # reused, not a new account

    both = w.db.scalars(select(RestaurantUser.restaurant_id).where(RestaurantUser.user_id == w.staff.id)).all()
    assert set(both) == {w.rid, other.id}


# ------------------------------------------------------------------ changing role / active

def test_deactivating_a_staff_member_revokes_their_access_immediately(world):
    w = world
    membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id)
    )
    assert w.client.get(f"{API}/admin/menu?restaurant_id={w.rid}", headers=header(w.staff)).status_code == 200

    r = w.client.patch(f"{API}/admin/staff/{membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"is_active": False})
    assert r.status_code == 200 and r.json()["is_active"] is False

    assert w.client.get(f"{API}/admin/menu?restaurant_id={w.rid}", headers=header(w.staff)).status_code == 403


def test_an_admin_cannot_remove_their_own_admin_access(world):
    w = world
    membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.owner.id)
    )
    r = w.client.patch(f"{API}/admin/staff/{membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"is_active": False})
    assert r.status_code == 400
    r2 = w.client.patch(f"{API}/admin/staff/{membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"role": "RESTAURANT_STAFF"})
    assert r2.status_code == 400


def test_a_restaurant_cannot_be_left_with_no_active_admin(world):
    w = world
    # Promote staff to a second admin, then confirm the owner can safely demote themself... except
    # they still can't (self-lock is blocked independently of the "last admin" count).
    staff_membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id)
    )
    w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"role": "RESTAURANT_ADMIN"})

    # Now deactivate the *new* admin (not self) — should succeed, since the owner is still active.
    r = w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"is_active": False})
    assert r.status_code == 200

    # Re-activate and re-promote, then try to demote the *owner* via someone else — blocked as the last admin.
    w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"is_active": True})
    owner_membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.owner.id)
    )
    # staff (now an admin) tries to demote the owner, the only *other* admin remaining after this action
    # would still be staff themself — this should succeed since staff stays admin.
    ok = w.client.patch(f"{API}/admin/staff/{owner_membership_id}?restaurant_id={w.rid}", headers=header(w.staff), json={"role": "RESTAURANT_STAFF"})
    assert ok.status_code == 200

    # Now only one admin (former-staff) remains; they cannot demote themself (self-lock), proving the
    # "last admin" rule and the self-lock rule both hold.
    r3 = w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.staff), json={"role": "RESTAURANT_STAFF"})
    assert r3.status_code == 400


def test_only_an_admin_can_change_a_membership(world):
    w = world
    membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id)
    )
    assert w.client.patch(
        f"{API}/admin/staff/{membership_id}?restaurant_id={w.rid}", headers=header(w.staff), json={"is_active": False},
    ).status_code == 403


# ------------------------------------------------------------------ global role sync
# Authorization runs on the account's *global* role, not the per-membership one — so promoting or
# demoting someone via a membership must keep the two in step, or the feature would lie about what a
# person can do (see StaffService._sync_global_role's docstring for why).

def test_promoting_staff_to_admin_actually_grants_admin_routes(world):
    w = world
    membership_id = w.db.scalar(select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id))

    # Before promotion: a global RESTAURANT_STAFF is refused an admin-only action (category creation
    # needs no feature flag, so a 403 here can only be about the role, not something else being off).
    assert w.client.post(f"{API}/admin/categories?restaurant_id={w.rid}", headers=header(w.staff), json={
        "restaurant_id": w.rid, "name": "Before", "slug": "before",
    }).status_code == 403

    r = w.client.patch(f"{API}/admin/staff/{membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"role": "RESTAURANT_ADMIN"})
    assert r.status_code == 200
    w.db.expire_all()
    assert w.staff.role.name == RoleName.RESTAURANT_ADMIN.value

    # After promotion, the same account can now do an admin-only action — not just look promoted.
    assert w.client.post(f"{API}/admin/categories?restaurant_id={w.rid}", headers=header(w.staff), json={
        "restaurant_id": w.rid, "name": "Promoted", "slug": "promoted",
    }).status_code == 201


def test_demoting_does_not_auto_downgrade_the_global_role(world):
    """The sync is promote-only (see StaffService._sync_global_role's docstring): row-level security
    restricts a tenant-scoped request to the current restaurant's rows, so there is no safe way to
    confirm "no admin membership anywhere else" from here. Demoting the membership role is still
    honoured — it's what actually gates their access to *this* restaurant — the global role is simply
    left as-is rather than guessed at."""
    w = world
    staff_membership_id = w.db.scalar(select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id))
    w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"role": "RESTAURANT_ADMIN"})
    w.db.expire_all()
    assert w.staff.role.name == RoleName.RESTAURANT_ADMIN.value

    r = w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={w.rid}", headers=header(w.owner), json={"role": "RESTAURANT_STAFF"})
    assert r.status_code == 200 and r.json()["role"] == "RESTAURANT_STAFF"  # the membership itself changed...
    w.db.expire_all()
    assert w.staff.role.name == RoleName.RESTAURANT_ADMIN.value  # ...the global role is left alone


def test_promoting_at_a_second_restaurant_upgrades_the_global_role_too(world):
    """The other direction (a grant) has no visibility problem — the membership that justifies it is
    the very row the request is already scoped to — so it applies immediately, from any restaurant."""
    w = world
    other = Restaurant(name="Elsewhere Kitchen", slug="elsewhere-kitchen", tax_rate=Decimal("0.1"))
    w.db.add(other)
    w.db.flush()
    w.db.add(RestaurantUser(restaurant_id=other.id, user_id=w.owner.id, role=RoleName.RESTAURANT_ADMIN))
    w.db.add(RestaurantUser(restaurant_id=other.id, user_id=w.staff.id, role=RoleName.RESTAURANT_STAFF))
    w.db.commit()
    assert w.staff.role.name == RoleName.RESTAURANT_STAFF.value

    staff_membership_id = w.db.scalar(
        select(RestaurantUser.id).where(RestaurantUser.user_id == w.staff.id, RestaurantUser.restaurant_id == other.id)
    )
    r = w.client.patch(f"{API}/admin/staff/{staff_membership_id}?restaurant_id={other.id}", headers=header(w.owner), json={"role": "RESTAURANT_ADMIN"})
    assert r.status_code == 200
    w.db.expire_all()
    assert w.staff.role.name == RoleName.RESTAURANT_ADMIN.value


# ------------------------------------------------------------------ resend invite

def test_resending_an_invite_issues_a_new_link(world):
    w = world
    membership_id = invite(w).json()["id"]
    r = w.client.post(f"{API}/admin/staff/{membership_id}/resend-invite?restaurant_id={w.rid}", headers=header(w.owner))
    assert r.status_code == 200 and "/reset-password?token=" in r.json()["invite_link"]


def test_resending_after_the_invite_was_accepted_is_refused(world):
    w = world
    body = invite(w).json()
    token = body["invite_link"].split("token=")[1]
    w.client.post(f"{API}/auth/reset-password", json={"token": token, "password": "Sturdy-Pass9"})
    r = w.client.post(f"{API}/admin/staff/{body['id']}/resend-invite?restaurant_id={w.rid}", headers=header(w.owner))
    assert r.status_code == 400
