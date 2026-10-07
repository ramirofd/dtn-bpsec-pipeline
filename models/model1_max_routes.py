from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from models.common.results import OptimizationResult
from models.common.runner import OptimizationBindings, budget_points, run_optimization
from pipelines.activation import ActivationProblem, attach_global_activation

if TYPE_CHECKING:
    import gurobipy as gp

from models.plot_utils import (
    palette_for,
    plot_contact_usage_heatmap,
    plot_gateway_usage_heatmap,
    plot_key_scope_heatmap,
    plot_metric_curve,
    plot_network_crossing_heatmap,
)


def build(model: gp.Model, problem: ActivationProblem) -> OptimizationBindings:
    import gurobipy as gp
    from gurobipy import GRB

    activation = attach_global_activation(model, problem)
    budget = model.addConstr(gp.quicksum(activation.key_vars.values()) <= 0, name="max_active_keys")
    model.setObjective(gp.quicksum(activation.route_vars.values()), GRB.MAXIMIZE)
    return OptimizationBindings(activation, budget)


def solve(
    problem: ActivationProblem, *, key_budgets: Iterable[int] | None = None,
    env: gp.Env | None = None,
) -> OptimizationResult:
    """Maximize enabled routes for each requested global-key budget."""
    return run_optimization(
        problem, name="budget_sweep", build=build,
        points=budget_points(key_budgets, len(problem.key_scopes)), env=env,
    )


def plot_selected_routes_vs_keys(
    df: pd.DataFrame,
    *,
    ax=None,
    normalize: bool = False,
    title: str | None = None,
):
    plot_df = df.sort_values("selected_keys")
    return plot_metric_curve(
        plot_df,
        x="selected_keys",
        y="selected_routes",
        ax=ax,
        sort_by="selected_keys",
        palette=palette_for(plot_df["model"]) if "model" in plot_df else None,
        normalize_x=normalize,
        normalize_y=normalize,
        x_percent_scale=1.0 if normalize else None,
        y_percent_scale=1.0 if normalize else None,
        x_label="Active keys" + (" (%)" if normalize else ""),
        y_label="Enabled routes" + (" (%)" if normalize else ""),
        title=title or "Enabled routes vs active keys",
    )


def plot_budget_key_scope_heatmap(
    traces_by_budget,
    *,
    ax=None,
    value_col: str = "selected",
    title: str | None = None,
):
    return plot_key_scope_heatmap(
        traces_by_budget,
        sweep_label="max_keys",
        value_col=value_col,
        ax=ax,
        x_label="Active keys",
        y_label="Key scope",
        title=title or "Key activation by budget",
    )


def plot_budget_contact_usage_heatmap(
    traces_by_budget,
    *,
    ax=None,
    value_col: str = "route_count",
    title: str | None = None,
):
    return plot_contact_usage_heatmap(
        traces_by_budget,
        sweep_label="max_keys",
        value_col=value_col,
        ax=ax,
        x_label="Active keys",
        y_label="Contact",
        title=title or "Contact usage by budget",
    )


def plot_budget_gateway_usage_heatmap(
    traces_by_budget,
    *,
    ax=None,
    value_col: str = "route_count",
    title: str | None = None,
):
    return plot_gateway_usage_heatmap(
        traces_by_budget,
        sweep_label="max_keys",
        value_col=value_col,
        ax=ax,
        x_label="Active keys",
        y_label="Gateway",
        title=title or "Gateway usage by budget",
    )


def plot_budget_network_crossing_heatmap(
    traces_by_budget,
    *,
    ax=None,
    value_col: str = "crossing_count",
    title: str | None = None,
):
    return plot_network_crossing_heatmap(
        traces_by_budget,
        sweep_label="max_keys",
        value_col=value_col,
        ax=ax,
        x_label="Active keys",
        y_label="Cross-network crossing",
        title=title or "Cross-network crossings by budget",
    )
