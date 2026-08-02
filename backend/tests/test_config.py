import pytest

from app.core.config import Settings
from app.main import create_app


def test_deterministic_provider_is_forbidden_in_production() -> None:
    settings = Settings(environment="production", road_routing_provider="deterministic_test")
    with pytest.raises(RuntimeError, match="cannot run in production"):
        create_app(settings=settings)
