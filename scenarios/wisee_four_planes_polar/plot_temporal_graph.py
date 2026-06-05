from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SCENARIO_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCENARIO_DIR.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.network.temporal_graph import plot_temporal_graph


DEFAULT_CONTACT_PLAN_PATH = SCENARIO_DIR / "contact_plan.json"
DEFAULT_TOPOLOGY_PATH = SCENARIO_DIR / "topology.json"
DEFAULT_OUTPUT_PATH = SCENARIO_DIR / "temporal_graph.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draw the temporal graph grouping nodes by network.")
    parser.add_argument(
        "--contact-plan",
        type=Path,
        default=DEFAULT_CONTACT_PLAN_PATH,
        help="Path to the contact-plan JSON file.",
    )
    parser.add_argument(
        "--topology",
        type=Path,
        default=DEFAULT_TOPOLOGY_PATH,
        help="Path to the topology JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for the PNG image.",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Optional chart title.",
    )
    return parser.parse_args()


def build_output_path(contact_plan_path: Path, output_path: Path | None) -> Path:
    if output_path is not None:
        return output_path
    if contact_plan_path == DEFAULT_CONTACT_PLAN_PATH:
        return DEFAULT_OUTPUT_PATH
    return SCENARIO_DIR / f"temporal_graph_{contact_plan_path.stem}.png"


def main() -> None:
    args = parse_args()
    output_path = build_output_path(args.contact_plan, args.output)
    title = args.title or f"Four Planes Polar Contact Plan ({args.contact_plan.stem})"
    fig, _ = plot_temporal_graph(
        contact_plan=args.contact_plan,
        topology=args.topology,
        title=title,
        output_path=output_path,
        legend_title="Grouping by network",
        network_label_prefix="Network",
    )
    plt.close(fig)

    print(output_path)


if __name__ == "__main__":
    main()
