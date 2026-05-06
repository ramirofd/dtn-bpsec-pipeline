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
│       ├── annotated_routes.py
│       ├── planning.py
│       ├── keys.py
│       ├── roles.py
│       └── models.py
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
    curr_time=0,
    routing_algorithm=CGRYenRouting(max_routes=3),
    num_routes=3,
)
```

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
