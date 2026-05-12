"""Public security-layer API."""

from modules.security.annotated_routes import AnnotatedHop, AnnotatedRoute, BoundaryCrossing, annotate_route, annotate_routes
from modules.security.artifacts import NodeSecurityRequirement, ProtectionOperation, ProtectionPlan
from modules.security.keys import KeyRequirement, KeyScope
from modules.security.models import KeyType, NodeAction, SecurityModel, SecurityModelType, SecurityService
from modules.security.planning import (
    DEFAULT_SECURITY_MODELS,
    SECURITY_MODEL_REGISTRY,
    BaseSecurityModel,
    EdgeByEdgeSecurityModel,
    EdgeToEdgeSecurityModel,
    EndToEndSecurityModel,
    HopByHopSecurityModel,
    build_protection_plan,
    build_protection_plans,
    get_security_model,
    resolve_security_models,
)
from modules.security.roles import get_network_role_for_endpoints

__all__ = [
    "AnnotatedHop",
    "AnnotatedRoute",
    "BoundaryCrossing",
    "annotate_route",
    "annotate_routes",
    "ProtectionOperation",
    "NodeSecurityRequirement",
    "ProtectionPlan",
    "KeyRequirement",
    "KeyScope",
    "SecurityModel",
    "SecurityModelType",
    "SecurityService",
    "KeyType",
    "NodeAction",
    "BaseSecurityModel",
    "HopByHopSecurityModel",
    "EndToEndSecurityModel",
    "EdgeByEdgeSecurityModel",
    "EdgeToEdgeSecurityModel",
    "DEFAULT_SECURITY_MODELS",
    "SECURITY_MODEL_REGISTRY",
    "get_security_model",
    "resolve_security_models",
    "build_protection_plan",
    "build_protection_plans",
    "get_network_role_for_endpoints",
]
