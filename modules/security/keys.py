"""Key management helpers for security models."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class KeyRef:
    src: int
    dst: int
    context: str


class Keys:
    """Simple in-memory key store indexed by (src, dst, context)."""

    def __init__(self) -> None:
        self._store: Dict[KeyRef, str] = {}

    def register(self, src: int, dst: int, key: str, context: str = "BCB") -> None:
        self._store[KeyRef(src=src, dst=dst, context=context)] = key

    def get(self, src: int, dst: int, context: str = "BCB") -> Optional[str]:
        return self._store.get(KeyRef(src=src, dst=dst, context=context))

    def has(self, src: int, dst: int, context: str = "BCB") -> bool:
        return KeyRef(src=src, dst=dst, context=context) in self._store

    def clear(self) -> None:
        self._store.clear()

    def as_dict(self) -> Dict[Tuple[int, int, str], str]:
        return {(k.src, k.dst, k.context): v for k, v in self._store.items()}
