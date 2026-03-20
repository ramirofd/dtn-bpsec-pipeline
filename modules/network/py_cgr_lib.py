"""Backward-compatible facade for CGR utilities.

This module keeps the historical import path while delegating implementation to
`modules.network.cgr` submodules.
"""

from modules.network.cgr.algorithms import cgr_anchor, cgr_depleted, cgr_depth, cgr_dijkstra, cgr_ended, cgr_yen
from modules.network.cgr.exceptions import (
    CGRError,
    ContactPlanError,
    ContactPlanFormatError,
    ContactPlanValidationError,
)
from modules.network.cgr.forwarding import fwd_candidate
from modules.network.cgr.loader import ContactPlanDocument, ContactPlanEntry, cp_load, cp_random
from modules.network.cgr.models import Bundle, Contact, Route

__all__ = [
    "CGRError",
    "ContactPlanError",
    "ContactPlanFormatError",
    "ContactPlanValidationError",
    "Bundle",
    "Contact",
    "Route",
    "ContactPlanEntry",
    "ContactPlanDocument",
    "cp_load",
    "cp_random",
    "cgr_dijkstra",
    "cgr_depth",
    "cgr_yen",
    "cgr_anchor",
    "cgr_ended",
    "cgr_depleted",
    "fwd_candidate",
]
