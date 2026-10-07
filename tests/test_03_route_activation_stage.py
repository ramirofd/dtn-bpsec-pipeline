from __future__ import annotations

from dataclasses import replace
import unittest

from modules.domain import PlanRef, RouteRef
from modules.security.keys import KeyScope
from modules.security.models import KeyType, SecurityModelType
from pipelines.activation import ActivationPlanner, ActivationSolution, build_trace
from pipelines.catalogs import AnnotationCatalog, ProtectionCatalog, RouteCatalog
from tests.builders import make_topology
from tests.test_06_node_key_distribution import make_catalog


class ActivationPlannerTests(unittest.TestCase):
    def test_deduplicates_scopes_but_preserves_operation_identity(self):
        catalog = make_catalog(make_topology({10: (1, 2, 3)}), {
            (1, 3): [(1, 2, 3)], (3, 1): [(3, 2, 1)], (2, 1): [],
        })
        problem = ActivationPlanner().build(
            catalog.protection, policy_id=SecurityModelType.HOP_BY_HOP.name, symmetric_keys=True,
        )
        self.assertEqual(len(problem.requirements), 2)
        self.assertEqual(len(problem.key_scopes), 2)
        self.assertEqual(problem.routes_by_pair[(2, 1)], ())
        self.assertEqual(len(problem.pairs), 3)
        operation_refs = [ref for requirement in problem.requirements.values() for ref in requirement.operation_refs]
        self.assertEqual(len(operation_refs), len(set(operation_refs)))
        self.assertEqual(len(set(map(str, operation_refs))), 4)
        for ref, requirement in problem.requirements.items():
            self.assertEqual(requirement.ref, ref)
            self.assertEqual(len(requirement.required_key_scopes), 2)
            self.assertTrue(all(operation.plan == PlanRef(ref, problem.policy_id)
                                for operation in requirement.operation_refs))

    def test_problem_is_deeply_read_only_and_unknown_policy_is_rejected(self):
        catalog = make_catalog(make_topology({10: (1, 2)}), {(1, 2): [(1, 2)]})
        with self.assertRaisesRegex(ValueError, "unknown protection policy"):
            ActivationPlanner().build(catalog.protection, policy_id="unknown")
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        ref = RouteRef((1, 2), 1)
        with self.assertRaises(TypeError):
            problem.requirements[ref] = problem.requirements[ref]
        with self.assertRaises(TypeError):
            problem.requirements[ref].required_keys_by_node[1] = ()
        with self.assertRaises(TypeError):
            problem.routes_by_key[problem.key_scopes[0]] = ()

    def test_trace_follows_references_after_independent_catalog_reordering(self):
        catalog = make_catalog(make_topology({1: (1, 2), 2: (3, 4), 3: (5,)}), {
            (1, 4): [(1, 2, 3, 4), (1, 5, 4)], (4, 1): [(4, 3, 2, 1)],
        })
        routes = RouteCatalog(catalog.routes.scenario, dict(reversed(tuple(catalog.routes.by_id.items()))))
        annotations = AnnotationCatalog(routes, dict(reversed(tuple(catalog.annotations.by_route.items()))))
        protection = ProtectionCatalog(annotations, catalog.protection.policies,
                                       dict(reversed(tuple(catalog.protection.by_plan.items()))))
        problem = ActivationPlanner().build(protection, policy_id="EDGE_BY_EDGE")
        selected = RouteRef((1, 4), 1)
        needed_keys = set(problem.requirements[selected].required_key_scopes)
        solution = ActivationSolution(
            {ref: float(ref == selected) for ref in reversed(tuple(problem.requirements))},
            {scope: float(scope in needed_keys) for scope in reversed(problem.key_scopes)},
        )
        trace = build_trace(problem, solution)
        self.assertEqual(trace.selected_route_ids, ("1->4:route-1",))
        route = trace.routes[0]
        self.assertEqual(route.node_path, (1, 2, 3, 4))
        self.assertEqual(route.network_path, (1, 1, 2, 2))
        self.assertEqual(route.boundary_crossings[0].hop_index, 1)
        self.assertEqual((route.contacts[1].from_node, route.contacts[1].to_node), (2, 3))
        boundary_operation = route.operations[1]
        self.assertEqual(boundary_operation.selected_key_scope, KeyScope(KeyType.GROUP_TO_GROUP, 1, 2))
        self.assertEqual(boundary_operation.covered_contacts, (route.contacts[1],))
        group_key = next(key for key in trace.keys if key.scope == boundary_operation.selected_key_scope)
        self.assertEqual(group_key.route_ids, trace.selected_route_ids)
        self.assertEqual(group_key.operation_ids, (boundary_operation.operation_id,))

    def test_trace_keeps_raw_and_normalized_scopes_in_symmetric_mode(self):
        catalog = make_catalog(make_topology({1: (1, 2)}), {(2, 1): [(2, 1)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END", symmetric_keys=True)
        trace = build_trace(problem, ActivationSolution(
            {ref: 1 for ref in problem.requirements}, {scope: 1 for scope in problem.key_scopes},
        ))
        self.assertEqual(trace.selected_key_scopes, (KeyScope(KeyType.NODE_TO_NODE, 1, 2),))
        self.assertEqual(trace.routes[0].operations[0].raw_key_scope, KeyScope(KeyType.NODE_TO_NODE, 2, 1))
        self.assertEqual(trace.routes[0].operations[0].selected_key_scope, trace.selected_key_scopes[0])

    def test_invalid_solutions_fail_before_building_a_trace(self):
        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        selected = {ref: 1 for ref in problem.requirements}
        keys = {scope: 1 for scope in problem.key_scopes}
        with self.assertRaisesRegex(ValueError, "route references"):
            build_trace(problem, ActivationSolution({}, keys))
        with self.assertRaisesRegex(ValueError, "unselected keys"):
            build_trace(problem, ActivationSolution(selected, {scope: 0 for scope in keys}))
        with self.assertRaisesRegex(ValueError, "finite"):
            ActivationSolution({ref: float("nan") for ref in selected}, keys)
        with self.assertRaisesRegex(ValueError, "threshold"):
            ActivationSolution(selected, keys, threshold=1)

    def test_unknown_recipients_and_inconsistent_incidence_are_rejected(self):
        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        ref, requirement = next(iter(problem.requirements.items()))
        for changes, message in (
            ({"required_keys_by_node": {}}, "incomplete or inconsistent"),
            ({"required_keys_by_node": {9: requirement.required_key_scopes}}, "unknown key recipient"),
            ({"operation_scopes": {}}, "inconsistent operation"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                replace(problem, requirements={ref: replace(requirement, **changes)})
        with self.assertRaisesRegex(ValueError, "absent from the catalog"):
            replace(problem, key_scopes=())

    def test_operation_scopes_cannot_be_swapped_even_when_the_key_union_matches(self):
        catalog = make_catalog(make_topology({1: (1, 2, 3)}), {(1, 3): [(1, 2, 3)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="HOP_BY_HOP")
        ref, requirement = next(iter(problem.requirements.items()))
        first, second = requirement.operation_scopes
        corrupted = replace(requirement, operation_scopes={
            first: requirement.operation_scopes[second], second: requirement.operation_scopes[first],
        })
        with self.assertRaisesRegex(ValueError, "operation key scopes do not match"):
            replace(problem, requirements={ref: corrupted})

    def test_policy_without_security_actions_has_an_empty_key_inventory(self):
        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        ref = PlanRef(RouteRef((1, 2), 1), "END_TO_END")
        plan = replace(catalog.protection.by_plan[ref], operations=(), key_requirements=(), node_requirements=())
        protection = ProtectionCatalog(catalog.annotations, {"END_TO_END": SecurityModelType.END_TO_END}, {ref: plan})
        problem = ActivationPlanner().build(protection, policy_id="END_TO_END")
        self.assertEqual(problem.key_scopes, ())
        trace = build_trace(problem, ActivationSolution({ref.route: 1}, {}))
        self.assertEqual(trace.selected_pairs, ((1, 2),))
        self.assertEqual(trace.routes[0].operations, ())
        self.assertEqual(trace.key_counts_by_node, {1: 0, 2: 0})


if __name__ == "__main__":
    unittest.main()
