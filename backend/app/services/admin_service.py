"""Admin business logic services."""

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.category import Category
from app.models.enums import OrderStatus, TableStatus
from app.models.menu_item import MenuItem
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption
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
    TableRead,
    TableStatusUpdate,
    TableUpdate,
)
from app.schemas.menu import CategoryRead, MenuItemDetailRead, MenuModifierRead
from app.schemas.order import OrderListResponse, OrderRead
from app.schemas.restaurant import RestaurantRead
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

    def dashboard_stats(self, restaurant_id: int) -> DashboardStats:
        data = self.dashboard.stats(restaurant_id)
        return DashboardStats(**data)

    # Categories
    def list_categories(self, restaurant_id: int) -> list[CategoryRead]:
        return [CategoryRead.model_validate(c) for c in self.categories.list_for_restaurant(restaurant_id)]

    def create_category(self, data: CategoryCreate) -> CategoryRead:
        category = Category(**data.model_dump())
        self.categories.create(category)
        self.db.commit()
        return CategoryRead.model_validate(category)

    def update_category(self, category_id: int, data: CategoryUpdate, restaurant_id: int) -> CategoryRead:
        category = self._get_category(category_id, restaurant_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(category, key, value)
        self.db.commit()
        return CategoryRead.model_validate(category)

    def delete_category(self, category_id: int, restaurant_id: int) -> None:
        category = self._get_category(category_id, restaurant_id)
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
        return [self.menu_reader.get_item(i.id) for i in items]

    def create_menu_item(self, data: MenuItemCreate) -> MenuItemDetailRead:
        self._get_category(data.category_id, data.restaurant_id)
        item = MenuItem(**data.model_dump(exclude={"modifier_ids"}))
        self.menu.create_item(item)
        if data.modifier_ids:
            self._validate_modifiers(data.restaurant_id, data.modifier_ids)
            self.menu.set_item_modifiers(item, data.modifier_ids)
        self.db.commit()
        return self.menu_reader.get_item(item.id)

    def update_menu_item(self, item_id: int, data: MenuItemUpdate, restaurant_id: int) -> MenuItemDetailRead:
        item = self._get_menu_item(item_id, restaurant_id)
        payload = data.model_dump(exclude_unset=True, exclude={"modifier_ids"})
        if "category_id" in payload:
            self._get_category(payload["category_id"], restaurant_id)
        for key, value in payload.items():
            setattr(item, key, value)
        if data.modifier_ids is not None:
            self._validate_modifiers(restaurant_id, data.modifier_ids)
            self.menu.set_item_modifiers(item, data.modifier_ids)
        self.db.commit()
        return self.menu_reader.get_item(item.id)

    def delete_menu_item(self, item_id: int, restaurant_id: int) -> None:
        item = self._get_menu_item(item_id, restaurant_id)
        self.menu.delete_item(item)
        self.db.commit()

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
        self.orders.add_status_history(
            order=order,
            previous=previous,
            new=data.status,
            user_id=user.id,
            notes=data.notes,
        )
        self.db.commit()
        logger.info("Order status updated: %s -> %s by user %s", previous.value, data.status.value, user.id)
        return self.get_order(order_id, restaurant_id)

    def kitchen_board(self, restaurant_id: int) -> KitchenBoard:
        groups = self.orders.kitchen_orders(restaurant_id)
        return KitchenBoard(
            new_orders=[OrderRead.model_validate(o) for o in groups["new_orders"]],
            preparing=[OrderRead.model_validate(o) for o in groups["preparing"]],
            ready=[OrderRead.model_validate(o) for o in groups["ready"]],
        )

    # Tables
    def list_tables(self, restaurant_id: int) -> list[TableRead]:
        return [
            TableRead(
                id=table.id,
                table_number=table.table_number,
                capacity=table.capacity,
                status=table.status,
                reservations=reservations,
            )
            for table, reservations in self.reservations.table_overview(restaurant_id)
        ]

    def create_table(self, data: TableCreate) -> TableRead:
        self._ensure_table_number_free(data.restaurant_id, data.table_number)
        table = RestaurantTable(**data.model_dump())
        self.tables.create(table)
        self.db.commit()
        return TableRead.model_validate(table, from_attributes=True)

    def update_table(self, table_id: int, data: TableUpdate, restaurant_id: int) -> TableRead:
        table = self._get_table(table_id, restaurant_id)
        payload = data.model_dump(exclude_unset=True)
        if "table_number" in payload and payload["table_number"] != table.table_number:
            self._ensure_table_number_free(restaurant_id, payload["table_number"])
        for key, value in payload.items():
            setattr(table, key, value)
        self.db.commit()
        return TableRead.model_validate(table, from_attributes=True)

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
            raise ConflictError("This table has reservations on record and can't be deleted")
        self.tables.delete(table)
        self.db.commit()

    # Customers
    def list_customers(self, restaurant_id: int) -> list[CustomerSummary]:
        rows = self.customers.list_for_restaurant(restaurant_id)
        return [CustomerSummary(**row) for row in rows]

    def get_customer_detail(self, restaurant_id: int, user_id: int) -> dict:
        orders = self.customers.get_customer_orders(restaurant_id, user_id)
        if not orders:
            raise NotFoundError("Customer not found for this restaurant")
        total_spending = sum((o.total for o in orders), Decimal("0.00"))
        return {
            "user_id": user_id,
            "total_orders": len(orders),
            "total_spending": total_spending,
            "orders": [OrderRead.model_validate(o) for o in orders],
        }

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
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(restaurant, key, value)
        self.db.commit()
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
