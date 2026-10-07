from __future__ import annotations

import unittest
from dataclasses import replace

from modules.domain import ContactSnapshot, PlanRef, RouteCandidate, RouteRef, Scenario
from modules.security.keys import KeyScope
from modules.security.models import KeyType, SecurityModelType
from modules.security.planning import build_protection_plan
from pipelines.activation import ActivationPlanner, ActivationSolution, build_trace
from pipelines.catalogs import RouteCatalog
from pipelines.simulation import RouteAnnotationStage, SecurityPlanningStage, SimulationResult
from tests.builders import make_annotated_route, make_contact, make_route, make_topology


def make_catalog(topology, paths_by_pair):
    """Real security plans over explicitly controlled immutable route candidates."""
    candidates = {}
    all_contacts = []
    for pair, paths in paths_by_pair.items():
        for index, path in enumerate(paths, start=1):
            contacts = tuple(make_contact(src, dst) for src, dst in zip(path, path[1:]))
            ref = RouteRef(pair, index)
            candidates[ref] = RouteCandidate.from_route(ref, make_route(contacts))
            all_contacts.extend(ContactSnapshot.from_contact(contact) for contact in contacts)
    scenario = Scenario(topology, tuple(all_contacts), tuple(paths_by_pair))
    routes = RouteCatalog(scenario, candidates)
    annotations = RouteAnnotationStage().annotate(routes)
    protection = SecurityPlanningStage().build(annotations)
    return SimulationResult(routes, annotations, protection)


class NodeKeyDistributionTests(unittest.TestCase):
    def test_all_schemes_count_both_participants_and_skip_forwarders(self):
        topology = make_topology({10: (1, 2), 20: (3, 4), 30: (5, 6), 40: (7,)})
        result = make_catalog(topology, {(1, 6): [(1, 2, 3, 4, 5, 6)]})
        expected = {
            SecurityModelType.HOP_BY_HOP: {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 1},
            SecurityModelType.END_TO_END: {1: 1, 6: 1},
            SecurityModelType.EDGE_BY_EDGE: {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 1},
            SecurityModelType.EDGE_TO_EDGE: {1: 1, 2: 2, 5: 2, 6: 1},
        }
        for scheme, counts in expected.items():
            with self.subTest(scheme=scheme):
                plan = result.protection.by_plan[PlanRef(RouteRef((1, 6), 1), scheme.name)]
                self.assertEqual(
                    {node: len(scopes) for node, scopes in plan.required_keys_by_node().items()}, counts,
                )

    def test_repeated_actions_and_symmetric_scopes_are_counted_once(self):
        topology = make_topology({10: (1, 2)})
        route = make_annotated_route(
            topology, source_node=2, destination_node=1, contacts=(make_contact(2, 1),),
        )
        plan = build_protection_plan(SecurityModelType.END_TO_END, route)
        plan = replace(plan, node_requirements=plan.node_requirements * 2)
        normalized = KeyScope(KeyType.NODE_TO_NODE, 1, 2)
        self.assertEqual(plan.required_keys_by_node(symmetric_keys=True), {
            1: (normalized,), 2: (normalized,),
        })
        self.assertEqual(plan.key_requirements[0].source_id, 2)

    def test_trace_uses_union_across_routes_and_reports_idle_nodes(self):
        topology = make_topology({10: (1, 2, 3, 4)})
        result = make_catalog(topology, {(1, 3): [(1, 2, 3)], (3, 1): [(3, 2, 1)]})
        problem = ActivationPlanner().build(
            result.protection, policy_id=SecurityModelType.HOP_BY_HOP.name, symmetric_keys=True,
        )
        solution = ActivationSolution(
            {ref: 1.0 for ref in problem.requirements}, {scope: 1.0 for scope in problem.key_scopes},
        )
        trace = build_trace(problem, solution)
        self.assertEqual(trace.key_counts_by_node, {1: 1, 2: 2, 3: 1, 4: 0})
        self.assertEqual(trace.max_keys_per_node, 2)
        self.assertEqual(len(trace.selected_key_scopes), 2)
        self.assertEqual(trace.keys[0].node_ids, (1, 2))

    def test_same_group_scope_has_route_specific_recipients(self):
        topology = make_topology({10: (1, 2, 5), 20: (3, 4, 6)})
        result = make_catalog(topology, {(1, 4): [(1, 2, 3, 4), (1, 5, 6, 4)]})
        problem = ActivationPlanner().build(
            result.protection, policy_id=SecurityModelType.EDGE_TO_EDGE.name,
        )
        scope = KeyScope(KeyType.GROUP_TO_GROUP, 10, 20)
        recipients = [
            {node for node, scopes in requirement.required_keys_by_node.items() if scope in scopes}
            for requirement in problem.requirements.values()
        ]
        self.assertEqual(recipients, [{2, 3}, {5, 6}])


if __name__ == "__main__":
    unittest.main()
