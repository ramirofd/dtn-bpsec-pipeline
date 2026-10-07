"""Solver-independent key incidences derived from a protection catalog."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from modules.domain import OperationRef, PlanRef, RouteRef
from modules.security.keys import KeyScope, normalize_key_scope
from modules.security.models import SecurityModelType
from pipelines.catalogs import ProtectionCatalog


@dataclass(frozen=True, slots=True)
class ActivationRequirement:
    ref: RouteRef
    required_key_scopes: tuple[KeyScope, ...]
    operation_scopes: Mapping[OperationRef, KeyScope]
    required_keys_by_node: Mapping[int, tuple[KeyScope, ...]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_key_scopes", tuple(self.required_key_scopes))
        object.__setattr__(self, "operation_scopes", MappingProxyType(dict(self.operation_scopes)))
        object.__setattr__(self, "required_keys_by_node", MappingProxyType({
            node: tuple(scopes) for node, scopes in self.required_keys_by_node.items()
        }))

    @property
    def operation_refs(self) -> tuple[OperationRef, ...]:
        return tuple(self.operation_scopes)


@dataclass(frozen=True, slots=True)
class ActivationProblem:
    """Validated immutable incidences, with provenance in one protection catalog.

    Candidate order comes from the route catalog, independently of annotation
    or plan insertion order. Empty pairs remain in the coverage denominator.
    """

    catalog: ProtectionCatalog
    policy_id: str
    symmetric_keys: bool
    requirements: Mapping[RouteRef, ActivationRequirement]
    key_scopes: tuple[KeyScope, ...]
    routes_by_key: Mapping[KeyScope, tuple[RouteRef, ...]] = field(init=False)
    routes_by_node_key: Mapping[tuple[int, KeyScope], tuple[RouteRef, ...]] = field(init=False)

    def __post_init__(self) -> None:
        if self.policy_id not in self.catalog.policies:
            raise ValueError(f"unknown protection policy: {self.policy_id}")
        requirements = dict(self.requirements)
        routes = self.catalog.annotations.routes.by_id
        if set(requirements) != set(routes):
            raise ValueError("activation requirements must cover exactly the route catalog")
        scopes = tuple(self.key_scopes)
        if len(set(scopes)) != len(scopes):
            raise ValueError("duplicate key scopes in activation catalog")
        routes_by_key = {scope: [] for scope in scopes}
        routes_by_node_key = {}
        nodes = set(self.node_ids)
        for ref, requirement in requirements.items():
            if ref != requirement.ref:
                raise ValueError("activation requirement identity differs from its catalog key")
            plan_ref = PlanRef(ref, self.policy_id)
            if plan_ref not in self.catalog.by_plan:
                raise ValueError(f"missing protection plan for {ref}")
            if len(set(requirement.required_key_scopes)) != len(requirement.required_key_scopes):
                raise ValueError(f"duplicate required key scopes for {ref}")
            delivered = {scope for node_scopes in requirement.required_keys_by_node.values()
                         for scope in node_scopes}
            if delivered != set(requirement.required_key_scopes):
                raise ValueError(f"incomplete or inconsistent node key requirements for {ref}")
            if set(requirement.operation_scopes.values()) != set(requirement.required_key_scopes):
                raise ValueError(f"inconsistent operation key requirements for {ref}")
            plan = self.catalog.by_plan[plan_ref]
            operations = {operation.ref for operation in plan.operations}
            if set(requirement.operation_scopes) != operations:
                raise ValueError(f"operation references do not match the protection plan for {ref}")
            expected_operation_scopes = {
                operation.ref: normalize_key_scope(KeyScope(
                    operation.required_key_type, operation.key_source_id, operation.key_target_id,
                ), symmetric=self.symmetric_keys)
                for operation in plan.operations
            }
            if requirement.operation_scopes != expected_operation_scopes:
                raise ValueError(f"operation key scopes do not match the protection plan for {ref}")
            if {key.operation_ref for key in plan.key_requirements} != operations:
                raise ValueError(f"key requirements must cover every protection operation for {ref}")
            for key in plan.key_requirements:
                if normalize_key_scope(key.scope, symmetric=self.symmetric_keys) != expected_operation_scopes[key.operation_ref]:
                    raise ValueError(f"key requirement scope differs from its operation for {ref}")
            for node_requirement in plan.node_requirements:
                node_scope = normalize_key_scope(KeyScope(
                    node_requirement.key_type, node_requirement.key_source_id, node_requirement.key_target_id,
                ), symmetric=self.symmetric_keys)
                if node_scope != expected_operation_scopes[node_requirement.operation_ref]:
                    raise ValueError(f"node requirement scope differs from its operation for {ref}")
            for scope in requirement.required_key_scopes:
                if scope not in routes_by_key:
                    raise ValueError(f"key scope {scope} for {ref} is absent from the catalog")
                if normalize_key_scope(scope, symmetric=self.symmetric_keys) != scope:
                    raise ValueError(f"non-normalized key scope for {ref}: {scope}")
                routes_by_key[scope].append(ref)
            for node, node_scopes in requirement.required_keys_by_node.items():
                if node not in nodes:
                    raise ValueError(f"unknown key recipient {node} for {ref}")
                if len(set(node_scopes)) != len(node_scopes):
                    raise ValueError(f"duplicate node key scopes for {ref}, node {node}")
                for scope in node_scopes:
                    routes_by_node_key.setdefault((node, scope), []).append(ref)
            if requirement.required_keys_by_node != plan.required_keys_by_node(symmetric_keys=self.symmetric_keys):
                raise ValueError(f"node key requirements do not match the protection plan for {ref}")
        if any(not refs for refs in routes_by_key.values()):
            raise ValueError("key catalog contains scopes unused by every route")
        object.__setattr__(self, "requirements", MappingProxyType(requirements))
        object.__setattr__(self, "key_scopes", scopes)
        object.__setattr__(self, "routes_by_key", MappingProxyType({
            scope: tuple(refs) for scope, refs in routes_by_key.items()
        }))
        object.__setattr__(self, "routes_by_node_key", MappingProxyType({
            node_scope: tuple(refs) for node_scope, refs in routes_by_node_key.items()
        }))

    @property
    def security_model(self) -> SecurityModelType:
        return self.catalog.policies[self.policy_id]

    @property
    def pairs(self) -> tuple[tuple[int, int], ...]:
        return self.catalog.annotations.routes.scenario.pairs

    @property
    def node_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self.catalog.annotations.routes.scenario.topology))

    @property
    def routes_by_pair(self) -> Mapping[tuple[int, int], tuple[RouteRef, ...]]:
        return self.catalog.annotations.routes.routes_by_pair


class ActivationPlanner:
    """Project security plans into reusable key and delivery incidences."""

    def build(
        self, catalog: ProtectionCatalog, *, policy_id: str, symmetric_keys: bool = False,
    ) -> ActivationProblem:
        if policy_id not in catalog.policies:
            raise ValueError(f"unknown protection policy: {policy_id}")
        requirements = {}
        all_scopes = {}
        ordered_refs = (ref for refs in catalog.annotations.routes.routes_by_pair.values() for ref in refs)
        for ref in ordered_refs:
            plan = catalog.by_plan[PlanRef(ref, policy_id)]
            scopes = tuple(dict.fromkeys(
                normalize_key_scope(requirement.scope, symmetric=symmetric_keys)
                for requirement in plan.key_requirements
            ))
            operation_scopes = {
                operation.ref: normalize_key_scope(KeyScope(
                    operation.required_key_type, operation.key_source_id, operation.key_target_id,
                ), symmetric=symmetric_keys)
                for operation in plan.operations
            }
            requirements[ref] = ActivationRequirement(
                ref=ref, required_key_scopes=scopes, operation_scopes=operation_scopes,
                required_keys_by_node=plan.required_keys_by_node(symmetric_keys=symmetric_keys),
            )
            for scope in scopes:
                all_scopes[scope] = None
        return ActivationProblem(catalog, policy_id, symmetric_keys, requirements, tuple(all_scopes))
