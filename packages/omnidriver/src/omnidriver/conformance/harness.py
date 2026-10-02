"""What the conformance checks and a solver's native tests share: a supplied
tree, supplied commands, and a record's sweep and run through the CLI.
Nothing is discovered. A missing tree or command raises
:class:`NativeEnvironmentError` naming the fix, an assertion failure, so a
native test that cannot see its environment fails instead of skipping."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.models import DataArtifact, data_artifact_from_json
from omnidriver.core.runtime.postprocess_phase import build_sweep_context
from omnidriver.core.runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from omnidriver.core.strict_planning import strict_plan

SWEEP_TIMEOUT_S = 1800.0


class NativeEnvironmentError(AssertionError):
    """A native test's supplied environment is missing."""


def supplied_tree(variable: str, *, contains: str | None = None) -> Path:
    """The directory ``variable`` names; ``contains`` is a path that must exist under it."""
    value = os.environ.get(variable)
    if not value:
        raise NativeEnvironmentError(
            f"{variable} is not set: a native test needs its tree supplied explicitly, "
            f"never discovered (`omnidriver env --plugin <plugin>` lists what to supply)"
        )
    root = Path(value)
    if not root.is_dir():
        raise NativeEnvironmentError(f"{variable}={value!r} is not a directory")
    if contains is not None and not (root / contains).exists():
        raise NativeEnvironmentError(f"{variable}={value!r} has no {contains}")
    return root


def require_commands(*names: str) -> None:
    """Every command is on PATH, as the solver's own shell leaves it."""
    missing = [name for name in names if shutil.which(name) is None]
    if missing:
        raise NativeEnvironmentError(
            f"not on PATH: {missing}; run from the solver's own shell (`omnidriver env --plugin <plugin>`)"
        )


def sweep_run(
    plugin: str, spec: Mapping[str, Any], *, work: Path, scratch_dir: Path,
    inputs: Mapping[str, str] | None = None, case_timeout_s: float | None = None,
    env: Mapping[str, str] | None = None, timeout_s: float = SWEEP_TIMEOUT_S,
) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
    """``omnidriver sweep-run`` of ``spec`` into ``work/out``, and its JSON payload (``None`` when it printed none)."""
    work.mkdir(parents=True, exist_ok=True)
    spec_path = work / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    argv = [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", plugin, "--spec", str(spec_path),
            "--output-dir", str(work / "out"), "--scratch-dir", str(scratch_dir)]
    if case_timeout_s is not None:
        argv += ["--case-timeout-s", str(case_timeout_s)]
    for name, path in (inputs or {}).items():
        argv += ["--input", f"{name}={path}"]
    proc = subprocess.run(argv, capture_output=True, text=True, env=None if env is None else dict(env), timeout=timeout_s)
    try:
        return proc, json.loads(proc.stdout)
    except ValueError:
        return proc, None


def sweep_spec(
    record: str, cases_root: Path, base: Mapping[str, Any], sweep: Mapping[str, Sequence[Any]],
) -> dict[str, Any]:
    return {
        "base": {"entry": record, "cases_root": str(cases_root), **base},
        "sweep": {"mode": "cross_product", "independent": {name: list(values) for name, values in sweep.items()}},
    }


def only_missing(case: Mapping[str, Any], predicted_paths: Sequence[str]) -> bool:
    """Whether ``case`` failed solely because artifacts at ``predicted_paths``
    are missing after the solver exited: not a refused patch, a plan error or
    a timeout."""
    if case.get("status") != "failed" or any(case.get(k) for k in ("materialization_error", "plan_error", "timeout_error")):
        return False
    reconciliation = case.get("artifact_reconciliation")
    if not reconciliation or reconciliation.get("missing_count", 0) <= 0:
        return False
    missing = [a for a in reconciliation.get("artifacts", ()) if a.get("status") == "missing"]
    return bool(missing) and all(a.get("predicted_path") in predicted_paths for a in missing)


def record_sweep(
    work: Path, *, plugin: str, record: str, cases_root: Path, sweep: Mapping[str, Sequence[Any]],
    study: Mapping[str, Any] | None = None, inputs: Mapping[str, str] | None = None,
    tolerate_missing: Sequence[str] = (), timeout_s: float = SWEEP_TIMEOUT_S,
) -> Path:
    """Sweep ``record`` over ``sweep`` and return the output directory. Every
    case must complete; one that failed only for want of an artifact at
    ``tolerate_missing`` is the sole exception."""
    proc, payload = sweep_run(
        plugin, sweep_spec(record, cases_root, study or {}, sweep), work=work, scratch_dir=work / "scratch",
        inputs=inputs, timeout_s=timeout_s,
    )
    tail = f"(rc={proc.returncode}): {proc.stdout[-2000:]} {proc.stderr[-2000:]}"
    if payload is None:
        raise AssertionError(f"sweep-run printed no JSON {tail}")
    if not payload.get("cases"):
        raise AssertionError(f"sweep-run produced no cases {tail}")
    for case in payload["cases"]:
        if case.get("status") != "completed" and not only_missing(case, tolerate_missing):
            raise AssertionError(f"sweep-run failed {tail}")
    return work / "out"


@dataclass(frozen=True)
class RecordRun:
    output_dir: Path
    case_id: str
    case_root: Path
    document: Mapping[str, Any]

    def artifact(self, artifact_format: str) -> DataArtifact:
        """The run document's expected artifact of ``artifact_format``."""
        (raw,) = [a for a in self.document["expectedArtifacts"] if a["format"] == artifact_format]
        return data_artifact_from_json(raw)


def record_run(work: Path, **sweep_arguments: Any) -> RecordRun:
    """:func:`record_sweep` of one case."""
    output = record_sweep(work, **sweep_arguments)
    (case,) = build_sweep_context(output).cases
    return RecordRun(output, case.case_id, Path(case.case_root), json.loads((output / case.run_document_path).read_text()))


def record_step(
    work: Path, *, plugin: str, record: str, cases_root: Path, step: str, apply: Mapping[str, Any],
    before: Sequence[str] = (), study: Mapping[str, Any] | None = None, inputs: Mapping[str, str] | None = None,
    timeout_s: float = SWEEP_TIMEOUT_S,
) -> tuple[Path, dict[str, Any]]:
    """Plan ``record`` under ``work/scratch``, run the steps in ``before``, then run ``step`` after
    ``omnidriver step --apply`` of ``apply``. Returns the staged case root and that step's JSON; a step in
    ``before`` that does not complete raises."""
    report = strict_plan(
        record, overrides={"cases_root": str(cases_root), **(study or {})}, scratch_root=work / "scratch",
        inputs=inputs, driver_context=load_plugin_context(plugin),
    )
    if report.status != "ok":
        raise AssertionError(f"plan of {record} is {report.status}: {json.dumps(report.to_json())[:2000]}")
    document = Path(report.launch["output_dir"]) / RUN_DOCUMENT_FILENAME
    patches = work / "apply.json"
    patches.write_text(json.dumps(apply))

    def run_step(name: str, *extra: str) -> tuple[subprocess.CompletedProcess, dict[str, Any]]:
        proc = subprocess.run(
            [sys.executable, "-m", "omnidriver", "step", "--plugin", plugin, "--run-document", str(document),
             "--step", name, *extra],
            capture_output=True, text=True, timeout=timeout_s,
        )
        try:
            return proc, json.loads(proc.stdout)
        except ValueError:
            raise AssertionError(f"step {name} printed no JSON (rc={proc.returncode}): {proc.stderr[-2000:]}") from None

    for name in before:
        proc, payload = run_step(name)
        if payload.get("status") != "ok":
            raise AssertionError(f"step {name} did not complete (rc={proc.returncode}): {json.dumps(payload)[:2000]}")
    return Path(report.launch["case_root"]), run_step(step, "--apply", str(patches))[1]
