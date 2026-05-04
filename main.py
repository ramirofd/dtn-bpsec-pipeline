import logging
from pathlib import Path

import typer

from modules.network.topology import Topology, topology_load
from modules.network.teneto_plot import plot_contact_plan_with_teneto
from modules.security.models import SecurityModelType
from pipelines.simulation import run_simulation

logger = logging.getLogger(__name__)
app = typer.Typer(help="CLI batch para cargar escenarios y resumir routing y seguridad.")

DEFAULT_CP_PATH = Path("scenarios/examples/basic/contact_plan.json")
DEFAULT_TOPOLOGY_PATH = Path("scenarios/examples/basic/topology.json")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _load_topology(topology_path: Path) -> Topology:
    return topology_load(str(topology_path))


def _parse_security_model(raw: str) -> SecurityModelType:
    normalized = raw.strip().replace("-", "_").upper()
    try:
        return SecurityModelType[normalized]
    except KeyError as exc:
        valid = ", ".join(model.name.lower() for model in SecurityModelType)
        raise typer.BadParameter(f"security model invalido: {raw}. validos: {valid}") from exc


def _count_nonempty_pairs(routes_by_pair: dict[tuple[int, int], tuple]) -> int:
    return sum(1 for routes in routes_by_pair.values() if routes)


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
        security_models=(),
    )

    logger.info(
        "cli.load.summary | networks=%d nodes=%d contacts=%d pairs=%d",
        len(result.topology.network_to_nodes),
        len(result.topology),
        result.contact_plan_size,
        len(result.routing.pairs),
    )


@app.command("routing-batch")
def routing_batch(
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
    curr_time: int = typer.Option(0, min=0, help="Tiempo actual para el calculo batch."),
    num_routes: int = typer.Option(3, min=1, help="Cantidad maxima de rutas por par."),
) -> None:
    logger.info(
        "cli.routing_batch.start | contact_plan=%s topology=%s curr_time=%d num_routes=%d",
        cp_path,
        topology_path,
        curr_time,
        num_routes,
    )

    result = run_simulation(
        cp_path=str(cp_path),
        topology_path=str(topology_path),
        security_models=(),
        curr_time=curr_time,
        num_routes=num_routes,
    )
    routes_by_pair = result.routing.routes_by_pair
    total_routes = sum(len(routes) for routes in routes_by_pair.values())
    reachable_pairs = _count_nonempty_pairs(routes_by_pair)

    logger.info(
        "cli.routing_batch.summary | pairs=%d reachable_pairs=%d total_routes=%d",
        len(result.routing.pairs),
        reachable_pairs,
        total_routes,
    )


@app.command("security-batch")
def security_batch(
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
    curr_time: int = typer.Option(0, min=0, help="Tiempo actual para el calculo batch."),
    num_routes: int = typer.Option(3, min=1, help="Cantidad maxima de rutas por par."),
) -> None:
    security_model = _parse_security_model(model)
    logger.info(
        "cli.security_batch.start | model=%s contact_plan=%s topology=%s curr_time=%d num_routes=%d",
        security_model.name.lower(),
        cp_path,
        topology_path,
        curr_time,
        num_routes,
    )

    result = run_simulation(
        cp_path=str(cp_path),
        topology_path=str(topology_path),
        security_models=(security_model,),
        curr_time=curr_time,
        num_routes=num_routes,
    )
    plans_by_pair = result.security.plans_by_model[security_model]
    annotated_by_pair = result.security.annotated_routes_by_pair

    candidate_routes = sum(len(routes) for routes in annotated_by_pair.values())
    operations = sum(len(plan.operations) for plans in plans_by_pair.values() for plan in plans)
    key_requirements = sum(len(plan.key_requirements) for plans in plans_by_pair.values() for plan in plans)
    reachable_pairs = _count_nonempty_pairs(annotated_by_pair)

    logger.info(
        "cli.security_batch.summary | model=%s pairs=%d reachable_pairs=%d candidate_routes=%d operations=%d key_requirements=%d",
        security_model.name.lower(),
        len(result.security.pairs),
        reachable_pairs,
        candidate_routes,
        operations,
        key_requirements,
    )


@app.command("topology-info")
def topology_info(
    topology_path: Path = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON.",
    ),
    node: int | None = typer.Option(None, min=1, help="Nodo a consultar."),
    network: int | None = typer.Option(None, min=1, help="Red a consultar."),
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
        if not topology.node_exists(node):
            raise typer.BadParameter(f"node {node} no existe en la topologia")
        logger.info("cli.topology.node | node=%d network=%d", node, topology[node])

    if network is not None:
        if not topology.network_exists(network):
            raise typer.BadParameter(f"network {network} no existe en la topologia")
        logger.info(
            "cli.topology.network | network=%d nodes=%s",
            network,
            sorted(topology.get_nodes_for_network(network)),
        )


@app.command("plot-contact-plan")
def plot_contact_plan(
    cp_path: Path = typer.Option(
        DEFAULT_CP_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path al contact plan JSON.",
    ),
    topology_path: Path | None = typer.Option(
        DEFAULT_TOPOLOGY_PATH,
        exists=True,
        dir_okay=False,
        readable=True,
        help="Path a la topologia JSON para colorear nodos por red.",
    ),
    output_path: Path | None = typer.Option(
        None,
        dir_okay=False,
        help="PNG de salida. Si se omite, usa <contact_plan>_teneto.png.",
    ),
    time_step: int = typer.Option(
        600,
        min=1,
        help="Tamano del bin temporal en segundos para discretizar contactos.",
    ),
    plot_kind: str = typer.Option(
        "slice",
        help="Tipo de grafico Teneto: slice o graphlet-stack.",
    ),
) -> None:
    resolved_output = output_path or cp_path.with_name(f"{cp_path.stem}_teneto.png")
    logger.info(
        "cli.plot_contact_plan.start | contact_plan=%s topology=%s output=%s time_step=%d plot_kind=%s",
        cp_path,
        topology_path,
        resolved_output,
        time_step,
        plot_kind,
    )

    try:
        generated_path = plot_contact_plan_with_teneto(
            cp_path,
            output_path=resolved_output,
            topology_path=topology_path,
            time_step=time_step,
            plot_kind=plot_kind,
        )
    except (RuntimeError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    logger.info("cli.plot_contact_plan.summary | output=%s", generated_path)


if __name__ == "__main__":
    _configure_logging()
    app()
