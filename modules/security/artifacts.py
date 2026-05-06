"""Security planning artifacts produced from annotated routes."""

from __future__ import annotations

from dataclasses import dataclass

from modules.security.keys import KeyRequirement
from modules.security.models import KeyType, NodeAction, SecurityModelType, SecurityService


@dataclass(slots=True, frozen=True)
class ProtectionOperation:
    operation_id: str
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


@dataclass(slots=True, frozen=True)
class NodeSecurityRequirement:
    operation_id: str
    node_id: int
    role: NodeAction
    service: SecurityService
    key_type: KeyType
    key_source_id: int
    key_target_id: int
    rationale: str


@dataclass(slots=True, frozen=True)
class ProtectionPlan:
    route_id: str
    model: SecurityModelType
    operations: tuple[ProtectionOperation, ...]
    node_requirements: tuple[NodeSecurityRequirement, ...]
    key_requirements: tuple[KeyRequirement, ...]
    notes: tuple[str, ...] = ()
