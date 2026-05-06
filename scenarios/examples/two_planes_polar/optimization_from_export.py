from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Iterable

from modules.security.models import SecurityModelType


SERIES_COLORS = {
    SecurityModelType.HOP_BY_HOP: "#0f4c5c",
    SecurityModelType.END_TO_END: "#e36414",
    SecurityModelType.EDGE_BY_EDGE: "#6a994e",
    SecurityModelType.EDGE_TO_EDGE: "#8d0801",
}


@dataclass(slots=True, frozen=True)
class RouteOption:
    route_id: str
    pair_id: str
    required_key_scopes: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ModelDataset:
    model: SecurityModelType
    route_options: tuple[RouteOption, ...]
    pair_ids: tuple[str, ...]
    key_scopes: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class BudgetSweepSummary:
    selected_routes: int
    selected_pairs: int
    selected_keys: int
    connectivity_pct: float


@dataclass(slots=True, frozen=True)
class ConnectivityTargetSummary:
    required_pairs: int
    selected_pairs: int
    selected_routes: int
    selected_keys: int
    achieved_connectivity_pct: float


def build_datasets_from_export(
    export_path: str | Path,
) -> dict[SecurityModelType, ModelDataset]:
    payload = json.loads(Path(export_path).read_text(encoding="utf-8"))
    datasets: dict[SecurityModelType, ModelDataset] = {}

    for model in SecurityModelType:
        route_options: list[RouteOption] = []
        pair_ids: list[str] = []
        key_scopes: list[str] = []
        seen_pair_ids: set[str] = set()
        seen_key_scopes: set[str] = set()

        for pair_payload in payload["pairs"]:
            if pair_payload["route_count"] <= 0:
                continue

            pair_id = f'{pair_payload["source"]}->{pair_payload["destination"]}'
            if pair_id not in seen_pair_ids:
                pair_ids.append(pair_id)
                seen_pair_ids.add(pair_id)

            for route_payload in pair_payload["routes"]:
                requirements = route_payload["security_models"][model.name.lower()]["key_requirements"]
                required_key_scopes = _dedupe_scopes(requirements)
                route_options.append(
                    RouteOption(
                        route_id=f'{pair_id}:{route_payload["route_id"]}',
                        pair_id=pair_id,
                        required_key_scopes=required_key_scopes,
                    )
                )
                for scope in required_key_scopes:
                    if scope not in seen_key_scopes:
                        key_scopes.append(scope)
                        seen_key_scopes.add(scope)

        datasets[model] = ModelDataset(
            model=model,
            route_options=tuple(route_options),
            pair_ids=tuple(pair_ids),
            key_scopes=tuple(key_scopes),
        )

    return datasets


def solve_max_routes_with_budget(
    dataset: ModelDataset,
    *,
    max_keys: int,
) -> BudgetSweepSummary:
    import gurobipy as gp
    from gurobipy import GRB

    model = gp.Model(f"{dataset.model.name.lower()}_budget_sweep")
    model.setParam("OutputFlag", 0)

    route_vars = {
        route.route_id: model.addVar(vtype=GRB.BINARY, name=f"route[{_sanitize_name(route.route_id)}]")
        for route in dataset.route_options
    }
    key_vars = {
        scope: model.addVar(vtype=GRB.BINARY, name=f"key[{_sanitize_name(scope)}]")
        for scope in dataset.key_scopes
    }

    for route in dataset.route_options:
        lhs = gp.quicksum(key_vars[scope] for scope in route.required_key_scopes)
        rhs = len(route.required_key_scopes) * route_vars[route.route_id]
        model.addConstr(lhs >= rhs, name=f"route_requires_keys[{_sanitize_name(route.route_id)}]")

    model.addConstr(gp.quicksum(key_vars.values()) <= max_keys, name="max_active_keys")
    model.setObjective(gp.quicksum(route_vars.values()), GRB.MAXIMIZE)
    model.optimize()

    if model.SolCount == 0:
        return BudgetSweepSummary(
            selected_routes=0,
            selected_pairs=0,
            selected_keys=0,
            connectivity_pct=0.0,
        )

    selected_route_ids = {
        route_id
        for route_id, variable in route_vars.items()
        if variable.X > 0.5
    }
    selected_pairs = {
        route.pair_id
        for route in dataset.route_options
        if route.route_id in selected_route_ids
    }
    selected_keys = sum(1 for variable in key_vars.values() if variable.X > 0.5)

    connectivity_pct = _percentage(len(selected_pairs), len(dataset.pair_ids))
    return BudgetSweepSummary(
        selected_routes=len(selected_route_ids),
        selected_pairs=len(selected_pairs),
        selected_keys=selected_keys,
        connectivity_pct=connectivity_pct,
    )


def solve_min_keys_for_connectivity_target(
    dataset: ModelDataset,
    *,
    target_connectivity_pct: float,
) -> ConnectivityTargetSummary:
    import gurobipy as gp
    from gurobipy import GRB

    clamped_pct = min(max(target_connectivity_pct, 0.0), 100.0)
    required_pairs = ceil((clamped_pct / 100.0) * len(dataset.pair_ids))

    model = gp.Model(f"{dataset.model.name.lower()}_connectivity_target")
    model.setParam("OutputFlag", 0)

    route_vars = {
        route.route_id: model.addVar(vtype=GRB.BINARY, name=f"route[{_sanitize_name(route.route_id)}]")
        for route in dataset.route_options
    }
    key_vars = {
        scope: model.addVar(vtype=GRB.BINARY, name=f"key[{_sanitize_name(scope)}]")
        for scope in dataset.key_scopes
    }
    pair_vars = {
        pair_id: model.addVar(vtype=GRB.BINARY, name=f"pair[{_sanitize_name(pair_id)}]")
        for pair_id in dataset.pair_ids
    }

    routes_by_pair: dict[str, list[RouteOption]] = {pair_id: [] for pair_id in dataset.pair_ids}
    for route in dataset.route_options:
        routes_by_pair[route.pair_id].append(route)

    for route in dataset.route_options:
        lhs = gp.quicksum(key_vars[scope] for scope in route.required_key_scopes)
        rhs = len(route.required_key_scopes) * route_vars[route.route_id]
        model.addConstr(lhs >= rhs, name=f"route_requires_keys[{_sanitize_name(route.route_id)}]")
        model.addConstr(
            route_vars[route.route_id] <= pair_vars[route.pair_id],
            name=f"route_implies_pair[{_sanitize_name(route.route_id)}]",
        )

    for pair_id, pair_routes in routes_by_pair.items():
        model.addConstr(
            pair_vars[pair_id] <= gp.quicksum(route_vars[route.route_id] for route in pair_routes),
            name=f"pair_has_route[{_sanitize_name(pair_id)}]",
        )

    model.addConstr(
        gp.quicksum(pair_vars.values()) >= required_pairs,
        name="min_connectivity_pairs",
    )
    model.setObjective(gp.quicksum(key_vars.values()), GRB.MINIMIZE)
    model.optimize()

    if model.SolCount == 0:
        raise RuntimeError(
            f"no feasible solution for model={dataset.model.name.lower()} "
            f"target_connectivity_pct={clamped_pct}"
        )

    selected_route_ids = {
        route_id
        for route_id, variable in route_vars.items()
        if variable.X > 0.5
    }
    selected_pairs = sum(1 for variable in pair_vars.values() if variable.X > 0.5)
    selected_keys = sum(1 for variable in key_vars.values() if variable.X > 0.5)

    return ConnectivityTargetSummary(
        required_pairs=required_pairs,
        selected_pairs=selected_pairs,
        selected_routes=len(selected_route_ids),
        selected_keys=selected_keys,
        achieved_connectivity_pct=_percentage(selected_pairs, len(dataset.pair_ids)),
    )


def write_multi_series_svg(
    output_path: str | Path,
    *,
    title: str,
    subtitle: str,
    x_label: str,
    y_label: str,
    series_by_model: dict[SecurityModelType, list[tuple[float, float]]],
    x_ticks: Iterable[float],
    y_ticks: Iterable[float] | None = None,
    x_formatter=None,
    y_formatter=None,
) -> None:
    width = 960
    height = 560
    margin_left = 70
    margin_right = 30
    margin_top = 40
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    all_x_values = [x for points in series_by_model.values() for x, _ in points]
    all_y_values = [y for points in series_by_model.values() for _, y in points]
    max_x = max(max(all_x_values, default=1.0), 1.0)
    max_y = max(max(all_y_values, default=1.0), 1.0)

    def x_pos(value: float) -> float:
        return margin_left + (value / max_x) * plot_width

    def y_pos(value: float) -> float:
        return margin_top + plot_height - (value / max_y) * plot_height

    format_x = x_formatter or (lambda value: f"{value:g}")
    format_y = y_formatter or (lambda value: f"{value:g}")
    resolved_y_ticks = list(y_ticks) if y_ticks is not None else _default_y_ticks(max_y)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f8f7f4"/>',
        f'<text x="{margin_left}" y="24" font-family="Helvetica, Arial, sans-serif" font-size="20" fill="#222">{title}</text>',
        f'<text x="{margin_left}" y="46" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#555">{subtitle}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="#333" stroke-width="1.5"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="#333" stroke-width="1.5"/>',
    ]

    for x_tick in x_ticks:
        x = x_pos(x_tick)
        parts.append(
            f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.2f}" y="{height - 35}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#444">{format_x(x_tick)}</text>'
        )

    for y_tick in resolved_y_ticks:
        y = y_pos(y_tick)
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#ddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#444">{format_y(y_tick)}</text>'
        )

    parts.append(
        f'<text x="{margin_left + plot_width / 2:.2f}" y="{height - 10}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#222">{x_label}</text>'
    )
    parts.append(
        f'<text x="18" y="{margin_top + plot_height / 2:.2f}" transform="rotate(-90 18 {margin_top + plot_height / 2:.2f})" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="13" fill="#222">{y_label}</text>'
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
        for x_value, y_value in points:
            parts.append(
                f'<circle cx="{x_pos(x_value):.2f}" cy="{y_pos(y_value):.2f}" r="3.5" fill="{color}"/>'
            )
        legend_item_y = legend_y + index * 22
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_item_y}" x2="{legend_x + 24}" y2="{legend_item_y}" stroke="{color}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{legend_x + 32}" y="{legend_item_y + 4}" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="#222">{model.name.lower()}</text>'
        )

    parts.append("</svg>")
    Path(output_path).write_text("\n".join(parts), encoding="utf-8")


def _dedupe_scopes(requirements: list[dict]) -> tuple[str, ...]:
    scopes: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        scope = f'{requirement["key_type"]}:{requirement["source_id"]}->{requirement["target_id"]}'
        if scope not in seen:
            scopes.append(scope)
            seen.add(scope)
    return tuple(scopes)


def _sanitize_name(value: str) -> str:
    return (
        value.replace(":", "_")
        .replace("->", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _percentage(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return 100.0 * part / total


def _default_y_ticks(max_y: float) -> list[float]:
    if max_y <= 10:
        step = 1
    else:
        step = max(1, ceil(max_y / 10))
    ticks: list[float] = []
    value = 0.0
    while value <= max_y + 1e-9:
        ticks.append(value)
        value += step
    if ticks[-1] < max_y:
        ticks.append(max_y)
    return ticks
