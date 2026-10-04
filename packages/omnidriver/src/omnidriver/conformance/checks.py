"""C1-C14. Each check is self-contained: it builds its own context, stages its own copy, and returns a verdict.

No check skips; a check that cannot run is a failure saying why."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.provider_stack import MemberAbsent, provider_profile
from omnidriver.core.experiments import inspect_sweep_experiment
from omnidriver.core.quantities import (
    Quantity, ReadRequest, ReaderDeclarationError, check_reader, convert, experiment_comparisons, read_quantities,
)
from omnidriver.core.runtime import mpi
from omnidriver.core.runtime.models import data_artifact_from_json
from omnidriver.core.runtime.process_control import run_child
from omnidriver.core.runtime.case_records import build_sweep_context
from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
from omnidriver.core.runtime.record_surface import lists_key
from omnidriver.core.runtime.record_execution import commit_record_case
from omnidriver.core.repository import read_repository
from omnidriver.core.runtime.run_command import omnidriver_run_command
from omnidriver.core.runtime.run_document_exec import RUN_DOCUMENT_FILENAME
from omnidriver.core.specs.paths import SCRATCH_ENV_VAR
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.sweep.sweep_derivation_catalog import NAMING_OUTPUT_KEYS
from omnidriver.core.tutorial_records import PLAIN_FILE_FORMAT, TutorialRecordError

from .harness import sweep_run, sweep_spec
from .target import CheckVerdict, ConformanceTarget


def _verdict(check_id: str, passed: bool, detail: str) -> CheckVerdict:
    return CheckVerdict(check_id=check_id, passed=passed, detail=detail)


def _output_tail(proc: subprocess.CompletedProcess) -> str:
    """The tail of what a child printed: its stderr, or its stdout when stderr is empty (a refusal is JSON on stdout)."""
    return (proc.stderr.strip() or proc.stdout.strip())[-800:]


def _recorded_failure(state_path: Path) -> str | None:
    """The error diagnostics the failed steps of a case's ``workflow_state.json`` recorded, or ``None``."""
    try:
        steps = json.loads(state_path.read_text()).get("steps", ())
    except (OSError, ValueError, AttributeError):
        return None
    reasons = [
        f"step {step.get('step_id')!r}: {d.get('code')}: {d.get('message')}"
        for step in steps if isinstance(step, dict) and step.get("status") == "failed"
        for d in step.get("diagnostics", ()) if isinstance(d, dict) and d.get("level") == "error"
    ]
    return "; ".join(reasons) or None


def _with_recorded_failure(problems: list[str], state_path: Path, subject: str) -> list[str]:
    reason = _recorded_failure(state_path)
    return [*problems, f"{subject} recorded: {reason}"] if reason else problems


def _context(target: ConformanceTarget):
    context = load_plugin_context(target.plugin)
    if target.repository is None:
        return context
    return dataclasses.replace(context, repository=read_repository(target.repository))


def _record(ctx, name: str):
    records = ctx.stack.call("get_tutorial_records")
    if name not in records:
        raise LookupError(f"{name!r} is not a tutorial record of this stack; it has {sorted(records)}")
    return records[name]


def check_load(target: ConformanceTarget) -> CheckVerdict:
    """C1: the stack is its root plus exactly what the root requires.

    A provider no one requires (for example an OpenFOAM environment layer a
    non-FOAM solver never asked for) means the stack depends on something
    it does not declare. The loaded stack must also serve the target's
    record: a stack that loads but lacks the record is not the stack the
    target names."""
    ctx = _context(target)
    ids = [provider.plugin_id for provider in ctx.providers]
    required = {rid for provider in ctx.providers for rid in provider_profile(provider).requires}
    roots = [pid for pid in ids if pid not in required]
    if len(roots) != 1:
        return _verdict("C1", False, f"stack {ids} has {len(roots)} unrequired providers {roots}; expected exactly one root")
    _record(ctx, target.record)
    return _verdict("C1", True, f"stack {ids}, root {roots[0]}")


def check_describe_noop(target: ConformanceTarget) -> CheckVerdict:
    """C2: with no study values, describe proposes no change to the native case."""
    ctx = _context(target)
    payload = describe_entry(
        target.record, overrides={"cases_root": str(target.cases_root)}, driver_context=ctx,
    )
    preview = payload.get("record_preview")
    if preview is None:
        return _verdict("C2", False, f"describe of {target.record!r} carries no record preview")
    changed = [p for p in preview["patches"] if p["status"] != "unchanged"]
    if changed:
        return _verdict("C2", False, f"describe proposes {len(changed)} change(s) to the untouched native case: {changed}")
    return _verdict("C2", True, "no changes proposed")


def _quotes(message: str, name: str) -> bool:
    """Whether ``message`` quotes ``name`` whole: ``'n'``, ``"n"`` or `` `n` ``."""
    return any(f"{q}{name}{q}" in message for q in ("'", '"', "`"))


def _names(message: str, name: str) -> bool:
    """Whether ``message`` names ``name`` as a whole token; a short name such as ``"x"`` is a substring of almost any message."""
    if _quotes(message, name):
        return True
    token = rf"(?<![\w.:/\-]){re.escape(name)}(?![\w:/\-]|\.\w)"
    return re.search(token, message) is not None


def check_refuses_unknown(target: ConformanceTarget) -> CheckVerdict:
    """C3: an unknown study name is refused, by that name, before anything runs."""
    ctx = _context(target)
    overrides = {"cases_root": str(target.cases_root), target.unknown_name: 1}
    try:
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
    try:
        reader = ctx.stack.call("get_config_value_reader")
        comparator = ctx.stack.call("get_case_value_comparator")
        validator = ctx.stack.call("get_record_key_validator")
    except MemberAbsent as exc:
        return _verdict("C4", False, str(exc))
    untouched_doc, untouched_key = target.untouched
    before = reader(staged / untouched_doc, untouched_key)
    if before is None:
        return _verdict("C4", False, f"target misconfigured: {untouched_doc}:{'.'.join(untouched_key)} is absent from the native case")
    patch_name, patch_value = target.patch
    patch_doc, patch_key = _split_study_key(patch_name)
    value_kind, _validated = validator(patch_doc, patch_key, patch_value)
    if comparator(value_kind, patch_value, reader(staged / patch_doc, patch_key)):
        return _verdict("C4", False, f"target misconfigured: the native case already holds {patch_name} = {patch_value!r}")
    commit_record_case(
        record, cases_root=target.cases_root, staged_case_root=staged,
        study_by_source={"base": {patch_name: patch_value}}, driver_context=ctx,
        inputs=target.inputs,
    )
    after_patched = reader(staged / patch_doc, patch_key)
    after_untouched = reader(staged / untouched_doc, untouched_key)
    problems = []
    if not comparator(value_kind, patch_value, after_patched):
        problems.append(f"{patch_name} reads {after_patched!r} after patching it to {patch_value!r}")
    if after_untouched != before:
        problems.append(f"{untouched_doc}:{'.'.join(untouched_key)} changed from {before!r} to {after_untouched!r}")
    return _verdict("C4", not problems, "; ".join(problems) or "patched one key; its sibling is unchanged")


def _plan(target: ConformanceTarget, ctx, study: Mapping[str, Any] = {}):
    return strict_plan(
        target.record,
        overrides={"cases_root": str(target.cases_root), **dict(target.base_study), **study},
        scratch_root=target.scratch_root,
        inputs=target.inputs,
        driver_context=ctx,
    )


def _child_env(target: ConformanceTarget) -> dict[str, str]:
    """The caller's environment plus the target's scratch root, set in the copy only, never in ``os.environ``."""
    env = dict(os.environ)
    env[SCRATCH_ENV_VAR] = str(target.scratch_root)
    return env


def _run_document_path(report) -> Path:
    return Path(report.launch["output_dir"]) / RUN_DOCUMENT_FILENAME


def check_strict_plan(target: ConformanceTarget) -> CheckVerdict:
    """C5: plan --strict on the record has no errors, and its launch command is runnable as written."""
    report = _plan(target, _context(target))
    errors = report.error_messages()
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
    """Ids of the non-optional artifacts a reconciliation found missing (C6 and C7)."""
    return [
        a["artifact_id"] for a in reconciliation.get("artifacts", ())
        if a["status"] == "missing" and not a.get("optional")
    ]


def _execute(
    target: ConformanceTarget, ctx, report, env: Mapping[str, str] = {},
) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
    # Never hand-build a run command: the canonical builder carries --plugin
    # from ctx.plugin_selector and ctx.repository.
    proc = run_child(
        omnidriver_run_command(ctx, "--run-document", str(_run_document_path(report))),
        env={**_child_env(target), **env}, timeout=target.timeout_s,
        state_path=Path(report.launch["workflow_state_path"]),
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
        return _verdict("C6", False, f"cannot run: plan failed: {report.error_messages()}")
    try:
        proc, payload = _execute(target, ctx, report)
    except subprocess.TimeoutExpired:
        return _verdict("C6", False, f"run timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if payload is None:
        return _verdict("C6", False, f"run printed no JSON (rc={proc.returncode}); output tail: {_output_tail(proc)}")
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
    problems = _with_recorded_failure(problems, Path(report.launch["workflow_state_path"]), "the workflow state")
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
    try:
        proc, payload = sweep_run(
            target.plugin, sweep_spec(target.record, target.cases_root, base, {target.sweep_name: target.sweep_values}),
            work=work, scratch_dir=target.scratch_root, repository=target.repository, inputs=target.inputs,
            case_timeout_s=target.timeout_s,
            env=_child_env(target), timeout_s=target.timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _verdict("C7", False, f"sweep timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if payload is None:
        return _verdict("C7", False, f"sweep printed no JSON (rc={proc.returncode}); output tail: {_output_tail(proc)}")
    problems = []
    if payload.get("completed_count") != 2 or payload.get("failed_count"):
        problems.append(f"completed {payload.get('completed_count')}, failed {payload.get('failed_count')}")
    for case in payload.get("cases", ()):
        rec = case.get("artifact_reconciliation")
        if rec is None:
            problems.append(f"case {case.get('case_id')} has no artifact reconciliation")
        elif missing := _missing_required(rec):
            problems.append(f"case {case.get('case_id')} is missing artifacts {missing}")
        problems = _with_recorded_failure(
            problems, work / "out" / case.get("workflow_state_path", ""), f"case {case.get('case_id')}'s workflow state",
        )
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
    with strength ``unavailable``. Only a component carrying a real
    fingerprint counts."""
    ctx = _context(target)
    report = _plan(target, ctx)
    if report.status != "ok" or report.workflow_dag is None:
        return _verdict("C8", False, f"cannot check: plan failed: {report.error_messages()}")
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


def _planned_programs(workflow_dag) -> list[str]:
    """The programs a plan runs, a launcher's payload named in its place."""
    programs = []
    for step in workflow_dag.get("steps", ()):
        command = step["command"]
        program = mpi.program(step.get("args", ())) if command in mpi.LAUNCHERS else command
        if program and program not in programs:
            programs.append(program)
    return programs


def check_environment(target: ConformanceTarget) -> CheckVerdict:
    """C9: preflight is clean in the supplied environment, and names a
    program the plan runs when it cannot be found.

    "Names" means quotes the program as a token (:func:`_quotes`), after the
    empty PATH this check supplied is removed from each message -- a bare
    substring match would pass whenever the scratch path itself happened to
    contain a program's name (e.g. ``~/openCARP-runs``).
    """
    ctx = _context(target)
    report = _plan(target, ctx)
    if report.workflow_dag is None:
        return _verdict("C9", False, f"cannot check: plan failed: {report.error_messages()}")
    def preflight(env):
        found = ctx.stack.call("get_environment_diagnostics", report.workflow_dag, env=env, driver_context=ctx)
        return [m for level, m in _levels(found) if level == "error"]

    env = _child_env(target)
    clean = preflight(env)
    empty = target.scratch_root / "conformance" / "C9-empty-path"
    empty.mkdir(parents=True, exist_ok=True)
    broken = preflight({**env, "PATH": str(empty)})
    programs = _planned_programs(report.workflow_dag)
    problems = []
    if clean:
        problems.append(f"errors in the supplied environment: {clean}")
    if not any(_quotes(m.replace(str(empty), ""), program) for m in broken for program in programs):
        problems.append(f"with {', '.join(map(repr, programs))} off PATH, preflight said {broken or 'nothing'}")
    return _verdict("C9", not problems, "; ".join(problems) or "clean; names a missing program")


#: What ``get_record_key_catalog`` requires of every entry. ``value_kind``
#: may be absent only from an entry that says ``validated: False``
#: (``record_surface``'s grammar: an open document).
_REQUIRED_KEY_FIELDS = ("document", "key", "value_kind")


def _incomplete(entry: Mapping[str, Any]) -> bool:
    required = _REQUIRED_KEY_FIELDS if entry.get("validated") is not False else ("document", "key")
    return any(not entry.get(field) for field in required)


def check_discoverable(target: ConformanceTarget) -> CheckVerdict:
    """C10: describe tells an agent, the same way for every solver, which axes
    and keys the record takes, and what to read first.

    The target's patch key is looked up through ``record_surface``'s key
    grammar (``[Int]``, ``<name>`` segments, open documents), so a catalogue
    may list a named segment (cardiacFOAM's
    ``regions.<region_name>.baseline``) or a document whose keys have no
    catalogue. Each listed axis's kind must match its contract's, and every
    bare study name the target itself uses (``base_study`` and
    ``sweep_name``, less the record's selector and the sweep naming keys)
    must be listed: an agent reading ``describe`` must find the axes a real
    study of this record needs."""
    ctx = _context(target)
    record = _record(ctx, target.record)
    payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)}, driver_context=ctx)
    surface = payload.get("record_surface")
    if surface is None:
        return _verdict("C10", False, "describe has no record_surface")
    problems = []
    listed = {a["name"]: a.get("value_kind") for a in surface["axes"]}
    declared = {axis.name: axis.value_kind for axis in record.axes}
    if set(listed) != set(declared):
        problems.append(f"axes listed {sorted(listed)}, record declares {sorted(declared)}")
    if any(not kind for kind in listed.values()):
        problems.append("an axis is listed without its value kind")
    for name in sorted(set(listed) & set(declared)):
        if listed[name] and listed[name] != declared[name]:
            problems.append(f"axis {name!r} is listed as {listed[name]!r}, but its contract takes {declared[name]!r}")
    own_names = {name for name in (*target.base_study, target.sweep_name) if ":" not in name}
    own_names -= NAMING_OUTPUT_KEYS | {record.variant_selector}
    unlisted = sorted(own_names - set(listed))
    if unlisted:
        problems.append(f"the target's own study name(s) {unlisted} are not listed among the axes")
    incomplete = [e for e in surface["keys"] if _incomplete(e)]
    if not surface["keys"]:
        problems.append("no key catalogue")
    elif incomplete:
        problems.append(f"{len(incomplete)} catalogue entr(ies) lack one of {list(_REQUIRED_KEY_FIELDS)}, e.g. {incomplete[0]}")
    document, key_path = _split_study_key(target.patch[0])
    key = ".".join(key_path)
    if not any(lists_key(e, document, key) for e in surface["keys"]):
        problems.append(f"the target's own patch key {document}:{key} is not in the catalogue")
    if not surface["guidance"]:
        problems.append("no agent guidance")
    if "inputs" not in surface:
        problems.append("record_surface has no 'inputs' key")
    elif {i["name"] for i in surface["inputs"]} != {i.name for i in record.inputs}:
        problems.append(
            f"record_surface lists inputs {sorted(i['name'] for i in surface['inputs'])}, "
            f"record declares {sorted(i.name for i in record.inputs)}"
        )
    return _verdict("C10", not problems, "; ".join(problems) or
                    f"{len(surface['axes'])} axes, {len(surface['keys'])} keys, {len(surface['guidance'])} guidance item(s)")


def _relpaths(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*")}


def check_restage_is_clean(target: ConformanceTarget) -> CheckVerdict:
    """C11: staging a record from a case one run has written carries nothing
    that run wrote, and drops nothing authored.

    A native case someone has already run in, or a copy of an earlier
    stage, holds that run's state (core's run records) and its outputs.
    Staging it again must give exactly the paths the untouched native case
    has -- no more, no fewer, checked in both directions. Every mismatched
    path is named.

    This compares path *sets* only, not file contents: a restage with
    ``study_by_source={"base": {}}`` (below) still inherits whatever values
    the first run's plan patched into the case's documents -- carrying that
    content forward is intended (a restage continues from the inputs the
    case holds), but content is not audited here.
    """
    ctx = _context(target)
    record = _record(ctx, target.record)
    report = _plan(target, ctx)
    if report.status != "ok":
        return _verdict("C11", False, f"cannot check: plan failed: {report.error_messages()}")
    try:
        proc, payload = _execute(target, ctx, report)
    except subprocess.TimeoutExpired:
        return _verdict("C11", False, f"the first run timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if payload is None or payload.get("status") != "ok":
        return _verdict("C11", False, f"cannot check: the first run did not complete (rc={proc.returncode}); output tail: {_output_tail(proc)}")
    work = target.scratch_root / "conformance" / "C11"
    if work.exists():
        shutil.rmtree(work)
    ran_cases_root = work / "ran"
    shutil.copytree(Path(report.launch["case_root"]), ran_cases_root / record.native_case_relpath, symlinks=True)
    restaged = work / "restaged" / record.name
    commit_record_case(
        record, cases_root=ran_cases_root, staged_case_root=restaged,
        study_by_source={"base": {}}, driver_context=ctx, inputs=target.inputs,
    )
    restaged_paths = _relpaths(restaged)
    # An input's destination is never part of the native case folder, so it
    # is added to the expected set here -- the native folder's paths plus
    # every input destination and its ancestor directories (``restaged_paths``
    # lists directories too).
    input_paths = {
        str(PurePosixPath(*parts[:i]))
        for input_ in record.inputs for destination in input_.destinations()
        for parts in (PurePosixPath(destination).parts,) for i in range(1, len(parts) + 1)
    }
    native_paths = _relpaths(target.cases_root / record.native_case_relpath) | input_paths
    carried = sorted(restaged_paths - native_paths)
    dropped = sorted(native_paths - restaged_paths)
    if carried or dropped:
        def _shown(paths: list[str]) -> list[str]:
            return paths[:20] + ([f"... {len(paths) - 20} more"] if len(paths) > 20 else [])
        parts = []
        if carried:
            parts.append(f"carried {len(carried)} path(s) the native case does not have: {_shown(carried)}")
        if dropped:
            parts.append(f"dropped {len(dropped)} path(s) the native case has: {_shown(dropped)}")
        return _verdict("C11", False, f"restaging a case the first run wrote " + "; ".join(parts))
    return _verdict(
        "C11", True,
        "restaged from a run case; the restaged case has exactly the native "
        "case's paths (content inherited from the run's plan is expected, "
        "and not checked here)",
    )


def check_readable_quantities(target: ConformanceTarget) -> CheckVerdict:
    """C12: every record output that declares a format has a reader for it,
    through the reader contract, with a valid declaration. A record whose
    outputs declare no format passes and says so: not every record is
    compared.

    This checks the reader's *declaration* only (``check_reader``) -- it
    never calls ``read``, so a reader whose ``read`` always raises still
    passes C12."""
    ctx = _context(target)
    record = _record(ctx, target.record)
    formats = sorted({step.produced_format(path) for step in record.workflow_steps for path in step.produces}
                     - {PLAIN_FILE_FORMAT})
    if not formats:
        return _verdict("C12", True, "no output declares a format, so there is nothing to read")
    problems = []
    for artifact_format in formats:
        reader = ctx.stack.call("get_artifact_value_reader", artifact_format)
        if reader is None:
            problems.append(f"no reader for format {artifact_format!r}")
            continue
        try:
            check_reader(reader, artifact_format=artifact_format)
        except ReaderDeclarationError as exc:
            problems.append(str(exc))
    return _verdict("C12", not problems, "; ".join(problems) or f"readers declared for {formats} (declaration checked, not read)")


def _artifact_and_quantities(target: ConformanceTarget, ctx, report) -> tuple[dict[str, Any], dict[str, Quantity]]:
    """A planned and run case's document, and the declared quantities read from it."""
    declared = target.quantity
    document = json.loads(_run_document_path(report).read_text())
    artifact = data_artifact_from_json(
        next(raw for raw in document["expectedArtifacts"] if raw["format"] == declared.artifact_format)
    )
    reader = ctx.stack.call("get_artifact_value_reader", declared.artifact_format)
    points = {}
    if reader.takes_points:
        points = {
            name: tuple(convert(c, declared.at_unit, reader.coordinate_unit) for c in xyz)
            for name, xyz in declared.at.items()
        }
    quantities = read_quantities(
        reader, Path(report.launch["case_root"]), artifact, ReadRequest(names=tuple(declared.at), points=points),
    )
    return document, {q.name: q for q in quantities}


def _run_for_quantities(
    target: ConformanceTarget, ctx, study: Mapping[str, Any], label: str, env: Mapping[str, str] = {},
):
    """The run document, declared quantities, case root and step logs of ``study``'s run, or a failure's detail."""
    report = _plan(target, ctx, study)
    if report.status != "ok":
        return f"the {label} plan failed: {report.error_messages()}"
    try:
        proc, payload = _execute(target, ctx, report, env)
    except subprocess.TimeoutExpired:
        return f"the {label} run timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)"
    if payload is None or payload.get("status") != "ok":
        return f"the {label} run did not complete (rc={proc.returncode}); output tail: {_output_tail(proc)}"
    document, quantities = _artifact_and_quantities(target, ctx, report)
    logs = [Path(step[key]) for step in payload["workflow_state"]["steps"] for key in ("stdout_log", "stderr_log") if step.get(key)]
    return document, quantities, Path(report.launch["case_root"]), logs


def _rank_problems(evidence, ranks: int, case_root: Path, logs: list[Path]) -> list[str]:
    """Why the parallel run does not show ``ranks`` ranks in the solver's own output, if it does not."""
    problems = []
    counts = [int(m) for log in logs if log.is_file() for m in re.findall(evidence.log_pattern, log.read_text(errors="replace"))]
    if ranks not in counts:
        problems.append(f"no step log matches {evidence.log_pattern!r} with {ranks} ranks (it names {sorted(set(counts)) or 'none'})")
    elif max(counts) > ranks:
        problems.append(f"a step log names {max(counts)} ranks, beyond the {ranks} requested")
    if evidence.paths is not None:
        found = sorted(path.name for path in case_root.glob(evidence.paths))
        if len(found) != ranks:
            problems.append(f"{evidence.paths!r} matches {len(found)} entries under the case root, not {ranks}: {found}")
    return problems


def check_parallel_agrees(target: ConformanceTarget) -> CheckVerdict:
    """C13: a serial run and a parallel run of the record give the same value
    of every declared quantity, within the target's ``parallel_tolerance``,
    the parallel run says it asked for those ranks, and the solver's own
    output shows it ran on them (``QuantityTarget.rank_evidence``).

    A target that declares no quantity passes and says so."""
    ctx = _context(target)
    _record(ctx, target.record)
    declared = target.quantity
    if declared is None:
        return _verdict("C13", True, "the target declares no quantity, so there is nothing to compare")
    serial = _run_for_quantities(target, ctx, declared.study, "serial")
    if isinstance(serial, str):
        return _verdict("C13", False, serial)
    parallel_study = {**declared.study, **declared.parallel_study, "parallel": declared.ranks}
    parallel = _run_for_quantities(target, ctx, parallel_study, "parallel", declared.rank_evidence.environment)
    if isinstance(parallel, str):
        return _verdict("C13", False, parallel)
    (serial_doc, serial_values, _, _), (parallel_doc, parallel_values, case_root, logs) = serial, parallel
    problems = _rank_problems(declared.rank_evidence, declared.ranks, case_root, logs)
    if "parallel" in serial_doc["resolvedEntry"]:
        problems.append("the serial run's document records a parallel request")
    requested = (parallel_doc["resolvedEntry"].get("parallel") or {}).get("requested")
    if requested != declared.ranks:
        problems.append(f"the parallel run's document records request {requested!r}, not {declared.ranks}")
    if serial_doc["workflowDag"] == parallel_doc["workflowDag"]:
        problems.append("the parallel run planned the serial steps")
    for name, s in serial_values.items():
        p = parallel_values[name]
        if (s.status, s.unit, s.sampled_at) != (p.status, p.unit, p.sampled_at):
            problems.append(f"{name!r}: serial reads {s.status} {s.sampled_at} {s.unit}, parallel {p.status} {p.sampled_at} {p.unit}")
        elif s.status == "evaluated" and abs(p.value - s.value) > declared.parallel_tolerance:
            problems.append(f"{name!r}: serial {s.value}, parallel {p.value}, beyond {declared.parallel_tolerance} {s.unit}")
    if not any(q.status == "evaluated" for q in serial_values.values()):
        problems.append("no declared quantity is evaluated in the serial run, so nothing was compared")
    return _verdict(
        "C13", not problems,
        "; ".join(problems) or f"{len(serial_values)} quantit(ies) agree between serial and {declared.ranks} ranks, which the solver's own output shows",
    )


def check_quantity_across_sweep(target: ConformanceTarget) -> CheckVerdict:
    """C14: the declared quantity compares across a two-case sweep of the
    target's sweep axis, end to end as an agent would: ``sweep-run``,
    ``compare`` on the target's reference, the report attached to each case.
    The comparison must read both sides of at least one pair; whether the two
    resolutions agree is physics, not conformance.

    A target that declares no quantity passes and says so."""
    _record(_context(target), target.record)
    declared = target.quantity
    if declared is None:
        return _verdict("C14", True, "the target declares no quantity, so there is nothing to compare")
    work = target.scratch_root / "conformance" / "C14"
    if work.exists():
        shutil.rmtree(work)
    base = {k: v for k, v in {**target.base_study, **declared.study}.items() if k != target.sweep_name}
    try:
        proc, payload = sweep_run(
            target.plugin,
            sweep_spec(target.record, target.cases_root, base, {target.sweep_name: declared.sweep_values}),
            work=work, scratch_dir=target.scratch_root, repository=target.repository, inputs=target.inputs,
            case_timeout_s=target.timeout_s,
            env=_child_env(target), timeout_s=target.timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _verdict("C14", False, f"sweep timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if payload is None or payload.get("completed_count") != 2 or payload.get("failed_count"):
        return _verdict("C14", False, f"cannot compare: the sweep did not complete both cases (rc={proc.returncode}); output tail: {_output_tail(proc)}")
    output = work / "out"
    cases = build_sweep_context(output).cases
    runs = {}
    for label, value in zip(("first", "second"), declared.sweep_values):
        case = next(c for c in cases if c.resolved_axis_values[target.sweep_name] == value)
        document = json.loads((output / case.run_document_path).read_text())
        artifact = next(a for a in document["expectedArtifacts"] if a["format"] == declared.artifact_format)
        runs[label] = {
            "plugin": target.plugin, "sweep_output": str(output), "case_id": case.case_id,
            "artifact_id": artifact["artifact_id"],
            "points": {"unit": declared.at_unit, "at": {name: list(xyz) for name, xyz in declared.at.items()}},
            "max_sampling_offset": declared.max_sampling_offset,
        }
    request = work / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "reference": str(declared.reference),
        "tolerance": {"kind": "absolute", "value": declared.tolerance, "unit": declared.tolerance_unit,
                      "rationale": "declared before either run was read; a self-comparison across the target's "
                                   "sweep, not a benchmark acceptance claim"},
        "both_not_reached": declared.both_not_reached,
        "runs": runs,
        "pairs": [{"reference_label": label, "left": {"run": "first", "quantity": name},
                   "right": {"run": "second", "quantity": name}} for label, name in declared.pairs.items()],
    }))
    report_path = work / "report.json"
    try:
        compare = subprocess.run(
            [sys.executable, "-m", "omnidriver", "compare", "--comparison-request", str(request), "--report", str(report_path)],
            capture_output=True, text=True, env=_child_env(target), timeout=target.timeout_s,
        )
    except subprocess.TimeoutExpired:
        return _verdict("C14", False, f"compare timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
    if compare.returncode != 0:
        return _verdict("C14", False, f"compare exited {compare.returncode}: {compare.stdout[-800:]} {compare.stderr[-800:]}")
    report = json.loads(report_path.read_text())
    metrics = report["metrics"]
    problems = []
    if report["status"] not in {"passed", "failed"}:
        problems.append(f"report status {report['status']!r}")
    if {m["reference_label"] for m in metrics} != set(declared.pairs):
        problems.append(f"the report compares {sorted(m['reference_label'] for m in metrics)}, the target pairs {sorted(declared.pairs)}")
    if off := [m["reference_label"] for m in metrics if m["status"] == "sampled_off_point"]:
        problems.append(f"sampled off the declared point: {off}")
    if not any(m["left"]["status"] == m["right"]["status"] == "evaluated" for m in metrics):
        problems.append("no pair is evaluated on both sides, so the comparison read nothing")
    experiment = inspect_sweep_experiment(output, comparisons=experiment_comparisons(report_path, sweep_output=output))
    if {c.comparison.association_status for c in experiment.cases} != {"run_verified"}:
        problems.append(f"the report is not attached to both cases as run_verified: {[c.comparison.association_status for c in experiment.cases]}")
    elif {c.comparison.status for c in experiment.cases} != {report["status"]}:
        problems.append("a case carries a comparison status other than the report's")
    return _verdict("C14", not problems, "; ".join(problems) or f"{len(metrics)} pair(s) compared, report {report['status']}")


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
    "C10": check_discoverable,
    "C11": check_restage_is_clean,
    "C12": check_readable_quantities,
    "C13": check_parallel_agrees,
    "C14": check_quantity_across_sweep,
}


_StatEntry = tuple[bool, int, int]


def _tree_stat(root: Path) -> dict[str, _StatEntry]:
    """``relpath -> (is_dir, size, mtime_ns)`` under ``root`` (itself ``"."``); stat, not bytes, as the native tree is large."""
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

    Every check runs inside one suite-wide native guard: a stat snapshot of
    the whole ``target.cases_root``, taken before and after. Any difference
    fails the verdict and names the changed paths, whatever the check itself
    concluded."""
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
