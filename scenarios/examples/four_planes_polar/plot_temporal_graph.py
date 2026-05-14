from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from teneto import TemporalNetwork


SCENARIO_DIR = Path(__file__).resolve().parent
CONTACT_PLAN_PATH = SCENARIO_DIR / "contact_plan.json"
OUTPUT_PATH = SCENARIO_DIR / "temporal_graph.png"


def load_contacts() -> list[dict[str, int]]:
    with CONTACT_PLAN_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_time_bins(contacts: list[dict[str, int]]) -> list[tuple[int, int]]:
    boundaries = sorted({contact["start"] for contact in contacts} | {contact["end"] for contact in contacts})
    return list(zip(boundaries[:-1], boundaries[1:]))


def build_temporal_array(
    contacts: list[dict[str, int]],
    time_bins: list[tuple[int, int]],
) -> np.ndarray:
    max_node = max(max(contact["from"], contact["to"]) for contact in contacts)
    temporal_array = np.zeros((max_node, max_node, len(time_bins)), dtype=int)

    for time_index, (start, end) in enumerate(time_bins):
        midpoint = (start + end) / 2
        for contact in contacts:
            if contact["start"] <= midpoint < contact["end"]:
                source = contact["from"] - 1
                target = contact["to"] - 1
                temporal_array[source, target, time_index] = 1

    return temporal_array


def main() -> None:
    contacts = load_contacts()
    time_bins = build_time_bins(contacts)
    temporal_array = build_temporal_array(contacts, time_bins)

    network = TemporalNetwork()
    network.network_from_array(temporal_array, forcesparse=True)

    fig, ax = plt.subplots(figsize=(20, 10))
    network.plot(
        "slice_plot",
        ax=ax,
        nodelabels=[str(node_id) for node_id in range(1, temporal_array.shape[0] + 1)],
        timelabels=[f"{start}-{end}" for start, end in time_bins],
        nodesize=18,
        nodekwargs={"c": "#1f2937"},
        edgekwargs={"alpha": 0.45, "linewidth": 0.8, "color": "#2563eb"},
    )
    ax.set_title("Four Planes Polar Contact Plan")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=220, bbox_inches="tight")
    plt.close(fig)

    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
