"""Security model base translated from the C++ implementation.

OMNeT++ specifics are intentionally omitted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.security.annotated_routes import AnnotatedRoute
    from modules.security.artifacts import ProtectionPlan


class OperationResult(Enum):
    SUCCESS = auto()
    FAIL = auto()


class NetworkRole(Enum):
    SOURCE = auto()
    SOURCE_N_EXIT = auto()
    DESTINATION = auto()
    DESTINATION_N_ENTRANCE = auto()
    ENTRANCE = auto()
    EXIT = auto()
    INNER = auto()
    UNKNOWN = auto()


class SecurityRole(Enum):
    SEC_SOURCE = auto()
    SEC_ACCEPTOR = auto()
    SEC_VERIFIER = auto()


class SecurityModelType(Enum):
    HOP_BY_HOP = auto()
    END_TO_END = auto()
    EDGE_BY_EDGE = auto()
    EDGE_TO_EDGE = auto()


class SecurityService(Enum):
    BCB = auto()
    BIB = auto()


class KeyType(Enum):
    NODE_TO_NODE = auto()
    NODE_TO_GROUP = auto()
    GROUP_TO_GROUP = auto()


class NodeAction(Enum):
    SOURCE = auto()
    ACCEPT = auto()
    VERIFY = auto()
    USE = auto()


class SecurityModel(ABC):
    type: SecurityModelType

    @property
    def name(self) -> str:
        return self.type.name.lower()

    @abstractmethod
    def build_plan(self, annotated_route: AnnotatedRoute) -> ProtectionPlan:
        raise NotImplementedError

    def build_plans(
        self,
        annotated_routes: tuple[AnnotatedRoute, ...] | list[AnnotatedRoute],
    ) -> tuple[ProtectionPlan, ...]:
        return tuple(self.build_plan(route) for route in annotated_routes)
