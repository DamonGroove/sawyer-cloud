"""Settings loaded from env. One source of truth for runtime config."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All process env overrides. DATABASE_URL is the only required field."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # --- Database (async for app; sync for alembic) --------------------
    database_url: str = Field(
        default="postgresql+asyncpg://sawyer:sawyer@localhost:5432/sawyer",
        description="Async SQLAlchemy URL for the app runtime.",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg://sawyer:sawyer@localhost:5432/sawyer",
        description="Sync URL for alembic (alembic's env.py reads this).",
    )

    # --- OIDC (stubbed in Phase 2) ------------------------------------
    oidc_issuer: str = "http://oidc-mock.invalid"
    oidc_client_id: str = "sawyer-mgmt-dev"
    oidc_client_secret: str = "CHANGEME"

    # --- Session / JWT ------------------------------------------------
    session_secret: str = "CHANGEME"
    jwt_algorithm: str = "HS256"
    jwt_lifetime_seconds: int = 3600

    # --- Object store (branding bundles) -------------------------------
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minio-admin"
    s3_secret_key: str = "minio-admin-pw"
    s3_bucket: str = "branding-bundles"

    # --- Misc ---------------------------------------------------------
    log_level: str = "INFO"
    environment: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
