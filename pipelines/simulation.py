from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

from modules.network.py_cgr_lib import Route, cp_load
from modules.network.topology import Topology, topology_load
from modules.security.annotated_routes import AnnotatedRoute, annotate_routes
from modules.security.artifacts import ProtectionPlan
from modules.security.models import SecurityModel, SecurityModelType
from modules.security.planning import build_protection_plan, resolve_security_models
from pipelines.routing import RoutingAlgorithm, RoutingRequest, ensure_routing_algorithm

if TYPE_CHECKING:
    from modules.network.cgr.algorithms import ContactPlan


NodePair = tuple[int, int]


@dataclass(slots=True, frozen=True)
class RoutingBatchResult:
    topology: Topology
    contact_plan_size: int
    pairs: tuple[NodePair, ...]
    routes_by_pair: dict[NodePair, tuple[Route, ...]]


@dataclass(slots=True, frozen=True)
class AnnotationBatchResult:
    topology: Topology
    contact_plan_size: int
    pairs: tuple[NodePair, ...]
    routes_by_pair: dict[NodePair, tuple[Route, ...]]
    annotated_routes_by_pair: dict[NodePair, tuple[AnnotatedRoute, ...]]


@dataclass(slots=True, frozen=True)
class SecurityBatchResult:
    pairs: tuple[NodePair, ...]
    symmetric_keys: bool
    plans_by_model: dict[SecurityModelType, dict[NodePair, tuple[ProtectionPlan, ...]]]


@dataclass(slots=True, frozen=True)
class SimulationResult:
    topology: Topology
    contact_plan_size: int
    routing: RoutingBatchResult
    annotation: AnnotationBatchResult
    security: SecurityBatchResult


class RoutingStage:
    def __init__(
        self,
        routing_algorithm: RoutingAlgorithm | None = None,
        *,
        default_num_routes: int = 3,
    ) -> None:
        self.routing_algorithm = routing_algorithm
        self.default_num_routes = default_num_routes

    def compute(
        self,
        *,
        topology: Topology,
        contact_plan: ContactPlan,
        curr_time: int = 0,
        num_routes: int | None = None,
    ) -> RoutingBatchResult:
        resolved_default_num_routes = (
            self.default_num_routes if num_routes is None else num_routes
        )
        algorithm = ensure_routing_algorithm(
            self.routing_algorithm,
            default_num_routes=resolved_default_num_routes,
        )
        pairs = _enumerate_node_pairs(topology)
        routes_by_pair = {
            pair: tuple(
                algorithm.compute_routes(
                    RoutingRequest(
                        source=pair[0],
                        destination=pair[1],
                        curr_time=curr_time,
                        contact_plan=contact_plan,
                        topology=topology,
                        num_routes=num_routes,
                    )
                )
            )
            for pair in pairs
        }

        return RoutingBatchResult(
            topology=topology,
            contact_plan_size=len(contact_plan),
            pairs=pairs,
            routes_by_pair=routes_by_pair,
        )


class RouteAnnotationStage:
    def annotate(self, routing: RoutingBatchResult) -> AnnotationBatchResult:
        annotated_routes_by_pair = {
            pair: annotate_routes(
                routing.routes_by_pair[pair],
                routing.topology,
                source_node=pair[0],
                destination_node=pair[1],
            )
            for pair in routing.pairs
        }
        return AnnotationBatchResult(
            topology=routing.topology,
            contact_plan_size=routing.contact_plan_size,
            pairs=routing.pairs,
            routes_by_pair=routing.routes_by_pair,
            annotated_routes_by_pair=annotated_routes_by_pair,
        )


class SecurityPlanningStage:
    def build_batch(
        self,
        annotation: AnnotationBatchResult,
        *,
        security_models: Sequence[SecurityModel | SecurityModelType] | None = None,
        symmetric_keys: bool = False,
    ) -> SecurityBatchResult:
        resolved_models = resolve_security_models(security_models)
        plans_by_model = {
            model.type: {
                pair: tuple(
                    build_protection_plan(model, route)
                    for route in annotation.annotated_routes_by_pair[pair]
                )
                for pair in annotation.pairs
            }
            for model in resolved_models
        }
        return SecurityBatchResult(
            pairs=annotation.pairs,
            symmetric_keys=symmetric_keys,
            plans_by_model=plans_by_model,
        )


class SimulationPipeline:
    def __init__(
        self,
        *,
        routing_stage: RoutingStage | None = None,
        annotation_stage: RouteAnnotationStage | None = None,
        security_stage: SecurityPlanningStage | None = None,
    ) -> None:
        self.routing_stage = routing_stage or RoutingStage()
        self.annotation_stage = annotation_stage or RouteAnnotationStage()
        self.security_stage = security_stage or SecurityPlanningStage()

    def run(
        self,
        *,
        cp_path: str,
        topology_path: str,
        security_models: Sequence[SecurityModel | SecurityModelType] | None = None,
        symmetric_keys: bool = False,
        curr_time: int = 0,
        routing_algorithm: RoutingAlgorithm | None = None,
        num_routes: int | None = None,
    ) -> SimulationResult:
        return self.run_loaded(
            topology=topology_load(topology_path),
            contact_plan=cp_load(cp_path),
            security_models=security_models,
            symmetric_keys=symmetric_keys,
            curr_time=curr_time,
            routing_algorithm=routing_algorithm,
            num_routes=num_routes,
        )

    def run_loaded(
        self,
        *,
        topology: Topology,
        contact_plan: ContactPlan,
        security_models: Sequence[SecurityModel | SecurityModelType] | None = None,
        symmetric_keys: bool = False,
        curr_time: int = 0,
        routing_algorithm: RoutingAlgorithm | None = None,
        num_routes: int | None = None,
    ) -> SimulationResult:
        routing_stage = (
            RoutingStage(
                routing_algorithm,
                default_num_routes=self.routing_stage.default_num_routes,
            )
            if routing_algorithm is not None
            else self.routing_stage
        )

        routing = routing_stage.compute(
            topology=topology,
            contact_plan=contact_plan,
            curr_time=curr_time,
            num_routes=num_routes,
        )
        annotation = self.annotation_stage.annotate(routing)
        security = self.security_stage.build_batch(
            annotation,
            security_models=security_models,
            symmetric_keys=symmetric_keys,
        )

        return SimulationResult(
            topology=topology,
            contact_plan_size=len(contact_plan),
            routing=routing,
            annotation=annotation,
            security=security,
        )


def _enumerate_node_pairs(topology: Topology) -> tuple[NodePair, ...]:
    ordered_nodes = tuple(sorted(topology))
    return tuple(
        (source, destination)
        for source in ordered_nodes
        for destination in ordered_nodes
        if source != destination
    )
