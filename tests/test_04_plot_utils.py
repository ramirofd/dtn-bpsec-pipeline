from __future__ import annotations

import unittest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from models.plot_utils import (
    build_contact_usage_data, build_key_reuse_data, build_key_scope_activation_data,
    build_pair_coverage_data, plot_metric_bars_by_model, plot_metric_curve,
)
from modules.security.models import SecurityModelType
from pipelines.activation import ActivationPlanner, ActivationSolution, build_trace
from pipelines.simulation import RouteAnnotationStage, SecurityPlanningStage
from tests.builders import make_contact, make_route, make_route_catalog, make_topology


def build_sample_trace():
    topology = make_topology({1: (1, 2), 2: (3, 4)})
    pair = (1, 4)
    route = make_route((
        make_contact(1, 2, start=0, end=10, rate=5, owlt=1),
        make_contact(2, 3, start=12, end=25, rate=7, owlt=2),
        make_contact(3, 4, start=30, end=45, rate=9, owlt=1),
    ))
    routes = make_route_catalog(topology=topology, pairs=(pair,), routes_by_pair={pair: (route,)})
    annotations = RouteAnnotationStage().annotate(routes)
    catalog = SecurityPlanningStage().build(annotations)
    problem = ActivationPlanner().build(catalog, policy_id=SecurityModelType.EDGE_BY_EDGE.name)
    solution = ActivationSolution(
        {ref: 1.0 for ref in problem.requirements}, {scope: 1.0 for scope in problem.key_scopes},
    )
    return build_trace(problem, solution)


class PlotUtilsDataTests(unittest.TestCase):
    def tearDown(self) -> None:
        plt.close("all")

    def test_configured_policies_are_kept_in_curves_and_bars(self) -> None:
        data = pd.DataFrame({
            "model": ["END_TO_END", "END_TO_END", "custom-policy", "custom-policy"],
            "target": [0, 1, 0, 1], "cost": [1, 2, 3, 4],
        })
        ax = plot_metric_curve(data, x="target", y="cost")
        self.assertEqual([text.get_text() for text in ax.get_legend().get_texts()], ["E2E", "custom-policy"])
        ax = plot_metric_bars_by_model(data[data.target == 1], y="cost")
        self.assertEqual([text.get_text() for text in ax.get_xticklabels()], ["E2E", "custom-policy"])
        self.assertEqual([bar.get_height() for bar in ax.patches], [2, 4])

    def test_infeasible_metrics_are_not_plotted_as_zero(self) -> None:
        data = pd.DataFrame({"model": ["END_TO_END"], "target": [100], "cost": [None]})
        for ax in (
            plot_metric_curve(data, x="target", y="cost"),
            plot_metric_bars_by_model(data, y="cost"),
        ):
            self.assertEqual(len(ax.patches), 0)
            self.assertEqual(len(ax.lines), 0)
            self.assertIn("No feasible solution", ax.texts[0].get_text())

    def test_connectivity_summary_supports_custom_and_infeasible_policies(self) -> None:
        from models.model2_min_keys import plot_required_key_percentage_at_connectivity

        data = pd.DataFrame({
            "model": ["custom-policy", "END_TO_END", "unreachable-policy"],
            "target_connectivity_pct": [100, 100, 100],
            "selected_keys_pct_of_available": [50, 25, None],
            "selected_keys": [2, 1, None], "total_key_scopes": [4, 4, 4],
        })
        ax = plot_required_key_percentage_at_connectivity(data)
        self.assertEqual([text.get_text() for text in ax.get_xticklabels()], ["E2E", "custom-policy"])
        self.assertEqual([text.get_text() for text in ax.texts], ["25.0%\n(1/4)", "50.0%\n(2/4)"])
        ax = plot_required_key_percentage_at_connectivity(data.iloc[2:])
        self.assertIn("No feasible solution", ax.texts[0].get_text())

    def test_build_key_scope_activation_data_counts_key_usage(self) -> None:
        trace = build_sample_trace()

        data = build_key_scope_activation_data({1: trace}, sweep_label="max_keys")

        self.assertEqual(set(data["key_scope"]), {"N-G 1->1", "G-G 1->2", "N-N 3->4"})
        group_row = data.loc[data["key_scope"] == "G-G 1->2"].iloc[0]
        self.assertEqual(group_row["selected"], 1)
        self.assertEqual(group_row["route_count"], 1)
        self.assertEqual(group_row["pair_count"], 1)
        self.assertEqual(group_row["operation_count"], 1)

    def test_build_contact_usage_data_marks_boundary_contacts(self) -> None:
        trace = build_sample_trace()

        data = build_contact_usage_data({1: trace}, sweep_label="max_keys")

        boundary_row = data.loc[data["contact"] == "2->3 [12-25, owlt=2]"].iloc[0]
        self.assertEqual(boundary_row["from_network"], 1)
        self.assertEqual(boundary_row["to_network"], 2)
        self.assertTrue(boundary_row["crosses_network_boundary"])
        self.assertEqual(boundary_row["route_count"], 1)
        self.assertEqual(boundary_row["pair_count"], 1)

    def test_build_pair_coverage_data_includes_unselected_pairs(self) -> None:
        trace = build_sample_trace()

        data = build_pair_coverage_data(
            {50: trace},
            sweep_label="target_connectivity_pct",
            all_pairs=((1, 4), (4, 1)),
        )

        selected_row = data.loc[
            (data["target_connectivity_pct"] == 50) & (data["pair"] == "1->4")
        ].iloc[0]
        missing_row = data.loc[
            (data["target_connectivity_pct"] == 50) & (data["pair"] == "4->1")
        ].iloc[0]
        self.assertEqual(selected_row["selected"], 1)
        self.assertEqual(missing_row["selected"], 0)

    def test_build_key_reuse_data_sorts_and_counts(self) -> None:
        trace = build_sample_trace()

        data = build_key_reuse_data(trace)

        self.assertEqual(len(data), 3)
        self.assertIn("key_scope", data.columns)
        self.assertTrue((data["route_count"] == 1).all())
        self.assertIn("G-G 1->2", set(data["key_scope"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
