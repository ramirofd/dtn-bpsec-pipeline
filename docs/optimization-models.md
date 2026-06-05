# Optimization Models Guide

This guide documents the optimization layer built on top of
`SimulationResult`, with special attention to:

- what each optimization model solves
- what each solver returns
- how to interpret `RouteActivationSelection`
- which plotting helpers exist today in the repository

## Where This Layer Fits

The optimization modules consume the output of `SimulationPipeline` after the
security stage has already produced protection plans.

```text
SimulationPipeline
    -> SimulationResult
        -> result.security
            -> RouteActivationPlanner / attach_route_activation_constraints(...)
                -> Gurobi optimization models
                    -> traces + DataFrame summaries
```

The relevant source files are:

- `models/model1_max_routes.py`
- `models/model2_min_keys.py`
- `models/model3_min_keys_full_connectivity.py`
- `models/model4_max_connectivity_under_budget.py`
- `models/plot_utils.py`
- `pipelines/route_activation.py`

## Input Contract

All four optimization models receive:

```python
result: SimulationResult
security_model: SecurityModelType
```

That `result` must already contain security plans for the requested
`security_model`.

Typical setup:

```python
from modules.security.models import SecurityModelType
from pipelines.routing import CGRYenRouting
from pipelines.simulation import SimulationPipeline

pipeline = SimulationPipeline()

result = pipeline.run(
    cp_path="scenarios/basic/contact_plan.json",
    topology_path="scenarios/basic/topology.json",
    security_models=tuple(SecurityModelType),
    curr_time=0,
    routing_algorithm=CGRYenRouting(max_routes=3),
    num_routes=3,
)
```

If you only build one security model during the pipeline run, only that model
will be available to the optimization layer.

## Shared Output Contract

All `solve_for_security_model(...)` functions return:

```python
(traces, df)
```

Where:

- `df` is a sweep summary `DataFrame`
- `traces` is a tuple aligned row by row with `df`
- if a sweep point has no feasible solution, the matching `trace` entry is `None`

This makes it possible to move from an aggregate curve back to the exact
selected routes and keys that produced one point in the curve.

## What a Trace Represents

Each non-`None` trace is a `RouteActivationSelection`.

It summarizes one concrete solved selection:

- `selected_pairs`
- `selected_route_ids`
- `selected_key_scopes`
- `routes`
- `keys`

### Route-Level Detail

Each element of `trace.routes` contains:

- `route_id`
- `pair`
- `pair_id`
- `local_route_id`
- `node_path`
- `network_path`
- `boundary_crossings`
- `gateway_nodes`
- `required_key_scopes`
- `contacts`
- `operations`
- `notes`

This is usually the best artifact for explaining why a solution needs the keys
it selected.

### Key-Level Detail

Each element of `trace.keys` contains:

- `scope`
- `route_ids`
- `pair_ids`
- `operation_ids`

This is usually the best artifact for measuring reuse:

- how many routes share one key scope
- how many ordered pairs depend on one key scope
- how many protection operations collapse onto the same selected key

## Model Comparison

### Model 1: `model1_max_routes.py`

Goal:

- maximize enabled routes
- under a maximum active-key budget

Sweep axis:

- `max_keys`

Summary columns:

- `max_keys`
- `selected_routes`
- `selected_pairs`
- `selected_keys`
- `connectivity_pct`
- `model`

Signature:

```python
from models.model1_max_routes import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Typical usage:

```python
df_m1 = pd.DataFrame()
traces_m1 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m1[sec_model.name] = dict(zip(sec_df["max_keys"], sec_traces))
    df_m1 = pd.concat([df_m1, sec_df], ignore_index=True)
```

### Model 2: `model2_min_keys.py`

Goal:

- minimize selected keys
- while reaching a target connectivity percentage

Sweep axis:

- `target_connectivity_pct`

Summary columns:

- `target_connectivity_pct`
- `required_pairs`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

Signature:

```python
from models.model2_min_keys import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Typical usage:

```python
df_m2 = pd.DataFrame()
traces_m2 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m2[sec_model.name] = dict(zip(sec_df["target_connectivity_pct"], sec_traces))
    df_m2 = pd.concat([df_m2, sec_df], ignore_index=True)
```

### Model 3: `model3_min_keys_full_connectivity.py`

Goal:

- minimize selected keys
- while enforcing at least one route for every ordered pair

Sweep axis:

- no multi-point sweep; one solved point per security model

Summary columns:

- `target_connectivity_pct`
- `required_pairs`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

Signature:

```python
from models.model3_min_keys_full_connectivity import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Typical usage:

```python
df_m3 = pd.DataFrame()
traces_m3 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m3[sec_model.name] = sec_traces[0] if sec_traces else None
    df_m3 = pd.concat([df_m3, sec_df], ignore_index=True)
```

### Model 4: `model4_max_connectivity_under_budget.py`

Goal:

- maximize selected pairs
- under a maximum active-key budget
- break ties by minimizing selected keys and then maximizing selected routes

Sweep axis:

- `max_keys`

Summary columns:

- `max_keys`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

Signature:

```python
from models.model4_max_connectivity_under_budget import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Typical usage:

```python
df_m4 = pd.DataFrame()
traces_m4 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m4[sec_model.name] = dict(zip(sec_df["max_keys"], sec_traces))
    df_m4 = pd.concat([df_m4, sec_df], ignore_index=True)
```

## Plotting Helpers

`models/plot_utils.py` provides the shared plotting and dataframe-building
layer. Model files then expose thin wrappers for the most common views.

### Shared Setup

```python
from models.plot_utils import set_plot_theme

set_plot_theme()
```

### Shared Data Builders

These helpers convert `RouteActivationSelection` traces into dataframes:

- `build_key_scope_activation_data(...)`
- `build_contact_usage_data(...)`
- `build_pair_coverage_data(...)`
- `build_gateway_usage_data(...)`
- `build_network_crossing_data(...)`
- `build_key_reuse_data(trace)`

### Shared Generic Plotters

- `plot_metric_curve(df, ...)`
- `plot_metric_bars_by_model(df, ...)`
- `plot_key_scope_heatmap(...)`
- `plot_contact_usage_heatmap(...)`
- `plot_pair_coverage_heatmap(...)`
- `plot_gateway_usage_heatmap(...)`
- `plot_network_crossing_heatmap(...)`
- `plot_key_reuse_bar(trace, ...)`
- `plot_gateway_usage_bar(trace, ...)`
- `plot_network_crossing_bar(trace, ...)`

## Model-Specific Plot Wrappers

### Model 1 Wrappers

- `plot_selected_routes_vs_keys(df, normalize=False, ...)`
- `plot_budget_key_scope_heatmap(traces_by_budget, ...)`
- `plot_budget_contact_usage_heatmap(traces_by_budget, ...)`
- `plot_budget_gateway_usage_heatmap(traces_by_budget, ...)`
- `plot_budget_network_crossing_heatmap(traces_by_budget, ...)`

Example:

```python
from models.model1_max_routes import (
    plot_budget_contact_usage_heatmap,
    plot_budget_key_scope_heatmap,
    plot_selected_routes_vs_keys,
)

plot_selected_routes_vs_keys(df_m1)
plot_budget_key_scope_heatmap(traces_m1["EDGE_TO_EDGE"])
plot_budget_contact_usage_heatmap(traces_m1["EDGE_TO_EDGE"])
```

Note:

- this curve uses actual `selected_keys` on the x-axis
- the underlying sweep still iterates over `max_keys`

### Model 2 Wrappers

- `plot_selected_keys_vs_connectivity(df, normalize_y=True, ...)`
- `plot_connectivity_pair_coverage_heatmap(traces_by_connectivity, all_pairs=..., ...)`
- `plot_connectivity_key_scope_heatmap(traces_by_connectivity, ...)`
- `plot_connectivity_contact_usage_heatmap(traces_by_connectivity, ...)`
- `plot_connectivity_network_crossing_heatmap(traces_by_connectivity, ...)`

Example:

```python
from models.model2_min_keys import (
    plot_connectivity_pair_coverage_heatmap,
    plot_connectivity_key_scope_heatmap,
    plot_selected_keys_vs_connectivity,
)

plot_selected_keys_vs_connectivity(df_m2)
plot_connectivity_pair_coverage_heatmap(
    traces_m2["EDGE_TO_EDGE"],
    all_pairs=result.security.pairs,
)
plot_connectivity_key_scope_heatmap(traces_m2["EDGE_TO_EDGE"])
```

Note:

- by default `plot_selected_keys_vs_connectivity(...)` shows keys as a percentage
- use `normalize_y=False` for absolute key counts

### Model 3 Wrappers

- `plot_selected_keys_by_model(df, normalize=True, ...)`
- `plot_selected_routes_by_model(df, normalize=False, ...)`
- `plot_full_connectivity_key_reuse(trace, metric="route_count", ...)`
- `plot_full_connectivity_gateway_usage(trace, metric="route_count", ...)`
- `plot_full_connectivity_network_crossings(trace, metric="crossing_count", ...)`

Example:

```python
from models.model3_min_keys_full_connectivity import (
    plot_full_connectivity_gateway_usage,
    plot_full_connectivity_key_reuse,
    plot_selected_keys_by_model,
    plot_selected_routes_by_model,
)

plot_selected_keys_by_model(df_m3)
plot_selected_routes_by_model(df_m3)
plot_full_connectivity_key_reuse(traces_m3["EDGE_TO_EDGE"])
plot_full_connectivity_gateway_usage(traces_m3["EDGE_TO_EDGE"])
```

Note:

- by default `plot_selected_keys_by_model(...)` shows percentages
- use `normalize=False` for absolute key counts

### Model 4 Wrappers

- `plot_connectivity_vs_budget(df, normalize_x=True, ...)`
- `plot_budget_pair_coverage_heatmap(traces_by_budget, all_pairs=..., ...)`
- `plot_budget_key_scope_heatmap(traces_by_budget, ...)`
- `plot_budget_contact_usage_heatmap(traces_by_budget, ...)`
- `plot_budget_network_crossing_heatmap(traces_by_budget, ...)`

Example:

```python
from models.model4_max_connectivity_under_budget import (
    plot_budget_pair_coverage_heatmap,
    plot_connectivity_vs_budget,
)

plot_connectivity_vs_budget(df_m4)
plot_budget_pair_coverage_heatmap(
    traces_m4["EDGE_TO_EDGE"],
    all_pairs=result.security.pairs,
)
```

## Recommended Notebook Pattern

1. Run `SimulationPipeline`.
2. Build security plans for the security models you want to compare.
3. Solve the optimization model for each `SecurityModelType`.
4. Keep the summary dataframes (`df_m1`, `df_m2`, `df_m3`, `df_m4`) separate from the trace maps.
5. Use model-specific wrappers first.
6. Drop to `models.plot_utils` when you need a custom analysis or export.

## When to Use `plot_utils.py` Directly

Use it directly when you want to:

- compare different scenarios with the same type of heatmap
- export trace-derived tables for a paper or spreadsheet
- build a visualization that is not already wrapped by one model module
- inspect one selected solution without re-reading the raw optimization model

Example:

```python
from models.plot_utils import build_contact_usage_data

contact_df = build_contact_usage_data(
    traces_m1["EDGE_TO_EDGE"],
    sweep_label="max_keys",
)
```

## About `None` Traces

In sweep-based models such as model 1, model 2, and model 4, some sweep points
may be infeasible. In those cases:

- the row still exists in `df`
- the corresponding entry in `traces` is `None`

The shared trace-based dataframe builders and plotters are designed to ignore
those `None` entries.
