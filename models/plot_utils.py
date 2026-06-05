"""Reusable plotting utilities for optimization results and trace selections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

import pandas as pd

from modules.security.keys import KeyScope
from modules.security.models import KeyType
from pipelines.route_activation import RouteActivationSelection

if TYPE_CHECKING:
    from matplotlib.axes import Axes


MODEL_PALETTE = {
    "HOP_BY_HOP": "#4c78a8",
    "END_TO_END": "#f58518",
    "EDGE_BY_EDGE": "#54a24b",
    "EDGE_TO_EDGE": "#e45756",
    "hop_by_hop": "#4c78a8",
    "end_to_end": "#f58518",
    "edge_by_edge": "#54a24b",
    "edge_to_edge": "#e45756",
    "hbh": "#4c78a8",
    "e2e": "#f58518",
    "ebe": "#54a24b",
    "ete": "#e45756",
}

KEY_TYPE_LABELS = {
    KeyType.NODE_TO_NODE: "N-N",
    KeyType.NODE_TO_GROUP: "N-G",
    KeyType.GROUP_TO_GROUP: "G-G",
}


def set_plot_theme(style: str = "whitegrid") -> None:
    """Apply the shared Seaborn theme used across the notebooks."""
    _, sns, _ = _load_plot_modules()
    sns.set_theme(style=style)


def palette_for(
    values: Sequence[str] | pd.Series,
    *,
    palette: Mapping[str, str] | None = None,
    default_color: str = "#4c78a8",
) -> dict[str, str]:
    """Build a stable palette for the provided labels."""
    resolved_palette = dict(MODEL_PALETTE)
    if palette is not None:
        resolved_palette.update(palette)
    unique_values = list(dict.fromkeys(str(value) for value in values))
    return {
        value: resolved_palette.get(value, default_color)
        for value in unique_values
    }


def format_key_scope(scope: KeyScope) -> str:
    return f"{KEY_TYPE_LABELS[scope.key_type]} {scope.source_id}->{scope.target_id}"


def format_pair_id(pair: tuple[int, int] | str) -> str:
    if isinstance(pair, str):
        return pair
    return f"{pair[0]}->{pair[1]}"


def ordered_trace_steps(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
) -> list[tuple[Any, RouteActivationSelection | None]]:
    """Normalize traces indexed either by mapping or by aligned sequences."""
    if isinstance(trace_steps, Mapping):
        return list(trace_steps.items())

    if sweep_values is None:
        sweep_values = tuple(range(len(trace_steps)))
    if len(trace_steps) != len(sweep_values):
        raise ValueError("trace sequence and sweep values must have the same length")

    return list(zip(sweep_values, trace_steps))


def build_key_scope_activation_data(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for step_value, trace in ordered_trace_steps(trace_steps, sweep_values=sweep_values):
        if trace is None:
            continue
        for key_selection in trace.keys:
            rows.append(
                {
                    sweep_label: step_value,
                    "key_scope": format_key_scope(key_selection.scope),
                    "key_type": KEY_TYPE_LABELS[key_selection.scope.key_type],
                    "selected": 1,
                    "route_count": len(key_selection.route_ids),
                    "pair_count": len(key_selection.pair_ids),
                    "operation_count": len(key_selection.operation_ids),
                }
            )
    return pd.DataFrame(rows)


def build_contact_usage_data(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for step_value, trace in ordered_trace_steps(trace_steps, sweep_values=sweep_values):
        if trace is None:
            continue

        contact_usage: dict[tuple[Any, ...], dict[str, Any]] = {}
        for route in trace.routes:
            for contact in route.contacts:
                key = (
                    contact.from_node,
                    contact.to_node,
                    contact.start,
                    contact.end,
                    contact.owlt,
                )
                entry = contact_usage.setdefault(
                    key,
                    {
                        "from_node": contact.from_node,
                        "to_node": contact.to_node,
                        "start": contact.start,
                        "end": contact.end,
                        "owlt": contact.owlt,
                        "from_network": contact.from_network,
                        "to_network": contact.to_network,
                        "crosses_network_boundary": contact.crosses_network_boundary,
                        "route_ids": set(),
                        "pair_ids": set(),
                        "usage_count": 0,
                    },
                )
                entry["usage_count"] += 1
                entry["route_ids"].add(route.route_id)
                entry["pair_ids"].add(route.pair_id)

        for entry in contact_usage.values():
            rows.append(
                {
                    sweep_label: step_value,
                    "contact": format_contact_label(
                        entry["from_node"],
                        entry["to_node"],
                        entry["start"],
                        entry["end"],
                        entry["owlt"],
                    ),
                    "from_node": entry["from_node"],
                    "to_node": entry["to_node"],
                    "start": entry["start"],
                    "end": entry["end"],
                    "owlt": entry["owlt"],
                    "from_network": entry["from_network"],
                    "to_network": entry["to_network"],
                    "crosses_network_boundary": entry["crosses_network_boundary"],
                    "route_count": len(entry["route_ids"]),
                    "pair_count": len(entry["pair_ids"]),
                    "usage_count": entry["usage_count"],
                }
            )
    return pd.DataFrame(rows)


def build_pair_coverage_data(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    all_pairs: Sequence[tuple[int, int] | str] | None = None,
) -> pd.DataFrame:
    normalized_steps = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    if all_pairs is None:
        all_pair_ids = _ordered_unique(
            format_pair_id(pair)
            for _, trace in normalized_steps
            if trace is not None
            for pair in trace.selected_pairs
        )
    else:
        all_pair_ids = [format_pair_id(pair) for pair in all_pairs]

    rows: list[dict[str, Any]] = []
    for step_value, trace in normalized_steps:
        selected_pair_ids = set()
        if trace is not None:
            selected_pair_ids = {format_pair_id(pair) for pair in trace.selected_pairs}
        for pair_id in all_pair_ids:
            rows.append(
                {
                    sweep_label: step_value,
                    "pair": pair_id,
                    "selected": 1 if pair_id in selected_pair_ids else 0,
                }
            )
    return pd.DataFrame(rows)


def build_gateway_usage_data(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for step_value, trace in ordered_trace_steps(trace_steps, sweep_values=sweep_values):
        if trace is None:
            continue

        gateway_usage: dict[int, dict[str, Any]] = {}
        for route in trace.routes:
            for gateway_node in route.gateway_nodes:
                entry = gateway_usage.setdefault(
                    gateway_node,
                    {
                        "route_ids": set(),
                        "pair_ids": set(),
                    },
                )
                entry["route_ids"].add(route.route_id)
                entry["pair_ids"].add(route.pair_id)

        for gateway_node, entry in gateway_usage.items():
            rows.append(
                {
                    sweep_label: step_value,
                    "gateway_node": gateway_node,
                    "route_count": len(entry["route_ids"]),
                    "pair_count": len(entry["pair_ids"]),
                }
            )
    return pd.DataFrame(rows)


def build_network_crossing_data(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for step_value, trace in ordered_trace_steps(trace_steps, sweep_values=sweep_values):
        if trace is None:
            continue

        crossing_usage: dict[str, dict[str, Any]] = {}
        for route in trace.routes:
            for crossing in route.boundary_crossings:
                label = f"{crossing.from_network}->{crossing.to_network}"
                entry = crossing_usage.setdefault(
                    label,
                    {
                        "from_network": crossing.from_network,
                        "to_network": crossing.to_network,
                        "route_ids": set(),
                        "pair_ids": set(),
                        "crossing_count": 0,
                    },
                )
                entry["route_ids"].add(route.route_id)
                entry["pair_ids"].add(route.pair_id)
                entry["crossing_count"] += 1

        for label, entry in crossing_usage.items():
            rows.append(
                {
                    sweep_label: step_value,
                    "crossing": label,
                    "from_network": entry["from_network"],
                    "to_network": entry["to_network"],
                    "route_count": len(entry["route_ids"]),
                    "pair_count": len(entry["pair_ids"]),
                    "crossing_count": entry["crossing_count"],
                }
            )
    return pd.DataFrame(rows)


def build_key_reuse_data(trace: RouteActivationSelection | None) -> pd.DataFrame:
    if trace is None:
        return pd.DataFrame()

    rows = [
        {
            "key_scope": format_key_scope(key_selection.scope),
            "key_type": KEY_TYPE_LABELS[key_selection.scope.key_type],
            "route_count": len(key_selection.route_ids),
            "pair_count": len(key_selection.pair_ids),
            "operation_count": len(key_selection.operation_ids),
        }
        for key_selection in trace.keys
    ]
    return pd.DataFrame(rows).sort_values(
        ["route_count", "pair_count", "operation_count", "key_scope"],
        ascending=[False, False, False, True],
    )


def plot_metric_curve(
    df: pd.DataFrame,
    *,
    x: str,
    y: str,
    ax: Axes | None = None,
    sort_by: str | list[str] | None = None,
    hue: str | None = "model",
    palette: Mapping[str, str] | None = None,
    normalize_x: bool = False,
    normalize_y: bool = False,
    x_percent_scale: float | None = None,
    y_percent_scale: float | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    title: str | None = None,
    linewidth: float = 2.0,
) -> Axes:
    if df.empty:
        return _empty_plot(ax, message="Sin datos para graficar.")

    _, sns, mtick = _load_plot_modules()
    ax = _resolve_ax(ax)

    plot_df = df.copy()
    if sort_by is not None:
        plot_df = plot_df.sort_values(sort_by)

    x_plot = x
    y_plot = y
    if normalize_x:
        x_plot = f"{x}_normalized"
        plot_df[x_plot] = _normalize_series(plot_df[x])
    if normalize_y:
        y_plot = f"{y}_normalized"
        plot_df[y_plot] = _normalize_series(plot_df[y])

    hue_arg = hue if hue and hue in plot_df and plot_df[hue].nunique() > 1 else None

    sns.lineplot(
        data=plot_df,
        x=x_plot,
        y=y_plot,
        hue=hue_arg,
        linewidth=linewidth,
        palette=palette,
        ax=ax,
    )

    ax.set_xlabel(x_label or x)
    ax.set_ylabel(y_label or y)
    if title:
        ax.set_title(title)
    if x_percent_scale is not None:
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(x_percent_scale))
    if y_percent_scale is not None:
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(y_percent_scale))
    return ax


def plot_metric_bars_by_model(
    df: pd.DataFrame,
    *,
    y: str,
    ax: Axes | None = None,
    palette: Mapping[str, str] | None = None,
    normalize_y: bool = False,
    y_percent_scale: float | None = None,
    x_label: str = "Modelo",
    y_label: str | None = None,
    title: str | None = None,
) -> Axes:
    if df.empty:
        return _empty_plot(ax, message="Sin datos para graficar.")

    _, sns, mtick = _load_plot_modules()
    ax = _resolve_ax(ax)

    plot_df = df.copy().sort_values(y)
    y_plot = y
    if normalize_y:
        y_plot = f"{y}_normalized"
        plot_df[y_plot] = _normalize_series(plot_df[y])

    plot_palette = palette or palette_for(plot_df["model"])
    sns.barplot(
        data=plot_df,
        x="model",
        y=y_plot,
        hue="model",
        dodge=False,
        palette=plot_palette,
        legend=False,
        ax=ax,
    )

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label or y)
    if title:
        ax.set_title(title)
    if y_percent_scale is not None:
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(y_percent_scale))
    _annotate_bars(ax, percent_scale=y_percent_scale)
    return ax


def plot_key_scope_heatmap(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    value_col: str = "selected",
    ax: Axes | None = None,
    cmap: str = "Blues",
    x_label: str | None = None,
    y_label: str = "Llave",
    title: str | None = None,
) -> Axes:
    items = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    data = build_key_scope_activation_data(
        dict(items),
        sweep_label=sweep_label,
    )
    return plot_heatmap_frame(
        data,
        x_col=sweep_label,
        y_col="key_scope",
        value_col=value_col,
        x_order=[step for step, _ in items],
        ax=ax,
        cmap=cmap,
        x_label=x_label or sweep_label,
        y_label=y_label,
        title=title,
    )


def plot_contact_usage_heatmap(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    value_col: str = "route_count",
    ax: Axes | None = None,
    cmap: str = "Blues",
    x_label: str | None = None,
    y_label: str = "Contacto",
    title: str | None = None,
) -> Axes:
    items = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    data = build_contact_usage_data(
        dict(items),
        sweep_label=sweep_label,
    )
    return plot_heatmap_frame(
        data,
        x_col=sweep_label,
        y_col="contact",
        value_col=value_col,
        x_order=[step for step, _ in items],
        ax=ax,
        cmap=cmap,
        x_label=x_label or sweep_label,
        y_label=y_label,
        title=title,
    )


def plot_pair_coverage_heatmap(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    all_pairs: Sequence[tuple[int, int] | str] | None = None,
    ax: Axes | None = None,
    cmap: str = "Greens",
    x_label: str | None = None,
    y_label: str = "Par",
    title: str | None = None,
) -> Axes:
    items = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    data = build_pair_coverage_data(
        dict(items),
        sweep_label=sweep_label,
        all_pairs=all_pairs,
    )
    return plot_heatmap_frame(
        data,
        x_col=sweep_label,
        y_col="pair",
        value_col="selected",
        x_order=[step for step, _ in items],
        ax=ax,
        cmap=cmap,
        x_label=x_label or sweep_label,
        y_label=y_label,
        title=title,
        vmin=0,
        vmax=1,
    )


def plot_gateway_usage_heatmap(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    value_col: str = "route_count",
    ax: Axes | None = None,
    cmap: str = "Purples",
    x_label: str | None = None,
    y_label: str = "Gateway",
    title: str | None = None,
) -> Axes:
    items = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    data = build_gateway_usage_data(
        dict(items),
        sweep_label=sweep_label,
    )
    return plot_heatmap_frame(
        data,
        x_col=sweep_label,
        y_col="gateway_node",
        value_col=value_col,
        x_order=[step for step, _ in items],
        ax=ax,
        cmap=cmap,
        x_label=x_label or sweep_label,
        y_label=y_label,
        title=title,
    )


def plot_network_crossing_heatmap(
    trace_steps: Mapping[Any, RouteActivationSelection | None]
    | Sequence[RouteActivationSelection | None],
    *,
    sweep_values: Sequence[Any] | None = None,
    sweep_label: str = "step",
    value_col: str = "crossing_count",
    ax: Axes | None = None,
    cmap: str = "Reds",
    x_label: str | None = None,
    y_label: str = "Cruce entre redes",
    title: str | None = None,
) -> Axes:
    items = ordered_trace_steps(trace_steps, sweep_values=sweep_values)
    data = build_network_crossing_data(
        dict(items),
        sweep_label=sweep_label,
    )
    return plot_heatmap_frame(
        data,
        x_col=sweep_label,
        y_col="crossing",
        value_col=value_col,
        x_order=[step for step, _ in items],
        ax=ax,
        cmap=cmap,
        x_label=x_label or sweep_label,
        y_label=y_label,
        title=title,
    )


def plot_key_reuse_bar(
    trace: RouteActivationSelection | None,
    *,
    metric: str = "route_count",
    ax: Axes | None = None,
    title: str | None = None,
    color: str = "#4c78a8",
) -> Axes:
    data = build_key_reuse_data(trace)
    return _plot_single_trace_bar(
        data,
        x_col="key_scope",
        y_col=metric,
        ax=ax,
        title=title,
        x_label="Llave",
        y_label=_metric_label(metric),
        color=color,
    )


def plot_gateway_usage_bar(
    trace: RouteActivationSelection | None,
    *,
    metric: str = "route_count",
    ax: Axes | None = None,
    title: str | None = None,
    color: str = "#7e57c2",
) -> Axes:
    data = build_gateway_usage_data([trace], sweep_values=["selected"])
    data = data.drop(columns=["step"], errors="ignore").sort_values(metric, ascending=False)
    return _plot_single_trace_bar(
        data,
        x_col="gateway_node",
        y_col=metric,
        ax=ax,
        title=title,
        x_label="Gateway",
        y_label=_metric_label(metric),
        color=color,
    )


def plot_network_crossing_bar(
    trace: RouteActivationSelection | None,
    *,
    metric: str = "crossing_count",
    ax: Axes | None = None,
    title: str | None = None,
    color: str = "#e45756",
) -> Axes:
    data = build_network_crossing_data([trace], sweep_values=["selected"])
    data = data.drop(columns=["step"], errors="ignore").sort_values(metric, ascending=False)
    return _plot_single_trace_bar(
        data,
        x_col="crossing",
        y_col=metric,
        ax=ax,
        title=title,
        x_label="Cruce entre redes",
        y_label=_metric_label(metric),
        color=color,
    )


def plot_heatmap_frame(
    data: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    value_col: str,
    ax: Axes | None = None,
    x_order: Sequence[Any] | None = None,
    y_order: Sequence[Any] | None = None,
    cmap: str = "Blues",
    x_label: str | None = None,
    y_label: str | None = None,
    title: str | None = None,
    vmin: float | None = 0,
    vmax: float | None = None,
) -> Axes:
    if data.empty:
        return _empty_plot(ax, message="Sin datos para graficar.")

    _, sns, _ = _load_plot_modules()

    pivot = data.pivot_table(
        index=y_col,
        columns=x_col,
        values=value_col,
        aggfunc="sum",
        fill_value=0,
    )
    if x_order is not None:
        pivot = pivot.reindex(columns=list(x_order), fill_value=0)
    if y_order is not None:
        pivot = pivot.reindex(index=list(y_order), fill_value=0)

    row_count, col_count = pivot.shape
    ax = _resolve_heatmap_ax(ax, row_count=row_count, col_count=col_count)
    linewidths = 0.0 if row_count > 120 or col_count > 40 else 0.3

    sns.heatmap(
        pivot,
        cmap=cmap,
        linewidths=linewidths,
        linecolor="#f1f5f9",
        ax=ax,
        vmin=vmin,
        vmax=vmax,
    )
    ax.set_xlabel(x_label or x_col)
    ax.set_ylabel(y_label or y_col)
    if title:
        ax.set_title(title)
    return ax


def format_contact_label(
    from_node: int,
    to_node: int,
    start: int,
    end: int,
    owlt: int,
) -> str:
    return f"{from_node}->{to_node} [{start}-{end}, owlt={owlt}]"


def _annotate_bars(ax: Axes, *, percent_scale: float | None = None) -> None:
    for patch in ax.patches:
        height = patch.get_height()
        if pd.isna(height):
            continue
        if percent_scale is None:
            label = f"{height:.0f}" if float(height).is_integer() else f"{height:.2f}"
        else:
            label = f"{height:.1%}"
        ax.text(
            patch.get_x() + patch.get_width() / 2.0,
            height,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )


def _plot_single_trace_bar(
    data: pd.DataFrame,
    *,
    x_col: str,
    y_col: str,
    ax: Axes | None = None,
    title: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    color: str = "#4c78a8",
) -> Axes:
    if data.empty:
        return _empty_plot(ax, message="La solucion no tiene trazas para mostrar.")

    _, sns, _ = _load_plot_modules()
    ax = _resolve_ax(ax)
    sns.barplot(data=data, x=x_col, y=y_col, color=color, ax=ax)
    ax.set_xlabel(x_label or x_col)
    ax.set_ylabel(y_label or y_col)
    if title:
        ax.set_title(title)
    _annotate_bars(ax)
    ax.tick_params(axis="x", rotation=45)
    return ax


def _empty_plot(ax: Axes | None, *, message: str) -> Axes:
    ax = _resolve_ax(ax)
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
    ax.set_axis_off()
    return ax


def _resolve_ax(ax: Axes | None) -> Axes:
    if ax is not None:
        return ax
    plt, _, _ = _load_plot_modules()
    _, resolved_ax = plt.subplots(figsize=(10, 6))
    return resolved_ax


def _resolve_heatmap_ax(
    ax: Axes | None,
    *,
    row_count: int,
    col_count: int,
) -> Axes:
    if ax is not None:
        return ax

    plt, _, _ = _load_plot_modules()
    width = min(18.0, max(10.0, 0.45 * col_count))
    height = min(18.0, max(6.0, 0.04 * row_count))
    _, resolved_ax = plt.subplots(figsize=(width, height))
    return resolved_ax


def _normalize_series(series: pd.Series) -> pd.Series:
    max_value = series.max()
    if max_value == 0:
        return pd.Series([0.0] * len(series), index=series.index)
    return series / max_value


def _metric_label(metric: str) -> str:
    return {
        "route_count": "Cantidad de rutas",
        "pair_count": "Cantidad de pares",
        "operation_count": "Cantidad de operaciones",
        "crossing_count": "Cantidad de cruces",
    }.get(metric, metric)


def _ordered_unique(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _load_plot_modules():
    import matplotlib.pyplot as plt
    import seaborn as sns
    import matplotlib.ticker as mtick

    return plt, sns, mtick


__all__ = [
    "MODEL_PALETTE",
    "KEY_TYPE_LABELS",
    "set_plot_theme",
    "palette_for",
    "format_key_scope",
    "format_pair_id",
    "ordered_trace_steps",
    "build_key_scope_activation_data",
    "build_contact_usage_data",
    "build_pair_coverage_data",
    "build_gateway_usage_data",
    "build_network_crossing_data",
    "build_key_reuse_data",
    "plot_metric_curve",
    "plot_metric_bars_by_model",
    "plot_key_scope_heatmap",
    "plot_contact_usage_heatmap",
    "plot_pair_coverage_heatmap",
    "plot_gateway_usage_heatmap",
    "plot_network_crossing_heatmap",
    "plot_key_reuse_bar",
    "plot_gateway_usage_bar",
    "plot_network_crossing_bar",
    "plot_heatmap_frame",
    "format_contact_label",
]
