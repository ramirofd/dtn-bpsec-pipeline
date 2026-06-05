from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import ListedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from modules.network.cgr.loader import cp_load
from modules.network.cgr.models import Contact
from modules.network.topology import Topology, topology_load


NETWORK_COLORS = (
    "#2563eb",
    "#f59e0b",
    "#10b981",
    "#ef4444",
    "#06b6d4",
    "#84cc16",
    "#f97316",
    "#14b8a6",
)


def plot_temporal_graph(
    *,
    contact_plan: str | Path | Sequence[Contact] | Sequence[Mapping[str, Any]],
    topology: str | Path | Topology | Sequence[Mapping[str, Any]] | Mapping[str, Any],
    title: str | None = None,
    output_path: str | Path | None = None,
    figsize: tuple[float, float] | None = None,
    nodesize: int = 30,
    edge_alpha: float = 0.5,
    edge_linewidth: float = 1.0,
    label_fontsize: float = 11,
    title_fontsize: float = 16,
    legend_fontsize: float = 11,
    legend_title: str = "Network Groups",
    network_label_prefix: str = "Network",
    dpi: int = 160,
) -> tuple[Figure, Axes]:
    """Render a temporal contact graph grouped by network.

    This function is designed for notebook usage and accepts either file paths
    or already-loaded topology/contact-plan objects.
    """

    resolved_contacts = _resolve_contact_plan(contact_plan)
    network_entries = _resolve_topology_entries(topology)
    node_ids = _build_node_order(network_entries)
    time_bins = _build_time_bins(resolved_contacts)
    temporal_array = _build_temporal_array(
        contacts=resolved_contacts,
        time_bins=time_bins,
        node_ids=node_ids,
    )
    network_by_node = _build_network_lookup(network_entries)
    community_index_by_network, cmap = _build_network_styles(list({*network_by_node.values()}))
    resolved_figsize = figsize or _resolve_figure_size(
        num_time_bins=len(time_bins),
        num_nodes=len(node_ids),
    )
    communities = np.array(
        [community_index_by_network[network_by_node[node_id]] for node_id in node_ids],
        dtype=int,
    )
    color_by_network = {
        network_id: cmap.colors[color_index]
        for network_id, color_index in community_index_by_network.items()
    }

    try:
        from teneto import TemporalNetwork
    except ImportError as exc:
        raise RuntimeError(
            "plot_temporal_graph requires the optional 'teneto' dependency to be installed."
        ) from exc

    network = TemporalNetwork()
    network.network_from_array(temporal_array, forcesparse=True)

    fig, ax = plt.subplots(figsize=resolved_figsize, dpi=dpi)
    network.plot(
        "slice_plot",
        ax=ax,
        nodelabels=[str(node_id) for node_id in node_ids],
        timelabels=[f"{start}-{end}" for start, end in time_bins],
        communities=communities,
        cmap=cmap,
        linestyle="-",
        nodesize=nodesize,
        nodekwargs={"edgecolors": "#0f172a", "linewidths": 0.25},
        edgekwargs={"alpha": edge_alpha, "linewidth": edge_linewidth, "color": "#2563eb"},
    )
    _style_network_groups(ax, network_entries, color_by_network)
    ax.set_facecolor("#ffffff")
    ax.set_axisbelow(True)
    ax.grid(
        visible=True,
        axis="x",
        color="#cbd5e1",
        linestyle="--",
        linewidth=0.8,
        alpha=0.85,
    )
    ax.grid(
        visible=True,
        axis="y",
        color="#e2e8f0",
        linestyle=":",
        linewidth=0.6,
        alpha=0.75,
    )
    legend_handles = [
        Patch(
            facecolor=color_by_network[entry["id"]],
            edgecolor="#0f172a",
            label=f"{network_label_prefix} {entry['id']}",
        )
        for entry in network_entries
    ]
    ax.legend(
        handles=legend_handles,
        title=legend_title,
        loc="upper right",
        frameon=False,
        fontsize=legend_fontsize,
        title_fontsize=legend_fontsize + 1,
        borderaxespad=0.4,
    )
    ax.set_title(title or "Temporal Contact Graph", fontsize=title_fontsize, pad=12)
    ax.set_xlabel(ax.get_xlabel() or "Time", fontsize=label_fontsize + 1)
    ax.tick_params(axis="x", labelsize=label_fontsize)
    ax.tick_params(axis="y", labelsize=label_fontsize)
    plt.xticks(rotation=35, ha="right")
    plt.tight_layout(pad=1.1)

    if output_path is not None:
        fig.savefig(output_path, dpi=dpi, bbox_inches="tight")

    return fig, ax


def _resolve_figure_size(*, num_time_bins: int, num_nodes: int) -> tuple[float, float]:
    """Pick a compact figure size that keeps labels readable when embedded in docs."""

    width = min(14.0, max(9.5, 4.5 + num_time_bins * 1.4))
    height = min(12.0, max(7.0, 4.0 + num_nodes * 0.28))
    return (width, height)


def _resolve_contact_plan(
    contact_plan: str | Path | Sequence[Contact] | Sequence[Mapping[str, Any]],
) -> list[Contact]:
    if isinstance(contact_plan, (str, Path)):
        return cp_load(str(contact_plan))

    resolved_contacts: list[Contact] = []
    for item in contact_plan:
        if isinstance(item, Contact):
            resolved_contacts.append(item)
            continue

        resolved_contacts.append(
            Contact(
                frm=int(item["from"]),
                to=int(item["to"]),
                start=int(item["start"]),
                end=int(item["end"]),
                rate=int(item["rate"]),
                owlt=int(item.get("owlt", 0)),
            )
        )

    if not resolved_contacts:
        raise ValueError("contact plan must contain at least one contact")

    return resolved_contacts


def _resolve_topology_entries(
    topology: str | Path | Topology | Sequence[Mapping[str, Any]] | Mapping[str, Any],
) -> list[dict[str, Any]]:
    if isinstance(topology, (str, Path)):
        resolved_topology = topology_load(str(topology))
        return _topology_to_entries(resolved_topology)

    if isinstance(topology, Topology):
        return _topology_to_entries(topology)

    if isinstance(topology, Mapping):
        raw_entries = topology["networks"]
    else:
        raw_entries = topology

    entries = [
        {
            "id": int(entry["id"]),
            "nodes": sorted(int(node_id) for node_id in entry["nodes"]),
        }
        for entry in raw_entries
    ]
    if not entries:
        raise ValueError("topology must contain at least one network")
    return sorted(entries, key=lambda entry: entry["id"])


def _topology_to_entries(topology: Topology) -> list[dict[str, Any]]:
    entries = [
        {
            "id": int(network_id),
            "nodes": sorted(int(node_id) for node_id in topology.get_nodes_for_network(network_id)),
        }
        for network_id in sorted(topology.network_to_nodes)
    ]
    if not entries:
        raise ValueError("topology must contain at least one network")
    return entries


def _build_node_order(network_entries: Sequence[Mapping[str, Any]]) -> list[int]:
    node_ids: list[int] = []
    seen_nodes: set[int] = set()

    for entry in network_entries:
        for node_id in entry["nodes"]:
            if node_id in seen_nodes:
                raise ValueError(f"node {node_id} appears in multiple networks")
            seen_nodes.add(node_id)
            node_ids.append(int(node_id))

    if not node_ids:
        raise ValueError("topology must contain at least one node")

    return node_ids


def _build_time_bins(contacts: Sequence[Contact]) -> list[tuple[int, int]]:
    boundaries = sorted({contact.start for contact in contacts} | {contact.end for contact in contacts})
    if len(boundaries) < 2:
        raise ValueError("contact plan must define at least one non-empty time interval")
    return list(zip(boundaries[:-1], boundaries[1:]))


def _build_temporal_array(
    *,
    contacts: Sequence[Contact],
    time_bins: Sequence[tuple[int, int]],
    node_ids: Sequence[int],
) -> np.ndarray:
    node_index_by_id = {node_id: index for index, node_id in enumerate(node_ids)}
    temporal_array = np.zeros((len(node_ids), len(node_ids), len(time_bins)), dtype=int)

    for contact in contacts:
        if contact.frm not in node_index_by_id or contact.to not in node_index_by_id:
            raise ValueError(
                f"contact {contact.frm}->{contact.to} references nodes that are not present in topology"
            )

    for time_index, (start, end) in enumerate(time_bins):
        midpoint = (start + end) / 2
        for contact in contacts:
            if contact.start <= midpoint < contact.end:
                source_index = node_index_by_id[contact.frm]
                target_index = node_index_by_id[contact.to]
                temporal_array[source_index, target_index, time_index] = 1

    return temporal_array


def _build_network_lookup(network_entries: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    network_by_node: dict[int, int] = {}
    for entry in network_entries:
        network_id = int(entry["id"])
        for node_id in entry["nodes"]:
            network_by_node[int(node_id)] = network_id
    return network_by_node


def _build_network_styles(network_ids: Sequence[int]) -> tuple[dict[int, int], ListedColormap]:
    sorted_ids = sorted(network_ids)
    color_indexes = {network_id: index for index, network_id in enumerate(sorted_ids)}
    colors = [NETWORK_COLORS[index % len(NETWORK_COLORS)] for index in range(len(sorted_ids))]
    return color_indexes, ListedColormap(colors)


def _style_network_groups(
    ax: Axes,
    network_entries: Sequence[Mapping[str, Any]],
    color_by_network: Mapping[int, Any],
) -> None:
    ytick_labels = {int(label.get_text()): label for label in ax.get_yticklabels() if label.get_text().isdigit()}

    offset = 0
    for entry in network_entries:
        network_id = int(entry["id"])
        nodes = [int(node_id) for node_id in entry["nodes"]]
        color = color_by_network[network_id]

        ax.axhspan(
            offset - 0.5,
            offset + len(nodes) - 0.5,
            color=color,
            alpha=0.035,
            zorder=-2,
        )

        for node_id in nodes:
            label = ytick_labels.get(node_id)
            if label is not None:
                label.set_color(color)
                label.set_fontweight("bold")

        offset += len(nodes)
        if offset < len(ytick_labels):
            ax.axhline(offset - 0.5, color="#cbd5e1", linewidth=1.0, linestyle="--", alpha=0.9, zorder=-1)
