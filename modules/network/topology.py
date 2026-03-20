from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

logger = logging.getLogger(__name__)


class TopologyError(Exception):
    """Base exception for topology operations."""


class TopologyFormatError(TopologyError):
    """Raised when the topology payload format is invalid."""


class TopologyValidationError(TopologyError):
    """Raised when topology validation fails."""


class NodeNotFoundError(TopologyError):
    """Raised when a node is not present in topology."""


class NetworkNotFoundError(TopologyError):
    """Raised when a network is not present in topology."""


class TopologyNetworkEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    nodes: list[int]

    @model_validator(mode="after")
    def validate_entry(self) -> TopologyNetworkEntry:
        if self.id <= 0:
            raise ValueError("network id must be > 0")
        if not self.nodes:
            raise ValueError(f"network {self.id} must include at least one node")
        if any(node <= 0 for node in self.nodes):
            raise ValueError(f"network {self.id} contains node ids <= 0")
        if len(set(self.nodes)) != len(self.nodes):
            raise ValueError(f"network {self.id} has duplicate nodes")
        return self


class TopologyDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    networks: list[TopologyNetworkEntry]

    @model_validator(mode="after")
    def validate_document(self) -> TopologyDocument:
        network_ids = [network.id for network in self.networks]
        if len(set(network_ids)) != len(network_ids):
            raise ValueError("topology has duplicate network ids")

        owner_by_node: dict[int, int] = {}
        for network in self.networks:
            for node_id in network.nodes:
                if node_id in owner_by_node:
                    raise ValueError(
                        f"node {node_id} appears in multiple networks: "
                        f"{owner_by_node[node_id]} and {network.id}"
                    )
                owner_by_node[node_id] = network.id

        return self


@dataclass(slots=True, frozen=True)
class Topology(Mapping[int, int]):
    node_to_network: dict[int, int]
    network_to_nodes: dict[int, frozenset[int]]

    @classmethod
    def from_json_file(cls, file_name: str) -> Topology:
        with open(file_name, "r", encoding="utf-8") as tf:
            payload = json.load(tf)

        document = _parse_topology_payload(payload)
        topology = cls.from_document(document)
        logger.info(
            "topology.load | file=%s networks=%d nodes=%d",
            file_name,
            len(topology.network_to_nodes),
            len(topology.node_to_network),
        )
        return topology

    @classmethod
    def from_document(cls, document: TopologyDocument) -> Topology:
        network_to_nodes: dict[int, frozenset[int]] = {}
        node_to_network: dict[int, int] = {}

        for network in document.networks:
            node_set = frozenset(network.nodes)
            network_to_nodes[network.id] = node_set
            for node_id in node_set:
                node_to_network[node_id] = network.id

        return cls(node_to_network=node_to_network, network_to_nodes=network_to_nodes)

    def get_network_for_node(self, node_id: int) -> int:
        return self[node_id]

    def get_nodes_for_network(self, network_id: int) -> frozenset[int]:
        nodes = self.network_to_nodes.get(network_id)
        if nodes is None:
            raise NetworkNotFoundError(f"network {network_id} is not present in topology")
        return nodes

    def node_exists(self, node_id: int) -> bool:
        return node_id in self

    def network_exists(self, network_id: int) -> bool:
        return network_id in self.network_to_nodes

    def are_in_same_network(self, node_a: int, node_b: int) -> bool:
        return self[node_a] == self[node_b]

    def __getitem__(self, node_id: int) -> int:
        network_id = self.node_to_network.get(node_id)
        if network_id is None:
            raise NodeNotFoundError(f"node {node_id} is not present in topology")
        return network_id

    def __iter__(self) -> Iterator[int]:
        return iter(self.node_to_network)

    def __len__(self) -> int:
        return len(self.node_to_network)

    def __contains__(self, node_id: object) -> bool:
        return node_id in self.node_to_network

    def get(self, node_id: int, default: int | None = None) -> int | None:
        return self.node_to_network.get(node_id, default)


def _parse_topology_payload(payload: Any) -> TopologyDocument:
    try:
        if isinstance(payload, list):
            return TopologyDocument.model_validate({"networks": payload})
        if isinstance(payload, dict):
            return TopologyDocument.model_validate(payload)
        raise TopologyFormatError("Invalid topology JSON format: expected a list or object with 'networks'.")
    except ValidationError as exc:
        raise TopologyValidationError(f"Invalid topology JSON: {exc}") from exc


def topology_load(file_name: str) -> Topology:
    return Topology.from_json_file(file_name)
