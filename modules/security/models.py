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


class SecurityModel(ABC):
    pass