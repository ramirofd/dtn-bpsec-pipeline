from __future__ import annotations

from dataclasses import replace
import unittest

from modules.domain import RouteCandidate, RouteRef
from pipelines.catalogs import AnnotationCatalog, RouteCatalog
from pipelines.simulation import RouteAnnotationStage
from tests.builders import make_contact, make_route, make_route_catalog, make_topology


class RouteAnnotationStageTests(unittest.TestCase):
    def setUp(self):
        topology = make_topology({1: (1, 2), 2: (3, 4), 3: (5,)})
        route = make_route((make_contact(1, 2), make_contact(2, 3), make_contact(3, 4), make_contact(4, 5)))
        self.routes = make_route_catalog(topology=topology, pairs=((1, 5), (5, 1)), routes_by_pair={(1, 5): (route,)})
        self.ref = RouteRef((1, 5), 1)

    def test_marks_boundary_crossings_and_gateway_nodes(self) -> None:
        result = RouteAnnotationStage().annotate(self.routes)
        annotated = result.by_route[self.ref]
        self.assertIs(result.routes, self.routes)
        self.assertEqual(annotated.ref, self.ref)
        self.assertEqual(annotated.node_path, (1, 2, 3, 4, 5))
        self.assertEqual(annotated.network_path, (1, 1, 2, 2, 3))
        self.assertEqual(tuple((c.exit_node, c.entrance_node) for c in annotated.boundary_crossings), ((2, 3), (4, 5)))
        self.assertEqual(annotated.gateway_nodes, frozenset({2, 3, 4, 5}))
        self.assertEqual(result.routes.routes_by_pair[(5, 1)], ())

    def test_identity_remains_correct_after_catalog_reordering(self) -> None:
        first = self.routes.by_id[self.ref]
        second_ref = RouteRef((1, 5), 2)
        second = replace(first, ref=second_ref)
        catalog = RouteCatalog(self.routes.scenario, {second_ref: second, self.ref: first})
        annotations = RouteAnnotationStage().annotate(catalog)
        self.assertEqual(catalog.routes_by_pair[(1, 5)], (self.ref, second_ref))
        self.assertEqual(annotations.by_route[self.ref].ref, self.ref)
        self.assertEqual(annotations.by_route[second_ref].ref, second_ref)

    def test_missing_annotation_and_mismatched_identity_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'exactly'):
            AnnotationCatalog(self.routes, {})
        annotation = RouteAnnotationStage().annotate(self.routes).by_route[self.ref]
        with self.assertRaisesRegex(ValueError, 'reference'):
            AnnotationCatalog(self.routes, {self.ref: replace(annotation, ref=RouteRef((1, 5), 2))})
        with self.assertRaisesRegex(ValueError, 'reference'):
            RouteCatalog(self.routes.scenario, {RouteRef((1, 5), 2): self.routes.by_id[self.ref]})

    def test_empty_or_disconnected_route_is_rejected_at_domain_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, 'at least one hop'):
            RouteCandidate(self.ref, (), 0, 0, 1)
        contacts = self.routes.by_id[self.ref].contacts
        with self.assertRaisesRegex(ValueError, 'continuous'):
            RouteCandidate(self.ref, (contacts[0], contacts[-1]), 0, 0, 1)

    def test_catalog_copies_mapping_before_exposing_it(self) -> None:
        by_id = dict(self.routes.by_id)
        catalog = RouteCatalog(self.routes.scenario, by_id)
        by_id.clear()
        self.assertEqual(len(catalog.by_id), 1)
        result = RouteAnnotationStage().annotate(catalog)
        with self.assertRaises(TypeError):
            result.by_route[self.ref] = None

    def test_injected_annotation_must_preserve_hop_indices(self) -> None:
        annotation = RouteAnnotationStage().annotate(self.routes).by_route[self.ref]
        corrupt_hops = (replace(annotation.hops[0], hop_index=3), *annotation.hops[1:])
        with self.assertRaisesRegex(ValueError, "indices and endpoints"):
            AnnotationCatalog(self.routes, {self.ref: replace(annotation, hops=corrupt_hops)})
