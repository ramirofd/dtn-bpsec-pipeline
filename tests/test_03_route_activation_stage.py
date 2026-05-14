from __future__ import annotations

import unittest

from modules.security.artifacts import ProtectionPlan
from modules.security.keys import KeyRequirement
from modules.security.models import KeyType, SecurityModelType, SecurityService
from pipelines.route_activation import RouteActivationPlanner
from pipelines.simulation import SecurityBatchResult


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


# if __name__ == "__main__":
#     unittest.main(verbosity=2)
