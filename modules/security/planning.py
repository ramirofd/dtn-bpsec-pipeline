"""Security planning built from concrete security-model classes."""

from __future__ import annotations

from abc import ABC
from typing import Sequence

from modules.security.annotated_routes import AnnotatedHop, AnnotatedRoute, BoundaryCrossing
from modules.security.artifacts import NodeSecurityRequirement, ProtectionOperation, ProtectionPlan
from modules.security.keys import KeyRequirement
from modules.security.models import KeyType, NodeAction, SecurityModel, SecurityModelType, SecurityService


class BaseSecurityModel(SecurityModel, ABC):
    service = SecurityService.BCB

    def _build_plan(
        self,
        annotated_route: AnnotatedRoute,
        operations: tuple[ProtectionOperation, ...],
        *,
        notes: tuple[str, ...] = (),
    ) -> ProtectionPlan:
        node_requirements: list[NodeSecurityRequirement] = []
        key_requirements: list[KeyRequirement] = []

        for operation in operations:
            node_requirements.extend(self._build_node_requirements(operation))
            key_requirements.append(self._build_key_requirement(operation))

        return ProtectionPlan(
            route_id=annotated_route.route_id,
            model=self.type,
            operations=operations,
            node_requirements=tuple(node_requirements),
            key_requirements=tuple(key_requirements),
            notes=notes,
        )

    def _build_boundary_operation(
        self,
        *,
        annotated_route: AnnotatedRoute,
        crossing: BoundaryCrossing,
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
            operation_id=f"{annotated_route.route_id}:{self.name}:{crossing.crossing_index}",
            model=self.type,
            service=self.service,
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
        self,
        *,
        annotated_route: AnnotatedRoute,
        hops: tuple[AnnotatedHop, ...],
        rationale: str,
    ) -> ProtectionOperation:
        first_hop = hops[0]
        last_hop = hops[-1]
        return ProtectionOperation(
            operation_id=(
                f"{annotated_route.route_id}:{self.name}:segment:"
                f"{first_hop.hop_index}-{last_hop.hop_index}"
            ),
            model=self.type,
            service=self.service,
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

    def _build_node_requirements(
        self,
        operation: ProtectionOperation,
    ) -> tuple[NodeSecurityRequirement, NodeSecurityRequirement]:
        return (
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
        )

    def _build_key_requirement(self, operation: ProtectionOperation) -> KeyRequirement:
        return KeyRequirement(
            operation_id=operation.operation_id,
            key_type=operation.required_key_type,
            usage=operation.service,
            source_id=operation.key_source_id,
            target_id=operation.key_target_id,
            local_node=operation.source_node,
            rationale=operation.rationale,
        )


class HopByHopSecurityModel(BaseSecurityModel):
    type = SecurityModelType.HOP_BY_HOP

    def build_plan(self, annotated_route: AnnotatedRoute) -> ProtectionPlan:
        operations = tuple(
            ProtectionOperation(
                operation_id=f"{annotated_route.route_id}:hop:{hop.hop_index}",
                model=self.type,
                service=self.service,
                source_node=hop.from_node,
                acceptor_node=hop.to_node,
                target_hop_indexes=(hop.hop_index,),
                source_network=hop.from_network,
                acceptor_network=hop.to_network,
                required_key_type=KeyType.NODE_TO_NODE,
                key_source_id=hop.from_node,
                key_target_id=hop.to_node,
                rationale=f"Protect hop {hop.from_node}->{hop.to_node} under hop-by-hop BCB",
            )
            for hop in annotated_route.hops
        )
        return self._build_plan(annotated_route, operations)


class EndToEndSecurityModel(BaseSecurityModel):
    type = SecurityModelType.END_TO_END

    def build_plan(self, annotated_route: AnnotatedRoute) -> ProtectionPlan:
        operation = ProtectionOperation(
            operation_id=f"{annotated_route.route_id}:e2e",
            model=self.type,
            service=self.service,
            source_node=annotated_route.src_node,
            acceptor_node=annotated_route.dst_node,
            target_hop_indexes=tuple(hop.hop_index for hop in annotated_route.hops),
            source_network=annotated_route.source_network,
            acceptor_network=annotated_route.destination_network,
            required_key_type=KeyType.NODE_TO_NODE,
            key_source_id=annotated_route.src_node,
            key_target_id=annotated_route.dst_node,
            rationale=(
                f"Protect route {annotated_route.src_node}->{annotated_route.dst_node} "
                "with a single end-to-end BCB"
            ),
        )
        return self._build_plan(annotated_route, (operation,))


class EdgeByEdgeSecurityModel(BaseSecurityModel):
    type = SecurityModelType.EDGE_BY_EDGE

    def build_plan(self, annotated_route: AnnotatedRoute) -> ProtectionPlan:
        operations: list[ProtectionOperation] = []
        segment_hops: list[AnnotatedHop] = []
        boundary_by_hop = {
            crossing.hop_index: crossing for crossing in annotated_route.boundary_crossings
        }

        for hop in annotated_route.hops:
            if hop.crosses_network_boundary:
                if segment_hops:
                    operations.append(
                        self._build_intra_network_segment_operation(
                            annotated_route=annotated_route,
                            hops=tuple(segment_hops),
                            rationale="Protect the current intra-network segment until the next gateway",
                        )
                    )
                    segment_hops.clear()
                operations.append(
                    self._build_boundary_operation(
                        annotated_route=annotated_route,
                        crossing=boundary_by_hop[hop.hop_index],
                        key_type=KeyType.GROUP_TO_GROUP,
                    )
                )
                continue

            segment_hops.append(hop)

        if segment_hops:
            operations.append(
                self._build_intra_network_segment_operation(
                    annotated_route=annotated_route,
                    hops=tuple(segment_hops),
                    rationale="Protect the final intra-network segment after the last gateway",
                )
            )

        return self._build_plan(annotated_route, tuple(operations))


class EdgeToEdgeSecurityModel(BaseSecurityModel):
    type = SecurityModelType.EDGE_TO_EDGE

    def build_plan(self, annotated_route: AnnotatedRoute) -> ProtectionPlan:
        if not annotated_route.boundary_crossings:
            operation = self._build_intra_network_segment_operation(
                annotated_route=annotated_route,
                hops=annotated_route.hops,
                rationale="Protect the whole intra-network route as a single edge segment",
            )
            return self._build_plan(
                annotated_route,
                (operation,),
                notes=(
                    "Route stays within one network; edge-to-edge degenerates to local intra-network protection.",
                ),
            )

        operations: list[ProtectionOperation] = []
        first_crossing = annotated_route.boundary_crossings[0]
        last_crossing = annotated_route.boundary_crossings[-1]

        source_segment_hops = tuple(
            hop for hop in annotated_route.hops if hop.hop_index < first_crossing.hop_index
        )
        if source_segment_hops:
            operations.append(
                self._build_intra_network_segment_operation(
                    annotated_route=annotated_route,
                    hops=source_segment_hops,
                    rationale="Protect the source-network segment from the bundle source to the exit gateway",
                )
            )

        operations.append(
            ProtectionOperation(
                operation_id=f"{annotated_route.route_id}:{self.name}:transit",
                model=self.type,
                service=self.service,
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
        )

        destination_segment_hops = tuple(
            hop for hop in annotated_route.hops if hop.hop_index > last_crossing.hop_index
        )
        if destination_segment_hops:
            operations.append(
                self._build_intra_network_segment_operation(
                    annotated_route=annotated_route,
                    hops=destination_segment_hops,
                    rationale=(
                        "Protect the destination-network segment from the entrance gateway "
                        "to the bundle destination"
                    ),
                )
            )

        return self._build_plan(annotated_route, tuple(operations))


HOP_BY_HOP_MODEL = HopByHopSecurityModel()
END_TO_END_MODEL = EndToEndSecurityModel()
EDGE_BY_EDGE_MODEL = EdgeByEdgeSecurityModel()
EDGE_TO_EDGE_MODEL = EdgeToEdgeSecurityModel()

DEFAULT_SECURITY_MODELS = (
    HOP_BY_HOP_MODEL,
    END_TO_END_MODEL,
    EDGE_BY_EDGE_MODEL,
    EDGE_TO_EDGE_MODEL,
)

SECURITY_MODEL_REGISTRY = {
    model.type: model
    for model in DEFAULT_SECURITY_MODELS
}


def get_security_model(
    model: SecurityModel | SecurityModelType,
) -> SecurityModel:
    if isinstance(model, SecurityModel):
        return model
    try:
        return SECURITY_MODEL_REGISTRY[model]
    except KeyError as exc:
        raise ValueError(f"unsupported security model: {model}") from exc


def resolve_security_models(
    security_models: Sequence[SecurityModel | SecurityModelType] | None,
) -> tuple[SecurityModel, ...]:
    if security_models is None:
        return DEFAULT_SECURITY_MODELS
    return tuple(get_security_model(model) for model in security_models)


def build_protection_plan(
    model: SecurityModel | SecurityModelType,
    annotated_route: AnnotatedRoute,
) -> ProtectionPlan:
    return get_security_model(model).build_plan(annotated_route)


def build_protection_plans(
    model: SecurityModel | SecurityModelType,
    annotated_routes: Sequence[AnnotatedRoute],
) -> tuple[ProtectionPlan, ...]:
    return get_security_model(model).build_plans(annotated_routes)


__all__ = [
    "BaseSecurityModel",
    "HopByHopSecurityModel",
    "EndToEndSecurityModel",
    "EdgeByEdgeSecurityModel",
    "EdgeToEdgeSecurityModel",
    "DEFAULT_SECURITY_MODELS",
    "SECURITY_MODEL_REGISTRY",
    "get_security_model",
    "resolve_security_models",
    "build_protection_plan",
    "build_protection_plans",
]
