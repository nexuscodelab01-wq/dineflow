"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Prefer repo-root .env when running from backend/; fall back to local .env
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"
_LOCAL_ENV = Path(__file__).resolve().parents[2] / ".env"
_ENV_FILES = tuple(
    str(path) for path in (_ROOT_ENV, _LOCAL_ENV, Path(".env")) if path.is_file()
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES or ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "DineFlow"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # The database the *running app* connects as. Point it at the restricted `dineflow_app` role (see docs/OPERATIONS.md,
    # "Row-level security") and PostgreSQL itself keeps each restaurant's rows apart. Empty = use DATABASE_URL (the owner,
    # which bypasses row-level security). Migrations, the seed and the operator CLI always use DATABASE_URL.
    APP_DATABASE_URL: str = ""
    DATABASE_URL: str = (
        "postgresql+psycopg://dineflow:dineflow_dev_password@localhost:5432/dineflow"
    )

    JWT_SECRET: str = "change-me-access-secret-min-32-chars-long"
    JWT_REFRESH_SECRET: str = "change-me-refresh-secret-min-32-chars-long"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Multi-tenancy. A restaurant's site is reached at <slug>.<PLATFORM_DOMAIN> (or its own custom domain).
    # In development set PLATFORM_DOMAIN=localhost so <slug>.localhost:3000 works, and DEFAULT_TENANT_SLUG so
    # plain localhost:3000 opens one restaurant. Leave both empty in production unless you want a default.
    PLATFORM_DOMAIN: str = ""
    DEFAULT_TENANT_SLUG: str = ""
    RESERVED_SUBDOMAINS: str = "www,admin,api,app,static,assets,cdn,mail,status,docs,platform"

    # QR table ordering: a single round can't exceed this total (stops prank/remote orders).
    QR_MAX_ORDER_TOTAL: float = 500.0

    # Abuse protection. The limiter is in-process (per worker); move it to Redis when we run
    # several workers/instances (roadmap stage A2).
    RATE_LIMIT_ENABLED: bool = True
    # Read the client IP from X-Forwarded-For. Only enable behind a proxy you control,
    # otherwise anyone can spoof their IP and dodge the limits.
    TRUST_PROXY_HEADERS: bool = False

    # File storage. "local" writes to backend/uploads (fine for one server / development);
    # "s3" uses any S3-compatible service (AWS S3, Cloudflare R2, MinIO, DigitalOcean Spaces).
    STORAGE_BACKEND: str = "local"
    # Public base URL files are served from (bucket/CDN URL). Required for "s3"; for "local" the
    # default "/uploads" (served by this API) is used.
    STORAGE_PUBLIC_URL: str = ""
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""  # blank for AWS; set for R2 / MinIO / Spaces
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    IMAGE_MAX_SIDE: int = 1600  # uploaded photos are scaled down to this many pixels on the long side

    # Background jobs (Postgres-backed queue). Each API process runs a worker thread by default;
    # set RUN_JOB_WORKER=false and start `python -m app.worker` separately for a dedicated worker.
    RUN_JOB_WORKER: bool = True
    JOB_POLL_SECONDS: float = 5.0  # safety-net poll; workers are also woken instantly by NOTIFY
    JOB_STUCK_MINUTES: int = 10  # a job "running" this long is assumed orphaned by a crashed worker

    # Email. "console" logs messages (development), "smtp" sends through any SMTP service
    # (SES, Postmark, Mailgun, Gmail…), "memory" keeps them in a list (tests).
    EMAIL_BACKEND: str = "console"
    EMAIL_FROM_ADDRESS: str = "noreply@dineflow.local"  # the address mail is sent from (display name = the restaurant)
    EMAIL_SMTP_HOST: str = ""
    EMAIL_SMTP_PORT: int = 587
    EMAIL_SMTP_USER: str = ""
    EMAIL_SMTP_PASSWORD: str = ""
    EMAIL_SMTP_SECURITY: str = "starttls"  # starttls | ssl | none
    PUBLIC_SITE_URL: str = "http://localhost:3000"  # links inside emails point here
    PUBLIC_API_URL: str = "http://localhost:8000"  # where uploaded logos are served from

    # Live-update connections (SSE) one worker will hold open before shedding load.
    REALTIME_MAX_STREAMS: int = 200

    # Observability
    LOG_FORMAT: str = "text"  # "text" (dev) or "json" (production log shippers)
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

    @property
    def runtime_database_url(self) -> str:
        return self.APP_DATABASE_URL or self.DATABASE_URL

    @property
    def rls_enforced(self) -> bool:
        return bool(self.APP_DATABASE_URL) and self.APP_DATABASE_URL != self.DATABASE_URL

    @property
    def reserved_subdomains(self) -> set[str]:
        return {s.strip().lower() for s in self.RESERVED_SUBDOMAINS.split(",") if s.strip()}

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "production"

    def assert_production_ready(self) -> None:
        """Refuse to boot in production with placeholder secrets (a classic way to get owned)."""
        if not self.is_production:
            return
        problems = []
        for name in ("JWT_SECRET", "JWT_REFRESH_SECRET"):
            value = getattr(self, name)
            if value.startswith("change-me") or len(value) < 32:
                problems.append(f"{name} must be a unique random value of at least 32 characters")
        if self.JWT_SECRET == self.JWT_REFRESH_SECRET:
            problems.append("JWT_SECRET and JWT_REFRESH_SECRET must differ")
        if "dineflow_dev_password" in self.DATABASE_URL:
            problems.append("DATABASE_URL still uses the development database password")
        if "dineflow_app_dev_password" in self.APP_DATABASE_URL:
            problems.append("APP_DATABASE_URL still uses the development password for the restricted role")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
