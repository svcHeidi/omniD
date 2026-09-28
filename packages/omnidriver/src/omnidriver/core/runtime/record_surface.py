"""What describe tells an agent about a tutorial record, the same for every solver (C10).

**The catalogue key grammar** (``SolverPlugin.get_record_key_catalog``).
Each entry names a ``document`` and a dotted ``key``. Two placeholders
stand for what a study writes concretely (added 2026-09-26, conformance
Task 14 step 4):

- ``[Int]`` stands for any non-negative index: ``stim[Int].start`` lists
  ``stim[0].start`` and ``stim[3].start``;
- a whole segment ``<name>`` -- any identifier in angle brackets, such as
  ``<region_name>`` -- stands for any single dot-free segment:
  ``regions.<region_name>.baseline`` lists ``regions.lv.baseline``, not
  ``regions.lv.inner.baseline``.

A document whose keys are written as asked, with no catalogue behind them,
is listed once, as ``{"document": d, "key": ANY_KEY, "validated": False}``.
It needs no ``value_kind``, and lists every key of ``d``: a key matches it
through its document, never through the pattern.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

DOCUMENTATION_ROLE = "case.documentation"

#: The key of a document-level entry: every key of its document.
ANY_KEY = "<any>"

_INDEX = re.escape("[Int]")
_NAMED_SEGMENT = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")


def _segment_pattern(segment: str) -> str:
    if _NAMED_SEGMENT.fullmatch(segment):
        return r"[^.]+"
    return re.escape(segment).replace(_INDEX, r"\[\d+\]")


def key_pattern(key: str) -> re.Pattern[str]:
    """``key``, a catalogue key in the grammar above, as a pattern that
    matches exactly the concrete keys it lists."""
    return re.compile(r"\.".join(_segment_pattern(segment) for segment in key.split(".")))


def lists_key(entry: Mapping[str, Any], document: str, key: str) -> bool:
    """Whether catalogue ``entry`` lists ``document:key``."""
    if entry.get("document") != document:
        return False
    if entry.get("key") == ANY_KEY:
        return entry.get("validated") is False
    return key_pattern(str(entry.get("key", ""))).fullmatch(key) is not None


def record_surface(
    record, *, native_case_root: Path, driver_context,
    supplied: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    axes = [
        {"name": axis.name, "value_kind": axis.value_kind}
        for axis in sorted(record.axes, key=lambda axis: axis.name)
    ]
    surface = driver_context.capabilities.record_surface
    documentation = []
    for rule in driver_context.capabilities.case_files.all_rules():
        path = Path(native_case_root) / rule.path
        if rule.role == DOCUMENTATION_ROLE and path.is_file():
            documentation.append({"path": rule.path, "text": path.read_text(errors="replace")})
    supplied = supplied or {}
    inputs = [
        {
            "name": input_.name,
            "files": [list(pair) for pair in input_.files],
            "native_location": input_.native_relpath,
            "supplied": input_.name in supplied,
        }
        for input_ in sorted(record.inputs, key=lambda input_: input_.name)
    ]
    return {
        "axes": axes,
        "keys": [dict(entry) for entry in surface.key_catalog(Path(native_case_root))],
        "guidance": [dict(item) for item in surface.guidance()],
        "case_documentation": documentation,
        "inputs": inputs,
    }
