"""Composable domain pipeline; stages communicate only through catalogs."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from modules.domain import PlanRef, RouteCandidate, RouteRef
from modules.security.annotated_routes import annotate_route
from modules.security.planning import ConfiguredSecurityPolicy, DEFAULT_SECURITY_MODELS
from pipelines.catalogs import AnnotationCatalog, ProtectionCatalog, RouteCatalog
from pipelines.contracts import ProtectionPlanner, RouteAnnotator, RoutePlanner
from pipelines.routing import CGRYenRouting, RoutingAlgorithm, RoutingBatchRequest, RoutingRequest


@dataclass(frozen=True, slots=True)
class SimulationResult:
    routes: RouteCatalog
    annotations: AnnotationCatalog
    protection: ProtectionCatalog

    def __post_init__(self) -> None:
        if self.annotations.routes is not self.routes or self.protection.annotations is not self.annotations:
            raise ValueError("simulation catalogs must preserve their stage lineage")


class RoutingStage:
    def __init__(self, algorithm: RoutingAlgorithm | None = None) -> None:
        self.algorithm = CGRYenRouting() if algorithm is None else algorithm

    def compute(self, request: RoutingBatchRequest) -> RouteCatalog:
        scenario = request.scenario
        candidates: dict[RouteRef, RouteCandidate] = {}
        for pair in scenario.pairs:
            routes = self.algorithm.compute_routes(RoutingRequest(
                source=pair[0], destination=pair[1], curr_time=request.curr_time,
                contacts=scenario.contacts, topology=scenario.topology, num_routes=request.num_routes,
            ))
            if request.num_routes is not None:
                routes = routes[:request.num_routes]
            for index, route in enumerate(routes, start=1):
                ref = RouteRef(pair, index)
                candidates[ref] = RouteCandidate.from_route(ref, route)
        return RouteCatalog(scenario, candidates)


class RouteAnnotationStage:
    def annotate(self, routes: RouteCatalog) -> AnnotationCatalog:
        return AnnotationCatalog(routes, {
            ref: annotate_route(candidate, routes.scenario.topology)
            for ref, candidate in routes.by_id.items()
        })


class SecurityPlanningStage:
    def __init__(self, policies: Sequence[ConfiguredSecurityPolicy] | None = None) -> None:
        self.policies = tuple(
            ConfiguredSecurityPolicy(model.type.name, model) for model in DEFAULT_SECURITY_MODELS
        ) if policies is None else tuple(policies)
        ids = [policy.policy_id for policy in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("configured policy identifiers must be unique")

    def build(self, annotations: AnnotationCatalog) -> ProtectionCatalog:
        return ProtectionCatalog(
            annotations,
            {policy.policy_id: policy.model.type for policy in self.policies},
            {PlanRef(ref, policy.policy_id): policy.model.build_plan(annotation, policy_id=policy.policy_id)
             for ref, annotation in annotations.by_route.items() for policy in self.policies},
        )


class SimulationPipeline:
    def __init__(self, *, routing: RoutePlanner | None = None,
                 annotation: RouteAnnotator | None = None,
                 security: ProtectionPlanner | None = None) -> None:
        self.routing = RoutingStage() if routing is None else routing
        self.annotation = RouteAnnotationStage() if annotation is None else annotation
        self.security = SecurityPlanningStage() if security is None else security

    def run(self, request: RoutingBatchRequest) -> SimulationResult:
        routes = self.routing.compute(request)
        if routes.scenario is not request.scenario:
            raise ValueError("routing stage must preserve the requested scenario")
        annotations = self.annotation.annotate(routes)
        protection = self.security.build(annotations)
        return SimulationResult(routes, annotations, protection)
