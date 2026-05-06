from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from modules.security.keys import KeyScope
from modules.security.artifacts import ProtectionPlan

if TYPE_CHECKING:
    import gurobipy as gp
    from modules.security.models import SecurityModelType
    from pipelines.simulation import SecurityBatchResult


@dataclass(slots=True, frozen=True)
class RouteActivationRequirement:
    route_id: str
    required_key_scopes: tuple[KeyScope, ...]
    operation_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RouteActivationPlanning:
    route_requirements: tuple[RouteActivationRequirement, ...]
    key_scopes: tuple[KeyScope, ...]


@dataclass(slots=True, frozen=True)
class RouteActivationArtifacts:
    planning: RouteActivationPlanning
    model: gp.Model
    route_vars: dict[str, gp.Var]
    key_vars: dict[KeyScope, gp.Var]
    route_constraints: dict[str, gp.Constr]


class RouteActivationPlanner:
    def build_for_model(
        self,
        security_batch: SecurityBatchResult,
        *,
        model: SecurityModelType,
    ) -> RouteActivationPlanning:
        protection_plans: list[ProtectionPlan] = []

        for pair in security_batch.pairs:
            scoped_pair = f"{pair[0]}->{pair[1]}"
            for plan in security_batch.plans_by_model[model][pair]:
                protection_plans.append(
                    ProtectionPlan(
                        route_id=f"{scoped_pair}:{plan.route_id}",
                        model=plan.model,
                        operations=plan.operations,
                        node_requirements=plan.node_requirements,
                        key_requirements=plan.key_requirements,
                        notes=plan.notes,
                    )
                )

        return self.build(protection_plans)

    def build(
        self,
        protection_plans: tuple[ProtectionPlan, ...] | list[ProtectionPlan],
    ) -> RouteActivationPlanning:
        route_requirements: list[RouteActivationRequirement] = []
        all_key_scopes: list[KeyScope] = []
        seen_global_scopes: set[KeyScope] = set()

        for plan in protection_plans:
            route_scopes: list[KeyScope] = []
            seen_route_scopes: set[KeyScope] = set()
            operation_ids: list[str] = []

            for requirement in plan.key_requirements:
                scope = requirement.scope
                if scope not in seen_route_scopes:
                    route_scopes.append(scope)
                    seen_route_scopes.add(scope)
                if scope not in seen_global_scopes:
                    all_key_scopes.append(scope)
                    seen_global_scopes.add(scope)
                if requirement.operation_id not in operation_ids:
                    operation_ids.append(requirement.operation_id)

            route_requirements.append(
                RouteActivationRequirement(
                    route_id=plan.route_id,
                    required_key_scopes=tuple(route_scopes),
                    operation_ids=tuple(operation_ids),
                )
            )

        return RouteActivationPlanning(
            route_requirements=tuple(route_requirements),
            key_scopes=tuple(all_key_scopes),
        )


class RouteActivationModelBuilder:
    def build_model(
        self,
        planning: RouteActivationPlanning,
        *,
        model_name: str = "route_activation",
        route_var_prefix: str = "route_enabled",
        key_var_prefix: str = "key_enabled",
    ) -> RouteActivationArtifacts:
        import gurobipy as gp

        model = gp.Model(model_name)
        return self.attach_constraints(
            model,
            planning,
            route_var_prefix=route_var_prefix,
            key_var_prefix=key_var_prefix,
        )

    def attach_constraints(
        self,
        model: gp.Model,
        planning: RouteActivationPlanning,
        *,
        route_vars: dict[str, gp.Var] | None = None,
        key_vars: dict[KeyScope, gp.Var] | None = None,
        create_missing_vars: bool = True,
        route_var_prefix: str = "route_enabled",
        key_var_prefix: str = "key_enabled",
    ) -> RouteActivationArtifacts:
        import gurobipy as gp
        from gurobipy import GRB

        resolved_route_vars = dict(route_vars or {})
        resolved_key_vars = dict(key_vars or {})
        route_constraints: dict[str, gp.Constr] = {}

        if create_missing_vars:
            for requirement in planning.route_requirements:
                resolved_route_vars.setdefault(
                    requirement.route_id,
                    model.addVar(
                        vtype=GRB.BINARY,
                        name=f"{route_var_prefix}[{_sanitize_name(requirement.route_id)}]",
                    ),
                )
            for scope in planning.key_scopes:
                resolved_key_vars.setdefault(
                    scope,
                    model.addVar(
                        vtype=GRB.BINARY,
                        name=f"{key_var_prefix}[{_scope_name(scope)}]",
                    ),
                )

        _validate_missing_route_vars(planning, resolved_route_vars)
        _validate_missing_key_vars(planning, resolved_key_vars)

        for requirement in planning.route_requirements:
            route_var = resolved_route_vars[requirement.route_id]
            if not requirement.required_key_scopes:
                continue

            lhs = gp.quicksum(resolved_key_vars[scope] for scope in requirement.required_key_scopes)
            rhs = len(requirement.required_key_scopes) * route_var
            route_constraints[requirement.route_id] = model.addConstr(
                lhs >= rhs,
                name=f"route_requires_keys[{_sanitize_name(requirement.route_id)}]",
            )

        model.update()
        return RouteActivationArtifacts(
            planning=planning,
            model=model,
            route_vars=resolved_route_vars,
            key_vars=resolved_key_vars,
            route_constraints=route_constraints,
        )


def build_route_activation_planning(
    protection_plans: tuple[ProtectionPlan, ...] | list[ProtectionPlan],
) -> RouteActivationPlanning:
    return RouteActivationPlanner().build(protection_plans)


def build_route_activation_model(
    planning: RouteActivationPlanning,
    *,
    model_name: str = "route_activation",
    route_var_prefix: str = "route_enabled",
    key_var_prefix: str = "key_enabled",
) -> RouteActivationArtifacts:
    return RouteActivationModelBuilder().build_model(
        planning,
        model_name=model_name,
        route_var_prefix=route_var_prefix,
        key_var_prefix=key_var_prefix,
    )


def attach_route_activation_constraints(
    model: gp.Model,
    planning: RouteActivationPlanning,
    *,
    route_vars: dict[str, gp.Var] | None = None,
    key_vars: dict[KeyScope, gp.Var] | None = None,
    create_missing_vars: bool = True,
    route_var_prefix: str = "route_enabled",
    key_var_prefix: str = "key_enabled",
) -> RouteActivationArtifacts:
    return RouteActivationModelBuilder().attach_constraints(
        model,
        planning,
        route_vars=route_vars,
        key_vars=key_vars,
        create_missing_vars=create_missing_vars,
        route_var_prefix=route_var_prefix,
        key_var_prefix=key_var_prefix,
    )


def _validate_missing_route_vars(
    planning: RouteActivationPlanning,
    route_vars: dict[str, gp.Var],
) -> None:
    missing = [
        requirement.route_id
        for requirement in planning.route_requirements
        if requirement.route_id not in route_vars
    ]
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"missing route variables for: {missing_list}")


def _validate_missing_key_vars(
    planning: RouteActivationPlanning,
    key_vars: dict[KeyScope, gp.Var],
) -> None:
    missing = [scope for scope in planning.key_scopes if scope not in key_vars]
    if missing:
        missing_list = ", ".join(_scope_name(scope) for scope in missing)
        raise ValueError(f"missing key variables for: {missing_list}")


def _sanitize_name(value: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_")
    return sanitized or "item"


def _scope_name(scope: KeyScope) -> str:
    return _sanitize_name(
        f"{scope.key_type.name.lower()}_{scope.source_id}_{scope.target_id}"
    )
