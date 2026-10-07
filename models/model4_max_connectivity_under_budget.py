from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

import pandas as pd

from models.common.coverage import attach_pair_coverage
from models.common.results import OptimizationResult
from models.common.runner import OptimizationBindings, budget_points, run_optimization
from pipelines.activation import ActivationProblem, attach_global_activation

if TYPE_CHECKING:
    import gurobipy as gp

from models.plot_utils import (
    palette_for,
    plot_contact_usage_heatmap,
    plot_key_scope_heatmap,
    plot_metric_curve,
    plot_network_crossing_heatmap,
    plot_pair_coverage_heatmap,
)

def build(model: gp.Model, problem: ActivationProblem) -> OptimizationBindings:
    import gurobipy as gp
    from gurobipy import GRB

    activation = attach_global_activation(model, problem)
    coverage = attach_pair_coverage(activation)
    budget = model.addConstr(gp.quicksum(activation.key_vars.values()) <= 0, name="max_active_keys")
    # Preserve the original priority: pairs, then fewer keys, then more routes.
    pair_weight = len(activation.key_vars) * (len(activation.route_vars) + 1) + len(activation.route_vars) + 1
    key_weight = len(activation.route_vars) + 1
    model.setObjective(
        pair_weight * coverage.covered_pair_count
        - key_weight * gp.quicksum(activation.key_vars.values())
        + gp.quicksum(activation.route_vars.values()),
        GRB.MAXIMIZE,
    )
    return OptimizationBindings(activation, budget)


def solve(
    problem: ActivationProblem, *, key_budgets: Iterable[int] | None = None,
    env: gp.Env | None = None,
) -> OptimizationResult:
    """Maximize pair coverage, keeping the original weighted tie breakers."""
    return run_optimization(
        problem, name="budget_connectivity_sweep", build=build,
        points=budget_points(key_budgets, len(problem.key_scopes)), env=env,
    )


def plot_connectivity_vs_budget(
    df: pd.DataFrame,
    *,
    ax=None,
    normalize_x: bool = True,
    title: str | None = None,
):
    plot_df = df.sort_values("max_keys")
    return plot_metric_curve(
        plot_df,
        x="max_keys",
        y="achieved_connectivity_pct",
        ax=ax,
        sort_by="max_keys",
        palette=palette_for(plot_df["model"]) if "model" in plot_df else None,
        normalize_x=normalize_x,
        x_percent_scale=1.0 if normalize_x else None,
        y_percent_scale=100,
        x_label="Active keys" + (" (%)" if normalize_x else ""),
        y_label="Achieved connectivity (%)",
        title=title or "Achieved connectivity vs active keys",
    )


def plot_budget_pair_coverage_heatmap(
    traces_by_budget,
    *,
    all_pairs=None,
    ax=None,
    title: str | None = None,
):
    return plot_pair_coverage_heatmap(
        traces_by_budget,
        sweep_label="max_keys",
        all_pairs=all_pairs,
        ax=ax,
        x_label="Active keys",
        y_label="Pair",
        title=title or "Pair coverage by budget",
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
