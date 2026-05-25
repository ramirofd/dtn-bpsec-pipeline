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


TOPOLOGY = make_topology(
    {
        1: (1, 2, 3, 4, 5),
        2: (6, 7, 8, 11, 14),
        3: (9, 10, 12, 13),
    }
)


ROUTE_NODE_PATHS: dict[str, tuple[int, ...]] = {
    "R1": (1, 2, 11, 7, 8, 9, 10),
    "R2": (4, 1, 2, 6, 7, 8, 9, 10),
    "R3": (3, 7, 12, 9, 8),
    "R4": (14, 7, 8, 9, 10, 13),
    "R5": (13, 12, 7, 3, 4, 5),
    "R6": (10, 9, 8, 7, 14),
}


def build_contact_plan() -> list[object]:
    seen_edges: set[tuple[int, int]] = set()
    contacts: list[object] = []

    for node_path in ROUTE_NODE_PATHS.values():
        for frm, to in zip(node_path, node_path[1:], strict=False):
            edge = (frm, to)
            if edge in seen_edges:
                continue
            seen_edges.add(edge)
            contacts.append(make_contact(frm, to))

    return contacts


def make_route_from_nodes(node_path: tuple[int, ...]):
    return make_route(
        tuple(
            make_contact(frm, to)
            for frm, to in zip(node_path, node_path[1:], strict=False)
        )
    )


def build_route_specs(route_names: tuple[str, ...]) -> dict[str, dict[str, object]]:
    specs: dict[str, dict[str, object]] = {}
    for route_name in route_names:
        node_path = ROUTE_NODE_PATHS[route_name]
        pair = (node_path[0], node_path[-1])
        specs[route_name] = {
            "pair": pair,
            "node_path": node_path,
            "route": make_route_from_nodes(node_path),
        }
    return specs


def build_pipeline_input(route_names: tuple[str, ...]) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    route_specs = build_route_specs(route_names)
    routes_by_pair = {
        spec["pair"]: (spec["route"],)
        for spec in route_specs.values()
    }
    return (
        {
            "topology": TOPOLOGY,
            "contact_plan": build_contact_plan(),
            "routing_algorithm": FixedPairRoutingAlgorithm(routes_by_pair),
            "security_models": tuple(SecurityModelType),
            "curr_time": 0,
            "num_routes": 1,
        },
        route_specs,
    )


# The expectations below intentionally mirror the image verbatim, including
# the surprising `N1-G1` prefix shown for R2.
EXPECTED_KEY_SCOPES_BY_ROUTE: dict[str, dict[SecurityModelType, tuple[tuple[KeyType, int, int], ...]]] = {
    "R1": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 1, 2),
            (KeyType.NODE_TO_NODE, 2, 11),
            (KeyType.NODE_TO_NODE, 11, 7),
            (KeyType.NODE_TO_NODE, 7, 8),
            (KeyType.NODE_TO_NODE, 8, 9),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 1, 10),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.NODE_TO_GROUP, 1, 1),
            (KeyType.GROUP_TO_GROUP, 1, 2),
            (KeyType.NODE_TO_GROUP, 11, 2),
            (KeyType.GROUP_TO_GROUP, 2, 3),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.NODE_TO_GROUP, 1, 1),
            (KeyType.GROUP_TO_GROUP, 1, 3),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
    },
    "R2": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 4, 1),
            (KeyType.NODE_TO_NODE, 1, 2),
            (KeyType.NODE_TO_NODE, 2, 6),
            (KeyType.NODE_TO_NODE, 6, 7),
            (KeyType.NODE_TO_NODE, 7, 8),
            (KeyType.NODE_TO_NODE, 8, 9),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 4, 10),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.NODE_TO_GROUP, 4, 1),
            (KeyType.GROUP_TO_GROUP, 1, 2),
            (KeyType.NODE_TO_GROUP, 6, 2),
            (KeyType.GROUP_TO_GROUP, 2, 3),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.NODE_TO_GROUP, 4, 1),
            (KeyType.GROUP_TO_GROUP, 1, 3),
            (KeyType.NODE_TO_NODE, 9, 10),
        ),
    },
    "R3": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 3, 7),
            (KeyType.NODE_TO_NODE, 7, 12),
            (KeyType.NODE_TO_NODE, 12, 9),
            (KeyType.NODE_TO_NODE, 9, 8),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 3, 8),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.GROUP_TO_GROUP, 1, 2),
            (KeyType.NODE_TO_NODE, 7, 8),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.GROUP_TO_GROUP, 1, 2),
            (KeyType.NODE_TO_NODE, 7, 8),
        ),
    },
    "R4": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 14, 7),
            (KeyType.NODE_TO_NODE, 7, 8),
            (KeyType.NODE_TO_NODE, 8, 9),
            (KeyType.NODE_TO_NODE, 9, 10),
            (KeyType.NODE_TO_NODE, 10, 13),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 14, 13),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.NODE_TO_GROUP, 14, 2),
            (KeyType.GROUP_TO_GROUP, 2, 3),
            (KeyType.NODE_TO_NODE, 9, 13),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.NODE_TO_GROUP, 14, 2),
            (KeyType.GROUP_TO_GROUP, 2, 3),
            (KeyType.NODE_TO_NODE, 9, 13),
        ),
    },
    "R5": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 13, 12),
            (KeyType.NODE_TO_NODE, 12, 7),
            (KeyType.NODE_TO_NODE, 7, 3),
            (KeyType.NODE_TO_NODE, 3, 4),
            (KeyType.NODE_TO_NODE, 4, 5),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 13, 5),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.NODE_TO_GROUP, 13, 3),
            (KeyType.GROUP_TO_GROUP, 3, 2),
            (KeyType.GROUP_TO_GROUP, 2, 1),
            (KeyType.NODE_TO_NODE, 3, 5),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.NODE_TO_GROUP, 13, 3),
            (KeyType.GROUP_TO_GROUP, 3, 1),
            (KeyType.NODE_TO_NODE, 3, 5),
        ),
    },
    "R6": {
        SecurityModelType.HOP_BY_HOP: (
            (KeyType.NODE_TO_NODE, 10, 9),
            (KeyType.NODE_TO_NODE, 9, 8),
            (KeyType.NODE_TO_NODE, 8, 7),
            (KeyType.NODE_TO_NODE, 7, 14),
        ),
        SecurityModelType.END_TO_END: (
            (KeyType.NODE_TO_NODE, 10, 14),
        ),
        SecurityModelType.EDGE_BY_EDGE: (
            (KeyType.NODE_TO_GROUP, 10, 3),
            (KeyType.GROUP_TO_GROUP, 3, 2),
            (KeyType.NODE_TO_NODE, 8, 14),
        ),
        SecurityModelType.EDGE_TO_EDGE: (
            (KeyType.NODE_TO_GROUP, 10, 3),
            (KeyType.GROUP_TO_GROUP, 3, 2),
            (KeyType.NODE_TO_NODE, 8, 14),
        ),
    },
}


class RouteCatalogIntegrationTests(unittest.TestCase):
    maxDiff = None

    def assert_route_expectations(
        self,
        result,
        *,
        route_specs: dict[str, dict[str, object]],
        route_names: tuple[str, ...],
    ) -> None:
        for route_name in route_names:
            pair = route_specs[route_name]["pair"]
            annotated_route = result.annotation.annotated_routes_by_pair[pair][0]
            self.assertEqual(
                annotated_route.node_path,
                route_specs[route_name]["node_path"],
                msg=f"{route_name} node_path",
            )

            for model, expected_scopes in EXPECTED_KEY_SCOPES_BY_ROUTE[route_name].items():
                with self.subTest(route=route_name, model=model.name):
                    plan = result.security.plans_by_model[model][pair][0]
                    actual_scopes = tuple(
                        (
                            requirement.key_type,
                            requirement.source_id,
                            requirement.target_id,
                        )
                        for requirement in plan.key_requirements
                    )
                    self.assertEqual(actual_scopes, expected_scopes)

    def test_routes_r1_to_r4_match_image_spec(self) -> None:
        """Guide test: compare the first four catalog routes against the provided key spec."""
        route_names = ("R1", "R2", "R3", "R4")
        pipeline_input, route_specs = build_pipeline_input(route_names)
        result = SimulationPipeline().run_loaded(**pipeline_input)

        self.assert_route_expectations(
            result,
            route_specs=route_specs,
            route_names=route_names,
        )

    def test_routes_r1_to_r6_match_image_spec(self) -> None:
        """Guide test: compare the full six-route catalog against the provided key spec."""
        route_names = ("R1", "R2", "R3", "R4", "R5", "R6")
        pipeline_input, route_specs = build_pipeline_input(route_names)
        result = SimulationPipeline().run_loaded(**pipeline_input)

        self.assert_route_expectations(
            result,
            route_specs=route_specs,
            route_names=route_names,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
