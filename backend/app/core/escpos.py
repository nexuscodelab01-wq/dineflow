"""ESC/POS bytes for a receipt — the command set almost every thermal receipt printer (Epson, Star in emulation,
Bixolon, generic 80mm/58mm network printers) understands. Pure functions, so they can be tested without a printer."""

from decimal import Decimal

from app.schemas.receipt import Receipt

INIT = b"\x1b@"
ALIGN_LEFT, ALIGN_CENTER = b"\x1ba\x00", b"\x1ba\x01"
BOLD_ON, BOLD_OFF = b"\x1bE\x01", b"\x1bE\x00"
DOUBLE_ON, DOUBLE_OFF = b"\x1d!\x11", b"\x1d!\x00"
FEED_AND_CUT = b"\n\n\n\x1dVB\x00"
# ESC p m t1 t2: pulse pin 2 for ~50ms — what opens a cash drawer wired to the printer's RJ11 port.
DRAWER_KICK = b"\x1bp\x00\x19\xfa"


def _money(value: Decimal) -> str:
    return f"${value:.2f}"


def _row(left: str, right: str, width: int) -> bytes:
    gap = max(1, width - len(left) - len(right))
    if len(left) + len(right) + 1 > width:  # too long for one line: let the name wrap, keep the amount on the right
        left = left[: max(1, width - len(right) - 1)]
        gap = max(1, width - len(left) - len(right))
    return (left + " " * gap + right + "\n").encode("cp437", "replace")


def _text(value: str) -> bytes:
    return (value + "\n").encode("cp437", "replace")


def render(receipt: Receipt, *, width: int = 42, drawer_kick: bool = False) -> bytes:
    out = bytearray(INIT)
    if drawer_kick:
        out += DRAWER_KICK
    out += ALIGN_CENTER + BOLD_ON + DOUBLE_ON + _text(receipt.restaurant_name[:width // 2]) + DOUBLE_OFF + BOLD_OFF
    for line in receipt.address_lines:
        out += _text(line)
    if receipt.phone:
        out += _text(receipt.phone)
    out += _text("")
    out += BOLD_ON + _text(receipt.title.upper()) + BOLD_OFF
    out += _text(receipt.reference)
    out += _text(receipt.printed_at.strftime("%Y-%m-%d %H:%M"))
    if receipt.served_by:
        out += _text(f"Served by {receipt.served_by}")
    out += ALIGN_LEFT + _text("-" * width)
    for item in receipt.lines:
        out += _row(f"{item.quantity} x {item.name}", _money(item.amount), width)
        for option in item.options:
            out += _text(f"    + {option}")
        if item.discount > 0:
            out += _text(f"    discount -{_money(item.discount)}")
        if item.note:
            out += _text(f"    note: {item.note}")
    out += _text("-" * width)
    out += _row("Subtotal", _money(receipt.subtotal), width)
    if receipt.discount > 0:
        out += _row("Discount", "-" + _money(receipt.discount), width)
    if receipt.service_charge > 0:
        out += _row("Service charge", _money(receipt.service_charge), width)
    if receipt.delivery_fee > 0:
        out += _row("Delivery", _money(receipt.delivery_fee), width)
    out += _row("Tax", _money(receipt.tax), width)
    out += BOLD_ON + _row("TOTAL", _money(receipt.total), width) + BOLD_OFF
    if receipt.tip > 0:
        out += _row("Tip", _money(receipt.tip), width)
    out += _text("-" * width)
    for payment in receipt.payments:
        if payment.status == "COMPLETED":
            out += _row(f"Paid ({payment.method.title()})", _money(payment.amount), width)
    if receipt.balance > 0:
        out += BOLD_ON + _row("BALANCE DUE", _money(receipt.balance), width) + BOLD_OFF
    out += ALIGN_CENTER + _text("") + _text(receipt.footer) + FEED_AND_CUT
    return bytes(out)
