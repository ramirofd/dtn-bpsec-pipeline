from __future__ import annotations

from dataclasses import dataclass

from modules.network.py_cgr_lib import Route, cp_load
from modules.network.topology import Topology, topology_load
from pipelines.routing import RoutingAlgorithm, RoutingRequest, ensure_routing_algorithm


@dataclass(slots=True, frozen=True)
class SimulationResult:
    topology: Topology
    contact_plan_size: int
    routes: tuple[Route, ...]


def run_simulation(
    cp_path: str,
    topology_path: str,
    source: int | None = None,
    destination: int | None = None,
    curr_time: int = 0,
    routing_algorithm: RoutingAlgorithm | None = None,
    num_routes: int = 3,
) -> SimulationResult:
    topology = topology_load(topology_path)
    contact_plan = cp_load(cp_path)
    algorithm = ensure_routing_algorithm(routing_algorithm, default_num_routes=num_routes)

    routes: tuple[Route, ...] = ()
    if (source is None) != (destination is None):
        raise ValueError("source and destination must be provided together")

    if source is not None and destination is not None:
        topology.get_network_for_node(source)
        topology.get_network_for_node(destination)
        request = RoutingRequest(
            source=source,
            destination=destination,
            curr_time=curr_time,
            contact_plan=contact_plan,
            topology=topology,
            num_routes=num_routes,
        )
        routes = tuple(
            algorithm.compute_routes(request)
        )

    return SimulationResult(
        topology=topology,
        contact_plan_size=len(contact_plan),
        routes=routes,
    )
