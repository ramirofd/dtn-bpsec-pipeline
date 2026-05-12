from __future__ import annotations

import unittest
from pathlib import Path

from modules.security.models import SecurityModelType
from modules.security.planning import DEFAULT_SECURITY_MODELS, resolve_security_models
from pipelines.route_activation import RouteActivationPlanner
from pipelines.simulation import SimulationPipeline


REPO_ROOT = Path(__file__).resolve().parents[1]
BASIC_DIR = REPO_ROOT / "scenarios" / "examples" / "basic"
FOUR_PLANES_DIR = REPO_ROOT / "scenarios" / "examples" / "four_planes_polar"


class SecurityPipelineRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = SimulationPipeline().run(
            cp_path=str(BASIC_DIR / "contact_plan.json"),
            topology_path=str(BASIC_DIR / "topology.json"),
            security_models=tuple(SecurityModelType),
            curr_time=0,
            num_routes=3,
        )

    def test_basic_pipeline_keeps_pair_and_plan_alignment(self) -> None:
        self.assertEqual(len(self.result.routing.pairs), 132)
        self.assertEqual(self.result.routing.pairs, self.result.annotation.pairs)
        self.assertEqual(self.result.routing.pairs, self.result.security.pairs)

        for pair in self.result.annotation.pairs:
            routes = self.result.routing.routes_by_pair[pair]
            annotated_routes = self.result.annotation.annotated_routes_by_pair[pair]
            self.assertEqual(len(routes), len(annotated_routes))

            for model in SecurityModelType:
                plans = self.result.security.plans_by_model[model][pair]
                self.assertEqual(len(plans), len(annotated_routes))

    def test_edge_to_edge_degenerates_inside_one_network(self) -> None:
        pair = (1, 3)
        plan = self.result.security.plans_by_model[SecurityModelType.EDGE_TO_EDGE][pair][0]

        self.assertEqual(plan.route_id, "route-1")
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(
            plan.notes,
            (
                "Route stays within one network; edge-to-edge degenerates to local intra-network protection.",
            ),
        )

    def test_cross_network_routes_keep_expected_operation_shapes(self) -> None:
        pair = (1, 9)
        annotated_route = self.result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(len(annotated_route.hops), 8)
        self.assertEqual(len(annotated_route.boundary_crossings), 2)

        hop_by_hop_plan = self.result.security.plans_by_model[SecurityModelType.HOP_BY_HOP][pair][0]
        end_to_end_plan = self.result.security.plans_by_model[SecurityModelType.END_TO_END][pair][0]
        edge_by_edge_plan = self.result.security.plans_by_model[SecurityModelType.EDGE_BY_EDGE][pair][0]
        edge_to_edge_plan = self.result.security.plans_by_model[SecurityModelType.EDGE_TO_EDGE][pair][0]

        self.assertEqual(len(hop_by_hop_plan.operations), 8)
        self.assertEqual(len(end_to_end_plan.operations), 1)
        self.assertEqual(len(edge_by_edge_plan.operations), 4)
        self.assertEqual(len(edge_to_edge_plan.operations), 2)

    def test_route_activation_planning_stays_consistent(self) -> None:
        planning = RouteActivationPlanner().build_for_model(
            self.result.security,
            model=SecurityModelType.EDGE_TO_EDGE,
        )

        candidate_routes = sum(
            len(routes)
            for routes in self.result.annotation.annotated_routes_by_pair.values()
        )
        self.assertEqual(len(planning.route_requirements), candidate_routes)
        self.assertTrue(planning.key_scopes)

    def test_model_resolution_accepts_types_and_instances(self) -> None:
        resolved_defaults = resolve_security_models(None)
        resolved_mixed = resolve_security_models(
            (
                SecurityModelType.HOP_BY_HOP,
                DEFAULT_SECURITY_MODELS[1],
            )
        )

        self.assertEqual(
            tuple(model.type for model in resolved_defaults),
            tuple(SecurityModelType),
        )
        self.assertEqual(
            tuple(model.type for model in resolved_mixed),
            (
                SecurityModelType.HOP_BY_HOP,
                SecurityModelType.END_TO_END,
            ),
        )


class FourPlanesPolarScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = SimulationPipeline().run(
            cp_path=str(FOUR_PLANES_DIR / "contact_plan.json"),
            topology_path=str(FOUR_PLANES_DIR / "topology.json"),
            security_models=tuple(SecurityModelType),
            curr_time=0,
            num_routes=3,
        )

    def test_routes_from_network_1_to_network_3_pass_through_network_2(self) -> None:
        pair = (1, 11)
        annotated_route = self.result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.source_network, 1)
        self.assertEqual(annotated_route.destination_network, 3)
        self.assertEqual(annotated_route.network_path, (1, 2, 3))
        self.assertEqual(len(annotated_route.boundary_crossings), 2)

    def test_routes_from_network_1_to_network_4_pass_through_two_intermediate_networks(self) -> None:
        pair = (1, 16)
        annotated_route = self.result.annotation.annotated_routes_by_pair[pair][0]

        self.assertEqual(annotated_route.source_network, 1)
        self.assertEqual(annotated_route.destination_network, 4)
        self.assertEqual(annotated_route.network_path, (1, 2, 3, 4))
        self.assertEqual(len(annotated_route.boundary_crossings), 3)


if __name__ == "__main__":
    unittest.main()
