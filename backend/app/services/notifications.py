"""Customer emails: branded confirmations queued as background jobs.

Everything is rendered when the event happens and queued in the same database transaction as the
order/booking itself (so no email for something that rolled back, and none lost after it committed).
All user-supplied text is HTML-escaped.
"""

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.hours import to_local
from app.jobs.queue import cancel_by_dedupe_key, enqueue

logger = logging.getLogger(__name__)

DEFAULT_COLOR = "#2c6f53"


def _logo_url(restaurant) -> str | None:
    url = getattr(restaurant, "logo_url", None)
    if not url:
        return None
    return url if url.startswith(("http://", "https://")) else f"{settings.PUBLIC_API_URL.rstrip('/')}{url}"


def _when(value: datetime, restaurant=None) -> str:
    """A reservation time in the restaurant's own timezone (falls back to UTC when there is none to hand)."""
    if restaurant is not None:
        local = to_local(restaurant, value)
        tz = getattr(restaurant, "timezone", None) or "UTC"
        return local.strftime(f"%a, %b %d, %I:%M %p {tz}").replace(" 0", " ")
    return value.astimezone(timezone.utc).strftime("%a, %b %d, %I:%M %p UTC").replace(" 0", " ")


def _layout(restaurant, heading: str, body_html: str, footer: str = "") -> str:
    name = escape(restaurant.name)
    logo = _logo_url(restaurant)
    header = (
        f'<img src="{escape(logo, quote=True)}" alt="{name}" style="max-height:48px;max-width:200px">' if logo else f'<span style="font-size:20px;font-weight:700">{name}</span>'
    )
    contact = " · ".join(escape(p) for p in (getattr(restaurant, "phone", None), getattr(restaurant, "address", None)) if p)
    return f"""<!doctype html><html><body style="margin:0;background:#f7f5f1;font-family:Arial,Helvetica,sans-serif;color:#1a1f1c">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden">
<tr><td style="background:{DEFAULT_COLOR};padding:18px 24px;color:#ffffff">{header}</td></tr>
<tr><td style="padding:24px"><h1 style="margin:0 0 12px;font-size:20px">{escape(heading)}</h1>{body_html}</td></tr>
<tr><td style="padding:16px 24px;background:#f1efe9;font-size:12px;color:#6b6f6c">{footer}{escape(restaurant.name)}{(' · ' + contact) if contact else ''}</td></tr>
</table></td></tr></table></body></html>"""


def _queue_email(
    db: Session, restaurant, to: str | None, subject: str, text: str, html: str, dedupe_key: str, *, run_at=None,
) -> None:
    if not to:
        return
    enqueue(
        db,
        "send_email",
        {
            "to": to,
            "subject": subject,
            "text": text,
            "html": html,
            "from_name": restaurant.name,
            "reply_to": getattr(restaurant, "email", None),
        },
        restaurant_id=restaurant.id,
        dedupe_key=dedupe_key,  # the same event can never queue the same email twice
        run_at=run_at,
    )


# ---------------------------------------------------------------------------------- orders

def notify_order_placed(db: Session, restaurant, order, lines: list[dict[str, Any]]) -> None:
    """`lines`: [{"quantity", "name", "options": [str], "instructions"}] captured while the order was built."""
    type_label = {"DINE_IN": "Dine-in", "PICKUP": "Pickup", "DELIVERY": "Delivery"}.get(getattr(order.order_type, "value", order.order_type), "Order")
    subject = f"Order {order.order_number} confirmed — {restaurant.name}"
    track = f"{settings.PUBLIC_SITE_URL.rstrip('/')}/orders/{order.id}"

    text_lines = [f"Hi {order.customer_name},", "", f"Thanks! Your {type_label.lower()} order {order.order_number} is confirmed.", ""]
    html_items = []
    for line in lines:
        text_lines.append(f"{line['quantity']}x {line['name']}")
        item_html = f"<strong>{line['quantity']}×</strong> {escape(line['name'])}"
        for option in line.get("options", []):
            text_lines.append(f"    + {option}")
            item_html += f'<div style="color:#6b6f6c;font-size:13px">+ {escape(option)}</div>'
        if line.get("instructions"):
            text_lines.append(f"    Note: {line['instructions']}")
            item_html += f'<div style="font-size:13px">Note: {escape(line["instructions"])}</div>'
        html_items.append(f'<li style="margin-bottom:8px">{item_html}</li>')
    text_lines += ["", f"Total: ${order.total}", "", f"Track your order: {track}", "", f"— {restaurant.name}"]

    body = (
        f"<p>Hi {escape(order.customer_name)}, thanks! Your {escape(type_label.lower())} order <strong>{escape(order.order_number)}</strong> is confirmed.</p>"
        f'<ul style="padding-left:18px;margin:16px 0">{"".join(html_items)}</ul>'
        f'<p style="font-size:16px"><strong>Total: ${escape(str(order.total))}</strong></p>'
        f'<p><a href="{escape(track, quote=True)}" style="display:inline-block;background:{DEFAULT_COLOR};color:#ffffff;padding:10px 18px;border-radius:8px;text-decoration:none">Track your order</a></p>'
    )
    _queue_email(db, restaurant, order.customer_email, subject, "\n".join(text_lines), _layout(restaurant, "Order confirmed", body), f"email:order:{order.id}:placed")


# ---------------------------------------------------------------------------------- reservations

def _reservation_details(reservation, table_number: str | None, restaurant=None) -> tuple[str, str]:
    table = f", table {table_number}" if table_number else ""
    line = f"{_when(reservation.starts_at, restaurant)} · party of {reservation.party_size}{table}"
    return line, escape(line)


def notify_reservation_confirmed(db: Session, restaurant, reservation, table_number: str | None, manage_link: str | None = None) -> None:
    text_line, html_line = _reservation_details(reservation, table_number, restaurant)
    subject = f"Your table at {restaurant.name} is booked"
    text = f"Hi {reservation.guest_name},\n\nYour reservation is confirmed:\n{text_line}\n\nNeed to change it?"
    text += f" {manage_link}\n\nThis link works until shortly after your booking time." if manage_link else f" Sign in at {settings.PUBLIC_SITE_URL.rstrip('/')}/reserve or contact us."
    text += f"\n\n— {restaurant.name}"
    manage = (
        _button(manage_link, "Manage your reservation")
        if manage_link else
        f'<p>Need to change it? <a href="{escape(settings.PUBLIC_SITE_URL.rstrip("/") + "/reserve", quote=True)}">Manage your reservation</a> or contact us.</p>'
    )
    body = (
        f"<p>Hi {escape(reservation.guest_name)}, your reservation is confirmed:</p>"
        f'<p style="font-size:16px;background:#f1efe9;padding:12px 16px;border-radius:8px"><strong>{html_line}</strong></p>'
        f"{manage}"
    )
    _queue_email(db, restaurant, reservation.guest_email, subject, text, _layout(restaurant, "You're booked", body), f"email:reservation:{reservation.id}:confirmed")


def notify_reservation_cancelled(db: Session, restaurant, reservation, table_number: str | None) -> None:
    text_line, html_line = _reservation_details(reservation, table_number, restaurant)
    subject = f"Your reservation at {restaurant.name} was cancelled"
    text = f"Hi {reservation.guest_name},\n\nYour reservation has been cancelled:\n{text_line}\n\nWe'd love to see you another time: {settings.PUBLIC_SITE_URL.rstrip('/')}/reserve\n\n— {restaurant.name}"
    body = (
        f"<p>Hi {escape(reservation.guest_name)}, your reservation has been cancelled:</p>"
        f'<p style="font-size:16px;background:#f1efe9;padding:12px 16px;border-radius:8px"><s>{html_line}</s></p>'
        f'<p>We\'d love to see you another time — <a href="{escape(settings.PUBLIC_SITE_URL.rstrip("/") + "/reserve", quote=True)}">book a table</a>.</p>'
    )
    _queue_email(db, restaurant, reservation.guest_email, subject, text, _layout(restaurant, "Reservation cancelled", body), f"email:reservation:{reservation.id}:cancelled")


# ---------------------------------------------------------------------------------- accounts

class _Platform:
    """Stands in for a restaurant when an email is not about one (e.g. a platform admin resetting a password)."""

    id = None
    name = "DineFlow"
    logo_url = None
    phone = None
    address = None
    email = None
    custom_domain = None
    slug = ""


def _button(link: str, label: str) -> str:
    return (
        f'<p><a href="{escape(link, quote=True)}" style="display:inline-block;background:{DEFAULT_COLOR};color:#ffffff;'
        f'padding:10px 18px;border-radius:8px;text-decoration:none">{escape(label)}</a></p>'
        f'<p style="font-size:12px;color:#6b6f6c;word-break:break-all">If the button does not work, copy this address into your browser:<br>{escape(link)}</p>'
    )


def notify_password_reset(db: Session, restaurant, to: str, first_name: str, link: str, token_id: int, *, invite: bool = False, hours: int = 1) -> None:
    restaurant = restaurant or _Platform()
    valid = f"{hours} hour{'s' if hours != 1 else ''}" if hours < 48 else f"{hours // 24} days"
    if invite:
        subject, heading = f"Set your password — {restaurant.name}", "Welcome! Set your password"
        intro = f"Your {restaurant.name} account is ready. Choose a password to sign in."
    else:
        subject, heading = f"Reset your password — {restaurant.name}", "Reset your password"
        intro = "We received a request to reset your password. If it was you, choose a new one with the link below."
    text = f"Hi {first_name},\n\n{intro}\n\n{link}\n\nThis link works once and expires in {valid}."
    if not invite:
        text += "\nIf you did not ask for this, you can ignore this email: your password stays the same."
    html = _layout(
        restaurant, heading,
        f"<p>Hi {escape(first_name)},</p><p>{escape(intro)}</p>{_button(link, 'Set your password' if invite else 'Choose a new password')}"
        f"<p style=\"font-size:13px\">This link works once and expires in {escape(valid)}."
        f"{'' if invite else ' If you did not ask for this, ignore this email: your password stays the same.'}</p>",
    )
    _queue_email(db, restaurant, to, subject, text, html, dedupe_key=f"pwreset:{token_id}")


def notify_password_changed(db: Session, restaurant, to: str, first_name: str, event_id: str) -> None:
    restaurant = restaurant or _Platform()
    subject = f"Your password was changed — {restaurant.name}"
    text = (
        f"Hi {first_name},\n\nThe password for your {restaurant.name} account was just changed, and you were signed out "
        "everywhere. If this was you, nothing more to do. If it was not, reset your password straight away."
    )
    html = _layout(
        restaurant, "Your password was changed",
        f"<p>Hi {escape(first_name)},</p><p>The password for your {escape(restaurant.name)} account was just changed, and you were "
        "signed out everywhere.</p><p>If this was you, there is nothing more to do. <strong>If it was not, reset your password straight away.</strong></p>",
    )
    _queue_email(db, restaurant, to, subject, text, html, dedupe_key=f"pwchanged:{event_id}")


def reminder_dedupe_key(reservation_id: int) -> str:
    return f"email:reservation:{reservation_id}:reminder"


def notify_reservation_reminder(db: Session, restaurant, reservation, table_number: str | None, run_at, manage_link: str | None = None) -> None:
    """Queued ahead of time (`run_at` = a few hours before the booking); the wording avoids "confirmed" since
    this arrives long after that email did."""
    text_line, html_line = _reservation_details(reservation, table_number, restaurant)
    subject = f"See you soon — your table at {restaurant.name}"
    text = f"Hi {reservation.guest_name},\n\nJust a reminder about your reservation:\n{text_line}\n\nWe're looking forward to it!"
    text += f"\n\nLet us know you're coming, or cancel if your plans changed: {manage_link}" if manage_link else ""
    text += f"\n\n— {restaurant.name}"
    manage = (
        f'<p>{_button(manage_link, "I\'ll be there / Cancel")}</p>'
        if manage_link else ""
    )
    body = (
        f"<p>Hi {escape(reservation.guest_name)}, just a reminder about your reservation:</p>"
        f'<p style="font-size:16px;background:#f1efe9;padding:12px 16px;border-radius:8px"><strong>{html_line}</strong></p>'
        "<p>We're looking forward to it!</p>"
        f"{manage}"
    )
    _queue_email(db, restaurant, reservation.guest_email, subject, text, _layout(restaurant, "See you soon", body), reminder_dedupe_key(reservation.id), run_at=run_at)


def cancel_reservation_reminder(db: Session, reservation_id: int) -> None:
    cancel_by_dedupe_key(db, reminder_dedupe_key(reservation_id))
