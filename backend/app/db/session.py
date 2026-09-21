"""Database engine and session factory, plus the per-request tenant context for row-level security.

Row-level security (RLS): every tenant table has a PostgreSQL policy that, when a transaction is in *tenant mode*,
only lets it see and change rows of one restaurant. Enforcement is switched on at the points that already decide who
is asking and for which restaurant (`enter_tenant_mode`): staff routes, signed-in customers and table guests.
Everything else (sign-in, public menus, QR lookups, background jobs, the operator CLI) runs in the default *bypass*
mode and relies on the explicit restaurant filters in the code, as before. RLS only bites when the app connects as
the restricted role (`APP_DATABASE_URL`): the owner role bypasses it by design.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.runtime_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_TENANT_SQL = text("SELECT set_config('app.rls_mode', 'tenant', true), set_config('app.tenant_id', :tenant, true)")
_BYPASS_SQL = text("SELECT set_config('app.rls_mode', 'bypass', true), set_config('app.tenant_id', '', true)")


def enter_tenant_mode(db: Session, tenant_id: int) -> None:
    """From now on this session may only see and change one restaurant's rows (enforced by PostgreSQL).

    Applies to the transaction in progress and to every later transaction of the session (a request commits several
    times), so it cannot be lost mid-request.
    """
    db.info["rls_tenant"] = int(tenant_id)
    db.execute(_TENANT_SQL, {"tenant": str(int(tenant_id))})


def enter_bypass_mode(db: Session) -> None:
    """Back to the default: no database-level restriction (used by trusted paths and to reset a reused session)."""
    db.info.pop("rls_tenant", None)
    db.execute(_BYPASS_SQL)


@event.listens_for(Session, "after_begin")
def _apply_tenant_mode(session: Session, transaction, connection) -> None:
    """Each new transaction of a tenant-mode session re-applies the restriction (`set_config(..., true)` lasts only
    until the transaction ends, so a pooled connection never carries it to someone else)."""
    tenant = session.info.get("rls_tenant")
    if tenant is not None:
        connection.execute(_TENANT_SQL, {"tenant": str(tenant)})


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
