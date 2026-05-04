import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.simulation import run_simulation


DEFAULT_EXPORT_NAME = "pipeline_export.json"


def main() -> None:
    args = _parse_args()
    scenario_dir = Path(__file__).resolve().parent
    output_path = scenario_dir / args.output

    result = run_simulation(
        cp_path=str(scenario_dir / "contact_plan.json"),
        topology_path=str(scenario_dir / "topology.json"),
        security_models=tuple(SecurityModelType),
        curr_time=0,
        routing_algorithm=CGRYenRouting(max_routes=args.max_routes),
    )
    export_payload = build_export_payload(result)
    output_path.write_text(
        json.dumps(export_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(
        "scenario | two_planes_polar networks=%d nodes=%d contacts=%d pairs=%d"
        % (
            len(result.topology.network_to_nodes),
            len(result.topology),
            result.contact_plan_size,
            len(result.routing.pairs),
        )
    )
    print("model | plane 1 nodes=[1, 2, 3, 4, 5] plane 2 nodes=[6, 7, 8, 9, 10]")
    print("model | intra-plane contacts are permanent; cross-plane contacts are polar windows")
    print("export | %s" % output_path)

    for pair in result.routing.pairs:
        routing_routes = result.routing.routes_by_pair[pair]
        print(
            "\npair | %d->%d routes=%d"
            % (
                pair[0],
                pair[1],
                len(routing_routes),
            )
        )

        for index, route in enumerate(routing_routes, start=1):
            hops = route.get_hops()
            node_path = [hops[0].frm] + [hop.to for hop in hops]
            windows = ["%d->%d@%d-%d" % (hop.frm, hop.to, hop.start, hop.end) for hop in hops]
            print(
                "route | index=%d node_path=%s delivery_time=%s volume=%s hops=%s"
                % (
                    index,
                    node_path,
                    route.best_delivery_time,
                    route.volume,
                    windows,
                )
            )

        annotated_routes = result.security.annotated_routes_by_pair[pair]
        for model in SecurityModelType:
            plans = result.security.plans_by_model[model][pair]
            for annotated, plan in zip(annotated_routes, plans, strict=True):
                print(
                    "security | model=%s route_id=%s network_path=%s crossings=%d gateways=%s operations=%d key_requirements=%d"
                    % (
                        model.name.lower(),
                        annotated.route_id,
                        list(annotated.network_path),
                        len(annotated.boundary_crossings),
                        sorted(annotated.gateway_nodes),
                        len(plan.operations),
                        len(plan.key_requirements),
                    )
                )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the two_planes_polar scenario for all ordered node pairs and "
            "export the complete routing/security pipeline."
        )
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_EXPORT_NAME,
        help="Export file name relative to this scenario directory.",
    )
    parser.add_argument(
        "--max-routes",
        type=int,
        default=3,
        help="Maximum number of CGR Yen routes to keep per ordered node pair.",
    )
    return parser.parse_args()


def build_export_payload(result) -> dict:
    return {
        "scenario": "two_planes_polar",
        "contact_plan_size": result.contact_plan_size,
        "topology": {
            "node_to_network": {
                str(node_id): network_id
                for node_id, network_id in sorted(result.topology.node_to_network.items())
            },
            "network_to_nodes": {
                str(network_id): sorted(node_ids)
                for network_id, node_ids in sorted(result.topology.network_to_nodes.items())
            },
        },
        "pairs": [
            _build_pair_payload(result, pair)
            for pair in result.routing.pairs
        ],
    }


def _build_pair_payload(result, pair: tuple[int, int]) -> dict:
    routes = result.routing.routes_by_pair[pair]
    annotated_routes = result.security.annotated_routes_by_pair[pair]

    return {
        "source": pair[0],
        "destination": pair[1],
        "route_count": len(routes),
        "routes": [
            _build_route_payload(result, pair, route, annotated)
            for route, annotated in zip(routes, annotated_routes, strict=True)
        ],
    }


def _build_route_payload(result, pair: tuple[int, int], route, annotated) -> dict:
    hops = route.get_hops()
    route_payload = {
        "route_id": annotated.route_id,
        "pair": [pair[0], pair[1]],
        "next_node": route.next_node,
        "best_delivery_time": route.best_delivery_time,
        "volume": route.volume,
        "confidence": route.confidence,
        "hop_count": len(hops),
        "node_path": list(annotated.node_path),
        "network_path": list(annotated.network_path),
        "hops": [
            {
                "hop_index": hop_index,
                "from_node": hop.frm,
                "to_node": hop.to,
                "start": hop.start,
                "end": hop.end,
                "rate": hop.rate,
                "owlt": hop.owlt,
                "confidence": hop.confidence,
                "volume": hop.volume,
            }
            for hop_index, hop in enumerate(hops)
        ],
        "annotation": {
            "source_network": annotated.source_network,
            "destination_network": annotated.destination_network,
            "gateway_nodes": sorted(annotated.gateway_nodes),
            "boundary_crossings": [
                {
                    "crossing_index": crossing.crossing_index,
                    "hop_index": crossing.hop_index,
                    "exit_node": crossing.exit_node,
                    "entrance_node": crossing.entrance_node,
                    "from_network": crossing.from_network,
                    "to_network": crossing.to_network,
                }
                for crossing in annotated.boundary_crossings
            ],
        },
        "security_models": {},
    }

    for model in SecurityModelType:
        plan = _get_plan_for_route(result, pair, annotated.route_id, model)
        route_payload["security_models"][model.name.lower()] = _build_plan_payload(plan)

    return route_payload


def _get_plan_for_route(result, pair: tuple[int, int], route_id: str, model: SecurityModelType):
    for plan in result.security.plans_by_model[model][pair]:
        if plan.route_id == route_id:
            return plan
    raise KeyError(f"missing protection plan for pair={pair} route_id={route_id} model={model.name}")


def _build_plan_payload(plan) -> dict:
    return {
        "route_id": plan.route_id,
        "model": plan.model.name.lower(),
        "notes": list(plan.notes),
        "operations": [
            {
                "operation_id": operation.operation_id,
                "service": operation.service.name.lower(),
                "source_node": operation.source_node,
                "acceptor_node": operation.acceptor_node,
                "target_hop_indexes": list(operation.target_hop_indexes),
                "source_network": operation.source_network,
                "acceptor_network": operation.acceptor_network,
                "required_key_type": operation.required_key_type.name.lower(),
                "key_source_id": operation.key_source_id,
                "key_target_id": operation.key_target_id,
                "rationale": operation.rationale,
            }
            for operation in plan.operations
        ],
        "node_requirements": [
            {
                "operation_id": requirement.operation_id,
                "node_id": requirement.node_id,
                "role": requirement.role.name.lower(),
                "service": requirement.service.name.lower(),
                "key_type": requirement.key_type.name.lower(),
                "key_source_id": requirement.key_source_id,
                "key_target_id": requirement.key_target_id,
                "rationale": requirement.rationale,
            }
            for requirement in plan.node_requirements
        ],
        "key_requirements": [
            {
                "operation_id": requirement.operation_id,
                "key_type": requirement.key_type.name.lower(),
                "usage": requirement.usage.name.lower(),
                "source_id": requirement.source_id,
                "target_id": requirement.target_id,
                "local_node": requirement.local_node,
                "rationale": requirement.rationale,
                "optional": requirement.optional,
            }
            for requirement in plan.key_requirements
        ],
    }


if __name__ == "__main__":
    main()
