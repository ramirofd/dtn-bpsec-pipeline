from __future__ import annotations

import unittest

from modules.domain import PlanRef, RouteRef
from modules.security.models import KeyType
from modules.security.models import SecurityModelType
from pipelines.simulation import RoutingStage, SimulationPipeline
from pipelines.routing import RoutingBatchRequest
from tests.builders import make_contact, make_topology, make_scenario


def build_two_nodes_same_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1, 2)}),
        "contact_plan": [make_contact(1, 2)],
    }


def build_two_nodes_cross_network() -> dict[str, object]:
    return {
        "topology": make_topology({1: (1,), 2: (2,)}),
        "contact_plan": [make_contact(1, 2)],
    }


class TwoNodesIntegrationTests(unittest.TestCase):
    def assert_single_key_requirement_by_model(
        self,
        result,
        *,
        pair: tuple[int, int],
        expected_by_model: dict[SecurityModelType, tuple[KeyType, int, int]],
    ) -> None:
        for model, (key_type, source_id, target_id) in expected_by_model.items():
            with self.subTest(model=model.name):
                plan = result.protection.by_plan[PlanRef(RouteRef(pair, 1), model.name)]
                self.assertEqual(len(plan.key_requirements), 1)
                requirement = plan.key_requirements[0]
                self.assertEqual(requirement.key_type, key_type)
                self.assertEqual(requirement.source_id, source_id)
                self.assertEqual(requirement.target_id, target_id)
                self.assertEqual(requirement.local_node, pair[0])

    def test_same_network_route_stays_local_and_edge_to_edge_degenerates(self) -> None:
        """Guide test: a two-node route inside one network has no boundary crossings."""
        data = build_two_nodes_same_network()
        result = SimulationPipeline().run(RoutingBatchRequest(
            make_scenario(data["topology"], data["contact_plan"]),
            num_routes=1,
        ))

        pair = (1, 2)
        annotated_route = result.annotations.by_route[RouteRef(pair, 1)]

        self.assertEqual(result.routes.scenario.pairs, (pair, (2, 1)))
        self.assertEqual(annotated_route.node_path, (1, 2))
        self.assertEqual(annotated_route.network_path, (1, 1))
        self.assertEqual(annotated_route.boundary_crossings, ())
        self.assertEqual(annotated_route.gateway_nodes, frozenset())
        self.assert_single_key_requirement_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (KeyType.NODE_TO_NODE, 1, 2),
                SecurityModelType.END_TO_END: (KeyType.NODE_TO_NODE, 1, 2),
                SecurityModelType.EDGE_BY_EDGE: (KeyType.NODE_TO_NODE, 1, 2),
                SecurityModelType.EDGE_TO_EDGE: (KeyType.NODE_TO_NODE, 1, 2),
            },
        )

    def test_cross_network_route_marks_one_boundary_and_keeps_gateway_nodes(self) -> None:
        """Guide test: a two-node route across networks records one boundary crossing."""
        data = build_two_nodes_cross_network()
        result = SimulationPipeline().run(RoutingBatchRequest(
            make_scenario(data["topology"], data["contact_plan"]),
            num_routes=1,
        ))

        pair = (1, 2)
        annotated_route = result.annotations.by_route[RouteRef(pair, 1)]

        self.assertEqual(annotated_route.node_path, (1, 2))
        self.assertEqual(annotated_route.network_path, (1, 2))
        self.assertEqual(len(annotated_route.boundary_crossings), 1)
        self.assertEqual(
            (
                annotated_route.boundary_crossings[0].exit_node,
                annotated_route.boundary_crossings[0].entrance_node,
            ),
            (1, 2),
        )
        self.assertEqual(annotated_route.gateway_nodes, frozenset({1, 2}))
        self.assert_single_key_requirement_by_model(
            result,
            pair=pair,
            expected_by_model={
                SecurityModelType.HOP_BY_HOP: (KeyType.NODE_TO_NODE, 1, 2),
                SecurityModelType.END_TO_END: (KeyType.NODE_TO_NODE, 1, 2),
                SecurityModelType.EDGE_BY_EDGE: (KeyType.GROUP_TO_GROUP, 1, 2),
                SecurityModelType.EDGE_TO_EDGE: (KeyType.GROUP_TO_GROUP, 1, 2),
            },
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
