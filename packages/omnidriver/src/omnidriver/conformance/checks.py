"""C1-C10. Each check is self-contained: it builds its own context, stages
its own copy, and returns a verdict naming what it saw. No check skips; a
check that cannot run is a failure saying why."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.record_execution import commit_record_case
from omnidriver.core.runtime.run_command import omnidriver_run_command
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError

from .target import CheckVerdict, ConformanceTarget

_PLAN_DIAGNOSTIC_GROUPS = (
    "validation_diagnostics", "workflow_diagnostics", "catalog_coverage_errors",
    "artifact_diagnostics", "mesh_geometry_diagnostics", "configuration_diagnostics",
)

_SCRATCH_VARIABLE = "OMNIDRIVER_SCRATCH_DIR"


def _verdict(check_id: str, passed: bool, detail: str) -> CheckVerdict:
    return CheckVerdict(check_id=check_id, passed=passed, detail=detail)


def _context(target: ConformanceTarget):
    return load_plugin_context(target.plugin)


def _record(ctx, name: str):
    records = ctx.capabilities.tutorial_records.catalog() or {}
    if name not in records:
        raise LookupError(f"{name!r} is not a tutorial record of this stack; it has {sorted(records)}")
    return records[name]


@contextlib.contextmanager
def _scratch_environment(target: ConformanceTarget) -> Iterator[None]:
    """Point core's scratch space at the target's scratch_root for an
    in-process call. Without it, planning a record writes
    ``<cases_root>/.omnidriver`` -- inside the caller's native tree."""
    previous = os.environ.get(_SCRATCH_VARIABLE)
    os.environ[_SCRATCH_VARIABLE] = str(target.scratch_root)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(_SCRATCH_VARIABLE, None)
        else:
            os.environ[_SCRATCH_VARIABLE] = previous


def check_load(target: ConformanceTarget) -> CheckVerdict:
    """C1: the stack is its root plus exactly what the root requires.

    A provider no one requires (for example an OpenFOAM environment layer a
    non-FOAM solver never asked for) means the stack depends on something
    it does not declare."""
    try:
        ctx = _context(target)
    except Exception as exc:  # the verdict names every load failure
        return _verdict("C1", False, f"stack did not load: {type(exc).__name__}: {exc}")
    ids = [provider.plugin_id for provider in ctx.providers]
    required = {rid for provider in ctx.providers for rid in provider.get_profile().requires}
    roots = [pid for pid in ids if pid not in required]
    if len(roots) != 1:
        return _verdict("C1", False, f"stack {ids} has {len(roots)} unrequired providers {roots}; expected exactly one root")
    return _verdict("C1", True, f"stack {ids}, root {roots[0]}")


def check_describe_noop(target: ConformanceTarget) -> CheckVerdict:
    """C2: with no study values, describe proposes no change to the native case."""
    ctx = _context(target)
    with _scratch_environment(target):
        payload = describe_entry(
            target.record, overrides={"cases_root": str(target.cases_root)}, driver_context=ctx,
        )
    preview = payload.get("record_preview")
    if preview is None:
        return _verdict("C2", False, f"{target.record!r} did not resolve as a tutorial record (resolution={payload.get('resolution')!r})")
    changed = [p for p in preview["patches"] if p["status"] != "unchanged"]
    if changed:
        return _verdict("C2", False, f"describe proposes {len(changed)} change(s) to the untouched native case: {changed}")
    return _verdict("C2", True, "no changes proposed")


def check_refuses_unknown(target: ConformanceTarget) -> CheckVerdict:
    """C3: an unknown study name is refused, by that name, before anything runs."""
    ctx = _context(target)
    overrides = {"cases_root": str(target.cases_root), target.unknown_name: 1}
    try:
        with _scratch_environment(target):
            describe_entry(target.record, overrides=overrides, driver_context=ctx)
    except (TutorialRecordError, KeyError, ValueError) as exc:
        named = target.unknown_name in str(exc)
        return _verdict("C3", named, f"refused: {exc}" if named else f"refused without naming {target.unknown_name!r}: {exc}")
    return _verdict("C3", False, f"{target.unknown_name!r} was accepted")


def _stage(target: ConformanceTarget, record, label: str) -> Path:
    """A fresh copy of the record's native case under scratch_root."""
    staged = target.scratch_root / "conformance" / label / record.name
    if staged.exists():
        shutil.rmtree(staged)
    shutil.copytree(target.cases_root / record.native_case_relpath, staged)
    return staged


def _split_study_key(name: str) -> tuple[str, tuple[str, ...]]:
    document, separator, dotted = name.partition(":")
    if not separator or not dotted:
        raise ValueError(f"{name!r} is not a document:key study name")
    return document, tuple(dotted.split("."))


def check_patch_preserves(target: ConformanceTarget) -> CheckVerdict:
    """C4: a one-key patch changes that key and leaves ``untouched`` as it was."""
    ctx = _context(target)
    record = _record(ctx, target.record)
    staged = _stage(target, record, "C4")
    reader = ctx.capabilities.config_value.reader()
    comparator = ctx.capabilities.case_value_comparison.comparator()
    validator = ctx.capabilities.record_key_validation.validator()
    if reader is None or comparator is None or validator is None:
        return _verdict("C4", False, "the stack lacks a config reader, comparator or key validator")
    untouched_doc, untouched_key = target.untouched
    before = reader(staged / untouched_doc, untouched_key)
    if before is None:
        return _verdict("C4", False, f"target misconfigured: {untouched_doc}:{'.'.join(untouched_key)} is absent from the native case")
    patch_name, patch_value = target.patch
    patch_doc, patch_key = _split_study_key(patch_name)
    value_kind, _validated = validator(patch_doc, patch_key, patch_value)
    if comparator(value_kind, patch_value, reader(staged / patch_doc, patch_key)):
        return _verdict("C4", False, f"target misconfigured: the native case already holds {patch_name} = {patch_value!r}")
    with _scratch_environment(target):
        commit_record_case(
            record, cases_root=target.cases_root, staged_case_root=staged,
            study_by_source={"base": {patch_name: patch_value}}, driver_context=ctx,
        )
    after_patched = reader(staged / patch_doc, patch_key)
    after_untouched = reader(staged / untouched_doc, untouched_key)
    problems = []
    if not comparator(value_kind, patch_value, after_patched):
        problems.append(f"{patch_name} reads {after_patched!r} after patching it to {patch_value!r}")
    if after_untouched != before:
        problems.append(f"{untouched_doc}:{'.'.join(untouched_key)} changed from {before!r} to {after_untouched!r}")
    return _verdict("C4", not problems, "; ".join(problems) or "patched one key; its sibling is unchanged")


def _plan(target: ConformanceTarget, ctx):
    with _scratch_environment(target):
        return strict_plan(
            target.record,
            overrides={"cases_root": str(target.cases_root), **dict(target.base_study)},
            driver_context=ctx,
        )


def _plan_errors(report) -> list[str]:
    payload = report.to_json()
    return [
        f"{d.get('code')}: {d.get('message')}"
        for group in _PLAN_DIAGNOSTIC_GROUPS
        for d in payload.get(group, ()) or ()
        if d.get("level") == "error"
    ]


def _child_env(target: ConformanceTarget) -> dict[str, str]:
    env = dict(os.environ)
    env.update(target.environment)
    env[_SCRATCH_VARIABLE] = str(target.scratch_root)
    return env


def _run_document_path(report) -> Path:
    return Path(report.launch["output_dir"]) / "run_document.json"


def check_strict_plan(target: ConformanceTarget) -> CheckVerdict:
    """C5: plan --strict on the record has no errors, and its launch command is runnable as written."""
    report = _plan(target, _context(target))
    errors = _plan_errors(report)
    command = list(report.launch.get("command") or ())
    problems = list(errors)
    if report.status != "ok":
        problems.append(f"plan status {report.status!r}")
    if "--run-document" not in command:
        problems.append(f"launch command {command} does not run the planned document")
    elif not _run_document_path(report).is_file():
        problems.append(f"launch names {_run_document_path(report)}, which was not written")
    return _verdict("C5", not problems, "; ".join(problems) or f"ok; launch {command}")


def _execute(target: ConformanceTarget, ctx, report) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
    # Never hand-build a run command (main, 2026-09-25): the canonical builder
    # carries --plugin from ctx.plugin_selector, set by load_plugin_context.
    proc = subprocess.run(
        omnidriver_run_command(ctx, "--run-document", str(_run_document_path(report))),
        capture_output=True, text=True, env=_child_env(target),
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        payload = None
    return proc, payload


def check_run(target: ConformanceTarget) -> CheckVerdict:
    """C6: the planned document runs, and every artifact the record declares is present."""
    ctx = _context(target)
    report = _plan(target, ctx)
    if report.status != "ok":
        return _verdict("C6", False, f"cannot run: plan failed: {_plan_errors(report)}")
    proc, payload = _execute(target, ctx, report)
    if payload is None:
        return _verdict("C6", False, f"run printed no JSON (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
    reconciliation = payload.get("artifact_reconciliation") or {}
    artifacts = reconciliation.get("artifacts", ())
    declared = [a for a in artifacts if a["artifact_id"].startswith("record.")]
    missing = [a["artifact_id"] for a in artifacts if a["status"] == "missing" and not a.get("optional")]
    problems = []
    if proc.returncode != 0 or payload.get("status") != "ok":
        problems.append(f"run status {payload.get('status')!r}, rc={proc.returncode}")
    if not declared:
        problems.append("the record declares no artifacts (no step `produces`), so a run proves nothing about outputs")
    if missing:
        problems.append(f"missing artifacts {missing}")
    return _verdict("C6", not problems, "; ".join(problems) or f"{len(declared)} declared artifact(s) present")


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def check_sweep(target: ConformanceTarget) -> CheckVerdict:
    """C7: a two-point sweep stages, runs and reconciles both cases, and
    leaves the native case byte-identical."""
    ctx = _context(target)
    record = _record(ctx, target.record)
    native = target.cases_root / record.native_case_relpath
    before = _tree_digest(native)
    work = target.scratch_root / "conformance" / "C7"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    base = {k: v for k, v in target.base_study.items() if k != target.sweep_name}
    spec = {
        "base": {"entry": target.record, "cases_root": str(target.cases_root), **base},
        "sweep": {"mode": "cross_product", "independent": {target.sweep_name: list(target.sweep_values)}},
    }
    spec_path = work / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    proc = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", target.plugin,
         "--spec", str(spec_path), "--output-dir", str(work / "out")],
        capture_output=True, text=True, env=_child_env(target),
    )
    try:
        payload = json.loads(proc.stdout)
    except ValueError:
        return _verdict("C7", False, f"sweep printed no JSON (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
    problems = []
    if payload.get("completed_count") != 2 or payload.get("failed_count"):
        problems.append(f"completed {payload.get('completed_count')}, failed {payload.get('failed_count')}")
    for case in payload.get("cases", ()):
        rec = case.get("artifact_reconciliation")
        if rec is None:
            problems.append(f"case {case.get('case_id')} has no artifact reconciliation")
        elif rec.get("missing_count"):
            problems.append(f"case {case.get('case_id')} is missing {rec.get('missing_count')} artifact(s)")
    if _tree_digest(native) != before:
        problems.append(f"the native case {native} changed")
    return _verdict("C7", not problems, "; ".join(problems) or "2 cases completed and reconciled; native tree unchanged")


CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]] = {
    "C1": check_load,
    "C2": check_describe_noop,
    "C3": check_refuses_unknown,
    "C4": check_patch_preserves,
    "C5": check_strict_plan,
    "C6": check_run,
    "C7": check_sweep,
}


def run_check(check_id: str, target: ConformanceTarget) -> CheckVerdict:
    if check_id not in CHECKS:
        raise KeyError(f"no conformance check {check_id!r}; known: {sorted(CHECKS)}")
    return CHECKS[check_id](target)
