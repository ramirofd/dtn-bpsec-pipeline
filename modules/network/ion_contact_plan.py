"""Convert static ION contact plans (including CPD exports) to our JSON schema.

Rates are copied verbatim (bytes/s in ION); times and OWLT remain integer
seconds. This module does not execute ionadmin commands or round input values.
"""

from __future__ import annotations

import argparse
import json
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from modules.network.cgr.loader import ContactPlanEntry


class IonContactPlanError(ValueError):
    """An input line cannot be represented faithfully by our contact schema."""


@dataclass(frozen=True)
class _Interval:
    start: int
    end: int
    frm: int
    to: int
    value: int
    line: int


def _error(line: int, message: str) -> IonContactPlanError:
    return IonContactPlanError(f"ION line {line}: {message}")


def _integer(token: str, line: int, field: str, minimum: int = 0) -> int:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise _error(line, f"invalid {field}: {token!r}") from exc
    if not value.is_finite() or value != value.to_integral_value():
        raise _error(line, f"{field} must be an integer; refusing to round {token!r}")
    if value < minimum:
        raise _error(line, f"{field} must be >= {minimum}")
    return int(value)


def _utc(token: str, line: int) -> datetime:
    try:
        return datetime.strptime(token, "%Y/%m/%d-%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise _error(line, f"expected UTC YYYY/MM/DD-HH:MM:SS, got {token!r}") from exc


def _time(token: str, epoch: datetime | None, line: int) -> int:
    if token.startswith("+"):
        return _integer(token[1:], line, "relative time")
    if epoch is None:
        raise _error(line, "absolute times require an initial '@ YYYY/MM/DD-HH:MM:SS'")
    seconds = int((_utc(token, line) - epoch).total_seconds())
    if seconds < 0:
        raise _error(line, "time precedes the scenario epoch")
    return seconds


def _read_records(text: str) -> tuple[list[_Interval], list[_Interval]]:
    contacts: list[_Interval] = []
    ranges: list[_Interval] = []
    epoch: datetime | None = None
    for line_number, raw in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        fields = raw.split("#", 1)[0].split()
        if not fields:
            continue
        if fields[0] == "@":
            if len(fields) != 2 or epoch is not None or contacts or ranges:
                raise _error(line_number, "only one initial absolute '@' reference is supported")
            epoch = _utc(fields[1], line_number)
            continue
        if fields[:2] not in (["a", "contact"], ["a", "range"]):
            raise _error(line_number, "unsupported command; expected 'a contact' or 'a range'")
        kind = fields[1]
        allowed_lengths = (7, 8) if kind == "contact" else (7,)
        if len(fields) not in allowed_lengths:
            raise _error(line_number, f"invalid number of fields for 'a {kind}'")
        if len(fields) == 8 and _integer(fields[7], line_number, "confidence", 1) != 1:
            raise _error(line_number, "only confidence=1 is supported by the destination schema")

        start = _time(fields[2], epoch, line_number)
        end = _time(fields[3], epoch, line_number)
        frm = _integer(fields[4], line_number, "source node", 1)
        to = _integer(fields[5], line_number, "destination node", 1)
        field_name = "rate" if kind == "contact" else "owlt"
        value = _integer(fields[6], line_number, field_name, 1 if kind == "contact" else 0)
        if end <= start:
            raise _error(line_number, "end must be greater than start")
        if frm == to:
            raise _error(line_number, "source and destination must be different")
        record = _Interval(start, end, frm, to, value, line_number)
        (contacts if kind == "contact" else ranges).append(record)
    if not contacts:
        raise IonContactPlanError("The input contains no scheduled contacts")
    return contacts, ranges


def _range_index(ranges: list[_Interval]) -> dict[tuple[int, int], list[_Interval]]:
    index: dict[tuple[int, int], list[_Interval]] = defaultdict(list)
    for interval in ranges:
        index[interval.frm, interval.to].append(interval)
    for pair, intervals in index.items():
        intervals.sort(key=lambda item: (item.start, item.end))
        for previous, current in zip(intervals, intervals[1:]):
            if current.start < previous.end:
                raise _error(current.line, f"overlapping ranges for {pair}; see line {previous.line}")
    return index


def parse_ion_contact_plan(
    text: str, *, default_owlt: int | None = None
) -> list[dict[str, int]]:
    """Parse ION text into dictionaries accepted by ``cp_load``.

    Supports comments, one initial absolute ``@`` epoch, relative ``+seconds``
    or absolute UTC times, ``a contact`` and ``a range``. Other commands,
    non-unit confidence and fractional times/rates/OWLT raise an error.

    An ascending-node range also applies in reverse unless an explicit reverse
    range overrides it. A descending-node range is directional, as in ION.
    Contacts are split at OWLT changes. Their order, direction and rates are
    preserved; no reverse contacts are invented and no contacts are merged.

    A missing range raises by default. Set ``default_owlt=0`` (or another
    nonnegative integer) explicitly to fill uncovered intervals with a warning.
    Zero present in an actual range is always retained, even with a fallback.
    """
    if default_owlt is not None and (type(default_owlt) is not int or default_owlt < 0):
        raise ValueError("default_owlt must be a nonnegative integer or None")
    contacts, ranges = _read_records(text)
    index = _range_index(ranges)
    output: list[dict[str, int]] = []
    fallback_contacts = 0

    for contact in contacts:
        def overlaps(interval: _Interval) -> bool:
            return interval.start < contact.end and interval.end > contact.start

        explicit = [item for item in index.get((contact.frm, contact.to), []) if overlaps(item)]
        implicit = []
        if contact.frm > contact.to:
            implicit = [item for item in index.get((contact.to, contact.frm), []) if overlaps(item)]
        boundaries = {contact.start, contact.end}
        for interval in explicit + implicit:
            boundaries.update((max(contact.start, interval.start), min(contact.end, interval.end)))
        ordered = sorted(boundaries)
        segments: list[dict[str, int]] = []
        used_fallback = False

        for start, end in zip(ordered, ordered[1:]):
            # Explicit ranges take precedence over ION's implicit reverse range.
            match = next(
                (item for item in explicit + implicit if item.start <= start and item.end >= end),
                None,
            )
            if match is None:
                if default_owlt is None:
                    raise _error(
                        contact.line,
                        f"no range covers {contact.frm}->{contact.to} during [{start}, {end}); "
                        "provide default_owlt explicitly if a fallback is intended",
                    )
                owlt = default_owlt
                used_fallback = True
            else:
                owlt = match.value
            if segments and segments[-1]["owlt"] == owlt:
                segments[-1]["end"] = end
            else:
                segments.append({
                    "start": start, "end": end, "from": contact.frm,
                    "to": contact.to, "rate": contact.value, "owlt": owlt,
                })
        for entry in segments:
            ContactPlanEntry.model_validate(entry)
        output.extend(segments)
        fallback_contacts += used_fallback

    if fallback_contacts:
        warnings.warn(
            f"Used default_owlt={default_owlt} in uncovered intervals of "
            f"{fallback_contacts} source contact(s)",
            UserWarning,
            stacklevel=2,
        )
    return output


def convert_ion_contact_plan(
    source: str | Path,
    destination: str | Path | None = None,
    *,
    default_owlt: int | None = None,
) -> list[dict[str, int]]:
    """Read an ION file, optionally save JSON, and return its converted contacts.

    ``destination=None`` performs no writes. An existing destination is replaced
    only after successful parsing/validation. The source cannot be overwritten.
    The output uses seconds relative to the initial epoch (not Unix seconds).
    Keep the original ION file to retain its absolute date and provenance.
    """
    source = Path(source).expanduser()
    target = Path(destination).expanduser() if destination is not None else None
    if target is not None and (
        source.resolve() == target.resolve()
        or (target.exists() and source.samefile(target))
    ):
        raise ValueError("The JSON destination must be different from the ION source")
    contacts = parse_ion_contact_plan(source.read_text(encoding="utf-8-sig"), default_owlt=default_owlt)
    if target is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(contacts, indent=2) + "\n", encoding="utf-8")
    return contacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="ION contact-plan text file")
    parser.add_argument("destination", type=Path, help="Destination contact_plan.json")
    parser.add_argument("--default-owlt", type=int, default=None, help="Explicit fallback for missing ranges")
    args = parser.parse_args()
    try:
        contacts = convert_ion_contact_plan(args.source, args.destination, default_owlt=args.default_owlt)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    nodes = {entry[key] for entry in contacts for key in ("from", "to")}
    print(f"Saved {len(contacts)} contacts, {len(nodes)} nodes to {args.destination}")


if __name__ == "__main__":
    main()
