"""Create (or refresh) the restricted database role the running app connects as.

    python -m app.db.roles

Reads APP_DATABASE_URL for the role's name and password and connects with DATABASE_URL (the owner). Safe to run on
every deploy: it creates the role if missing, updates its password, and grants it only ordinary data access (no
superuser, no CREATEDB/CREATEROLE, and crucially no BYPASSRLS, so the row-level security policies apply to it).
Run it after migrations, since new tables need their grants (it also sets default privileges for future ones).
"""

import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import settings


def ensure_app_role(owner_url: str, app_url: str) -> str:
    target = make_url(app_url)
    role, password = target.username, target.password
    if not role or not password:
        raise SystemExit("APP_DATABASE_URL needs a user name and password")
    if role == make_url(owner_url).username:
        raise SystemExit("APP_DATABASE_URL must use a different role from DATABASE_URL, or nothing is restricted")
    database = make_url(owner_url).database

    # DDL cannot take bound parameters, so identifiers and the password are quoted by the driver's own escaping.
    dsn = make_url(owner_url).set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(dsn, autocommit=True) as conn:
        who, db = sql.Identifier(role), sql.Identifier(database)
        exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
        verb = sql.SQL("ALTER" if exists else "CREATE")
        conn.execute(sql.SQL("{} ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS").format(verb, who, sql.Literal(password)))
        for statement in (
            "GRANT CONNECT ON DATABASE {db} TO {who}",
            "GRANT USAGE ON SCHEMA public TO {who}",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {who}",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {who}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {who}",
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {who}",
        ):
            conn.execute(sql.SQL(statement).format(db=db, who=who))
    return role


def main() -> int:
    if not settings.APP_DATABASE_URL:
        print("APP_DATABASE_URL is not set: the app will connect as the owner and row-level security is NOT enforced.")
        return 0
    role = ensure_app_role(settings.DATABASE_URL, settings.APP_DATABASE_URL)
    print(f"Database role '{role}' is ready: row-level security is enforced for the running app.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
