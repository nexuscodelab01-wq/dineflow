"""Operator commands. Run inside the backend container:

    python -m app.cli features <restaurant-slug>                 # show every flag for a restaurant
    python -m app.cli features <restaurant-slug> <flag> on|off|default
    python -m app.cli audit [<restaurant-slug>]                  # recent sensitive changes
    python -m app.cli create-tenant --name "Luigi's" --slug luigis --owner owner@luigis.com \\
        [--color "#c0392b"] [--logo path/to/logo.png] [--template generic|pizzeria|cafe] [--timezone "America/Los_Angeles"]
        [--owner-name "Luigi Rossi"] [--no-branding] [--send-invite]
"""

import argparse
import sys

from app.core.exceptions import AppError
from app.db.session import SessionLocal
from app.repositories.restaurant import RestaurantRepository
from app.services.feature_service import FeatureService

USAGE = __doc__


def _restaurant(db, slug: str):
    restaurant = RestaurantRepository(db).get_by_slug(slug)
    if restaurant is None:
        sys.exit(f"No restaurant with slug '{slug}'")
    return restaurant


def create_tenant(argv: list[str]) -> int:
    from pathlib import Path

    from app.core.config import settings
    from app.services.tenant_provisioning import TEMPLATES, provision_tenant

    parser = argparse.ArgumentParser(prog="python -m app.cli create-tenant")
    parser.add_argument("--name", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--owner", required=True, help="email of the restaurant's admin")
    parser.add_argument("--owner-name", default="Owner")
    parser.add_argument("--color", help="brand colour, e.g. #c0392b")
    parser.add_argument("--logo", help="path to a PNG/JPEG/WebP logo")
    parser.add_argument("--template", default="generic", choices=sorted(TEMPLATES))
    parser.add_argument("--timezone", default="UTC", help='IANA name, e.g. "America/Los_Angeles" (default: UTC)')
    parser.add_argument("--no-branding", action="store_true", help="don't switch on custom branding")
    parser.add_argument("--send-invite", action="store_true", help="email the owner their set-password link (needs email configured)")
    args = parser.parse_args(argv)

    logo = None
    if args.logo:
        path = Path(args.logo)
        if not path.is_file():
            sys.exit(f"Logo file not found: {args.logo}")
        logo = path.read_bytes()
    with SessionLocal() as db:
        try:
            result = provision_tenant(
                db, name=args.name, slug=args.slug, owner_email=args.owner, owner_name=args.owner_name, color=args.color,
                logo=logo, template=args.template, timezone=args.timezone, branding=not args.no_branding, send_invite=args.send_invite,
            )
        except AppError as exc:
            sys.exit(exc.message)
    domain = settings.PLATFORM_DOMAIN
    print(f"Created '{result.name}' (id {result.restaurant_id}, orders {result.order_prefix}-1001…)")
    if domain:
        port = ":3000" if domain == "localhost" else ""
        print(f"  Site:    http://{args.slug}.{domain}{port}")
    print(f"  Admin:   {result.owner_email}")
    if result.invite_link:
        print(f"  Set password (one-time link, valid 7 days): {result.invite_link}")
        print("           Sent by email too." if args.send_invite else "           Send that link to the owner (or re-run with --send-invite next time).")
    else:
        print("           (existing account: it keeps its password and now also manages this restaurant)")
    return 0


def main(argv: list[str]) -> int:
    if argv and argv[0] == "create-tenant":
        return create_tenant(argv[1:])
    if len(argv) < 2 or argv[0] not in {"features", "audit"}:
        print(USAGE)
        return 2
    with SessionLocal() as db:
        service = FeatureService(db)
        if argv[0] == "audit":
            rid = _restaurant(db, argv[1]).id if len(argv) > 1 else None
            for row in service.audit_log(rid):
                print(f"{row.created_at:%Y-%m-%d %H:%M}  {row.actor_label:<28} {row.action:<14} {row.target}  {row.details}")
            return 0
        restaurant = _restaurant(db, argv[1])
        if len(argv) == 4:
            value = {"on": True, "off": False, "default": None}.get(argv[3])
            if argv[3] not in {"on", "off", "default"}:
                print(USAGE)
                return 2
            try:
                service.set(restaurant.id, argv[2], value, None, actor_label="cli")
            except AppError as exc:
                sys.exit(exc.message)
        for f in service.listing(restaurant.id):
            mark = "on " if f["enabled"] else "off"
            note = "" if f["override"] is None else "  (override)"
            print(f"{mark}  {f['key']:<20} {f['description']}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
