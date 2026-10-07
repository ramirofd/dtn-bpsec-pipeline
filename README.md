# BPSec Keys

Tools for studying CGR routes, BPSec protection policies, and key allocation in
DTN networks.

## Install

Use Python 3.11 or later:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-notebooks.txt
```

This installs the runtime, optimization, plotting, and notebook execution
dependencies. Optimization requires an accessible Gurobi license. Select the
same Python environment in your notebook editor. For routing and security
planning alone, `requirements.txt` provides the core dependencies.

## Use the pipeline

Start with [Using the BPSec pipeline](docs/pipeline_usage.ipynb), the executable
usage guide. It covers scenario loading, routing, security policies, catalog
navigation, reusable stages, the five optimization models, plots, and custom
constraints.

The scenario notebooks provide larger worked examples:

- [Basic](scenarios/basic/resultados.ipynb): routes, key inventories, and initial
  optimization experiments.
- [Four Planes](scenarios/wisee_four_planes_polar/four_planes.ipynb): connectivity
  sweeps, key share, operation density, exposure, and tradeoff plots.

Repository documentation is maintained in English.

## Validate

Run the tests and execute the usage guide and both scenario notebooks in fresh
kernels:

```bash
python -m unittest discover -s tests -v
python scripts/validate_notebooks.py --output-dir /tmp/bpsec-notebooks
```

The validator exports executed notebooks, result tables, and displayed figures.
Use `--notebook docs/pipeline_usage.ipynb` to run only the guide, `--write` to
refresh saved notebook outputs, and `--compare-dir` to compare tables with a
previous export. Comparisons exclude `runtime_seconds` and report any changes
in results, including different selections among equally optimal solutions.
