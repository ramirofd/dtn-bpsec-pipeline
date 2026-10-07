"""Read-only stage outputs connected by explicit domain references."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from modules.domain import NodePair, PlanRef, RouteCandidate, RouteRef, Scenario
from modules.security.annotated_routes import AnnotatedRoute
from modules.security.artifacts import ProtectionPlan
from modules.security.models import SecurityModelType


@dataclass(frozen=True, slots=True)
class RouteCatalog:
    scenario: Scenario
    by_id: Mapping[RouteRef, RouteCandidate]
    routes_by_pair: Mapping[NodePair, tuple[RouteRef, ...]] = field(init=False)

    def __post_init__(self) -> None:
        by_id = dict(self.by_id)
        grouped: dict[NodePair, list[RouteRef]] = {pair: [] for pair in self.scenario.pairs}
        for ref, candidate in by_id.items():
            if ref != candidate.ref:
                raise ValueError("route catalog key must equal candidate reference")
            if ref.pair not in grouped:
                raise ValueError("route reference is outside scenario pairs")
            if any(c.frm not in self.scenario.topology or c.to not in self.scenario.topology for c in candidate.contacts):
                raise ValueError("route contacts are outside the scenario topology")
            grouped[ref.pair].append(ref)
        object.__setattr__(self, "by_id", MappingProxyType(by_id))
        object.__setattr__(self, "routes_by_pair", MappingProxyType({pair: tuple(sorted(refs)) for pair, refs in grouped.items()}))


@dataclass(frozen=True, slots=True)
class AnnotationCatalog:
    routes: RouteCatalog
    by_route: Mapping[RouteRef, AnnotatedRoute]

    def __post_init__(self) -> None:
        by_route = dict(self.by_route)
        if set(by_route) != set(self.routes.by_id):
            raise ValueError("annotation catalog must cover exactly the route references")
        for ref, annotation in by_route.items():
            if ref != annotation.ref or ref.pair != (annotation.src_node, annotation.dst_node):
                raise ValueError("annotation reference must match its route")
            contacts = self.routes.by_id[ref].contacts
            expected_nodes = (contacts[0].frm, *(contact.to for contact in contacts))
            if annotation.node_path != expected_nodes:
                raise ValueError("annotation node path must match its candidate")
            topology = self.routes.scenario.topology
            if len(annotation.hops) != len(contacts):
                raise ValueError("annotation hops must cover every candidate contact")
            for index, (hop, contact) in enumerate(zip(annotation.hops, contacts, strict=True)):
                if (hop.hop_index, hop.from_node, hop.to_node) != (index, contact.frm, contact.to):
                    raise ValueError("annotation hop indices and endpoints must match candidate contacts")
                if (hop.from_network, hop.to_network) != (topology[contact.frm], topology[contact.to]):
                    raise ValueError("annotation hop networks must match the scenario topology")
            if annotation.network_path != tuple(topology[node] for node in expected_nodes):
                raise ValueError("annotation network path must match the scenario topology")
        object.__setattr__(self, "by_route", MappingProxyType(by_route))


@dataclass(frozen=True, slots=True)
class ProtectionCatalog:
    annotations: AnnotationCatalog
    policies: Mapping[str, SecurityModelType]
    by_plan: Mapping[PlanRef, ProtectionPlan]

    def __post_init__(self) -> None:
        policies = dict(self.policies)
        by_plan = dict(self.by_plan)
        if any(not policy or not policy.strip() for policy in policies):
            raise ValueError("policy identifiers must not be empty")
        expected = {PlanRef(ref, policy) for ref in self.annotations.by_route for policy in policies}
        if set(by_plan) != expected:
            raise ValueError("protection catalog must cover every route and policy combination")
        for ref, plan in by_plan.items():
            if ref != plan.ref or plan.model != policies[ref.policy_id]:
                raise ValueError("protection plan identity or family does not match its catalog")
            operation_refs = {operation.ref for operation in plan.operations}
            if len(operation_refs) != len(plan.operations):
                raise ValueError("operation references must be unique within a plan")
            if any(operation.plan != ref for operation in operation_refs):
                raise ValueError("operation must refer to its containing plan")
            if any(requirement.operation_ref not in operation_refs for requirement in (*plan.node_requirements, *plan.key_requirements)):
                raise ValueError("security requirements must refer to an operation in their plan")
            hop_count = len(self.annotations.by_route[ref.route].hops)
            if any(operation.model != plan.model or any(index < 0 or index >= hop_count for index in operation.target_hop_indexes) for operation in plan.operations):
                raise ValueError("operation family and target hops must match its annotated route")
        object.__setattr__(self, "policies", MappingProxyType(policies))
        object.__setattr__(self, "by_plan", MappingProxyType(by_plan))
