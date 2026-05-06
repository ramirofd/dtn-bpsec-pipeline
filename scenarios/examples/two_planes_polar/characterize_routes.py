from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

MPL_CONFIG_DIR = Path(tempfile.gettempdir()) / "bpsec_keys_mplconfig"
MPL_CONFIG_DIR.mkdir(exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CONFIG_DIR))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


MODEL_ORDER = (
    "hop_by_hop",
    "end_to_end",
    "edge_by_edge",
    "edge_to_edge",
)

MODEL_COLORS = {
    "hop_by_hop": "#0f4c5c",
    "end_to_end": "#e36414",
    "edge_by_edge": "#6a994e",
    "edge_to_edge": "#8d0801",
}

FAMILY_ORDER = (
    "intra_no_crossing",
    "inter_single_crossing",
    "intra_round_trip",
)

FAMILY_LABELS = {
    "intra_no_crossing": "Intra-plane, no crossing",
    "inter_single_crossing": "Inter-plane, single crossing",
    "intra_round_trip": "Intra-plane, round trip",
}

FAMILY_COLORS = {
    "intra_no_crossing": "#355070",
    "inter_single_crossing": "#e56b6f",
    "intra_round_trip": "#6d597a",
}

SCENARIO_DIR = Path(__file__).resolve().parent
RUN_RESULTS_DIR = SCENARIO_DIR / "results" / "run"
DEFAULT_OUTPUT_DIR = SCENARIO_DIR / "results" / "characterize_routes"


@dataclass(slots=True, frozen=True)
class RouteRecord:
    pair_id: str
    source: int
    destination: int
    source_network: int
    destination_network: int
    pair_type: str
    route_count_for_pair: int
    route_id: str
    family: str
    network_signature: str
    network_path: tuple[int, ...]
    boundary_crossings: int
    hop_count: int
    best_delivery_time: float
    volume: float
    confidence: float
    metrics_by_model: dict[str, dict[str, float]]


def main() -> None:
    args = _parse_args()
    export_path = Path(args.export)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records, topology = load_route_records(export_path)

    summary_csv_path = output_dir / f"{args.prefix}_summary.csv"
    report_md_path = output_dir / f"{args.prefix}_report.md"
    routes_png_path = output_dir / f"{args.prefix}_routes.png"
    security_png_path = output_dir / f"{args.prefix}_security.png"
    cases_png_path = output_dir / f"{args.prefix}_cases.png"

    write_summary_csv(summary_csv_path, records)
    write_report(report_md_path, export_path, records, topology)
    plot_route_overview(routes_png_path, records)
    plot_security_overview(security_png_path, records)
    plot_case_comparisons(cases_png_path, records)

    print(f"input  | {export_path}")
    print(f"output | {summary_csv_path}")
    print(f"output | {report_md_path}")
    print(f"output | {routes_png_path}")
    print(f"output | {security_png_path}")
    print(f"output | {cases_png_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Characterize the routing and security results exported by "
            "the two_planes_polar scenario."
        )
    )
    parser.add_argument(
        "--export",
        default=str(RUN_RESULTS_DIR / "pipeline_export.json"),
        help="Path to the pipeline export JSON.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where the figures and summaries will be written.",
    )
    parser.add_argument(
        "--prefix",
        default="route_characterization",
        help="Prefix for generated files.",
    )
    return parser.parse_args()


def load_route_records(export_path: Path) -> tuple[list[RouteRecord], dict]:
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    topology = payload["topology"]
    node_to_network = {
        int(node_id): int(network_id)
        for node_id, network_id in topology["node_to_network"].items()
    }

    records: list[RouteRecord] = []
    for pair_payload in payload["pairs"]:
        source = int(pair_payload["source"])
        destination = int(pair_payload["destination"])
        source_network = node_to_network[source]
        destination_network = node_to_network[destination]
        pair_type = (
            "intra_plane"
            if source_network == destination_network
            else "inter_plane"
        )

        for route_payload in pair_payload["routes"]:
            network_path = tuple(int(value) for value in route_payload["network_path"])
            family = classify_route_family(network_path, route_payload["annotation"]["boundary_crossings"])
            metrics_by_model = {
                model_name: build_model_metrics(model_payload["key_requirements"], model_payload["operations"])
                for model_name, model_payload in route_payload["security_models"].items()
            }
            records.append(
                RouteRecord(
                    pair_id=f"{source}->{destination}",
                    source=source,
                    destination=destination,
                    source_network=source_network,
                    destination_network=destination_network,
                    pair_type=pair_type,
                    route_count_for_pair=int(pair_payload["route_count"]),
                    route_id=str(route_payload["route_id"]),
                    family=family,
                    network_signature=compress_network_signature(network_path),
                    network_path=network_path,
                    boundary_crossings=len(route_payload["annotation"]["boundary_crossings"]),
                    hop_count=int(route_payload["hop_count"]),
                    best_delivery_time=float(route_payload["best_delivery_time"]),
                    volume=float(route_payload["volume"]),
                    confidence=float(route_payload["confidence"]),
                    metrics_by_model=metrics_by_model,
                )
            )

    return records, topology


def build_model_metrics(key_requirements: list[dict], operations: list[dict]) -> dict[str, float]:
    unique_scopes = dedupe_key_scopes(key_requirements)
    return {
        "operations": float(len(operations)),
        "key_requirements": float(len(key_requirements)),
        "unique_key_scopes": float(len(unique_scopes)),
    }


def dedupe_key_scopes(requirements: list[dict]) -> tuple[str, ...]:
    scopes: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        scope = f'{requirement["key_type"]}:{requirement["source_id"]}->{requirement["target_id"]}'
        if scope not in seen:
            scopes.append(scope)
            seen.add(scope)
    return tuple(scopes)


def classify_route_family(network_path: tuple[int, ...], crossings: list[dict]) -> str:
    crossing_count = len(crossings)
    if crossing_count == 0:
        return "intra_no_crossing"
    if crossing_count == 1:
        return "inter_single_crossing"
    if network_path[0] == network_path[-1]:
        return "intra_round_trip"
    return "other"


def compress_network_signature(network_path: tuple[int, ...]) -> str:
    chunks: list[str] = []
    current = network_path[0]
    count = 1
    for value in network_path[1:]:
        if value == current:
            count += 1
            continue
        chunks.append(f"{current}x{count}")
        current = value
        count = 1
    chunks.append(f"{current}x{count}")
    return " -> ".join(chunks)


def write_summary_csv(output_path: Path, records: list[RouteRecord]) -> None:
    fieldnames = [
        "pair_id",
        "source",
        "destination",
        "source_network",
        "destination_network",
        "pair_type",
        "route_count_for_pair",
        "route_id",
        "family",
        "network_signature",
        "boundary_crossings",
        "hop_count",
        "best_delivery_time",
        "volume",
        "confidence",
    ]
    for model_name in MODEL_ORDER:
        fieldnames.extend(
            [
                f"{model_name}_operations",
                f"{model_name}_key_requirements",
                f"{model_name}_unique_key_scopes",
            ]
        )

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = {
                "pair_id": record.pair_id,
                "source": record.source,
                "destination": record.destination,
                "source_network": record.source_network,
                "destination_network": record.destination_network,
                "pair_type": record.pair_type,
                "route_count_for_pair": record.route_count_for_pair,
                "route_id": record.route_id,
                "family": record.family,
                "network_signature": record.network_signature,
                "boundary_crossings": record.boundary_crossings,
                "hop_count": record.hop_count,
                "best_delivery_time": record.best_delivery_time,
                "volume": record.volume,
                "confidence": record.confidence,
            }
            for model_name in MODEL_ORDER:
                metrics = record.metrics_by_model[model_name]
                row[f"{model_name}_operations"] = int(metrics["operations"])
                row[f"{model_name}_key_requirements"] = int(metrics["key_requirements"])
                row[f"{model_name}_unique_key_scopes"] = int(metrics["unique_key_scopes"])
            writer.writerow(row)


def write_report(output_path: Path, export_path: Path, records: list[RouteRecord], topology: dict) -> None:
    pair_to_routes: dict[str, list[RouteRecord]] = defaultdict(list)
    for record in records:
        pair_to_routes[record.pair_id].append(record)

    pair_type_counts = Counter(record.pair_type for record in _unique_pair_records(pair_to_routes))
    route_count_distribution = Counter(len(routes) for routes in pair_to_routes.values())
    family_counts = Counter(record.family for record in records)
    signature_counts = Counter(record.network_signature for record in records)

    lines = [
        "# Two Planes Polar Route Characterization",
        "",
        f"- Export analyzed: `{export_path}`",
        f"- Ordered node pairs: `{len(pair_to_routes)}`",
        f"- Route options: `{len(records)}`",
        f"- Networks: `{len(topology['network_to_nodes'])}`",
        "",
        "## Pair coverage",
        "",
    ]

    for pair_type, count in sorted(pair_type_counts.items()):
        lines.append(f"- `{pair_type}`: `{count}` ordered pairs")

    lines.extend(
        [
            "",
            "## Routes per pair",
            "",
        ]
    )
    for route_count, count in sorted(route_count_distribution.items()):
        lines.append(f"- `{count}` pairs have `{route_count}` route options")

    lines.extend(
        [
            "",
            "## Route families",
            "",
        ]
    )
    for family in FAMILY_ORDER:
        lines.append(
            f"- `{family}` ({FAMILY_LABELS[family]}): `{family_counts[family]}` routes"
        )

    lines.extend(
        [
            "",
            "## Most common network signatures",
            "",
        ]
    )
    for signature, count in signature_counts.most_common(8):
        lines.append(f"- `{signature}`: `{count}` routes")

    lines.extend(
        [
            "",
            "## Security cost by model",
            "",
        ]
    )

    for model_name in MODEL_ORDER:
        lines.append(f"### `{model_name}`")
        lines.append("")
        for family in FAMILY_ORDER:
            values = [record.metrics_by_model[model_name]["unique_key_scopes"] for record in records if record.family == family]
            if not values:
                continue
            lines.append(
                "- %s: avg scopes=`%.2f`, min=`%d`, max=`%d`"
                % (
                    FAMILY_LABELS[family],
                    mean(values),
                    int(min(values)),
                    int(max(values)),
                )
        )
        lines.append("")

    highlighted_cases = select_highlight_cases(records)
    lines.extend(
        [
            "## Highlighted route cases",
            "",
            "These are concrete routes that most affect model-to-model comparisons.",
            "",
        ]
    )
    for label, record in highlighted_cases:
        metrics = record.metrics_by_model
        lines.append(
            "- `%s`: pair=`%s`, route=`%s`, family=`%s`, signature=`%s`, hops=`%d`, delivery=`%.0f`, scopes hbh/e2e/ebe/ete=`%d/%d/%d/%d`"
            % (
                label,
                record.pair_id,
                record.route_id,
                record.family,
                record.network_signature,
                record.hop_count,
                record.best_delivery_time,
                int(metrics["hop_by_hop"]["unique_key_scopes"]),
                int(metrics["end_to_end"]["unique_key_scopes"]),
                int(metrics["edge_by_edge"]["unique_key_scopes"]),
                int(metrics["edge_to_edge"]["unique_key_scopes"]),
            )
        )

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _unique_pair_records(pair_to_routes: dict[str, list[RouteRecord]]) -> list[RouteRecord]:
    return [routes[0] for routes in pair_to_routes.values() if routes]


def plot_route_overview(output_path: Path, records: list[RouteRecord]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axes = plt.subplots(2, 2, figsize=(16, 11))
    figure.patch.set_facecolor("#f8f7f4")
    figure.suptitle("two_planes_polar | Route characterization", fontsize=18, y=0.98)

    pair_to_routes: dict[str, list[RouteRecord]] = defaultdict(list)
    for record in records:
        pair_to_routes[record.pair_id].append(record)

    pair_type_route_count = defaultdict(Counter)
    for routes in pair_to_routes.values():
        pair_type_route_count[routes[0].pair_type][len(routes)] += 1

    ax = axes[0, 0]
    x_positions = [0, 1]
    bottoms = [0, 0]
    route_count_levels = sorted({len(routes) for routes in pair_to_routes.values()})
    for route_count in route_count_levels:
        heights = [
            pair_type_route_count["intra_plane"][route_count],
            pair_type_route_count["inter_plane"][route_count],
        ]
        ax.bar(
            x_positions,
            heights,
            bottom=bottoms,
            width=0.55,
            label=f"{route_count} routes/pair",
            color="#355070" if route_count == 1 else "#b56576",
        )
        bottoms = [bottom + height for bottom, height in zip(bottoms, heights)]
    ax.set_title("Ordered pairs by available route count")
    ax.set_xticks(x_positions, ["Intra-plane", "Inter-plane"])
    ax.set_ylabel("Ordered pairs")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    signature_counts = Counter(record.network_signature for record in records)
    top_signatures = signature_counts.most_common(10)
    labels = [signature for signature, _ in reversed(top_signatures)]
    values = [count for _, count in reversed(top_signatures)]
    colors = []
    for label in labels:
        family = next(record.family for record in records if record.network_signature == label)
        colors.append(FAMILY_COLORS.get(family, "#999999"))
    ax.barh(labels, values, color=colors)
    ax.set_title("Most common network signatures")
    ax.set_xlabel("Routes")

    ax = axes[1, 0]
    family_hops = [
        [record.hop_count for record in records if record.family == family]
        for family in FAMILY_ORDER
    ]
    box = ax.boxplot(
        family_hops,
        patch_artist=True,
        tick_labels=[FAMILY_LABELS[family] for family in FAMILY_ORDER],
    )
    for patch, family in zip(box["boxes"], FAMILY_ORDER, strict=True):
        patch.set_facecolor(FAMILY_COLORS[family])
        patch.set_alpha(0.75)
    ax.set_title("Hop count by route family")
    ax.set_ylabel("Hops")
    ax.tick_params(axis="x", rotation=14)

    ax = axes[1, 1]
    for family in FAMILY_ORDER:
        family_records = [record for record in records if record.family == family]
        ax.scatter(
            [record.hop_count for record in family_records],
            [record.best_delivery_time for record in family_records],
            s=60,
            alpha=0.75,
            c=FAMILY_COLORS[family],
            label=FAMILY_LABELS[family],
            edgecolors="white",
            linewidths=0.5,
        )
    ax.set_title("Delivery time vs hop count")
    ax.set_xlabel("Hops")
    ax.set_ylabel("Best delivery time")
    ax.legend(frameon=False)

    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_security_overview(output_path: Path, records: list[RouteRecord]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axes = plt.subplots(2, 2, figsize=(14, 10))
    figure.patch.set_facecolor("#f8f7f4")
    figure.suptitle("two_planes_polar | Security characterization", fontsize=18, y=0.98)

    ax = axes[0, 0]
    x_positions = list(range(len(FAMILY_ORDER)))
    bar_width = 0.18
    offsets = [-1.5, -0.5, 0.5, 1.5]
    for offset, model_name in zip(offsets, MODEL_ORDER, strict=True):
        means = [
            mean(
                record.metrics_by_model[model_name]["unique_key_scopes"]
                for record in records
                if record.family == family
            )
            for family in FAMILY_ORDER
        ]
        ax.bar(
            [value + offset * bar_width for value in x_positions],
            means,
            width=bar_width,
            color=MODEL_COLORS[model_name],
            label=model_name,
        )
    ax.set_title("Average unique key scopes by route family")
    ax.set_xticks(x_positions, [FAMILY_LABELS[family] for family in FAMILY_ORDER])
    ax.set_ylabel("Unique key scopes")
    ax.tick_params(axis="x", rotation=14)
    ax.legend(frameon=False, ncols=2)

    ax = axes[0, 1]
    scope_counts = [
        [record.metrics_by_model[model_name]["unique_key_scopes"] for record in records]
        for model_name in MODEL_ORDER
    ]
    box = ax.boxplot(
        scope_counts,
        patch_artist=True,
        tick_labels=MODEL_ORDER,
    )
    for patch, model_name in zip(box["boxes"], MODEL_ORDER, strict=True):
        patch.set_facecolor(MODEL_COLORS[model_name])
        patch.set_alpha(0.75)
    ax.set_title("Distribution of unique key scopes")
    ax.set_ylabel("Unique key scopes")
    ax.tick_params(axis="x", rotation=14)

    ax = axes[1, 0]
    crossing_levels = sorted({record.boundary_crossings for record in records})
    matrix = []
    for model_name in MODEL_ORDER:
        row = []
        for crossing_count in crossing_levels:
            values = [
                record.metrics_by_model[model_name]["unique_key_scopes"]
                for record in records
                if record.boundary_crossings == crossing_count
            ]
            row.append(mean(values) if values else 0.0)
        matrix.append(row)
    heatmap = ax.imshow(matrix, cmap="YlOrRd", aspect="auto")
    ax.set_title("Average unique key scopes by boundary crossings")
    ax.set_xticks(range(len(crossing_levels)), crossing_levels)
    ax.set_yticks(range(len(MODEL_ORDER)), MODEL_ORDER)
    ax.set_xlabel("Boundary crossings")
    figure.colorbar(heatmap, ax=ax, fraction=0.05, pad=0.03)

    ax = axes[1, 1]
    for model_name in MODEL_ORDER:
        x_values = []
        y_values = []
        for family in FAMILY_ORDER:
            family_records = [record for record in records if record.family == family]
            x_values.append(
                mean(record.hop_count for record in family_records)
            )
            y_values.append(
                mean(record.metrics_by_model[model_name]["unique_key_scopes"] for record in family_records)
            )
        ax.plot(
            x_values,
            y_values,
            marker="o",
            markersize=8,
            linewidth=2.5,
            color=MODEL_COLORS[model_name],
            label=model_name,
        )
    ax.set_title("Average key scopes vs average hops")
    ax.set_xlabel("Average hops per route family")
    ax.set_ylabel("Average unique key scopes")
    ax.legend(frameon=False)

    figure.text(
        0.5,
        0.02,
        "Families: "
        + " | ".join(FAMILY_LABELS[family] for family in FAMILY_ORDER),
        ha="center",
        fontsize=10,
        color="#444444",
    )

    figure.subplots_adjust(
        left=0.07,
        right=0.97,
        top=0.90,
        bottom=0.10,
        wspace=0.24,
        hspace=0.25,
    )
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_case_comparisons(output_path: Path, records: list[RouteRecord]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axes = plt.subplots(2, 2, figsize=(16, 11))
    figure.patch.set_facecolor("#f8f7f4")
    figure.suptitle("two_planes_polar | Highlighted comparison cases", fontsize=18, y=0.98)

    highlighted = select_highlight_cases(records)
    highlighted_keys = {(record.pair_id, record.route_id) for _, record in highlighted}

    ax = axes[0, 0]
    for family in FAMILY_ORDER:
        family_records = [record for record in records if record.family == family]
        ax.scatter(
            [record.metrics_by_model["hop_by_hop"]["unique_key_scopes"] for record in family_records],
            [record.metrics_by_model["edge_to_edge"]["unique_key_scopes"] for record in family_records],
            s=42,
            alpha=0.45,
            c=FAMILY_COLORS[family],
            label=FAMILY_LABELS[family],
            edgecolors="none",
        )
    for label, record in highlighted:
        x_value = record.metrics_by_model["hop_by_hop"]["unique_key_scopes"]
        y_value = record.metrics_by_model["edge_to_edge"]["unique_key_scopes"]
        ax.scatter([x_value], [y_value], s=180, facecolors="none", edgecolors="#111111", linewidths=1.8)
        ax.annotate(label, (x_value, y_value), xytext=(6, 6), textcoords="offset points", fontsize=9, color="#111111")
    ax.set_title("Hop-by-hop vs edge-to-edge")
    ax.set_xlabel("Hop-by-hop unique key scopes")
    ax.set_ylabel("Edge-to-edge unique key scopes")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    for family in FAMILY_ORDER:
        family_records = [record for record in records if record.family == family]
        ax.scatter(
            [record.hop_count for record in family_records],
            [route_spread(record) for record in family_records],
            s=42,
            alpha=0.45,
            c=FAMILY_COLORS[family],
            edgecolors="none",
        )
    for label, record in highlighted:
        x_value = record.hop_count
        y_value = route_spread(record)
        ax.scatter([x_value], [y_value], s=180, facecolors="none", edgecolors="#111111", linewidths=1.8)
        ax.annotate(label, (x_value, y_value), xytext=(6, 6), textcoords="offset points", fontsize=9, color="#111111")
    ax.set_title("Model spread vs hops")
    ax.set_xlabel("Hop count")
    ax.set_ylabel("Spread across models")

    ax = axes[1, 0]
    labels = [label for label, _ in highlighted]
    hop_by_hop_vals = [int(record.metrics_by_model["hop_by_hop"]["unique_key_scopes"]) for _, record in highlighted]
    end_to_end_vals = [int(record.metrics_by_model["end_to_end"]["unique_key_scopes"]) for _, record in highlighted]
    edge_by_edge_vals = [int(record.metrics_by_model["edge_by_edge"]["unique_key_scopes"]) for _, record in highlighted]
    edge_to_edge_vals = [int(record.metrics_by_model["edge_to_edge"]["unique_key_scopes"]) for _, record in highlighted]
    positions = list(range(len(labels)))
    width = 0.18
    series = [
        ("hop_by_hop", hop_by_hop_vals, -1.5),
        ("end_to_end", end_to_end_vals, -0.5),
        ("edge_by_edge", edge_by_edge_vals, 0.5),
        ("edge_to_edge", edge_to_edge_vals, 1.5),
    ]
    for model_name, values, offset in series:
        ax.bar(
            [value + offset * width for value in positions],
            values,
            width=width,
            color=MODEL_COLORS[model_name],
            label=model_name,
        )
    ax.set_title("Security cost for highlighted cases")
    ax.set_xticks(positions, labels)
    ax.set_ylabel("Unique key scopes")
    ax.legend(frameon=False, ncols=2)

    ax = axes[1, 1]
    ax.axis("off")
    text_lines = []
    for label, record in highlighted:
        text_lines.append(
            "%s | %s %s | hops=%d | sig=%s"
            % (label, record.pair_id, record.route_id, record.hop_count, record.network_signature)
        )
    ax.text(
        0.0,
        1.0,
        "\n".join(text_lines),
        va="top",
        ha="left",
        fontsize=10.5,
        family="monospace",
        color="#222222",
    )
    ax.set_title("Case legend", loc="left")

    figure.tight_layout(rect=(0, 0, 1, 0.96))
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def route_spread(record: RouteRecord) -> int:
    values = [
        int(record.metrics_by_model[model_name]["unique_key_scopes"])
        for model_name in MODEL_ORDER
    ]
    return max(values) - min(values)


def select_highlight_cases(records: list[RouteRecord]) -> list[tuple[str, RouteRecord]]:
    selectors = [
        lambda blocked: select_case(
            records,
            blocked,
            predicate=lambda record: True,
            ranking=lambda record: (
                route_spread(record),
                record.hop_count,
                record.best_delivery_time,
            ),
            reverse=True,
        ),
        lambda blocked: select_case(
            records,
            blocked,
            predicate=lambda record: record.family == "intra_round_trip",
            ranking=lambda record: (
                int(record.metrics_by_model["edge_by_edge"]["unique_key_scopes"])
                - int(record.metrics_by_model["edge_to_edge"]["unique_key_scopes"]),
                route_spread(record),
                record.hop_count,
                record.best_delivery_time,
            ),
            reverse=True,
        ),
        lambda blocked: select_case(
            records,
            blocked,
            predicate=lambda record: record.family == "inter_single_crossing",
            ranking=lambda record: (
                route_spread(record),
                record.hop_count,
                -record.best_delivery_time,
            ),
            reverse=True,
        ),
        lambda blocked: select_case(
            records,
            blocked,
            predicate=lambda record: record.family == "inter_single_crossing",
            ranking=lambda record: (
                route_spread(record),
                record.hop_count,
                record.best_delivery_time,
            ),
            reverse=False,
        ),
    ]

    selected_records: list[RouteRecord] = []
    blocked: set[tuple[str, str]] = set()
    for selector in selectors:
        record = selector(blocked)
        if record is None:
            continue
        selected_records.append(record)
        blocked.add((record.pair_id, record.route_id))

    labels = ("A", "B", "C", "D", "E", "F")
    return list(zip(labels, selected_records, strict=False))


def select_case(
    records: list[RouteRecord],
    blocked: set[tuple[str, str]],
    *,
    predicate,
    ranking,
    reverse: bool,
) -> RouteRecord | None:
    filtered = [
        record
        for record in records
        if predicate(record) and (record.pair_id, record.route_id) not in blocked
    ]
    if not filtered:
        return None
    return sorted(filtered, key=ranking, reverse=reverse)[0]


if __name__ == "__main__":
    main()
