"""``omnidriver check``: the conformance checks C1-C14 and the native regression, reported as JSON.

It gates nothing: a solver under development that fails a check is the report doing its job."""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from omnidriver.core.environment_connection import load_environment
from omnidriver.core.runtime.process_control import run_child

from .checks import CHECKS, run_check
from .target import ConformanceTarget

if TYPE_CHECKING:
    from omnidriver.core.plugin_interface import DriverContext

REGRESSION_ROLE = "case.regression_test"
REGRESSION_TIMEOUT_S = 3600.0
#: What a native script exits with to say the case does not apply to this build.
_SKIPPED = 77


def _tail(text: str) -> str:
    return text[-1500:]


def regression_script(driver_context: "DriverContext", native_case: Path) -> Path | None:
    """The record's native regression script, where the stack's case-file
    rules put it, or ``None``."""
    for rule in driver_context.stack.call("get_profile").case_files:
        if rule.role == REGRESSION_ROLE and (native_case / rule.path).is_file():
            return native_case / rule.path
    return None


def _regression(script: Path, native_case: Path, work: Path, timeout_s: float) -> dict[str, Any]:
    """Run the native regression script in a copy under ``work``; the native case is never written."""
    case = work / native_case.name
    shutil.rmtree(case, ignore_errors=True)
    shutil.copytree(native_case, case, symlinks=True)
    started = time.monotonic()
    try:
        proc = run_child(["bash", str(case / script.relative_to(native_case))], cwd=case, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"status": "failed", "detail": f"timed out after {timeout_s}s", "case": str(case)}
    status = "skipped" if proc.returncode == _SKIPPED else "passed" if proc.returncode == 0 else "failed"
    return {
        "status": status, "script": script.relative_to(native_case).as_posix(), "exit_code": proc.returncode,
        "seconds": round(time.monotonic() - started, 1), "case": str(case), "output_tail": _tail(proc.stdout + proc.stderr),
    }


def _probe(probe: Any, env: Mapping[str, str]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        passed, detail = probe(env)
    except Exception as exc:
        passed, detail = False, f"{type(exc).__name__}: {exc}"
    return {"passed": passed, "detail": detail, "seconds": round(time.monotonic() - started, 1)}


def _target(
    driver_context: "DriverContext", plugin: str, record: Any, cases_root: Path, scratch_root: Path,
    inputs: Mapping[str, str], benchmarks: Path | None,
) -> tuple[ConformanceTarget, str | None]:
    """The record's study placed at the roots, and why its quantity could not be placed (``None`` when it could)."""
    study = {
        field.name: getattr(record.conformance, field.name) for field in dataclasses.fields(record.conformance)
    }
    problem = None
    if study["quantity"] is not None:
        try:
            study["quantity"] = study["quantity"].resolved(benchmarks)
        except (OSError, ValueError) as exc:
            study["quantity"], problem = None, str(exc)
    return ConformanceTarget(
        plugin=plugin, record=record.name, cases_root=cases_root, scratch_root=scratch_root, inputs=dict(inputs),
        repository=None if driver_context.repository is None else driver_context.repository.root, **study,
    ), problem


def check_report(
    driver_context: "DriverContext", *, plugin: str, cases_root: Path, scratch_root: Path,
    records: Sequence[str] = (), check_ids: Sequence[str] = (), inputs: Mapping[str, str] | None = None,
    benchmarks: Path | None = None, regression: bool = False,
) -> dict[str, Any]:
    """Run ``check_ids`` (all when empty) over ``records`` (every record that
    declares a study when empty) and report each verdict, in the order run.

    A check that cannot run is a failed verdict saying why; a record whose
    commands are not on ``PATH`` is reported ``not_run`` naming them, so the
    solver's shell is what to fix."""
    unknown = [check_id for check_id in check_ids if check_id not in CHECKS]
    if unknown:
        raise KeyError(f"no conformance check {unknown}; known: {sorted(CHECKS)}")
    catalog = driver_context.stack.call("get_tutorial_records")
    missing = [name for name in records if name not in catalog]
    if missing:
        raise KeyError(f"not a record of this stack: {missing}; it has {sorted(catalog)}")
    selected = [catalog[name] for name in (records or sorted(catalog))]
    ran = list(check_ids or sorted(CHECKS, key=lambda check_id: int(check_id[1:])))
    reported: list[dict[str, Any]] = []
    for record in selected:
        entry: dict[str, Any] = {"record": record.name}
        reported.append(entry)
        if record.conformance is None:
            entry["status"] = "no_study"
            continue
        absent = [command for command in record.conformance.requires if shutil.which(command) is None]
        if absent:
            entry.update(status="not_run", missing_commands=absent, hint="run from the solver's shell (omnidriver env)")
            continue
        verdicts: list[dict[str, Any]] = []
        for check_id in ran:
            target, quantity_problem = _target(
                driver_context, plugin, record, cases_root, scratch_root / record.name / check_id, inputs or {}, benchmarks,
            )
            started = time.monotonic()
            if check_id in {"C13", "C14"} and quantity_problem:
                passed, detail = False, f"could not place the quantity: {quantity_problem}"
            else:
                verdict = run_check(check_id, target)
                passed, detail = verdict.passed, verdict.detail
            verdicts.append({
                "check": check_id, "passed": passed, "detail": detail, "seconds": round(time.monotonic() - started, 1),
            })
        entry["checks"] = verdicts
        passed = all(v["passed"] for v in verdicts)
        if not check_ids and record.conformance.probes:
            env = load_environment(driver_context, None)
            entry["probes"] = {name: _probe(probe, env) for name, probe in record.conformance.probes.items()}
            passed = passed and all(item["passed"] for item in entry["probes"].values())
        entry["status"] = "passed" if passed else "failed"
        if regression:
            native_case = cases_root / record.native_case_relpath
            script = regression_script(driver_context, native_case)
            entry["regression"] = (
                _regression(script, native_case, scratch_root / record.name / "regression", REGRESSION_TIMEOUT_S)
                if script is not None else {"status": "no_script", "detail": "the native case has no regression script"}
            )
    counts = [verdict["passed"] for entry in reported for verdict in entry.get("checks", ())]
    return {
        "action": "check",
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "cases_root": str(cases_root),
        "scratch_root": str(scratch_root),
        "records": reported,
        "summary": {"checks": len(counts), "passed": sum(counts), "failed": len(counts) - sum(counts)},
        "gates": "nothing: this reports",
    }
