from __future__ import annotations

import unittest

from modules.security.models import KeyType, SecurityModelType
from pipelines.routing import RoutingAlgorithm, RoutingRequest
from pipelines.simulation import SimulationPipeline
from tests.builders import make_contact, make_route, make_topology


class FixedPairRoutingAlgorithm(RoutingAlgorithm):
    def __init__(self, routes_by_pair: dict[tuple[int, int], tuple[object, ...]]) -> None:
        self.routes_by_pair = routes_by_pair

    def compute_routes(self, request: RoutingRequest):
        return list(self.routes_by_pair.get((request.source, request.destination), ()))


def build_four_nodes_same_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2, 3, 4)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_enter_foreign_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1,), 2: (2, 3, 4)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_three_networks_destination_segment() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1,), 2: (2,), 3: (3, 4)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_exit_home_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2, 3), 2: (4,)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_transit_and_return() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 4), 2: (2, 3)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_three_networks_exit_chain() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2), 2: (3,), 3: (4,)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_boundary_then_destination_segment() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2), 2: (3, 4)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


def build_four_nodes_foreign_segment_then_exit() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1,), 2: (2, 3), 3: (4,)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3), make_contact(3, 4)],
    }


class FourNodesIntegrationTests(unittest.TestCase):
    def run_guided_pipeline(self, scenario: dict[str, object]):
        route = make_route(scenario["contact_plan"])
        return SimulationPipeline().run_loaded(
            **scenario,
            security_models=tuple(SecurityModelType),
            curr_time=0,
            num_routes=1,
            routing_algorithm=FixedPairRoutingAlgorithm({(1, 4): (route,)}),
        )

    def assert_key_requirements_by_model(
        self,
        result,
        *,
        pair: tuple[int, int],
        expected_by_model: dict[SecurityModelType, tuple[tuple[KeyType, int, int, int], ...]],
    ) -> None:
        for model, expected_requirements in expected_by_model.items():
            with self.subTest(model=model.name):
                plan = result.security.plans_by_model[model][pair][0]
                actual_requirements = tuple(
                    (
                        requirement.key_type,
                        requirement.source_id,
                        requirement.target_id,
                        requirement.local_node,
                    )
                    for requirement in plan.key_requirements
                )
                self.assertEqual(actual_requirements, expected_requirements)

    def test_same_network_chain(self) -> None:
        """Spec: a single-network four-hop route collapses edge-based keys to N1-N4."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_same_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 1, 1, 1))
        self.assertEqual(annotated_route.boundary_crossings, ())
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
            },
        )

    def test_enter_foreign_network_then_destination_segment(self) -> None:
        """Spec: one boundary plus a destination-local segment."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_enter_foreign_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 2, 2, 2))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 4, 2),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 4, 2),
                ),
            },
        )

    def test_three_networks_with_destination_segment(self) -> None:
        """Spec: edge-by-edge preserves both boundaries; edge-to-edge collapses groups G1-G3."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_three_networks_destination_segment())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 2, 3, 3))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.GROUP_TO_GROUP, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 3, 1),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
            },
        )

    def test_exit_home_network(self) -> None:
        """Spec: a long source-local segment becomes N1-G1 before crossing G1-G2."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_exit_home_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 1, 1, 2))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 3),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 3),
                ),
            },
        )

    def test_transit_and_return_to_source_network(self) -> None:
        """Spec: if the route returns to the source network, both edge-based models collapse to N1-N4."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_transit_and_return())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 2, 2, 1))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
            },
        )

    def test_three_networks_exit_chain(self) -> None:
        """Spec: source-local plus two boundary scopes, then edge-to-edge collapses the last two groups."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_three_networks_exit_chain())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 1, 2, 3))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 2),
                    (KeyType.GROUP_TO_GROUP, 2, 3, 3),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 3, 2),
                ),
            },
        )

    def test_boundary_then_destination_segment(self) -> None:
        """Spec: one boundary followed by a destination-local node-to-node segment."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_boundary_then_destination_segment())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 1, 2, 2))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
            },
        )

    def test_foreign_segment_then_exit(self) -> None:
        """Spec: edge-by-edge keeps the foreign local segment; edge-to-edge collapses transit to G1-G3."""
        pair = (1, 4)
        result = self.run_guided_pipeline(build_four_nodes_foreign_segment_then_exit())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.network_path, (1, 2, 2, 3))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                    (KeyType.NODE_TO_NODE, 3, 4, 3),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 4, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.NODE_TO_GROUP, 2, 2, 2),
                    (KeyType.GROUP_TO_GROUP, 2, 3, 3),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 3, 1),
                ),
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
