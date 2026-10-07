"""Minimize the largest distinct-key inventory using shared activation components."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from models.common.coverage import PairCoverageBindings, attach_pair_coverage
from models.common.results import OptimizationResult
from models.common.runner import connectivity_points, run_optimization
from pipelines.activation import (
    ActivationProblem, GlobalActivationBindings, NodeDeliveryBindings,
    attach_global_activation, attach_node_deliveries,
)

if TYPE_CHECKING:
    import gurobipy as gp


@dataclass(frozen=True, slots=True)
class MinMaxNodeKeysBindings:
    node_delivery: NodeDeliveryBindings
    coverage: PairCoverageBindings
    max_keys_var: gp.Var
    connectivity_constraint: gp.Constr

    @property
    def activation(self) -> GlobalActivationBindings:
        return self.node_delivery.activation

    @property
    def sweep_constraint(self) -> gp.Constr:
        return self.connectivity_constraint

    @property
    def fixed_point(self) -> None:
        return None


def build(model: gp.Model, problem: ActivationProblem) -> MinMaxNodeKeysBindings:
    """Attach this formulation to a caller-owned solver model, without solving."""
    from gurobipy import GRB

    activation = attach_global_activation(model, problem)
    deliveries = attach_node_deliveries(activation)
    coverage = attach_pair_coverage(activation)
    minimum = model.addConstr(
        coverage.covered_pair_count >= len(problem.pairs), name="min_connectivity_pairs",
    )
    maximum = model.addVar(vtype=GRB.INTEGER, lb=0, name="max_keys_per_node")
    for node, load in deliveries.node_key_loads.items():
        model.addConstr(load <= maximum, name=f"node_key_load[{node}]")
    model.setObjective(maximum, GRB.MINIMIZE)
    return MinMaxNodeKeysBindings(deliveries, coverage, maximum, minimum)


def solve(
    problem: ActivationProblem, *, target_connectivity_pcts: Iterable[float] = (100,),
    env: gp.Env | None = None,
) -> OptimizationResult:
    """Minimax inventories for each target; no secondary objective among ties."""
    return run_optimization(
        problem, name="min_max_keys_per_node", build=build,
        points=connectivity_points(target_connectivity_pcts, len(problem.pairs)), env=env,
    )
