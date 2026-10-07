"""Reusable pair-coverage definitions, independent of coverage targets."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

from modules.domain import NodePair, RouteRef
from pipelines.activation import GlobalActivationBindings

if TYPE_CHECKING:
    import gurobipy as gp


@dataclass(frozen=True, slots=True)
class PairCoverageBindings:
    pair_vars: Mapping[NodePair, gp.Var]
    route_implies_pair: Mapping[RouteRef, gp.Constr]
    pair_has_route: Mapping[NodePair, gp.Constr]

    @property
    def covered_pair_count(self) -> gp.LinExpr:
        import gurobipy as gp
        return gp.quicksum(self.pair_vars.values())


def attach_pair_coverage(activation: GlobalActivationBindings) -> PairCoverageBindings:
    """Define pair activation iff at least one candidate route is selected.

    The problem retains pairs with no candidates; their variables are zero.
    This function neither requires coverage nor chooses an objective.
    """
    import gurobipy as gp
    from gurobipy import GRB

    model = activation.model
    pairs = {
        pair: model.addVar(vtype=GRB.BINARY, name=f"pair[{pair[0]}->{pair[1]}]")
        for pair in activation.problem.pairs
    }
    implications = {
        ref: model.addConstr(var <= pairs[ref.pair], name=f"route_implies_pair[{ref}]")
        for ref, var in activation.route_vars.items()
    }
    usage = {
        pair: model.addConstr(
            pairs[pair] <= gp.quicksum(activation.route_vars[ref] for ref in refs),
            name=f"pair_has_route[{pair[0]}->{pair[1]}]",
        )
        for pair, refs in activation.problem.routes_by_pair.items()
    }
    return PairCoverageBindings(
        MappingProxyType(pairs), MappingProxyType(implications), MappingProxyType(usage),
    )


def require_full_coverage(activation: GlobalActivationBindings) -> Mapping[NodePair, gp.Constr]:
    """Require one route per pair without introducing unnecessary pair variables."""
    import gurobipy as gp

    return MappingProxyType({
        pair: activation.model.addConstr(
            gp.quicksum(activation.route_vars[ref] for ref in refs) >= 1,
            name=f"pair_has_at_least_one_route[{pair[0]}->{pair[1]}]",
        )
        for pair, refs in activation.problem.routes_by_pair.items()
    })
