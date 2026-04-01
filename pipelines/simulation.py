from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from modules.network.py_cgr_lib import Route, cp_load
from modules.network.topology import Topology, topology_load
from modules.security.annotated_routes import AnnotatedRoute, annotate_routes
from modules.security.models import SecurityModelType
from modules.security.planning import ProtectionPlan
from pipelines.routing import RoutingAlgorithm, RoutingRequest, ensure_routing_algorithm
from pipelines.security import build_protection_plans

if TYPE_CHECKING:
    from modules.network.cgr.algorithms import ContactPlan


@dataclass(slots=True, frozen=True)
class NodePairRoutesResult:
    source: int
    destination: int
    routes: tuple[Route, ...]


@dataclass(slots=True, frozen=True)
class RoutingBatchResult:
    topology: Topology
    contact_plan_size: int
    node_pair_results: tuple[NodePairRoutesResult, ...]


@dataclass(slots=True, frozen=True)
class AnnotatedNodePairResult:
    source: int
    destination: int
    routes: tuple[Route, ...]
    annotated_routes: tuple[AnnotatedRoute, ...]


@dataclass(slots=True, frozen=True)
class AnnotationBatchResult:
    topology: Topology
    contact_plan_size: int
    node_pair_results: tuple[AnnotatedNodePairResult, ...]


@dataclass(slots=True, frozen=True)
class SecurityModelResult:
    model: SecurityModelType
    protection_plans: tuple[ProtectionPlan, ...]


@dataclass(slots=True, frozen=True)
class SecurityNodePairResult:
    source: int
    destination: int
    routes: tuple[Route, ...]
    annotated_routes: tuple[AnnotatedRoute, ...]
    security_results: tuple[SecurityModelResult, ...]


@dataclass(slots=True, frozen=True)
class SecurityBatchResult:
    topology: Topology
    contact_plan_size: int
    node_pair_results: tuple[SecurityNodePairResult, ...]


@dataclass(slots=True, frozen=True)
class SimulationResult:
    topology: Topology
    contact_plan_size: int
    routing: RoutingBatchResult
    annotation: AnnotationBatchResult
    security: SecurityBatchResult


def run_simulation(
    cp_path: str,
    topology_path: str,
    node_pairs: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None,
    security_models: list[SecurityModelType] | tuple[SecurityModelType, ...] | None = None,
    curr_time: int = 0,
    routing_algorithm: RoutingAlgorithm | None = None,
    num_routes: int = 3,
) -> SimulationResult:
    topology = topology_load(topology_path)
    contact_plan = cp_load(cp_path)
    resolved_pairs = _resolve_node_pairs(topology, node_pairs)
    resolved_models = _resolve_security_models(security_models)

    routing = compute_routes_for_pairs(
        topology=topology,
        contact_plan=contact_plan,
        node_pairs=resolved_pairs,
        curr_time=curr_time,
        routing_algorithm=routing_algorithm,
        num_routes=num_routes,
    )
    annotation = annotate_routing_batch(routing)
    security = build_security_batch(annotation, security_models=resolved_models)

    return SimulationResult(
        topology=topology,
        contact_plan_size=len(contact_plan),
        routing=routing,
        annotation=annotation,
        security=security,
    )


def compute_routes_for_pairs(
    *,
    topology: Topology,
    contact_plan: ContactPlan,
    node_pairs: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None,
    curr_time: int = 0,
    routing_algorithm: RoutingAlgorithm | None = None,
    num_routes: int = 3,
) -> RoutingBatchResult:
    resolved_pairs = _resolve_node_pairs(topology, node_pairs)
    algorithm = ensure_routing_algorithm(routing_algorithm, default_num_routes=num_routes)

    return RoutingBatchResult(
        topology=topology,
        contact_plan_size=len(contact_plan),
        node_pair_results=tuple(
            _compute_routes_for_pair(
                source=source,
                destination=destination,
                topology=topology,
                contact_plan=contact_plan,
                curr_time=curr_time,
                algorithm=algorithm,
                num_routes=num_routes,
            )
            for source, destination in resolved_pairs
        ),
    )


def annotate_routing_batch(routing: RoutingBatchResult) -> AnnotationBatchResult:
    return AnnotationBatchResult(
        topology=routing.topology,
        contact_plan_size=routing.contact_plan_size,
        node_pair_results=tuple(
            AnnotatedNodePairResult(
                source=pair_result.source,
                destination=pair_result.destination,
                routes=pair_result.routes,
                annotated_routes=annotate_routes(
                    pair_result.routes,
                    routing.topology,
                    source_node=pair_result.source,
                    destination_node=pair_result.destination,
                ),
            )
            for pair_result in routing.node_pair_results
        ),
    )


def build_security_batch(
    annotation: AnnotationBatchResult,
    *,
    security_models: list[SecurityModelType] | tuple[SecurityModelType, ...] | None = None,
) -> SecurityBatchResult:
    resolved_models = _resolve_security_models(security_models)
    return SecurityBatchResult(
        topology=annotation.topology,
        contact_plan_size=annotation.contact_plan_size,
        node_pair_results=tuple(
            SecurityNodePairResult(
                source=pair_result.source,
                destination=pair_result.destination,
                routes=pair_result.routes,
                annotated_routes=pair_result.annotated_routes,
                security_results=tuple(
                    SecurityModelResult(
                        model=model,
                        protection_plans=build_protection_plans(
                            pair_result.annotated_routes,
                            model=model,
                        ),
                    )
                    for model in resolved_models
                ),
            )
            for pair_result in annotation.node_pair_results
        ),
    )


def _resolve_node_pairs(
    topology: Topology,
    node_pairs: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None,
) -> tuple[tuple[int, int], ...]:
    if node_pairs is None:
        ordered_nodes = tuple(sorted(topology))
        return tuple(
            (source, destination)
            for source in ordered_nodes
            for destination in ordered_nodes
            if source != destination
        )

    resolved_pairs = tuple(node_pairs)
    for source, destination in resolved_pairs:
        if source == destination:
            raise ValueError("source and destination must be different nodes")
        topology.get_network_for_node(source)
        topology.get_network_for_node(destination)
    return resolved_pairs


def _resolve_security_models(
    security_models: list[SecurityModelType] | tuple[SecurityModelType, ...] | None,
) -> tuple[SecurityModelType, ...]:
    if security_models is None:
        return tuple(SecurityModelType)
    return tuple(security_models)


def _compute_routes_for_pair(
    *,
    source: int,
    destination: int,
    topology: Topology,
    contact_plan: ContactPlan,
    curr_time: int,
    algorithm: RoutingAlgorithm,
    num_routes: int,
) -> NodePairRoutesResult:
    topology.get_network_for_node(source)
    topology.get_network_for_node(destination)
    request = RoutingRequest(
        source=source,
        destination=destination,
        curr_time=curr_time,
        contact_plan=contact_plan,
        topology=topology,
        num_routes=num_routes,
    )
    return NodePairRoutesResult(
        source=source,
        destination=destination,
        routes=tuple(algorithm.compute_routes(request)),
    )
