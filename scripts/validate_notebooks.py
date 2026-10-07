"""Execute the pipeline guide and scenario notebooks in clean kernels.

Run with the project Python environment (including nbclient and ipykernel):
    python scripts/validate_notebooks.py --output-dir /tmp/bpsec-notebooks

An optional --compare-dir compares exported tables with an earlier execution.
Selected routes can differ between equally optimal solutions; differences are
reported explicitly, never silently accepted as equivalent.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from time import perf_counter
from pathlib import Path

import nbformat
import pandas as pd
from jupyter_client import KernelManager
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = (
    Path("docs/pipeline_usage.ipynb"),
    Path("scenarios/basic/resultados.ipynb"),
    Path("scenarios/wisee_four_planes_polar/four_planes.ipynb"),
)


def execute(path: Path, output: Path, *, write: bool) -> None:
    """Run every cell without pre-existing state; keep instrumentation external."""
    notebook = nbformat.read(path, as_version=4)
    original_count = len(notebook.cells)
    output.mkdir(parents=True, exist_ok=True)
    notebook.cells.append(nbformat.v4.new_code_cell(
        "from pathlib import Path as _Path\n"
        "import pandas as _pd\n"
        f"_validation_output = _Path({str(output)!r})\n"
        "for _name, _value in list(globals().items()):\n"
        "    if isinstance(_value, _pd.DataFrame) and not _name.startswith('_'):\n"
        "        _value.to_json(_validation_output / f'{_name}.json', "
        "orient='table', index=False, default_handler=str)\n"
    ))
    manager = KernelManager(kernel_name="python3")
    manager.kernel_spec.argv = [
        sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}",
    ]

    def progress(cell, cell_index, **kwargs):
        if cell.cell_type == "code" and cell_index < original_count:
            print(f"{path.name}: cell {cell_index + 1}/{original_count}", flush=True)

    client = NotebookClient(
        notebook,
        timeout=3600,
        km=manager,
        resources={"metadata": {"path": str(path.parent)}},
        on_cell_start=progress,
    )
    try:
        client.execute()
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
        nbformat.write(notebook, output / "executed.ipynb")
        for index, cell in enumerate(notebook.cells[:original_count]):
            for output_index, item in enumerate(cell.get("outputs", ())):
                for mime, extension in (("image/png", "png"), ("image/svg+xml", "svg")):
                    image = item.get("data", {}).get(mime)
                    if image:
                        destination = output / f"cell-{index:02d}-output-{output_index:02d}.{extension}"
                        if extension == "png":
                            destination.write_bytes(base64.b64decode(image))
                        else:
                            destination.write_text(image)
    if write:
        notebook.cells = notebook.cells[:original_count]
        nbformat.write(notebook, path)
        checkpoint = path.parent / ".ipynb_checkpoints" / f"{path.stem}-checkpoint.ipynb"
        if checkpoint.exists():
            nbformat.write(notebook, checkpoint)


def compare(current: Path, reference: Path) -> dict[str, str]:
    """Compare reference results in stable domain order, excluding elapsed time."""
    if not reference.is_dir() or not any(reference.glob("*.json")):
        raise FileNotFoundError(f"No reference result tables found in {reference}")
    report = {}
    for reference_file in sorted(reference.glob("*.json")):
        if reference_file.name == "comparison-report.json":
            continue
        current_file = current / reference_file.name
        if not current_file.exists():
            report[reference_file.name] = "Missing current table"
            continue
        before = pd.read_json(reference_file, orient="table").drop(columns=["runtime_seconds"], errors="ignore")
        after = pd.read_json(current_file, orient="table")
        missing = before.columns.difference(after.columns).tolist()
        if missing:
            report[reference_file.name] = f"Missing columns: {missing}"
            continue
        after = after[before.columns]
        order = [column for column in (
            "model", "Model", "target_connectivity_pct", "max_keys", "pair",
            "route", "key_type", "Scope", "mode",
        ) if column in before]
        for frame in (before, after):
            for column in frame:
                if isinstance(frame[column].dtype, pd.CategoricalDtype):
                    frame[column] = frame[column].astype(str)
            if order:
                frame.sort_values(order, kind="stable", inplace=True)
            frame.reset_index(drop=True, inplace=True)
        try:
            pd.testing.assert_frame_equal(before, after, check_dtype=False, atol=1e-10, rtol=1e-10)
            report[reference_file.name] = "equal"
        except AssertionError as error:
            report[reference_file.name] = str(error)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, action="append", help="Repository-relative path; default: pipeline guide and both scenario notebooks")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compare-dir", type=Path)
    parser.add_argument("--write", action="store_true", help="Save executed outputs into notebooks and existing checkpoints")
    arguments = parser.parse_args()
    differences = False
    timing_path = arguments.output_dir / "execution-times.json"
    execution_times = json.loads(timing_path.read_text()) if timing_path.exists() else {}
    for relative in arguments.notebook or NOTEBOOKS:
        path = (ROOT / relative).resolve()
        output = (arguments.output_dir / path.stem).resolve()
        started = perf_counter()
        execute(path, output, write=arguments.write)
        elapsed = round(perf_counter() - started, 3)
        execution_times[str(relative)] = elapsed
        print(f"Completed {path.name} in {elapsed:.3f} seconds", flush=True)
        if arguments.compare_dir:
            report = compare(output, arguments.compare_dir / path.stem)
            (output / "comparison-report.json").write_text(json.dumps(report, indent=2))
            differences |= any(value != "equal" for value in report.values())
            print(json.dumps(report, indent=2))
    timing_path.write_text(json.dumps(execution_times, indent=2))
    return int(differences)


if __name__ == "__main__":
    raise SystemExit(main())
