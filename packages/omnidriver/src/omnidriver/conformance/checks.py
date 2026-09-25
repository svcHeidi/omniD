"""C1-C10. Each check is self-contained: it builds its own context, stages
its own copy, and returns a verdict naming what it saw. No check skips; a
check that cannot run is a failure saying why.

Checks are not thread-parallel within one process; run targets in separate
processes. In-process planning reads core's scratch root from the process
environment (``_scratch_environment``), so every check that plans in
process holds one module-level lock for as long as it overrides it (fix
round 1 I2, 2026-09-25)."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
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


#: Held for the whole of every ``_scratch_environment``: the override is
#: process-global, so two threads interleaving it would plan one target
#: with no override (writing ``<cases_root>/.omnidriver``) and leave the
#: variable pointing at the other's scratch. Reentrant so nesting works.
_SCRATCH_LOCK = threading.RLock()


@contextlib.contextmanager
def _scratch_environment(target: ConformanceTarget) -> Iterator[None]:
    """Point core's scratch space at the target's scratch_root for an
    in-process call. Without it, planning a record writes
    ``<cases_root>/.omnidriver`` -- inside the caller's native tree.

    Checks are not thread-parallel within one process; run targets in
    separate processes. ``_SCRATCH_LOCK`` serialises concurrent callers
    rather than letting them corrupt each other's environment."""
    with _SCRATCH_LOCK:
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
    it does not declare. The loaded stack must also serve the target's
    record: a stack that loads but lacks the record is not the stack the
    target names (added 2026-09-25, fix round 1 I3)."""
    ctx = _context(target)
    ids = [provider.plugin_id for provider in ctx.providers]
    required = {rid for provider in ctx.providers for rid in provider.get_profile().requires}
    roots = [pid for pid in ids if pid not in required]
    if len(roots) != 1:
        return _verdict("C1", False, f"stack {ids} has {len(roots)} unrequired providers {roots}; expected exactly one root")
    _record(ctx, target.record)
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


def _names(message: str, name: str) -> bool:
    """Whether ``message`` names ``name`` as a whole token, not merely
    contains it (fix round 1 M6, 2026-09-25): a short unknown name such as
    ``"x"`` is a substring of almost any message. Quoted (``'n'``, ``"n"``,
    `` `n` ``) always counts; otherwise ``name`` must not continue into a
    longer identifier or ``document:dotted.path`` on either side. A
    sentence-ending ``.`` does not continue a token; ``.inner`` does."""
    if any(f"{q}{name}{q}" in message for q in ("'", '"', "`")):
        return True
    token = rf"(?<![\w.:/\-]){re.escape(name)}(?![\w:/\-]|\.\w)"
    return re.search(token, message) is not None


def check_refuses_unknown(target: ConformanceTarget) -> CheckVerdict:
    """C3: an unknown study name is refused, by that name, before anything runs."""
    ctx = _context(target)
    overrides = {"cases_root": str(target.cases_root), target.unknown_name: 1}
    try:
        with _scratch_environment(target):
            describe_entry(target.record, overrides=overrides, driver_context=ctx)
    except (TutorialRecordError, KeyError, ValueError) as exc:
        named = _names(str(exc), target.unknown_name)
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


def _missing_required(reconciliation: Mapping[str, Any]) -> list[str]:
    """Ids of the non-optional artifacts a reconciliation found missing. One
    rule for C6 and C7: an absent optional artifact fails neither (fix round
    1 M3, 2026-09-25; C7 used to count ``missing_count``, optional included)."""
    return [
        a["artifact_id"] for a in reconciliation.get("artifacts", ())
        if a["status"] == "missing" and not a.get("optional")
    ]


def _execute(target: ConformanceTarget, ctx, report) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
    # Never hand-build a run command (main, 2026-09-25): the canonical builder
    # carries --plugin from ctx.plugin_selector, set by load_plugin_context.
    proc = subprocess.run(
        omnidriver_run_command(ctx, "--run-document", str(_run_document_path(report))),
        capture_output=True, text=True, env=_child_env(target), timeout=target.timeout_s,
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
    try:
        proc, payload = _execute(target, ctx, report)
    except subprocess.TimeoutExpired:
        return _verdict("C6", False, f"run timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if payload is None:
        return _verdict("C6", False, f"run printed no JSON (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
    reconciliation = payload.get("artifact_reconciliation") or {}
    artifacts = reconciliation.get("artifacts", ())
    declared = [a for a in artifacts if a["artifact_id"].startswith("record.")]
    missing = _missing_required(reconciliation)
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
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", target.plugin,
             "--spec", str(spec_path), "--output-dir", str(work / "out"),
             "--case-timeout-s", str(target.timeout_s)],
            capture_output=True, text=True, env=_child_env(target), timeout=target.timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _verdict("C7", False, f"sweep timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
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
        elif missing := _missing_required(rec):
            problems.append(f"case {case.get('case_id')} is missing artifacts {missing}")
    if _tree_digest(native) != before:
        problems.append(f"the native case {native} changed")
    return _verdict("C7", not problems, "; ".join(problems) or "2 cases completed and reconciled; native tree unchanged")


#: Component kinds that fingerprint a file the case reads: an ordinary case
#: file, or a symlink out of the case (fingerprinted through its target).
_FILE_KINDS = frozenset({"case_file", "external_link"})


def _posix(path: str) -> str:
    return PurePosixPath(path).as_posix()


def check_provenance(target: ConformanceTarget) -> CheckVerdict:
    """C8: every file a planned step consumes is fingerprinted.

    Listed is not fingerprinted: ``enumerate_case_inputs`` adds every
    consumed path unconditionally, and a missing one becomes a component
    with strength ``unavailable`` (fix round 1 I1, 2026-09-25). Only a
    component carrying a real fingerprint counts."""
    ctx = _context(target)
    report = _plan(target, ctx)
    if report.status != "ok" or report.workflow_dag is None:
        return _verdict("C8", False, f"cannot check: plan failed: {_plan_errors(report)}")
    consumed = sorted({_posix(str(e)) for s in report.workflow_dag.get("steps", ()) for e in s.get("consumes", ()) or ()})
    if not consumed:
        return _verdict("C8", False, "no step declares `consumes`, so provenance cannot be shown to cover the record's inputs")
    case_root = Path(report.launch["case_root"])
    components = enumerate_case_inputs(case_root, workflow_dag=report.workflow_dag, driver_context=ctx, env=_child_env(target))
    fingerprinted = {
        _posix(c.path) for c in components
        if c.kind in _FILE_KINDS and c.strength != "unavailable"
    }
    missing = [p for p in consumed if p not in fingerprinted]
    return _verdict("C8", not missing, f"consumed but not fingerprinted: {missing}" if missing else f"{len(consumed)} consumed file(s) fingerprinted")


def _levels(diagnostics) -> list[tuple[str, str]]:
    out = []
    for d in diagnostics:
        level = getattr(d, "level", None) or (d.get("level") if isinstance(d, dict) else None)
        message = getattr(d, "message", None) or (d.get("message") if isinstance(d, dict) else str(d))
        out.append((level, message))
    return out


def check_environment(target: ConformanceTarget) -> CheckVerdict:
    """C9: preflight is clean in the supplied environment, and names the
    solver when the solver cannot be found."""
    ctx = _context(target)
    report = _plan(target, ctx)
    if report.workflow_dag is None:
        return _verdict("C9", False, f"cannot check: plan failed: {_plan_errors(report)}")
    preflight = ctx.capabilities.environment_preflight
    env = _child_env(target)
    clean = [m for level, m in _levels(preflight.diagnostics(report.workflow_dag, env=env, driver_context=ctx)) if level == "error"]
    empty = target.scratch_root / "conformance" / "C9-empty-path"
    empty.mkdir(parents=True, exist_ok=True)
    broken = [m for level, m in _levels(preflight.diagnostics(report.workflow_dag, env={**env, "PATH": str(empty)}, driver_context=ctx)) if level == "error"]
    problems = []
    if clean:
        problems.append(f"errors in the supplied environment: {clean}")
    if not any(target.solver_command in m for m in broken):
        problems.append(f"with {target.solver_command!r} off PATH, preflight said {broken or 'nothing'}")
    return _verdict("C9", not problems, "; ".join(problems) or "clean; names the missing solver")


CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]] = {
    "C1": check_load,
    "C2": check_describe_noop,
    "C3": check_refuses_unknown,
    "C4": check_patch_preserves,
    "C5": check_strict_plan,
    "C6": check_run,
    "C7": check_sweep,
    "C8": check_provenance,
    "C9": check_environment,
}


_StatEntry = tuple[bool, int, int]


def _tree_stat(root: Path) -> dict[str, _StatEntry]:
    """``relpath -> (is_dir, size, mtime_ns)`` for every file and directory
    under ``root``, the root itself included as ``"."``. Stat, not bytes:
    a real native tutorials tree is large, and this runs around every
    check. An absent root is an empty snapshot, so its creation shows."""
    if not root.exists():
        return {}
    snapshot: dict[str, _StatEntry] = {}
    for path in (root, *root.rglob("*")):
        info = path.lstat()
        snapshot[path.relative_to(root).as_posix()] = (path.is_dir() and not path.is_symlink(), info.st_size, info.st_mtime_ns)
    return snapshot


def _tree_changes(before: dict[str, _StatEntry], after: dict[str, _StatEntry]) -> list[str]:
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def _guarded(verdict: CheckVerdict, changed: list[str], cases_root: Path) -> CheckVerdict:
    if not changed:
        return verdict
    shown = changed[:20] + ([f"... {len(changed) - 20} more"] if len(changed) > 20 else [])
    guard = f"the native tree {cases_root} changed during the check: {shown}"
    if verdict.passed:
        return _verdict(verdict.check_id, False, guard)
    return _verdict(verdict.check_id, False, f"{verdict.detail}; {guard}")


def run_check(check_id: str, target: ConformanceTarget) -> CheckVerdict:
    """Run one check. An unknown ``check_id`` is the caller's error and
    raises ``KeyError``; a check that cannot run (a stack that does not
    load, a misnamed record, a plan refusal) is a failed verdict naming why,
    so a runner looping over ``CHECKS`` always gets one verdict per check.

    Every check runs inside one suite-wide native guard (fix round 1 I4,
    2026-09-25): a stat snapshot of the whole ``target.cases_root``, taken
    before and after. Any difference fails the verdict and names the
    changed paths, whatever the check itself concluded."""
    if check_id not in CHECKS:
        raise KeyError(f"no conformance check {check_id!r}; known: {sorted(CHECKS)}")
    try:
        before = _tree_stat(target.cases_root)
    except Exception as exc:  # the verdict names every failure to run
        return _verdict(check_id, False, f"could not run: cannot snapshot the native tree {target.cases_root}: {type(exc).__name__}: {exc}")
    try:
        verdict = CHECKS[check_id](target)
    except Exception as exc:  # the verdict names every failure to run
        verdict = _verdict(check_id, False, f"could not run: {type(exc).__name__}: {exc}")
    try:
        changed = _tree_changes(before, _tree_stat(target.cases_root))
    except Exception as exc:  # the verdict names every failure to run
        return _verdict(check_id, False, f"{verdict.detail}; could not re-snapshot the native tree {target.cases_root}: {type(exc).__name__}: {exc}")
    return _guarded(verdict, changed, target.cases_root)
