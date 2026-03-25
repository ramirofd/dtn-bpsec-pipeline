"""Security planning derived from annotated routes and chosen models."""

from __future__ import annotations

from dataclasses import dataclass

from modules.security.annotated_routes import AnnotatedRoute, BoundaryCrossing
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


def build_protection_plan(
    annotated_route: AnnotatedRoute,
    model: SecurityModelType,
) -> ProtectionPlan:
    if model is SecurityModelType.HOP_BY_HOP:
        return _build_hop_by_hop_plan(annotated_route)
    if model is SecurityModelType.END_TO_END:
        return _build_end_to_end_plan(annotated_route)
    if model is SecurityModelType.EDGE_BY_EDGE:
        return _build_edge_by_edge_plan(annotated_route)
    if model is SecurityModelType.EDGE_TO_EDGE:
        return _build_edge_to_edge_plan(annotated_route)
    raise ValueError(f"unsupported security model: {model}")


def _build_hop_by_hop_plan(annotated_route: AnnotatedRoute) -> ProtectionPlan:
    operations: list[ProtectionOperation] = []
    node_requirements: list[NodeSecurityRequirement] = []
    key_requirements: list[KeyRequirement] = []

    for hop in annotated_route.hops:
        operation_id = f"{annotated_route.route_id}:hop:{hop.hop_index}"
        rationale = f"Protect hop {hop.from_node}->{hop.to_node} under hop-by-hop BCB"
        operation = ProtectionOperation(
            operation_id=operation_id,
            model=SecurityModelType.HOP_BY_HOP,
            service=SecurityService.BCB,
            source_node=hop.from_node,
            acceptor_node=hop.to_node,
            target_hop_indexes=(hop.hop_index,),
            source_network=hop.from_network,
            acceptor_network=hop.to_network,
            required_key_type=KeyType.NODE_TO_NODE,
            key_source_id=hop.from_node,
            key_target_id=hop.to_node,
            rationale=rationale,
        )
        operations.append(operation)
        node_requirements.extend(_build_node_requirements(operation))
        key_requirements.append(_build_key_requirement(operation))

    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=SecurityModelType.HOP_BY_HOP,
        operations=tuple(operations),
        node_requirements=tuple(node_requirements),
        key_requirements=tuple(key_requirements),
    )


def _build_end_to_end_plan(annotated_route: AnnotatedRoute) -> ProtectionPlan:
    rationale = (
        f"Protect route {annotated_route.src_node}->{annotated_route.dst_node} "
        "with a single end-to-end BCB"
    )
    operation = ProtectionOperation(
        operation_id=f"{annotated_route.route_id}:e2e",
        model=SecurityModelType.END_TO_END,
        service=SecurityService.BCB,
        source_node=annotated_route.src_node,
        acceptor_node=annotated_route.dst_node,
        target_hop_indexes=tuple(hop.hop_index for hop in annotated_route.hops),
        source_network=annotated_route.source_network,
        acceptor_network=annotated_route.destination_network,
        required_key_type=KeyType.NODE_TO_NODE,
        key_source_id=annotated_route.src_node,
        key_target_id=annotated_route.dst_node,
        rationale=rationale,
    )
    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=SecurityModelType.END_TO_END,
        operations=(operation,),
        node_requirements=tuple(_build_node_requirements(operation)),
        key_requirements=(_build_key_requirement(operation),),
    )


def _build_edge_by_edge_plan(annotated_route: AnnotatedRoute) -> ProtectionPlan:
    if not annotated_route.boundary_crossings:
        return ProtectionPlan(
            route_id=annotated_route.route_id,
            model=SecurityModelType.EDGE_BY_EDGE,
            operations=(),
            node_requirements=(),
            key_requirements=(),
            notes=("Route stays within one network; no edge-by-edge crossings were generated.",),
        )

    operations: list[ProtectionOperation] = []
    node_requirements: list[NodeSecurityRequirement] = []
    key_requirements: list[KeyRequirement] = []

    for crossing in annotated_route.boundary_crossings:
        operation = _build_edge_boundary_operation(
            annotated_route=annotated_route,
            crossing=crossing,
            model=SecurityModelType.EDGE_BY_EDGE,
            key_type=KeyType.NODE_TO_NETWORK,
        )
        operations.append(operation)
        node_requirements.extend(_build_node_requirements(operation))
        key_requirements.append(_build_key_requirement(operation))

    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=SecurityModelType.EDGE_BY_EDGE,
        operations=tuple(operations),
        node_requirements=tuple(node_requirements),
        key_requirements=tuple(key_requirements),
    )


def _build_edge_to_edge_plan(annotated_route: AnnotatedRoute) -> ProtectionPlan:
    if not annotated_route.boundary_crossings:
        return ProtectionPlan(
            route_id=annotated_route.route_id,
            model=SecurityModelType.EDGE_TO_EDGE,
            operations=(),
            node_requirements=(),
            key_requirements=(),
            notes=("Route stays within one network; no edge-to-edge crossings were generated.",),
        )

    operations: list[ProtectionOperation] = []
    node_requirements: list[NodeSecurityRequirement] = []
    key_requirements: list[KeyRequirement] = []

    for crossing in annotated_route.boundary_crossings:
        operation = _build_edge_boundary_operation(
            annotated_route=annotated_route,
            crossing=crossing,
            model=SecurityModelType.EDGE_TO_EDGE,
            key_type=KeyType.NETWORK_TO_NETWORK,
        )
        operations.append(operation)
        node_requirements.extend(_build_node_requirements(operation))
        key_requirements.append(_build_key_requirement(operation))

    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=SecurityModelType.EDGE_TO_EDGE,
        operations=tuple(operations),
        node_requirements=tuple(node_requirements),
        key_requirements=tuple(key_requirements),
    )


def _build_edge_boundary_operation(
    *,
    annotated_route: AnnotatedRoute,
    crossing: BoundaryCrossing,
    model: SecurityModelType,
    key_type: KeyType,
) -> ProtectionOperation:
    rationale = (
        f"Protect boundary crossing {crossing.from_network}->{crossing.to_network} "
        f"through hop {crossing.exit_node}->{crossing.entrance_node}"
    )
    if key_type is KeyType.NODE_TO_NETWORK:
        key_source_id = crossing.exit_node
        key_target_id = crossing.to_network
    else:
        key_source_id = crossing.from_network
        key_target_id = crossing.to_network

    return ProtectionOperation(
        operation_id=f"{annotated_route.route_id}:{model.name.lower()}:{crossing.crossing_index}",
        model=model,
        service=SecurityService.BCB,
        source_node=crossing.exit_node,
        acceptor_node=crossing.entrance_node,
        target_hop_indexes=(crossing.hop_index,),
        source_network=crossing.from_network,
        acceptor_network=crossing.to_network,
        required_key_type=key_type,
        key_source_id=key_source_id,
        key_target_id=key_target_id,
        rationale=rationale,
    )


def _build_node_requirements(operation: ProtectionOperation) -> list[NodeSecurityRequirement]:
    return [
        NodeSecurityRequirement(
            operation_id=operation.operation_id,
            node_id=operation.source_node,
            role=NodeAction.SOURCE,
            service=operation.service,
            key_type=operation.required_key_type,
            key_source_id=operation.key_source_id,
            key_target_id=operation.key_target_id,
            rationale=operation.rationale,
        ),
        NodeSecurityRequirement(
            operation_id=operation.operation_id,
            node_id=operation.acceptor_node,
            role=NodeAction.ACCEPT,
            service=operation.service,
            key_type=operation.required_key_type,
            key_source_id=operation.key_source_id,
            key_target_id=operation.key_target_id,
            rationale=operation.rationale,
        ),
    ]


def _build_key_requirement(operation: ProtectionOperation) -> KeyRequirement:
    return KeyRequirement(
        operation_id=operation.operation_id,
        key_type=operation.required_key_type,
        usage=operation.service,
        source_id=operation.key_source_id,
        target_id=operation.key_target_id,
        local_node=operation.source_node,
        rationale=operation.rationale,
    )
