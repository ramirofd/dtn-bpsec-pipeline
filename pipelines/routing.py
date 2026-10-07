"""Routing contracts and adapters; CGR working state stays inside each call."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from modules.domain import ContactSnapshot, Scenario
from modules.network.cgr.algorithms import cgr_anchor, cgr_depleted, cgr_ended, cgr_yen
from modules.network.cgr.models import Contact, Route
from modules.network.topology import Topology


def _validate_limit(limit: int | None) -> None:
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("num_routes must be a positive integer or None")


@dataclass(frozen=True, slots=True)
class RoutingBatchRequest:
    scenario: Scenario
    curr_time: int = 0
    num_routes: int | None = None

    def __post_init__(self) -> None:
        _validate_limit(self.num_routes)


@dataclass(frozen=True, slots=True)
class RoutingRequest:
    source: int
    destination: int
    curr_time: int
    contacts: tuple[ContactSnapshot, ...]
    topology: Topology
    num_routes: int | None = None

    def __post_init__(self) -> None:
        _validate_limit(self.num_routes)
        object.__setattr__(self, "contacts", tuple(self.contacts))


def _working_contacts(request: RoutingRequest) -> list[Contact]:
    return [Contact(frm=c.frm, to=c.to, start=c.start, end=c.end, rate=c.rate,
                    owlt=c.owlt, confidence=c.confidence) for c in request.contacts]


class RoutingAlgorithm(ABC):
    """Adapter boundary for a single pair. Returned CGR routes are snapshotted.

    Input snapshots must remain unchanged. Each adapter owns its search state;
    batch route limits are enforced once more by RoutingStage for every adapter.
    """
    name = "routing_algorithm"

    @abstractmethod
    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        raise NotImplementedError


class CGRYenRouting(RoutingAlgorithm):
    name = "cgr_yen"

    def __init__(self, max_routes: int = 3) -> None:
        _validate_limit(max_routes)
        self.max_routes = max_routes

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_yen(source=request.source, destination=request.destination,
                       curr_time=request.curr_time, contact_plan=_working_contacts(request),
                       num_routes=self.max_routes if request.num_routes is None else request.num_routes)


class CGRAnchorRouting(RoutingAlgorithm):
    name = "cgr_anchor"

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_anchor(source=request.source, destination=request.destination,
                          curr_time=request.curr_time, contact_plan=_working_contacts(request))


class CGREndedRouting(RoutingAlgorithm):
    name = "cgr_ended"

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_ended(source=request.source, destination=request.destination,
                         curr_time=request.curr_time, contact_plan=_working_contacts(request))


class CGRDepletedRouting(RoutingAlgorithm):
    name = "cgr_depleted"

    def __init__(self, keep_residual_volume: bool = False) -> None:
        self.keep_residual_volume = keep_residual_volume

    def compute_routes(self, request: RoutingRequest) -> list[Route]:
        return cgr_depleted(source=request.source, destination=request.destination,
                            curr_time=request.curr_time, contact_plan=_working_contacts(request),
                            keep_residual_volume=self.keep_residual_volume)
