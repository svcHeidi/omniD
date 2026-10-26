"""Solver-neutral primitives for building an OpenFOAM case from a catalogue, outside the record path.

Value resolution, block serialisation and the committed write; a solver's builder composes them.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from omnidriver.core.case_transaction import commit_case_write
from omnidriver.core.case_write import (
    CaseMutationRequest,
    CaseWritePlan,
    RenderedFile,
)
from omnidriver.core.contracts.catalogue_paths import PLACEHOLDER, slot_key

from .case_rendering import FORMAT

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry


def populate_values(
    entries: list[DictEntry],
    context: dict[str, Any],
    *,
    typical_value_fallback: bool = True,
) -> dict[str, str]:
    """Resolve each entry's value to write: an explicit value in `context`,
    else `entry.typical_value` when `typical_value_fallback`, else omitted
    (left for the caller's rule check to flag if required)."""
    populated: dict[str, str] = {}

    dynamic_entries = []
    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            # Any <placeholder> segment is a wildcard, not a fixed set of names --
            # a template can use any placeholder name and must still match.
            pattern = PLACEHOLDER.sub(r"([^.]+)", re.escape(template))
            dynamic_entries.append((entry, template, re.compile(f"^{pattern}$")))

    active_instances: dict[str, set[tuple[str, ...]]] = {}
    for key, val in context.items():
        if val in (None, ""):
            continue
        for entry, template, regex in dynamic_entries:
            match = regex.match(key)
            if match:
                groups = match.groups()
                prefix = template.split(".<")[0]
                active_instances.setdefault(prefix, set()).add(groups)

    for entry in entries:
        if getattr(entry, "dynamic_path", False):
            template = slot_key(entry.driver_path)
            prefix = template.split(".<")[0]
            if prefix in active_instances:
                for groups in active_instances[prefix]:
                    concrete_key = template
                    for captured in groups:
                        concrete_key = PLACEHOLDER.sub(captured, concrete_key, count=1)

                    if concrete_key in context and context[concrete_key] not in (None, ""):
                        populated[concrete_key] = str(context[concrete_key])
                    elif typical_value_fallback and entry.typical_value:
                        populated[concrete_key] = entry.typical_value
            continue

        key = slot_key(entry.driver_path)
        if key in context and context[key] not in (None, ""):
            populated[key] = str(context[key])
            continue
        if typical_value_fallback and entry.typical_value:
            conflict = False
            for mx_path in getattr(entry, "mutually_exclusive_with", ()):
                mx_key = slot_key(mx_path)
                if mx_key in context and context[mx_key] not in (None, ""):
                    conflict = True
                    break
            if not conflict:
                populated[key] = entry.typical_value
            continue
    return populated


def set_nested(node: dict, path: list[str], value: Any) -> None:
    """Insert `value` at `path` inside the nested dict `node`, creating
    intermediate sub-dicts as needed."""
    cursor = node
    for segment in path[:-1]:
        cursor = cursor.setdefault(segment, {})
        if not isinstance(cursor, dict):
            raise ValueError(
                f"Path collision in serialiser at segment {segment!r}: a leaf "
                f"value exists where a sub-block is needed."
            )
    cursor[path[-1]] = value


def value_token(value: str) -> str:
    # OpenFOAM's tokenizer reads a bare token starting with a digit as a number
    # (e.g. `3D` becomes label `3` plus junk), so only that case needs quoting.
    if not isinstance(value, str) or not value:
        return value
    token = value.strip()
    if not token or not token[0].isdigit():
        return value
    if any(ch.isspace() for ch in token) or token[0] in "([{\"":
        return value
    try:
        float(token)
    except ValueError:
        return f'"{token}"'
    return value


def serialize_block(tree: dict, indent: int) -> str:
    """Emit nested OpenFOAM block syntax. Leaves are `key value;`,
    sub-blocks are `key\\n{\\n  ...\\n}` recursively."""
    lines: list[str] = []
    pad = " " * indent
    for key, value in tree.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}")
            lines.append(f"{pad}{{")
            lines.append(serialize_block(value, indent + 4))
            lines.append(f"{pad}}}")
        else:
            lines.append(f"{pad}{key} {value_token(value)};")
    return "\n".join(lines)


def write_documents(
    case_dir: Path,
    documents: Mapping[str, str],
    *,
    owner_id: str,
    source_artifacts: tuple[str, ...],
    driver_context: Any,
    executable: frozenset[str] = frozenset(),
    keep_existing: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Commit ``documents`` (case-relative path to text) into ``case_dir`` as
    one commit. A path in ``keep_existing`` that already exists
    is left alone; one in ``executable`` is written ``0o755``."""
    case_dir.mkdir(parents=True, exist_ok=True)
    files: list[RenderedFile] = []
    for path, text in documents.items():
        target = case_dir / path
        if path in keep_existing and target.is_file():
            continue
        existed = target.is_file()
        files.append(RenderedFile(
            path=path, content=text.encode(), mode=0o755 if path in executable else None,
            exists_before=existed,
            before_digest=hashlib.sha256(target.read_bytes()).hexdigest() if existed else None,
            renderer_id=owner_id, format=FORMAT,
        ))
    identity = getattr(driver_context, "identity", None)
    plan = CaseWritePlan(
        request=CaseMutationRequest(
            mode="synthesize", case_root=case_dir, adapter_id=owner_id, workflow="build",
            source_artifacts=source_artifacts, parameters=(), requested_by=f"{owner_id}.build",
        ),
        files=tuple(files), semantic_owner_id=owner_id,
        stack_identity=identity.capability_digest if identity is not None else "0" * 64,
        expected_effects=tuple(f"author {file.path}" for file in files),
    )
    return commit_case_write(plan, driver_context=driver_context)
