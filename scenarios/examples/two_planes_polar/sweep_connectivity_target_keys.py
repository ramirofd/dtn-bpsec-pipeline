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
    solve_min_keys_for_connectivity_target,
    write_multi_series_svg,
)


SCENARIO_DIR = Path(__file__).resolve().parent
RUN_RESULTS_DIR = SCENARIO_DIR / "results" / "run"
OUTPUT_DIR = SCENARIO_DIR / "results" / "sweep_connectivity_target_keys"
EXPORT_PATH = RUN_RESULTS_DIR / "pipeline_export.json"
CSV_PATH = OUTPUT_DIR / "connectivity_target_vs_keys.csv"
SVG_PATH = OUTPUT_DIR / "connectivity_target_vs_keys.svg"
TARGET_PCTS = tuple(range(0, 101, 5))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = build_datasets_from_export(EXPORT_PATH)
    rows: list[dict[str, int | float | str]] = []
    series_by_model: dict[SecurityModelType, list[tuple[float, float]]] = {
        model: [] for model in SecurityModelType
    }

    print(
        "sweep_config | export=%s target_pct_values=%s reachable_pairs=%d"
        % (
            EXPORT_PATH,
            list(TARGET_PCTS),
            len(next(iter(datasets.values())).pair_ids),
        )
    )

    for target_pct in TARGET_PCTS:
        row: dict[str, int | float | str] = {"target_connectivity_pct": target_pct}
        for model in SecurityModelType:
            summary = solve_min_keys_for_connectivity_target(
                datasets[model],
                target_connectivity_pct=float(target_pct),
            )
            row[f"{model.name.lower()}_required_pairs"] = summary.required_pairs
            row[f"{model.name.lower()}_selected_pairs"] = summary.selected_pairs
            row[f"{model.name.lower()}_selected_routes"] = summary.selected_routes
            row[f"{model.name.lower()}_selected_keys"] = summary.selected_keys
            row[f"{model.name.lower()}_achieved_connectivity_pct"] = round(summary.achieved_connectivity_pct, 4)
            series_by_model[model].append((float(target_pct), float(summary.selected_keys)))
            print(
                "sweep_point | model=%s target_pct=%d required_pairs=%d selected_keys=%d achieved_connectivity_pct=%.2f"
                % (
                    model.name.lower(),
                    target_pct,
                    summary.required_pairs,
                    summary.selected_keys,
                    summary.achieved_connectivity_pct,
                )
            )
        rows.append(row)

    _write_csv(rows)
    write_multi_series_svg(
        SVG_PATH,
        title="Minimum keys vs connectivity target",
        subtitle="Scenario two_planes_polar | objective: minimize keys for a target connectivity percentage",
        x_label="target_connectivity_pct",
        y_label="selected_keys",
        series_by_model=series_by_model,
        x_ticks=TARGET_PCTS,
        x_formatter=lambda value: f"{int(value)}%",
    )

    print(f"output | csv={CSV_PATH}")
    print(f"output | svg={SVG_PATH}")


def _write_csv(rows: list[dict[str, int | float | str]]) -> None:
    fieldnames = ["target_connectivity_pct"]
    for model in SecurityModelType:
        prefix = model.name.lower()
        fieldnames.extend(
            [
                f"{prefix}_required_pairs",
                f"{prefix}_selected_pairs",
                f"{prefix}_selected_routes",
                f"{prefix}_selected_keys",
                f"{prefix}_achieved_connectivity_pct",
            ]
        )

    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
