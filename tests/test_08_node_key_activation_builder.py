from __future__ import annotations

import unittest

try:
    import gurobipy as gp
except ImportError:
    gp = None

from modules.domain import RouteRef
from pipelines.activation import (
    ActivationPlanner, attach_global_activation, attach_node_deliveries, build_trace, extract_solution,
)
from tests.builders import make_topology
from tests.test_06_node_key_distribution import make_catalog


@unittest.skipIf(gp is None, "optional gurobipy dependency is not installed")
class ActivationBindingsTests(unittest.TestCase):
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

    def setUp(self):
        catalog = make_catalog(make_topology({10: (1, 2, 3, 4)}), {
            (1, 3): [(1, 2, 3)], (3, 1): [(3, 2, 1)],
        })
        self.problem = ActivationPlanner().build(
            catalog.protection, policy_id="HOP_BY_HOP", symmetric_keys=True,
        )
        self.first, self.second = self.problem.requirements

    def test_deliveries_are_exact_unions_without_minimizing_keys(self):
        for selected_a, selected_b, expected in (
            (0, 0, {1: 0, 2: 0, 3: 0, 4: 0}),
            (1, 0, {1: 1, 2: 2, 3: 1, 4: 0}),
            (0, 1, {1: 1, 2: 2, 3: 1, 4: 0}),
            (1, 1, {1: 1, 2: 2, 3: 1, 4: 0}),
        ):
            with self.subTest(selected=(selected_a, selected_b)), gp.Model(env=self.env) as model:
                activation = attach_global_activation(model, self.problem)
                deliveries = attach_node_deliveries(activation)
                for ref, value in ((self.first, selected_a), (self.second, selected_b)):
                    activation.route_vars[ref].LB = value
                    activation.route_vars[ref].UB = value
                model.setObjective(gp.quicksum(deliveries.node_key_vars.values()), gp.GRB.MAXIMIZE)
                model.optimize()
                self.assertEqual(model.Status, gp.GRB.OPTIMAL)
                self.assertEqual({node: round(load.getValue()) for node, load in deliveries.node_key_loads.items()}, expected)
                self.assertEqual({round(var.X) for var in activation.key_vars.values()}, {max(selected_a, selected_b)})
                solution = extract_solution(activation)
            # Detached data remains usable after the solver has been disposed.
            self.assertEqual(build_trace(self.problem, solution).key_counts_by_node, expected)

    def test_node_composition_preserves_objective_and_supports_external_budgets(self):
        catalog = make_catalog(make_topology({10: (1, 2, 3, 4)}), {
            (1, 2): [(1, 2)], (2, 3): [(2, 3)],
        })
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        with gp.Model(env=self.env) as model:
            benefit = model.addVar(lb=0, ub=1, name="benefit")
            model.setObjective(7 * benefit + 3, gp.GRB.MAXIMIZE)
            activation = attach_global_activation(model, problem)
            deliveries = attach_node_deliveries(activation)
            model.addConstr(deliveries.node_key_loads[3] <= 0)
            model.addConstr(activation.route_vars[RouteRef((1, 2), 1)] == 1)
            model.optimize()
            self.assertEqual(model.Status, gp.GRB.OPTIMAL)
            self.assertEqual(model.ModelSense, gp.GRB.MAXIMIZE)
            self.assertEqual(model.ObjVal, 10)
            self.assertEqual(round(activation.route_vars[RouteRef((2, 3), 1)].X), 0)
            self.assertEqual(deliveries.node_key_loads[4].getValue(), 0)

    def test_global_implication_and_exact_modes_have_distinct_semantics(self):
        for exact in (False, True):
            with self.subTest(exact=exact), gp.Model(env=self.env) as model:
                activation = attach_global_activation(model, self.problem, exact_keys=exact)
                for var in activation.route_vars.values():
                    var.UB = 0
                for var in activation.key_vars.values():
                    var.LB = 1
                model.optimize()
                self.assertEqual(model.Status, gp.GRB.INFEASIBLE if exact else gp.GRB.OPTIMAL)

    def test_existing_variables_are_reused_without_orphan_variables(self):
        with gp.Model(env=self.env) as model:
            routes = {ref: model.addVar(vtype=gp.GRB.BINARY) for ref in self.problem.requirements}
            keys = {scope: model.addVar(vtype=gp.GRB.BINARY) for scope in self.problem.key_scopes}
            activation = attach_global_activation(model, self.problem, route_vars=routes, key_vars=keys)
            self.assertEqual(model.NumVars, len(routes) + len(keys))
            for ref, var in routes.items():
                self.assertIs(activation.route_vars[ref], var)
            for scope, var in keys.items():
                self.assertIs(activation.key_vars[scope], var)

    def test_partial_variables_only_add_missing_handles(self):
        with gp.Model(env=self.env) as model:
            first = model.addVar(vtype=gp.GRB.BINARY)
            activation = attach_global_activation(model, self.problem, route_vars={self.first: first})
            self.assertIs(activation.route_vars[self.first], first)
            self.assertEqual(model.NumVars, len(self.problem.requirements) + len(self.problem.key_scopes))

    def test_invalid_variable_mappings_do_not_attach_components(self):
        with gp.Model(env=self.env) as model:
            existing = model.addVar(vtype=gp.GRB.BINARY)
            model.update()
            cases = (
                ({"route_vars": {RouteRef((1, 4), 1): existing}}, "unknown route"),
                ({"route_vars": {self.first: existing}, "create_missing_vars": False}, "missing route"),
                ({"route_vars": {self.first: existing, self.second: existing}}, "distinct solver"),
            )
            for kwargs, message in cases:
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    attach_global_activation(model, self.problem, **kwargs)
                model.update()
                self.assertEqual(model.NumVars, 1)
                self.assertEqual(model.NumConstrs, 0)
        with gp.Model(env=self.env) as model:
            continuous = model.addVar()
            with self.assertRaisesRegex(ValueError, "binary"):
                attach_global_activation(model, self.problem, route_vars={self.first: continuous})
            model.update()
            self.assertEqual(model.NumVars, 1)
            self.assertEqual(model.NumConstrs, 0)

    def test_supplied_variables_must_belong_to_target_model(self):
        with gp.Model(env=self.env) as source, gp.Model(env=self.env) as target:
            foreign = source.addVar(vtype=gp.GRB.BINARY)
            source.update()
            with self.assertRaisesRegex(ValueError, "target model"):
                attach_global_activation(target, self.problem, route_vars={self.first: foreign})
            target.update()
            self.assertEqual(target.NumVars, 0)
            self.assertEqual(target.NumConstrs, 0)

    def test_exact_key_component_is_reused_when_adding_deliveries(self):
        with gp.Model(env=self.env) as model:
            activation = attach_global_activation(model, self.problem, exact_keys=True)
            deliveries = attach_node_deliveries(activation)
            for scope, constraint in activation.key_usage_constraints.items():
                self.assertIs(deliveries.key_usage_constraints[scope], constraint)
            self.assertEqual(model.NumVars, len(activation.route_vars) + len(activation.key_vars)
                             + len(deliveries.node_key_vars))

    def test_extraction_requires_a_feasible_incumbent(self):
        with gp.Model(env=self.env) as model:
            activation = attach_global_activation(model, self.problem)
            with self.assertRaisesRegex(ValueError, "no feasible solution"):
                extract_solution(activation)


if __name__ == "__main__":
    unittest.main()
