"""Payment ORM model."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import PaymentMethod, PaymentStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order
    from app.models.table_session import TableSession


class Payment(TimestampMixin, Base):
    """A payment for one order, OR a payment for a whole table session's tab — exactly one of `order_id`
    / `table_session_id` is set (enforced in the service layer, not a DB constraint). One real charge is
    one row here, never split across the orders it covers, so Phase 2's eventual refund
    (`PaymentProvider.refund(provider_intent_id, ...)`) always refunds exactly one thing."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True
    )
    table_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("table_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Denormalized from the order: lets a restaurant's payouts be queried without joining through
    # orders, which RLS-scoped reporting needs anyway (every tenant table is filtered by this column).
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="usd", server_default="usd", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), default=PaymentStatus.PENDING, nullable=False
    )
    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(PaymentMethod, name="payment_method"), default=PaymentMethod.MOCK, nullable=False
    )
    # "MOCK" or "STRIPE" — which PaymentProvider (app/services/payments/) handled this payment.
    provider: Mapped[str] = mapped_column(String(20), default="MOCK", server_default="MOCK", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # The Stripe PaymentIntent id (or equivalent for another provider) — how a webhook finds this row.
    provider_intent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # The platform's cut of a Stripe direct charge (0 until a fee is actually decided on).
    application_fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), server_default="0.00", nullable=False
    )
    # Set on a FAILED payment so staff (and the customer, on retry) can see why.
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    order: Mapped["Order | None"] = relationship("Order", back_populates="payments")
    table_session: Mapped["TableSession | None"] = relationship("TableSession")
