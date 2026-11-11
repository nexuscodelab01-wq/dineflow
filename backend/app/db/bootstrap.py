"""What every start-up must guarantee, with or without demo data: the built-in roles and the catalogue of feature flags.

This used to happen only inside the demo seed, so a deployment that (rightly) runs with RUN_SEED=false would never learn
about flags added in later releases and the platform console couldn't switch them on. It's idempotent and touches nothing
that already exists, so it is safe to run on every boot of a live database.
"""

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.user import RoleRepository
from app.services.feature_service import FeatureService


def run(db: Session) -> None:
    RoleRepository(db).ensure_defaults()
    FeatureService(db).ensure_defaults()
    db.commit()


def main() -> None:
    db = SessionLocal()
    try:
        run(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
