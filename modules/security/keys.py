"""Key inventory and requirement models aligned with scoped security plans."""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.security.models import KeyType, SecurityService


@dataclass(slots=True, frozen=True)
class KeyScope:
    key_type: KeyType
    source_id: int
    target_id: int


@dataclass(slots=True, frozen=True)
class KeyRecord:
    key_id: str
    scope: KeyScope
    usages: frozenset[SecurityService]
    material: str = ""


@dataclass(slots=True, frozen=True)
class KeyRequirement:
    operation_id: str
    key_type: KeyType
    usage: SecurityService
    source_id: int
    target_id: int
    local_node: int
    rationale: str
    optional: bool = False

    @property
    def scope(self) -> KeyScope:
        return KeyScope(
            key_type=self.key_type,
            source_id=self.source_id,
            target_id=self.target_id,
        )


@dataclass(slots=True, frozen=True)
class KeyMatch:
    requirement: KeyRequirement
    record: KeyRecord | None

    @property
    def missing(self) -> bool:
        return self.record is None


@dataclass(slots=True)
class KeyInventory:
    _records: dict[KeyScope, list[KeyRecord]] = field(default_factory=dict)

    def register(
        self,
        *,
        key_id: str,
        key_type: KeyType,
        source_id: int,
        target_id: int,
        usages: set[SecurityService] | frozenset[SecurityService] | None = None,
        material: str = "",
    ) -> KeyRecord:
        record = KeyRecord(
            key_id=key_id,
            scope=KeyScope(key_type=key_type, source_id=source_id, target_id=target_id),
            usages=frozenset(usages or {SecurityService.BCB}),
            material=material,
        )
        self._records.setdefault(record.scope, []).append(record)
        return record

    def find(self, requirement: KeyRequirement) -> KeyRecord | None:
        for record in self._records.get(requirement.scope, []):
            if requirement.usage in record.usages:
                return record
        return None

    def resolve(self, requirements: list[KeyRequirement] | tuple[KeyRequirement, ...]) -> tuple[KeyMatch, ...]:
        return tuple(
            KeyMatch(requirement=requirement, record=self.find(requirement))
            for requirement in requirements
        )

    def has(self, requirement: KeyRequirement) -> bool:
        return self.find(requirement) is not None

    def as_dict(self) -> dict[tuple[str, int, int], list[str]]:
        return {
            (scope.key_type.name, scope.source_id, scope.target_id): [record.key_id for record in records]
            for scope, records in self._records.items()
        }
