"""Discount coupons: validation, the money, and staff CRUD.

The client only ever sends a *code*. Every amount here is worked out from the server's own subtotal
(see `OrderService.create_order`), which is the rule the pricing path has followed since the
client-supplied `discount` was removed in Stage A.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.coupon import Coupon, CouponRedemption
from app.models.enums import CouponDiscountType
from app.models.order import Order
from app.models.user import User
from app.schemas.coupon import CouponCreate, CouponRead, CouponUpdate

ZERO = Decimal("0.00")


class CouponService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ validation & money

    def _by_code(self, restaurant_id: int, code: str, *, lock: bool = False) -> Coupon:
        stmt = select(Coupon).where(Coupon.restaurant_id == restaurant_id, Coupon.code == code.strip().upper())
        if lock:
            # Taken before the limit checks so two simultaneous checkouts can't both slip past the last
            # redemption of a capped coupon.
            stmt = stmt.with_for_update()
        coupon = self.db.scalar(stmt)
        if coupon is None:
            raise AppError("That code isn't valid here")
        return coupon

    def _check_usable(self, coupon: Coupon, subtotal: Decimal, user_id: int | None) -> None:
        now = datetime.now(UTC)
        if not coupon.is_active:
            raise AppError("That code is no longer available")
        if coupon.starts_at and now < coupon.starts_at:
            raise AppError("That code isn't active yet")
        if coupon.ends_at and now > coupon.ends_at:
            raise AppError("That code has expired")
        if coupon.min_order_amount is not None and subtotal < coupon.min_order_amount:
            raise AppError(f"That code needs an order of at least {coupon.min_order_amount:.2f}")
        if coupon.max_redemptions is not None and coupon.times_redeemed >= coupon.max_redemptions:
            raise AppError("That code has been fully claimed")
        if coupon.max_per_customer is not None and user_id is not None:
            used = self.db.scalar(
                select(func.count(CouponRedemption.id)).where(
                    CouponRedemption.coupon_id == coupon.id, CouponRedemption.user_id == user_id
                )
            ) or 0
            if used >= coupon.max_per_customer:
                raise AppError("You've already used that code")

    def compute_discount(self, coupon: Coupon, subtotal: Decimal) -> Decimal:
        """Never more than the subtotal — a coupon reduces the bill, it never pays money out."""
        if coupon.discount_type == CouponDiscountType.PERCENT:
            discount = (subtotal * coupon.discount_value / Decimal("100")).quantize(Decimal("0.01"))
            if coupon.max_discount_amount is not None:
                discount = min(discount, coupon.max_discount_amount)
        else:
            discount = coupon.discount_value
        return min(discount, subtotal).quantize(Decimal("0.01"))

    def preview(self, restaurant_id: int, code: str, subtotal: Decimal, user: User | None) -> tuple[Coupon, Decimal]:
        """What the customer is shown at checkout. Advisory: `apply_to_order` recomputes it for real."""
        coupon = self._by_code(restaurant_id, code)
        self._check_usable(coupon, subtotal, user.id if user else None)
        return coupon, self.compute_discount(coupon, subtotal)

    def apply_to_order(self, restaurant_id: int, code: str, subtotal: Decimal, user: User | None) -> tuple[Coupon, Decimal]:
        """Validate under a row lock and return the binding discount. The caller records the redemption
        with `record_redemption` once the order exists."""
        coupon = self._by_code(restaurant_id, code, lock=True)
        self._check_usable(coupon, subtotal, user.id if user else None)
        return coupon, self.compute_discount(coupon, subtotal)

    def record_redemption(self, coupon: Coupon, order: Order, user: User | None, amount: Decimal) -> None:
        self.db.add(CouponRedemption(
            restaurant_id=coupon.restaurant_id, coupon_id=coupon.id, order_id=order.id,
            user_id=user.id if user else None, amount=amount,
        ))
        coupon.times_redeemed += 1

    # ------------------------------------------------------------------ staff CRUD

    def _get(self, coupon_id: int, restaurant_id: int) -> Coupon:
        coupon = self.db.get(Coupon, coupon_id)
        if coupon is None or coupon.restaurant_id != restaurant_id:
            raise NotFoundError("Coupon not found")
        return coupon

    def list_for_restaurant(self, restaurant_id: int) -> list[CouponRead]:
        coupons = self.db.scalars(
            select(Coupon).where(Coupon.restaurant_id == restaurant_id).order_by(Coupon.created_at.desc())
        ).all()
        return [CouponRead.model_validate(c) for c in coupons]

    def create(self, restaurant_id: int, data: CouponCreate) -> CouponRead:
        coupon = Coupon(restaurant_id=restaurant_id, **data.model_dump())
        self.db.add(coupon)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("A coupon with that code already exists") from exc
        self.db.refresh(coupon)
        return CouponRead.model_validate(coupon)

    def update(self, coupon_id: int, restaurant_id: int, data: CouponUpdate) -> CouponRead:
        coupon = self._get(coupon_id, restaurant_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(coupon, key, value)
        if coupon.discount_type == CouponDiscountType.PERCENT and coupon.discount_value > 100:
            raise AppError("A percentage discount can't be more than 100%")
        if coupon.starts_at and coupon.ends_at and coupon.ends_at <= coupon.starts_at:
            raise AppError("The end date must be after the start date")
        self.db.commit()
        self.db.refresh(coupon)
        return CouponRead.model_validate(coupon)

    def delete(self, coupon_id: int, restaurant_id: int) -> None:
        """Deactivates rather than deletes once it has been used, so past orders keep their history."""
        coupon = self._get(coupon_id, restaurant_id)
        if coupon.times_redeemed > 0:
            coupon.is_active = False
        else:
            self.db.delete(coupon)
        self.db.commit()
