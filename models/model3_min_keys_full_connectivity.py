from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from models.common.coverage import require_full_coverage
from models.common.results import OptimizationResult
from models.common.runner import OptimizationBindings, connectivity_points, run_optimization
from pipelines.activation import ActivationProblem, attach_global_activation

if TYPE_CHECKING:
    import gurobipy as gp

from models.plot_utils import (
    palette_for,
    plot_gateway_usage_bar,
    plot_key_reuse_bar,
    plot_metric_bars_by_model,
    plot_network_crossing_bar,
)

def build(model: gp.Model, problem: ActivationProblem) -> OptimizationBindings:
    import gurobipy as gp
    from gurobipy import GRB

    activation = attach_global_activation(model, problem)
    require_full_coverage(activation)
    model.setObjective(gp.quicksum(activation.key_vars.values()), GRB.MINIMIZE)
    return OptimizationBindings(
        activation, fixed_point=connectivity_points((100,), len(problem.pairs))[0],
    )


def solve(problem: ActivationProblem, *, env: gp.Env | None = None) -> OptimizationResult:
    """Minimize key scopes with at least one route for every requested pair."""
    return run_optimization(
        problem, name="full_connectivity_min_keys", build=build,
        points=connectivity_points((100,), len(problem.pairs)), env=env,
    )


def plot_selected_keys_by_model(
    df: pd.DataFrame,
    *,
    ax=None,
    normalize: bool = True,
    title: str | None = None,
):
    return plot_metric_bars_by_model(
        df,
        y="selected_keys",
        ax=ax,
        palette=palette_for(df["model"]) if "model" in df else None,
        normalize_y=normalize,
        y_percent_scale=1.0 if normalize else None,
        y_label="Minimum keys" + (" (%)" if normalize else ""),
        title=title or "Minimum keys by model",
    )


def plot_selected_routes_by_model(
    df: pd.DataFrame,
    *,
    ax=None,
    normalize: bool = False,
    title: str | None = None,
):
    return plot_metric_bars_by_model(
        df,
        y="selected_routes",
        ax=ax,
        palette=palette_for(df["model"]) if "model" in df else None,
        normalize_y=normalize,
        y_percent_scale=1.0 if normalize else None,
        y_label="Selected routes" + (" (%)" if normalize else ""),
        title=title or "Selected routes by model",
    )


def plot_full_connectivity_key_reuse(
    trace,
    *,
    metric: str = "route_count",
    ax=None,
    title: str | None = None,
):
    return plot_key_reuse_bar(
        trace,
        metric=metric,
        ax=ax,
        title=title or "Key reuse in the optimal solution",
    )


def plot_full_connectivity_gateway_usage(
    trace,
    *,
    metric: str = "route_count",
    ax=None,
    title: str | None = None,
):
    return plot_gateway_usage_bar(
        trace,
        metric=metric,
        ax=ax,
        title=title or "Gateway usage in the optimal solution",
    )


def plot_full_connectivity_network_crossings(
    trace,
    *,
    metric: str = "crossing_count",
    ax=None,
    title: str | None = None,
):
    return plot_network_crossing_bar(
        trace,
        metric=metric,
        ax=ax,
        title=title or "Cross-network crossings in the optimal solution",
    )
