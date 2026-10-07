from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.domain import ContactSnapshot, Scenario
from modules.network.cgr.loader import cp_load
from modules.network.ion_contact_plan import (
    IonContactPlanError,
    convert_ion_contact_plan,
    parse_ion_contact_plan,
)
from modules.network.topology import Topology
from pipelines.routing import RoutingBatchRequest
from pipelines.simulation import SimulationPipeline


class IonContactPlanTests(unittest.TestCase):
    def test_cpd_export_preserves_rate_zero_owlt_order_and_directions(self) -> None:
        text = """\ufeff# miniature CPD export
@ 2026/10/06-00:00:00
a contact +0 +122 10 20 1000000
a contact +0 +122 20 10 1000000 1.0 # optional unit confidence
a range +0 +122 10 20 0
"""
        self.assertEqual(parse_ion_contact_plan(text, default_owlt=9), [
            {"start": 0, "end": 122, "from": 10, "to": 20, "rate": 1000000, "owlt": 0},
            {"start": 0, "end": 122, "from": 20, "to": 10, "rate": 1000000, "owlt": 0},
        ])

    def test_contact_is_split_when_range_changes_without_changing_volume(self) -> None:
        text = """a contact +0 +100 1 2 5
a range +40 +100 1 2 3
a range +0 +40 1 2 1
"""
        contacts = parse_ion_contact_plan(text)
        self.assertEqual([(c["start"], c["end"], c["owlt"]) for c in contacts], [(0, 40, 1), (40, 100, 3)])
        self.assertEqual(sum((c["end"] - c["start"]) * c["rate"] for c in contacts), 500)

    def test_explicit_reverse_range_overrides_only_its_interval(self) -> None:
        text = """a contact +0 +100 2 1 5
a contact +0 +100 1 2 5
a range +20 +60 2 1 7
a range +0 +100 1 2 2
"""
        contacts = parse_ion_contact_plan(text)
        self.assertEqual(
            [(c["from"], c["start"], c["end"], c["owlt"]) for c in contacts],
            [(2, 0, 20, 2), (2, 20, 60, 7), (2, 60, 100, 2), (1, 0, 100, 2)],
        )

    def test_descending_range_does_not_imply_ascending_range(self) -> None:
        with self.assertRaisesRegex(IonContactPlanError, "no range covers 1->2"):
            parse_ion_contact_plan("a contact +0 +10 1 2 5\na range +0 +10 2 1 3")

    def test_absolute_and_relative_times_share_epoch(self) -> None:
        text = """@ 2026/10/06-00:00:00
a contact 2026/10/06-00:01:00 2026/10/06-00:02:00 1 2 5
a range +0 +120 1 2 2
"""
        self.assertEqual(parse_ion_contact_plan(text)[0], {
            "start": 60, "end": 120, "from": 1, "to": 2, "rate": 5, "owlt": 2,
        })

    def test_missing_range_requires_explicit_fallback_and_warns(self) -> None:
        text = "a contact +0 +10 1 2 5"
        with self.assertRaisesRegex(IonContactPlanError, "ION line 1: no range"):
            parse_ion_contact_plan(text)
        with self.assertWarnsRegex(UserWarning, "1 source contact"):
            self.assertEqual(parse_ion_contact_plan(text, default_owlt=0)[0]["owlt"], 0)

    def test_partial_range_gap_is_not_filled_silently(self) -> None:
        text = "a contact +0 +30 1 2 5\na range +10 +20 1 2 2"
        with self.assertRaisesRegex(IonContactPlanError, r"\[0, 10\)"):
            parse_ion_contact_plan(text)
        with self.assertWarns(UserWarning):
            contacts = parse_ion_contact_plan(text, default_owlt=1)
        self.assertEqual([(c["start"], c["end"], c["owlt"]) for c in contacts], [(0, 10, 1), (10, 20, 2), (20, 30, 1)])

    def test_rejects_overlapping_ranges_even_when_input_is_unsorted(self) -> None:
        text = "a contact +0 +30 1 2 5\na range +10 +30 1 2 2\na range +0 +20 1 2 1"
        with self.assertRaisesRegex(IonContactPlanError, "overlapping ranges"):
            parse_ion_contact_plan(text)

    def test_rejects_malformed_or_lossy_inputs(self) -> None:
        bad_inputs = {
            "fractional start": "a contact +0.1 +10 1 2 5",
            "fractional rate": "a contact +0 +10 1 2 5.5",
            "fractional delay": "a contact +0 +10 1 2 5\na range +0 +10 1 2 0.03",
            "nan": "a contact +0 +10 1 2 NaN",
            "zero rate": "a contact +0 +10 1 2 0",
            "same endpoints": "a contact +0 +10 1 1 5",
            "zero duration": "a contact +10 +10 1 2 5",
            "negative time": "a contact +-1 +10 1 2 5",
            "negative range": "a contact +0 +10 1 2 5\na range +0 +10 1 2 -1",
            "node zero": "a contact +0 +10 0 2 5",
            "nonunit confidence": "a contact +0 +10 1 2 5 0.5",
            "excess confidence": "a contact +0 +10 1 2 5 2",
            "missing field": "a contact +0 +10 1 2",
            "extra field": "a range +0 +10 1 2 1 extra",
            "unsupported command": "d contact +0 1 2",
            "extra epoch": "@ 2026/10/06-00:00:00\n@ 2026/10/06-00:01:00",
            "late epoch": "a contact +0 +10 1 2 5\n@ 2026/10/06-00:00:00",
            "absolute without epoch": "a contact 2026/10/06-00:00:00 2026/10/06-00:01:00 1 2 5",
            "invalid epoch": "@ 2026/99/06-00:00:00",
            "no contacts": "# empty plan",
        }
        for label, text in bad_inputs.items():
            with self.subTest(label=label), self.assertRaises(IonContactPlanError):
                parse_ion_contact_plan(text, default_owlt=0)

    def test_preserves_contact_boundaries_and_does_not_invent_reverse_contacts(self) -> None:
        text = """a contact +10 +20 1 2 5
a contact +0 +10 1 2 5
a range +0 +5 1 2 1
a range +5 +20 1 2 1
"""
        contacts = parse_ion_contact_plan(text)
        self.assertEqual([(c["start"], c["end"]) for c in contacts], [(10, 20), (0, 10)])
        self.assertTrue(all(c["from"] == 1 and c["to"] == 2 for c in contacts))

    def test_conversion_loads_and_runs_in_pipeline(self) -> None:
        text = "a contact +0 +100 1 2 125000\na range +0 +100 1 2 1\n"
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.txt"
            target = Path(folder) / "nested" / "contact_plan.json"
            source.write_text(text, encoding="utf-8")
            contacts = convert_ion_contact_plan(source, target)
            self.assertEqual(json.loads(target.read_text()), contacts)
            self.assertEqual(convert_ion_contact_plan(source), contacts)
            self.assertEqual(source.read_text(), text)
            loaded = cp_load(str(target))
            self.assertEqual((loaded[0].rate, loaded[0].owlt, loaded[0].volume), (125000, 1, 12500000))
            scenario = Scenario(
                topology=Topology(node_to_network={1: 1, 2: 2}, network_to_nodes={1: frozenset({1}), 2: frozenset({2})}),
                contacts=tuple(ContactSnapshot.from_contact(contact) for contact in loaded),
            )
            result = SimulationPipeline().run(RoutingBatchRequest(scenario, num_routes=1))
            self.assertEqual(len(result.routes.scenario.contacts), 1)
            self.assertEqual(len(result.routes.routes_by_pair[(1, 2)]), 1)
            self.assertEqual(len(result.routes.routes_by_pair[(2, 1)]), 0)

    def test_invalid_input_does_not_replace_existing_json(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "bad.txt"
            target = Path(folder) / "contact_plan.json"
            source.write_text("a contact +0 +10 1 2 0", encoding="utf-8")
            target.write_text("keep me", encoding="utf-8")
            with self.assertRaises(IonContactPlanError):
                convert_ion_contact_plan(source, target)
            self.assertEqual(target.read_text(), "keep me")

    def test_cannot_overwrite_source(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "input.txt"
            text = "a contact +0 +10 1 2 5\na range +0 +10 1 2 0"
            source.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different"):
                convert_ion_contact_plan(source, source)
            self.assertEqual(source.read_text(), text)

    def test_invalid_fallback_is_rejected(self) -> None:
        for value in (-1, 0.03, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_ion_contact_plan("a contact +0 +10 1 2 5", default_owlt=value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
