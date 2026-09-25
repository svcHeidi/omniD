"""C1-C10. Each check is self-contained: it builds its own context, stages
its own copy, and returns a verdict naming what it saw. No check skips; a
check that cannot run is a failure saying why."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any, Callable, Iterator

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
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


CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]] = {
    "C1": check_load,
    "C2": check_describe_noop,
    "C3": check_refuses_unknown,
}


def run_check(check_id: str, target: ConformanceTarget) -> CheckVerdict:
    if check_id not in CHECKS:
        raise KeyError(f"no conformance check {check_id!r}; known: {sorted(CHECKS)}")
    return CHECKS[check_id](target)
