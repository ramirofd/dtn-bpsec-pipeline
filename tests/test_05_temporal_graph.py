from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from modules.network.temporal_graph import plot_temporal_graph
from tests.builders import make_contact, make_topology


@unittest.skipUnless(importlib.util.find_spec("teneto") is not None, "teneto is not installed")
class TemporalGraphPlotTests(unittest.TestCase):
    def test_plot_temporal_graph_returns_figure_and_saves_png(self) -> None:
        topology = make_topology({1: (1, 2), 2: (3,)})
        contact_plan = [
            make_contact(1, 2, start=0, end=10),
            make_contact(2, 3, start=10, end=20),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "temporal_graph.png"
            fig, ax = plot_temporal_graph(
                topology=topology,
                contact_plan=contact_plan,
                title="Notebook Plot",
                output_path=output_path,
            )

            self.assertEqual(ax.get_title(), "Notebook Plot")
            self.assertTrue(output_path.exists())
            self.assertEqual([tick.get_text() for tick in ax.get_yticklabels()[:3]], ["1", "2", "3"])
            plt.close(fig)


if __name__ == "__main__":
    unittest.main(verbosity=2)
