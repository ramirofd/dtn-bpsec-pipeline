from __future__ import annotations

import unittest

from models.plot_utils import (
    build_contact_usage_data,
    build_key_reuse_data,
    build_key_scope_activation_data,
    build_pair_coverage_data,
)
from modules.security.keys import KeyScope
from modules.security.models import KeyType, SecurityModelType
from modules.security.planning import build_protection_plan
from pipelines.route_activation import (
    RouteActivationArtifacts,
    RouteActivationPlanner,
    trace_route_activation_solution,
)
from pipelines.simulation import SecurityBatchResult, SimulationResult
from tests.builders import (
    make_annotation_batch_result,
    make_annotated_route,
    make_contact,
    make_route,
    make_routing_batch_result,
    make_topology,
)


class _DummyVar:
    def __init__(self, value: float) -> None:
        self.X = value


def build_sample_trace():
    topology = make_topology({1: (1, 2), 2: (3, 4)})
    pair = (1, 4)
    route = make_route(
        (
            make_contact(1, 2, start=0, end=10, rate=5, owlt=1),
            make_contact(2, 3, start=12, end=25, rate=7, owlt=2),
            make_contact(3, 4, start=30, end=45, rate=9, owlt=1),
        )
    )
    annotated_route = make_annotated_route(
        topology,
        source_node=pair[0],
        destination_node=pair[1],
        contacts=route.get_hops(),
        route_id="route-1",
    )
    plan = build_protection_plan(SecurityModelType.EDGE_BY_EDGE, annotated_route)
    security_batch = SecurityBatchResult(
        pairs=(pair,),
        symmetric_keys=False,
        plans_by_model={
            SecurityModelType.EDGE_BY_EDGE: {
                pair: (plan,),
            }
        },
    )
    planning = RouteActivationPlanner().build_for_model(
        security_batch,
        model=SecurityModelType.EDGE_BY_EDGE,
    )
    routing = make_routing_batch_result(
        topology=topology,
        pairs=(pair,),
        routes_by_pair={pair: (route,)},
        contact_plan_size=3,
    )
    annotation = make_annotation_batch_result(
        topology=topology,
        pairs=(pair,),
        routes_by_pair={pair: (route,)},
        annotated_routes_by_pair={pair: (annotated_route,)},
        contact_plan_size=3,
    )
    result = SimulationResult(
        topology=topology,
        contact_plan_size=3,
        routing=routing,
        annotation=annotation,
        security=security_batch,
    )
    artifacts = RouteActivationArtifacts(
        planning=planning,
        model=None,
        route_vars={
            planning.route_requirements[0].route_id: _DummyVar(1.0),
        },
        key_vars={
            scope: _DummyVar(1.0)
            for scope in planning.key_scopes
        },
        route_constraints={},
    )
    trace = trace_route_activation_solution(
        result,
        artifacts,
        security_model=SecurityModelType.EDGE_BY_EDGE,
    )
    return trace


class PlotUtilsDataTests(unittest.TestCase):
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
