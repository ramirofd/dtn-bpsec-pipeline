from __future__ import annotations

import logging
import sys

from .models import Bundle, Contact, Route

logger = logging.getLogger(__name__)


# compute candidate routes for a bundle
def fwd_candidate(
    curr_time: int,
    curr_node: int,
    contact_plan: list[Contact],
    bundle: Bundle,
    routes: list[Route],
    excluded_nodes: list[int],
) -> list[Route]:
    debug = logger.isEnabledFor(logging.DEBUG)

    return_to_sender = False
    candidate_routes: list[Route] = []

    for route in routes:
        # 3.2.5.2 a) preparation: backward propagation
        if not return_to_sender:
            if route.next_node is bundle.sender:
                excluded_nodes.append(route.next_node)
                if debug:
                    logger.debug("fwd.prepare.skip_sender | next_node=%s", route.next_node)
                continue

        # 3.2.6.9 a)
        if route.best_delivery_time > bundle.deadline:
            logger.debug(
                "fwd.candidate.reject | reason=bdt_after_deadline route_bdt=%s deadline=%s route=%s",
                route.best_delivery_time,
                bundle.deadline,
                route,
            )
            continue

        # 3.2.6.9 b)
        if route.next_node in excluded_nodes:
            if debug:
                logger.debug("fwd.candidate.reject | reason=next_node_excluded next_node=%s", route.next_node)
            continue

        # 3.2.6.9 c)
        for contact in route.hops:
            if contact.to is curr_node:
                if debug:
                    logger.debug("fwd.candidate.reject | reason=loop_to_current_node contact=%s", contact)
                continue

        # 3.2.6.9 d) calculate eto and if it is later than 1st contact end time, ignore
        adjusted_start_time = max(curr_time, route.hops[0].start)
        applicable_backlog_p = 0  # todo: this the current route.next_node queue status now for p or higher
        applicable_backlog_relief = 0
        for contact in contact_plan:
            if contact.frm == route.hops[0].frm and contact.to == route.hops[0].to:
                if contact.end > curr_time and contact.start < route.hops[0].start:
                    applicable_duration = contact.end - max(curr_time, contact.start)
                    applicable_prior_contact_volume = applicable_duration * contact.rate
                    applicable_backlog_relief += applicable_prior_contact_volume
        residual_backlog = max(0, applicable_backlog_p - applicable_backlog_relief)
        backlog_lien = residual_backlog / route.hops[0].rate
        early_tx_opportunity = adjusted_start_time + backlog_lien
        if early_tx_opportunity > route.hops[0].end:
            if debug:
                logger.debug(
                    "fwd.candidate.reject | reason=eto_after_first_contact_end eto=%s first_contact_end=%s",
                    early_tx_opportunity,
                    route.hops[0].end,
                )
            continue

        # 3.2.6.9 e) use eto to compute projected arrival time
        prev_last_byte_arr_time = 0.0
        for contact in route.hops:
            if contact == route.hops[0]:
                contact.first_byte_tx_time = early_tx_opportunity
            else:
                contact.first_byte_tx_time = max(contact.start, prev_last_byte_arr_time)
            bundle_tx_time = bundle.size / contact.rate
            contact.last_byte_tx_time = contact.first_byte_tx_time + bundle_tx_time
            contact.last_byte_arr_time = contact.last_byte_tx_time + contact.owlt
            prev_last_byte_arr_time = contact.last_byte_arr_time
        proj_arr_time = prev_last_byte_arr_time
        if proj_arr_time > bundle.deadline:
            if debug:
                logger.debug(
                    "fwd.candidate.reject | reason=projected_arrival_after_deadline projected_arrival=%s deadline=%s",
                    proj_arr_time,
                    bundle.deadline,
                )
            continue

        # 3.2.6.9 f) if route depleted for bundle priority P, ignore
        reserved_volume_p = 0  # todo: sum of al bundle.evc with p or higher that were forwarded via this route
        min_effective_volume_limit: int | float = sys.maxsize
        for index, contact in enumerate(route.hops):
            if reserved_volume_p >= contact.volume:
                if debug:
                    logger.debug(
                        "fwd.candidate.reject | reason=reserved_volume_exceeds_contact_volume reserved=%s contact_volume=%s",
                        reserved_volume_p,
                        contact.volume,
                    )
                continue

            effective_start_time = contact.first_byte_tx_time
            min_succ_stop_time = sys.maxsize
            for successor in route.hops[index:]:
                if successor.end < min_succ_stop_time:
                    min_succ_stop_time = successor.end
            effective_stop_time = min(contact.end, min_succ_stop_time)
            effective_duration = effective_stop_time - effective_start_time
            contact.effective_volume_limit = min(effective_duration * contact.rate, contact.mav[bundle.priority])
            if contact.effective_volume_limit < min_effective_volume_limit:
                min_effective_volume_limit = contact.effective_volume_limit
        route_volume_limit = min_effective_volume_limit
        if route_volume_limit <= 0:
            if debug:
                logger.debug(
                    "fwd.candidate.reject | reason=route_volume_depleted route_volume_limit=%s",
                    route_volume_limit,
                )
            continue

        # 3.2.6.9 g) if frag is False and route rvl(P) < bundle.evc, ignore
        if not bundle.fragment:
            if route_volume_limit < bundle.evc:
                if debug:
                    logger.debug(
                        "fwd.candidate.reject | reason=no_fragment_and_insufficient_volume route_volume_limit=%s bundle_evc=%s",
                        route_volume_limit,
                        bundle.evc,
                    )
                continue

        if debug:
            logger.debug("fwd.candidate.accept | route=%s", route)
        candidate_routes.append(route)

    candidate_routes.sort()

    return candidate_routes
