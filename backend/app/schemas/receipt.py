"""Receipt and printing schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class ReceiptLine(BaseModel):
    quantity: int
    name: str
    options: list[str] = Field(default_factory=list)
    note: str | None = None
    amount: Decimal  # the line after any comp / discount
    discount: Decimal = Decimal("0.00")


class ReceiptPayment(BaseModel):
    method: str
    amount: Decimal
    tip: Decimal = Decimal("0.00")
    status: str


class Receipt(BaseModel):
    restaurant_name: str
    address_lines: list[str] = Field(default_factory=list)
    phone: str | None = None
    kind: str  # ORDER | TAB
    title: str  # "Receipt", or "Check" for a tab nobody has paid yet
    reference: str  # order number, or "Table 4"
    served_by: str | None = None
    printed_at: datetime
    currency: str = "usd"
    lines: list[ReceiptLine]
    subtotal: Decimal
    discount: Decimal = Decimal("0.00")
    service_charge: Decimal = Decimal("0.00")
    tax: Decimal
    delivery_fee: Decimal = Decimal("0.00")
    total: Decimal
    paid: Decimal = Decimal("0.00")
    tip: Decimal = Decimal("0.00")
    balance: Decimal = Decimal("0.00")
    payments: list[ReceiptPayment] = Field(default_factory=list)
    footer: str = "Thank you!"


class EscPosRead(BaseModel):
    """The receipt as printer bytes (base64), ready to send to a network thermal printer on port 9100."""

    data: str
    drawer_kick: bool = False


class EmailReceiptRequest(BaseModel):
    email: EmailStr


class PrinterSettings(BaseModel):
    host: str | None = None
    port: int = 9100
    cash_drawer: bool = False
    auto_print: bool = False
