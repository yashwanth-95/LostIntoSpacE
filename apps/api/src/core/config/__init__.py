"""Application settings loaded from environment variables / the repo-root .env file."""

from functools import lru_cache

from dotenv import find_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(usecwd=True),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    app_env: str = "development"
    debug: bool = True
    log_level: str = "info"

    # Backend
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # CORS - comma-separated list of allowed origins.
    # 3000 is the port apps/web/vite.config.ts serves on; the previous 5173
    # default named Vite's stock port, which this project does not use.
    cors_origins: str = "http://localhost:3000"

    # Database. The URL always comes from the environment; this default points at
    # a local development database and contains no real credentials.
    database_url: str = "postgresql+asyncpg://lostintospace:password@localhost:5432/lostintospace"
    database_echo: bool = False
    # Separate database for the test suite, so running tests can never touch
    # development data. Only used when TEST_DATABASE_URL is set; tests that need
    # a live database skip when it is absent.
    test_database_url: str | None = None

    # Redis (optional)
    redis_url: str | None = None

    # External APIs
    nasa_api_key: str = "DEMO_KEY"

    # Storage
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 50

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def validate_production_safety(self) -> None:
        """Refuse to run with an obviously-unsafe config in production.

        Closes docs/backend/KNOWN_ISSUES.md D-2 (2026-08-18 audit): nothing previously
        stopped the app from booting in production with the example secret key.
        """
        if self.app_env == "production" and self.secret_key == "change-me-in-production":
            raise RuntimeError(
                "SECRET_KEY is still the example default while APP_ENV=production. "
                "Set a real SECRET_KEY before starting in production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
