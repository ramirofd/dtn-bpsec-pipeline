"""Solver-independent optimization outcomes and a single table projection."""

from __future__ import annotations

from dataclasses import dataclass

from pipelines.activation import ActivationProblem, ActivationSolution, RouteActivationSelection


@dataclass(frozen=True, slots=True)
class SweepPoint:
    key_budget: int | None = None
    target_connectivity_pct: float | None = None
    required_pairs: int | None = None

    def __post_init__(self) -> None:
        if self.key_budget is not None:
            if self.target_connectivity_pct is not None or self.required_pairs is not None:
                raise ValueError("a sweep point must choose either a key budget or a coverage target")
            if type(self.key_budget) is not int or self.key_budget < 0:
                raise ValueError("key_budget must be a nonnegative integer")
        elif self.target_connectivity_pct is None or self.required_pairs is None:
            raise ValueError("a coverage point requires both percentage and pair count")
        else:
            if not 0 <= self.target_connectivity_pct <= 100:
                raise ValueError("target_connectivity_pct must be in [0, 100]")
            if type(self.required_pairs) is not int or self.required_pairs < 0:
                raise ValueError("required_pairs must be a nonnegative integer")

    @property
    def bound(self) -> int:
        return self.key_budget if self.key_budget is not None else self.required_pairs


@dataclass(frozen=True, slots=True)
class SolveOutcome:
    point: SweepPoint
    solver_status: int
    is_optimal: bool
    objective_value: float | None
    objective_bound: float | None
    mip_gap: float | None
    runtime_seconds: float
    solution: ActivationSolution | None
    trace: RouteActivationSelection | None

    def __post_init__(self) -> None:
        if (self.solution is None) != (self.trace is None):
            raise ValueError("solution and trace must be present or absent together")
        if self.is_optimal and self.solution is None:
            raise ValueError("an optimal outcome must contain a solution")

    @property
    def has_solution(self) -> bool:
        return self.solution is not None


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    optimization_model: str
    problem: ActivationProblem
    outcomes: tuple[SolveOutcome, ...]

    @property
    def traces(self) -> tuple[RouteActivationSelection | None, ...]:
        return tuple(outcome.trace for outcome in self.outcomes)

    def to_frame(self):
        """Project all models through the same metric definitions.

        Missing incumbents have missing metrics, never invented zero costs.
        The model column identifies a configured security policy for plotting;
        security_model preserves its family separately.
        """
        import pandas as pd

        rows = []
        total_pairs = len(self.problem.pairs)
        total_keys = len(self.problem.key_scopes)
        for outcome in self.outcomes:
            trace = outcome.trace
            row = {
                "model": self.problem.policy_id,
                "security_model": self.problem.security_model.name,
                "optimization_model": self.optimization_model,
                "solver_status": outcome.solver_status,
                "has_solution": outcome.has_solution,
                "is_optimal": outcome.is_optimal,
                "objective_value": outcome.objective_value,
                "objective_bound": outcome.objective_bound,
                "mip_gap": outcome.mip_gap,
                "runtime_seconds": outcome.runtime_seconds,
                "total_pairs": total_pairs,
                "total_key_scopes": total_keys,
                "selected_pairs": None,
                "selected_routes": None,
                "selected_keys": None,
                "selected_keys_pct_of_available": None,
                "achieved_connectivity_pct": None,
                "total_key_deliveries": None,
                "max_keys_per_node": None,
            }
            if outcome.point.key_budget is not None:
                row["max_keys"] = outcome.point.key_budget
            else:
                row["target_connectivity_pct"] = outcome.point.target_connectivity_pct
                row["required_pairs"] = outcome.point.required_pairs
            if trace is not None:
                selected_keys = len(trace.selected_key_scopes)
                row.update(
                    selected_pairs=len(trace.selected_pairs),
                    selected_routes=len(trace.selected_route_ids),
                    selected_keys=selected_keys,
                    selected_keys_pct_of_available=100 * selected_keys / total_keys if total_keys else 0.0,
                    achieved_connectivity_pct=100 * len(trace.selected_pairs) / total_pairs if total_pairs else 0.0,
                    total_key_deliveries=sum(trace.key_counts_by_node.values()),
                    max_keys_per_node=trace.max_keys_per_node,
                )
            rows.append(row)
        return pd.DataFrame(rows)
