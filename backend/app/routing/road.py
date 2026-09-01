"""Provider-neutral road-routing contract.

Providers must return observed/calculated route facts. The planning engine validates
the response and never fills missing provider facts with invented route data.
"""

from typing import Any, Protocol, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models import Coordinates, LegRole, NormalizedEndpoint, RouteGeometry


class RoadRouteRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    origin: NormalizedEndpoint
    destination: NormalizedEndpoint
    require_first_mile: bool
    require_last_mile: bool


class RoadRouteSegment(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: LegRole
    origin_name: str
    destination_name: str
    origin: Coordinates
    destination: Coordinates
    distance_metres: int = Field(gt=0)
    duration_seconds: int = Field(gt=0)
    geometry: RouteGeometry
    toll_cost_inr: int | None = Field(default=None, ge=0)


class RoadRoute(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str = Field(min_length=1)
    provider_label: str = Field(min_length=1)
    segments: list[RoadRouteSegment] = Field(min_length=1)


class RoadRoutingError(RuntimeError):
    """A routing provider could not return a trustworthy route."""


class RoadRoutingProvider(Protocol):
    def route(self, request: RoadRouteRequest) -> RoadRoute: ...


class UnavailableRoadRoutingProvider:
    """Safe default until an external routing adapter is configured."""

    def route(self, request: RoadRouteRequest) -> RoadRoute:
        del request
        raise RoadRoutingError("No road-routing provider is configured")


class OsrmRoadRoutingProvider:
    """Road-route adapter using OSRM's provider-calculated road geometry."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=20.0,
            transport=transport,
            headers={"User-Agent": "Waystory/0.3 local-development"},
        )

    def route(self, request: RoadRouteRequest) -> RoadRoute:
        start = request.origin.location
        end = request.destination.location
        coordinates = f"{start.longitude},{start.latitude};{end.longitude},{end.latitude}"
        try:
            response = self._client.get(
                f"/route/v1/driving/{coordinates}",
                params={"overview": "full", "geometries": "geojson", "steps": "false"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RoadRoutingError("The road-routing service is temporarily unavailable") from exc
        if not isinstance(payload, dict) or payload.get("code") != "Ok":
            code = payload.get("code") if isinstance(payload, dict) else None
            message = (
                "No drivable road route was found"
                if code == "NoRoute"
                else "The road-routing service returned invalid data"
            )
            raise RoadRoutingError(message)
        routes = payload.get("routes")
        if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
            raise RoadRoutingError("The road-routing service returned no route")
        route = cast(dict[str, Any], routes[0])
        geometry = route.get("geometry")
        raw_coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if not isinstance(raw_coordinates, list) or len(raw_coordinates) < 2:
            raise RoadRoutingError("The road-routing service returned no usable geometry")
        try:
            route_geometry = RouteGeometry(
                coordinates=[(float(item[0]), float(item[1])) for item in raw_coordinates]
            )
            distance_metres = round(float(route["distance"]))
            duration_seconds = round(float(route["duration"]))
        except (KeyError, TypeError, ValueError, IndexError, ValidationError) as exc:
            raise RoadRoutingError("The road-routing service returned invalid route facts") from exc
        return RoadRoute(
            provider_id="osrm",
            provider_label="OSRM road route using OpenStreetMap data",
            segments=[
                RoadRouteSegment(
                    role=LegRole.MAIN,
                    origin_name=request.origin.name,
                    destination_name=request.destination.name,
                    origin=start,
                    destination=end,
                    distance_metres=distance_metres,
                    duration_seconds=duration_seconds,
                    geometry=route_geometry,
                    toll_cost_inr=None,
                )
            ],
        )
