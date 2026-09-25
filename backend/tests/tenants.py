"""Builders for multi-tenant tests: complete, independent restaurants that must never see each other."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.category import Category
from app.models.enums import ReservationStatus, RoleName, TableStatus
from app.models.menu_item import MenuItem
from app.models.menu_item_modifier import MenuItemModifier
from app.models.menu_modifier import MenuModifier
from app.models.menu_modifier_option import MenuModifierOption
from app.models.reservation import Reservation
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from app.models.waitlist_entry import WaitlistEntry


def header(user: User) -> dict[str, str]:
    """A bearer token exactly as login issues it: role plus the tenant the identity belongs to."""
    role = user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)
    token = create_access_token(str(user.id), claims={"role": role, "tenant": user.restaurant_id})
    return {"Authorization": f"Bearer {token}"}


def make_user(db: Session, email: str, role: RoleName, *, restaurant_id: int | None = None, first: str = "Test") -> User:
    role_row = db.query(Role).filter(Role.name == role.value).one()
    user = User(
        email=email, hashed_password=hash_password("Test1234!"), first_name=first, last_name="User",
        role_id=role_row.id, restaurant_id=restaurant_id,
    )
    db.add(user)
    db.flush()
    db.refresh(user)
    return user


def make_tenant(db: Session, label: str) -> SimpleNamespace:
    """One restaurant with staff, an admin, a customer, a menu, a table and a booking.

    Everything is named after `label` so leaks are obvious in assertion output.
    """
    restaurant = Restaurant(
        name=f"{label} Kitchen", slug=f"{label.lower()}-kitchen", tax_rate=Decimal("0.10"), delivery_fee=Decimal("2.00"),
        order_prefix=label[:2].upper(),
    )
    db.add(restaurant)
    db.flush()

    admin = make_user(db, f"admin-{label.lower()}@iso-demo.com", RoleName.RESTAURANT_ADMIN, first=label)
    staff = make_user(db, f"staff-{label.lower()}@iso-demo.com", RoleName.RESTAURANT_STAFF, first=label)
    customer = make_user(db, f"cust-{label.lower()}@iso-demo.com", RoleName.CUSTOMER, restaurant_id=restaurant.id, first=label)
    db.add_all([
        RestaurantUser(restaurant_id=restaurant.id, user_id=admin.id, role=RoleName.RESTAURANT_ADMIN),
        RestaurantUser(restaurant_id=restaurant.id, user_id=staff.id, role=RoleName.RESTAURANT_STAFF),
    ])

    category = Category(restaurant_id=restaurant.id, name=f"{label} Mains", slug="mains")
    db.add(category)
    db.flush()
    item = MenuItem(restaurant_id=restaurant.id, category_id=category.id, name=f"{label} Burger", price=Decimal("12.00"))
    modifier = MenuModifier(restaurant_id=restaurant.id, name=f"{label} Size")
    db.add_all([item, modifier])
    db.flush()
    option = MenuModifierOption(modifier_id=modifier.id, name=f"{label} Large", price_adjustment=Decimal("2.00"))
    db.add_all([option, MenuItemModifier(menu_item_id=item.id, modifier_id=modifier.id)])

    table = RestaurantTable(restaurant_id=restaurant.id, table_number=f"{label[0]}1", capacity=4, status=TableStatus.AVAILABLE)
    db.add(table)
    db.flush()
    start = datetime.now(timezone.utc) + timedelta(days=2)
    reservation = Reservation(
        restaurant_id=restaurant.id, table_id=table.id, user_id=customer.id, party_size=2, guest_name=f"{label} Guest",
        starts_at=start, ends_at=start + timedelta(minutes=90), status=ReservationStatus.CONFIRMED,
    )
    db.add(reservation)
    waitlist_entry = WaitlistEntry(restaurant_id=restaurant.id, guest_name=f"{label} Walk-in", party_size=2)
    db.add(waitlist_entry)
    db.flush()
    db.expire_all()

    return SimpleNamespace(
        label=label, restaurant=restaurant, rid=restaurant.id, slug=restaurant.slug,
        admin=db.get(User, admin.id), staff=db.get(User, staff.id), customer=db.get(User, customer.id),
        category=category, item=item, modifier=modifier, option=option, table=table, reservation=reservation,
        waitlist_entry=waitlist_entry, order=None,
    )


def place_order(client, tenant, *, quantity: int = 1):
    """The tenant's own customer orders one of its own burgers (goes through the real API)."""
    return client.post("/api/v1/orders", headers=header(tenant.customer), json={
        "restaurant_id": tenant.rid, "order_type": "PICKUP", "customer_name": tenant.customer.full_name,
        "customer_email": tenant.customer.email,
        "items": [{"menu_item_id": tenant.item.id, "quantity": quantity, "modifier_option_ids": []}],
    })
