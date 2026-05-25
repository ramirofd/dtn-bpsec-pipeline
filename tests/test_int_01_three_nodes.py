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


def build_three_nodes_same_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2, 3)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3)],
    }


def build_three_nodes_enter_foreign_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1,), 2: (2, 3)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3)],
    }


def build_three_nodes_exit_home_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2), 2: (3,)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3)],
    }


def build_three_nodes_transit_foreign_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 3), 2: (2,)}),
        "contact_plan": [make_contact(1, 2), make_contact(2, 3)],
    }


class ThreeNodesIntegrationTests(unittest.TestCase):
    def run_guided_pipeline(self, scenario: dict[str, object]):
        route = make_route(scenario["contact_plan"])
        return SimulationPipeline().run_loaded(
            **scenario,
            security_models=tuple(SecurityModelType),
            curr_time=0,
            num_routes=1,
            routing_algorithm=FixedPairRoutingAlgorithm({(1, 3): (route,)}),
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

    def test_same_network_chain_stays_local_for_edge_models(self) -> None:
        """Guide test: a three-node route inside one network never creates boundaries."""
        pair = (1, 3)
        result = self.run_guided_pipeline(build_three_nodes_same_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.node_path, (1, 2, 3))
        self.assertEqual(annotated_route.network_path, (1, 1, 1))
        self.assertEqual(annotated_route.boundary_crossings, ())
        self.assertEqual(annotated_route.gateway_nodes, frozenset())
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
            },
        )

    def test_entering_foreign_network_splits_boundary_then_remote_segment(self) -> None:
        """Guide test: entering another network creates one boundary plus one remote segment."""
        pair = (1, 3)
        result = self.run_guided_pipeline(build_three_nodes_enter_foreign_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.node_path, (1, 2, 3))
        self.assertEqual(annotated_route.network_path, (1, 2, 2))
        self.assertEqual(
            tuple((crossing.exit_node, crossing.entrance_node) for crossing in annotated_route.boundary_crossings),
            ((1, 2),),
        )
        self.assertEqual(annotated_route.gateway_nodes, frozenset({1, 2}))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.GROUP_TO_GROUP, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
            },
        )

    def test_exiting_home_network_splits_local_segment_then_boundary(self) -> None:
        """Guide test: leaving the home network keeps the first hop local before the boundary."""
        pair = (1, 3)
        result = self.run_guided_pipeline(build_three_nodes_exit_home_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.node_path, (1, 2, 3))
        self.assertEqual(annotated_route.network_path, (1, 1, 2))
        self.assertEqual(
            tuple((crossing.exit_node, crossing.entrance_node) for crossing in annotated_route.boundary_crossings),
            ((2, 3),),
        )
        self.assertEqual(annotated_route.gateway_nodes, frozenset({2, 3}))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 2),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_GROUP, 1, 1, 1),
                    (KeyType.GROUP_TO_GROUP, 1, 2, 2),
                ),
            },
        )

    def test_transiting_foreign_network_collapses_when_route_returns_home(self) -> None:
        """Guide test: leaving and re-entering the home network collapses both edge-based models to N1-N3."""
        pair = (1, 3)
        result = self.run_guided_pipeline(build_three_nodes_transit_foreign_network())
        annotated_route = result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.node_path, (1, 2, 3))
        self.assertEqual(annotated_route.network_path, (1, 2, 1))
        self.assertEqual(
            tuple((crossing.exit_node, crossing.entrance_node) for crossing in annotated_route.boundary_crossings),
            ((1, 2), (2, 3)),
        )
        self.assertEqual(annotated_route.gateway_nodes, frozenset({1, 2, 3}))
        self.assert_key_requirements_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (
                    (KeyType.NODE_TO_NODE, 1, 2, 1),
                    (KeyType.NODE_TO_NODE, 2, 3, 2),
                ),
                SecurityModelType.END_TO_END: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_BY_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
                SecurityModelType.EDGE_TO_EDGE: (
                    (KeyType.NODE_TO_NODE, 1, 3, 1),
                ),
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
