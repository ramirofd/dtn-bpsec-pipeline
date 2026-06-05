# BPSec Keys

Experimental tooling for studying how CGR routes, network domains, and BPSec
key requirements interact in DTN scenarios.

The repository is organized around three practical layers:

- scenario assets under `scenarios/`
- a stage-based Python API under `pipelines/`
- optimization and trace-analysis helpers under `models/`

## Repository Layout

```text
bpsec-keys/
├── docs/
│   └── stage-artifacts.md
├── models/
│   ├── README.md
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
│   ├── basic/
│   ├── wisee_four_planes_polar/
│   └── wisee_nse2_lunar_communication/
├── tests/
├── WISEE_2026_DTN_Security_Schemes_Optimization/
├── requirements.txt
└── requirements-optimization.txt
```

## Core Workflow

`SimulationPipeline` orchestrates the repository's main workflow:

1. `topology_load(...)` and `cp_load(...)` load topology and contact-plan data.
2. `RoutingStage.compute(...)` enumerates ordered node pairs and computes candidate routes.
3. `RouteAnnotationStage.annotate(...)` derives node paths, network paths, gateway nodes, and boundary crossings.
4. `SecurityPlanningStage.build_batch(...)` generates `ProtectionPlan` objects for one or more security models.

The pipeline exposes two execution modes:

- `SimulationPipeline.run(...)` loads JSON files from disk
- `SimulationPipeline.run_loaded(...)` operates on already-built in-memory topology and contact-plan objects

The repository also includes two important downstream helpers:

- `pipelines.route_activation`: converts security plans into optimization-ready route/key activation artifacts and reconstructs solved selections as `RouteActivationSelection`
- `modules.network.temporal_graph`: renders temporal contact graphs for notebook and reporting workflows

## Documentation Map

- Artifact guide: [`docs/stage-artifacts.md`](docs/stage-artifacts.md)
- Optimization and plotting guide: [`models/README.md`](models/README.md)
- Lunar NSE scenario notes: [`scenarios/wisee_nse2_lunar_communication/nse2_files/README.md`](scenarios/wisee_nse2_lunar_communication/nse2_files/README.md)

## Installation

The codebase uses Python 3.11+ syntax and ships with reproducible dependency
files.

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

`requirements-optimization.txt` adds `gurobipy` for the optimization models in
`models/`. That layer typically requires a valid Gurobi license.

If your workflow is notebook-first, install your preferred frontend
(`jupyterlab`, `notebook`, or `ipykernel`) on top of the base environment.

## Python Usage

### Run from JSON Files

```python
from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.simulation import SimulationPipeline

pipeline = SimulationPipeline()

result = pipeline.run(
    cp_path="scenarios/basic/contact_plan.json",
    topology_path="scenarios/basic/topology.json",
    security_models=(SecurityModelType.EDGE_TO_EDGE,),
    symmetric_keys=False,
    curr_time=0,
    routing_algorithm=CGRYenRouting(max_routes=3),
    num_routes=3,
)
```

If you pass a custom `routing_algorithm` and omit `num_routes`, the algorithm's
own configured default applies. Pass `num_routes` only when you want to
override that limit for a specific run.

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

When `symmetric_keys=True`, reciprocal `A->B` and `B->A` scopes are normalized
into the same key requirement for `NODE_TO_NODE` and `GROUP_TO_GROUP` keys.
The default is `False`, so directional scopes remain distinct.

## Scenario Assets

The `scenarios/` tree contains the datasets and exploratory notebooks used to
exercise the API.

- `scenarios/basic/`
  Minimal topology/contact-plan JSON plus `resultados.ipynb` and its rendered HTML export.
- `scenarios/wisee_four_planes_polar/`
  Polar-orbit scenario assets, two contact-plan variants, a notebook, and a dedicated temporal-graph script.
- `scenarios/wisee_nse2_lunar_communication/`
  Lunar scenario notebook, alternate topology files, a scenario image, and `nse2_files/` with Docker/NSE testbed material.

The notebooks are useful exploratory companions, but the most stable interface
in the repository is the Python API exercised by the tests.

## Optimization Layer

The `models/` directory adds optimization models on top of a `SimulationResult`
and uses the route-activation abstractions from `pipelines/route_activation.py`.

Main modules:

- `model1_max_routes.py`: maximize enabled routes under a key budget
- `model2_min_keys.py`: minimize keys for a target connectivity level
- `model3_min_keys_full_connectivity.py`: minimize keys for full ordered-pair coverage
- `model4_max_connectivity_under_budget.py`: maximize ordered-pair connectivity under a key budget
- `plot_utils.py`: shared dataframe builders and plotting helpers for solved traces

The most explanatory optimization artifact is usually `RouteActivationSelection`,
which reconstructs the selected routes, contacts, gateway nodes, and key scopes
from a solved activation model.

For a detailed walkthrough of that layer, see [`models/README.md`](models/README.md).

## Additional Materials

- `WISEE_2026_DTN_Security_Schemes_Optimization/` contains the paper draft and supporting figures for the WISEE 2026 workflow.

## Tests

The automated suite currently covers:

- `tests/test_00_routing_stage.py`: ordered-pair enumeration and routing-stage defaults
- `tests/test_01_annotation_stage.py`: route annotation, boundary detection, and empty-route validation
- `tests/test_02_security_stage.py`: scaffold for dedicated security-stage tests; test bodies are currently commented out
- `tests/test_03_route_activation_stage.py`: route/key activation planning and solved-trace reconstruction
- `tests/test_04_plot_utils.py`: dataframe builders derived from `RouteActivationSelection`
- `tests/test_05_temporal_graph.py`: temporal graph plotting helper
- `tests/test_int_00_two_nodes.py`: two-node end-to-end scenarios
- `tests/test_int_01_three_nodes.py`: three-node boundary-crossing scenarios
- `tests/test_int_02_four_nodes.py`: four-node, multi-network integration scenarios
- `tests/test_int_03_route_catalog.py`: route-catalog expectations across security models

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
