"""Database seed data for development and demos."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.address import Address
from app.models.category import Category
from app.models.enums import (
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
    ReservationStatus,
    RoleName,
    TableStatus,
)
from app.models.menu_item import MenuItem
from app.models.menu_item_modifier import MenuItemModifier
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption
from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.reservation import Reservation
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.user import User
from app.repositories.user import RoleRepository

logger = logging.getLogger(__name__)

DEMO_PASSWORD = "Demo1234!"

# Curated Unsplash food photos for demo menu items
MENU_IMAGES: dict[str, str] = {
    "Garlic Bread": "https://images.unsplash.com/photo-1573140247632-f8fd74997d5c?w=800&h=600&fit=crop",
    "Bruschetta Trio": "https://images.unsplash.com/photo-1572695157366-5e59ab6cf4c2?w=800&h=600&fit=crop",
    "Calamari Fritti": "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?w=800&h=600&fit=crop",
    "Soup of the Day": "https://images.unsplash.com/photo-1547592166-23ac45744acd?w=800&h=600&fit=crop",
    "Grilled Salmon": "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=800&h=600&fit=crop",
    "Herb Chicken": "https://images.unsplash.com/photo-1598103442097-8b74394b95c6?w=800&h=600&fit=crop",
    "Eggplant Parmigiana": "https://images.unsplash.com/photo-1625944230946-1e95e6c4c0e9?w=800&h=600&fit=crop",
    "Ribeye Steak": "https://images.unsplash.com/photo-1546833999-b9f581a1996d?w=800&h=600&fit=crop",
    "Margherita Pizza": "https://images.unsplash.com/photo-1574071318508-1cdbab80d264?w=800&h=600&fit=crop",
    "Pepperoni Pizza": "https://images.unsplash.com/photo-1628840042765-356cda07504e?w=800&h=600&fit=crop",
    "BBQ Chicken Pizza": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800&h=600&fit=crop",
    "Veggie Supreme Pizza": "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=800&h=600&fit=crop",
    "Classic Smash Burger": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=800&h=600&fit=crop",
    "Mushroom Swiss Burger": "https://images.unsplash.com/photo-1550547660-d9450f859349?w=800&h=600&fit=crop",
    "Spicy Jalapeño Burger": "https://images.unsplash.com/photo-1572802419224-296b0aeee0d9?w=800&h=600&fit=crop",
    "Veggie Burger": "https://images.unsplash.com/photo-1520072959219-c595dc870360?w=800&h=600&fit=crop",
    "Fettuccine Alfredo": "https://images.unsplash.com/photo-1645112411341-6c4fd023714a?w=800&h=600&fit=crop",
    "Spaghetti Bolognese": "https://images.unsplash.com/photo-1622973536968-3ead9e780960?w=800&h=600&fit=crop",
    "Pesto Penne": "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=800&h=600&fit=crop",
    "Caesar Salad": "https://images.unsplash.com/photo-1546793665-c74683f339c1?w=800&h=600&fit=crop",
    "Garden Salad": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&h=600&fit=crop",
    "Truffle Fries": "https://images.unsplash.com/photo-1576107233122-c2d2d0e0e1f5?w=800&h=600&fit=crop",
    "Onion Rings": "https://images.unsplash.com/photo-1639024471283-035266109961?w=800&h=600&fit=crop",
    "Sparkling Water": "https://images.unsplash.com/photo-1523362628745-0c100150b504?w=800&h=600&fit=crop",
    "Craft Lemonade": "https://images.unsplash.com/photo-1523677011785-c18980f1c4f7?w=800&h=600&fit=crop",
    "House Red Wine": "https://images.unsplash.com/photo-1510812431401-41d2bd2722f3?w=800&h=600&fit=crop",
    "Espresso": "https://images.unsplash.com/photo-1510590337019-5ef8d3d32116?w=800&h=600&fit=crop",
    "Tiramisu": "https://images.unsplash.com/photo-1571877227200-a0d98ea607e9?w=800&h=600&fit=crop",
    "Chocolate Lava Cake": "https://images.unsplash.com/photo-1624353365286-3f8d62daad51?w=800&h=600&fit=crop",
    "Panna Cotta": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=800&h=600&fit=crop",
    "Chef's Tasting Board": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&h=600&fit=crop",
    "Seasonal Risotto": "https://images.unsplash.com/photo-1476124369491-e7addf5db371?w=800&h=600&fit=crop",
}


def _backfill_menu_images(db) -> int:
    """Fill missing image_url values for known demo items."""
    updated = 0
    items = db.scalars(select(MenuItem)).all()
    for item in items:
        if item.image_url:
            continue
        url = MENU_IMAGES.get(item.name)
        if url:
            item.image_url = url
            updated += 1
    return updated


def _backfill_demo_reservation(db) -> bool:
    """Ensure one upcoming demo reservation exists for customer1."""
    if db.scalar(select(Reservation.id).limit(1)):
        return False
    restaurant = db.scalar(select(Restaurant).limit(1))
    customer = db.scalar(select(User).where(User.email == "customer1@demo.com"))
    table = db.scalar(
        select(RestaurantTable).where(
            RestaurantTable.status == TableStatus.AVAILABLE,
            RestaurantTable.capacity >= 2,
        ).limit(1)
    )
    if not restaurant or not customer or not table:
        return False
    starts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=3)
    db.add(
        Reservation(
            restaurant_id=restaurant.id,
            table_id=table.id,
            user_id=customer.id,
            party_size=2,
            starts_at=starts,
            ends_at=starts + timedelta(minutes=90),
            status=ReservationStatus.CONFIRMED,
            guest_name=f"{customer.first_name} {customer.last_name}",
            guest_email=customer.email,
            guest_phone=customer.phone,
        )
    )
    return True


# Demo floor plan: table -> (zone, shape, x%, y%). Coordinates are percentages of the plan's
# width/height (top-left origin), laid out like a small dining room.
DEMO_LAYOUT: dict[str, tuple[str, str, float, float]] = {
    "T1": ("Window", "SQUARE", 10, 16),
    "T2": ("Window", "SQUARE", 27, 16),
    "T3": ("Window", "SQUARE", 44, 16),
    "T4": ("Center", "ROUND", 24, 46),
    "T5": ("Center", "ROUND", 44, 46),
    "T6": ("Center", "RECT", 34, 74),
    "T7": ("Booth", "RECT", 74, 16),
    "T8": ("Booth", "RECT", 74, 40),
    "P1": ("Patio", "ROUND", 62, 70),
    "P2": ("Patio", "ROUND", 80, 70),
    "B1": ("Bar", "RECT", 90, 90),
}


def _backfill_table_layout(db) -> int:
    """Give tables that were created before floor plans existed a zone, shape and position.

    Only touches tables that have never been placed (pos_x is NULL); anything staff have
    arranged is left alone. Known demo tables get the demo layout, others are gridded.
    """
    updated = 0
    unplaced = list(
        db.scalars(
            select(RestaurantTable)
            .where(RestaurantTable.pos_x.is_(None))
            .order_by(RestaurantTable.restaurant_id, RestaurantTable.table_number)
        ).all()
    )
    extra_index: dict[int, int] = {}
    for table in unplaced:
        layout = DEMO_LAYOUT.get(table.table_number)
        if layout:
            zone, shape, x, y = layout
            table.zone = table.zone or zone
            table.shape = shape
            table.pos_x, table.pos_y = x, y
        else:
            i = extra_index.get(table.restaurant_id, 0)
            extra_index[table.restaurant_id] = i + 1
            table.pos_x, table.pos_y = 8 + (i % 6) * 15, 92 - (i // 6) * 12
        updated += 1
    return updated


def seed() -> None:
    db = SessionLocal()
    try:
        roles = RoleRepository(db)
        roles.ensure_defaults()
        db.commit()

        if db.scalar(select(Restaurant).limit(1)):
            filled = _backfill_menu_images(db)
            reserved = _backfill_demo_reservation(db)
            laid_out = _backfill_table_layout(db)
            if filled or reserved or laid_out:
                db.commit()
                logger.info(
                    "Seed backfill complete (images=%s reservation=%s tables=%s)",
                    filled,
                    reserved,
                    laid_out,
                )
            else:
                logger.info("Seed skipped — data already exists")
            return

        restaurant = Restaurant(
            name="Bella Vista Kitchen",
            slug="bella-vista-kitchen",
            order_prefix="BV",
            timezone="America/Los_Angeles",
            description="Modern Italian-American dining with wood-fired pizza and craft burgers.",
            logo_url=None,
            address="124 Market Street",
            city="San Francisco",
            postal_code="94105",
            phone="+1 (415) 555-0199",
            email="hello@bellavista.demo",
            opening_hours={
                "monday": "11:00-22:00",
                "tuesday": "11:00-22:00",
                "wednesday": "11:00-22:00",
                "thursday": "11:00-23:00",
                "friday": "11:00-23:00",
                "saturday": "10:00-23:00",
                "sunday": "10:00-21:00",
            },
            tax_rate=Decimal("0.0875"),
            delivery_fee=Decimal("4.99"),
        )
        db.add(restaurant)
        db.flush()

        role_map = {r.name.value if hasattr(r.name, "value") else str(r.name): r for r in roles.list_all()}

        def create_user(
            email: str,
            first: str,
            last: str,
            role: RoleName,
            phone: str | None = None,
            restaurant_id: int | None = None,
        ) -> User:
            user = User(
                email=email,
                hashed_password=hash_password(DEMO_PASSWORD),
                first_name=first,
                last_name=last,
                phone=phone,
                role_id=role_map[role.value].id,
                restaurant_id=restaurant_id,  # customers belong to one restaurant; staff are global
            )
            db.add(user)
            db.flush()
            return user

        super_admin = create_user("superadmin@dineflow.demo", "Sasha", "Platform", RoleName.SUPER_ADMIN)
        admin = create_user("admin@bellavista.demo", "Marco", "Rossi", RoleName.RESTAURANT_ADMIN, "+14155550101")
        staff = create_user("staff@bellavista.demo", "Elena", "Chen", RoleName.RESTAURANT_STAFF, "+14155550102")

        customers = [
            create_user("customer1@demo.com", "Alex", "Johnson", RoleName.CUSTOMER, "+14155550111", restaurant.id),
            create_user("customer2@demo.com", "Priya", "Patel", RoleName.CUSTOMER, "+14155550112", restaurant.id),
            create_user("customer3@demo.com", "Jordan", "Lee", RoleName.CUSTOMER, "+14155550113", restaurant.id),
        ]

        for user, role in ((admin, RoleName.RESTAURANT_ADMIN), (staff, RoleName.RESTAURANT_STAFF)):
            db.add(RestaurantUser(restaurant_id=restaurant.id, user_id=user.id, role=role))

        category_defs = [
            ("Appetizers", "appetizers", "Shareable starters"),
            ("Main Course", "main-course", "Hearty plates"),
            ("Pizza", "pizza", "Wood-fired pies"),
            ("Burgers", "burgers", "House burgers"),
            ("Pasta", "pasta", "Fresh pasta"),
            ("Salads", "salads", "Crisp greens"),
            ("Sides", "sides", "Perfect add-ons"),
            ("Drinks", "drinks", "Beverages"),
            ("Desserts", "desserts", "Sweet finishes"),
            ("Specials", "specials", "Chef's picks"),
        ]
        categories: dict[str, Category] = {}
        for idx, (name, slug, desc) in enumerate(category_defs):
            cat = Category(
                restaurant_id=restaurant.id,
                name=name,
                slug=slug,
                description=desc,
                sort_order=idx,
            )
            db.add(cat)
            db.flush()
            categories[slug] = cat

        size_modifier = MenuModifier(
            restaurant_id=restaurant.id,
            name="Size",
            description="Choose your size",
            is_required=True,
            min_selections=1,
            max_selections=1,
            sort_order=0,
        )
        db.add(size_modifier)
        db.flush()
        size_options = [
            MenuModifierOption(modifier_id=size_modifier.id, name="Small", price_adjustment=Decimal("0.00"), sort_order=0),
            MenuModifierOption(modifier_id=size_modifier.id, name="Medium", price_adjustment=Decimal("2.00"), sort_order=1, is_default=True),
            MenuModifierOption(modifier_id=size_modifier.id, name="Large", price_adjustment=Decimal("4.00"), sort_order=2),
        ]
        db.add_all(size_options)

        extras_modifier = MenuModifier(
            restaurant_id=restaurant.id,
            name="Extras",
            description="Add extra toppings",
            is_required=False,
            min_selections=0,
            max_selections=5,
            sort_order=1,
        )
        db.add(extras_modifier)
        db.flush()
        db.add_all([
            MenuModifierOption(modifier_id=extras_modifier.id, name="Extra cheese", price_adjustment=Decimal("1.50"), sort_order=0),
            MenuModifierOption(modifier_id=extras_modifier.id, name="Mushrooms", price_adjustment=Decimal("1.00"), sort_order=1),
            MenuModifierOption(modifier_id=extras_modifier.id, name="Jalapeños", price_adjustment=Decimal("0.75"), sort_order=2),
        ])

        burger_modifier = MenuModifier(
            restaurant_id=restaurant.id,
            name="Burger options",
            description="Customize your burger",
            is_required=False,
            min_selections=0,
            max_selections=3,
            sort_order=2,
        )
        db.add(burger_modifier)
        db.flush()
        db.add_all([
            MenuModifierOption(modifier_id=burger_modifier.id, name="Add cheese", price_adjustment=Decimal("1.00"), sort_order=0),
            MenuModifierOption(modifier_id=burger_modifier.id, name="Add bacon", price_adjustment=Decimal("2.00"), sort_order=1),
            MenuModifierOption(modifier_id=burger_modifier.id, name="Remove onions", price_adjustment=Decimal("0.00"), sort_order=2),
        ])

        menu_defs = [
            ("Garlic Bread", "appetizers", "12.00", True, False, True, 10),
            ("Bruschetta Trio", "appetizers", "13.50", True, False, False, 12),
            ("Calamari Fritti", "appetizers", "15.00", False, False, True, 14),
            ("Soup of the Day", "appetizers", "9.00", True, False, False, 8),
            ("Grilled Salmon", "main-course", "26.00", False, False, True, 22),
            ("Herb Chicken", "main-course", "22.00", False, False, False, 20),
            ("Eggplant Parmigiana", "main-course", "19.00", True, False, False, 18),
            ("Ribeye Steak", "main-course", "34.00", False, False, True, 25),
            ("Margherita Pizza", "pizza", "16.00", True, False, True, 16),
            ("Pepperoni Pizza", "pizza", "18.00", False, True, True, 16),
            ("BBQ Chicken Pizza", "pizza", "19.50", False, False, False, 18),
            ("Veggie Supreme Pizza", "pizza", "17.50", True, False, False, 16),
            ("Classic Smash Burger", "burgers", "15.00", False, False, True, 14),
            ("Mushroom Swiss Burger", "burgers", "16.50", False, False, False, 14),
            ("Spicy Jalapeño Burger", "burgers", "16.00", False, True, True, 14),
            ("Veggie Burger", "burgers", "14.50", True, False, False, 12),
            ("Fettuccine Alfredo", "pasta", "17.00", True, False, True, 15),
            ("Spaghetti Bolognese", "pasta", "18.00", False, False, True, 16),
            ("Pesto Penne", "pasta", "16.50", True, False, False, 14),
            ("Caesar Salad", "salads", "12.00", False, False, False, 8),
            ("Garden Salad", "salads", "10.00", True, False, False, 8),
            ("Truffle Fries", "sides", "7.50", True, False, True, 10),
            ("Onion Rings", "sides", "6.50", False, False, False, 10),
            ("Sparkling Water", "drinks", "3.50", True, False, False, 1),
            ("Craft Lemonade", "drinks", "4.50", True, False, True, 2),
            ("House Red Wine", "drinks", "8.00", True, False, False, 1),
            ("Espresso", "drinks", "3.00", True, False, False, 3),
            ("Tiramisu", "desserts", "9.00", True, False, True, 5),
            ("Chocolate Lava Cake", "desserts", "10.00", False, False, True, 8),
            ("Panna Cotta", "desserts", "8.50", True, False, False, 5),
            ("Chef's Tasting Board", "specials", "29.00", False, False, True, 20),
            ("Seasonal Risotto", "specials", "24.00", True, False, False, 18),
        ]

        pizza_items: list[MenuItem] = []
        burger_items: list[MenuItem] = []
        for idx, (name, cat_slug, price, veg, spicy, popular, prep) in enumerate(menu_defs):
            item = MenuItem(
                restaurant_id=restaurant.id,
                category_id=categories[cat_slug].id,
                name=name,
                description=f"Freshly prepared {name.lower()}.",
                price=Decimal(price),
                image_url=MENU_IMAGES.get(name),
                is_available=True,
                preparation_time_minutes=prep,
                is_vegetarian=veg,
                is_spicy=spicy,
                is_popular=popular,
                sort_order=idx,
            )
            db.add(item)
            db.flush()
            if cat_slug == "pizza":
                pizza_items.append(item)
            if cat_slug == "burgers":
                burger_items.append(item)

        for item in pizza_items:
            db.add(MenuItemModifier(menu_item_id=item.id, modifier_id=size_modifier.id))
            db.add(MenuItemModifier(menu_item_id=item.id, modifier_id=extras_modifier.id))
        for item in burger_items:
            db.add(MenuItemModifier(menu_item_id=item.id, modifier_id=burger_modifier.id))

        tables = []
        for number, capacity in [
            ("T1", 2), ("T2", 2), ("T3", 4), ("T4", 4), ("T5", 4),
            ("T6", 6), ("T7", 6), ("T8", 8), ("P1", 2), ("P2", 4), ("B1", 10),
        ]:
            zone, shape, x, y = DEMO_LAYOUT[number]
            table = RestaurantTable(
                restaurant_id=restaurant.id,
                table_number=number,
                capacity=capacity,
                status=TableStatus.AVAILABLE,
                zone=zone,
                shape=shape,
                pos_x=x,
                pos_y=y,
            )
            db.add(table)
            db.flush()
            tables.append(table)

        addresses = []
        for customer, street in zip(customers, ["88 Oak Street", "220 Pine Avenue", "15 Harbor View"]):
            addr = Address(
                user_id=customer.id,
                label="Home",
                street=street,
                city="San Francisco",
                postal_code="94105",
            )
            db.add(addr)
            db.flush()
            addresses.append(addr)

        def create_order(
            *,
            customer: User,
            order_type: OrderType,
            status: OrderStatus,
            items: list[tuple[MenuItem, int]],
            table: RestaurantTable | None = None,
            address: Address | None = None,
            order_no: str,
        ) -> Order:
            subtotal = sum(item.price * qty for item, qty in items)
            tax = (subtotal * restaurant.tax_rate).quantize(Decimal("0.01"))
            delivery_fee = restaurant.delivery_fee if order_type == OrderType.DELIVERY else Decimal("0.00")
            total = subtotal + tax + delivery_fee
            order = Order(
                user_id=customer.id,
                restaurant_id=restaurant.id,
                order_number=order_no,
                order_type=order_type,
                status=status,
                subtotal=subtotal,
                tax=tax,
                delivery_fee=delivery_fee,
                discount=Decimal("0.00"),
                total=total,
                customer_name=customer.full_name,
                customer_email=customer.email,
                customer_phone=customer.phone,
                table_id=table.id if table else None,
                delivery_address_id=address.id if address else None,
            )
            db.add(order)
            db.flush()
            for menu_item, qty in items:
                line_total = menu_item.price * qty
                db.add(
                    OrderItem(
                        order_id=order.id,
                        menu_item_id=menu_item.id,
                        item_name=menu_item.name,
                        quantity=qty,
                        unit_price=menu_item.price,
                        line_total=line_total,
                    )
                )
            db.add(
                OrderStatusHistory(
                    order_id=order.id,
                    previous_status=None,
                    new_status=OrderStatus.PENDING,
                    changed_by_user_id=customer.id,
                )
            )
            if status != OrderStatus.PENDING:
                db.add(
                    OrderStatusHistory(
                        order_id=order.id,
                        previous_status=OrderStatus.PENDING,
                        new_status=status,
                        changed_by_user_id=staff.id,
                    )
                )
            db.add(
                Payment(
                    order_id=order.id,
                    amount=total,
                    status=PaymentStatus.COMPLETED if status != OrderStatus.CANCELLED else PaymentStatus.REFUNDED,
                    payment_method=PaymentMethod.MOCK,
                    provider_reference=f"mock_{order_no}",
                )
            )
            return order

        all_items = db.scalars(select(MenuItem).where(MenuItem.restaurant_id == restaurant.id)).all()
        item_by_name = {item.name: item for item in all_items}

        create_order(
            customer=customers[0],
            order_type=OrderType.DELIVERY,
            status=OrderStatus.OUT_FOR_DELIVERY,
            items=[(item_by_name["Pepperoni Pizza"], 1), (item_by_name["Craft Lemonade"], 2)],
            address=addresses[0],
            order_no="BV-10001",
        )
        create_order(
            customer=customers[1],
            order_type=OrderType.PICKUP,
            status=OrderStatus.PREPARING,
            items=[(item_by_name["Classic Smash Burger"], 2), (item_by_name["Truffle Fries"], 1)],
            order_no="BV-10002",
        )
        dine_in_order = create_order(
            customer=customers[2],
            order_type=OrderType.DINE_IN,
            status=OrderStatus.READY,
            items=[(item_by_name["Margherita Pizza"], 1), (item_by_name["Caesar Salad"], 1)],
            table=tables[2],
            order_no="BV-10003",
        )
        create_order(
            customer=customers[0],
            order_type=OrderType.DELIVERY,
            status=OrderStatus.COMPLETED,
            items=[(item_by_name["Tiramisu"], 2)],
            address=addresses[0],
            order_no="BV-10004",
        )
        create_order(
            customer=customers[1],
            order_type=OrderType.PICKUP,
            status=OrderStatus.CANCELLED,
            items=[(item_by_name["Spaghetti Bolognese"], 1)],
            order_no="BV-10005",
        )

        # Parties currently seated at T3 and T6 — table status is derived from these bookings.
        seated_from = datetime.now(timezone.utc) - timedelta(minutes=30)
        for table, guest, party, order in (
            (tables[2], customers[2], 2, dine_in_order),
            (tables[5], customers[1], 4, None),
        ):
            db.add(
                Reservation(
                    restaurant_id=restaurant.id,
                    table_id=table.id,
                    user_id=guest.id,
                    order_id=order.id if order else None,
                    party_size=party,
                    starts_at=seated_from,
                    ends_at=seated_from + timedelta(minutes=90),
                    status=ReservationStatus.SEATED,
                    guest_name=f"{guest.first_name} {guest.last_name}",
                    guest_email=guest.email,
                    guest_phone=guest.phone,
                )
            )
            table.status = TableStatus.OCCUPIED

        starts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=3)
        db.add(
            Reservation(
                restaurant_id=restaurant.id,
                table_id=tables[0].id,
                user_id=customers[0].id,
                party_size=2,
                starts_at=starts,
                ends_at=starts + timedelta(minutes=90),
                status=ReservationStatus.CONFIRMED,
                guest_name=f"{customers[0].first_name} {customers[0].last_name}",
                guest_email=customers[0].email,
                guest_phone=customers[0].phone,
            )
        )

        db.commit()
        logger.info("Seed complete for restaurant_id=%s", restaurant.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
