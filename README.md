# BPSec Keys

Toolchain experimental para estudiar la relacion entre rutas CGR, dominios de
red y requerimientos criptograficos BPSec en escenarios DTN.

La superficie publica del proyecto quedo reducida a dos formas de uso:

- scripts de escenario en `scenarios/examples/...`
- API Python basada en etapas dentro de `pipelines/`

No hay una CLI general ni wrappers legacy de compatibilidad.

## Estructura

```text
bpsec-keys/
├── pipelines/
│   ├── routing.py
│   ├── simulation.py
│   └── route_activation.py
├── modules/
│   ├── network/
│   │   ├── topology.py
│   │   ├── py_cgr_lib.py
│   │   └── cgr/
│   └── security/
│       ├── __init__.py
│       ├── annotated_routes.py
│       ├── artifacts.py
│       ├── planning.py
│       ├── keys.py
│       ├── roles.py
│       └── models.py
└── tests/
    └── test_security_pipeline.py
└── scenarios/examples/
    ├── basic/
    └── two_planes_polar/
```

## Pipeline

1. `Topology.from_json_file(...)` y `cp_load(...)` cargan topologia y contactos.
2. `RoutingStage.compute(...)` calcula rutas para todos los pares ordenados.
3. `RouteAnnotationStage.annotate(...)` agrega `node_path`, `network_path`,
   gateways y cruces de frontera.
4. `SecurityPlanningStage.build_batch(...)` genera `ProtectionPlan` por modelo.
5. `RouteActivationPlanner` y `RouteActivationModelBuilder` agregan la etapa
   opcional de activacion y optimizacion.

`SimulationPipeline.run(...)` orquesta esas etapas de punta a punta.
`SimulationPipeline.run_loaded(...)` ejecuta la misma orquestacion sobre
objetos ya cargados en memoria, util para tests y escenarios armados por codigo.

`modules.security` expone la API publica de la capa de seguridad y concentra
los modelos concretos, artefactos y helpers de resolucion.

## Uso desde Python

```python
from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.simulation import SimulationPipeline

pipeline = SimulationPipeline()

result = pipeline.run(
    cp_path="scenarios/examples/basic/contact_plan.json",
    topology_path="scenarios/examples/basic/topology.json",
    security_models=(SecurityModelType.EDGE_TO_EDGE,),
    symmetric_keys=False,
    curr_time=0,
    routing_algorithm=CGRYenRouting(max_routes=3),
    num_routes=3,
)
```

Uso en memoria, sin depender de archivos JSON:

```python
from pipelines.simulation import SimulationPipeline
from tests.builders import make_contact, make_topology

pipeline = SimulationPipeline()

result = pipeline.run_loaded(
    topology=make_topology({1: (1, 2), 2: (3,)}),
    contact_plan=[
        make_contact(1, 2),
        make_contact(2, 3),
    ],
    security_models=(SecurityModelType.EDGE_TO_EDGE,),
    curr_time=0,
    num_routes=2,
)
```

`symmetric_keys=True` colapsa los scopes `A->B` y `B->A` para llaves
`NODE_TO_NODE` y `GROUP_TO_GROUP` durante la etapa de activacion/optimizacion.
Por defecto queda en `False`, asi que las llaves siguen siendo dirigidas.

## Escenarios

Scripts principales:

- `python scenarios/examples/basic/run.py`
- `python scenarios/examples/basic/show_node_keys.py`
- `python scenarios/examples/basic/optimize_route_activation.py`
- `python scenarios/examples/basic/sweep_route_activation_budget.py`
- `python scenarios/examples/two_planes_polar/run.py`
- `python scenarios/examples/two_planes_polar/characterize_routes.py`
- `python scenarios/examples/two_planes_polar/sweep_budget_connectivity.py`
- `python scenarios/examples/two_planes_polar/sweep_connectivity_target_keys.py`

## Dependencias

- `pydantic`
- `gurobipy`
- `matplotlib`

Instalacion:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Tests de regresion:

```bash
python -m unittest tests.test_security_pipeline
```

Tests por etapa:

- `tests/test_routing_stage.py`: prueba enumeracion de pares, propagacion de metadata y defaults del routing stage.
- `tests/test_annotation_stage.py`: prueba anotacion de rutas, cruces de frontera y validacion de rutas vacias.
- `tests/test_security_stage.py`: prueba la generacion de planes por modelo y el caso degenerado intra-network.
- `tests/test_route_activation_stage.py`: prueba deduplicacion de scopes, prefijos por par y colapso simetrico.

Para ver esos tests con salida mas descriptiva:

```bash
python -m unittest discover -s tests -p 'test_*stage.py' -v
```
