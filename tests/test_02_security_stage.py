from __future__ import annotations

from dataclasses import replace
import unittest

from modules.domain import OperationRef, PlanRef, RouteRef
from modules.security.models import SecurityModelType
from modules.security.planning import ConfiguredSecurityPolicy, EndToEndSecurityModel
from pipelines.catalogs import ProtectionCatalog
from pipelines.simulation import RouteAnnotationStage, SecurityPlanningStage
from tests.builders import make_contact, make_route, make_route_catalog, make_topology


class SecurityPlanningStageTests(unittest.TestCase):
    def setUp(self) -> None:
        topology = make_topology({1: (1, 2), 2: (3, 4), 3: (5,)})
        route = make_route((make_contact(1, 2), make_contact(2, 3), make_contact(3, 4), make_contact(4, 5)))
        routes = make_route_catalog(topology=topology, pairs=((1, 5),), routes_by_pair={(1, 5): (route,)})
        self.annotations = RouteAnnotationStage().annotate(routes)
        self.ref = RouteRef((1, 5), 1)

    def test_one_plan_per_route_and_family_preserves_key_semantics(self) -> None:
        result = SecurityPlanningStage().build(self.annotations)
        expected_counts = {SecurityModelType.HOP_BY_HOP: 4, SecurityModelType.END_TO_END: 1,
                           SecurityModelType.EDGE_BY_EDGE: 4, SecurityModelType.EDGE_TO_EDGE: 2}
        for family, count in expected_counts.items():
            ref = PlanRef(self.ref, family.name)
            plan = result.by_plan[ref]
            self.assertEqual(plan.ref, ref)
            self.assertEqual(len(plan.operations), count)
            self.assertTrue(all(operation.ref.plan == ref for operation in plan.operations))
            self.assertEqual({r.operation_ref for r in plan.node_requirements}, {o.ref for o in plan.operations})

    def test_two_configurations_of_same_family_do_not_overwrite(self) -> None:
        policies = [ConfiguredSecurityPolicy('first', EndToEndSecurityModel()),
                    ConfiguredSecurityPolicy('second', EndToEndSecurityModel())]
        stage = SecurityPlanningStage(policies)
        policies.clear()
        result = stage.build(self.annotations)
        self.assertEqual(len(result.by_plan), 2)
        first = result.by_plan[PlanRef(self.ref, 'first')]
        second = result.by_plan[PlanRef(self.ref, 'second')]
        self.assertNotEqual(first.operations[0].ref, second.operations[0].ref)
        self.assertEqual(first.key_requirements[0].scope, second.key_requirements[0].scope)

    def test_duplicate_policies_are_rejected(self) -> None:
        policy = ConfiguredSecurityPolicy('same', EndToEndSecurityModel())
        with self.assertRaisesRegex(ValueError, 'unique'):
            SecurityPlanningStage((policy, policy))

    def test_missing_plan_and_foreign_operation_are_rejected(self) -> None:
        result = SecurityPlanningStage((ConfiguredSecurityPolicy('test', EndToEndSecurityModel()),)).build(self.annotations)
        with self.assertRaisesRegex(ValueError, 'every route'):
            ProtectionCatalog(self.annotations, result.policies, {})
        ref, plan = next(iter(result.by_plan.items()))
        foreign = replace(plan.operations[0], ref=OperationRef(PlanRef(self.ref, 'other'), 'e2e'))
        with self.assertRaisesRegex(ValueError, 'containing plan'):
            ProtectionCatalog(self.annotations, result.policies, {ref: replace(plan, operations=(foreign,))})
        with self.assertRaisesRegex(ValueError, 'unique'):
            ProtectionCatalog(self.annotations, result.policies, {ref: replace(plan, operations=plan.operations * 2)})

    def test_reordered_annotations_are_joined_by_reference(self) -> None:
        result = SecurityPlanningStage().build(self.annotations)
        plans = dict(reversed(tuple(result.by_plan.items())))
        reordered = ProtectionCatalog(self.annotations, result.policies, plans)
        self.assertEqual(reordered.by_plan, result.by_plan)
        plans.clear()
        self.assertEqual(len(reordered.by_plan), 4)
        with self.assertRaises(TypeError):
            reordered.policies['other'] = SecurityModelType.END_TO_END
