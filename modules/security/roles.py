"""Security-oriented network role classification helpers."""

from __future__ import annotations

from modules.network.cgr.models import Bundle, Contact
from modules.network.topology import Topology
from modules.security.models import NetworkRole


def get_network_role_from_hop(
    bundle: Bundle,
    contact: Contact,
    topology: Topology,
    current_node: int,
) -> NetworkRole:
    is_source = current_node == bundle.src
    is_destination = current_node == bundle.dst

    crosses_network_boundary = not topology.are_in_same_network(contact.frm, contact.to)

    is_exit_gateway = current_node == contact.frm and crosses_network_boundary
    is_entrance_gateway = current_node == contact.to and crosses_network_boundary

    if is_source:
        return NetworkRole.SOURCE_N_EXIT if is_exit_gateway else NetworkRole.SOURCE

    if is_destination:
        return (
            NetworkRole.DESTINATION_N_ENTRANCE
            if is_entrance_gateway
            else NetworkRole.DESTINATION
        )

    if is_exit_gateway:
        return NetworkRole.EXIT

    if is_entrance_gateway:
        return NetworkRole.ENTRANCE

    return NetworkRole.INNER
