"""Immutable identities and scenario data shared across pipeline stages.

CGR contacts and routes are working objects. Snapshots deliberately contain no
search/forwarding state, so a completed catalog can be reused across runs.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from modules.network.topology import Topology, topology_load

if TYPE_CHECKING:
    from modules.network.cgr.models import Contact, Route

NodePair = tuple[int, int]


@dataclass(frozen=True, slots=True, order=True)
class RouteRef:
    pair: NodePair
    candidate_id: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", tuple(self.pair))
        if len(self.pair) != 2 or self.pair[0] == self.pair[1]:
            raise ValueError("a route requires two distinct endpoint nodes")
        if not isinstance(self.candidate_id, int) or self.candidate_id < 1:
            raise ValueError("candidate_id must be a positive integer")

    def __str__(self) -> str:
        return f"{self.pair[0]}->{self.pair[1]}:route-{self.candidate_id}"


@dataclass(frozen=True, slots=True, order=True)
class PlanRef:
    route: RouteRef
    policy_id: str

    def __post_init__(self) -> None:
        if not self.policy_id or not self.policy_id.strip():
            raise ValueError("policy_id must not be empty")

    def __str__(self) -> str:
        return f"{self.route}:{self.policy_id}"


@dataclass(frozen=True, slots=True, order=True)
class OperationRef:
    plan: PlanRef
    local_id: str

    def __post_init__(self) -> None:
        if not self.local_id or not self.local_id.strip():
            raise ValueError("local_id must not be empty")

    def __str__(self) -> str:
        return f"{self.plan}:{self.local_id}"


@dataclass(frozen=True, slots=True)
class ContactSnapshot:
    frm: int
    to: int
    start: int
    end: int
    rate: int
    owlt: int = 0
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.end <= self.start or self.rate <= 0 or self.owlt < 0:
            raise ValueError("contact requires end > start, rate > 0 and owlt >= 0")
        if not 0 <= self.confidence <= 1:
            raise ValueError("contact confidence must be between zero and one")

    @classmethod
    def from_contact(cls, contact: Contact) -> ContactSnapshot:
        return cls(contact.frm, contact.to, contact.start, contact.end,
                   contact.rate, contact.owlt, contact.confidence)


@dataclass(frozen=True, slots=True)
class RouteCandidate:
    ref: RouteRef
    contacts: tuple[ContactSnapshot, ...]
    best_delivery_time: int | float
    volume: int | float
    confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "contacts", tuple(self.contacts))
        if not self.contacts:
            raise ValueError("route must contain at least one hop")
        if any(not isinstance(contact, ContactSnapshot) for contact in self.contacts):
            raise TypeError("route contacts must be immutable ContactSnapshot objects")
        if (self.contacts[0].frm, self.contacts[-1].to) != self.ref.pair:
            raise ValueError("route endpoints do not match its reference")
        if any(left.to != right.frm for left, right in zip(self.contacts, self.contacts[1:])):
            raise ValueError("route contacts must form a continuous path")

    @classmethod
    def from_route(cls, ref: RouteRef, route: Route) -> RouteCandidate:
        return cls(ref, tuple(ContactSnapshot.from_contact(c) for c in route.get_hops()),
                   route.best_delivery_time, route.volume, route.confidence)


@dataclass(frozen=True, slots=True)
class Scenario:
    topology: Topology
    contacts: tuple[ContactSnapshot, ...]
    pairs: tuple[NodePair, ...] | None = None

    def __post_init__(self) -> None:
        contacts = tuple(self.contacts)
        if any(not isinstance(contact, ContactSnapshot) for contact in contacts):
            raise TypeError("scenario contacts must be immutable ContactSnapshot objects")
        nodes = tuple(sorted(self.topology))
        pairs = (
            tuple((source, destination) for source in nodes for destination in nodes if source != destination)
            if self.pairs is None else tuple(tuple(pair) for pair in self.pairs)
        )
        if len(set(pairs)) != len(pairs):
            raise ValueError("scenario pairs must be unique")
        for pair in pairs:
            if len(pair) != 2 or pair[0] == pair[1] or any(node not in self.topology for node in pair):
                raise ValueError(f"invalid scenario pair: {pair}")
        for contact in contacts:
            if contact.frm not in self.topology or contact.to not in self.topology:
                raise ValueError("contact endpoints must belong to the scenario topology")
        object.__setattr__(self, "contacts", contacts)
        object.__setattr__(self, "pairs", pairs)

    @classmethod
    def from_files(cls, *, topology_path: str | Path, contact_plan_path: str | Path) -> Scenario:
        from modules.network.cgr.loader import cp_load
        return cls(topology_load(str(topology_path)), tuple(
            ContactSnapshot.from_contact(contact) for contact in cp_load(str(contact_plan_path))
        ))
