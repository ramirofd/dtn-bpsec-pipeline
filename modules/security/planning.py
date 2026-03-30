"""Security planning derived from annotated routes and chosen models."""

from __future__ import annotations

from dataclasses import dataclass

from modules.security.annotated_routes import AnnotatedHop, AnnotatedRoute, BoundaryCrossing
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
    operations: list[ProtectionOperation] = []
    node_requirements: list[NodeSecurityRequirement] = []
    key_requirements: list[KeyRequirement] = []

    for operation in _build_edge_by_edge_operations(annotated_route):
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
        return _build_local_only_plan(
            annotated_route,
            model=SecurityModelType.EDGE_TO_EDGE,
            note="Route stays within one network; edge-to-edge degenerates to local intra-network protection.",
        )

    operations: list[ProtectionOperation] = []
    node_requirements: list[NodeSecurityRequirement] = []
    key_requirements: list[KeyRequirement] = []

    first_crossing = annotated_route.boundary_crossings[0]
    last_crossing = annotated_route.boundary_crossings[-1]

    source_segment_hops = tuple(
        hop for hop in annotated_route.hops if hop.hop_index < first_crossing.hop_index
    )
    if source_segment_hops:
        source_operation = _build_intra_network_segment_operation(
            annotated_route=annotated_route,
            hops=source_segment_hops,
            model=SecurityModelType.EDGE_TO_EDGE,
            rationale=(
                "Protect the source-network segment from the bundle source "
                "to the exit gateway"
            ),
        )
        operations.append(source_operation)
        node_requirements.extend(_build_node_requirements(source_operation))
        key_requirements.append(_build_key_requirement(source_operation))

    transit_operation = ProtectionOperation(
        operation_id=f"{annotated_route.route_id}:edge_to_edge:transit",
        model=SecurityModelType.EDGE_TO_EDGE,
        service=SecurityService.BCB,
        source_node=first_crossing.exit_node,
        acceptor_node=last_crossing.entrance_node,
        target_hop_indexes=tuple(
            hop.hop_index
            for hop in annotated_route.hops
            if first_crossing.hop_index <= hop.hop_index <= last_crossing.hop_index
        ),
        source_network=first_crossing.from_network,
        acceptor_network=annotated_route.destination_network,
        required_key_type=KeyType.GROUP_TO_GROUP,
        key_source_id=first_crossing.from_network,
        key_target_id=annotated_route.destination_network,
        rationale=(
            f"Protect inter-network transit between source group {first_crossing.from_network} "
            f"and destination group {annotated_route.destination_network}"
        ),
    )
    operations.append(transit_operation)
    node_requirements.extend(_build_node_requirements(transit_operation))
    key_requirements.append(_build_key_requirement(transit_operation))

    destination_segment_hops = tuple(
        hop for hop in annotated_route.hops if hop.hop_index > last_crossing.hop_index
    )
    if destination_segment_hops:
        destination_operation = _build_intra_network_segment_operation(
            annotated_route=annotated_route,
            hops=destination_segment_hops,
            model=SecurityModelType.EDGE_TO_EDGE,
            rationale=(
                "Protect the destination-network segment from the entrance gateway "
                "to the bundle destination"
            ),
        )
        operations.append(destination_operation)
        node_requirements.extend(_build_node_requirements(destination_operation))
        key_requirements.append(_build_key_requirement(destination_operation))

    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=SecurityModelType.EDGE_TO_EDGE,
        operations=tuple(operations),
        node_requirements=tuple(node_requirements),
        key_requirements=tuple(key_requirements),
    )


def _build_local_only_plan(
    annotated_route: AnnotatedRoute,
    *,
    model: SecurityModelType,
    note: str,
) -> ProtectionPlan:
    operation = _build_intra_network_segment_operation(
        annotated_route=annotated_route,
        hops=annotated_route.hops,
        model=model,
        rationale="Protect the whole intra-network route as a single edge segment",
    )

    return ProtectionPlan(
        route_id=annotated_route.route_id,
        model=model,
        operations=(operation,),
        node_requirements=tuple(_build_node_requirements(operation)),
        key_requirements=(_build_key_requirement(operation),),
        notes=(note,),
    )


def _build_edge_by_edge_operations(
    annotated_route: AnnotatedRoute,
) -> tuple[ProtectionOperation, ...]:
    operations: list[ProtectionOperation] = []
    segment_hops: list[AnnotatedHop] = []
    boundary_by_hop = {
        crossing.hop_index: crossing for crossing in annotated_route.boundary_crossings
    }

    for hop in annotated_route.hops:
        if hop.crosses_network_boundary:
            if segment_hops:
                operations.append(
                    _build_intra_network_segment_operation(
                        annotated_route=annotated_route,
                        hops=tuple(segment_hops),
                        model=SecurityModelType.EDGE_BY_EDGE,
                        rationale=(
                            "Protect the current intra-network segment until the next gateway"
                        ),
                    )
                )
                segment_hops.clear()
            operations.append(
                _build_edge_boundary_operation(
                    annotated_route=annotated_route,
                    crossing=boundary_by_hop[hop.hop_index],
                    model=SecurityModelType.EDGE_BY_EDGE,
                    key_type=KeyType.GROUP_TO_GROUP,
                )
            )
            continue

        segment_hops.append(hop)

    if segment_hops:
        operations.append(
            _build_intra_network_segment_operation(
                annotated_route=annotated_route,
                hops=tuple(segment_hops),
                model=SecurityModelType.EDGE_BY_EDGE,
                rationale="Protect the final intra-network segment after the last gateway",
            )
        )

    return tuple(operations)


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
    if key_type is KeyType.NODE_TO_GROUP:
        key_source_id = crossing.exit_node
        key_target_id = crossing.from_network
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


def _build_intra_network_segment_operation(
    *,
    annotated_route: AnnotatedRoute,
    hops: tuple[AnnotatedHop, ...],
    model: SecurityModelType,
    rationale: str,
) -> ProtectionOperation:
    first_hop = hops[0]
    last_hop = hops[-1]
    return ProtectionOperation(
        operation_id=(
            f"{annotated_route.route_id}:{model.name.lower()}:segment:"
            f"{first_hop.hop_index}-{last_hop.hop_index}"
        ),
        model=model,
        service=SecurityService.BCB,
        source_node=first_hop.from_node,
        acceptor_node=last_hop.to_node,
        target_hop_indexes=tuple(hop.hop_index for hop in hops),
        source_network=first_hop.from_network,
        acceptor_network=last_hop.to_network,
        required_key_type=KeyType.NODE_TO_GROUP,
        key_source_id=first_hop.from_node,
        key_target_id=first_hop.from_network,
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
