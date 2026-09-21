"""Forgotten and changed passwords: emailed one-time links, changing while signed in, and what each one signs out."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core import rate_limit as rl
from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.password_reset_token import PasswordResetToken
from app.models.enums import RoleName
from tests.conftest import override_get_db
from tests.tenants import header, make_tenant, make_user

API = "/api/v1"
OLD = "Test1234!"
NEW = "Brand-New-Pass7"


@pytest.fixture
def world(client, db):
    app.dependency_overrides[get_db] = override_get_db(db)
    a, b = make_tenant(db, "Alpha"), make_tenant(db, "Bravo")
    yield type("W", (), {"client": client, "db": db, "a": a, "b": b})
    app.dependency_overrides.clear()


def emails(db, subject_contains=None):
    rows = db.execute(text("SELECT payload, restaurant_id FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    return [r for r in rows if subject_contains is None or subject_contains in r.payload["subject"]]


def forgot(w, email, restaurant_id=None):
    body = {"email": email, **({"restaurant_id": restaurant_id} if restaurant_id is not None else {})}
    return w.client.post(f"{API}/auth/forgot-password", json=body)


def latest_token(w):
    """The token from the newest reset email's link (what the person would click)."""
    text_body = emails(w.db, "Reset your password")[-1].payload["text"]
    return re.search(r"token=([\w-]+)", text_body).group(1)


def login(w, email, password, restaurant_id=None):
    body = {"email": email, "password": password, **({"restaurant_id": restaurant_id} if restaurant_id is not None else {})}
    return w.client.post(f"{API}/auth/login", json=body)


# ------------------------------------------------------------------ asking for a link

def test_a_reset_link_is_emailed_from_the_restaurants_own_site(world, monkeypatch):
    w = world
    monkeypatch.setattr(settings, "PLATFORM_DOMAIN", "dineflow.test")
    r = forgot(w, w.a.customer.email, w.a.rid)
    assert r.status_code == 200
    [mail] = emails(w.db, "Reset your password")
    assert mail.payload["to"] == w.a.customer.email and mail.payload["from_name"] == "Alpha Kitchen" and mail.restaurant_id == w.a.rid
    assert f"http://alpha-kitchen.dineflow.test:3000/reset-password?token=" in mail.payload["text"] or "alpha-kitchen.dineflow.test" in mail.payload["text"]
    assert "expires in 1 hour" in mail.payload["text"] and "Choose a new password" in mail.payload["html"]


def test_asking_reveals_nothing_about_who_has_an_account(world):
    w = world
    known = forgot(w, w.a.customer.email, w.a.rid)
    unknown = forgot(w, "nobody@iso-demo.com", w.a.rid)
    bad_site = forgot(w, w.a.customer.email, 999999)
    other_site = forgot(w, w.a.customer.email, w.b.rid)                  # Alpha's customer has no account at Bravo
    assert {r.status_code for r in (known, unknown, bad_site, other_site)} == {200}
    assert known.json() == unknown.json() == bad_site.json() == other_site.json()
    assert len(emails(w.db, "Reset your password")) == 1                  # only the real one


def test_staff_can_reset_from_any_site_and_inactive_accounts_get_nothing(world):
    w = world
    assert forgot(w, w.a.admin.email, w.a.rid).status_code == 200 and len(emails(w.db, "Reset")) == 1
    w.a.customer.is_active = False
    w.db.flush()
    forgot(w, w.a.customer.email, w.a.rid)
    assert len(emails(w.db, "Reset")) == 1


def test_an_inbox_cannot_be_flooded(world):
    w = world
    for _ in range(6):
        forgot(w, w.a.customer.email, w.a.rid)
    assert len(emails(w.db, "Reset your password")) == 3


# ------------------------------------------------------------------ using the link

def test_the_link_sets_a_new_password_once_and_signs_everyone_out(world):
    w = world
    email = w.a.customer.email
    old_session = login(w, email, OLD, w.a.rid).json()
    forgot(w, email, w.a.rid)
    token = latest_token(w)

    done = w.client.post(f"{API}/auth/reset-password", json={"token": token, "password": NEW})
    assert done.status_code == 200
    assert login(w, email, OLD, w.a.rid).status_code == 401 and login(w, email, NEW, w.a.rid).status_code == 200
    assert w.client.post(f"{API}/auth/refresh", json={"refresh_token": old_session["refresh_token"]}).status_code == 401   # old sessions end
    assert emails(w.db, "password was changed")[-1].payload["to"] == email                                                  # and they are told

    again = w.client.post(f"{API}/auth/reset-password", json={"token": token, "password": "Another-Pass8"})
    assert again.status_code == 400 and "invalid or has expired" in again.json()["detail"]                                  # one use only


def test_bad_expired_and_weak_attempts_change_nothing(world):
    w = world
    email = w.a.customer.email
    forgot(w, email, w.a.rid)
    token = latest_token(w)
    reset = lambda t, p: w.client.post(f"{API}/auth/reset-password", json={"token": t, "password": p})  # noqa: E731
    assert reset("x" * 40, NEW).status_code == 400                              # unknown token
    assert reset("short", NEW).status_code == 422                               # not even token-shaped
    for weak in ("onlyletters", "12345678", "Password123"):
        assert reset(token, weak).status_code == 400
    w.db.query(PasswordResetToken).update({"expires_at": datetime.now(UTC) - timedelta(minutes=1), "used_at": None})
    w.db.flush()
    assert reset(token, NEW).status_code == 400                                 # expired
    assert login(w, email, OLD, w.a.rid).status_code == 200                     # the old password still works


def test_a_password_containing_the_email_name_is_refused(world):
    w = world
    forgot(w, w.a.customer.email, w.a.rid)
    local = w.a.customer.email.split("@")[0]
    r = w.client.post(f"{API}/auth/reset-password", json={"token": latest_token(w), "password": f"{local}-9999"})
    assert r.status_code == 400 and "email name" in r.json()["detail"]


def test_a_new_link_spends_the_older_ones_when_used(world):
    w = world
    forgot(w, w.a.customer.email, w.a.rid)
    first = latest_token(w)
    forgot(w, w.a.customer.email, w.a.rid)
    second = latest_token(w)
    assert first != second
    assert w.client.post(f"{API}/auth/reset-password", json={"token": second, "password": NEW}).status_code == 200
    assert w.client.post(f"{API}/auth/reset-password", json={"token": first, "password": "Third-Pass-1"}).status_code == 400


def test_only_a_hash_of_the_token_is_stored(world):
    w = world
    forgot(w, w.a.customer.email, w.a.rid)
    token = latest_token(w)
    [row] = w.db.query(PasswordResetToken).all()
    assert row.token_hash != token and token not in row.token_hash and len(row.token_hash) == 64


# ------------------------------------------------------------------ while signed in

def test_changing_the_password_needs_the_current_one_and_keeps_only_this_session(world):
    w = world
    email = w.a.customer.email
    mine = login(w, email, OLD, w.a.rid).json()
    other_device = login(w, email, OLD, w.a.rid).json()
    auth = {"Authorization": f"Bearer {mine['access_token']}"}
    change = lambda cur, new: w.client.post(f"{API}/auth/change-password", headers=auth, json={"current_password": cur, "new_password": new})  # noqa: E731

    wrong = change("wrong-password-1", NEW)
    assert wrong.status_code == 400 and "current password" in wrong.json()["detail"]     # not 401: that would sign the person out
    assert w.client.get(f"{API}/auth/me", headers=auth).status_code == 200                # and they are still signed in
    assert change(OLD, OLD).status_code == 400                                   # must actually change
    assert change(OLD, "onlyletters").status_code == 400
    ok = change(OLD, NEW)
    assert ok.status_code == 200 and ok.json()["access_token"]
    fresh = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert w.client.get(f"{API}/auth/me", headers=fresh).status_code == 200      # this session carries on
    assert w.client.post(f"{API}/auth/refresh", json={"refresh_token": ok.json()["refresh_token"]}).status_code == 200
    assert w.client.post(f"{API}/auth/refresh", json={"refresh_token": other_device["refresh_token"]}).status_code == 401
    assert login(w, email, OLD, w.a.rid).status_code == 401 and login(w, email, NEW, w.a.rid).status_code == 200
    assert emails(w.db, "password was changed")


def test_changing_needs_to_be_signed_in(world):
    assert world.client.post(f"{API}/auth/change-password", json={"current_password": OLD, "new_password": NEW}).status_code == 401


# ------------------------------------------------------------------ abuse control

def test_asking_for_links_is_rate_limited_per_address_and_per_account(world, monkeypatch):
    w = world
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    rl.limiter.reset()
    try:
        codes = [forgot(w, "victim@iso-demo.com", w.a.rid).status_code for _ in range(6)]
        assert codes[:4] == [200] * 4 and codes[4:] == [429, 429]          # per account: 4 an hour
        other = [forgot(w, f"someone{i}@iso-demo.com", w.a.rid).status_code for i in range(6)]
        assert 429 in other                                                # per address: 8 in ten minutes, however many accounts
    finally:
        rl.limiter.reset()
