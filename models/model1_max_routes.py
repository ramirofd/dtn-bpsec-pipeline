import gurobipy as gp
import pandas as pd
from gurobipy import GRB
from modules.security.models import SecurityModelType
from models.plot_utils import (
    palette_for,
    plot_contact_usage_heatmap,
    plot_gateway_usage_heatmap,
    plot_key_scope_heatmap,
    plot_metric_curve,
    plot_network_crossing_heatmap,
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

    model = gp.Model(f"budget_sweep_{security_model.name.lower()}")
    model.setParam("OutputFlag", 0)

    artifacts = attach_route_activation_constraints(model, planning)

    budget_constr = model.addConstr(
        gp.quicksum(artifacts.key_vars.values()) <= 0,
        name="max_active_keys",
    )

    model.setObjective(gp.quicksum(artifacts.route_vars.values()), GRB.MAXIMIZE)

    sweep_rows = []
    trace_rows = []

    for max_keys in range(len(planning.key_scopes) + 1):
        budget_constr.RHS = max_keys
        model.optimize()

        if model.SolCount == 0:
            sweep_rows.append({
                "max_keys": max_keys,
                "selected_routes": 0,
                "selected_pairs": 0,
                "selected_keys": 0,
                "connectivity_pct": 0.0,
            })
            trace_rows.append(None)
            continue

        selected_route_ids = {
            route_id
            for route_id, var in artifacts.route_vars.items()
            if var.X > 0.5
        }

        selected_pairs = {
            route_id.split(":")[0]
            for route_id in selected_route_ids
        }

        selected_keys = sum(
            1 for var in artifacts.key_vars.values()
            if var.X > 0.5
        )

        sweep_rows.append({
            "max_keys": max_keys,
            "selected_routes": len(selected_route_ids),
            "selected_pairs": len(selected_pairs),
            "selected_keys": selected_keys,
            "connectivity_pct": 100.0 * len(selected_pairs) / len(result.security.pairs),
        })
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
