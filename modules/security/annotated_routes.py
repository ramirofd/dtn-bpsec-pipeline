"""Route annotations enriched with topology and per-hop role hints."""

from __future__ import annotations

from dataclasses import dataclass

from modules.network.cgr.models import Route
from modules.network.topology import Topology
from modules.security.models import NetworkRole
from modules.security.roles import get_network_role_for_endpoints


@dataclass(slots=True, frozen=True)
class AnnotatedHop:
    hop_index: int
    from_node: int
    to_node: int
    from_network: int
    to_network: int
    crosses_network_boundary: bool
    from_role: NetworkRole
    to_role: NetworkRole


@dataclass(slots=True, frozen=True)
class BoundaryCrossing:
    crossing_index: int
    hop_index: int
    exit_node: int
    entrance_node: int
    from_network: int
    to_network: int
    
    def __repr__(self):
        return f"{self.exit_node}->{self.entrance_node}"


@dataclass(slots=True, frozen=True)
class AnnotatedRoute:
    route_id: str
    src_node: int
    dst_node: int
    source_network: int
    destination_network: int
    hops: tuple[AnnotatedHop, ...]
    node_path: tuple[int, ...]
    network_path: tuple[int, ...]
    boundary_crossings: tuple[BoundaryCrossing, ...]
    gateway_nodes: frozenset[int]


def annotate_route(
    route: Route,
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
    route_id: str | None = None,
) -> AnnotatedRoute:
    raw_hops = route.get_hops()
    if not raw_hops:
        raise ValueError("route must contain at least one hop")

    annotated_hops: list[AnnotatedHop] = []
    boundary_crossings: list[BoundaryCrossing] = []
    gateway_nodes: set[int] = set()

    node_path = [raw_hops[0].frm]
    network_path = [topology.get_network_for_node(raw_hops[0].frm)]

    for hop_index, contact in enumerate(raw_hops):
        from_network = topology.get_network_for_node(contact.frm)
        to_network = topology.get_network_for_node(contact.to)
        crosses_network_boundary = from_network != to_network

        from_role = get_network_role_for_endpoints(
            source_node=source_node,
            destination_node=destination_node,
            contact=contact,
            topology=topology,
            current_node=contact.frm,
        )
        to_role = get_network_role_for_endpoints(
            source_node=source_node,
            destination_node=destination_node,
            contact=contact,
            topology=topology,
            current_node=contact.to,
        )

        annotated_hops.append(
            AnnotatedHop(
                hop_index=hop_index,
                from_node=contact.frm,
                to_node=contact.to,
                from_network=from_network,
                to_network=to_network,
                crosses_network_boundary=crosses_network_boundary,
                from_role=from_role,
                to_role=to_role,
            )
        )
        node_path.append(contact.to)
        network_path.append(to_network)

        if crosses_network_boundary:
            crossing = BoundaryCrossing(
                crossing_index=len(boundary_crossings),
                hop_index=hop_index,
                exit_node=contact.frm,
                entrance_node=contact.to,
                from_network=from_network,
                to_network=to_network,
            )
            boundary_crossings.append(crossing)
            gateway_nodes.add(contact.frm)
            gateway_nodes.add(contact.to)

    return AnnotatedRoute(
        route_id=route_id or f"{source_node}->{destination_node}:{len(raw_hops)}h",
        src_node=source_node,
        dst_node=destination_node,
        source_network=topology.get_network_for_node(source_node),
        destination_network=topology.get_network_for_node(destination_node),
        hops=tuple(annotated_hops),
        node_path=tuple(node_path),
        network_path=tuple(network_path),
        boundary_crossings=tuple(boundary_crossings),
        gateway_nodes=frozenset(gateway_nodes),
    )


def annotate_routes(
    routes: list[Route] | tuple[Route, ...],
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
) -> tuple[AnnotatedRoute, ...]:
    return tuple(
        annotate_route(
            route,
            topology,
            source_node=source_node,
            destination_node=destination_node,
            route_id=f"route-{index}",
        )
        for index, route in enumerate(routes, start=1)
    )
