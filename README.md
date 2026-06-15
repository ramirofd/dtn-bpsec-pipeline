# BPSec Keys

Tooling for exploring how CGR route catalogs, network boundaries, and BPSec
key scopes interact in DTN scenarios.

The repository has three working layers:

- `scenarios/` for tracked scenario assets and notebooks
- `pipelines/` for the stage-based API
- `models/` for optimization and trace-analysis helpers

## Repository Layout

```text
bpsec-keys/
├── docs/
│   ├── optimization-models.md
│   └── stage-artifacts.md
├── models/
│   ├── model1_max_routes.py
│   ├── model2_min_keys.py
│   ├── model3_min_keys_full_connectivity.py
│   ├── model4_max_connectivity_under_budget.py
│   └── plot_utils.py
├── modules/
│   ├── network/
│   │   ├── cgr/
│   │   ├── py_cgr_lib.py
│   │   ├── temporal_graph.py
│   │   └── topology.py
│   └── security/
│       ├── annotated_routes.py
│       ├── artifacts.py
│       ├── keys.py
│       ├── models.py
│       ├── planning.py
│       └── roles.py
├── pipelines/
│   ├── __init__.py
│   ├── route_activation.py
│   ├── routing.py
│   └── simulation.py
├── scenarios/
│   └── wisee_four_planes_polar/
├── tests/
├── requirements.txt
└── requirements-optimization.txt
```

Your working copy may also contain ignored notebooks, figures, or paper
material. Those local artifacts are not part of the tracked interface
documented here.

## Core Workflow

`SimulationPipeline` drives the main workflow:

1. `topology_load(...)` and `cp_load(...)` load topology and contact-plan data.
2. `RoutingStage.compute(...)` enumerates ordered node pairs and computes candidate routes.
3. `RouteAnnotationStage.annotate(...)` derives node paths, network paths, gateway nodes, and boundary crossings.
4. `SecurityPlanningStage.build_batch(...)` generates `ProtectionPlan` objects for one or more security models.

The pipeline exposes two execution modes:

- `SimulationPipeline.run(...)` loads JSON files from disk
- `SimulationPipeline.run_loaded(...)` works with already-built in-memory topology and contact-plan objects

Two downstream helpers show up often in notebooks and analysis scripts:

- `pipelines.route_activation` turns security plans into optimization-ready route/key activation artifacts and reconstructs solved selections as `RouteActivationSelection`
- `modules.network.temporal_graph` renders temporal contact graphs for reporting and exploratory analysis

## Documentation Map

- Artifact guide: [`docs/stage-artifacts.md`](docs/stage-artifacts.md)
- Optimization and plotting guide: [`docs/optimization-models.md`](docs/optimization-models.md)

## Installation

The project uses Python 3.11+ syntax and ships with version-constrained
requirements files.

Base environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional optimization dependencies:

```bash
pip install -r requirements-optimization.txt
```

`requirements.txt` covers the core pipeline plus plotting and notebook-oriented
analysis helpers:

- `pydantic`
- `matplotlib`
- `numpy`
- `pandas`
- `teneto`

`requirements-optimization.txt` extends that base environment with `gurobipy`
for the optimization models in `models/`. That layer still requires a valid
Gurobi license.

If your workflow is notebook-first, add your preferred frontend on top of the
base environment, such as `jupyterlab`, `notebook`, or `ipykernel`.

## Python Usage

### Run from JSON Files

```python
from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.simulation import SimulationPipeline

pipeline = SimulationPipeline()

result = pipeline.run(
    cp_path="scenarios/wisee_four_planes_polar/contact_plan.json",
    topology_path="scenarios/wisee_four_planes_polar/topology.json",
    security_models=(SecurityModelType.EDGE_TO_EDGE,),
    curr_time=0,
    routing_algorithm=CGRYenRouting(max_routes=3),
)
```

If you pass a custom `routing_algorithm` and omit `num_routes`, the algorithm's
own configured default applies. Pass `num_routes` only when you want to
override that limit for one specific run.

### Run from In-Memory Fixtures

This mirrors how the tests exercise the pipeline.

```python
from modules.security.models import SecurityModelType
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

When `symmetric_keys=True`, the flag is preserved in
`result.security.symmetric_keys` and used by route-activation and optimization
helpers to normalize reciprocal `A->B` and `B->A` scopes for
`NODE_TO_NODE` and `GROUP_TO_GROUP` keys. The raw `plan.key_requirements`
inside `result.security.plans_by_model` remain directional.

## Scenario Assets

The tracked repository currently includes one scenario package:

- `scenarios/wisee_four_planes_polar/`
  Topology JSON, two contact-plan variants, one notebook, and a dedicated temporal-graph script.

The notebooks are useful companions for exploration, but the most stable
interface in the repository is still the Python API exercised by the tests.

## Optimization Layer

The `models/` directory adds optimization models on top of a `SimulationResult`
and uses the route-activation abstractions from `pipelines/route_activation.py`.

Main modules:

- `model1_max_routes.py`: maximize enabled routes under a key budget
- `model2_min_keys.py`: minimize keys for a target connectivity level
- `model3_min_keys_full_connectivity.py`: minimize keys for full ordered-pair coverage
- `model4_max_connectivity_under_budget.py`: maximize ordered-pair connectivity under a key budget
- `plot_utils.py`: shared dataframe builders and plotting helpers for solved traces

The most explanatory optimization artifact is usually
`RouteActivationSelection`, which reconstructs the selected routes, contacts,
gateway nodes, and key scopes from a solved activation model.

For a detailed walkthrough of that layer, see
[`docs/optimization-models.md`](docs/optimization-models.md).

## Tests

The executed suite currently covers:

- `tests/test_00_routing_stage.py`: ordered-pair enumeration and routing-stage defaults
- `tests/test_01_annotation_stage.py`: route annotation, boundary detection, and empty-route validation
- `tests/test_03_route_activation_stage.py`: route/key activation planning and solved-trace reconstruction
- `tests/test_04_plot_utils.py`: dataframe builders derived from `RouteActivationSelection`
- `tests/test_05_temporal_graph.py`: temporal graph plotting helper
- `tests/test_int_00_two_nodes.py`: two-node end-to-end scenarios
- `tests/test_int_01_three_nodes.py`: three-node boundary-crossing scenarios
- `tests/test_int_02_four_nodes.py`: four-node, multi-network integration scenarios
- `tests/test_int_03_route_catalog.py`: route-catalog expectations across security models

There is also a scaffold at `tests/test_02_security_stage.py`, but its test
bodies are currently commented out and it is not part of the executed suite.

Run the full suite with:

```bash
python -m unittest discover -s tests -v
```

Run the stage-oriented tests with:

```bash
python -m unittest \
  tests.test_00_routing_stage \
  tests.test_01_annotation_stage \
  tests.test_03_route_activation_stage \
  tests.test_04_plot_utils \
  tests.test_05_temporal_graph -v
```
