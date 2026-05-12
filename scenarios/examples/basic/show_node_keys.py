from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipelines.routing import CGRYenRouting
from pipelines.simulation import SimulationPipeline


KEY_TYPE_LABELS = {
    "NODE_TO_NODE": "n2n",
    "NODE_TO_GROUP": "n2g",
    "GROUP_TO_GROUP": "g2g",
}

ROLE_LABELS = {
    "SOURCE": "src",
    "ACCEPT": "acc",
    "VERIFY": "ver",
    "USE": "use",
}


def _format_requirement(requirement) -> str:
    key_type = KEY_TYPE_LABELS.get(requirement.key_type.name, requirement.key_type.name.lower())
    role = ROLE_LABELS.get(requirement.role.name, requirement.role.name.lower())
    return f"{requirement.node_id}:{role}:{key_type}_{requirement.key_source_id}->{requirement.key_target_id}"


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    pipeline = SimulationPipeline()

    result = pipeline.run(
        cp_path=str(example_dir / "contact_plan.json"),
        topology_path=str(example_dir / "topology.json"),
        curr_time=0,
        routing_algorithm=CGRYenRouting(max_routes=2),
    )

    for pair in result.annotation.pairs:
        annotated_routes = result.annotation.annotated_routes_by_pair[pair]
        routes_with_hops = [route for route in annotated_routes if len(route.hops) >= 1]
        if not routes_with_hops:
            continue

        print(f"\npair | {pair[0]}->{pair[1]}")

        for model, plans_by_pair in result.security.plans_by_model.items():
            plans_by_route_id = {
                plan.route_id: plan
                for plan in plans_by_pair[pair]
            }
            printed_model = False

            for annotated in routes_with_hops:
                plan = plans_by_route_id[annotated.route_id]
                hop_count = len(annotated.hops)
                if not printed_model:
                    print(f"model | {model.name.lower()}")
                    printed_model = True

                ordered_requirements = [
                    _format_requirement(requirement)
                    for node_id in annotated.node_path
                    for requirement in plan.node_requirements
                    if requirement.node_id == node_id
                ]
                print(
                    "route | route_id=%s hops=%d keys= %s"
                    % (
                        annotated.route_id,
                        hop_count,
                        " ".join(ordered_requirements),
                    )
                )


if __name__ == "__main__":
    main()
