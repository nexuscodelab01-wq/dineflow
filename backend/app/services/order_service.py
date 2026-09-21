"""Order creation and validation business logic."""

import logging
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, NotFoundError
from app.models.address import Address
from app.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.models.menu_item import MenuItem
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_item_modifier import OrderItemModifier
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.restaurant import Restaurant
from app.core.realtime import kitchen_topic, publish
from app.models.user import User
from app.repositories.menu import MenuRepository
from app.repositories.order import OrderRepository
from app.repositories.restaurant import RestaurantRepository
from app.core.tenancy import ensure_customer_of
from app.schemas.order import OrderCreate, OrderListResponse, OrderRead
from app.services.notifications import notify_order_placed
from app.services.payment_service import PaymentService
from app.services.reservation_service import ReservationService

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.orders = OrderRepository(db)
        self.restaurants = RestaurantRepository(db)
        self.menu = MenuRepository(db)
        self.payments = PaymentService()
        self.reservations = ReservationService(db)

    def create_order(self, data: OrderCreate, user: User) -> OrderRead:
        restaurant = self.restaurants.get_by_id(data.restaurant_id)
        if restaurant is None or not restaurant.is_active:
            raise NotFoundError("Restaurant not found")
        ensure_customer_of(user, restaurant.id)

        # The table always comes from the customer's reservation (dine-in), never from the request.
        table_id: int | None = None
        reservation = None

        if data.order_type == OrderType.DELIVERY:
            if not restaurant.delivery_enabled:
                raise AppError("Delivery is not available for this restaurant")
            if data.delivery_address is None:
                raise AppError("Delivery address is required")
        elif data.order_type == OrderType.PICKUP:
            if not restaurant.pickup_enabled:
                raise AppError("Pickup is not available for this restaurant")
        elif data.order_type == OrderType.DINE_IN:
            if not restaurant.dine_in_enabled:
                raise AppError("Dine-in is not available for this restaurant")
            if data.reservation_id is None:
                raise AppError(
                    "A table reservation is required for dine-in. "
                    "Book a table first, or ask staff to seat you for walk-ins."
                )
            reservation = self.reservations.get_reservation(data.reservation_id, restaurant.id)
            if reservation.user_id is not None and reservation.user_id != user.id:
                raise AppError("Reservation does not belong to this customer")
            table_id = reservation.table_id

        item_ids = [line.menu_item_id for line in data.items]
        menu_items = self.menu.get_items_by_ids(item_ids, restaurant.id)
        items_by_id = {item.id: item for item in menu_items}

        if len(items_by_id) != len(set(item_ids)):
            raise AppError("One or more menu items are invalid for this restaurant")

        subtotal = Decimal("0.00")
        email_lines: list[dict] = []  # what the confirmation email will list
        order = Order(
            user_id=user.id,
            restaurant_id=restaurant.id,
            order_number=self._next_order_number(restaurant.id),
            order_type=data.order_type,
            status=OrderStatus.PENDING,
            subtotal=Decimal("0.00"),
            tax=Decimal("0.00"),
            delivery_fee=Decimal("0.00"),
            discount=Decimal("0.00"),  # server-side only; coupons will set this later
            total=Decimal("0.00"),
            customer_name=data.customer_name,
            customer_email=str(data.customer_email),
            customer_phone=data.customer_phone,
            delivery_instructions=data.delivery_instructions,
            notes=data.notes,
            table_id=table_id,
        )

        if data.order_type == OrderType.DELIVERY and data.delivery_address:
            address = Address(
                user_id=user.id,
                street=data.delivery_address.street,
                city=data.delivery_address.city,
                postal_code=data.delivery_address.postal_code,
                delivery_instructions=data.delivery_address.delivery_instructions,
            )
            self.db.add(address)
            self.db.flush()
            order.delivery_address_id = address.id

        self.orders.add(order)

        for line in data.items:
            menu_item = items_by_id[line.menu_item_id]
            if not menu_item.is_available:
                raise AppError(f"{menu_item.name} is currently unavailable")

            unit_price, selected_modifiers = self._validate_modifiers(menu_item, line.modifier_option_ids)
            line_total = (unit_price * line.quantity).quantize(Decimal("0.01"))
            subtotal += line_total
            email_lines.append({
                "quantity": line.quantity,
                "name": menu_item.name,
                "options": [mod.name for mod in selected_modifiers],
                "instructions": line.special_instructions,
            })

            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                item_name=menu_item.name,
                quantity=line.quantity,
                unit_price=unit_price,
                line_total=line_total,
                special_instructions=line.special_instructions,
            )
            self.db.add(order_item)
            self.db.flush()

            for mod in selected_modifiers:
                self.db.add(
                    OrderItemModifier(
                        order_item_id=order_item.id,
                        modifier_option_id=mod.id,
                        modifier_name=mod.modifier.name,
                        option_name=mod.name,
                        price_adjustment=mod.price_adjustment,
                    )
                )

        delivery_fee = restaurant.delivery_fee if data.order_type == OrderType.DELIVERY else Decimal("0.00")
        taxable = max(subtotal - order.discount, Decimal("0.00"))
        tax = (taxable * restaurant.tax_rate).quantize(Decimal("0.01"))
        total = (taxable + tax + delivery_fee).quantize(Decimal("0.01"))

        order.subtotal = subtotal
        order.tax = tax
        order.delivery_fee = delivery_fee
        order.total = total

        payment_result = self.payments.process(total)
        if not payment_result.success:
            raise AppError(payment_result.message or "Payment failed")

        self.db.add(
            Payment(
                order_id=order.id,
                amount=total,
                status=payment_result.status,
                payment_method=PaymentMethod.MOCK,
                provider_reference=payment_result.provider_reference,
            )
        )
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                previous_status=None,
                new_status=OrderStatus.PENDING,
                changed_by_user_id=user.id,
            )
        )
        order.status = OrderStatus.CONFIRMED
        self.db.add(
            OrderStatusHistory(
                order_id=order.id,
                previous_status=OrderStatus.PENDING,
                new_status=OrderStatus.CONFIRMED,
                changed_by_user_id=user.id,
                notes="Payment confirmed (mock)",
            )
        )

        if reservation is not None:
            self.reservations.attach_to_order(reservation.id, order.id, user.id, restaurant.id)

        # Queued in this same transaction: the email exists only if the order does.
        notify_order_placed(self.db, restaurant, order, email_lines)
        # Delivered to kitchen screens only if this transaction commits.
        publish(self.db, kitchen_topic(restaurant.id), "order.created", {"order_id": order.id, "order_number": order.order_number})
        self.db.commit()
        logger.info("Order created: order_number=%s user_id=%s", order.order_number, user.id)

        refreshed = self.orders.get_by_id(order.id)
        if refreshed is None:
            raise AppError("Order could not be loaded after creation")
        return OrderRead.model_validate(refreshed)

    def get_order(self, order_id: int, user: User) -> OrderRead:
        order = self.orders.get_by_id_for_user(order_id, user.id)
        if order is None:
            raise NotFoundError("Order not found")
        return OrderRead.model_validate(order)

    def list_orders(self, user: User, *, page: int = 1, page_size: int = 20) -> OrderListResponse:
        items, total = self.orders.list_for_user(user.id, page=page, page_size=page_size)
        pages = self.orders.pages(total, page_size)
        return OrderListResponse(
            items=[OrderRead.model_validate(o) for o in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def _validate_modifiers(
        self,
        menu_item: MenuItem,
        selected_option_ids: list[int],
    ) -> tuple[Decimal, list[MenuModifierOption]]:
        modifier_links = menu_item.modifier_links
        allowed_modifiers = {link.modifier_id: link.modifier for link in modifier_links}
        options_by_id: dict[int, MenuModifierOption] = {}
        for link in modifier_links:
            for option in link.modifier.options:
                options_by_id[option.id] = option

        selected: list[MenuModifierOption] = []
        for option_id in selected_option_ids:
            option = options_by_id.get(option_id)
            if option is None:
                raise AppError(f"Invalid modifier option for {menu_item.name}")
            selected.append(option)

        by_modifier: dict[int, list[MenuModifierOption]] = defaultdict(list)
        for option in selected:
            by_modifier[option.modifier_id].append(option)

        for modifier_id, modifier in allowed_modifiers.items():
            count = len(by_modifier.get(modifier_id, []))
            if modifier.is_required and count < max(modifier.min_selections, 1):
                raise AppError(f"Please select {modifier.name} for {menu_item.name}")
            if count > modifier.max_selections:
                raise AppError(f"Too many selections for {modifier.name}")

        for modifier_id, options in by_modifier.items():
            if modifier_id not in allowed_modifiers:
                raise AppError("Invalid modifier selection")
            modifier = allowed_modifiers[modifier_id]
            if len(options) > modifier.max_selections:
                raise AppError(f"Too many selections for {modifier.name}")

        unit_price = menu_item.price + sum(opt.price_adjustment for opt in selected)
        return unit_price.quantize(Decimal("0.01")), selected

    def _next_order_number(self, restaurant_id: int) -> str:
        """Sequential per restaurant (e.g. PZ-1001). The row lock serialises concurrent orders, and the
        counter rolls back with the order if it fails, so numbers never skip or repeat."""
        row = self.db.execute(
            update(Restaurant)
            .where(Restaurant.id == restaurant_id)
            .values(next_order_number=Restaurant.next_order_number + 1)
            .returning(Restaurant.order_prefix, Restaurant.next_order_number)
        ).one()
        return f"{row.order_prefix}-{row.next_order_number - 1}"
