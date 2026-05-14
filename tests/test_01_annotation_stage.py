from __future__ import annotations

import unittest

from modules.security.annotated_routes import annotate_route
from pipelines.simulation import RouteAnnotationStage
from tests.builders import make_contact, make_route, make_routing_batch_result, make_topology


class RouteAnnotationStageTests(unittest.TestCase):
    def test_annotate_marks_boundary_crossings_and_gateway_nodes(self) -> None:
        """Proves annotation derives node paths, network crossings, and gateway nodes."""
        topology = make_topology({1: (1, 2), 2: (3, 4), 3: (5,)})
        route = make_route(
            (
                make_contact(1, 2),
                make_contact(2, 3),
                make_contact(3, 4),
                make_contact(4, 5),
            )
        )
        routing = make_routing_batch_result(
            topology=topology,
            pairs=((1, 5),),
            routes_by_pair={(1, 5): (route,)},
            contact_plan_size=9,
        )

        result = RouteAnnotationStage().annotate(routing)
        annotated = result.annotated_routes_by_pair[(1, 5)][0]

        self.assertEqual(result.pairs, ((1, 5),))
        self.assertEqual(result.contact_plan_size, 9)
        self.assertEqual(annotated.route_id, "route-1")
        self.assertEqual(annotated.node_path, (1, 2, 3, 4, 5))
        self.assertEqual(annotated.network_path, (1, 1, 2, 2, 3))
        self.assertEqual(len(annotated.boundary_crossings), 2)
        self.assertEqual(
            tuple((crossing.exit_node, crossing.entrance_node) for crossing in annotated.boundary_crossings),
            ((2, 3), (4, 5)),
        )
        self.assertEqual(annotated.gateway_nodes, frozenset({2, 3, 4, 5}))

    def test_annotate_route_rejects_empty_routes(self) -> None:
        """Proves the low-level annotator rejects routes without hops."""
        topology = make_topology({1: (1,), 2: (2,)})

        class EmptyRoute:
            def get_hops(self):
                return []

        with self.assertRaisesRegex(ValueError, "route must contain at least one hop"):
            annotate_route(
                EmptyRoute(),
                topology,
                source_node=1,
                destination_node=2,
            )


# if __name__ == "__main__":
#     unittest.main(verbosity=2)
