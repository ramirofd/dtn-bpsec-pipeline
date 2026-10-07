"""Portable activation results; no solver dependency is needed to store them."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from modules.domain import RouteRef
from modules.security.keys import KeyScope

if TYPE_CHECKING:
    from pipelines.activation.bindings import GlobalActivationBindings


@dataclass(frozen=True, slots=True)
class ActivationSolution:
    route_values: Mapping[RouteRef, float]
    key_values: Mapping[KeyScope, float]
    threshold: float = 0.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold) or not 0 <= self.threshold < 1:
            raise ValueError("selection threshold must be finite and in [0, 1)")
        for name in ("route_values", "key_values"):
            values = {key: float(value) for key, value in getattr(self, name).items()}
            if any(not math.isfinite(value) or value < -1e-5 or value > 1 + 1e-5
                   for value in values.values()):
                raise ValueError(f"{name} must contain finite binary variable values")
            object.__setattr__(self, name, MappingProxyType(values))

    @property
    def selected_routes(self) -> tuple[RouteRef, ...]:
        return tuple(ref for ref, value in self.route_values.items() if value > self.threshold)

    @property
    def selected_key_scopes(self) -> tuple[KeyScope, ...]:
        return tuple(scope for scope, value in self.key_values.items() if value > self.threshold)


def extract_solution(bindings: GlobalActivationBindings, *, threshold: float = 0.5) -> ActivationSolution:
    """Detach numeric values while the caller's solver model is still alive."""
    if bindings.model.SolCount <= 0:
        raise ValueError("cannot extract activation values: solver has no feasible solution")
    return ActivationSolution(
        {ref: float(bindings.route_vars[ref].X) for ref in bindings.problem.requirements},
        {scope: float(bindings.key_vars[scope].X) for scope in bindings.problem.key_scopes},
        threshold=threshold,
    )
