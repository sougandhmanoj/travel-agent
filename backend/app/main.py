"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.data.places import PlaceRepository, SupabasePlaceRepository, UnavailablePlaceRepository
from app.routing.road import RoadRoutingProvider, UnavailableRoadRoutingProvider
from app.routing.testing import DeterministicRoadRoutingProvider


def create_app(
    *,
    settings: Settings | None = None,
    place_repository: PlaceRepository | None = None,
    road_provider: RoadRoutingProvider | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    if place_repository is None:
        if (
            active_settings.supabase_url is not None
            and active_settings.supabase_service_role_key is not None
        ):
            place_repository = SupabasePlaceRepository(
                str(active_settings.supabase_url),
                active_settings.supabase_service_role_key.get_secret_value(),
            )
        else:
            place_repository = UnavailablePlaceRepository()
    if road_provider is None:
        if active_settings.road_routing_provider == "deterministic_test":
            if active_settings.environment == "production":
                raise RuntimeError("The deterministic test provider cannot run in production")
            road_provider = DeterministicRoadRoutingProvider()
        else:
            road_provider = UnavailableRoadRoutingProvider()

    application = FastAPI(
        title=active_settings.app_name,
        description=(
            "Explanation-first journey planning for supported South Indian cities and "
            "transport hubs. Milestone 2 exposes Road; the candidate contract is ready for "
            "Rail and Air."
        ),
        version=active_settings.app_version,
        debug=active_settings.debug,
    )
    application.state.place_repository = place_repository
    application.state.road_provider = road_provider
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    application.include_router(
        api_router,
        prefix=active_settings.api_v1_prefix,
    )

    @application.get("/", tags=["System"])
    def root() -> dict[str, str]:
        return {"message": "South India Travel Guide API", "documentation": "/docs"}

    return application


app = create_app()
