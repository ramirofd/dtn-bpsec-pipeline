from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import gurobipy as gp
from gurobipy import GRB

from modules.security.keys import KeyScope
from modules.security.models import SecurityModelType
from pipelines.route_activation import (
    RouteActivationPlanner,
    attach_route_activation_constraints,
)
from pipelines.simulation import SimulationPipeline


DEFAULT_CP_PATH = Path(__file__).resolve().parent / "contact_plan.json"
DEFAULT_TOPOLOGY_PATH = Path(__file__).resolve().parent / "topology.json"
DEFAULT_NUM_ROUTES = 3
DEFAULT_MAX_KEYS = 5
DEFAULT_CURR_TIME = 0


@dataclass(slots=True, frozen=True)
class RouteOptimizationSummary:
    route_id: str
    selected: int
    required_keys: tuple[str, ...]
    pair_summary: str


@dataclass(slots=True, frozen=True)
class KeyOptimizationSummary:
    scope: str
    selected: int


@dataclass(slots=True, frozen=True)
class ModelOptimizationSummary:
    model: SecurityModelType
    pair_count: int
    candidate_routes: int
    unique_keys: int
    max_keys: int
    status: str
    objective: int
    selected_routes: int
    selected_keys: int
    key_constraint_name: str
    key_summaries: tuple[KeyOptimizationSummary, ...]
    route_summaries: tuple[RouteOptimizationSummary, ...]


def format_scope(scope: KeyScope) -> str:
    return f"{scope.key_type.name.lower()}:{scope.source_id}->{scope.target_id}"


def main() -> None:
    print(
        "config | curr_time=%d num_routes=%d max_keys=%d"
        % (DEFAULT_CURR_TIME, DEFAULT_NUM_ROUTES, DEFAULT_MAX_KEYS)
    )

    for security_model in SecurityModelType:
        summary = solve_route_activation_for_model(security_model)
        print_model_summary(summary)
        print()


def solve_route_activation_for_model(
    security_model: SecurityModelType,
    *,
    max_keys: int = DEFAULT_MAX_KEYS,
    curr_time: int = DEFAULT_CURR_TIME,
    num_routes: int = DEFAULT_NUM_ROUTES,
) -> ModelOptimizationSummary:
    result = SimulationPipeline().run(
        cp_path=str(DEFAULT_CP_PATH),
        topology_path=str(DEFAULT_TOPOLOGY_PATH),
        security_models=(security_model,),
        curr_time=curr_time,
        num_routes=num_routes,
    )

    route_summaries: dict[str, str] = {}
    total_candidate_routes = 0

    plans_by_pair = result.security.plans_by_model[security_model]

    for pair in result.annotation.pairs:
        annotated_routes = result.annotation.annotated_routes_by_pair[pair]
        total_candidate_routes += len(annotated_routes)
        for annotated, plan in zip(
            annotated_routes,
            plans_by_pair[pair],
            strict=True,
        ):
            scoped_route_id = f"{pair[0]}->{pair[1]}:{plan.route_id}"
            route_summaries[scoped_route_id] = (
                f"pair={pair[0]}->{pair[1]} "
                f"path={list(annotated.node_path)} "
                f"networks={list(annotated.network_path)}"
            )

    planning = RouteActivationPlanner().build_for_model(result.security, model=security_model)

    model = gp.Model(f"basic_route_activation_{security_model.name.lower()}")
    model.setParam("OutputFlag", 0)

    artifacts = attach_route_activation_constraints(
        model,
        planning,
        route_var_prefix="route",
        key_var_prefix="key",
    )

    key_budget_constraint = model.addConstr(
        gp.quicksum(artifacts.key_vars.values()) <= max_keys,
        name="max_active_keys",
    )
    model.setObjective(gp.quicksum(artifacts.route_vars.values()), GRB.MAXIMIZE)
    model.optimize()

    return ModelOptimizationSummary(
        model=security_model,
        pair_count=len(result.annotation.pairs),
        candidate_routes=total_candidate_routes,
        unique_keys=len(planning.key_scopes),
        max_keys=max_keys,
        status=_status_name(model.Status),
        objective=int(round(model.ObjVal)) if model.SolCount else 0,
        selected_routes=int(round(sum(var.X for var in artifacts.route_vars.values()))) if model.SolCount else 0,
        selected_keys=int(round(sum(var.X for var in artifacts.key_vars.values()))) if model.SolCount else 0,
        key_constraint_name=key_budget_constraint.ConstrName,
        key_summaries=tuple(
            KeyOptimizationSummary(
                scope=format_scope(scope),
                selected=int(round(artifacts.key_vars[scope].X)) if model.SolCount else 0,
            )
            for scope in planning.key_scopes
        ),
        route_summaries=tuple(
            RouteOptimizationSummary(
                route_id=requirement.route_id,
                selected=int(round(artifacts.route_vars[requirement.route_id].X)) if model.SolCount else 0,
                required_keys=tuple(format_scope(scope) for scope in requirement.required_key_scopes),
                pair_summary=route_summaries.get(requirement.route_id, ""),
            )
            for requirement in planning.route_requirements
        ),
    )


def print_model_summary(summary: ModelOptimizationSummary) -> None:
    print(
        "model | name=%s pairs=%d candidate_routes=%d unique_keys=%d max_keys=%d status=%s objective=%d selected_routes=%d selected_keys=%d"
        % (
            summary.model.name.lower(),
            summary.pair_count,
            summary.candidate_routes,
            summary.unique_keys,
            summary.max_keys,
            summary.status,
            summary.objective,
            summary.selected_routes,
            summary.selected_keys,
        )
    )
    print(
        f"constraint | model={summary.model.name.lower()} "
        f"name={summary.key_constraint_name}"
    )

    for key_summary in summary.key_summaries:
        print(
            "key_summary | model=%s selected=%d scope=%s"
            % (
                summary.model.name.lower(),
                key_summary.selected,
                key_summary.scope,
            )
        )

    for route_summary in summary.route_summaries:
        print(
            "route_summary | model=%s id=%s selected=%d required_keys=%s %s"
            % (
                summary.model.name.lower(),
                route_summary.route_id,
                route_summary.selected,
                list(route_summary.required_keys),
                route_summary.pair_summary,
            )
        )


def _status_name(status_code: int) -> str:
    status_names = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.INFEASIBLE: "INFEASIBLE",
        GRB.UNBOUNDED: "UNBOUNDED",
        GRB.INF_OR_UNBD: "INF_OR_UNBD",
        GRB.TIME_LIMIT: "TIME_LIMIT",
    }
    return status_names.get(status_code, str(status_code))


if __name__ == "__main__":
    main()
