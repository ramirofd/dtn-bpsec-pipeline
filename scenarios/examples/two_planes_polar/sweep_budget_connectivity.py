from __future__ import annotations

import csv
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.security.models import SecurityModelType
from scenarios.examples.two_planes_polar.optimization_from_export import (
    build_datasets_from_export,
    solve_max_routes_with_budget,
    write_multi_series_svg,
)


SCENARIO_DIR = Path(__file__).resolve().parent
RUN_RESULTS_DIR = SCENARIO_DIR / "results" / "run"
OUTPUT_DIR = SCENARIO_DIR / "results" / "sweep_budget_connectivity"
EXPORT_PATH = RUN_RESULTS_DIR / "pipeline_export.json"
CSV_PATH = OUTPUT_DIR / "budget_vs_connectivity.csv"
SVG_PATH = OUTPUT_DIR / "budget_vs_connectivity.svg"
MAX_PLOT_BUDGET = 30


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = build_datasets_from_export(EXPORT_PATH)
    max_budget = max(len(dataset.key_scopes) for dataset in datasets.values())
    plot_budget = min(max_budget, MAX_PLOT_BUDGET)
    x_ticks = _budget_ticks(plot_budget)

    rows: list[dict[str, int | float | str]] = []
    series_by_model: dict[SecurityModelType, list[tuple[float, float]]] = {
        model: [] for model in SecurityModelType
    }

    print(
        "sweep_config | export=%s max_budget=%d reachable_pairs=%d"
        % (EXPORT_PATH, max_budget, len(next(iter(datasets.values())).pair_ids))
    )

    for max_keys in range(max_budget + 1):
        row: dict[str, int | float | str] = {"max_keys": max_keys}
        for model in SecurityModelType:
            summary = solve_max_routes_with_budget(datasets[model], max_keys=max_keys)
            row[f"{model.name.lower()}_connectivity_pct"] = round(summary.connectivity_pct, 4)
            row[f"{model.name.lower()}_selected_pairs"] = summary.selected_pairs
            row[f"{model.name.lower()}_selected_routes"] = summary.selected_routes
            row[f"{model.name.lower()}_selected_keys"] = summary.selected_keys
            series_by_model[model].append((float(max_keys), summary.connectivity_pct))
            print(
                "sweep_point | model=%s max_keys=%d selected_pairs=%d selected_routes=%d connectivity_pct=%.2f"
                % (
                    model.name.lower(),
                    max_keys,
                    summary.selected_pairs,
                    summary.selected_routes,
                    summary.connectivity_pct,
                )
            )
        rows.append(row)

    _write_csv(rows)
    plot_series_by_model = {
        model: [(x_value, y_value) for x_value, y_value in points if x_value <= plot_budget]
        for model, points in series_by_model.items()
    }

    write_multi_series_svg(
        SVG_PATH,
        title="Connectivity vs key budget",
        subtitle=(
            "Scenario two_planes_polar | objective: maximize routes under a key budget "
            f"| plotted range: 0-{plot_budget}"
        ),
        x_label="max_keys",
        y_label="connectivity_pct",
        series_by_model=plot_series_by_model,
        x_ticks=x_ticks,
        y_ticks=range(0, 101, 10),
        y_formatter=lambda value: f"{int(value)}%",
    )

    print(f"output | csv={CSV_PATH}")
    print(f"output | svg={SVG_PATH}")


def _write_csv(rows: list[dict[str, int | float | str]]) -> None:
    fieldnames = ["max_keys"]
    for model in SecurityModelType:
        prefix = model.name.lower()
        fieldnames.extend(
            [
                f"{prefix}_connectivity_pct",
                f"{prefix}_selected_pairs",
                f"{prefix}_selected_routes",
                f"{prefix}_selected_keys",
            ]
        )

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _budget_ticks(max_budget: int) -> list[int]:
    if max_budget <= 12:
        step = 1
    elif max_budget <= 24:
        step = 2
    elif max_budget <= 50:
        step = 5
    else:
        step = 10

    ticks = list(range(0, max_budget + 1, step))
    if ticks[-1] != max_budget:
        ticks.append(max_budget)
    return ticks


if __name__ == "__main__":
    main()
