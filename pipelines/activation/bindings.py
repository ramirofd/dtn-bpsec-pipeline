"""Compose objective-free Gurobi constraints over a pure activation problem.

The caller creates and disposes the solver model. Bindings are live handles;
only the incidence problem and extracted solution are portable artifacts.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from types import MappingProxyType
from typing import TYPE_CHECKING

from modules.domain import RouteRef
from modules.security.keys import KeyScope
from pipelines.activation.planning import ActivationProblem

if TYPE_CHECKING:
    import gurobipy as gp


@dataclass(frozen=True, slots=True)
class GlobalActivationBindings:
    model: gp.Model
    problem: ActivationProblem
    route_vars: Mapping[RouteRef, gp.Var]
    key_vars: Mapping[KeyScope, gp.Var]
    route_constraints: Mapping[RouteRef, gp.Constr]
    key_usage_constraints: Mapping[KeyScope, gp.Constr]


@dataclass(frozen=True, slots=True)
class NodeDeliveryBindings:
    activation: GlobalActivationBindings
    node_key_vars: Mapping[tuple[int, KeyScope], gp.Var]
    node_key_loads: Mapping[int, gp.LinExpr]
    route_node_key_constraints: Mapping[tuple[RouteRef, int, KeyScope], gp.Constr]
    node_key_usage_constraints: Mapping[tuple[int, KeyScope], gp.Constr]
    key_usage_constraints: Mapping[KeyScope, gp.Constr]


def attach_global_activation(
    model: gp.Model,
    problem: ActivationProblem,
    *,
    route_vars: Mapping[RouteRef, gp.Var] | None = None,
    key_vars: Mapping[KeyScope, gp.Var] | None = None,
    create_missing_vars: bool = True,
    exact_keys: bool = False,
) -> GlobalActivationBindings:
    """Attach route implies all required keys, optionally exact key unions.

    Supplied variables are reused, never shadowed or duplicated. Their mapping
    keys must belong to the problem and they must be binary in this model.
    Validate all supplied inputs before adding variables or constraints.
    """
    import gurobipy as gp
    from gurobipy import GRB

    resolved_routes = dict(route_vars or {})
    resolved_keys = dict(key_vars or {})
    if set(resolved_routes) - set(problem.requirements):
        raise ValueError("route variable mapping contains unknown route references")
    if set(resolved_keys) - set(problem.key_scopes):
        raise ValueError("key variable mapping contains unknown key scopes")
    missing_routes = [ref for ref in problem.requirements if ref not in resolved_routes]
    missing_keys = [scope for scope in problem.key_scopes if scope not in resolved_keys]
    if not create_missing_vars:
        if missing_routes:
            raise ValueError(f"missing route variables for: {missing_routes}")
        if missing_keys:
            raise ValueError(f"missing key variables for: {missing_keys}")
    supplied = [*resolved_routes.values(), *resolved_keys.values()]
    if len({id(var) for var in supplied}) != len(supplied):
        raise ValueError("each route and key requires a distinct solver variable")
    if supplied:
        model.update()
        for var in supplied:
            try:
                # getAttr checks ownership as well as the variable type.
                vtype = model.getAttr(GRB.Attr.VType, [var])[0]
            except (gp.GurobiError, AttributeError, TypeError) as exc:
                raise ValueError("supplied variables must belong to the target model") from exc
            if vtype != GRB.BINARY:
                raise ValueError("activation variables must be binary")
    for ref in problem.requirements:
        if ref not in resolved_routes:
            resolved_routes[ref] = model.addVar(vtype=GRB.BINARY, name=f"route_enabled[{_sanitize_name(str(ref))}]")
    for scope in problem.key_scopes:
        if scope not in resolved_keys:
            resolved_keys[scope] = model.addVar(vtype=GRB.BINARY, name=f"key_enabled[{_scope_name(scope)}]")
    route_constraints = {}
    for index, (ref, requirement) in enumerate(problem.requirements.items()):
        if requirement.required_key_scopes:
            route_constraints[ref] = model.addConstr(
                gp.quicksum(resolved_keys[scope] for scope in requirement.required_key_scopes)
                >= len(requirement.required_key_scopes) * resolved_routes[ref],
                name=f"route_requires_keys[{_sanitize_name(str(ref))}]",
            )
    key_usage_constraints = _attach_exact_keys(model, problem, resolved_routes, resolved_keys) if exact_keys else {}
    model.update()
    return GlobalActivationBindings(
        model, problem, MappingProxyType(resolved_routes), MappingProxyType(resolved_keys),
        MappingProxyType(route_constraints), MappingProxyType(key_usage_constraints),
    )


def _attach_exact_keys(model, problem, route_vars, key_vars):
    import gurobipy as gp

    return {
        scope: model.addConstr(
            key_vars[scope] <= gp.quicksum(route_vars[ref] for ref in refs),
            name=f"key_has_route[{_scope_name(scope)}]",
        )
        for index, (scope, refs) in enumerate(problem.routes_by_key.items())
    }


def attach_node_deliveries(activation: GlobalActivationBindings) -> NodeDeliveryBindings:
    """Compose exact deliveries and load expressions using existing activation.

    Global keys and node deliveries are precisely the union needed by selected
    routes. Nonparticipating topology nodes receive an explicit zero load.
    """
    import gurobipy as gp
    from gurobipy import GRB

    model, problem = activation.model, activation.problem
    node_key_vars = {
        node_key: model.addVar(vtype=GRB.BINARY, name=f"node_key[{node_key[0]},{_scope_name(node_key[1])}]")
        for index, node_key in enumerate(problem.routes_by_node_key)
    }
    vars_by_node = {node: [] for node in problem.node_ids}
    route_constraints = {}
    usage_constraints = {}
    for index, ((node, scope), refs) in enumerate(problem.routes_by_node_key.items()):
        var = node_key_vars[node, scope]
        vars_by_node[node].append(var)
        for route_index, ref in enumerate(refs):
            route_constraints[ref, node, scope] = model.addConstr(
                activation.route_vars[ref] <= var,
                name=f"route_requires_node_key[{index},{route_index}]",
            )
        usage_constraints[node, scope] = model.addConstr(
            var <= gp.quicksum(activation.route_vars[ref] for ref in refs),
            name=f"node_key_has_route[{index}]",
        )
    key_usage = activation.key_usage_constraints or _attach_exact_keys(
        model, problem, activation.route_vars, activation.key_vars,
    )
    model.update()
    return NodeDeliveryBindings(
        activation, MappingProxyType(node_key_vars),
        MappingProxyType({node: gp.quicksum(variables) for node, variables in vars_by_node.items()}),
        MappingProxyType(route_constraints), MappingProxyType(usage_constraints), MappingProxyType(dict(key_usage)),
    )


def _sanitize_name(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_") or "item"


def _scope_name(scope: KeyScope) -> str:
    return _sanitize_name(f"{scope.key_type.name.lower()}_{scope.source_id}_{scope.target_id}")
