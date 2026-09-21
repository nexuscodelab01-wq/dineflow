"""Sending email through a swappable backend.

Application code never sends mail directly: it queues a `send_email` job (see app/jobs), so a slow
or failing mail server can never slow down or break an order. This module is what that job calls.
"""

import logging
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, make_msgid
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")


def clean_header(value: str) -> str:
    """Header values must be a single line — stripping CR/LF blocks header-injection attacks."""
    return re.sub(r"[\r\n]+", " ", value or "").strip()


@dataclass
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    from_name: str | None = None  # shown as the sender name, e.g. the restaurant
    reply_to: str | None = None
    extra_headers: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not _EMAIL_RE.match(self.to):
            raise ValueError(f"Invalid recipient address: {self.to!r}")
        if self.reply_to and not _EMAIL_RE.match(self.reply_to):
            self.reply_to = None  # a bad reply-to shouldn't stop the message

    def to_mime(self) -> MimeMessage:
        self.validate()
        msg = MimeMessage()
        msg["From"] = formataddr((clean_header(self.from_name or ""), settings.EMAIL_FROM_ADDRESS))
        msg["To"] = self.to
        msg["Subject"] = clean_header(self.subject)
        msg["Message-ID"] = make_msgid(domain=settings.EMAIL_FROM_ADDRESS.split("@")[-1])
        if self.reply_to:
            msg["Reply-To"] = self.reply_to
        for name, value in self.extra_headers.items():
            msg[clean_header(name)] = clean_header(value)
        msg.set_content(self.text)
        if self.html:
            msg.add_alternative(self.html, subtype="html")
        return msg


class EmailBackend(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleBackend:
    """Development: print what would be sent."""

    def send(self, message: EmailMessage) -> None:
        message.validate()
        logger.info("EMAIL (console) to=%s from=%s subject=%r\n%s", message.to, message.from_name, message.subject, message.text)


class MemoryBackend:
    """Tests: collect messages instead of sending them."""

    def __init__(self) -> None:
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        message.validate()
        self.outbox.append(message)


class SmtpBackend:
    def send(self, message: EmailMessage) -> None:
        mime = message.to_mime()
        host, port, mode = settings.EMAIL_SMTP_HOST, settings.EMAIL_SMTP_PORT, settings.EMAIL_SMTP_SECURITY.lower()
        if not host:
            raise RuntimeError("EMAIL_BACKEND=smtp needs EMAIL_SMTP_HOST")
        context = ssl.create_default_context()
        client = smtplib.SMTP_SSL(host, port, timeout=20, context=context) if mode == "ssl" else smtplib.SMTP(host, port, timeout=20)
        with client:
            if mode == "starttls":
                client.starttls(context=context)
            if settings.EMAIL_SMTP_USER:
                client.login(settings.EMAIL_SMTP_USER, settings.EMAIL_SMTP_PASSWORD)
            client.send_message(mime)


_backend: EmailBackend | None = None


def get_email_backend() -> EmailBackend:
    global _backend
    if _backend is None:
        kind = settings.EMAIL_BACKEND.lower()
        if kind == "smtp":
            _backend = SmtpBackend()
        elif kind == "memory":
            _backend = MemoryBackend()
        else:
            if settings.is_production and kind == "console":
                logger.warning("EMAIL_BACKEND=console in production: emails are only logged, not delivered")
            _backend = ConsoleBackend()
    return _backend


def set_email_backend(backend: EmailBackend | None) -> None:
    """Swap the backend (tests)."""
    global _backend
    _backend = backend
