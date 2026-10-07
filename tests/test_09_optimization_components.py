from __future__ import annotations

import itertools
import math
import unittest
from dataclasses import replace
from decimal import Decimal

try:
    import gurobipy as gp
except ImportError:
    gp = None

from models.common.runner import budget_points, connectivity_points
from modules.security.models import SecurityModelType
from pipelines.activation import ActivationPlanner, attach_global_activation, build_trace
from tests.builders import make_topology
from tests.test_06_node_key_distribution import make_catalog


def route_subset_metrics(result, scheme, *, symmetric_keys):
    """Enumerate alternatives from protection operations, without MILP incidences."""
    routes = []
    for ref, plan in result.protection.by_plan.items():
        if ref.policy_id != scheme.name:
            continue
        keys = set()
        for operation in plan.operations:
            source, target = operation.key_source_id, operation.key_target_id
            if symmetric_keys and operation.required_key_type.name in {"NODE_TO_NODE", "GROUP_TO_GROUP"}:
                source, target = sorted((source, target))
            keys.add((operation.required_key_type, source, target))
        routes.append((ref.route.pair, keys))
    metrics = []
    for mask in itertools.product((False, True), repeat=len(routes)):
        pairs, keys = set(), set()
        for selected, (pair, route_keys) in zip(mask, routes):
            if selected:
                pairs.add(pair)
                keys.update(route_keys)
        metrics.append((len(pairs), len(keys), sum(mask)))
    return tuple(metrics)


class SweepValidationTests(unittest.TestCase):
    def test_percentages_round_the_pair_requirement_up_without_premature_division(self):
        self.assertEqual(connectivity_points((55,), 380)[0].required_pairs, 209)
        self.assertEqual(connectivity_points((34,), 3)[0].required_pairs, 2)
        self.assertEqual(connectivity_points((0, 100), 0)[1].required_pairs, 0)

    def test_decimal_percentages_do_not_accidentally_require_an_extra_pair(self):
        self.assertEqual(connectivity_points((4.4,), 750)[0].required_pairs, 33)
        self.assertEqual(connectivity_points((8.8,), 375)[0].required_pairs, 33)
        self.assertEqual(connectivity_points((Decimal("8.8"),), 750)[0].required_pairs, 66)
        self.assertEqual(connectivity_points((4.4001,), 750)[0].required_pairs, 34)

    def test_budgets_are_nonnegative_integers_and_defaults_include_zero(self):
        self.assertEqual(tuple(point.key_budget for point in budget_points(None, 2)), (0, 1, 2))
        for invalid in ((), (-1,), (0.5,), (True,), (float("nan"),), (float("inf"),), ("2",)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                budget_points(invalid, 2)


@unittest.skipIf(gp is None, "optional gurobipy dependency is not installed")
class OptimizationComponentsTests(unittest.TestCase):
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

    def test_models_one_to_four_match_independent_exhaustive_objectives(self):
        from models import model1_max_routes as model1
        from models import model2_min_keys as model2
        from models import model3_min_keys_full_connectivity as model3
        from models import model4_max_connectivity_under_budget as model4

        catalog = make_catalog(make_topology({10: (1, 2), 20: (3, 4), 30: (5, 6)}), {
            (1, 6): [(1, 3, 6), (1, 4, 6)], (6, 1): [(6, 3, 1)],
        })
        for scheme in SecurityModelType:
            for symmetric in (False, True):
                with self.subTest(scheme=scheme, symmetric=symmetric):
                    metrics = route_subset_metrics(catalog, scheme, symmetric_keys=symmetric)
                    available_keys = max(keys for _, keys, _ in metrics)
                    problem = ActivationPlanner().build(catalog.protection, policy_id=scheme.name, symmetric_keys=symmetric)
                    route_maximum = model1.solve(problem, env=self.env)
                    self.assertEqual(len(route_maximum.outcomes), available_keys + 1)
                    for outcome in route_maximum.outcomes:
                        self.assertTrue(outcome.is_optimal)
                        budget = outcome.point.key_budget
                        expected = max(routes for _, keys, routes in metrics if keys <= budget)
                        self.assertEqual(outcome.objective_value, expected)
                        self.assertEqual(len(outcome.trace.selected_route_ids), expected)
                        self.assertLessEqual(len(outcome.trace.selected_key_scopes), budget)
                    minimum_keys = model2.solve(problem, env=self.env)
                    self.assertEqual(tuple(outcome.point.target_connectivity_pct for outcome in minimum_keys.outcomes),
                                     tuple(range(0, 101, 5)))
                    for outcome in minimum_keys.outcomes:
                        self.assertTrue(outcome.is_optimal)
                        required = math.ceil(outcome.point.target_connectivity_pct * 2 / 100)
                        expected = min(keys for pairs, keys, _ in metrics if pairs >= required)
                        self.assertEqual(outcome.objective_value, expected)
                        self.assertEqual(len(outcome.trace.selected_key_scopes), expected)
                        self.assertGreaterEqual(len(outcome.trace.selected_pairs), required)
                    full_coverage = model3.solve(problem, env=self.env)
                    full = full_coverage.outcomes[0]
                    expected_full = min(keys for pairs, keys, _ in metrics if pairs == 2)
                    self.assertTrue(full.is_optimal)
                    self.assertEqual(full.objective_value, expected_full)
                    self.assertEqual(full.objective_value, minimum_keys.outcomes[-1].objective_value)
                    self.assertEqual(len(full.trace.selected_pairs), 2)
                    connectivity = model4.solve(problem, env=self.env)
                    self.assertEqual(len(connectivity.outcomes), available_keys + 1)
                    for outcome in connectivity.outcomes:
                        self.assertTrue(outcome.is_optimal)
                        expected = max((pairs, -keys, routes) for pairs, keys, routes in metrics
                                       if keys <= outcome.point.key_budget)
                        actual = (len(outcome.trace.selected_pairs), -len(outcome.trace.selected_key_scopes),
                                  len(outcome.trace.selected_route_ids))
                        self.assertEqual(actual, expected)

    def test_pair_coverage_is_exact_and_objective_free_including_unreachable_pairs(self):
        from models.common.coverage import attach_pair_coverage

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)], (2, 1): []})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        for selected in (0, 1):
            with self.subTest(selected=selected), gp.Model(env=self.env) as model:
                benefit = model.addVar(lb=0, ub=1)
                model.setObjective(7 * benefit + 3, gp.GRB.MAXIMIZE)
                activation = attach_global_activation(model, problem)
                coverage = attach_pair_coverage(activation)
                ref = next(iter(problem.requirements))
                model.addConstr(activation.route_vars[ref] == selected)
                model.optimize()
                self.assertEqual(model.Status, gp.GRB.OPTIMAL)
                self.assertEqual(model.ModelSense, gp.GRB.MAXIMIZE)
                self.assertEqual(model.ObjVal, 10)
                self.assertEqual(round(coverage.pair_vars[(1, 2)].X), selected)
                self.assertEqual(round(coverage.pair_vars[(2, 1)].X), 0)
                self.assertEqual(round(coverage.covered_pair_count.getValue()), selected)

    def test_every_model_handles_empty_catalogs_and_traces_survive_solver_disposal(self):
        from models import model1_max_routes, model2_min_keys, model3_min_keys_full_connectivity
        from models import model4_max_connectivity_under_budget, model5_min_max_keys_per_node

        catalog = make_catalog(make_topology({1: (1,)}), {})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        for module in (model1_max_routes, model2_min_keys, model3_min_keys_full_connectivity,
                       model4_max_connectivity_under_budget, model5_min_max_keys_per_node):
            with self.subTest(model=module.__name__):
                optimization = module.solve(problem, env=self.env)
                for outcome in optimization.outcomes:
                    self.assertTrue(outcome.is_optimal)
                    self.assertEqual(outcome.objective_value, 0)
                    self.assertEqual(outcome.trace.selected_route_ids, ())
                    self.assertEqual(outcome.trace.keys_by_node, {1: ()})
                    self.assertEqual(build_trace(problem, outcome.solution), outcome.trace)
                frame = optimization.to_frame()
                for column in ("selected_pairs", "selected_routes", "selected_keys", "total_key_deliveries",
                               "max_keys_per_node", "selected_keys_pct_of_available", "achieved_connectivity_pct"):
                    self.assertTrue((frame[column] == 0).all(), column)

    def test_missing_incumbents_have_absent_solution_trace_and_metrics_for_all_formulations(self):
        import pandas as pd
        from models import model1_max_routes, model2_min_keys, model3_min_keys_full_connectivity
        from models import model4_max_connectivity_under_budget, model5_min_max_keys_per_node
        from models.common.runner import run_optimization

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)], (2, 1): []})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        for module in (model1_max_routes, model2_min_keys, model3_min_keys_full_connectivity,
                       model4_max_connectivity_under_budget, model5_min_max_keys_per_node):
            with self.subTest(model=module.__name__):
                if module in (model1_max_routes, model4_max_connectivity_under_budget):
                    # A caller can require one route; a zero-key budget then makes
                    # these otherwise always-feasible maximization models infeasible.
                    def require_one_route(model, activation_problem):
                        bindings = module.build(model, activation_problem)
                        model.addConstr(next(iter(bindings.activation.route_vars.values())) == 1)
                        return bindings
                    optimization = run_optimization(problem, name="infeasible_budget", build=require_one_route,
                                                    points=budget_points((0,), len(problem.key_scopes)), env=self.env)
                elif module is model3_min_keys_full_connectivity:
                    optimization = module.solve(problem, env=self.env)
                else:
                    optimization = module.solve(problem, target_connectivity_pcts=(100,), env=self.env)
                outcome = optimization.outcomes[0]
                self.assertEqual(outcome.solver_status, gp.GRB.INFEASIBLE)
                self.assertFalse(outcome.has_solution)
                self.assertFalse(outcome.is_optimal)
                self.assertIsNone(outcome.solution)
                self.assertIsNone(outcome.trace)
                self.assertIsNone(outcome.objective_value)
                row = optimization.to_frame().iloc[0]
                for column in ("selected_pairs", "selected_routes", "selected_keys", "total_key_deliveries",
                               "max_keys_per_node", "selected_keys_pct_of_available", "achieved_connectivity_pct"):
                    self.assertTrue(pd.isna(row[column]), column)

    def test_nonempty_solution_can_be_reexplained_after_the_runner_disposes_its_model(self):
        from models.model3_min_keys_full_connectivity import solve

        catalog = make_catalog(make_topology({1: (1, 2), 2: (3,)}), {(1, 3): [(1, 2, 3)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="EDGE_BY_EDGE")
        optimization = solve(problem, env=self.env)
        self.assertEqual(build_trace(problem, optimization.outcomes[0].solution), optimization.traces[0])
        self.assertEqual(optimization.traces[0].routes[0].node_path, (1, 2, 3))

    def test_foreign_sweep_constraint_is_rejected_without_mutating_the_other_model(self):
        from models.common.runner import run_optimization
        from models.model1_max_routes import build

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        with gp.Model(env=self.env) as foreign:
            var = foreign.addVar(vtype=gp.GRB.BINARY)
            foreign_constraint = foreign.addConstr(var <= 0)
            foreign.update()

            def incorrect_builder(model, activation_problem):
                return replace(build(model, activation_problem), sweep_constraint=foreign_constraint)

            with self.assertRaisesRegex(ValueError, "sweep constraint must belong"):
                run_optimization(problem, name="foreign_constraint", build=incorrect_builder,
                                 points=budget_points((1,), 1), env=self.env)
            foreign.update()
            self.assertEqual(foreign_constraint.RHS, 0)

    def test_fixed_formulations_cannot_relabel_their_declared_point(self):
        from models.common.runner import run_optimization
        from models.model3_min_keys_full_connectivity import build

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        for points in (connectivity_points((50,), 1), budget_points((1,), 1),
                       connectivity_points((100, 100), 1)):
            with self.subTest(points=points), self.assertRaisesRegex(ValueError, "declared fixed point"):
                run_optimization(problem, name="fixed_coverage", build=build, points=points, env=self.env)

    def test_custom_fixed_budget_is_reusable_without_runner_knowledge_of_its_policy(self):
        from models.common.runner import OptimizationBindings, run_optimization
        from models.model1_max_routes import build

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        point = budget_points((1,), 1)[0]

        def fixed_budget(model, activation_problem):
            bindings = build(model, activation_problem)
            bindings.sweep_constraint.RHS = point.bound
            return OptimizationBindings(bindings.activation, fixed_point=point)

        optimization = run_optimization(problem, name="fixed_budget", build=fixed_budget,
                                        points=(point,), env=self.env)
        self.assertEqual(optimization.outcomes[0].point, point)
        self.assertEqual(optimization.outcomes[0].objective_value, 1)
        self.assertEqual(len(optimization.traces[0].selected_route_ids), 1)

    def test_builders_must_declare_exactly_one_parameterization_contract(self):
        from models.common.runner import run_optimization
        from models import model1_max_routes, model3_min_keys_full_connectivity

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")

        def undeclared_fixed(model, activation_problem):
            return replace(model3_min_keys_full_connectivity.build(model, activation_problem), fixed_point=None)

        with self.assertRaisesRegex(ValueError, "declared fixed point"):
            run_optimization(problem, name="undeclared_fixed", build=undeclared_fixed,
                             points=connectivity_points((100,), 1), env=self.env)

        point = budget_points((1,), 1)[0]

        def contradictory_builder(model, activation_problem):
            return replace(model1_max_routes.build(model, activation_problem), fixed_point=point)

        with self.assertRaisesRegex(ValueError, "not both"):
            run_optimization(problem, name="contradictory_builder", build=contradictory_builder,
                             points=(point,), env=self.env)

    def test_coverage_points_and_sweep_kinds_must_be_consistent(self):
        from models.common.results import SweepPoint
        from models.common.runner import run_optimization
        from models.model2_min_keys import build

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        with self.assertRaisesRegex(ValueError, "pair count does not match"):
            run_optimization(problem, name="inconsistent_coverage", build=build,
                             points=(SweepPoint(target_connectivity_pct=100, required_pairs=0),), env=self.env)
        with self.assertRaisesRegex(ValueError, "cannot mix"):
            run_optimization(problem, name="mixed_sweep", build=build,
                             points=(*budget_points((0,), 1), *connectivity_points((100,), 1)), env=self.env)

    def test_builder_failure_disposes_only_the_owned_model(self):
        from models.common.runner import run_optimization

        catalog = make_catalog(make_topology({1: (1, 2)}), {(1, 2): [(1, 2)]})
        problem = ActivationPlanner().build(catalog.protection, policy_id="END_TO_END")
        captured_models = []

        def failing_builder(model, activation_problem):
            captured_models.append(model)
            attach_global_activation(model, activation_problem)
            raise RuntimeError("construction failed")

        with self.assertRaisesRegex(RuntimeError, "construction failed"):
            run_optimization(problem, name="failing_build", build=failing_builder,
                             points=budget_points((0,), 1), env=self.env)
        with self.assertRaises(gp.GurobiError):
            captured_models[0].getAttr(gp.GRB.Attr.NumVars)
        # The environment is borrowed, so another model can still use it.
        with gp.Model(env=self.env) as model:
            model.optimize()
            self.assertEqual(model.Status, gp.GRB.OPTIMAL)


if __name__ == "__main__":
    unittest.main()
