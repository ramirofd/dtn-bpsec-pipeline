from __future__ import annotations

import itertools
import math
import unittest

try:
    import gurobipy as gp
except ImportError:
    gp = None

from modules.domain import RouteRef
from modules.security.models import SecurityModelType
from pipelines.activation import ActivationPlanner
from tests.builders import make_topology
from tests.test_06_node_key_distribution import make_catalog


def exhaustive_optimum(result, scheme, target, *, symmetric_keys=False):
    """Independent oracle: count keys at operation endpoints over every route subset."""
    plans = [plan for ref, plan in result.protection.by_plan.items() if ref.policy_id == scheme.name]
    best = math.inf
    for mask in itertools.product((False, True), repeat=len(plans)):
        pairs = set()
        inventories = {node: set() for node in result.routes.scenario.topology}
        for selected, plan in zip(mask, plans):
            if not selected:
                continue
            pairs.add(plan.ref.route.pair)
            for operation in plan.operations:
                source, dest = operation.key_source_id, operation.key_target_id
                if symmetric_keys and operation.required_key_type.name in {"NODE_TO_NODE", "GROUP_TO_GROUP"}:
                    source, dest = sorted((source, dest))
                key = (operation.required_key_type, source, dest)
                inventories[operation.source_node].add(key)
                inventories[operation.acceptor_node].add(key)
        if len(pairs) >= math.ceil(target * len(result.routes.scenario.pairs) / 100):
            best = min(best, max(map(len, inventories.values()), default=0))
    return best


@unittest.skipIf(gp is None, "optional gurobipy dependency is not installed")
class MinMaxNodeKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = gp.Env(empty=True)
        cls.env.setParam("OutputFlag", 0)
        try:
            cls.env.start()
        except gp.GurobiError as error:
            cls.env.dispose()
            raise unittest.SkipTest(f"Gurobi license unavailable: {error}")
        cls.addClassCleanup(cls.env.dispose)

    def test_all_schemes_match_exhaustive_route_subset_search(self):
        from models.model5_min_max_keys_per_node import solve

        topology = make_topology({10: (1, 2), 20: (3, 4), 30: (5, 6), 40: (7,)})
        result = make_catalog(topology, {
            (1, 6): [(1, 3, 6), (1, 4, 6)],
            (2, 5): [(2, 3, 5), (2, 4, 5)],
            (6, 1): [(6, 3, 1)],
        })
        for symmetric in (False, True):
            for scheme in SecurityModelType:
                with self.subTest(scheme=scheme, symmetric=symmetric):
                    problem = ActivationPlanner().build(result.protection, policy_id=scheme.name, symmetric_keys=symmetric)
                    optimization = solve(problem, target_connectivity_pcts=(0, 34, 100), env=self.env)
                    for outcome, row in zip(optimization.outcomes, optimization.to_frame().itertuples()):
                        self.assertTrue(row.is_optimal)
                        self.assertEqual(row.max_keys_per_node, exhaustive_optimum(
                            result, scheme, row.target_connectivity_pct, symmetric_keys=symmetric,
                        ))
                        self.assertEqual(row.max_keys_per_node, outcome.trace.max_keys_per_node)
                        self.assertEqual(outcome.objective_value, row.max_keys_per_node)
                        self.assertEqual(outcome.trace.key_counts_by_node[7], 0)
                        self.assertEqual(row.total_key_deliveries, sum(outcome.trace.key_counts_by_node.values()))

    def test_routes_split_between_gateways_to_reduce_peak(self):
        from models.model5_min_max_keys_per_node import solve

        result = make_catalog(make_topology({10: (1, 2, 3, 4, 5, 6)}), {
            (1, 6): [(1, 3, 6), (1, 4, 6)],
            (2, 5): [(2, 3, 5), (2, 4, 5)],
        })
        problem = ActivationPlanner().build(result.protection, policy_id="HOP_BY_HOP")
        optimization = solve(problem, env=self.env)
        trace = optimization.traces[0]
        self.assertEqual(optimization.to_frame().iloc[0].max_keys_per_node, 2)
        self.assertEqual(trace.key_counts_by_node[3], 2)
        self.assertEqual(trace.key_counts_by_node[4], 2)
        self.assertEqual(len(trace.selected_route_ids), 2)

    def test_unused_routes_do_not_distribute_shared_group_keys(self):
        from models.model5_min_max_keys_per_node import build

        result = make_catalog(make_topology({10: (1, 2, 5), 20: (3, 4, 6)}), {
            (1, 4): [(1, 2, 3, 4), (1, 5, 6, 4)],
        })
        problem = ActivationPlanner().build(result.protection, policy_id="EDGE_TO_EDGE")
        first, second = RouteRef((1, 4), 1), RouteRef((1, 4), 2)
        plan = result.protection.by_plan[next(ref for ref in result.protection.by_plan
                                             if ref.route == first and ref.policy_id == "EDGE_TO_EDGE")]
        expected = {(operation.source_node, operation.required_key_type, operation.key_source_id, operation.key_target_id)
                    for operation in plan.operations}
        expected.update((operation.acceptor_node, operation.required_key_type, operation.key_source_id, operation.key_target_id)
                        for operation in plan.operations)
        with gp.Model(env=self.env) as model:
            bindings = build(model, problem)
            bindings.activation.route_vars[first].LB = 1
            bindings.activation.route_vars[second].UB = 0
            model.optimize()
            self.assertEqual(model.Status, gp.GRB.OPTIMAL)
            for (node, scope), var in bindings.node_delivery.node_key_vars.items():
                self.assertEqual(round(var.X), int((node, scope.key_type, scope.source_id, scope.target_id) in expected))
            self.assertEqual(bindings.node_delivery.node_key_loads[5].getValue(), 0)
            self.assertEqual(bindings.node_delivery.node_key_loads[6].getValue(), 0)

    def test_unreachable_pairs_are_infeasible_not_zero_cost(self):
        from models.model5_min_max_keys_per_node import solve

        result = make_catalog(make_topology({10: (1, 2)}), {(1, 2): [(1, 2)], (2, 1): []})
        problem = ActivationPlanner().build(result.protection, policy_id="END_TO_END")
        optimization = solve(problem, target_connectivity_pcts=(50, 100), env=self.env)
        frame = optimization.to_frame()
        self.assertIsNotNone(optimization.traces[0])
        self.assertIsNone(optimization.traces[1])
        self.assertIsNone(optimization.outcomes[1].solution)
        self.assertEqual(frame.iloc[1].solver_status, gp.GRB.INFEASIBLE)
        self.assertTrue(math.isnan(frame.iloc[1].max_keys_per_node))
        self.assertFalse(frame.iloc[1].has_solution)

    def test_empty_catalog_and_invalid_targets(self):
        from models.model5_min_max_keys_per_node import solve

        result = make_catalog(make_topology({10: (1,)}), {})
        problem = ActivationPlanner().build(result.protection, policy_id="END_TO_END")
        optimization = solve(problem, env=self.env)
        self.assertEqual(optimization.to_frame().iloc[0].max_keys_per_node, 0)
        self.assertEqual(optimization.traces[0].key_counts_by_node, {1: 0})
        for targets in ((), (-1,), (101,), (float("nan"),), (float("inf"),)):
            with self.subTest(targets=targets), self.assertRaises(ValueError):
                solve(problem, target_connectivity_pcts=targets, env=self.env)


if __name__ == "__main__":
    unittest.main()
