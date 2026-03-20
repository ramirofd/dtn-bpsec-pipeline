from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from modules.network.cgr.algorithms import cgr_anchor, cgr_depleted, cgr_ended, cgr_yen
from modules.network.cgr.models import Route

if TYPE_CHECKING:
    from modules.network.cgr.algorithms import ContactPlan
    from modules.network.topology import Topology


@dataclass(slots=True, frozen=True)
class RoutingRequest:
    source: int
    destination: int
    curr_time: int
    contact_plan: ContactPlan
    topology: Topology
    num_routes: int | None = None


class RoutingAlgorithm(ABC):
    name = "routing_algorithm"

    @abstractmethod
    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        raise NotImplementedError


class CGRYenRouting(RoutingAlgorithm):
    name = "cgr_yen"

    def __init__(self, max_routes: int = 3) -> None:
        self.max_routes = max_routes

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_yen(
            source=request.source,
            destination=request.destination,
            curr_time=request.curr_time,
            contact_plan=request.contact_plan,
            num_routes=request.num_routes or self.max_routes,
        )


class CGRAnchorRouting(RoutingAlgorithm):
    name = "cgr_anchor"

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_anchor(
            source=request.source,
            destination=request.destination,
            curr_time=request.curr_time,
            contact_plan=request.contact_plan,
        )


class CGREndedRouting(RoutingAlgorithm):
    name = "cgr_ended"

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_ended(
            source=request.source,
            destination=request.destination,
            curr_time=request.curr_time,
            contact_plan=request.contact_plan,
        )


class CGRDepletedRouting(RoutingAlgorithm):
    name = "cgr_depleted"

    def __init__(self, keep_residual_volume: bool = False) -> None:
        self.keep_residual_volume = keep_residual_volume

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_depleted(
            source=request.source,
            destination=request.destination,
            curr_time=request.curr_time,
            contact_plan=request.contact_plan,
            keep_residual_volume=self.keep_residual_volume,
        )

def ensure_routing_algorithm(
    routing_algorithm: RoutingAlgorithm | None,
    *,
    default_num_routes: int = 3,
) -> RoutingAlgorithm:
    if routing_algorithm is None:
        return CGRYenRouting(max_routes=default_num_routes)
    return routing_algorithm
