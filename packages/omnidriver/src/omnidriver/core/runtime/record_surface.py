"""What describe tells an agent about a tutorial record, the same for every solver (C10)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from ..contracts.catalogue_paths import PLACEHOLDER

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


def record_surface(
    record, *, native_case_root: Path, driver_context,
    supplied: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    axes = [
        {"name": axis.name, "value_kind": axis.value_kind}
        for axis in sorted(record.axes, key=lambda axis: axis.name)
    ]
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
    listed = stack.call("get_record_key_catalog", Path(native_case_root))
    keys = stack.call("select_applicable_record_keys", listed, Path(native_case_root))
    return {
        "axes": axes,
        "keys": [dict(entry) for entry in keys],
        **({"keys_omitted": {
            "count": len(listed) - len(keys),
            "why": "their applicable_when does not hold in this case's own settings; `omnidriver catalog` lists every key",
        }} if len(keys) < len(listed) else {}),
        "guidance": [dict(item) for item in stack.call("get_agent_guidance")],
        "case_documentation": documentation,
        "inputs": inputs,
    }
