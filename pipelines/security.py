from __future__ import annotations

from dataclasses import dataclass

from modules.network.cgr.models import Route
from modules.network.topology import Topology
from modules.security.annotated_routes import AnnotatedRoute, annotate_route, annotate_routes
from modules.security.planning import ProtectionPlan, build_protection_plan
from modules.security.models import SecurityModelType


@dataclass(slots=True, frozen=True)
class SecurityPipelineResult:
    annotated_routes: tuple[AnnotatedRoute, ...]
    protection_plans: tuple[ProtectionPlan, ...]


def build_security_artifacts(
    routes: tuple[Route, ...] | list[Route],
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
    model: SecurityModelType,
) -> SecurityPipelineResult:
    annotated = annotate_routes(
        routes,
        topology,
        source_node=source_node,
        destination_node=destination_node,
    )
    plans = tuple(build_protection_plan(route, model) for route in annotated)
    return SecurityPipelineResult(
        annotated_routes=annotated,
        protection_plans=plans,
    )


def build_security_plan_for_route(
    route: Route,
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
    model: SecurityModelType,
    route_id: str | None = None,
) -> tuple[AnnotatedRoute, ProtectionPlan]:
    annotated = annotate_route(
        route,
        topology,
        source_node=source_node,
        destination_node=destination_node,
        route_id=route_id,
    )
    return annotated, build_protection_plan(annotated, model)
