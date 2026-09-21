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

    DATABASE_URL: str = (
        "postgresql+psycopg://dineflow:dineflow_dev_password@localhost:5432/dineflow"
    )

    JWT_SECRET: str = "change-me-access-secret-min-32-chars-long"
    JWT_REFRESH_SECRET: str = "change-me-refresh-secret-min-32-chars-long"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Abuse protection. The limiter is in-process (per worker); move it to Redis when we run
    # several workers/instances (roadmap stage A2).
    RATE_LIMIT_ENABLED: bool = True
    # Read the client IP from X-Forwarded-For. Only enable behind a proxy you control,
    # otherwise anyone can spoof their IP and dodge the limits.
    TRUST_PROXY_HEADERS: bool = False

    # Observability
    LOG_FORMAT: str = "text"  # "text" (dev) or "json" (production log shippers)
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.0

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
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
