"""C1-C10. Each check is self-contained: it builds its own context, stages
its own copy, and returns a verdict naming what it saw. No check skips; a
check that cannot run is a failure saying why."""
from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Iterator

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.runtime.record_execution import commit_record_case
from omnidriver.core.tutorial_records import TutorialRecordError

from .target import CheckVerdict, ConformanceTarget

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


CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]] = {
    "C1": check_load,
    "C2": check_describe_noop,
    "C3": check_refuses_unknown,
    "C4": check_patch_preserves,
}


def run_check(check_id: str, target: ConformanceTarget) -> CheckVerdict:
    if check_id not in CHECKS:
        raise KeyError(f"no conformance check {check_id!r}; known: {sorted(CHECKS)}")
    return CHECKS[check_id](target)
