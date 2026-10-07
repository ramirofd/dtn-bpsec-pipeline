from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from modules.domain import ContactSnapshot, RouteRef, Scenario
from pipelines.catalogs import RouteCatalog
from pipelines.routing import CGRYenRouting, RoutingAlgorithm, RoutingBatchRequest, RoutingRequest
from pipelines.simulation import RoutingStage, SimulationPipeline, RouteAnnotationStage, SecurityPlanningStage
from tests.builders import make_contact, make_route, make_scenario, make_topology


class RecordingRoutingAlgorithm(RoutingAlgorithm):
    def __init__(self) -> None:
        self.requests: list[RoutingRequest] = []
        self.returned = []

    def compute_routes(self, request: RoutingRequest):
        self.requests.append(request)
        routes = [make_route((make_contact(request.source, request.destination,
                                          start=request.curr_time, end=request.curr_time + 10),))]
        self.returned.extend(routes)
        return routes


class RoutingStageTests(unittest.TestCase):
    def test_enumerates_pairs_and_forwards_immutable_request(self) -> None:
        topology = make_topology({1: (1, 2), 2: (3,)})
        scenario = make_scenario(topology, [make_contact(1, 3), make_contact(3, 2)])
        algorithm = RecordingRoutingAlgorithm()
        result = RoutingStage(algorithm).compute(RoutingBatchRequest(scenario, curr_time=12, num_routes=4))
        self.assertEqual(scenario.pairs, ((1, 2), (1, 3), (2, 1), (2, 3), (3, 1), (3, 2)))
        self.assertIs(result.scenario, scenario)
        for pair, request in zip(scenario.pairs, algorithm.requests, strict=True):
            self.assertEqual((request.source, request.destination), pair)
            self.assertIs(request.contacts, scenario.contacts)
            self.assertEqual(request.curr_time, 12)
            self.assertEqual(request.num_routes, 4)
            self.assertEqual(result.routes_by_pair[pair], (RouteRef(pair, 1),))

    def test_route_snapshots_do_not_expose_cgr_state(self) -> None:
        scenario = make_scenario(make_topology({1: (1, 2)}), [], pairs=((1, 2),))
        algorithm = RecordingRoutingAlgorithm()
        result = RoutingStage(algorithm).compute(RoutingBatchRequest(scenario))
        snapshot = result.by_id[RouteRef((1, 2), 1)].contacts[0]
        algorithm.returned[0].get_hops()[0].rate = 90
        algorithm.returned[0].get_hops()[0].visited_nodes.append(999)
        self.assertEqual(snapshot.rate, 1)
        self.assertFalse(hasattr(snapshot, 'visited_nodes'))
        with self.assertRaises(FrozenInstanceError):
            snapshot.rate = 7
        with self.assertRaises(TypeError):
            result.by_id[RouteRef((1, 2), 1)] = None

    def test_topology_and_scenario_take_defensive_copies(self) -> None:
        node_membership = {1: 10, 2: 10}
        groups = {10: {1, 2}}
        from modules.network.topology import Topology
        topology = Topology(node_membership, groups)
        node_membership[1] = 99
        groups[10].add(3)
        self.assertEqual(topology[1], 10)
        self.assertEqual(topology.get_nodes_for_network(10), frozenset((1, 2)))
        with self.assertRaises(TypeError):
            topology.node_to_network[1] = 20
        snapshots = [ContactSnapshot.from_contact(make_contact(1, 2))]
        scenario = Scenario(topology, snapshots)
        snapshots.clear()
        self.assertEqual(len(scenario.contacts), 1)

    def test_scenario_rejects_duplicate_pairs_and_mutable_contacts(self) -> None:
        topology = make_topology({1: (1, 2)})
        with self.assertRaisesRegex(ValueError, 'unique'):
            Scenario(topology, (), ((1, 2), (1, 2)))
        with self.assertRaisesRegex(TypeError, 'ContactSnapshot'):
            Scenario(topology, (make_contact(1, 2),))
        self.assertEqual(Scenario(topology, (), ()).pairs, ())

    def test_invalid_limits_fail_before_routing(self) -> None:
        scenario = make_scenario(make_topology({1: (1, 2)}), [])
        for limit in (0, -1, 1.5, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                RoutingBatchRequest(scenario, num_routes=limit)


class RouteLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scenario = make_scenario(make_topology({1: (1, 2, 3, 4)}), [
            make_contact(1, 2), make_contact(2, 4), make_contact(1, 3), make_contact(3, 4)])

    def test_custom_router_default_and_explicit_limit(self) -> None:
        stage = RoutingStage(CGRYenRouting(max_routes=1))
        implicit = stage.compute(RoutingBatchRequest(self.scenario))
        explicit = stage.compute(RoutingBatchRequest(self.scenario, num_routes=2))
        self.assertEqual(len(implicit.routes_by_pair[(1, 4)]), 1)
        self.assertEqual(len(explicit.routes_by_pair[(1, 4)]), 2)
        self.assertEqual(explicit.routes_by_pair[(4, 1)], ())

    def test_batch_limit_is_enforced_for_every_custom_algorithm(self) -> None:
        class ManyRoutes(RoutingAlgorithm):
            def compute_routes(self, request):
                return [make_route((make_contact(request.source, request.destination),)) for _ in range(3)]
        result = RoutingStage(ManyRoutes()).compute(RoutingBatchRequest(self.scenario, num_routes=1))
        self.assertTrue(all(len(refs) == 1 for refs in result.routes_by_pair.values()))

    def test_reusing_scenario_is_deterministic_and_does_not_mutate_it(self) -> None:
        stage = RoutingStage(CGRYenRouting(max_routes=2))
        before = tuple(self.scenario.contacts)
        first = stage.compute(RoutingBatchRequest(self.scenario))
        second = stage.compute(RoutingBatchRequest(self.scenario))
        self.assertEqual(first.by_id, second.by_id)
        self.assertEqual(self.scenario.contacts, before)

    def test_injected_stages_are_used_even_when_falsey(self) -> None:
        called = []
        class InjectedRouting:
            def __bool__(self): return False
            def compute(self, request):
                called.append('routing')
                return RouteCatalog(request.scenario, {})
        class InjectedAnnotation:
            def annotate(self, routes):
                called.append('annotation')
                return RouteAnnotationStage().annotate(routes)
        class InjectedSecurity:
            def build(self, annotations):
                called.append('security')
                return SecurityPlanningStage().build(annotations)
        router = InjectedRouting()
        pipeline = SimulationPipeline(routing=router, annotation=InjectedAnnotation(), security=InjectedSecurity())
        result = pipeline.run(RoutingBatchRequest(self.scenario))
        self.assertIs(pipeline.routing, router)
        self.assertEqual(called, ['routing', 'annotation', 'security'])
        self.assertIs(result.annotations.routes, result.routes)
        self.assertIs(result.protection.annotations, result.annotations)
