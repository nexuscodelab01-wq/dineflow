"""Creating a complete, ready-to-demo restaurant in one go (used by `python -m app.cli create-tenant`).

Nothing is written unless everything is valid: the slug, colour and logo are checked first, and the
restaurant, its starter content and its owner are created in a single transaction.
"""

import re
import secrets
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError
from app.core.images import InvalidImage, process_image
from app.core.security import hash_password
from app.core.stations import CATEGORY_STATIONS, DEFAULT_STATION
from app.core.storage import get_storage, tenant_prefix
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.enums import RoleName, TableStatus
from app.models.menu_item import MenuItem
from app.models.restaurant import Restaurant
from app.models.restaurant_table import RestaurantTable
from app.models.restaurant_user import RestaurantUser
from app.models.role import Role
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.feature_service import FeatureService
from app.services.password_service import PasswordService

SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]{0,60}[a-z0-9])?$")
COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

HOURS = {day: "11:00-22:00" for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")}

# category -> [(name, description, price, vegetarian, popular)]
TEMPLATES: dict[str, dict[str, list[tuple[str, str, str, bool, bool]]]] = {
    "generic": {
        "Starters": [("House Salad", "Seasonal greens, house dressing", "8.50", True, False),
                     ("Soup of the Day", "Ask your server", "7.00", True, False)],
        "Mains": [("Grilled Chicken", "With roasted vegetables", "17.50", False, True),
                  ("Vegetable Curry", "Coconut, rice", "15.00", True, False),
                  ("Steak Frites", "Sirloin, herb butter", "24.00", False, True)],
        "Desserts": [("Chocolate Cake", "Warm, with cream", "8.00", True, True)],
        "Drinks": [("Sparkling Water", "500 ml", "3.50", True, False), ("Fresh Lemonade", "House made", "4.50", True, False)],
    },
    "pizzeria": {
        "Pizza": [("Margherita", "Tomato, mozzarella, basil", "12.00", True, True),
                  ("Pepperoni", "Spicy salami, mozzarella", "14.00", False, True),
                  ("Quattro Formaggi", "Four cheeses", "15.00", True, False)],
        "Pasta": [("Spaghetti Carbonara", "Guanciale, egg, pecorino", "15.50", False, False),
                  ("Penne Arrabbiata", "Spicy tomato", "13.00", True, False)],
        "Starters": [("Garlic Bread", "With herb butter", "6.00", True, False), ("Bruschetta", "Tomato, basil", "7.50", True, False)],
        "Drinks": [("Sparkling Water", "500 ml", "3.50", True, False), ("Italian Soda", "Blood orange", "4.50", True, False)],
    },
    "cafe": {
        "Coffee": [("Flat White", "Double shot, silky milk", "4.20", True, True),
                   ("Cappuccino", "", "4.00", True, False), ("Iced Latte", "", "4.80", True, False)],
        "Breakfast": [("Avocado Toast", "Sourdough, chilli, lime", "11.00", True, True),
                      ("Granola Bowl", "Yoghurt, berries", "9.50", True, False)],
        "Bakery": [("Butter Croissant", "Baked this morning", "3.80", True, True), ("Blueberry Muffin", "", "3.90", True, False)],
    },
}

# (number, seats, zone, x %, y %): placed on the floor plan so a new restaurant's map looks tidy straight away
TABLES = [
    ("1", 2, "Main", 14, 28), ("2", 2, "Main", 32, 28), ("3", 4, "Main", 50, 28), ("4", 4, "Main", 68, 28), ("5", 6, "Main", 86, 28),
    ("6", 4, "Patio", 30, 72), ("7", 2, "Patio", 58, 72),
]


@dataclass
class Provisioned:
    """Plain values (not ORM objects), so callers can use them after the session is closed."""

    restaurant_id: int
    name: str
    slug: str
    order_prefix: str
    owner_email: str
    invite_link: str | None  # a one-time link to choose a password; None when the owner already had an account


def order_prefix(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"['’]", "", name))  # "Luigi's" is one word
    initials = "".join(w[0] for w in words)[:4].upper()
    return initials if len(initials) >= 2 else (re.sub(r"[^A-Za-z0-9]", "", name)[:3].upper() or "DF")


def provision_tenant(
    db: Session,
    *,
    name: str,
    slug: str,
    owner_email: str,
    color: str | None = None,
    logo: bytes | None = None,
    template: str = "generic",
    owner_name: str = "Owner",
    branding: bool = True,
    send_invite: bool = False,
) -> Provisioned:
    name = name.strip()
    if not name:
        raise AppError("A restaurant needs a name")
    if not SLUG.match(slug) or slug in settings.reserved_subdomains:
        raise AppError("Slug must be lowercase letters, numbers and dashes (and not a reserved name like 'www')")
    if template not in TEMPLATES:
        raise AppError(f"Unknown template '{template}'. Choose one of: {', '.join(TEMPLATES)}")
    if color is not None and not COLOR.match(color):
        raise AppError("Colour must look like #1a7f5a")
    if db.scalar(select(Restaurant.id).where(Restaurant.slug == slug)) is not None:
        raise ConflictError(f"A restaurant with slug '{slug}' already exists")

    processed = None
    if logo is not None:  # validate before writing anything
        try:
            processed = process_image(logo, max_side=800, thumb_side=None, max_bytes=settings.MAX_UPLOAD_BYTES)
        except InvalidImage as exc:
            raise AppError(f"Logo: {exc}") from exc

    restaurant = Restaurant(
        name=name, slug=slug, order_prefix=order_prefix(name), primary_color=color.lower() if color else None,
        opening_hours=HOURS, tax_rate=Decimal("0.0800"), delivery_fee=Decimal("3.99"),
    )
    db.add(restaurant)
    db.flush()

    if processed is not None:
        key = f"{tenant_prefix(restaurant.id, 'branding')}/{uuid.uuid4().hex}{processed.extension}"
        restaurant.logo_url = get_storage().save(key, processed.main, processed.content_type)

    for order, (category_name, items) in enumerate(TEMPLATES[template].items()):
        category = Category(restaurant_id=restaurant.id, name=category_name, slug=category_name.lower().replace(" ", "-"), sort_order=order)
        db.add(category)
        db.flush()
        for position, (item, description, price, vegetarian, popular) in enumerate(items):
            db.add(MenuItem(
                restaurant_id=restaurant.id, category_id=category.id, name=item, description=description or None,
                price=Decimal(price), is_vegetarian=vegetarian, is_popular=popular, sort_order=position,
                station=CATEGORY_STATIONS.get(category_name, DEFAULT_STATION),
            ))
    for number, seats, zone, x, y in TABLES:
        db.add(RestaurantTable(
            restaurant_id=restaurant.id, table_number=number, capacity=seats, zone=zone, pos_x=x, pos_y=y, status=TableStatus.AVAILABLE))

    owner, is_new = _owner(db, owner_email, owner_name)
    restaurant_id = restaurant.id
    db.add(RestaurantUser(restaurant_id=restaurant_id, user_id=owner.id))
    db.add(AuditLog(
        restaurant_id=restaurant.id, actor_label="cli", action="tenant.create", target=slug,
        details={"template": template, "color": color, "owner": owner.email},
    ))
    prefix, owner_email = restaurant.order_prefix, owner.email
    invite_link = PasswordService(db).issue_link(owner, restaurant, invite=True, send=send_invite) if is_new else None
    db.commit()

    if branding:  # commits on its own; the tenant already exists either way
        FeatureService(db).set(restaurant.id, "custom_branding", True, None, actor_label="cli")
    return Provisioned(restaurant_id, name, slug, prefix, owner_email, invite_link)


def _owner(db: Session, email: str, full_name: str) -> tuple[User, bool]:
    users = UserRepository(db)
    existing = users.get_by_email(email)  # a global identity (staff): reuse it, e.g. an agency running many restaurants
    if existing is not None:
        return existing, False
    role = db.scalar(select(Role).where(Role.name == RoleName.RESTAURANT_ADMIN.value))
    first, _, last = full_name.strip().partition(" ")
    # The owner never sees a password: this one is random and thrown away, and they set their own from the invite link.
    user = users.create(email=email, hashed_password=hash_password(secrets.token_urlsafe(32)), first_name=first or "Owner", last_name=last or "-", role_id=role.id)
    return user, True
