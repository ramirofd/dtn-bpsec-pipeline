import gurobipy as gp
import pandas as pd
from gurobipy import GRB
from pipelines.route_activation import RouteActivationPlanner, attach_route_activation_constraints
from modules.security.models import SecurityModelType

def solve_for_security_model(result, security_model):
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
    new_df = pd.DataFrame(sweep_rows)
    new_df['model'] = security_model.name
    
    return new_df