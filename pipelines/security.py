from __future__ import annotations

from dataclasses import dataclass

from modules.network.cgr.models import Route
from modules.network.topology import Topology
from modules.security.annotated_routes import AnnotatedRoute, annotate_routes
from modules.security.planning import ProtectionPlan, build_protection_plan
from modules.security.models import SecurityModelType


@dataclass(slots=True, frozen=True)
class SecurityPipelineResult:
    annotated_routes: tuple[AnnotatedRoute, ...]
    protection_plans: tuple[ProtectionPlan, ...]


class SecurityPipeline:
    def build_protection_plans(
        self,
        annotated_routes: tuple[AnnotatedRoute, ...] | list[AnnotatedRoute],
        *,
        model: SecurityModelType,
    ) -> tuple[ProtectionPlan, ...]:
        return tuple(build_protection_plan(route, model) for route in annotated_routes)

    def build_artifacts(
        self,
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
        plans = self.build_protection_plans(annotated, model=model)
        return SecurityPipelineResult(
            annotated_routes=annotated,
            protection_plans=plans,
        )


def build_protection_plans(
    annotated_routes: tuple[AnnotatedRoute, ...] | list[AnnotatedRoute],
    *,
    model: SecurityModelType,
) -> tuple[ProtectionPlan, ...]:
    return SecurityPipeline().build_protection_plans(annotated_routes, model=model)


def build_security_artifacts(
    routes: tuple[Route, ...] | list[Route],
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
    model: SecurityModelType,
) -> SecurityPipelineResult:
    return SecurityPipeline().build_artifacts(
        routes,
        topology,
        source_node=source_node,
        destination_node=destination_node,
        model=model,
    )
