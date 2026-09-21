"""Operator commands. Run inside the backend container:

    python -m app.cli features <restaurant-slug>                 # show every flag for a restaurant
    python -m app.cli features <restaurant-slug> <flag> on|off|default
    python -m app.cli audit [<restaurant-slug>]                  # recent sensitive changes
"""

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


def main(argv: list[str]) -> int:
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
