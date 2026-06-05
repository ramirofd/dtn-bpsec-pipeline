# BPSec Keys

Experimental tooling for studying how CGR routes, network domains, and BPSec
key requirements interact in DTN scenarios.

The repository currently exposes two main entry points:

- scenario assets under `scenarios/`
- a stage-based Python API under `pipelines/`

## Repository Layout

```text
bpsec-keys/
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
│   │   └── topology.py
│   └── security/
│       ├── annotated_routes.py
│       ├── artifacts.py
│       ├── keys.py
│       ├── models.py
│       ├── planning.py
│       └── roles.py
├── pipelines/
│   ├── routing.py
│   ├── route_activation.py
│   └── simulation.py
├── scenarios/
│   ├── basic/
│   ├── edge_based_comparison/
│   ├── four_planes_polar/
│   └── two_planes_polar/
└── tests/
    ├── test_00_routing_stage.py
    ├── test_01_annotation_stage.py
    ├── test_03_route_activation_stage.py
    ├── test_04_plot_utils.py
    ├── test_int_00_two_nodes.py
    ├── test_int_01_three_nodes.py
    ├── test_int_02_four_nodes.py
    └── test_int_03_route_catalog.py
```

## Pipeline

`SimulationPipeline` orchestrates the repository's core workflow:

1. `topology_load(...)` and `cp_load(...)` load topology and contact-plan data.
2. `RoutingStage.compute(...)` enumerates ordered node pairs and computes routes.
3. `RouteAnnotationStage.annotate(...)` derives `node_path`, `network_path`,
   gateway nodes, and boundary crossings for every route.
4. `SecurityPlanningStage.build_batch(...)` generates `ProtectionPlan`
   instances for the requested security models.

The pipeline exposes two execution modes:

- `SimulationPipeline.run(...)` loads JSON files from disk.
- `SimulationPipeline.run_loaded(...)` operates on already-built in-memory
  topology and contact-plan objects.

`modules.security` contains the reusable security-planning domain model, and
`models/` contains optimization and plotting utilities built on top of
`SimulationResult`.

## Installation

The project is currently exercised with Python 3.11+ syntax and has a base
`requirements.txt` to make local setup reproducible:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you also want to run the optimization models under `models/`, install the
optional Gurobi layer as well:

```bash
pip install -r requirements-optimization.txt
```

If your workflow is notebook-first, install your preferred notebook frontend
(`jupyterlab`, `notebook`, or `ipykernel`) on top of the base requirements.

## Python Usage

### Run from JSON files

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

### Run from in-memory fixtures

This mirrors how the test suite exercises the pipeline.

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

## Scenarios

The `scenarios/` tree currently contains data files, notebooks, and one plotting
helper script.

The notebooks are useful as exploratory artifacts, but the most stable and
well-exercised interface is the Python API used by the test suite.

## Optimization Models

The `models/` directory adds optimization layers on top of a
`SimulationResult`:

- `model1_max_routes.py`: maximize enabled routes under a key budget
- `model2_min_keys.py`: minimize keys for a target connectivity level
- `model3_min_keys_full_connectivity.py`: minimize keys for full pair coverage
- `model4_max_connectivity_under_budget.py`: maximize pair connectivity under a key budget
- `plot_utils.py`: shared builders and plotting helpers for trace analysis

These modules depend on `gurobipy` and `pandas`.

## Dependencies

The repository now includes:

- `requirements.txt` for the core pipeline, plotting helpers, and temporal
  graph notebook support
- `requirements-optimization.txt` for the optimization models in `models/`

The main packages captured there are:

- `pydantic`
- `matplotlib`
- `numpy`
- `teneto`
- `pandas`

`gurobipy` is intentionally kept in the optional optimization requirements
because not every use case needs it and it typically requires a valid Gurobi
license.

## Tests

The current automated coverage is organized around the files below:

- `tests/test_00_routing_stage.py`: ordered-pair enumeration and routing-stage
  defaults
- `tests/test_01_annotation_stage.py`: route annotation, gateway detection, and
  empty-route validation
- `tests/test_03_route_activation_stage.py`: key-scope deduplication,
  symmetric-key collapsing, and activation trace reconstruction
- `tests/test_04_plot_utils.py`: trace-to-dataframe builders and plotting
  helpers
- `tests/test_int_00_two_nodes.py`: two-node end-to-end integration scenarios
- `tests/test_int_01_three_nodes.py`: three-node boundary-crossing scenarios
- `tests/test_int_02_four_nodes.py`: four-node, multi-network integration
  scenarios
- `tests/test_int_03_route_catalog.py`: route-catalog expectations across
  security models

`tests/test_02_security_stage.py` exists as a scaffold, but its test cases are
currently commented out.

Run the full suite with:

```bash
python -m unittest discover -s tests
```

Run only the stage-oriented tests with:

```bash
python -m unittest tests.test_00_routing_stage \
  tests.test_01_annotation_stage \
  tests.test_03_route_activation_stage \
  tests.test_04_plot_utils -v
```
