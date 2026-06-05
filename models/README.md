# Models

Esta carpeta contiene:

- los cuatro modelos de optimizacion que corren sobre un `SimulationResult`
- wrappers de plots especificos para cada modelo
- una capa comun de utilidades de visualizacion en `plot_utils.py`

La idea es que las notebooks de distintos escenarios puedan reutilizar exactamente la misma API.

## Estructura

- `model1_max_routes.py`
  Maximiza la cantidad de rutas habilitadas dado un presupuesto de llaves.
- `model2_min_keys.py`
  Minimiza la cantidad de llaves para alcanzar un objetivo de conectividad.
- `model3_min_keys_full_connectivity.py`
  Minimiza la cantidad de llaves para garantizar al menos una ruta por par.
- `model4_max_connectivity_under_budget.py`
  Maximiza la conectividad entre pares dado un presupuesto de llaves.
- `plot_utils.py`
  Builders y plots genericos basados en `traces`, independientes del modelo.

## Requisito de entrada

Los tres modelos reciben un `result` generado por `SimulationPipeline.run(...)` o `SimulationPipeline.run_loaded(...)`.

Ejemplo:

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

## Contrato comun de salida

Los cuatro `solve_for_security_model(...)` devuelven:

```python
(traces, df)
```

Donde:

- `df` es el `DataFrame` resumen tradicional del sweep
- `traces` es una tupla alineada fila por fila con `df`
- cuando un punto del sweep no tiene solucion, la posicion correspondiente en `traces` vale `None`

Esto permite pasar de una curva agregada a la solucion concreta que la produjo.

## Que contiene un trace

Cada trace es un `RouteActivationSelection` y resume una solucion optima concreta:

- `selected_pairs`
- `selected_route_ids`
- `selected_key_scopes`
- `routes`
- `keys`

Cada elemento de `routes` incluye:

- `node_path`
- `network_path`
- `boundary_crossings`
- `gateway_nodes`
- `contacts`
- `operations`

Cada elemento de `keys` incluye:

- `scope`
- `route_ids`
- `pair_ids`
- `operation_ids`

En otras palabras: desde el trace se puede volver a las llaves elegidas, las rutas elegidas, los contactos usados y los cruces entre redes.

## Modelo 1

Archivo: `model1_max_routes.py`

Objetivo:

- maximizar `selected_routes`
- sujeto a un presupuesto maximo de llaves activadas

Firma:

```python
from models.model1_max_routes import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Columnas de `df`:

- `max_keys`
- `selected_routes`
- `selected_pairs`
- `selected_keys`
- `connectivity_pct`
- `model`

Uso tipico en notebook:

```python
df_m1 = pd.DataFrame()
traces_m1 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m1[sec_model.name] = dict(zip(sec_df["max_keys"], sec_traces))
    df_m1 = pd.concat([df_m1, sec_df], ignore_index=True)
```

## Modelo 2

Archivo: `model2_min_keys.py`

Objetivo:

- minimizar `selected_keys`
- sujeto a un objetivo de conectividad en porcentaje

Firma:

```python
from models.model2_min_keys import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Columnas de `df`:

- `target_connectivity_pct`
- `required_pairs`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

Uso tipico en notebook:

```python
df_m2 = pd.DataFrame()
traces_m2 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m2[sec_model.name] = dict(zip(sec_df["target_connectivity_pct"], sec_traces))
    df_m2 = pd.concat([df_m2, sec_df], ignore_index=True)
```

## Modelo 3

Archivo: `model3_min_keys_full_connectivity.py`

Objetivo:

- minimizar `selected_keys`
- garantizando al menos una ruta por cada par ordenado

Firma:

```python
from models.model3_min_keys_full_connectivity import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Columnas de `df`:

- `target_connectivity_pct`
- `required_pairs`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

En este modelo el sweep tiene un solo punto, por eso lo usual es guardar un trace unico por modelo:

```python
df_m3 = pd.DataFrame()
traces_m3 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m3[sec_model.name] = sec_traces[0] if sec_traces else None
    df_m3 = pd.concat([df_m3, sec_df], ignore_index=True)
```

## Modelo 4

Archivo: `model4_max_connectivity_under_budget.py`

Objetivo:

- maximizar `selected_pairs`
- sujeto a un presupuesto maximo de llaves activadas
- desempatar minimizando `selected_keys` y luego maximizando `selected_routes`

Firma:

```python
from models.model4_max_connectivity_under_budget import solve_for_security_model

traces, df = solve_for_security_model(result, SecurityModelType.EDGE_TO_EDGE)
```

Columnas de `df`:

- `max_keys`
- `selected_pairs`
- `selected_routes`
- `selected_keys`
- `achieved_connectivity_pct`
- `model`

Uso tipico en notebook:

```python
df_m4 = pd.DataFrame()
traces_m4 = {}

for sec_model in SecurityModelType:
    sec_traces, sec_df = solve_for_security_model(result, sec_model)
    traces_m4[sec_model.name] = dict(zip(sec_df["max_keys"], sec_traces))
    df_m4 = pd.concat([df_m4, sec_df], ignore_index=True)
```

## Plots comunes

Archivo: `plot_utils.py`

### Setup

```python
from models.plot_utils import set_plot_theme

set_plot_theme()
```

### Helpers visuales

- `palette_for(values)`
- `set_plot_theme(style="whitegrid")`

### Builders de datos desde traces

Estos helpers convierten `traces` a `DataFrame` para análisis o plots propios:

- `build_key_scope_activation_data(...)`
- `build_contact_usage_data(...)`
- `build_pair_coverage_data(...)`
- `build_gateway_usage_data(...)`
- `build_network_crossing_data(...)`
- `build_key_reuse_data(trace)`

### Plotters genericos

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

## Plots especificos por modelo

La recomendacion es usar primero los wrappers especificos de cada archivo de modelo y bajar a `plot_utils.py` solo cuando haga falta algo mas custom.

### Modelo 1

Archivo: `model1_max_routes.py`

- `plot_selected_routes_vs_keys(df, normalize=False, ...)`
- `plot_budget_key_scope_heatmap(traces_by_budget, ...)`
- `plot_budget_contact_usage_heatmap(traces_by_budget, ...)`
- `plot_budget_gateway_usage_heatmap(traces_by_budget, ...)`
- `plot_budget_network_crossing_heatmap(traces_by_budget, ...)`

Ejemplo:

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

### Modelo 2

Archivo: `model2_min_keys.py`

- `plot_selected_keys_vs_connectivity(df, normalize_y=True, ...)`
- `plot_connectivity_pair_coverage_heatmap(traces_by_connectivity, all_pairs=..., ...)`
- `plot_connectivity_key_scope_heatmap(traces_by_connectivity, ...)`
- `plot_connectivity_contact_usage_heatmap(traces_by_connectivity, ...)`
- `plot_connectivity_network_crossing_heatmap(traces_by_connectivity, ...)`

Ejemplo:

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

Nota:

- por defecto este plot muestra la cantidad minima de llaves en porcentaje
- si queres valores absolutos, usa `plot_selected_keys_vs_connectivity(df_m2, normalize_y=False)`

### Modelo 3

Archivo: `model3_min_keys_full_connectivity.py`

- `plot_selected_keys_by_model(df, normalize=True, ...)`
- `plot_selected_routes_by_model(df, normalize=False, ...)`
- `plot_full_connectivity_key_reuse(trace, metric="route_count", ...)`
- `plot_full_connectivity_gateway_usage(trace, metric="route_count", ...)`
- `plot_full_connectivity_network_crossings(trace, metric="crossing_count", ...)`

Ejemplo:

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

Nota:

- por defecto `plot_selected_keys_by_model(...)` muestra porcentaje de llaves
- si queres valores absolutos, usa `plot_selected_keys_by_model(df_m3, normalize=False)`

## Patron recomendado para notebooks

1. Correr `SimulationPipeline`
2. Resolver los modelos con `solve_for_security_model(...)`
3. Guardar `df_m1`, `df_m2`, `df_m3`
4. Guardar `traces_m1`, `traces_m2`, `traces_m3`
5. Usar wrappers especificos del modelo para los plots mas comunes
6. Usar `plot_utils.py` cuando haga falta componer visualizaciones nuevas

## Cuando usar `plot_utils.py` directo

Usalo directo cuando quieras:

- comparar diferentes escenarios con el mismo tipo de heatmap
- construir un plot no previsto en los wrappers
- transformar traces a `DataFrame` antes de exportar o analizar en pandas

Ejemplo:

```python
from models.plot_utils import build_contact_usage_data

contact_df = build_contact_usage_data(
    traces_m1["EDGE_TO_EDGE"],
    sweep_label="max_keys",
)
```

## Nota sobre `None` en traces

En `model1` y `model2` puede haber puntos del sweep sin solucion. En ese caso:

- la fila existe en `df`
- la posicion correspondiente en `traces` vale `None`

Los plotters comunes ignoran esos puntos automaticamente cuando trabajan desde `traces`.
