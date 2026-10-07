from __future__ import annotations

from collections.abc import Iterable, Mapping

from modules.domain import ContactSnapshot, RouteCandidate, RouteRef, Scenario
from modules.network.cgr.models import Contact, Route
from modules.network.topology import Topology
from modules.security.annotated_routes import (
    AnnotatedHop,
    AnnotatedRoute,
    BoundaryCrossing,
)
from modules.security.models import NetworkRole
from pipelines.catalogs import AnnotationCatalog, RouteCatalog


def make_contact(
    frm: int,
    to: int,
    *,
    start: int = 0,
    end: int = 1000,
    rate: int = 1,
    owlt: int = 0,
) -> Contact:
    return Contact(
        frm=frm,
        to=to,
        start=start,
        end=end,
        rate=rate,
        owlt=owlt,
    )


def make_route(contacts: Iterable[Contact]) -> Route:
    iterator = iter(contacts)
    first = next(iterator)
    route = Route(first)
    for contact in iterator:
        route = route + contact
    return route


def make_topology(networks: Mapping[int, Iterable[int]]) -> Topology:
    node_to_network: dict[int, int] = {}
    network_to_nodes: dict[int, frozenset[int]] = {}

    for network_id, nodes in networks.items():
        node_set = frozenset(nodes)
        network_to_nodes[network_id] = node_set
        for node_id in node_set:
            node_to_network[node_id] = network_id

    return Topology(
        node_to_network=node_to_network,
        network_to_nodes=network_to_nodes,
    )


def make_annotated_route(
    topology: Topology,
    *,
    source_node: int,
    destination_node: int,
    contacts: Iterable[Contact],
    candidate_id: int = 1,
) -> AnnotatedRoute:
    contact_list = tuple(contacts)
    if not contact_list:
        raise ValueError("annotated routes used as test fixtures must contain at least one hop")

    annotated_hops: list[AnnotatedHop] = []
    node_path = [contact_list[0].frm]
    network_path = [topology.get_network_for_node(contact_list[0].frm)]
    boundary_crossings: list[BoundaryCrossing] = []
    gateway_nodes: set[int] = set()

    for hop_index, contact in enumerate(contact_list):
        from_network = topology.get_network_for_node(contact.frm)
        to_network = topology.get_network_for_node(contact.to)
        crosses_network_boundary = from_network != to_network

        annotated_hops.append(
            AnnotatedHop(
                hop_index=hop_index,
                from_node=contact.frm,
                to_node=contact.to,
                from_network=from_network,
                to_network=to_network,
                crosses_network_boundary=crosses_network_boundary,
                from_role=NetworkRole.UNKNOWN,
                to_role=NetworkRole.UNKNOWN,
            )
        )
        node_path.append(contact.to)
        network_path.append(to_network)

        if crosses_network_boundary:
            boundary_crossings.append(
                BoundaryCrossing(
                    crossing_index=len(boundary_crossings),
                    hop_index=hop_index,
                    exit_node=contact.frm,
                    entrance_node=contact.to,
                    from_network=from_network,
                    to_network=to_network,
                )
            )
            gateway_nodes.add(contact.frm)
            gateway_nodes.add(contact.to)
    
    return AnnotatedRoute(
        ref=RouteRef((source_node, destination_node), candidate_id),
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


def make_scenario(topology: Topology, contacts: Iterable[Contact], pairs=None) -> Scenario:
    return Scenario(topology, tuple(ContactSnapshot.from_contact(c) for c in contacts), pairs)


def make_route_catalog(
    *, topology: Topology,
    pairs: tuple[tuple[int, int], ...],
    routes_by_pair: Mapping[tuple[int, int], tuple[Route, ...]],
) -> RouteCatalog:
    candidates = {
        RouteRef(pair, index): RouteCandidate.from_route(RouteRef(pair, index), route)
        for pair, routes in routes_by_pair.items()
        for index, route in enumerate(routes, start=1)
    }
    contacts = tuple(dict.fromkeys(c for route in candidates.values() for c in route.contacts))
    return RouteCatalog(Scenario(topology, contacts, pairs), candidates)


def make_annotation_catalog(
    *, routes: RouteCatalog, annotated_routes: Iterable[AnnotatedRoute],
) -> AnnotationCatalog:
    annotations = tuple(annotated_routes)
    by_route = {annotation.ref: annotation for annotation in annotations}
    if len(by_route) != len(annotations):
        raise ValueError("duplicate annotated route reference")
    return AnnotationCatalog(routes, by_route)
