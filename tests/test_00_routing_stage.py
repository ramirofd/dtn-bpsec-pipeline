from __future__ import annotations

import unittest

from pipelines.routing import CGRYenRouting, RoutingAlgorithm, RoutingRequest
from pipelines.simulation import RoutingStage
from tests.builders import make_contact, make_route, make_topology


class RecordingRoutingAlgorithm(RoutingAlgorithm):
    def __init__(self) -> None:
        self.requests: list[RoutingRequest] = []

    def compute_routes(self, request: RoutingRequest):
        self.requests.append(request)
        return [
            make_route(
                (
                    make_contact(
                        request.source,
                        request.destination,
                        start=request.curr_time,
                        end=request.curr_time + 10,
                    ),
                )
            )
        ]


class RoutingStageTests(unittest.TestCase):
    def test_compute_enumerates_ordered_pairs_and_preserves_batch_metadata(self) -> None:
        """Proves routing iterates every ordered node pair and preserves request metadata."""
        topology = make_topology({1: (1, 2), 2: (3,)})
        contact_plan = [make_contact(1, 3), make_contact(3, 2)]
        algorithm = RecordingRoutingAlgorithm()

        result = RoutingStage(routing_algorithm=algorithm, default_num_routes=5).compute(
            topology=topology,
            contact_plan=contact_plan,
            curr_time=12,
            num_routes=4,
        )

        self.assertEqual(
            result.pairs,
            ((1, 2), (1, 3), (2, 1), (2, 3), (3, 1), (3, 2)),
        )
        self.assertEqual(result.contact_plan_size, 2)
        self.assertEqual(set(result.routes_by_pair), set(result.pairs))
        self.assertEqual(len(algorithm.requests), len(result.pairs))

        for pair, request in zip(result.pairs, algorithm.requests, strict=True):
            self.assertEqual((request.source, request.destination), pair)
            self.assertIs(request.topology, topology)
            self.assertIs(request.contact_plan, contact_plan)
            self.assertEqual(request.curr_time, 12)
            self.assertEqual(request.num_routes, 4)

    def test_compute_leaves_route_limit_unset_when_num_routes_is_omitted(self) -> None:
        """Proves custom routing algorithms can use their own default limit."""
        topology = make_topology({1: (1,), 2: (2,)})
        contact_plan = [make_contact(1, 2)]
        algorithm = RecordingRoutingAlgorithm()

        RoutingStage(routing_algorithm=algorithm, default_num_routes=7).compute(
            topology=topology,
            contact_plan=contact_plan,
            curr_time=0,
        )

        self.assertEqual([request.num_routes for request in algorithm.requests], [None, None])


class SimulationPipelineRouteLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topology = make_topology({1: (1, 2, 3, 4)})
        self.contact_plan = [
            make_contact(1, 2),
            make_contact(2, 4),
            make_contact(1, 3),
            make_contact(3, 4),
        ]

    def test_compute_uses_custom_router_limit_when_num_routes_is_omitted(self) -> None:
        """Proves a custom router's configured limit applies when no override is passed."""
        result = RoutingStage(
            routing_algorithm=CGRYenRouting(max_routes=1)
        ).compute(
            topology=self.topology,
            contact_plan=self.contact_plan,
            curr_time=0,
        )

        self.assertEqual(len(result.routes_by_pair[(1, 4)]), 1)

    def test_compute_explicit_num_routes_overrides_custom_router_limit(self) -> None:
        """Proves the per-run override still wins when explicitly requested."""
        result = RoutingStage(
            routing_algorithm=CGRYenRouting(max_routes=1)
        ).compute(
            topology=self.topology,
            contact_plan=self.contact_plan,
            curr_time=0,
            num_routes=2,
        )

        self.assertEqual(len(result.routes_by_pair[(1, 4)]), 2)


# if __name__ == "__main__":
#     unittest.main(verbosity=2)
