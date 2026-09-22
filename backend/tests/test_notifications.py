"""Customer emails: what is queued, what it says, how it is escaped and sent."""

import smtplib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core import email as mail
from app.core.config import settings
from app.jobs.handlers import HANDLERS, JobContext
from app.models.reservation import Reservation
from app.services import notifications
from tests.test_admin_management import place_order, url as admin_url, world as menu_world  # noqa: F401
from tests.test_reservation_flows import _admin_book, _book, _iso, _now, world as floor_world  # noqa: F401


@pytest.fixture(autouse=True)
def memory_mail():
    backend = mail.MemoryBackend()
    mail.set_email_backend(backend)
    yield backend
    mail.set_email_backend(None)


def queued(db, subject_contains=None):
    rows = db.execute(text("SELECT id, payload, restaurant_id, dedupe_key, status FROM jobs WHERE type = 'send_email' ORDER BY id")).all()
    return [r for r in rows if subject_contains is None or subject_contains in r.payload["subject"]]


def deliver(db, memory_mail):
    """What the worker does with each due, still-queued email job (in the test's own transaction) — a cancelled
    reminder, for instance, is never claimed and so never delivered, same as the real worker."""
    for row in queued(db):
        if row.status != "queued":
            continue
        HANDLERS["send_email"](row.payload, JobContext(job_id=row.id, attempt=1, restaurant_id=row.restaurant_id))
    return memory_mail.outbox


# ---------------------------------------------------------------- orders

def test_placing_an_order_queues_a_branded_confirmation(menu_world, memory_mail):
    w = menu_world
    r = place_order(w, notes="ignored here", items=[{"menu_item_id": w.item.id, "quantity": 2, "modifier_option_ids": [],
                                                       "special_instructions": "No onions"}])
    assert r.status_code == 201
    [job] = queued(w.db)
    p = job.payload
    assert p["to"] == "am-cust@demo.com" and p["from_name"] == "Alpha" and job.restaurant_id == w.a.id
    assert f"Order {r.json()['order_number']} confirmed" in p["subject"]
    assert "2x Burger" in p["text"] and "Note: No onions" in p["text"] and f"Total: ${r.json()['total']}" in p["text"]
    assert f"/orders/{r.json()['id']}" in p["text"] and "Track your order" in p["html"]

    [sent] = deliver(w.db, memory_mail)
    assert sent.to == "am-cust@demo.com" and sent.from_name == "Alpha" and sent.html.startswith("<!doctype html>")


def test_user_supplied_text_is_html_escaped_in_emails(menu_world):
    w = menu_world
    r = place_order(w, customer_name='<script>alert("x")</script>', items=[{
        "menu_item_id": w.item.id, "quantity": 1, "modifier_option_ids": [], "special_instructions": '<img src=x onerror=alert(1)>'}])
    assert r.status_code == 201
    html = queued(w.db)[0].payload["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html
    assert '<img src=x onerror=alert(1)>' in queued(w.db)[0].payload["text"]             # plain text stays literal


def test_the_same_order_can_never_queue_two_emails(menu_world):
    w = menu_world
    r = place_order(w)
    assert len(queued(w.db)) == 1
    order = w.db.execute(text("SELECT id FROM orders WHERE order_number = :n"), {"n": r.json()["order_number"]}).one()
    assert queued(w.db)[0].dedupe_key == f"email:order:{order.id}:placed"


def test_a_failed_order_queues_nothing(menu_world):
    w = menu_world
    bad = place_order(w, items=[{"menu_item_id": 987654, "quantity": 1, "modifier_option_ids": []}])
    assert bad.status_code == 400 and queued(w.db) == []


def test_logo_urls_in_emails_are_absolute():
    class R:
        name = "X"; logo_url = "/uploads/tenants/1/branding/a.webp"; phone = None; address = None
    assert notifications._logo_url(R) == f"{settings.PUBLIC_API_URL.rstrip('/')}/uploads/tenants/1/branding/a.webp"
    R.logo_url = "https://cdn.example.com/l.png"
    assert notifications._logo_url(R) == "https://cdn.example.com/l.png"
    R.logo_url = None
    assert notifications._logo_url(R) is None


# ---------------------------------------------------------------- reservations

def test_booking_and_cancelling_send_emails(floor_world, memory_mail):
    w = floor_world
    start = _now() + timedelta(hours=5)
    res = _book(w, w.t1, start).json()
    [confirmed] = queued(w.db, "is booked")
    assert confirmed.payload["to"] == "rf-cust@demo.com" and "party of 2, table T1" in confirmed.payload["text"]
    assert "UTC" in confirmed.payload["text"]                                            # honest about the time zone for now

    assert w.client.post(f"/api/v1/reservations/{res['id']}/cancel", headers=w.ch).status_code == 200
    [cancelled] = queued(w.db, "was cancelled")
    assert "cancelled" in cancelled.payload["text"] and cancelled.dedupe_key == f"email:reservation:{res['id']}:cancelled"
    assert len(deliver(w.db, memory_mail)) == 2


def test_staff_cancelling_a_booking_emails_the_guest(floor_world):
    w = floor_world
    res = _book(w, w.t1, _now() + timedelta(hours=5)).json()
    w.client.patch(f"/api/v1/admin/reservations/{res['id']}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "CANCELLED"})
    assert len(queued(w.db, "was cancelled")) == 1


def test_releasing_a_table_emails_guests_whose_booking_was_cancelled(floor_world):
    w = floor_world
    _book(w, w.t1, _now() + timedelta(minutes=30))
    r = w.client.patch(f"/api/v1/admin/tables/{w.t1.id}/status?restaurant_id={w.rid}", headers=w.ah, json={"status": "AVAILABLE", "force": True})
    assert r.json()["cancelled_reservations"] == 1 and len(queued(w.db, "was cancelled")) == 1


def test_walk_ins_and_bookings_without_an_email_send_nothing(floor_world):
    w = floor_world
    seated = _admin_book(w, w.t1, _now(), name="Walk In", seat_immediately=True)
    assert seated.status_code == 201
    no_mail = _admin_book(w, w.t2, _now() + timedelta(hours=4), name="Phone Booking")          # staff booking, no email, no user
    assert no_mail.status_code == 201
    assert queued(w.db) == []
    with_mail = _admin_book(w, w.t3, _now() + timedelta(hours=6), name="Emailed", guest_email="guest@example.com")
    assert with_mail.status_code == 201
    # Confirmation now, and (6h notice is plenty) a reminder queued for later — both addressed to the guest.
    assert [j.payload["to"] for j in queued(w.db, "is booked")] == ["guest@example.com"]
    assert [j.payload["to"] for j in queued(w.db, "See you soon")] == ["guest@example.com"]


def test_confirming_a_hold_sends_the_confirmation(floor_world):
    w = floor_world
    held = _book(w, w.t1, _now() + timedelta(hours=5), hold=True).json()
    assert held["status"] == "HELD" and queued(w.db) == []                                       # holds are provisional: no email yet
    assert w.client.post(f"/api/v1/reservations/{held['id']}/confirm", headers=w.ch).status_code == 200
    assert len(queued(w.db, "is booked")) == 1


# ---------------------------------------------------------------- message building & backends

def test_headers_cannot_be_injected():
    msg = mail.EmailMessage(to="a@b.com", subject="Hello\r\nBcc: evil@x.com", text="hi", from_name="Cafe\r\nBcc: evil@x.com",
                            reply_to="owner@cafe.com", extra_headers={"X-Test": "1\r\nBcc: evil@x.com"})
    mime = msg.to_mime()
    assert mime["Bcc"] is None and "\n" not in mime["Subject"] and "\n" not in mime["From"] and "\n" not in mime["X-Test"]
    assert mime["Reply-To"] == "owner@cafe.com" and settings.EMAIL_FROM_ADDRESS in mime["From"]
    for bad in ("a@b.com\nBcc:x@y.com", "not-an-email", "a@b", "a b@c.com", "a@b.com,c@d.com"):
        with pytest.raises(ValueError):
            mail.EmailMessage(to=bad, subject="s", text="t").to_mime()
    assert mail.EmailMessage(to="a@b.com", subject="s", text="t", reply_to="garbage").to_mime()["Reply-To"] is None


def test_message_has_a_text_part_and_an_html_alternative():
    mime = mail.EmailMessage(to="a@b.com", subject="s", text="plain", html="<p>rich</p>").to_mime()
    assert mime.is_multipart() and [p.get_content_type() for p in mime.iter_parts()] == ["text/plain", "text/html"]
    assert not mail.EmailMessage(to="a@b.com", subject="s", text="plain").to_mime().is_multipart()


def test_smtp_backend_uses_starttls_login_and_sends(monkeypatch):
    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): events.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): events.append(("quit",))
        def starttls(self, context=None): events.append(("starttls",))
        def login(self, user, password): events.append(("login", user, password))
        def send_message(self, msg): events.append(("send", msg["To"], msg["Subject"]))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for name, value in dict(EMAIL_SMTP_HOST="smtp.example.com", EMAIL_SMTP_PORT=587, EMAIL_SMTP_USER="u", EMAIL_SMTP_PASSWORD="p", EMAIL_SMTP_SECURITY="starttls").items():
        monkeypatch.setattr(settings, name, value)
    mail.SmtpBackend().send(mail.EmailMessage(to="a@b.com", subject="Hi", text="t"))
    assert events == [("connect", "smtp.example.com", 587), ("starttls",), ("login", "u", "p"), ("send", "a@b.com", "Hi"), ("quit",)]

    monkeypatch.setattr(settings, "EMAIL_SMTP_HOST", "")
    with pytest.raises(RuntimeError, match="EMAIL_SMTP_HOST"):
        mail.SmtpBackend().send(mail.EmailMessage(to="a@b.com", subject="Hi", text="t"))


def test_backend_selection(monkeypatch):
    mail.set_email_backend(None)
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "console")
    assert isinstance(mail.get_email_backend(), mail.ConsoleBackend)
    mail.set_email_backend(None)
    monkeypatch.setattr(settings, "EMAIL_BACKEND", "smtp")
    assert isinstance(mail.get_email_backend(), mail.SmtpBackend)
    mail.set_email_backend(None)


def test_a_bad_recipient_makes_the_job_fail_so_it_can_be_retried_or_parked():
    with pytest.raises(ValueError):
        HANDLERS["send_email"]({"to": "nope", "subject": "s", "text": "t"}, JobContext(1, 1, None))
