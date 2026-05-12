import gurobipy as gp
import pandas as pd
from gurobipy import GRB

from modules.security.models import SecurityModelType
from pipelines.route_activation import (
    RouteActivationPlanner,
    attach_route_activation_constraints,
)


def solve_for_security_model(result, security_model: SecurityModelType):
    planning = RouteActivationPlanner().build_for_model(
        result.security,
        model=security_model,
    )

    model = gp.Model(f"full_connectivity_min_keys_{security_model.name.lower()}")
    model.setParam("OutputFlag", 0)

    artifacts = attach_route_activation_constraints(model, planning)

    pair_ids = [f"{src}->{dst}" for src, dst in result.security.pairs]
    routes_by_pair = {pair_id: [] for pair_id in pair_ids}

    for route_id in artifacts.route_vars:
        pair_id = route_id.split(":")[0]
        routes_by_pair[pair_id].append(route_id)

    for pair_id, route_ids in routes_by_pair.items():
        model.addConstr(
            gp.quicksum(artifacts.route_vars[route_id] for route_id in route_ids) >= 1,
            name=f"pair_has_at_least_one_route[{pair_id}]",
        )

    model.setObjective(gp.quicksum(artifacts.key_vars.values()), GRB.MINIMIZE)
    model.optimize()

    if model.SolCount == 0:
        new_df = pd.DataFrame(
            [
                {
                    "target_connectivity_pct": 100,
                    "required_pairs": len(pair_ids),
                    "selected_pairs": 0,
                    "selected_routes": 0,
                    "selected_keys": 0,
                    "achieved_connectivity_pct": 0.0,
                }
            ]
        )
        new_df["model"] = security_model.name
        return new_df

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

    new_df = pd.DataFrame(
        [
            {
                "target_connectivity_pct": 100,
                "required_pairs": len(pair_ids),
                "selected_pairs": len(selected_pairs),
                "selected_routes": len(selected_route_ids),
                "selected_keys": selected_keys,
                "achieved_connectivity_pct": 100.0 * len(selected_pairs) / len(pair_ids),
            }
        ]
    )
    new_df["model"] = security_model.name

    return new_df
