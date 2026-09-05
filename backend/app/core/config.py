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

    frontend_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ]

    # These values are consumed only by the backend process. Never expose the
    # service-role key through a VITE_* variable or browser bundle.
    supabase_url: AnyHttpUrl | None = None
    supabase_service_role_key: SecretStr | None = None
    road_routing_provider: Literal[
        "unavailable", "deterministic_test", "osrm", "google_routes"
    ] = "unavailable"
    osrm_base_url: AnyHttpUrl = "https://router.project-osrm.org"  # type: ignore[assignment]
    multimodal_provider: Literal[
        "unavailable", "deterministic_test", "google_routes", "railradar"
    ] = "unavailable"
    google_routes_api_key: SecretStr | None = None
    google_routes_base_url: AnyHttpUrl = "https://routes.googleapis.com"  # type: ignore[assignment]
    railradar_api_key: SecretStr | None = None
    railradar_base_url: AnyHttpUrl = "https://api.railradar.in/v1"  # type: ignore[assignment]

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
