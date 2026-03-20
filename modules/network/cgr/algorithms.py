from __future__ import annotations

import logging
import sys
from typing import TypeAlias

from .models import Contact, Route

logger = logging.getLogger(__name__)

ContactPlan: TypeAlias = list[Contact]


def _build_contact_plan_hash(contact_plan: ContactPlan) -> dict[int, list[Contact]]:
    contact_plan_hash: dict[int, list[Contact]] = {}
    for contact in contact_plan:
        contact_plan_hash.setdefault(contact.frm, []).append(contact)
        contact_plan_hash.setdefault(contact.to, [])
    return contact_plan_hash


# compute the best route with dijkstra # (root_contact.arrival_time sets the current_time)
def cgr_dijkstra(root_contact: Contact, destination: int, contact_plan: ContactPlan) -> Route | None:
    debug = logger.isEnabledFor(logging.DEBUG)

    # Clear working area of all contacts except the root, which in the case of Yens' it
    # can be any of the contacts in the plan, and requires to carry the work area intact
    for contact in contact_plan:
        if contact is not root_contact:
            contact.clear_dijkstra_working_area()

    contact_plan_hash = _build_contact_plan_hash(contact_plan)

    route: Route | None = None
    final_contact: Contact | None = None
    earliest_fin_arr_t = sys.maxsize

    current = root_contact
    if root_contact.to not in root_contact.visited_nodes:
        root_contact.visited_nodes.append(root_contact.to)

    if debug:
        logger.debug(
            "cgr.dijkstra.start | from=%s destination=%s arrival_time=%s",
            root_contact,
            destination,
            root_contact.arrival_time,
        )
    while True:
        if debug:
            logger.debug("cgr.dijkstra.current | contact=%s", current)

        # Calculate cost of all proximate contacts
        for contact in contact_plan_hash[current.to]:
            if contact in current.suppressed_next_hop:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=suppressed_next_hop", contact)
                continue
            if contact.suppressed:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=suppressed", contact)
                continue
            if contact.visited:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=contact_visited", contact)
                continue
            if contact.to in current.visited_nodes:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=node_visited", contact)
                continue
            if contact.end <= current.arrival_time:  # <= important!
                if debug:
                    logger.debug(
                        "cgr.dijkstra.skip | contact=%s reason=ended_before_arrival contact_end=%s current_arrival=%s",
                        contact,
                        contact.end,
                        current.arrival_time,
                    )
                continue
            if max(contact.mav) <= 0:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=no_residual_volume", contact)
                continue
            if current.frm == contact.to and current.to == contact.frm:
                if debug:
                    logger.debug("cgr.dijkstra.skip | contact=%s reason=return_to_previous_node", contact)
                continue

            # Calculate arrival time (cost)
            if contact.start < current.arrival_time:
                arrvl_time = current.arrival_time + contact.owlt
            else:
                arrvl_time = contact.start + contact.owlt

            # Update cost if better or equal
            if arrvl_time <= contact.arrival_time:
                previous_arrival = contact.arrival_time
                contact.arrival_time = arrvl_time
                contact.predecessor = current
                contact.visited_nodes = current.visited_nodes[:]
                contact.visited_nodes.append(contact.to)
                if debug:
                    logger.debug(
                        "cgr.dijkstra.update | contact=%s arrival_time=%s previous_arrival=%s visited_nodes=%s",
                        contact,
                        contact.arrival_time,
                        previous_arrival,
                        contact.visited_nodes,
                    )

                # Mark if destination reached
                if contact.to == destination and contact.arrival_time < earliest_fin_arr_t:
                    earliest_fin_arr_t = contact.arrival_time
                    final_contact = contact
                    if debug:
                        logger.debug(
                            "cgr.dijkstra.final_candidate | contact=%s earliest_arrival=%s",
                            contact,
                            earliest_fin_arr_t,
                        )
            else:
                if debug:
                    logger.debug(
                        "cgr.dijkstra.no_update | contact=%s candidate_arrival=%s previous_arrival=%s",
                        contact,
                        arrvl_time,
                        contact.arrival_time,
                    )

        current.visited = True

        # Determine best next contact among all in contactPlan
        earliest_arr_t = sys.maxsize
        next_contact: Contact | None = None

        for contact in contact_plan:
            # Ignore suppressed, visited
            if contact.suppressed or contact.visited:
                continue

            # If we know there is another better contact, continue
            if contact.arrival_time > earliest_fin_arr_t:
                continue

            if contact.arrival_time < earliest_arr_t:
                earliest_arr_t = contact.arrival_time
                next_contact = contact

        if next_contact is None:
            break

        current = next_contact

    # Done contact graph exploration, check and store new route
    if final_contact is not None:
        hops: list[Contact] = []
        backtrack: Contact | int = final_contact
        while isinstance(backtrack, Contact) and backtrack != root_contact:
            hops.insert(0, backtrack)
            backtrack = backtrack.predecessor

        route = Route(hops[0])
        for hop in hops[1:]:
            route.append(hop)

    return route


# computes all routes using deph first
def cgr_depth(source: int, destination: int, contact_plan: ContactPlan) -> list[Route]:
    # store contact plan in hash table (key: starting node, value: list of contacts with same starting node)
    contacts: dict[int, list[Contact]] = {}
    source_in_plan = False
    destination_in_plan = False
    for contact in contact_plan:
        if contact.frm == source:
            source_in_plan = True
        if contact.to == destination:
            destination_in_plan = True
        contacts.setdefault(contact.frm, []).append(contact)

    assert source_in_plan and destination_in_plan

    # Now initialize the list of routes with direct contacts from source
    routes: list[Route] = []
    for contact in contacts[source]:
        routes.append(Route(contact))

    # finally, fill in the paths
    for i, _ in enumerate(routes):
        while True:
            current_last = routes[i].get_last_node()
            candidates = [c for c in contacts[current_last] if routes[i].eligible(c)]
            if candidates and current_last != destination:
                fork = False
                for other_option in candidates[1:]:
                    routes.append(routes[i] + other_option)
                    fork = True
                if fork:
                    routes[i] = routes[i] + candidates[0]
                else:
                    routes[i].append(candidates[0])
            else:
                break

    # filter out the paths that did not lead to the destination
    routes = [route for route in routes if route.get_last_node() == destination]

    # by now all possible paths should be contained in "routes".
    # Sort routes from best to worst
    routes.sort()

    return routes


# calculates best num_routes (K) routes out of a contact graph
def cgr_yen(source: int, destination: int, curr_time: int, contact_plan: ContactPlan, num_routes: int) -> list[Route]:
    debug = logger.isEnabledFor(logging.DEBUG)

    # best routes (container A)
    routes: list[Route] = []
    # potential_routes route list (container B)
    potential_routes: list[Route] = []

    # create Root Contact
    root_contact = Contact(source, source, 0, sys.maxsize, 100, 1.0, 0)  # root contact
    root_contact.arrival_time = curr_time

    # reset contacts
    for contact in contact_plan:
        contact.clear_dijkstra_working_area()
        contact.clear_management_working_area()

    # get first route and add the root contact as the first hop.
    # in yen's formulation we add the root contact to each new route
    # so we can use it as spur_contact as well.
    route = cgr_dijkstra(root_contact, destination, contact_plan)
    if route is None:
        return routes
    routes.append(route)
    routes[0].hops.insert(0, root_contact)

    for k in range(num_routes - 1):
        if debug:
            logger.debug("cgr.yen.iteration | k=%s last_route=%s", k, routes[-1])
        for spur_contact in routes[-1].hops[:-1]:
            # create root_path from root_contact until spur_contact
            spur_contact_index = routes[-1].hops.index(spur_contact)
            if debug:
                logger.debug(
                    "cgr.yen.spur | k=%s spur_index=%s spur_contact=%s",
                    k,
                    spur_contact_index,
                    spur_contact,
                )

            root_path = Route(routes[-1].hops[0])
            for hop in routes[-1].hops[1 : spur_contact_index + 1]:
                root_path.append(hop)
            if debug:
                logger.debug("cgr.yen.root_path | k=%s root_path=%s", k, root_path)

            # reset contacts
            for contact in contact_plan:
                contact.clear_dijkstra_working_area()
                contact.clear_management_working_area()

            # suppress all contacts in root_path except spur_contact
            for contact in root_path.hops[:-1]:
                contact.suppressed = True
                if debug:
                    logger.debug("cgr.yen.suppress_node | contact=%s", contact)

            # suppress all outgoing edges from spur_contact already covered by known routes
            for known_route in routes:
                if root_path.hops == known_route.hops[0 : len(root_path.hops)]:
                    next_hop = known_route.hops[len(root_path.hops)]
                    if next_hop not in spur_contact.suppressed_next_hop:
                        spur_contact.suppressed_next_hop.append(next_hop)
                        if debug:
                            logger.debug(
                                "cgr.yen.suppress_edge | from=%s to=%s",
                                spur_contact,
                                next_hop,
                            )

            # prepare spur_contact as root contact
            spur_contact.clear_dijkstra_working_area()
            spur_contact.arrival_time = root_path.best_delivery_time
            for hop in root_path.hops:  # add visited nodes to spur_contact
                spur_contact.visited_nodes.append(hop.to)
            if debug:
                logger.debug(
                    "cgr.yen.prepare_spur | visited_nodes=%s arrival_time=%s",
                    spur_contact.visited_nodes,
                    spur_contact.arrival_time,
                )

            # try to find a spur_path with dijkstra
            spur_path = cgr_dijkstra(spur_contact, destination, contact_plan)

            # if found store new route in potential_routes
            if spur_path:
                total_path = Route(root_path.hops[0])
                for hop in root_path.hops[1:]:  # append root_path
                    total_path.append(hop)
                for hop in spur_path.hops:  # append spur_path
                    total_path.append(hop)
                potential_routes.append(total_path)
                if debug:
                    logger.debug("cgr.yen.new_route | route=%s", total_path)
            else:
                if debug:
                    logger.debug("cgr.yen.no_route | k=%s spur_contact=%s", k, spur_contact)

        # if no more potential routes end search
        if not potential_routes:
            break

        # sort potential routes by arrival_time
        potential_routes.sort()

        # add best route to routes
        routes.append(potential_routes[0])
        potential_routes.pop(0)

    # remove root_contact from hops and refresh values
    for route in routes:
        route.hops.pop(0)
        route.refresh_metrics()

    return routes


# compute route list using anchor search (ION 3.6 and older)
def cgr_anchor(source: int, destination: int, curr_time: int, contact_plan: ContactPlan) -> list[Route]:
    routes: list[Route] = []

    # create Root Contact
    root_contact = Contact(source, source, 0, sys.maxsize, 100, 1.0, 0)  # root contact
    root_contact.arrival_time = curr_time

    # reset suppressed contacts
    for contact in contact_plan:
        contact.clear_dijkstra_working_area()
        contact.clear_management_working_area()

    limit_contact: Contact | None = None
    anchor_contact: Contact | None = None
    while True:
        route = cgr_dijkstra(root_contact, destination, contact_plan)
        if not route:
            break  # no more routes in contact graph

        first_contact = route.hops[0]

        # if anchored search on-going and first_contact is no longer
        # the anchor, end anchored search and discard this route
        if anchor_contact and anchor_contact is not first_contact:
            # reset suppressed contacts
            for contact in contact_plan:
                contact.clear_dijkstra_working_area()
                if contact.frm != source:
                    contact.suppressed = True
            anchor_contact.suppressed = True
            anchor_contact = None
            continue  # go straight to next dijkstra

        routes.append(route)

        # find limiting contact and suppress it
        if route.to_time == first_contact.end:
            limit_contact = first_contact
        else:
            # the first is not a limiting contact: start anchor search
            anchor_contact = first_contact
            for contact in route.hops:
                if contact.end == route.to_time:
                    limit_contact = contact
                    break

        if limit_contact is not None:
            limit_contact.suppressed = True

        # reset working area
        for contact in contact_plan:
            contact.clear_dijkstra_working_area()

    return routes


# compute route list using first-ended (time-based search)
def cgr_ended(source: int, destination: int, curr_time: int, contact_plan: ContactPlan) -> list[Route]:
    routes: list[Route] = []

    # create Root Contact
    root_contact = Contact(source, source, 0, sys.maxsize, 100, 1.0, 0)  # root contact
    root_contact.arrival_time = curr_time

    while True:
        route = cgr_dijkstra(root_contact, destination, contact_plan)
        if not route:
            break  # no more routes in contact graph

        # consume volume in all hops and supress limiting hop
        for hop in route.hops:
            if hop.end == route.to_time:
                hop.suppressed = True

        routes.append(route)

    return routes


# compute route list using first-depleted (capacity-oriented search)
def cgr_depleted(
    source: int,
    destination: int,
    curr_time: int,
    contact_plan: ContactPlan,
    keep_residual_volume: bool = False,
) -> list[Route]:
    routes: list[Route] = []

    # create Root Contact
    root_contact = Contact(source, source, 0, sys.maxsize, 100, 1.0, 0)  # root contact
    root_contact.arrival_time = curr_time

    # reset residual volume
    if not keep_residual_volume:
        for contact in contact_plan:
            contact.clear_management_working_area()

    while True:
        route = cgr_dijkstra(root_contact, destination, contact_plan)
        if not route:
            break  # no more routes in contact graph

        # consume volume in all hops and supress limiting hop
        for hop in route.hops:
            if hop.effective_volume_limit is None:
                continue
            hop.effective_volume_limit -= route.volume
            if hop.effective_volume_limit == 0:
                hop.suppressed = True

        routes.append(route)

    return routes
