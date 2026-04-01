import logging
from pathlib import Path

import typer

from modules.network.topology import NodeNotFoundError, Topology, topology_load
from modules.security.models import SecurityModelType
from pipelines.simulation import run_simulation

logger = logging.getLogger(__name__)
app = typer.Typer(help="CLI minima para cargar topologia, contact plan y calcular rutas.")

DEFAULT_CP_PATH = Path("scenarios/examples/basic/contact_plan.json")
DEFAULT_TOPOLOGY_PATH = Path("scenarios/examples/basic/topology.json")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _load_topology(topology_path: Path) -> Topology:
    topology = topology_load(str(topology_path))
    return topology


def _validate_node_exists(topology: Topology, node_id: int, label: str) -> None:
    if not topology.node_exists(node_id):
        raise typer.BadParameter(f"{label} node {node_id} no existe en la topologia")


def _parse_security_model(raw: str) -> SecurityModelType:
    normalized = raw.strip().replace("-", "_").upper()
    try:
        return SecurityModelType[normalized]
    except KeyError as exc:
        valid = ", ".join(model.name.lower() for model in SecurityModelType)
        raise typer.BadParameter(f"security model invalido: {raw}. validos: {valid}") from exc


@app.command()
def load(
    cp_path: Path = typer.Option(
        DEFAULT_CP_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path al contact plan JSON.",
    ),
    topology_path: Path = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON.",
    ),
) -> None:
    logger.info("cli.load.start | contact_plan=%s topology=%s", cp_path, topology_path)

    result = run_simulation(
        cp_path=str(cp_path),
        topology_path=str(topology_path),
        node_pairs=(),
        security_models=(),
    )

    logger.info(
        "cli.load.summary | networks=%d nodes=%d contacts=%d",
        len(result.topology.network_to_nodes),
        len(result.topology),
        result.contact_plan_size,
    )


@app.command()
def routes(
    source: int = typer.Option(..., min=1, help="Nodo origen."),
    destination: int = typer.Option(..., min=1, help="Nodo destino."),
    cp_path: Path = typer.Option(
        DEFAULT_CP_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path al contact plan JSON.",
    ),
    topology_path: Path = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON.",
    ),
    curr_time: int = typer.Option(
        0,
        min=0,
        help="Tiempo actual para el calculo de rutas.",
    ),
    num_routes: int = typer.Option(
        3,
        min=1,
        help="Cantidad maxima de rutas a calcular.",
    ),
) -> None:
    logger.info(
        "cli.routes.start | contact_plan=%s topology=%s source=%s destination=%s",
        cp_path,
        topology_path,
        source,
        destination,
    )

    try:
        result = run_simulation(
            cp_path=str(cp_path),
            topology_path=str(topology_path),
            node_pairs=((source, destination),),
            security_models=(),
            curr_time=curr_time,
            num_routes=num_routes,
        )
    except NodeNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    topology = result.topology
    pair_result = result.routing.node_pair_results[0]

    logger.info(
        "cli.routes.summary | source=%d source_network=%d destination=%d destination_network=%d routes=%d",
        source,
        topology[source],
        destination,
        topology[destination],
        len(pair_result.routes),
    )

    for index, route in enumerate(pair_result.routes, start=1):
        logger.info(
            "cli.routes.route | index=%d next_node=%s hops=%d delivery_time=%s volume=%s",
            index,
            route.next_node,
            len(route.get_hops()),
            route.best_delivery_time,
            route.volume,
        )


@app.command("security-plan")
def security_plan(
    source: int = typer.Option(..., min=1, help="Nodo origen."),
    destination: int = typer.Option(..., min=1, help="Nodo destino."),
    model: str = typer.Option(..., help="Modelo: hop_by_hop, end_to_end, edge_by_edge o edge_to_edge."),
    cp_path: Path = typer.Option(
        DEFAULT_CP_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path al contact plan JSON.",
    ),
    topology_path: Path = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON.",
    ),
    curr_time: int = typer.Option(0, min=0, help="Tiempo actual para el calculo de rutas."),
    num_routes: int = typer.Option(1, min=1, help="Cantidad maxima de rutas a calcular."),
) -> None:
    security_model = _parse_security_model(model)
    result = run_simulation(
        cp_path=str(cp_path),
        topology_path=str(topology_path),
        node_pairs=((source, destination),),
        security_models=(security_model,),
        curr_time=curr_time,
        num_routes=num_routes,
    )
    pair_result = result.security.node_pair_results[0]
    security_result = pair_result.security_results[0]

    logger.info(
        "cli.security.summary | model=%s routes=%d",
        security_model.name.lower(),
        len(pair_result.annotated_routes),
    )
    for annotated, plan in zip(pair_result.annotated_routes, security_result.protection_plans, strict=True):
        logger.info(
            "cli.security.route | route_id=%s node_path=%s network_path=%s crossings=%d gateways=%s",
            annotated.route_id,
            list(annotated.node_path),
            list(annotated.network_path),
            len(annotated.boundary_crossings),
            sorted(annotated.gateway_nodes),
        )
        for operation in plan.operations:
            logger.info(
                "cli.security.operation | operation=%s service=%s source=%d acceptor=%d key_type=%s scope=%s->%s hops=%s",
                operation.operation_id,
                operation.service.name,
                operation.source_node,
                operation.acceptor_node,
                operation.required_key_type.name,
                operation.key_source_id,
                operation.key_target_id,
                list(operation.target_hop_indexes),
            )
        for note in plan.notes:
            logger.info("cli.security.note | route_id=%s note=%s", annotated.route_id, note)


@app.command("topology-info")
def topology_info(
    topology_path: Path = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON.",
    ),
    node: int | None = typer.Option(
        None,
        min=1,
        help="Nodo a consultar.",
    ),
    network: int | None = typer.Option(
        None,
        min=1,
        help="Red a consultar.",
    ),
) -> None:
    logger.info("cli.topology.start | topology=%s node=%s network=%s", topology_path, node, network)

    topology = _load_topology(topology_path)

    if node is None and network is None:
        logger.info(
            "cli.topology.summary | networks=%d nodes=%d",
            len(topology.network_to_nodes),
            len(topology),
        )
        return

    if node is not None:
        _validate_node_exists(topology, node, "node")
        logger.info("cli.topology.node | node=%d network=%d", node, topology[node])

    if network is not None:
        if not topology.network_exists(network):
            raise typer.BadParameter(f"network {network} no existe en la topologia")
        logger.info(
            "cli.topology.network | network=%d nodes=%s",
            network,
            sorted(topology.get_nodes_for_network(network)),
        )


if __name__ == "__main__":
    _configure_logging()
    app()
