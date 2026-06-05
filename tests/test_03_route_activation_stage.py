from __future__ import annotations

import unittest

from modules.security.artifacts import ProtectionPlan
from modules.security.keys import KeyRequirement, KeyScope
from modules.security.models import KeyType, SecurityModelType, SecurityService
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


class RouteActivationPlannerTests(unittest.TestCase):
    def test_build_deduplicates_route_and_global_scopes(self) -> None:
        """Proves activation planning deduplicates repeated key scopes per route and globally."""
        planner = RouteActivationPlanner()
        shared_requirement = KeyRequirement(
            operation_id="op-shared",
            key_type=KeyType.NODE_TO_NODE,
            usage=SecurityService.BCB,
            source_id=1,
            target_id=2,
            local_node=1,
            rationale="shared",
        )
        repeated_requirement = KeyRequirement(
            operation_id="op-shared",
            key_type=KeyType.NODE_TO_NODE,
            usage=SecurityService.BCB,
            source_id=1,
            target_id=2,
            local_node=1,
            rationale="shared again",
        )
        extra_requirement = KeyRequirement(
            operation_id="op-extra",
            key_type=KeyType.GROUP_TO_GROUP,
            usage=SecurityService.BCB,
            source_id=10,
            target_id=20,
            local_node=3,
            rationale="extra",
        )

        planning = planner.build(
            (
                ProtectionPlan(
                    route_id="route-a",
                    model=SecurityModelType.HOP_BY_HOP,
                    operations=(),
                    node_requirements=(),
                    key_requirements=(shared_requirement, repeated_requirement, extra_requirement),
                ),
                ProtectionPlan(
                    route_id="route-b",
                    model=SecurityModelType.HOP_BY_HOP,
                    operations=(),
                    node_requirements=(),
                    key_requirements=(shared_requirement,),
                ),
            )
        )

        self.assertEqual(len(planning.route_requirements), 2)
        self.assertEqual(
            planning.route_requirements[0].required_key_scopes,
            (shared_requirement.scope, extra_requirement.scope),
        )
        self.assertEqual(
            planning.route_requirements[0].operation_ids,
            ("op-shared", "op-extra"),
        )
        self.assertEqual(
            planning.key_scopes,
            (shared_requirement.scope, extra_requirement.scope),
        )

    def test_build_for_model_prefixes_pair_into_route_ids(self) -> None:
        """Proves per-model planning namespaces route ids with their source-destination pair."""
        planner = RouteActivationPlanner()
        pair = (1, 3)
        security_batch = SecurityBatchResult(
            pairs=(pair,),
            symmetric_keys=False,
            plans_by_model={
                SecurityModelType.HOP_BY_HOP: {
                    pair: (
                        ProtectionPlan(
                            route_id="route-1",
                            model=SecurityModelType.HOP_BY_HOP,
                            operations=(),
                            node_requirements=(),
                            key_requirements=(),
                        ),
                    )
                }
            },
        )

        planning = planner.build_for_model(
            security_batch,
            model=SecurityModelType.HOP_BY_HOP,
        )

        self.assertEqual(planning.route_requirements[0].route_id, "1->3:route-1")

    def test_build_can_collapse_symmetric_scopes(self) -> None:
        """Proves symmetric mode merges reciprocal key scopes into one normalized requirement."""
        planner = RouteActivationPlanner()
        planning = planner.build(
            (
                ProtectionPlan(
                    route_id="route-ab",
                    model=SecurityModelType.HOP_BY_HOP,
                    operations=(),
                    node_requirements=(),
                    key_requirements=(
                        KeyRequirement(
                            operation_id="op1",
                            key_type=KeyType.NODE_TO_NODE,
                            usage=SecurityService.BCB,
                            source_id=1,
                            target_id=2,
                            local_node=1,
                            rationale="ab",
                        ),
                    ),
                ),
                ProtectionPlan(
                    route_id="route-ba",
                    model=SecurityModelType.HOP_BY_HOP,
                    operations=(),
                    node_requirements=(),
                    key_requirements=(
                        KeyRequirement(
                            operation_id="op2",
                            key_type=KeyType.NODE_TO_NODE,
                            usage=SecurityService.BCB,
                            source_id=2,
                            target_id=1,
                            local_node=2,
                            rationale="ba",
                        ),
                    ),
                ),
            ),
            symmetric_keys=True,
        )

        self.assertEqual(len(planning.key_scopes), 1)
        self.assertEqual(planning.key_scopes[0].source_id, 1)
        self.assertEqual(planning.key_scopes[0].target_id, 2)

    def test_trace_solution_links_selected_keys_routes_and_contacts(self) -> None:
        """Proves the trace helper rebuilds selected routes, contacts, and key usage."""
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

        self.assertEqual(trace.selected_pairs, (pair,))
        self.assertEqual(trace.selected_route_ids, ("1->4:route-1",))
        self.assertEqual(trace.selected_key_scopes, planning.key_scopes)

        route_selection = trace.routes[0]
        self.assertEqual(route_selection.local_route_id, "route-1")
        self.assertEqual(route_selection.node_path, (1, 2, 3, 4))
        self.assertEqual(route_selection.network_path, (1, 1, 2, 2))
        self.assertEqual(route_selection.boundary_crossings[0].hop_index, 1)
        self.assertEqual(route_selection.contacts[1].from_node, 2)
        self.assertEqual(route_selection.contacts[1].to_node, 3)
        self.assertTrue(route_selection.contacts[1].crosses_network_boundary)
        self.assertEqual(route_selection.contacts[1].start, 12)
        self.assertEqual(
            route_selection.required_key_scopes,
            planning.route_requirements[0].required_key_scopes,
        )

        boundary_operation = route_selection.operations[1]
        self.assertEqual(boundary_operation.target_hop_indexes, (1,))
        self.assertEqual(
            boundary_operation.selected_key_scope,
            KeyScope(KeyType.GROUP_TO_GROUP, 1, 2),
        )
        self.assertEqual(boundary_operation.covered_contacts[0], route_selection.contacts[1])

        group_key_selection = next(
            key_selection
            for key_selection in trace.keys
            if key_selection.scope == KeyScope(KeyType.GROUP_TO_GROUP, 1, 2)
        )
        self.assertEqual(group_key_selection.route_ids, ("1->4:route-1",))
        self.assertEqual(group_key_selection.pair_ids, ("1->4",))
        self.assertEqual(
            group_key_selection.operation_ids,
            (boundary_operation.operation_id,),
        )

    def test_trace_solution_keeps_raw_and_normalized_scopes_in_symmetric_mode(self) -> None:
        """Proves the trace helper preserves raw scopes while exposing normalized selected scopes."""
        topology = make_topology({1: (1, 2)})
        pair = (2, 1)
        route = make_route((make_contact(2, 1, start=0, end=10, rate=5, owlt=1),))
        annotated_route = make_annotated_route(
            topology,
            source_node=pair[0],
            destination_node=pair[1],
            contacts=route.get_hops(),
            route_id="route-1",
        )
        plan = build_protection_plan(SecurityModelType.END_TO_END, annotated_route)
        security_batch = SecurityBatchResult(
            pairs=(pair,),
            symmetric_keys=True,
            plans_by_model={
                SecurityModelType.END_TO_END: {
                    pair: (plan,),
                }
            },
        )
        planning = RouteActivationPlanner().build_for_model(
            security_batch,
            model=SecurityModelType.END_TO_END,
        )
        routing = make_routing_batch_result(
            topology=topology,
            pairs=(pair,),
            routes_by_pair={pair: (route,)},
            contact_plan_size=1,
        )
        annotation = make_annotation_batch_result(
            topology=topology,
            pairs=(pair,),
            routes_by_pair={pair: (route,)},
            annotated_routes_by_pair={pair: (annotated_route,)},
            contact_plan_size=1,
        )
        result = SimulationResult(
            topology=topology,
            contact_plan_size=1,
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
                planning.key_scopes[0]: _DummyVar(1.0),
            },
            route_constraints={},
        )

        trace = trace_route_activation_solution(
            result,
            artifacts,
            security_model=SecurityModelType.END_TO_END,
        )

        self.assertEqual(
            trace.selected_key_scopes,
            (KeyScope(KeyType.NODE_TO_NODE, 1, 2),),
        )
        self.assertEqual(
            trace.routes[0].required_key_scopes,
            (KeyScope(KeyType.NODE_TO_NODE, 1, 2),),
        )
        self.assertEqual(
            trace.routes[0].operations[0].raw_key_scope,
            KeyScope(KeyType.NODE_TO_NODE, 2, 1),
        )
        self.assertEqual(
            trace.routes[0].operations[0].selected_key_scope,
            KeyScope(KeyType.NODE_TO_NODE, 1, 2),
        )


# if __name__ == "__main__":
#     unittest.main(verbosity=2)
