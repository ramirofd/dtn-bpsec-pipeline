"""Small structural contracts for independently replaceable pipeline stages."""
from __future__ import annotations
from typing import Protocol, runtime_checkable

from pipelines.catalogs import AnnotationCatalog, ProtectionCatalog, RouteCatalog
from pipelines.routing import RoutingBatchRequest


@runtime_checkable
class RoutePlanner(Protocol):
    """Produce identified immutable routes, retaining empty requested pairs."""
    def compute(self, request: RoutingBatchRequest) -> RouteCatalog: ...


@runtime_checkable
class RouteAnnotator(Protocol):
    """Annotate exactly the supplied references without changing route data."""
    def annotate(self, routes: RouteCatalog) -> AnnotationCatalog: ...


@runtime_checkable
class ProtectionPlanner(Protocol):
    """Build every route/policy combination; reject duplicate policy IDs."""
    def build(self, annotations: AnnotationCatalog) -> ProtectionCatalog: ...
