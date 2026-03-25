from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.security import build_security_artifacts
from pipelines.simulation import run_simulation


def main() -> None:
    example_dir = Path(__file__).resolve().parent

    result = run_simulation(
        cp_path=str(example_dir / "contact_plan.json"),
        topology_path=str(example_dir / "topology.json"),
        source=1,
        destination=5,
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

    print("\nsecurity pipeline")
    for model in SecurityModelType:
        security = build_security_artifacts(
            result.routes,
            result.topology,
            source_node=1,
            destination_node=5,
            model=model,
        )
        print(f"model | {model.name.lower()}")
        for annotated, plan in zip(security.annotated_routes, security.protection_plans, strict=True):
            print(
                "annotated_route | id=%s node_path=%s network_path=%s crossings=%s gateways=%s"
                % (
                    annotated.route_id,
                    list(annotated.node_path),
                    list(annotated.network_path),
                    [
                        (
                            crossing.from_network,
                            crossing.to_network,
                            crossing.exit_node,
                            crossing.entrance_node,
                        )
                        for crossing in annotated.boundary_crossings
                    ],
                    sorted(annotated.gateway_nodes),
                )
            )
            for operation in plan.operations:
                print(
                    "operation | id=%s service=%s source=%d acceptor=%d key_type=%s scope=%s->%s hops=%s"
                    % (
                        operation.operation_id,
                        operation.service.name,
                        operation.source_node,
                        operation.acceptor_node,
                        operation.required_key_type.name,
                        operation.key_source_id,
                        operation.key_target_id,
                        list(operation.target_hop_indexes),
                    )
                )
            for requirement in plan.key_requirements:
                print(
                    "key_requirement | operation=%s key_type=%s usage=%s scope=%s->%s local_node=%s"
                    % (
                        requirement.operation_id,
                        requirement.key_type.name,
                        requirement.usage.name,
                        requirement.source_id,
                        requirement.target_id,
                        requirement.local_node,
                    )
                )
            for note in plan.notes:
                print(f"note | {note}")
        print()


if __name__ == "__main__":
    main()
