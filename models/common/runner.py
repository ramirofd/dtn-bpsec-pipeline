"""One owner for the solver lifecycle, sweeps and solution extraction."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from math import isfinite
from numbers import Integral
from typing import TYPE_CHECKING, Protocol

from models.common.results import OptimizationResult, SolveOutcome, SweepPoint
from pipelines.activation import (
    ActivationProblem, GlobalActivationBindings, build_trace, extract_solution,
)

if TYPE_CHECKING:
    import gurobipy as gp


class BuiltOptimization(Protocol):
    @property
    def activation(self) -> GlobalActivationBindings: ...

    @property
    def sweep_constraint(self) -> gp.Constr | None: ...

    @property
    def fixed_point(self) -> SweepPoint | None: ...


@dataclass(frozen=True, slots=True)
class OptimizationBindings:
    activation: GlobalActivationBindings
    sweep_constraint: gp.Constr | None = None
    fixed_point: SweepPoint | None = None


def connectivity_points(targets: Iterable[float], total_pairs: int) -> tuple[SweepPoint, ...]:
    try:
        values = tuple(Decimal(str(value)) for value in targets)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("target_connectivity_pcts must contain finite percentages in [0, 100]") from exc
    if not values or any(not value.is_finite() or not 0 <= value <= 100 for value in values):
        raise ValueError("target_connectivity_pcts must contain finite percentages in [0, 100]")
    return tuple(
        SweepPoint(target_connectivity_pct=float(value), required_pairs=_required_pairs(value, total_pairs))
        for value in values
    )


def _required_pairs(target: Decimal, total_pairs: int) -> int:
    return int((target * total_pairs / 100).to_integral_value(rounding=ROUND_CEILING))


def budget_points(budgets: Iterable[int] | None, total_keys: int) -> tuple[SweepPoint, ...]:
    values = tuple(range(total_keys + 1) if budgets is None else budgets)
    if not values or any(isinstance(value, bool) or not isinstance(value, Integral) or value < 0 for value in values):
        raise ValueError("key_budgets must contain nonnegative integers")
    return tuple(SweepPoint(key_budget=int(value)) for value in values)


def run_optimization(
    problem: ActivationProblem,
    *,
    name: str,
    build: Callable[[gp.Model, ActivationProblem], BuiltOptimization],
    points: tuple[SweepPoint, ...],
    env: gp.Env | None = None,
) -> OptimizationResult:
    """Build once, vary a constraint bound, extract pure results, then dispose.

    A supplied environment is borrowed and never disposed by this function.
    The model is disposed on construction, optimization and extraction errors.
    """
    import gurobipy as gp
    from gurobipy import GRB

    if not points:
        raise ValueError("an optimization run requires at least one sweep point")
    for point in points:
        if point.target_connectivity_pct is not None and point.required_pairs != _required_pairs(
            Decimal(str(point.target_connectivity_pct)), len(problem.pairs),
        ):
            raise ValueError("coverage point pair count does not match its percentage and problem")
    if len({point.key_budget is None for point in points}) != 1:
        raise ValueError("an optimization sweep cannot mix key budgets and coverage targets")
    model = gp.Model(f"{name}_{problem.policy_id.lower()}", env=env)
    try:
        model.setParam("OutputFlag", 0)
        bindings = build(model, problem)
        if bindings.activation.model is not model or bindings.activation.problem is not problem:
            raise ValueError("builder returned bindings for another model or problem")
        model.update()
        if bindings.sweep_constraint is None:
            if bindings.fixed_point is None or points != (bindings.fixed_point,):
                raise ValueError("a fixed formulation requires exactly its declared fixed point")
        else:
            if bindings.fixed_point is not None:
                raise ValueError("a formulation must declare either a sweep constraint or a fixed point, not both")
            try:
                model.getAttr(GRB.Attr.RHS, [bindings.sweep_constraint])
            except (gp.GurobiError, AttributeError, TypeError) as exc:
                raise ValueError("sweep constraint must belong to the optimization model") from exc
        outcomes = []
        for point in points:
            if bindings.sweep_constraint is not None:
                bindings.sweep_constraint.RHS = point.bound
            model.optimize()
            solution = extract_solution(bindings.activation) if model.SolCount else None
            trace = build_trace(problem, solution) if solution is not None else None
            outcomes.append(SolveOutcome(
                point=point,
                solver_status=model.Status,
                is_optimal=model.Status == GRB.OPTIMAL,
                objective_value=_number(model, "ObjVal") if solution is not None else None,
                objective_bound=_number(model, "ObjBound"),
                mip_gap=_number(model, "MIPGap") if solution is not None else None,
                runtime_seconds=float(model.Runtime),
                solution=solution,
                trace=trace,
            ))
        return OptimizationResult(name, problem, tuple(outcomes))
    finally:
        model.dispose()


def _number(model: gp.Model, attribute: str) -> float | None:
    import gurobipy as gp
    try:
        value = float(model.getAttr(attribute))
    except (AttributeError, gp.GurobiError):
        return None
    return value if isfinite(value) else None
