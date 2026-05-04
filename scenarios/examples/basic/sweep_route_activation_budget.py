from __future__ import annotations

import csv
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.security.models import SecurityModelType
from scenarios.examples.basic.optimize_route_activation import (
    DEFAULT_CURR_TIME,
    DEFAULT_NUM_ROUTES,
    solve_route_activation_for_model,
)


OUTPUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUTPUT_DIR / "route_activation_budget.csv"
SVG_PATH = OUTPUT_DIR / "route_activation_budget.svg"

SERIES_COLORS = {
    SecurityModelType.HOP_BY_HOP: "#0f4c5c",
    SecurityModelType.END_TO_END: "#e36414",
    SecurityModelType.EDGE_BY_EDGE: "#6a994e",
    SecurityModelType.EDGE_TO_EDGE: "#8d0801",
}


def main() -> None:
    max_budget = _compute_max_budget()
    rows: list[dict[str, int | str]] = []
    series_by_model: dict[SecurityModelType, list[tuple[int, int]]] = {
        model: [] for model in SecurityModelType
    }

    print(
        "sweep_config | curr_time=%d num_routes=%d max_budget=%d"
        % (DEFAULT_CURR_TIME, DEFAULT_NUM_ROUTES, max_budget)
    )

    for max_keys in range(max_budget + 1):
        budget_summary = {"max_keys": max_keys}
        for model in SecurityModelType:
            summary = solve_route_activation_for_model(
                model,
                max_keys=max_keys,
                curr_time=DEFAULT_CURR_TIME,
                num_routes=DEFAULT_NUM_ROUTES,
            )
            budget_summary[model.name.lower()] = summary.selected_routes
            series_by_model[model].append((max_keys, summary.selected_routes))
            print(
                "sweep_point | model=%s max_keys=%d selected_routes=%d objective=%d"
                % (
                    model.name.lower(),
                    max_keys,
                    summary.selected_routes,
                    summary.objective,
                )
            )
        rows.append(budget_summary)

    _write_csv(rows)
    _write_svg(series_by_model, max_budget=max_budget)

    print(f"output | csv={CSV_PATH}")
    print(f"output | svg={SVG_PATH}")


def _compute_max_budget() -> int:
    max_budget = 0
    for model in SecurityModelType:
        summary = solve_route_activation_for_model(
            model,
            max_keys=10_000,
            curr_time=DEFAULT_CURR_TIME,
            num_routes=DEFAULT_NUM_ROUTES,
        )
        if summary.unique_keys > max_budget:
            max_budget = summary.unique_keys
    return max_budget


def _write_csv(rows: list[dict[str, int | str]]) -> None:
    fieldnames = ["max_keys"] + [model.name.lower() for model in SecurityModelType]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_svg(
    series_by_model: dict[SecurityModelType, list[tuple[int, int]]],
    *,
    max_budget: int,
) -> None:
    width = 960
    height = 560
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    max_selected_routes = max(
        max((value for _, value in points), default=0)
        for points in series_by_model.values()
    )
    max_x = max(max_budget, 1)
    max_y = max(max_selected_routes, 1)

    def x_pos(value: int) -> float:
        return margin_left + (value / max_x) * plot_width

    def y_pos(value: int) -> float:
        return margin_top + plot_height - (value / max_y) * plot_height

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f7f4"/>',
        '<text x="70" y="24" font-family="Helvetica, Arial, sans-serif" font-size="20" fill="#222">',
        'Route activation vs key budget',
        "</text>",
        '<text x="70" y="46" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#555">',
        f"Scenario basic | curr_time={DEFAULT_CURR_TIME} | num_routes={DEFAULT_NUM_ROUTES}",
        "</text>",
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#333" stroke-width="1.5"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#333" stroke-width="1.5"/>',
    ]

    for x_tick in range(max_budget + 1):
        x = x_pos(x_tick)
        parts.append(
            f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.2f}" y="{height - 35}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#444">{x_tick}</text>'
        )

    y_step = max(1, (max_selected_routes + 9) // 10)
    for y_tick in range(0, max_selected_routes + 1, y_step):
        y = y_pos(y_tick)
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#444">{y_tick}</text>'
        )

    parts.append(
        f'<text x="{margin_left + plot_width / 2:.2f}" y="{height - 10}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#222">max_keys</text>'
    )
    parts.append(
        f'<text x="18" y="{margin_top + plot_height / 2:.2f}" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#222">selected_routes</text>'
    )

    legend_x = margin_left + plot_width - 170
    legend_y = margin_top + 10

    for index, model in enumerate(SecurityModelType):
        color = SERIES_COLORS[model]
        points = series_by_model[model]
        polyline = " ".join(f"{x_pos(x):.2f},{y_pos(y):.2f}" for x, y in points)
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{polyline}"/>'
        )
        for x, y in points:
            parts.append(
                f'<circle cx="{x_pos(x):.2f}" cy="{y_pos(y):.2f}" r="3.5" fill="{color}"/>'
            )
        legend_item_y = legend_y + index * 22
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_item_y}" x2="{legend_x + 24}" y2="{legend_item_y}" stroke="{color}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{legend_x + 32}" y="{legend_item_y + 4}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#222">{model.name.lower()}</text>'
        )

    parts.append("</svg>")
    SVG_PATH.write_text("\n".join(parts), encoding="utf-8")


if __name__ == "__main__":
    main()
