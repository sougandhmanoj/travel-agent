"""Versioned HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.data.places import PlaceRepository, PlaceRepositoryError
from app.models import JourneyPlanRequest, JourneyPlanResponse, PlaceSearchResponse
from app.providers.transit import (
    AirServiceProvider,
    FareEstimateProvider,
    LocalTransferProvider,
    RailItineraryProvider,
    RailServiceProvider,
)
from app.routing.road import RoadRoutingProvider
from app.services.journeys import JourneyPlanningService, PlaceNotFoundError, SameEndpointError

api_router = APIRouter()

JOURNEY_RESPONSE_EXAMPLES = {
    "multimodal_pattern": {
        "summary": "Complete Rail-led pattern with access, onboard stop, and egress",
        "value": {
            "travel_date": "2026-08-20",
            "recommended_mode": "rail",
            "recommendation_explanation": "Recommended after scoring the complete itinerary.",
            "candidates": [
                {
                    "candidate_id": "rail-1",
                    "mode": "rail",
                    "dominant_mode": "rail",
                    "status": "available",
                    "recommended": True,
                    "transfer_count": 2,
                    "intermediate_stops": [
                        {"name": "Dharwad", "guidance": "Stay onboard this service."}
                    ],
                    "connections": [
                        {
                            "kind": "suggested_buffer",
                            "location_name": "Karmali",
                            "guidance": "Planning guidance, not a guaranteed connection.",
                        }
                    ],
                }
            ],
        },
    },
    "unavailable_modes": {
        "summary": "Rail unavailable and Flight omitted because no complete pattern is feasible",
        "value": {
            "recommended_mode": "road",
            "candidates": [
                {
                    "candidate_id": "rail-unavailable",
                    "mode": "rail",
                    "status": "unavailable",
                    "unavailable_reason": "No Rail options available",
                }
            ],
        },
    },
    "manual_verification": {
        "summary": "No trustworthy recommendation; partial possibility requires verification",
        "value": {
            "recommended_mode": None,
            "recommendation_explanation": "No trustworthy recommendation is available.",
            "candidates": [
                {
                    "candidate_id": "rail-1",
                    "mode": "rail",
                    "status": "unverified",
                    "verification_requirements": [
                        {
                            "subject": "Services and selected date",
                            "required": True,
                            "guidance": "Verify operation, times, fare, and every connection.",
                        }
                    ],
                }
            ],
        },
    },
}


def get_place_repository(request: Request) -> PlaceRepository:
    return request.app.state.place_repository  # type: ignore[no-any-return]


def get_road_provider(request: Request) -> RoadRoutingProvider:
    return request.app.state.road_provider  # type: ignore[no-any-return]


def get_rail_provider(request: Request) -> RailServiceProvider:
    return request.app.state.rail_provider  # type: ignore[no-any-return]


def get_rail_itinerary_provider(request: Request) -> RailItineraryProvider | None:
    return request.app.state.rail_itinerary_provider  # type: ignore[no-any-return]


def get_air_provider(request: Request) -> AirServiceProvider:
    return request.app.state.air_provider  # type: ignore[no-any-return]


def get_local_provider(request: Request) -> LocalTransferProvider:
    return request.app.state.local_provider  # type: ignore[no-any-return]


def get_fare_provider(request: Request) -> FareEstimateProvider:
    return request.app.state.fare_provider  # type: ignore[no-any-return]


@api_router.get("/health", tags=["System"])
def health_check(request: Request) -> dict[str, str]:
    return {"status": "ok", "version": request.app.version}


@api_router.get(
    "/places/search",
    tags=["Places"],
    response_model=PlaceSearchResponse,
    responses={
        200: {
            "description": "Ranked suggestions across all supported cities/localities and hubs.",
            "content": {
                "application/json": {
                    "example": {
                        "query": "goa",
                        "results": [
                            {
                                "place_id": "hub_00001",
                                "name": "Goa International Airport",
                                "place_type": "airport",
                                "locality_or_city": "Vasco da Gama",
                                "state": "Goa",
                                "code": "GOI",
                                "latitude": 15.3805865,
                                "longitude": 73.8326572,
                            }
                        ],
                    }
                }
            },
        }
    },
)
def search_places(
    repository: Annotated[PlaceRepository, Depends(get_place_repository)],
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> PlaceSearchResponse:
    query = " ".join(q.split())
    if not query:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="q is required",
        )
    try:
        return PlaceSearchResponse(query=query, results=repository.search(query))
    except PlaceRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Place data is temporarily unavailable",
        ) from exc


@api_router.post(
    "/journeys/plan",
    tags=["Journeys"],
    response_model=JourneyPlanResponse,
    responses={
        200: {
            "description": "Educational complete-itinerary patterns and honest unavailable states.",
            "content": {"application/json": {"examples": JOURNEY_RESPONSE_EXAMPLES}},
        },
        404: {"description": "A well-formed place ID is not in the supported dataset."},
        409: {"description": "Origin and destination identify the same place."},
        503: {"description": "Supported-place data is temporarily unavailable."},
    },
)
def plan_journey(
    plan_request: JourneyPlanRequest,
    repository: Annotated[PlaceRepository, Depends(get_place_repository)],
    road_provider: Annotated[RoadRoutingProvider, Depends(get_road_provider)],
    rail_provider: Annotated[RailServiceProvider, Depends(get_rail_provider)],
    rail_itinerary_provider: Annotated[
        RailItineraryProvider | None, Depends(get_rail_itinerary_provider)
    ],
    air_provider: Annotated[AirServiceProvider, Depends(get_air_provider)],
    local_provider: Annotated[LocalTransferProvider, Depends(get_local_provider)],
    fare_provider: Annotated[FareEstimateProvider, Depends(get_fare_provider)],
) -> JourneyPlanResponse:
    try:
        return JourneyPlanningService(
            repository,
            road_provider,
            rail_provider=rail_provider,
            rail_itinerary_provider=rail_itinerary_provider,
            air_provider=air_provider,
            local_provider=local_provider,
            fare_provider=fare_provider,
        ).plan(plan_request)
    except PlaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SameEndpointError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PlaceRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Place data is temporarily unavailable",
        ) from exc
