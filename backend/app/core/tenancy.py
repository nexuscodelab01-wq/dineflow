"""Tenant (restaurant) rules shared by routes and services.

A tenant is one restaurant. Its site lives at ``<slug>.<PLATFORM_DOMAIN>`` or on its own custom domain.
Customers belong to exactly one tenant; staff and platform admins are global identities that reach
restaurants through memberships.
"""

import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.models.enums import RoleName
from app.models.restaurant import Restaurant
from app.models.user import User

_SLUG = re.compile(r"^[a-z0-9]([a-z0-9-]{0,60}[a-z0-9])?$")


def role_value(user: User) -> str:
    return user.role.name.value if hasattr(user.role.name, "value") else str(user.role.name)


def ensure_customer_of(user: User, restaurant_id: int) -> None:
    """A customer may only act inside the restaurant they signed up at."""
    if role_value(user) == RoleName.CUSTOMER.value and user.restaurant_id != restaurant_id:
        raise ForbiddenError("Your account belongs to a different restaurant")


def normalize_host(host: str) -> str:
    """Lower-case hostname without port or trailing dot."""
    host = host.strip().lower()
    if host.startswith("["):  # IPv6 literal: leave alone
        return host
    return host.split(":", 1)[0].rstrip(".")


def slug_from_host(host: str) -> str | None:
    """The subdomain label when the host is directly under PLATFORM_DOMAIN, else None."""
    platform = normalize_host(settings.PLATFORM_DOMAIN) if settings.PLATFORM_DOMAIN else ""
    if not platform:
        return None
    host = normalize_host(host)
    if not host.endswith("." + platform):
        return None
    label = host[: -(len(platform) + 1)]
    if "." in label or not _SLUG.match(label) or label in settings.reserved_subdomains:
        return None
    return label


def resolve_tenant(db: Session, host: str | None) -> Restaurant | None:
    """Find the active restaurant a request for ``host`` is meant for."""
    from sqlalchemy import func, select

    restaurant: Restaurant | None = None
    if host:
        normalized = normalize_host(host)
        slug = slug_from_host(normalized)
        if slug:
            restaurant = db.scalar(select(Restaurant).where(Restaurant.slug == slug))
        else:
            restaurant = db.scalar(
                select(Restaurant).where(func.lower(Restaurant.custom_domain) == normalized)
            )
    if restaurant is None and settings.DEFAULT_TENANT_SLUG:
        # Only bare/unknown-but-not-claimed hosts fall back; a host that names a subdomain never does.
        if not host or slug_from_host(host) is None:
            restaurant = db.scalar(select(Restaurant).where(Restaurant.slug == settings.DEFAULT_TENANT_SLUG))
    if restaurant is not None and not restaurant.is_active:
        return None
    return restaurant


def origin_regex() -> str | None:
    """CORS: any subdomain of the platform domain (custom domains are allowed via CORS_ORIGINS)."""
    platform = normalize_host(settings.PLATFORM_DOMAIN) if settings.PLATFORM_DOMAIN else ""
    if not platform:
        return None
    return rf"^https?://([a-z0-9-]+\.)?{re.escape(platform)}(:\d+)?$"


def site_url(restaurant) -> str:
    """The address of a restaurant's own site, for links in emails (`https://pizza.dineflow.app`, or its custom
    domain). Falls back to PUBLIC_SITE_URL when the restaurant has no address of its own (or there is no restaurant)."""
    from urllib.parse import urlsplit

    base = urlsplit(settings.PUBLIC_SITE_URL)
    port = f":{base.port}" if base.port else ""
    if restaurant is not None and getattr(restaurant, "custom_domain", None):
        return f"{base.scheme}://{restaurant.custom_domain}{port if base.scheme == 'http' else ''}"
    platform = normalize_host(settings.PLATFORM_DOMAIN) if settings.PLATFORM_DOMAIN else ""
    if restaurant is not None and platform:
        return f"{base.scheme}://{restaurant.slug}.{platform}{port}"
    return settings.PUBLIC_SITE_URL.rstrip("/")
