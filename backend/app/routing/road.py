"""Provider-neutral road-routing contract.

Providers must return observed/calculated route facts. The planning engine validates
the response and never fills missing provider facts with invented route data.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

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
