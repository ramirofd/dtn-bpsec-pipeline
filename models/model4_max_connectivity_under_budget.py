import gurobipy as gp
import pandas as pd
from gurobipy import GRB

from modules.security.models import SecurityModelType
from models.plot_utils import (
    palette_for,
    plot_contact_usage_heatmap,
    plot_key_scope_heatmap,
    plot_metric_curve,
    plot_network_crossing_heatmap,
    plot_pair_coverage_heatmap,
)
from pipelines.route_activation import (
    RouteActivationPlanner,
    attach_route_activation_constraints,
    trace_route_activation_solution,
)


def solve_for_security_model(result, security_model: SecurityModelType):
    planning = RouteActivationPlanner().build_for_model(
        result.security,
        model=security_model,
    )

    model = gp.Model(f"budget_connectivity_sweep_{security_model.name.lower()}")
    model.setParam("OutputFlag", 0)

    artifacts = attach_route_activation_constraints(model, planning)

    pair_ids = [f"{src}->{dst}" for src, dst in result.security.pairs]
    pair_vars = {
        pair_id: model.addVar(vtype=GRB.BINARY, name=f"pair[{pair_id}]")
        for pair_id in pair_ids
    }

    routes_by_pair = {pair_id: [] for pair_id in pair_ids}
    for route_id in artifacts.route_vars:
        pair_id = route_id.split(":")[0]
        routes_by_pair[pair_id].append(route_id)

    for route_id, route_var in artifacts.route_vars.items():
        pair_id = route_id.split(":")[0]
        model.addConstr(
            route_var <= pair_vars[pair_id],
            name=f"route_implies_pair[{route_id}]",
        )

    for pair_id, route_ids in routes_by_pair.items():
        model.addConstr(
            pair_vars[pair_id]
            <= gp.quicksum(artifacts.route_vars[route_id] for route_id in route_ids),
            name=f"pair_has_route[{pair_id}]",
        )

    budget_constr = model.addConstr(
        gp.quicksum(artifacts.key_vars.values()) <= 0,
        name="max_active_keys",
    )

    pair_weight = (
        len(artifacts.key_vars) * (len(artifacts.route_vars) + 1)
        + len(artifacts.route_vars)
        + 1
    )
    key_weight = len(artifacts.route_vars) + 1
    model.setObjective(
        pair_weight * gp.quicksum(pair_vars.values())
        - key_weight * gp.quicksum(artifacts.key_vars.values())
        + gp.quicksum(artifacts.route_vars.values()),
        GRB.MAXIMIZE,
    )

    sweep_rows = []
    trace_rows = []

    for max_keys in range(len(planning.key_scopes) + 1):
        budget_constr.RHS = max_keys
        model.optimize()

        if model.SolCount == 0:
            sweep_rows.append(
                {
                    "max_keys": max_keys,
                    "selected_pairs": 0,
                    "selected_routes": 0,
                    "selected_keys": 0,
                    "achieved_connectivity_pct": 0.0,
                }
            )
            trace_rows.append(None)
            continue

        selected_route_ids = {
            route_id
            for route_id, var in artifacts.route_vars.items()
            if var.X > 0.5
        }
        selected_pairs = sum(
            1 for var in pair_vars.values()
            if var.X > 0.5
        )
        selected_keys = sum(
            1 for var in artifacts.key_vars.values()
            if var.X > 0.5
        )

        sweep_rows.append(
            {
                "max_keys": max_keys,
                "selected_pairs": selected_pairs,
                "selected_routes": len(selected_route_ids),
                "selected_keys": selected_keys,
                "achieved_connectivity_pct": 100.0 * selected_pairs / len(pair_ids),
            }
        )
        trace_rows.append(
            trace_route_activation_solution(
                result,
                artifacts,
                security_model=security_model,
            )
        )

    new_df = pd.DataFrame(sweep_rows)
    new_df["model"] = security_model.name

    return tuple(trace_rows), new_df


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
