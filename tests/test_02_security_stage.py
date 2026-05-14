from __future__ import annotations

import unittest

from modules.security.models import SecurityModelType
from pipelines.simulation import SecurityPlanningStage
from tests.builders import (
    make_annotation_batch_result,
    make_annotated_route,
    make_contact,
    make_route,
    make_topology,
)


# class SecurityPlanningStageTests(unittest.TestCase):
#     def test_build_batch_keeps_one_plan_per_route_per_model(self) -> None:
#         """Proves security planning emits one plan per route for every requested model."""
#         topology = make_topology({1: (1, 2), 2: (3, 4), 3: (5,)})
#         pair = (1, 5)
#         route = make_route(
#             (
#                 make_contact(1, 2),
#                 make_contact(2, 3),
#                 make_contact(3, 4),
#                 make_contact(4, 5),
#             )
#         )
#         annotated_route = make_annotated_route(
#             topology,
#             source_node=1,
#             destination_node=5,
#             contacts=route.get_hops(),
#         )
#         annotation = make_annotation_batch_result(
#             topology=topology,
#             pairs=(pair,),
#             routes_by_pair={pair: (route,)},
#             annotated_routes_by_pair={pair: (annotated_route,)},
#             contact_plan_size=4,
#         )

#         result = SecurityPlanningStage().build_batch(
#             annotation,
#             security_models=tuple(SecurityModelType),
#         )

#         self.assertEqual(result.pairs, (pair,))
#         for model in SecurityModelType:
#             self.assertEqual(len(result.plans_by_model[model][pair]), 1)

#         hop_by_hop_plan = result.plans_by_model[SecurityModelType.HOP_BY_HOP][pair][0]
#         end_to_end_plan = result.plans_by_model[SecurityModelType.END_TO_END][pair][0]
#         edge_by_edge_plan = result.plans_by_model[SecurityModelType.EDGE_BY_EDGE][pair][0]
#         edge_to_edge_plan = result.plans_by_model[SecurityModelType.EDGE_TO_EDGE][pair][0]

#         self.assertEqual(len(hop_by_hop_plan.operations), 4)
#         self.assertEqual(len(end_to_end_plan.operations), 1)
#         self.assertEqual(len(edge_by_edge_plan.operations), 4)
#         self.assertEqual(len(edge_to_edge_plan.operations), 2)

#     def test_edge_to_edge_degenerates_for_intra_network_routes(self) -> None:
#         """Proves edge-to-edge collapses to one local protection step inside a single network."""
#         topology = make_topology({1: (1, 2, 3)})
#         pair = (1, 3)
#         route = make_route((make_contact(1, 2), make_contact(2, 3)))
#         annotated_route = make_annotated_route(
#             topology,
#             source_node=1,
#             destination_node=3,
#             contacts=route.get_hops(),
#         )
#         annotation = make_annotation_batch_result(
#             topology=topology,
#             pairs=(pair,),
#             routes_by_pair={pair: (route,)},
#             annotated_routes_by_pair={pair: (annotated_route,)},
#             contact_plan_size=2,
#         )

#         result = SecurityPlanningStage().build_batch(
#             annotation,
#             security_models=(SecurityModelType.EDGE_TO_EDGE,),
#         )
#         plan = result.plans_by_model[SecurityModelType.EDGE_TO_EDGE][pair][0]

#         self.assertEqual(len(plan.operations), 1)
#         self.assertEqual(
#             plan.notes,
#             (
#                 "Route stays within one network; edge-to-edge degenerates to local intra-network protection.",
#             ),
#         )


# if __name__ == "__main__":
#     unittest.main(verbosity=2)
