"""Versioned HTTP endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.data.places import PlaceRepository, PlaceRepositoryError
from app.models import JourneyPlanRequest, JourneyPlanResponse, PlaceSearchResponse
from app.routing.road import RoadRoutingProvider
from app.services.journeys import JourneyPlanningService, PlaceNotFoundError, SameEndpointError

api_router = APIRouter()


def get_place_repository(request: Request) -> PlaceRepository:
    return request.app.state.place_repository  # type: ignore[no-any-return]


def get_road_provider(request: Request) -> RoadRoutingProvider:
    return request.app.state.road_provider  # type: ignore[no-any-return]


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
        404: {"description": "A well-formed place ID is not in the supported dataset."},
        409: {"description": "Origin and destination identify the same place."},
        503: {"description": "Supported-place data is temporarily unavailable."},
    },
)
def plan_journey(
    plan_request: JourneyPlanRequest,
    repository: Annotated[PlaceRepository, Depends(get_place_repository)],
    road_provider: Annotated[RoadRoutingProvider, Depends(get_road_provider)],
) -> JourneyPlanResponse:
    try:
        return JourneyPlanningService(repository, road_provider).plan(plan_request)
    except PlaceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SameEndpointError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PlaceRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Place data is temporarily unavailable",
        ) from exc
