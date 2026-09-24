"""Loyalty points: earn on a completed order, view a balance, and let staff adjust it by hand.

`LoyaltyAccount.balance` is a denormalized running total; `LoyaltyTransaction` is the ledger that
explains it. Every change to the balance goes through `_apply`, so the two can never drift apart.
"""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.enums import LoyaltyReason
from app.models.loyalty import LoyaltyAccount, LoyaltyTransaction
from app.models.order import Order
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.loyalty import AdminLoyaltyAccountRead, LoyaltyAccountRead, LoyaltyTransactionRead


class LoyaltyService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _account(self, restaurant_id: int, user_id: int, *, create: bool = False) -> LoyaltyAccount | None:
        account = self.db.scalar(
            select(LoyaltyAccount).where(LoyaltyAccount.restaurant_id == restaurant_id, LoyaltyAccount.user_id == user_id)
        )
        if account is None and create:
            account = LoyaltyAccount(restaurant_id=restaurant_id, user_id=user_id, balance=0)
            self.db.add(account)
            self.db.flush()
        return account

    def _apply(self, restaurant_id: int, user_id: int, points: int, reason: LoyaltyReason, *, order_id: int | None = None, note: str | None = None, created_by: str | None = None) -> LoyaltyAccount:
        account = self._account(restaurant_id, user_id, create=True)
        account.balance += points
        self.db.add(LoyaltyTransaction(
            restaurant_id=restaurant_id, user_id=user_id, order_id=order_id, points=points,
            reason=reason, note=note, created_by=created_by,
        ))
        return account

    # ------------------------------------------------------------------ earning

    def earn_for_completed_order(self, order: Order, restaurant: Restaurant) -> None:
        """Called once when an order transitions to COMPLETED. A no-op for guest orders (no account to
        credit) and idempotent per order (the DB's unique constraint on `order_id` is the real guard)."""
        if order.user_id is None or restaurant.loyalty_points_per_currency <= 0:
            return
        existing = self.db.scalar(select(LoyaltyTransaction).where(LoyaltyTransaction.order_id == order.id))
        if existing is not None:
            return
        points = math.floor(float(order.total) * restaurant.loyalty_points_per_currency)
        if points <= 0:
            return
        self._apply(restaurant.id, order.user_id, points, LoyaltyReason.EARNED, order_id=order.id)

    # ------------------------------------------------------------------ customer

    def my_account(self, restaurant_id: int, user: User) -> LoyaltyAccountRead:
        account = self._account(restaurant_id, user.id)
        transactions = self.db.scalars(
            select(LoyaltyTransaction).where(
                LoyaltyTransaction.restaurant_id == restaurant_id, LoyaltyTransaction.user_id == user.id,
            ).order_by(LoyaltyTransaction.created_at.desc())
        ).all()
        restaurant = self.db.get(Restaurant, restaurant_id)
        return LoyaltyAccountRead(
            balance=account.balance if account else 0,
            points_per_currency=restaurant.loyalty_points_per_currency if restaurant else 1,
            transactions=[LoyaltyTransactionRead.model_validate(t) for t in transactions],
        )

    # ------------------------------------------------------------------ admin

    def admin_list(self, restaurant_id: int) -> list[AdminLoyaltyAccountRead]:
        rows = self.db.execute(
            select(LoyaltyAccount, User).join(User, User.id == LoyaltyAccount.user_id).where(
                LoyaltyAccount.restaurant_id == restaurant_id
            ).order_by(LoyaltyAccount.balance.desc())
        ).all()
        return [
            AdminLoyaltyAccountRead(user_id=user.id, name=user.full_name, email=user.email, balance=account.balance)
            for account, user in rows
        ]

    def admin_adjust(self, restaurant_id: int, user_id: int, points: int, note: str | None, actor: User) -> AdminLoyaltyAccountRead:
        target = self.db.scalar(select(User).where(User.id == user_id, User.restaurant_id == restaurant_id))
        if target is None:
            raise NotFoundError("Customer not found")
        account = self._account(restaurant_id, user_id, create=True)
        if points < 0 and account.balance + points < 0:
            raise AppError("Can't deduct more points than the customer has")
        self._apply(
            restaurant_id, user_id, points, LoyaltyReason.ADJUSTED, note=note,
            created_by=actor.full_name if actor else None,
        )
        self.db.commit()
        self.db.refresh(account)
        return AdminLoyaltyAccountRead(user_id=target.id, name=target.full_name, email=target.email, balance=account.balance)
