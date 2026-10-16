"""What describe tells an agent about a tutorial record, the same for every solver (C10)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from ..contracts.catalogue_paths import PLACEHOLDER
from ..tutorial_records import PLAIN_FILE_FORMAT

DOCUMENTATION_ROLE = "case.documentation"

#: The key of a document-level entry: every key of its document.
ANY_KEY = "<any>"

_INDEX = re.escape("[Int]")


def _segment_pattern(segment: str) -> str:
    if PLACEHOLDER.fullmatch(segment):
        return r"[^.]+"
    return re.escape(segment).replace(_INDEX, r"\[\d+\]")


def key_pattern(key: str) -> re.Pattern[str]:
    """``key``, a catalogue key using ``[Int]`` (any index) and ``<name>``
    (any single dot-free segment) placeholders, as a pattern that matches
    exactly the concrete keys it lists."""
    return re.compile(r"\.".join(_segment_pattern(segment) for segment in key.split(".")))


def lists_key(entry: Mapping[str, Any], document: str, key: str) -> bool:
    """Whether catalogue ``entry`` lists ``document:key``."""
    if entry.get("document") != document:
        return False
    if entry.get("key") == ANY_KEY:
        return entry.get("validated") is False
    return key_pattern(str(entry.get("key", ""))).fullmatch(key) is not None


def _listed_points(points: Mapping[str, Any] | None) -> dict[str, list[float]] | None:
    return None if points is None else {label: list(point) for label, point in points.items()}


def conformance_quantity(record, benchmarks: Path | None = None) -> dict[str, Any] | None:
    """The quantity ``omnidriver check`` compares for the record, or ``None``: the study its runs take, and its
    points (``at``, in ``at_unit``, which is also ``max_sampling_offset``'s unit). Points the reference supplies
    are read from it under ``benchmarks`` when that is given, and are ``null`` otherwise."""
    conformance = record.conformance
    quantity = conformance.quantity if conformance is not None else None
    if quantity is None:
        return None
    points_from = "reference" if quantity.at is None else "declared"
    if benchmarks is not None:
        quantity = quantity.resolved(benchmarks)
    return {
        "compared_by": "omnidriver check (C13: serial against parallel; C14: across its sweep)",
        "artifact_format": quantity.artifact_format, "study": {**conformance.base_study, **quantity.study},
        "points_from": points_from, "max_sampling_offset": quantity.max_sampling_offset,
        "reference": str(quantity.reference), "at": _listed_points(quantity.at),
        "pairs": None if quantity.pairs is None else dict(quantity.pairs),
        "at_unit": quantity.at_unit, "max_sampling_offset_unit": quantity.at_unit,
    }


def record_readers(record, stack) -> list[dict[str, Any]]:
    """For each format the record's steps declare on what they produce, the reader the stack reads it with,
    and the steps producing it; a format no reader takes is not listed."""
    steps: dict[str, list[str]] = {}
    for step in record.workflow_steps:
        for path in step.produces:
            artifact_format = step.produced_format(path)
            if artifact_format != PLAIN_FILE_FORMAT and step.step_id not in steps.setdefault(artifact_format, []):
                steps[artifact_format].append(step.step_id)
    listed = []
    for artifact_format, producers in steps.items():
        reader = stack.call("get_artifact_value_reader", artifact_format)
        if reader is None:
            continue
        listed.append({
            "format": artifact_format, "steps": producers, "value_unit": reader.value_unit,
            "sampling_rule": reader.sampling_rule, "coordinate_unit": reader.coordinate_unit,
            "takes_points": reader.takes_points, "sentinels": sorted(reader.sentinels),
        })
    return listed


def record_surface(
    record, *, native_case_root: Path, driver_context,
    supplied: Mapping[str, Any] | None = None, benchmarks: Path | None = None,
) -> dict[str, Any]:
    axes = [axis.to_json() for axis in sorted(record.axes, key=lambda axis: axis.name)]
    stack = driver_context.stack
    documentation = []
    for rule in stack.call("get_profile").case_files:
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
    listed = stack.call("get_record_key_catalog", Path(native_case_root), driver_context=driver_context)
    keys = stack.call("select_applicable_record_keys", listed, Path(native_case_root))
    return {
        "axes": axes,
        "derivations": [derivation.to_json() for derivation in record.derivations],
        "keys": [dict(entry) for entry in keys],
        **({"keys_omitted": {
            "count": len(listed) - len(keys),
            "why": "their applicable_when rules out this case's own solver; `omnidriver catalog` lists every key",
        }} if len(keys) < len(listed) else {}),
        "conformance_quantity": conformance_quantity(record, benchmarks),
        "readers": record_readers(record, stack),
        "guidance": [dict(item) for item in stack.call("get_agent_guidance")],
        "case_documentation": documentation,
        "inputs": inputs,
    }
