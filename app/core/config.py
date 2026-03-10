from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Smart Auth API"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    secret_key: str = "change-me"
    log_level: str = "INFO"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smart_auth"
    redis_url: str = "redis://localhost:6379/0"
    public_backend_url: str = "http://localhost"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost", "http://127.0.0.1"]
    prometheus_public_url: str | None = None
    grafana_public_url: str | None = None

    rate_limit_auth_requests: int = 5
    rate_limit_auth_window_seconds: int = 60
    rate_limit_fail_closed: bool = True
    trust_proxy_headers: bool = False
    trusted_proxy_cidrs: Annotated[list[str], NoDecode] = []

    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""

    @field_validator("cors_origins", "trusted_proxy_cidrs", mode="before")
    @classmethod
    def parse_csv_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("public_backend_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("prometheus_public_url", "grafana_public_url")
    @classmethod
    def normalize_optional_urls(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().rstrip("/")
        return normalized or None

    @model_validator(mode="after")
    def validate_production_configuration(self) -> Settings:
        if self.app_env.lower() != "production":
            return self

        if self.debug:
            raise ValueError("DEBUG must be false when APP_ENV is production")

        if self.secret_key in {"", "change-me", "change-this-in-production"} or len(self.secret_key) < 64:
            raise ValueError("SECRET_KEY must be a strong non-placeholder value in production")

        public_url = urlparse(self.public_backend_url)
        if public_url.scheme != "https" or not public_url.netloc:
            raise ValueError("PUBLIC_BACKEND_URL must be a valid HTTPS URL in production")
        if public_url.hostname in {"localhost", "127.0.0.1"}:
            raise ValueError("PUBLIC_BACKEND_URL cannot point to localhost in production")

        if "@localhost" in self.database_url or "@127.0.0.1" in self.database_url:
            raise ValueError("DATABASE_URL cannot point to localhost in production")

        if self.trust_proxy_headers and not self.trusted_proxy_cidrs:
            raise ValueError("TRUSTED_PROXY_CIDRS must be set when TRUST_PROXY_HEADERS is enabled")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
