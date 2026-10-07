"""Build presentation data from explicit identities and detached solution values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from modules.domain import PlanRef
from modules.security.annotated_routes import BoundaryCrossing
from modules.security.keys import KeyScope
from modules.security.models import SecurityModelType
from pipelines.activation.planning import ActivationProblem
from pipelines.activation.solution import ActivationSolution


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
    required_keys_by_node: Mapping[int, tuple[KeyScope, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_keys_by_node", MappingProxyType({
            node: tuple(scopes) for node, scopes in self.required_keys_by_node.items()
        }))


@dataclass(slots=True, frozen=True)
class RouteActivationKeySelection:
    scope: KeyScope
    route_ids: tuple[str, ...]
    pair_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    node_ids: tuple[int, ...] = ()


@dataclass(slots=True, frozen=True)
class RouteActivationSelection:
    model: SecurityModelType
    symmetric_keys: bool
    selected_pairs: tuple[tuple[int, int], ...]
    selected_route_ids: tuple[str, ...]
    selected_key_scopes: tuple[KeyScope, ...]
    routes: tuple[RouteActivationRouteSelection, ...]
    keys: tuple[RouteActivationKeySelection, ...]
    keys_by_node: Mapping[int, tuple[KeyScope, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys_by_node", MappingProxyType({
            node: tuple(scopes) for node, scopes in self.keys_by_node.items()
        }))

    @property
    def key_counts_by_node(self) -> dict[int, int]:
        return {node: len(scopes) for node, scopes in self.keys_by_node.items()}

    @property
    def max_keys_per_node(self) -> int:
        return max(self.key_counts_by_node.values(), default=0)


def build_trace(problem: ActivationProblem, solution: ActivationSolution) -> RouteActivationSelection:
    """Explain a solution without a solver or any positional joins.

    Human-readable IDs are labels only: all catalog lookup uses structured
    route, plan and operation references, including reordered catalogs.
    """
    if set(solution.route_values) != set(problem.requirements):
        raise ValueError("solution route references differ from the activation problem")
    if set(solution.key_values) != set(problem.key_scopes):
        raise ValueError("solution key scopes differ from the activation problem")
    selected_refs = tuple(ref for ref in problem.requirements
                          if solution.route_values[ref] > solution.threshold)
    selected_scopes = tuple(scope for scope in problem.key_scopes
                            if solution.key_values[scope] > solution.threshold)
    scope_set = set(selected_scopes)
    selected_routes = []
    for ref in selected_refs:
        requirement = problem.requirements[ref]
        if not set(requirement.required_key_scopes) <= scope_set:
            raise ValueError(f"selected route {ref} requires unselected keys")
        raw_route = problem.catalog.annotations.routes.by_id[ref]
        annotated = problem.catalog.annotations.by_route[ref]
        plan = problem.catalog.by_plan[PlanRef(ref, problem.policy_id)]
        contacts = []
        for hop in annotated.hops:
            contact = raw_route.contacts[hop.hop_index]
            contacts.append(RouteActivationContactSelection(
                hop_index=hop.hop_index,
                from_node=contact.frm, to_node=contact.to,
                start=contact.start, end=contact.end, rate=contact.rate, owlt=contact.owlt,
                from_network=hop.from_network, to_network=hop.to_network,
                crosses_network_boundary=hop.crosses_network_boundary,
            ))
        by_hop = {contact.hop_index: contact for contact in contacts}
        operations = tuple(RouteActivationOperationSelection(
            operation_id=str(operation.ref),
            target_hop_indexes=operation.target_hop_indexes,
            raw_key_scope=KeyScope(
                operation.required_key_type, operation.key_source_id, operation.key_target_id,
            ),
            selected_key_scope=requirement.operation_scopes[operation.ref],
            source_node=operation.source_node, acceptor_node=operation.acceptor_node,
            source_network=operation.source_network, acceptor_network=operation.acceptor_network,
            rationale=operation.rationale,
            covered_contacts=tuple(by_hop[index] for index in operation.target_hop_indexes),
        ) for operation in plan.operations)
        selected_routes.append(RouteActivationRouteSelection(
            route_id=str(ref), pair=ref.pair, pair_id=f"{ref.pair[0]}->{ref.pair[1]}",
            local_route_id=f"route-{ref.candidate_id}",
            node_path=annotated.node_path, network_path=annotated.network_path,
            boundary_crossings=annotated.boundary_crossings, gateway_nodes=annotated.gateway_nodes,
            required_key_scopes=requirement.required_key_scopes, contacts=tuple(contacts),
            operations=operations, notes=plan.notes, required_keys_by_node=requirement.required_keys_by_node,
        ))
    node_scopes = {node: {} for node in problem.node_ids}
    for route in selected_routes:
        for node, scopes in route.required_keys_by_node.items():
            node_scopes[node].update(dict.fromkeys(scopes))
    keys_by_node = MappingProxyType({node: tuple(scopes) for node, scopes in node_scopes.items()})
    keys = tuple(RouteActivationKeySelection(
        scope=scope,
        route_ids=tuple(route.route_id for route in selected_routes if scope in route.required_key_scopes),
        pair_ids=tuple(dict.fromkeys(route.pair_id for route in selected_routes if scope in route.required_key_scopes)),
        operation_ids=tuple(dict.fromkeys(
            operation.operation_id for route in selected_routes for operation in route.operations
            if operation.selected_key_scope == scope
        )),
        node_ids=tuple(node for node, scopes in keys_by_node.items() if scope in scopes),
    ) for scope in selected_scopes)
    return RouteActivationSelection(
        model=problem.security_model, symmetric_keys=problem.symmetric_keys,
        selected_pairs=tuple(dict.fromkeys(route.pair for route in selected_routes)),
        selected_route_ids=tuple(str(ref) for ref in selected_refs), selected_key_scopes=selected_scopes,
        routes=tuple(selected_routes), keys=keys, keys_by_node=keys_by_node,
    )
