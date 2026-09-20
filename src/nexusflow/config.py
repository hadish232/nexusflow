from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ----------------------------------------------------------
    # Application
    # ----------------------------------------------------------

    app_name: str = "NexusFlow"
    app_env: str = "development"
    debug: bool = False

    # ----------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------

    secret_key: str = Field(min_length=32)

    jwt_algorithm: str = "HS256"

    access_token_expire_minutes: int = 30

    # ----------------------------------------------------------
    # PostgreSQL
    # ----------------------------------------------------------

    database_url: str

    database_url_sync: str

    db_pool_size: int = Field(default=10, ge=1, le=100)

    db_max_overflow: int = Field(default=20, ge=0, le=200)

    db_pool_timeout: int = Field(default=30, ge=1, le=300)

    db_pool_recycle: int = Field(default=1800, ge=60, le=86400)

    # ----------------------------------------------------------
    # Redis
    # ----------------------------------------------------------

    redis_url: str

    # ----------------------------------------------------------
    # Celery
    # ----------------------------------------------------------

    celery_broker_url: str

    celery_result_backend: str

    # ----------------------------------------------------------
    # API
    # ----------------------------------------------------------

    cors_origins: str = ""

    # ----------------------------------------------------------
    # Rate limiting
    # ----------------------------------------------------------

    job_rate_limit_per_ip: int = Field(
        default=60,
        ge=1,
    )

    job_rate_limit_per_tenant: int = Field(
        default=300,
        ge=1,
    )

    job_rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
    )

    # ----------------------------------------------------------
    # Outbox
    # ----------------------------------------------------------

    outbox_poll_seconds: float = Field(
        default=2.0,
        gt=0,
    )

    outbox_batch_size: int = Field(
        default=100,
        ge=1,
        le=1000,
    )

    # ----------------------------------------------------------
    # Job execution
    # ----------------------------------------------------------

    job_max_retries: int = Field(
        default=5,
        ge=0,
        le=20,
    )

    job_retry_max_delay: int = Field(
        default=60,
        ge=1,
        le=3600,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()