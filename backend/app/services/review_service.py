"""Guest reviews: a rating + comment left against one completed order or reservation.

A visit is reviewable once (`uq_reviews_order`/`uq_reviews_reservation` in the DB); resubmitting the
same visit edits the existing review rather than erroring, so a guest can fix a typo.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ForbiddenError, NotFoundError
from app.models.enums import OrderStatus, ReservationStatus
from app.models.order import Order
from app.models.reservation import Reservation
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    AdminReviewRead,
    EligibleVisit,
    PublicReviewList,
    PublicReviewRead,
    ReviewCreate,
    ReviewRead,
)


class ReviewService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ customer

    def eligible_visits(self, user: User) -> list[EligibleVisit]:
        """Completed orders/reservations belonging to this customer that have no review yet."""
        reviewed_orders = set(
            self.db.scalars(
                select(Review.order_id).where(Review.user_id == user.id, Review.order_id.is_not(None))
            ).all()
        )
        reviewed_reservations = set(
            self.db.scalars(
                select(Review.reservation_id).where(Review.user_id == user.id, Review.reservation_id.is_not(None))
            ).all()
        )

        out: list[EligibleVisit] = []
        orders = self.db.scalars(
            select(Order).where(
                Order.user_id == user.id, Order.status.in_([OrderStatus.COMPLETED, OrderStatus.DELIVERED])
            )
        ).all()
        for order in orders:
            if order.id in reviewed_orders:
                continue
            out.append(EligibleVisit(order_id=order.id, label=f"Order #{order.order_number}", visited_at=order.created_at))

        reservations = self.db.scalars(
            select(Reservation).where(Reservation.user_id == user.id, Reservation.status == ReservationStatus.COMPLETED)
        ).all()
        for reservation in reservations:
            if reservation.id in reviewed_reservations:
                continue
            out.append(
                EligibleVisit(
                    reservation_id=reservation.id,
                    label=f"Table booking, {reservation.starts_at:%d %b}",
                    visited_at=reservation.starts_at,
                )
            )

        out.sort(key=lambda v: v.visited_at, reverse=True)
        return out

    def submit(self, user: User, data: ReviewCreate) -> ReviewRead:
        if data.order_id is not None:
            order = self.db.get(Order, data.order_id)
            if order is None or order.user_id != user.id:
                raise NotFoundError("Order not found")
            if order.status not in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
                raise AppError("This order isn't completed yet")
            restaurant_id = order.restaurant_id
            existing = self.db.scalar(select(Review).where(Review.order_id == data.order_id))
        else:
            reservation = self.db.get(Reservation, data.reservation_id)
            if reservation is None or reservation.user_id != user.id:
                raise NotFoundError("Reservation not found")
            if reservation.status != ReservationStatus.COMPLETED:
                raise AppError("This booking isn't completed yet")
            restaurant_id = reservation.restaurant_id
            existing = self.db.scalar(select(Review).where(Review.reservation_id == data.reservation_id))

        if existing is not None:
            if existing.user_id != user.id:
                raise ForbiddenError("This visit was already reviewed")
            existing.rating = data.rating
            existing.comment = data.comment
            review = existing
        else:
            review = Review(
                restaurant_id=restaurant_id, user_id=user.id, order_id=data.order_id,
                reservation_id=data.reservation_id, rating=data.rating, comment=data.comment,
            )
            self.db.add(review)

        self.db.commit()
        self.db.refresh(review)
        return ReviewRead.model_validate(review)

    def my_reviews(self, user: User) -> list[ReviewRead]:
        reviews = self.db.scalars(
            select(Review).where(Review.user_id == user.id).order_by(Review.created_at.desc())
        ).all()
        return [ReviewRead.model_validate(r) for r in reviews]

    # ------------------------------------------------------------------ public

    def public_list(self, restaurant_id: int, page: int, page_size: int) -> PublicReviewList:
        base = select(Review).where(Review.restaurant_id == restaurant_id, Review.is_published.is_(True))
        total = self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.db.scalars(
            base.order_by(Review.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
        items = [
            PublicReviewRead(
                id=r.id, reviewer_name=_display_name(r.user), rating=r.rating, comment=r.comment,
                staff_reply=r.staff_reply, staff_reply_at=r.staff_reply_at, created_at=r.created_at,
            )
            for r in rows
        ]

        agg = self.db.execute(
            select(Review.rating, func.count()).where(
                Review.restaurant_id == restaurant_id, Review.is_published.is_(True)
            ).group_by(Review.rating)
        ).all()
        counts_by_rating = {rating: count for rating, count in agg}
        all_ratings_count = sum(counts_by_rating.values())
        average = (
            round(sum(rating * count for rating, count in counts_by_rating.items()) / all_ratings_count, 1)
            if all_ratings_count
            else None
        )

        pages = max(1, (total + page_size - 1) // page_size)
        return PublicReviewList(
            items=items, total=total, page=page, page_size=page_size, pages=pages,
            average_rating=average, counts_by_rating=counts_by_rating,
        )

    # ------------------------------------------------------------------ admin

    def _get(self, review_id: int, restaurant_id: int) -> Review:
        review = self.db.get(Review, review_id)
        if review is None or review.restaurant_id != restaurant_id:
            raise NotFoundError("Review not found")
        return review

    def admin_list(self, restaurant_id: int) -> list[AdminReviewRead]:
        reviews = self.db.scalars(
            select(Review).where(Review.restaurant_id == restaurant_id).order_by(Review.created_at.desc())
        ).all()
        return [
            AdminReviewRead(
                id=r.id, reviewer_name=_display_name(r.user, full=True), reviewer_email=r.user.email,
                order_id=r.order_id, reservation_id=r.reservation_id, rating=r.rating, comment=r.comment,
                is_published=r.is_published, staff_reply=r.staff_reply, staff_reply_at=r.staff_reply_at,
                created_at=r.created_at,
            )
            for r in reviews
        ]

    def moderate(self, review_id: int, restaurant_id: int, is_published: bool) -> AdminReviewRead:
        review = self._get(review_id, restaurant_id)
        review.is_published = is_published
        self.db.commit()
        self.db.refresh(review)
        return self._to_admin_read(review)

    def reply(self, review_id: int, restaurant_id: int, reply: str) -> AdminReviewRead:
        review = self._get(review_id, restaurant_id)
        review.staff_reply = reply.strip()
        review.staff_reply_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(review)
        return self._to_admin_read(review)

    def _to_admin_read(self, review: Review) -> AdminReviewRead:
        return AdminReviewRead(
            id=review.id, reviewer_name=_display_name(review.user, full=True), reviewer_email=review.user.email,
            order_id=review.order_id, reservation_id=review.reservation_id, rating=review.rating,
            comment=review.comment, is_published=review.is_published, staff_reply=review.staff_reply,
            staff_reply_at=review.staff_reply_at, created_at=review.created_at,
        )


def _display_name(user: User, full: bool = False) -> str:
    if full:
        return user.full_name
    last_initial = f"{user.last_name[0]}." if user.last_name else ""
    return f"{user.first_name} {last_initial}".strip()
