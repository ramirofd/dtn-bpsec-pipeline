from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from modules.security.keys import KeyScope, normalize_key_scope
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


@dataclass(slots=True, frozen=True)
class RouteActivationContactSelection:
    hop_index: int
    from_node: int
    to_node: int
    start: int
    end: int
    rate: int
    owlt: int
    from_network: int
    to_network: int
    crosses_network_boundary: bool


@dataclass(slots=True, frozen=True)
class RouteActivationOperationSelection:
    operation_id: str
    target_hop_indexes: tuple[int, ...]
    raw_key_scope: KeyScope
    selected_key_scope: KeyScope
    source_node: int
    acceptor_node: int
    source_network: int
    acceptor_network: int
    rationale: str
    covered_contacts: tuple[RouteActivationContactSelection, ...]


@dataclass(slots=True, frozen=True)
class RouteActivationRouteSelection:
    route_id: str
    pair: tuple[int, int]
    pair_id: str
    local_route_id: str
    node_path: tuple[int, ...]
    network_path: tuple[int, ...]
    boundary_crossings: tuple[BoundaryCrossing, ...]
    gateway_nodes: frozenset[int]
    required_key_scopes: tuple[KeyScope, ...]
    contacts: tuple[RouteActivationContactSelection, ...]
    operations: tuple[RouteActivationOperationSelection, ...]
    notes: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class RouteActivationKeySelection:
    scope: KeyScope
    route_ids: tuple[str, ...]
    pair_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RouteActivationSelection:
    model: SecurityModelType
    symmetric_keys: bool
    selected_pairs: tuple[tuple[int, int], ...]
    selected_route_ids: tuple[str, ...]
    selected_key_scopes: tuple[KeyScope, ...]
    routes: tuple[RouteActivationRouteSelection, ...]
    keys: tuple[RouteActivationKeySelection, ...]


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

        return self.build(
            protection_plans,
            symmetric_keys=security_batch.symmetric_keys,
        )

    def build(
        self,
        protection_plans: tuple[ProtectionPlan, ...] | list[ProtectionPlan],
        *,
        symmetric_keys: bool = False,
    ) -> RouteActivationPlanning:
        route_requirements: list[RouteActivationRequirement] = []
        all_key_scopes: list[KeyScope] = []
        seen_global_scopes: set[KeyScope] = set()

        for plan in protection_plans:
            route_scopes: list[KeyScope] = []
            seen_route_scopes: set[KeyScope] = set()
            operation_ids: list[str] = []

            for requirement in plan.key_requirements:
                scope = normalize_key_scope(
                    requirement.scope,
                    symmetric=symmetric_keys,
                )
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


def trace_route_activation_solution(
    result: SimulationResult,
    artifacts: RouteActivationArtifacts,
    *,
    security_model: SecurityModelType,
    threshold: float = 0.5,
) -> RouteActivationSelection:
    route_requirements_by_id = {
        requirement.route_id: requirement
        for requirement in artifacts.planning.route_requirements
    }
    selected_route_ids = tuple(
        requirement.route_id
        for requirement in artifacts.planning.route_requirements
        if _variable_value(artifacts.route_vars[requirement.route_id]) > threshold
    )
    selected_key_scopes = tuple(
        scope
        for scope in artifacts.planning.key_scopes
        if _variable_value(artifacts.key_vars[scope]) > threshold
    )

    route_lookup = _build_route_selection_lookup(
        result,
        security_model=security_model,
    )
    selected_routes: list[RouteActivationRouteSelection] = []

    for route_id in selected_route_ids:
        pair, local_route_id = _parse_scoped_route_id(route_id)
        try:
            raw_route, annotated_route, plan = route_lookup[(pair, local_route_id)]
        except KeyError as exc:
            raise ValueError(
                f"selected route {route_id} is not present in the simulation result"
            ) from exc

        raw_contacts = tuple(raw_route.get_hops())
        if len(raw_contacts) != len(annotated_route.hops):
            raise ValueError(
                "selected route context is inconsistent: raw and annotated hop counts differ "
                f"for {route_id}"
            )

        contacts = tuple(
            RouteActivationContactSelection(
                hop_index=annotated_hop.hop_index,
                from_node=contact.frm,
                to_node=contact.to,
                start=contact.start,
                end=contact.end,
                rate=contact.rate,
                owlt=contact.owlt,
                from_network=annotated_hop.from_network,
                to_network=annotated_hop.to_network,
                crosses_network_boundary=annotated_hop.crosses_network_boundary,
            )
            for contact, annotated_hop in zip(raw_contacts, annotated_route.hops)
        )
        contacts_by_index = {
            contact.hop_index: contact
            for contact in contacts
        }

        operations = tuple(
            RouteActivationOperationSelection(
                operation_id=operation.operation_id,
                target_hop_indexes=operation.target_hop_indexes,
                raw_key_scope=KeyScope(
                    key_type=operation.required_key_type,
                    source_id=operation.key_source_id,
                    target_id=operation.key_target_id,
                ),
                selected_key_scope=normalize_key_scope(
                    KeyScope(
                        key_type=operation.required_key_type,
                        source_id=operation.key_source_id,
                        target_id=operation.key_target_id,
                    ),
                    symmetric=result.security.symmetric_keys,
                ),
                source_node=operation.source_node,
                acceptor_node=operation.acceptor_node,
                source_network=operation.source_network,
                acceptor_network=operation.acceptor_network,
                rationale=operation.rationale,
                covered_contacts=tuple(
                    contacts_by_index[hop_index]
                    for hop_index in operation.target_hop_indexes
                ),
            )
            for operation in plan.operations
        )

        selected_routes.append(
            RouteActivationRouteSelection(
                route_id=route_id,
                pair=pair,
                pair_id=_format_pair(pair),
                local_route_id=local_route_id,
                node_path=annotated_route.node_path,
                network_path=annotated_route.network_path,
                boundary_crossings=annotated_route.boundary_crossings,
                gateway_nodes=annotated_route.gateway_nodes,
                required_key_scopes=route_requirements_by_id[route_id].required_key_scopes,
                contacts=contacts,
                operations=operations,
                notes=plan.notes,
            )
        )

    selected_keys = tuple(
        RouteActivationKeySelection(
            scope=scope,
            route_ids=tuple(
                route.route_id
                for route in selected_routes
                if scope in route.required_key_scopes
            ),
            pair_ids=_ordered_unique(
                route.pair_id
                for route in selected_routes
                if scope in route.required_key_scopes
            ),
            operation_ids=_ordered_unique(
                operation.operation_id
                for route in selected_routes
                for operation in route.operations
                if operation.selected_key_scope == scope
            ),
        )
        for scope in selected_key_scopes
    )

    return RouteActivationSelection(
        model=security_model,
        symmetric_keys=result.security.symmetric_keys,
        selected_pairs=_ordered_unique(
            route.pair
            for route in selected_routes
        ),
        selected_route_ids=selected_route_ids,
        selected_key_scopes=selected_key_scopes,
        routes=tuple(selected_routes),
        keys=selected_keys,
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


def _build_route_selection_lookup(
    result: SimulationResult,
    *,
    security_model: SecurityModelType,
) -> dict[tuple[tuple[int, int], str], tuple[Route, AnnotatedRoute, ProtectionPlan]]:
    try:
        plans_by_pair = result.security.plans_by_model[security_model]
    except KeyError as exc:
        raise ValueError(f"security model {security_model} is not present in the simulation result") from exc

    lookup: dict[tuple[tuple[int, int], str], tuple[Route, AnnotatedRoute, ProtectionPlan]] = {}
    for pair in result.annotation.pairs:
        try:
            raw_routes = result.routing.routes_by_pair[pair]
            annotated_routes = result.annotation.annotated_routes_by_pair[pair]
            plans = plans_by_pair[pair]
        except KeyError as exc:
            raise ValueError(
                f"pair {_format_pair(pair)} is missing route, annotation, or plan context"
            ) from exc

        if not (len(raw_routes) == len(annotated_routes) == len(plans)):
            raise ValueError(
                "route context is inconsistent for pair "
                f"{_format_pair(pair)}: got {len(raw_routes)} raw routes, "
                f"{len(annotated_routes)} annotated routes, and {len(plans)} plans"
            )

        for raw_route, annotated_route, plan in zip(raw_routes, annotated_routes, plans):
            if plan.route_id != annotated_route.route_id:
                raise ValueError(
                    "route context is inconsistent for pair "
                    f"{_format_pair(pair)}: plan {plan.route_id} does not match "
                    f"annotated route {annotated_route.route_id}"
                )

            lookup_key = (pair, annotated_route.route_id)
            if lookup_key in lookup:
                raise ValueError(
                    f"duplicated route context detected for {_format_pair(pair)}:{annotated_route.route_id}"
                )
            lookup[lookup_key] = (raw_route, annotated_route, plan)

    return lookup


def _parse_scoped_route_id(route_id: str) -> tuple[tuple[int, int], str]:
    try:
        pair_id, local_route_id = route_id.split(":", 1)
    except ValueError as exc:
        raise ValueError(f"route id {route_id!r} does not contain a scoped pair prefix") from exc

    try:
        source_text, destination_text = pair_id.split("->", 1)
        pair = (int(source_text), int(destination_text))
    except ValueError as exc:
        raise ValueError(f"route id {route_id!r} does not encode a valid source-destination pair") from exc

    return pair, local_route_id


def _variable_value(var: object) -> float:
    try:
        value = getattr(var, "X")
    except AttributeError:
        value = var
    return float(value)


def _ordered_unique(values: tuple[object, ...] | list[object] | object) -> tuple[object, ...]:
    seen: set[object] = set()
    ordered: list[object] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _format_pair(pair: tuple[int, int]) -> str:
    return f"{pair[0]}->{pair[1]}"
