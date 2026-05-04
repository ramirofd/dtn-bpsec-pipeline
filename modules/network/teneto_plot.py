from __future__ import annotations

import os
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import numpy as np

from modules.network.cgr.loader import cp_load
from modules.network.topology import topology_load


@dataclass(slots=True, frozen=True)
class TemporalEdgeBin:
    source_index: int
    target_index: int
    time_index: int


@dataclass(slots=True, frozen=True)
class TenetoContactPlanData:
    node_labels: tuple[str, ...]
    time_labels: tuple[str, ...]
    edge_list: list[list[int]]
    temporal_array: np.ndarray
    communities: tuple[int, ...] | None
    start_time: int
    end_time: int
    time_step: int


def build_teneto_contact_plan_data(
    cp_path: str | Path,
    *,
    topology_path: str | Path | None = None,
    time_step: int = 600,
) -> TenetoContactPlanData:
    if time_step <= 0:
        raise ValueError("time_step must be greater than 0")

    contacts = cp_load(str(cp_path))
    if not contacts:
        raise ValueError("contact plan is empty")

    ordered_nodes = tuple(sorted({contact.frm for contact in contacts} | {contact.to for contact in contacts}))
    node_to_index = {node_id: index for index, node_id in enumerate(ordered_nodes)}

    start_time = min(contact.start for contact in contacts)
    end_time = max(contact.end for contact in contacts)
    total_bins = max(1, ceil((end_time - start_time) / time_step))

    edge_bins: set[TemporalEdgeBin] = set()
    for contact in contacts:
        first_bin = max(0, (contact.start - start_time) // time_step)
        last_bin_exclusive = min(
            total_bins,
            ceil((contact.end - start_time) / time_step),
        )
        for time_index in range(first_bin, last_bin_exclusive):
            edge_bins.add(
                TemporalEdgeBin(
                    source_index=node_to_index[contact.frm],
                    target_index=node_to_index[contact.to],
                    time_index=time_index,
                )
            )

    edge_list = [
        [edge.source_index, edge.target_index, edge.time_index]
        for edge in sorted(edge_bins, key=lambda item: (item.time_index, item.source_index, item.target_index))
    ]
    temporal_array = np.zeros((len(ordered_nodes), len(ordered_nodes), total_bins), dtype=int)
    for source_index, target_index, time_index in edge_list:
        temporal_array[source_index, target_index, time_index] = 1

    time_labels = tuple(
        f"{start_time + time_index * time_step}-{min(end_time, start_time + (time_index + 1) * time_step)}"
        for time_index in range(total_bins)
    )

    communities = None
    if topology_path is not None:
        topology = topology_load(str(topology_path))
        communities = tuple(topology.get_network_for_node(node_id) for node_id in ordered_nodes)

    return TenetoContactPlanData(
        node_labels=tuple(str(node_id) for node_id in ordered_nodes),
        time_labels=time_labels,
        edge_list=edge_list,
        temporal_array=temporal_array,
        communities=communities,
        start_time=start_time,
        end_time=end_time,
        time_step=time_step,
    )


def plot_contact_plan_with_teneto(
    cp_path: str | Path,
    *,
    output_path: str | Path,
    topology_path: str | Path | None = None,
    time_step: int = 600,
    plot_kind: str = "slice",
    figsize: tuple[int, int] = (16, 8),
) -> Path:
    try:
        os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import teneto
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "teneto plotting requires optional dependencies. "
            "Install them with: pip install teneto matplotlib"
        ) from exc

    plot_kind_normalized = plot_kind.strip().lower().replace("_", "-")
    if plot_kind_normalized not in {"slice", "graphlet-stack"}:
        raise ValueError("plot_kind must be 'slice' or 'graphlet-stack'")
    if plot_kind_normalized == "graphlet-stack":
        raise ValueError(
            "plot_kind='graphlet-stack' is currently unsupported with this Teneto/Matplotlib version. "
            "Use plot_kind='slice'."
        )

    data = build_teneto_contact_plan_data(
        cp_path,
        topology_path=topology_path,
        time_step=time_step,
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=figsize)
    teneto.plot.slice_plot(
        data.temporal_array,
        ax,
        nodelabels=list(data.node_labels),
        timelabels=list(data.time_labels),
        communities=np.asarray(data.communities) if data.communities is not None else None,
        timeunit="s",
        nodesize=120,
        edgekwargs={"alpha": 0.35, "linewidth": 1.2},
        nodekwargs={"edgecolors": "black", "linewidths": 0.3},
    )

    ax.set_title(
        "Contact Plan Temporal Network\n"
        f"bins={len(data.time_labels)} step={data.time_step}s window={data.start_time}-{data.end_time}"
    )
    fig.tight_layout()
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)

    return output
