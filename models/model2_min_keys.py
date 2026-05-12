from math import ceil
import gurobipy as gp
import pandas as pd
from gurobipy import GRB
from pipelines.route_activation import RouteActivationPlanner, attach_route_activation_constraints
from modules.security.models import SecurityModelType

def solve_for_security_model(result,security_model:SecurityModelType):
    planning = RouteActivationPlanner().build_for_model(
        result.security,
        model=security_model,
    )

    model = gp.Model(f"connectivity_sweep_{security_model.name.lower()}")
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
            pair_vars[pair_id] <= gp.quicksum(artifacts.route_vars[route_id] for route_id in route_ids),
            name=f"pair_has_route[{pair_id}]",
        )

    connectivity_constr = model.addConstr(
        gp.quicksum(pair_vars.values()) >= 0,
        name="min_connectivity_pairs",
    )

    model.setObjective(gp.quicksum(artifacts.key_vars.values()), GRB.MINIMIZE)

    sweep_rows = []

    for target_connectivity_pct in range(0, 101,5):
        required_pairs = ceil((target_connectivity_pct / 100.0) * len(pair_ids))
        connectivity_constr.RHS = required_pairs
        model.optimize()

        if model.SolCount == 0:
            sweep_rows.append({
                "target_connectivity_pct": target_connectivity_pct,
                "required_pairs": required_pairs,
                "selected_pairs": 0,
                "selected_routes": 0,
                "selected_keys": 0,
                "achieved_connectivity_pct": 0.0,
            })
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

        sweep_rows.append({
            "target_connectivity_pct": target_connectivity_pct,
            "required_pairs": required_pairs,
            "selected_pairs": selected_pairs,
            "selected_routes": len(selected_route_ids),
            "selected_keys": selected_keys,
            "achieved_connectivity_pct": 100.0 * selected_pairs / len(pair_ids),
        })

    new_df = pd.DataFrame(sweep_rows)
    new_df["model"] = security_model.name
    
    return new_df