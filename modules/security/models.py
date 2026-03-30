"""Security model base translated from the C++ implementation.

OMNeT++ specifics are intentionally omitted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Any


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
    pass
