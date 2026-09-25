"""Admin business logic services."""

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.realtime import kitchen_topic, publish, publish_order_change
from app.core.storage import delete_owned_url
from app.models.category import Category
from app.models.enums import OrderStatus, TableStatus
from app.models.menu_item import MenuItem
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption
from app.models.order_item import OrderItem
from app.models.reservation import Reservation
from app.models.restaurant_table import RestaurantTable
from app.models.user import User
from app.repositories.admin_order import AdminOrderRepository, CustomerRepository, TableRepository
from app.repositories.category import CategoryRepository
from app.repositories.dashboard import DashboardRepository
from app.repositories.menu_admin import MenuAdminRepository
from app.repositories.restaurant import RestaurantRepository
from app.schemas.admin import (
    CategoryCreate,
    CategoryUpdate,
    CategoryReorder,
    CustomerDetail,
    CustomerProfileUpdate,
    CustomerReservationBrief,
    CustomerSummary,
    DashboardStats,
    KitchenBoard,
    MenuItemCreate,
    MenuItemUpdate,
    MenuModifierCreate,
    MenuModifierUpdate,
    ModifierOptionCreate,
    ModifierOptionUpdate,
    OrderStatusUpdate,
    RestaurantSettingsUpdate,
    TableCreate,
    TableLayoutUpdate,
    TableRead,
    TableStatusUpdate,
    TableUpdate,
)
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuModifierRead
from app.schemas.order import OrderListResponse, OrderRead
from app.schemas.restaurant import RestaurantRead
from app.services.feature_service import FeatureService
from app.services.loyalty_service import LoyaltyService
from app.services.menu_service import MenuService
from app.services.reservation_service import ReservationService

logger = logging.getLogger(__name__)

STAFF_ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
    OrderStatus.READY: {OrderStatus.COMPLETED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.CANCELLED},
    OrderStatus.OUT_FOR_DELIVERY: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED},
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
}


class AdminService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.dashboard = DashboardRepository(db)
        self.categories = CategoryRepository(db)
        self.menu = MenuAdminRepository(db)
        self.orders = AdminOrderRepository(db)
        self.tables = TableRepository(db)
        self.customers = CustomerRepository(db)
        self.restaurants = RestaurantRepository(db)
        self.menu_reader = MenuService(db)
        self.reservations = ReservationService(db)
        self.features = FeatureService(db)
        self.loyalty = LoyaltyService(db)

    def dashboard_stats(self, restaurant_id: int) -> DashboardStats:
        data = self.dashboard.stats(restaurant_id)
        return DashboardStats(**data)

    # Categories
    def list_categories(self, restaurant_id: int) -> list[CategoryRead]:
        return [CategoryRead.model_validate(c) for c in self.categories.list_for_restaurant(restaurant_id)]

    def create_category(self, data: CategoryCreate) -> CategoryRead:
        self._ensure_category_slug_free(data.restaurant_id, data.slug)
        category = Category(**data.model_dump())
        self.categories.create(category)
        self.db.commit()
        return CategoryRead.model_validate(category)

    def update_category(self, category_id: int, data: CategoryUpdate, restaurant_id: int) -> CategoryRead:
        category = self._get_category(category_id, restaurant_id)
        payload = data.model_dump(exclude_unset=True)
        if payload.get("slug") and payload["slug"] != category.slug:
            self._ensure_category_slug_free(restaurant_id, payload["slug"])
        for key, value in payload.items():
            setattr(category, key, value)
        self.db.commit()
        return CategoryRead.model_validate(category)

    def delete_category(self, category_id: int, restaurant_id: int) -> None:
        category = self._get_category(category_id, restaurant_id)
        count = self.db.scalar(select(func.count(MenuItem.id)).where(MenuItem.category_id == category.id)) or 0
        if count:
            raise ConflictError(
                f"“{category.name}” still has {count} menu item{'s' if count != 1 else ''}. "
                "Move or delete them first."
            )
        self.categories.delete(category)
        self.db.commit()

    def reorder_categories(self, data: CategoryReorder, restaurant_id: int) -> list[CategoryRead]:
        for item in data.items:
            category = self._get_category(item.id, restaurant_id)
            category.sort_order = item.sort_order
        self.db.commit()
        return self.list_categories(restaurant_id)

    # Menu items
    def list_menu_items(self, restaurant_id: int) -> list[MenuItemDetailRead]:
        items = self.menu.list_items(restaurant_id)
        return [self.menu_reader.get_item(i.id, i.restaurant_id) for i in items]

    def create_menu_item(self, data: MenuItemCreate) -> MenuItemDetailRead:
        self._get_category(data.category_id, data.restaurant_id)
        item = MenuItem(**data.model_dump(exclude={"modifier_ids"}))
        self.menu.create_item(item)
        if data.modifier_ids:
            self._validate_modifiers(data.restaurant_id, data.modifier_ids)
            self.menu.set_item_modifiers(item, data.modifier_ids)
        self.db.commit()
        return self.menu_reader.get_item(item.id, item.restaurant_id)

    def update_menu_item(self, item_id: int, data: MenuItemUpdate, restaurant_id: int) -> MenuItemDetailRead:
        item = self._get_menu_item(item_id, restaurant_id)
        payload = data.model_dump(exclude_unset=True, exclude={"modifier_ids"})
        old_image = item.image_url
        if "category_id" in payload:
            self._get_category(payload["category_id"], restaurant_id)
        for key, value in payload.items():
            setattr(item, key, value)
        if data.modifier_ids is not None:
            self._validate_modifiers(restaurant_id, data.modifier_ids)
            self.menu.set_item_modifiers(item, data.modifier_ids)
        self.db.commit()
        if "image_url" in payload and old_image != item.image_url:
            delete_owned_url(old_image, restaurant_id)  # the replaced upload is no longer referenced
        return self.menu_reader.get_item(item.id, item.restaurant_id)

    def delete_menu_item(self, item_id: int, restaurant_id: int) -> None:
        item = self._get_menu_item(item_id, restaurant_id)
        if self.db.scalar(select(OrderItem.id).where(OrderItem.menu_item_id == item.id).limit(1)) is not None:
            raise ConflictError(
                f"“{item.name}” appears in past orders, so it can't be deleted. "
                "Mark it unavailable instead to hide it from the menu."
            )
        image = item.image_url
        self.menu.delete_item(item)
        self.db.commit()
        delete_owned_url(image, restaurant_id)

    # Modifiers
    def list_modifiers(self, restaurant_id: int) -> list[MenuModifierRead]:
        modifiers = self.menu.list_modifiers(restaurant_id)
        return [MenuModifierRead.model_validate(m) for m in modifiers]

    def create_modifier(self, data: MenuModifierCreate) -> MenuModifierRead:
        modifier = MenuModifier(**data.model_dump(exclude={"options"}))
        self.menu.create_modifier(modifier)
        for opt in data.options:
            self.menu.create_option(MenuModifierOption(modifier_id=modifier.id, **opt.model_dump()))
        self.db.commit()
        return MenuModifierRead.model_validate(self.menu.get_modifier(modifier.id))

    def update_modifier(self, modifier_id: int, data: MenuModifierUpdate, restaurant_id: int) -> MenuModifierRead:
        modifier = self._get_modifier(modifier_id, restaurant_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(modifier, key, value)
        self.db.commit()
        return MenuModifierRead.model_validate(self.menu.get_modifier(modifier.id))

    def delete_modifier(self, modifier_id: int, restaurant_id: int) -> None:
        modifier = self._get_modifier(modifier_id, restaurant_id)
        self.menu.delete_modifier(modifier)
        self.db.commit()

    def add_modifier_option(self, modifier_id: int, data: ModifierOptionCreate, restaurant_id: int):
        modifier = self._get_modifier(modifier_id, restaurant_id)
        option = MenuModifierOption(modifier_id=modifier.id, **data.model_dump())
        self.menu.create_option(option)
        self.db.commit()
        return MenuModifierRead.model_validate(self.menu.get_modifier(modifier.id))

    def update_modifier_option(self, option_id: int, data: ModifierOptionUpdate, restaurant_id: int):
        option = self.menu.get_option(option_id)
        if option is None:
            raise NotFoundError("Modifier option not found")
        self._get_modifier(option.modifier_id, restaurant_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(option, key, value)
        self.db.commit()
        return MenuModifierRead.model_validate(self.menu.get_modifier(option.modifier_id))

    def delete_modifier_option(self, option_id: int, restaurant_id: int) -> None:
        option = self.menu.get_option(option_id)
        if option is None:
            raise NotFoundError("Modifier option not found")
        modifier_id = option.modifier_id
        self._get_modifier(modifier_id, restaurant_id)
        self.menu.delete_option(option)
        self.db.commit()

    # Orders
    def list_orders(
        self,
        restaurant_id: int,
        *,
        status: OrderStatus | None = None,
        order_type=None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OrderListResponse:
        items, total = self.orders.list_for_restaurant(
            restaurant_id,
            status=status,
            order_type=order_type,
            search=search,
            page=page,
            page_size=page_size,
        )
        return OrderListResponse(
            items=[OrderRead.model_validate(o) for o in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=self.orders.pages(total, page_size),
        )

    def get_order(self, order_id: int, restaurant_id: int) -> OrderRead:
        order = self.orders.get_for_restaurant(order_id, restaurant_id)
        if order is None:
            raise NotFoundError("Order not found")
        return OrderRead.model_validate(order)

    def update_order_status(
        self,
        order_id: int,
        data: OrderStatusUpdate,
        restaurant_id: int,
        user: User,
    ) -> OrderRead:
        order = self.orders.get_for_restaurant(order_id, restaurant_id)
        if order is None:
            raise NotFoundError("Order not found")
        if order.status == OrderStatus.CANCELLED or order.status == OrderStatus.COMPLETED:
            raise AppError("Order cannot be updated")

        allowed = STAFF_ALLOWED_TRANSITIONS.get(order.status, set())
        if data.status not in allowed and data.status != order.status:
            raise AppError(f"Cannot transition from {order.status.value} to {data.status.value}")

        previous = order.status
        order.status = data.status
        if data.status in (OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            for line in order.items:  # the whole ticket is done, so no dish is left open on a kitchen screen
                if line.status != "READY":
                    line.status, line.ready_at = "READY", datetime.now(UTC)
        self.orders.add_status_history(
            order=order,
            previous=previous,
            new=data.status,
            user_id=user.id,
            notes=data.notes,
        )
        publish(self.db, kitchen_topic(restaurant_id), "order.status", {"order_id": order.id, "status": data.status.value})
        publish_order_change(self.db, order, "order.status", {"status": data.status.value})
        if data.status == OrderStatus.COMPLETED and self.features.is_enabled(restaurant_id, "loyalty"):
            self.loyalty.earn_for_completed_order(order, order.restaurant)
        self.db.commit()
        logger.info("Order status updated: %s -> %s by user %s", previous.value, data.status.value, user.id)
        return self.get_order(order_id, restaurant_id)

    def kitchen_board(self, restaurant_id: int) -> KitchenBoard:
        restaurant = self.restaurants.get_by_id(restaurant_id)
        lead_minutes = restaurant.scheduled_order_lead_minutes if restaurant else 30
        groups = self.orders.kitchen_orders(restaurant_id, lead_minutes=lead_minutes)
        return KitchenBoard(
            new_orders=[OrderRead.model_validate(o) for o in groups["new_orders"]],
            preparing=[OrderRead.model_validate(o) for o in groups["preparing"]],
            ready=[OrderRead.model_validate(o) for o in groups["ready"]],
        )

    # Tables
    def list_tables(self, restaurant_id: int, include_inactive: bool = False) -> list[TableRead]:
        return [
            TableRead(
                id=table.id,
                table_number=table.table_number,
                capacity=table.capacity,
                status=table.status,
                zone=table.zone,
                shape=table.shape,
                pos_x=table.pos_x,
                pos_y=table.pos_y,
                is_active=table.is_active,
                reservations=reservations,
            )
            for table, reservations in self.reservations.table_overview(
                restaurant_id, include_inactive=include_inactive
            )
        ]

    def create_table(self, data: TableCreate) -> TableRead:
        self._ensure_table_number_free(data.restaurant_id, data.table_number)
        table = RestaurantTable(**{**data.model_dump(), "shape": data.shape.value})
        self.tables.create(table)
        self.db.commit()
        return TableRead.model_validate(table, from_attributes=True)

    def update_table(self, table_id: int, data: TableUpdate, restaurant_id: int) -> TableRead:
        table = self._get_table(table_id, restaurant_id)
        payload = data.model_dump(exclude_unset=True)
        for required in ("table_number", "capacity", "shape", "is_active"):
            if required in payload and payload[required] is None:
                raise AppError(f"{required.replace('_', ' ').capitalize()} can't be empty")
        if "shape" in payload:
            payload["shape"] = payload["shape"].value
        if "table_number" in payload and payload["table_number"] != table.table_number:
            self._ensure_table_number_free(restaurant_id, payload["table_number"])

        # Don't pull the rug from under guests who are booked or seated.
        if "capacity" in payload and payload["capacity"] < table.capacity:
            too_big = self.reservations.has_upcoming_bookings(table.id, min_party_size=payload["capacity"])
            if too_big:
                names = ", ".join(f"{r.guest_name} (party of {r.party_size})" for r in too_big)
                raise ConflictError(
                    f"Table {table.table_number} can't seat fewer than its booked guests: {names}. "
                    "Move or change those bookings first."
                )
        if payload.get("is_active") is False and table.is_active:
            live = self.reservations.has_upcoming_bookings(table.id)
            if live:
                names = ", ".join(r.guest_name for r in live)
                raise ConflictError(
                    f"Table {table.table_number} still has active bookings ({names}). "
                    "Move or cancel them before taking the table out of service."
                )
        for key, value in payload.items():
            setattr(table, key, value)
        self.db.commit()
        return TableRead.model_validate(table, from_attributes=True)

    def update_table_layout(self, restaurant_id: int, data: TableLayoutUpdate) -> list[TableRead]:
        """Save floor-plan positions for many tables in one go (all-or-nothing)."""
        wanted = {item.id: item for item in data.items}
        rows = self.db.scalars(
            select(RestaurantTable).where(
                RestaurantTable.restaurant_id == restaurant_id, RestaurantTable.id.in_(wanted)
            )
        ).all()
        if len(rows) != len(wanted):
            raise NotFoundError("Table not found")
        for table in rows:
            table.pos_x = wanted[table.id].pos_x
            table.pos_y = wanted[table.id].pos_y
        self.db.commit()
        return [TableRead.model_validate(t, from_attributes=True) for t in rows]

    def update_table_status(
        self, table_id: int, data: TableStatusUpdate, restaurant_id: int
    ) -> tuple[RestaurantTable, int, int]:
        """Returns (table, cancelled_reservations, completed_reservations)."""
        table = self._get_table(table_id, restaurant_id)
        cancelled = completed = 0
        if data.status in (TableStatus.AVAILABLE, TableStatus.CLEANING):
            cancelled, completed = self.reservations.release_table(table, data.status, force=data.force)
        elif data.status == TableStatus.RESERVED:
            raise AppError("Reserved is set automatically from bookings — create a reservation instead")
        else:
            table.status = data.status
        self.db.commit()
        return table, cancelled, completed

    def delete_table(self, table_id: int, restaurant_id: int) -> None:
        table = self._get_table(table_id, restaurant_id)
        if self.db.scalar(select(Reservation.id).where(Reservation.table_id == table.id).limit(1)) is not None:
            raise ConflictError(
                f"Table {table.table_number} has reservations on record, so it can't be deleted. "
                "Take it out of service instead — its history is kept."
            )
        self.tables.delete(table)
        self.db.commit()

    # Customers
    def list_customers(self, restaurant_id: int) -> list[CustomerSummary]:
        rows = self.customers.list_for_restaurant(restaurant_id)
        return [CustomerSummary(**row) for row in rows]

    def get_customer_detail(self, restaurant_id: int, user_id: int) -> CustomerDetail:
        customer = self.customers.get_for_restaurant(restaurant_id, user_id)
        if customer is None:
            raise NotFoundError("Customer not found for this restaurant")
        orders = self.customers.get_customer_orders(restaurant_id, user_id)
        reservations = self.customers.get_customer_reservations(restaurant_id, user_id)
        total_spending = sum((o.total for o in orders), Decimal("0.00"))
        return CustomerDetail(
            id=customer.id, email=customer.email, first_name=customer.first_name, last_name=customer.last_name,
            phone=customer.phone, is_active=customer.is_active, is_vip=customer.is_vip,
            notes=customer.notes, allergies=customer.allergies,
            total_orders=len(orders), total_spending=total_spending, total_bookings=len(reservations),
            orders=[OrderRead.model_validate(o) for o in orders],
            reservations=[
                CustomerReservationBrief(
                    id=r.id, starts_at=r.starts_at, party_size=r.party_size, status=r.status,
                    table_number=r.table.table_number if r.table else None,
                )
                for r in reservations
            ],
        )

    def update_customer_profile(self, restaurant_id: int, user_id: int, data: CustomerProfileUpdate) -> CustomerSummary:
        customer = self.customers.get_for_restaurant(restaurant_id, user_id)
        if customer is None:
            raise NotFoundError("Customer not found for this restaurant")
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, key, value)
        self.db.commit()
        rows = self.customers.list_for_restaurant(restaurant_id)
        row = next(r for r in rows if r["id"] == user_id)
        return CustomerSummary(**row)

    # Settings
    def get_settings(self, restaurant_id: int) -> RestaurantRead:
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        return RestaurantRead.model_validate(restaurant)

    def update_settings(self, restaurant_id: int, data: RestaurantSettingsUpdate) -> RestaurantRead:
        restaurant = self.restaurants.get_by_id(restaurant_id)
        if restaurant is None:
            raise NotFoundError("Restaurant not found")
        old_logo = restaurant.logo_url
        old_gallery = list(restaurant.gallery or [])
        payload = data.model_dump(exclude_unset=True)
        if "custom_domain" in payload and payload["custom_domain"] != restaurant.custom_domain:
            restaurant.domain_verified_at = None  # a changed domain needs verifying again
        for key, value in payload.items():
            setattr(restaurant, key, value)
        if restaurant.max_party_size is not None and restaurant.max_party_size < restaurant.min_party_size:
            raise AppError("Maximum party size can't be smaller than the minimum")
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError("That domain is already in use by another restaurant") from exc
        if old_logo and old_logo != restaurant.logo_url:
            delete_owned_url(old_logo, restaurant_id)
        for removed in set(old_gallery) - set(restaurant.gallery or []):
            delete_owned_url(removed, restaurant_id)
        return RestaurantRead.model_validate(restaurant)

    # Helpers
    def _get_category(self, category_id: int, restaurant_id: int) -> Category:
        category = self.categories.get_by_id(category_id)
        if category is None or category.restaurant_id != restaurant_id:
            raise NotFoundError("Category not found")
        return category

    def _get_menu_item(self, item_id: int, restaurant_id: int) -> MenuItem:
        item = self.menu.get_item(item_id)
        if item is None or item.restaurant_id != restaurant_id:
            raise NotFoundError("Menu item not found")
        return item

    def _get_modifier(self, modifier_id: int, restaurant_id: int) -> MenuModifier:
        modifier = self.menu.get_modifier(modifier_id)
        if modifier is None or modifier.restaurant_id != restaurant_id:
            raise NotFoundError("Modifier not found")
        return modifier

    def _get_table(self, table_id: int, restaurant_id: int) -> RestaurantTable:
        table = self.tables.get_by_id(table_id)
        if table is None or table.restaurant_id != restaurant_id:
            raise NotFoundError("Table not found")
        return table

    def _ensure_category_slug_free(self, restaurant_id: int, slug: str) -> None:
        taken = self.db.scalar(
            select(Category.id).where(Category.restaurant_id == restaurant_id, Category.slug == slug)
        )
        if taken is not None:
            raise ConflictError(f"A category with the link name “{slug}” already exists")

    def _ensure_table_number_free(self, restaurant_id: int, table_number: str) -> None:
        taken = self.db.scalar(
            select(RestaurantTable.id).where(
                RestaurantTable.restaurant_id == restaurant_id,
                RestaurantTable.table_number == table_number,
            )
        )
        if taken is not None:
            raise ConflictError(f"Table {table_number} already exists")

    def _validate_modifiers(self, restaurant_id: int, modifier_ids: list[int]) -> None:
        for modifier_id in modifier_ids:
            self._get_modifier(modifier_id, restaurant_id)
