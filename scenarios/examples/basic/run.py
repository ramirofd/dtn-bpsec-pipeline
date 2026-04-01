from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.routing import CGRYenRouting
from pipelines.simulation import run_simulation


def main() -> None:
    example_dir = Path(__file__).resolve().parent

    result = run_simulation(
        cp_path=str(example_dir / "contact_plan.json"),
        topology_path=str(example_dir / "topology.json"),
        curr_time=0,
        routing_algorithm=CGRYenRouting(max_routes=2),
    )

    print(
        "scenario | networks=%d nodes=%d contacts=%d pairs=%d"
        % (
            len(result.topology.network_to_nodes),
            len(result.topology),
            result.contact_plan_size,
            len(result.routing.node_pair_results),
        )
    )

    for routing_pair, security_pair in zip(
        result.routing.node_pair_results,
        result.security.node_pair_results,
        strict=True,
    ):
        print(
            "\npair | %d->%d routes=%d"
            % (
                routing_pair.source,
                routing_pair.destination,
                len(routing_pair.routes),
            )
        )

        for index, route in enumerate(routing_pair.routes, start=1):
            print(
                "route | index=%d next_node=%s delivery_time=%s volume=%s hops=%d"
                % (
                    index,
                    route.next_node,
                    route.best_delivery_time,
                    route.volume,
                    len(route.get_hops()),
                )
            )

        for security_result in security_pair.security_results:
            print(f"model | {security_result.model.name.lower()}")
            for annotated, plan in zip(security_pair.annotated_routes, security_result.protection_plans, strict=True):
                print(
                    "plan_summary | route_id=%s node_path=%s network_path=%s crossings=%d gateways=%s operations=%d key_requirements=%d"
                    % (
                        annotated.route_id,
                        list(annotated.node_path),
                        list(annotated.network_path),
                        len(annotated.boundary_crossings),
                        sorted(annotated.gateway_nodes),
                        len(plan.operations),
                        len(plan.key_requirements),
                    )
                )
                for note in plan.notes:
                    print(f"note | {note}")


if __name__ == "__main__":
    main()
