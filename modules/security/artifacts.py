"""Security planning artifacts produced from annotated routes."""

from __future__ import annotations

from dataclasses import dataclass

from modules.domain import OperationRef, PlanRef
from modules.security.keys import KeyRequirement, KeyScope, normalize_key_scope
from modules.security.models import KeyType, NodeAction, SecurityModelType, SecurityService


@dataclass(slots=True, frozen=True)
class ProtectionOperation:
    """One concrete protection action applied to a route span or boundary crossing."""

    ref: OperationRef
    model: SecurityModelType
    service: SecurityService
    source_node: int
    acceptor_node: int
    target_hop_indexes: tuple[int, ...]
    source_network: int
    acceptor_network: int
    required_key_type: KeyType
    key_source_id: int
    key_target_id: int
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "target_hop_indexes", tuple(self.target_hop_indexes))


@dataclass(slots=True, frozen=True)
class NodeSecurityRequirement:
    """One node-local action implied by a protection operation."""

    operation_ref: OperationRef
    node_id: int
    role: NodeAction
    service: SecurityService
    key_type: KeyType
    key_source_id: int
    key_target_id: int
    rationale: str


@dataclass(slots=True, frozen=True)
class ProtectionPlan:
    """All operations and key requirements needed to protect one annotated route."""

    ref: PlanRef
    model: SecurityModelType
    operations: tuple[ProtectionOperation, ...]
    node_requirements: tuple[NodeSecurityRequirement, ...]
    key_requirements: tuple[KeyRequirement, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("operations", "node_requirements", "key_requirements", "notes"):
            object.__setattr__(self, name, tuple(getattr(self, name)))

    def required_keys_by_node(
        self, *, symmetric_keys: bool = False,
    ) -> dict[int, tuple[KeyScope, ...]]:
        """Distinct keys needed by each node performing a security action.

        Group scopes are delivered only to the participants in this plan, not
        to every group member. Node requirements include both the security
        source and acceptor; KeyRequirement.local_node includes only the source.
        """
        scopes_by_node: dict[int, dict[KeyScope, None]] = {}
        for requirement in self.node_requirements:
            scope = normalize_key_scope(
                KeyScope(
                    requirement.key_type,
                    requirement.key_source_id,
                    requirement.key_target_id,
                ),
                symmetric=symmetric_keys,
            )
            scopes_by_node.setdefault(requirement.node_id, {})[scope] = None
        return {
            node: tuple(scopes)
            for node, scopes in sorted(scopes_by_node.items())
        }
