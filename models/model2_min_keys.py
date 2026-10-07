from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from models.common.coverage import attach_pair_coverage
from models.common.results import OptimizationResult
from models.common.runner import OptimizationBindings, connectivity_points, run_optimization
from pipelines.activation import ActivationProblem, attach_global_activation

if TYPE_CHECKING:
    import gurobipy as gp

from models.plot_utils import (
    format_model_series,
    model_display_order,
    palette_for,
    plot_contact_usage_heatmap,
    plot_key_scope_heatmap,
    plot_metric_bars_by_model,
    plot_metric_curve,
    plot_network_crossing_heatmap,
    plot_pair_coverage_heatmap,
)

def build(model: gp.Model, problem: ActivationProblem) -> OptimizationBindings:
    import gurobipy as gp
    from gurobipy import GRB

    activation = attach_global_activation(model, problem)
    coverage = attach_pair_coverage(activation)
    minimum = model.addConstr(coverage.covered_pair_count >= 0, name="min_connectivity_pairs")
    model.setObjective(gp.quicksum(activation.key_vars.values()), GRB.MINIMIZE)
    return OptimizationBindings(activation, minimum)


def solve(
    problem: ActivationProblem, *, target_connectivity_pcts: Iterable[float] = range(0, 101, 5),
    env: gp.Env | None = None,
) -> OptimizationResult:
    """Minimize distinct global key scopes for each connectivity target."""
    return run_optimization(
        problem, name="connectivity_sweep", build=build,
        points=connectivity_points(target_connectivity_pcts, len(problem.pairs)), env=env,
    )


def plot_selected_keys_vs_connectivity(
    df: pd.DataFrame,
    *,
    ax=None,
    normalize_y: bool = True,
    title: str | None = None,
):
    plot_df = df.sort_values("target_connectivity_pct")
    return plot_metric_curve(
        plot_df,
        x="target_connectivity_pct",
        y="selected_keys",
        ax=ax,
        sort_by="target_connectivity_pct",
        palette=palette_for(plot_df["model"]) if "model" in plot_df else None,
        normalize_y=normalize_y,
        x_percent_scale=100,
        y_percent_scale=1.0 if normalize_y else None,
        x_label="Target connectivity (%)",
        y_label="Minimum active keys" + (" (%)" if normalize_y else ""),
        title=title or "Minimum keys vs target connectivity",
    )


def plot_required_key_percentage_at_connectivity(
    df: pd.DataFrame,
    *,
    target_connectivity_pct: int = 100,
    ax=None,
    title: str | None = None,
):
    plot_df = df[df["target_connectivity_pct"] == target_connectivity_pct].copy()
    if plot_df.empty:
        return plot_metric_bars_by_model(
            pd.DataFrame(),
            y="selected_keys_pct_of_available",
            ax=ax,
        )

    if plot_df["selected_keys_pct_of_available"].isna().all():
        return plot_metric_bars_by_model(plot_df, y="selected_keys_pct_of_available", ax=ax)
    plot_df = plot_df.dropna(subset=["selected_keys_pct_of_available"])
    plot_df["model"] = pd.Categorical(
        format_model_series(plot_df["model"]),
        categories=model_display_order(plot_df["model"]),
        ordered=True,
    )
    plot_df = plot_df.sort_values("model")
    plot_df["model"] = plot_df["model"].astype(str)
    ax = plot_metric_bars_by_model(
        plot_df,
        y="selected_keys_pct_of_available",
        ax=ax,
        palette=palette_for(plot_df["model"]) if "model" in plot_df else None,
        y_percent_scale=100,
        y_label="Required keys (% of available scopes)",
        title=title
        or f"Required keys at {target_connectivity_pct}% connectivity",
    )

    for text in list(ax.texts):
        text.remove()

    for bar, row in zip(ax.patches, plot_df.itertuples(index=False), strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.0,
            (
                f"{row.selected_keys_pct_of_available:.1f}%\n"
                f"({int(row.selected_keys)}/{int(row.total_key_scopes)})"
            ),
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylim(0, max(plot_df["selected_keys_pct_of_available"].max() + 8.0, 100.0))
    return ax


def plot_connectivity_pair_coverage_heatmap(
    traces_by_connectivity,
    *,
    all_pairs=None,
    ax=None,
    title: str | None = None,
):
    return plot_pair_coverage_heatmap(
        traces_by_connectivity,
        sweep_label="target_connectivity_pct",
        all_pairs=all_pairs,
        ax=ax,
        x_label="Target connectivity (%)",
        y_label="Pair",
        title=title or "Pair coverage by target connectivity",
    )


def plot_connectivity_key_scope_heatmap(
    traces_by_connectivity,
    *,
    ax=None,
    value_col: str = "selected",
    title: str | None = None,
):
    return plot_key_scope_heatmap(
        traces_by_connectivity,
        sweep_label="target_connectivity_pct",
        value_col=value_col,
        ax=ax,
        x_label="Target connectivity (%)",
        y_label="Key scope",
        title=title or "Key activation by target connectivity",
    )


def plot_connectivity_contact_usage_heatmap(
    traces_by_connectivity,
    *,
    ax=None,
    value_col: str = "route_count",
    title: str | None = None,
):
    return plot_contact_usage_heatmap(
        traces_by_connectivity,
        sweep_label="target_connectivity_pct",
        value_col=value_col,
        ax=ax,
        x_label="Target connectivity (%)",
        y_label="Contact",
        title=title or "Contact usage by target connectivity",
    )


def plot_connectivity_network_crossing_heatmap(
    traces_by_connectivity,
    *,
    ax=None,
    value_col: str = "crossing_count",
    title: str | None = None,
):
    return plot_network_crossing_heatmap(
        traces_by_connectivity,
        sweep_label="target_connectivity_pct",
        value_col=value_col,
        ax=ax,
        x_label="Target connectivity (%)",
        y_label="Cross-network crossing",
        title=title or "Cross-network crossings by target connectivity",
    )
