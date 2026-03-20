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
        source=1,
        destination=3,
        curr_time=0,
        routing_algorithm=CGRYenRouting(max_routes=2),
    )

    print(
        "scenario | networks=%d nodes=%d contacts=%d routes=%d"
        % (
            len(result.topology.network_to_nodes),
            len(result.topology),
            result.contact_plan_size,
            len(result.routes),
        )
    )

    for index, route in enumerate(result.routes, start=1):
        hop_summary = [
            f"{contact.frm}->{contact.to}@frm_nw:{result.topology[contact.frm]}->to_nw:{result.topology[contact.to]}({contact.start}-{contact.end})"
            for contact in route.get_hops()
        ]
        print(
            "route | index=%d next_node=%s delivery_time=%s volume=%s hops=%s"
            % (
                index,
                route.next_node,
                route.best_delivery_time,
                route.volume,
                hop_summary,
            )
        )


if __name__ == "__main__":
    main()
