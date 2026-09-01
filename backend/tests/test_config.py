import pytest

from app.core.config import Settings
from app.data.places import SupabasePlaceRepository, UnavailablePlaceRepository
from app.main import create_app
from app.providers.google_routes import GoogleRoutesRailItineraryProvider


def test_deterministic_provider_is_forbidden_in_production() -> None:
    settings = Settings(environment="production", road_routing_provider="deterministic_test")
    with pytest.raises(RuntimeError, match="cannot run in production"):
        create_app(settings=settings)

    multimodal = Settings(environment="production", multimodal_provider="deterministic_test")
    with pytest.raises(RuntimeError, match="cannot run in production"):
        create_app(settings=multimodal)


def test_development_can_use_auth_disabled_local_supabase() -> None:
    app = create_app(settings=Settings.model_validate({"supabase_url": "http://127.0.0.1:54421"}))
    assert isinstance(app.state.place_repository, SupabasePlaceRepository)


def test_production_still_requires_server_credentials() -> None:
    app = create_app(
        settings=Settings.model_validate(
            {
                "environment": "production",
                "supabase_url": "https://example.supabase.co",
            }
        )
    )
    assert isinstance(app.state.place_repository, UnavailablePlaceRepository)


def test_google_routes_provider_requires_server_api_key() -> None:
    with pytest.raises(RuntimeError, match="GOOGLE_ROUTES_API_KEY"):
        create_app(settings=Settings(multimodal_provider="google_routes"))

    app = create_app(
        settings=Settings.model_validate(
            {
                "multimodal_provider": "google_routes",
                "google_routes_api_key": "server-key",
            }
        )
    )
    assert isinstance(app.state.rail_itinerary_provider, GoogleRoutesRailItineraryProvider)
