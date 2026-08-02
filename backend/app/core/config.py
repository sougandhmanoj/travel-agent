from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    """Configuration loaded from environment variables or a local .env file."""

    app_name: str = "South India Travel Guide API"
    app_version: str = __version__
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    frontend_origins: list[str] = ["http://localhost:5173"]

    supabase_url: AnyHttpUrl | None = None
    supabase_key: SecretStr | None = None
    google_routes_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return one cached Settings instance for the application process."""

    return Settings()