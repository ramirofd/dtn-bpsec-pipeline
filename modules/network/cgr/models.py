from __future__ import annotations

import copy
import sys
from dataclasses import dataclass, field
from typing import Self


@dataclass(slots=True)
class Contact:
    # fixed parameters
    frm: int
    to: int
    start: int
    end: int
    rate: int
    confidence: float = 1.0
    owlt: int = 0

    # computed parameters
    volume: int = field(init=False)
    mav: list[int] = field(init=False)

    # route search working area
    arrival_time: int = field(default=sys.maxsize)
    visited: bool = field(default=False)
    visited_nodes: list[int] = field(default_factory=list)
    predecessor: Contact | int = field(default=0)

    # route management working area
    suppressed: bool = field(default=False)
    suppressed_next_hop: list[Contact] = field(default_factory=list)

    # forwarding working area
    first_byte_tx_time: float | None = field(default=None)
    last_byte_tx_time: float | None = field(default=None)
    last_byte_arr_time: float | None = field(default=None)
    effective_volume_limit: float | None = field(default=None)

    def __post_init__(self) -> None:
        self.volume = self.rate * (self.end - self.start)
        self.mav = [self.volume, self.volume, self.volume]

    def clear_dijkstra_working_area(self) -> None:
        self.arrival_time = sys.maxsize
        self.visited = False
        self.predecessor = 0
        self.visited_nodes = []

    def clear_management_working_area(self) -> None:
        self.suppressed = False
        self.suppressed_next_hop = []

    def clear_working_area(self) -> None:
        self.clear_dijkstra_working_area()
        self.clear_management_working_area()

    def __repr__(self) -> str:
        # replace with inf
        if self.end == sys.maxsize:
            end = "inf"
        else:
            end = str(self.end)

        # mav in %
        volume = 100 * min(self.mav) / self.volume

        return "%s->%s(%s-%s,d%s)[mav%d%%]" % (self.frm, self.to, self.start, end, self.owlt, volume)


class Route:
    __slots__ = (
        "parent",
        "hops",
        "to_node",
        "next_node",
        "from_time",
        "to_time",
        "best_delivery_time",
        "volume",
        "confidence",
        "_visited",
    )

    def __init__(self, contact: Contact, parent: Route | None = None) -> None:
        # dfs: carry on from where parent route left
        self.parent = parent

        # fixed parameters
        self.hops: list[Contact] = []
        if parent is None:
            self.to_node: int | None = None
            self.next_node: int | None = None
            self.from_time = 0
            self.to_time = sys.maxsize
            self.best_delivery_time = 0
            self.volume: int | float = sys.maxsize
            self.confidence = 1.0

            self._visited: dict[int, bool] = {}
        else:
            self.to_node = parent.to_node
            self.next_node = parent.next_node
            self.from_time = parent.from_time
            self.to_time = parent.to_time
            self.best_delivery_time = parent.best_delivery_time
            self.volume = parent.volume
            self.confidence = parent.confidence

            self._visited = copy.copy(parent._visited)

        # initial contact
        self.append(contact)

    def get_last_node(self) -> int:
        return self.get_last_contact().to

    def get_last_contact(self) -> Contact:
        return self.hops[-1]

    def visited(self, node: int) -> bool:
        return node in self._visited and self._visited[node]

    def append(self, contact: Contact) -> None:
        assert self.eligible(contact)
        self.hops.append(contact)
        self._visited[contact.frm] = True
        self._visited[contact.to] = True

        self.refresh_metrics()

    def refresh_metrics(self) -> None:
        assert self.hops
        hops = self.get_hops()

        self.to_node = hops[-1].to
        self.next_node = hops[0].to
        self.from_time = hops[0].start
        self.to_time = sys.maxsize
        self.best_delivery_time = 0
        self.confidence = 1.0
        for contact in hops:
            self.to_time = min(self.to_time, contact.end)
            self.best_delivery_time = max(self.best_delivery_time + contact.owlt, contact.start + contact.owlt)
            self.confidence *= contact.confidence

        # volume
        prev_last_byte_arr_time = 0.0
        min_effective_volume_limit: int | float = sys.maxsize
        for index, contact in enumerate(hops):
            if index == 0:
                contact.first_byte_tx_time = float(contact.start)
            else:
                contact.first_byte_tx_time = max(float(contact.start), prev_last_byte_arr_time)
            bundle_tx_time = 0.0  # immediate transmission
            contact.last_byte_tx_time = contact.first_byte_tx_time + bundle_tx_time
            contact.last_byte_arr_time = contact.last_byte_tx_time + contact.owlt
            prev_last_byte_arr_time = contact.last_byte_arr_time

            effective_start_time = contact.first_byte_tx_time
            min_succ_stop_time = sys.maxsize
            for successor in hops[index:]:
                if successor.end < min_succ_stop_time:
                    min_succ_stop_time = successor.end
            effective_stop_time = min(contact.end, min_succ_stop_time)
            effective_duration = effective_stop_time - effective_start_time
            contact.effective_volume_limit = min(effective_duration * contact.rate, contact.volume)
            if contact.effective_volume_limit < min_effective_volume_limit:
                min_effective_volume_limit = contact.effective_volume_limit
        self.volume = min_effective_volume_limit

    # This method decides whether a contact can be inserted in this path
    # Modify this method to set more constraints (include owlt ?)
    def eligible(self, contact: Contact) -> bool:
        try:
            return not self.visited(contact.to) and contact.end > self.get_last_contact().start + self.get_last_contact().owlt
        except IndexError:
            return True

    # OPERATOR OVERLOAD FOR SELECTION #
    # Less than = this route is better than the other (less costly)
    def __lt__(self, other_route: Route) -> bool:
        # 1st priority : arrival time
        if self.best_delivery_time < other_route.best_delivery_time:
            return True

        # 2nd: volume
        if self.best_delivery_time == other_route.best_delivery_time:
            if self.volume > other_route.volume:
                return True

            # 3rd: confidence
            if self.volume == other_route.volume:
                if self.confidence >= other_route.confidence:
                    return True

        return False

    # now we do not have all the hops, so reconstruct the full path from parents
    def get_hops(self) -> list[Contact]:
        if self.parent is None:
            return self.hops
        return self.parent.get_hops() + self.hops

    # utility methods
    def __repr__(self) -> str:
        return "to:%s|via:%s(%03d,%03d)|bdt:%s|hops:%s|vol:%s|conf:%s|%s" % (
            self.to_node,
            self.next_node,
            self.from_time,
            self.to_time,
            self.best_delivery_time,
            len(self.get_hops()),
            self.volume,
            self.confidence,
            self.get_hops(),
        )

    def __add__(self, contact: Contact) -> Self:
        return Route(contact, self)


@dataclass(slots=True)
class Bundle:
    # bundle primary block parameters
    src: int
    dst: int
    size: int
    deadline: int
    priority: int
    critical: bool = False
    sender: int = 0
    custody: bool = False
    fragment: bool = True

    # computed parameters
    evc: float = field(init=False)

    def __post_init__(self) -> None:
        self.evc = max(self.size * 1.03, 100)
