# Stage Artifacts Guide

This guide is a practical map of what each pipeline stage returns and how the
pieces line up once you start exploring results in notebooks or scripts.

## Pipeline Lineage

The repository's main execution flow produces artifacts in layers:

```text
topology + contact plan
        |
        v
RoutingStage.compute(...)
        |
        v
RoutingBatchResult
        |
        v
RouteAnnotationStage.annotate(...)
        |
        v
AnnotationBatchResult
        |
        v
SecurityPlanningStage.build_batch(...)
        |
        v
SecurityBatchResult
        |
        v
SimulationResult
```

The optimization layer in `models/` works on top of `SimulationResult` and can
also emit trace artifacts such as `RouteActivationSelection`.

## Shared Indexing Rules

All batch-level stage results are indexed by ordered node pair:

- a pair is always represented as `(source_node, destination_node)`
- `pairs` preserves the full ordered pair list used in the run
- `routes_by_pair`, `annotated_routes_by_pair`, and `plans_by_model[model]`
  all use the same pair keys

That alignment is deliberate. You can move from raw routes, to annotated
routes, to protection plans for the same pair without rebuilding joins by hand.

## Stage 1: Routing

Produced by `RoutingStage.compute(...)`.

### Batch Artifact

`RoutingBatchResult` contains:

- `topology`: the validated `Topology` used for the run
- `contact_plan_size`: number of contacts loaded into the routing run
- `pairs`: ordered `(source, destination)` pairs enumerated from the topology
- `routes_by_pair`: candidate `Route` objects for each ordered pair

### Unit Artifact

`routes_by_pair[pair]` is a tuple of `Route` objects from
`modules.network.cgr.models`.

Useful `Route` attributes and methods:

- `route.get_hops()`: returns the ordered list of `Contact` hops
- `route.best_delivery_time`: arrival-oriented ranking metric
- `route.volume`: bottleneck effective volume across the full route
- `route.confidence`: product of per-contact confidence values
- `route.to_node`, `route.next_node`, `route.from_time`, `route.to_time`

Each hop is a `Contact` with fields such as:

- `frm`, `to`
- `start`, `end`
- `rate`, `owlt`
- `volume`

### What You Can Compute From Routing

How many routes were found per pair:

```python
route_counts = {
    pair: len(routes)
    for pair, routes in result.routing.routes_by_pair.items()
}
```

How many hops each candidate route has:

```python
hop_counts = {
    pair: [len(route.get_hops()) for route in routes]
    for pair, routes in result.routing.routes_by_pair.items()
}
```

Best delivery time of the first route per pair:

```python
best_delivery_by_pair = {
    pair: routes[0].best_delivery_time
    for pair, routes in result.routing.routes_by_pair.items()
    if routes
}
```

## Stage 2: Annotation

Produced by `RouteAnnotationStage.annotate(...)`.

### Batch Artifact

`AnnotationBatchResult` keeps the routing context and adds:

- `annotated_routes_by_pair`: tuple of `AnnotatedRoute` objects for each pair

The batch still carries:

- `topology`
- `contact_plan_size`
- `pairs`
- `routes_by_pair`

This is the first artifact that is both route-aware and network-aware.

### Unit Artifact

`AnnotatedRoute` adds topology-derived structure on top of each raw route:

- `route_id`: stable local identifier such as `route-1`
- `src_node`, `dst_node`
- `source_network`, `destination_network`
- `hops`: tuple of `AnnotatedHop`
- `node_path`: ordered node sequence, including endpoints
- `network_path`: ordered network sequence aligned with `node_path`
- `boundary_crossings`: explicit inter-network transitions
- `gateway_nodes`: nodes that participate in a crossing

Each `AnnotatedHop` tells you:

- `hop_index`
- `from_node`, `to_node`
- `from_network`, `to_network`
- `crosses_network_boundary`
- `from_role`, `to_role`

Each `BoundaryCrossing` isolates one network exit/entrance event:

- `crossing_index`
- `hop_index`
- `exit_node`, `entrance_node`
- `from_network`, `to_network`

### What You Can Compute From Annotation

Which routes cross at least one network boundary:

```python
cross_network_routes = {
    pair: [
        route.route_id
        for route in annotated_routes
        if route.boundary_crossings
    ]
    for pair, annotated_routes in result.annotation.annotated_routes_by_pair.items()
}
```

How many boundary crossings each route contains:

```python
boundary_counts = {
    (pair, route.route_id): len(route.boundary_crossings)
    for pair, annotated_routes in result.annotation.annotated_routes_by_pair.items()
    for route in annotated_routes
}
```

Gateway nodes used by each route:

```python
gateway_nodes = {
    (pair, route.route_id): sorted(route.gateway_nodes)
    for pair, annotated_routes in result.annotation.annotated_routes_by_pair.items()
    for route in annotated_routes
}
```

Route-level network sequences:

```python
network_paths = {
    (pair, route.route_id): route.network_path
    for pair, annotated_routes in result.annotation.annotated_routes_by_pair.items()
    for route in annotated_routes
}
```

## Stage 3: Security Planning

Produced by `SecurityPlanningStage.build_batch(...)`.

### Batch Artifact

`SecurityBatchResult` contains:

- `pairs`: the same ordered pair list used by earlier stages
- `symmetric_keys`: a flag carried into downstream route-activation and
  optimization helpers when reciprocal scopes should be normalized together
- `plans_by_model`: protection plans grouped by security model and by pair

The access pattern is:

```python
plans = result.security.plans_by_model[security_model][pair]
```

One subtle but important detail: `symmetric_keys` does not rewrite the
`ProtectionPlan` objects inside `plans_by_model`. Those plans keep the raw
directional requirements produced by the security model. Scope normalization
happens later in the route-activation layer when requested.

### Unit Artifact

Each item in `plans_by_model[model][pair]` is a `ProtectionPlan`.

`ProtectionPlan` contains:

- `route_id`: matches the annotated route used to build the plan
- `model`: `SecurityModelType`
- `operations`: concrete protection operations applied to the route
- `node_requirements`: node-local actions implied by those operations
- `key_requirements`: required key scopes implied by those operations
- `notes`: explanations for degenerate or collapsed cases

Each `ProtectionOperation` answers:

- what is being protected
- between which nodes or networks
- which hops it covers
- which key type is required
- why the operation exists

Its main fields are:

- `operation_id`
- `source_node`, `acceptor_node`
- `target_hop_indexes`
- `source_network`, `acceptor_network`
- `required_key_type`
- `key_source_id`, `key_target_id`
- `rationale`

Each `NodeSecurityRequirement` tells you what a specific node must do:

- `node_id`
- `role` such as `SOURCE` or `ACCEPT`
- `service`
- `key_type`
- `key_source_id`, `key_target_id`

Each `KeyRequirement` tells you which scoped key is needed:

- `operation_id`
- `key_type`
- `usage`
- `source_id`, `target_id`
- `local_node`
- `rationale`

`requirement.scope` returns the raw scope attached to that operation:

```python
requirement.scope
```

If you want the same symmetric view used by route activation and optimization,
normalize that scope explicitly:

```python
from modules.security.keys import normalize_key_scope

normalized_scope = normalize_key_scope(
    requirement.scope,
    symmetric=result.security.symmetric_keys,
)
```

For `NODE_TO_NODE` and `GROUP_TO_GROUP`, that can merge reciprocal `A->B` and
`B->A` scopes into one normalized requirement.

### What You Can Compute From Security Plans

Distinct raw key scopes required by one security model:

```python
from modules.security.models import SecurityModelType

model = SecurityModelType.EDGE_TO_EDGE

distinct_scopes = {
    requirement.scope
    for plans in result.security.plans_by_model[model].values()
    for plan in plans
    for requirement in plan.key_requirements
}
```

Distinct normalized scopes, using the same rule as the optimization helpers:

```python
from modules.security.keys import normalize_key_scope

normalized_scopes = {
    normalize_key_scope(
        requirement.scope,
        symmetric=result.security.symmetric_keys,
    )
    for plans in result.security.plans_by_model[model].values()
    for plan in plans
    for requirement in plan.key_requirements
}
```

How many operations each route needs under a given model:

```python
operation_counts = {
    (pair, plan.route_id): len(plan.operations)
    for pair, plans in result.security.plans_by_model[model].items()
    for plan in plans
}
```

Key scopes required for one pair:

```python
pair = (1, 4)

pair_key_scopes = [
    requirement.scope
    for plan in result.security.plans_by_model[model][pair]
    for requirement in plan.key_requirements
]
```

Node-level actions implied by a plan:

```python
node_actions = [
    (req.node_id, req.role.name, req.key_type.name, req.key_source_id, req.key_target_id)
    for req in plan.node_requirements
]
```

## Combined Artifact: SimulationResult

Produced by `SimulationPipeline.run(...)` and `SimulationPipeline.run_loaded(...)`.

`SimulationResult` is the top-level container returned to most callers:

- `topology`
- `contact_plan_size`
- `routing`
- `annotation`
- `security`

Use it when you want one object that preserves the full lineage of the run.

### Typical Navigation Pattern

```python
pair = (1, 4)
security_model = SecurityModelType.EDGE_TO_EDGE

raw_routes = result.routing.routes_by_pair[pair]
annotated_routes = result.annotation.annotated_routes_by_pair[pair]
plans = result.security.plans_by_model[security_model][pair]

for raw_route, annotated_route, plan in zip(raw_routes, annotated_routes, plans):
    print(annotated_route.route_id)
    print(annotated_route.node_path)
    print([requirement.scope for requirement in plan.key_requirements])
```

That is usually the cleanest way to explain one route end to end:

1. show the raw contacts chosen by routing
2. show how the route traverses nodes and networks
3. show which protection operations and key scopes that traversal induces

## Optimization Trace Artifacts

If you run the optimization models, the most explanatory artifact is usually
`RouteActivationSelection` from `pipelines.route_activation`.

It adds solved-decision context such as:

- `selected_pairs`
- `selected_route_ids`
- `selected_key_scopes`
- `routes`
- `keys`

This is the best artifact when you want to answer questions like:

- which routes were activated by the optimization model
- which keys were actually selected
- which contacts and gateway nodes are used by the selected solution
- how much key reuse was achieved

The helper functions in `models/plot_utils.py` already convert those traces into
analysis-friendly tables:

- `build_key_scope_activation_data(...)`
- `build_contact_usage_data(...)`
- `build_pair_coverage_data(...)`
- `build_gateway_usage_data(...)`
- `build_network_crossing_data(...)`
- `build_key_reuse_data(trace)`
