"""Render ``clone_and_patch`` mutations into OpenFOAM dictionary bytes.

Rendering happens against a copy under ``snapshot_root``; the real case is only read.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.case_write import (
    CaseMutationRequest,
    ParameterAssignment,
    RenderedFile,
    ResolvedMutation,
    patch_resolution,
    render_by_document,
)

from .case_planning import (
    HEX_CELL_COUNTS_KEY_PATH,
    _rewrite_hex_block_lines,
    hex_cell_counts_expected_blocks,
    plan_block_mesh_resolution,
)
from .literals import CONTAINER_FORMATTERS
from .mutators import remove_foam_dict, remove_foam_entry, update_foam_entry

#: Must match what ``OpenFOAMEnvironmentPlugin.get_rendered_formats`` declares;
#: ``case_write.render_mutation`` refuses a ``RenderedFile`` whose format its
#: provider did not declare.
FORMAT = "openfoam_dictionary"


def _snapshot_copy(case_root: Path, snapshot_root: Path, relpath: str) -> Path:
    """Copy ``relpath`` from the real case into the snapshot, preserving mode."""
    source = case_root / relpath
    destination = snapshot_root / relpath
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_file():
        shutil.copy2(source, destination)
    return destination


def _target_for_parameter(parameter: ParameterAssignment) -> dict[str, Any]:
    """One ``render_patch_case_files`` edit target; a parameter at ``HEX_CELL_COUNTS_KEY_PATH`` becomes the structural ``plan_block_mesh_resolution`` target."""
    if parameter.key_path[:1] == HEX_CELL_COUNTS_KEY_PATH:
        return dict(plan_block_mesh_resolution(
            parameter.document, " ".join(str(count) for count in parameter.value),
            expected_blocks=hex_cell_counts_expected_blocks(parameter.key_path),
        ))
    target: dict[str, Any] = {
        "qualified_id": parameter.qualified_id,
        "document": parameter.document,
        "expanded_key_path": list(parameter.expanded_key_path()),
        "operation": parameter.operation,
        "format": FORMAT,
    }
    if parameter.operation != "remove":
        render = CONTAINER_FORMATTERS.get(parameter.value_kind)
        target["value"] = render(parameter.value) if render is not None else parameter.value
    elif parameter.value_kind == "mapping":
        target["removes_dictionary"] = True
    return target


def patch_mutation(request: CaseMutationRequest, *, owner_id: str) -> ResolvedMutation:
    """The semantic owner's answer for a ``clone_and_patch`` request, for
    every OpenFOAM-based plugin. ``owner_id`` is the calling plugin's id."""
    return patch_resolution(request, owner_id=owner_id, target=_target_for_parameter)


def render_patch_case_files(
    resolved: Any,
    *,
    snapshot_root: Path,
    driver_context: Any,
    execution_env: Any | None = None,
    renderer_id: str,
) -> tuple[RenderedFile, ...]:
    """Render a ``clone_and_patch`` resolution: one file per edited document.

    Multiple edits landing on one document are folded into a single pass over
    one snapshot copy (``CaseWritePlan`` refuses two ``RenderedFile``s
    claiming one path). A target may instead carry:

    - ``"hex_cell_counts"`` -- a structural rewrite of every ``hex (`` block
      declaration via :func:`case_planning._rewrite_hex_block_lines`,
      validated against ``expected_blocks``. At most one per document.
    - ``"dict_operation": "remove"`` -- a whole named sub-dictionary deleted
      via :func:`mutators.remove_foam_dict`, applied before the key/value
      edits below, with ``missing_ok=True``.

    Otherwise a target is a key/value edit whose ``"operation"`` (default
    ``"set"``) selects between :func:`mutators.update_foam_entry` and
    :func:`mutators.remove_foam_entry`: ``"set"`` requires the key to already
    exist (``add_if_missing=False``), ``"ensure"`` upserts it, and
    ``"remove"`` deletes it with ``missing_ok=True``, through
    :func:`mutators.remove_foam_dict` when its value kind is ``mapping``.
    """
    del driver_context, execution_env
    case_root = Path(resolved.request.case_root)
    snapshot_root = Path(snapshot_root)
    for document in sorted({str(target["document"]) for target in resolved.targets}):
        if not (case_root / document).is_file():
            raise ValueError(
                f"patch target {document!r} does not exist under {case_root}; "
                f"clone_and_patch edits a document that already exists"
            )
        _snapshot_copy(case_root, snapshot_root, document)
    return render_by_document(
        resolved, snapshot_root=snapshot_root, renderer_id=renderer_id, format=FORMAT, patch=_patch_document,
    )


def _patch_document(snapshot_path: Path, edits: list[Mapping[str, Any]]) -> bytes:
    document = str(edits[0]["document"])
    hex_edits = [edit for edit in edits if "hex_cell_counts" in edit]
    dict_edits = [edit for edit in edits if "dict_operation" in edit]
    value_edits = [
        edit for edit in edits
        if "hex_cell_counts" not in edit and "dict_operation" not in edit
    ]
    if len(hex_edits) > 1:
        raise ValueError(
            f"patch target {document!r} carries {len(hex_edits)} hex "
            f"block-count rewrites; a document's `hex (` blocks are "
            f"rewritten once, by one target"
        )
    for edit in hex_edits:
        rewritten = _rewrite_hex_block_lines(
            snapshot_path.read_text(), edit["hex_cell_counts"],
            int(edit["expected_blocks"]), label=document,
        )
        snapshot_path.write_text(rewritten)
    for edit in dict_edits:
        scope = tuple(edit["scope"]) if edit.get("scope") else None
        if edit["dict_operation"] == "remove":
            remove_foam_dict(
                snapshot_path, edit["dict_name"], scope=scope, missing_ok=True,
            )
        else:
            raise ValueError(
                f"patch target {document!r} declares dict_operation "
                f"{edit['dict_operation']!r}; the known operation is "
                f"'remove'"
            )
    for edit in value_edits:
        key_path = tuple(edit["expanded_key_path"])
        scope = key_path[:-1] or None
        key = key_path[-1]
        operation = edit.get("operation", "set")
        if operation == "remove" and edit.get("removes_dictionary"):
            remove_foam_dict(snapshot_path, key, scope=scope, missing_ok=True)
        elif operation == "remove":
            remove_foam_entry(snapshot_path, key, scope=scope, missing_ok=True)
        elif operation == "ensure":
            update_foam_entry(
                snapshot_path, key, edit["value"], scope=scope, add_if_missing=True,
            )
        elif operation == "set":
            update_foam_entry(
                snapshot_path, key, edit["value"], scope=scope, add_if_missing=False,
            )
        else:
            raise ValueError(
                f"patch target {document!r} declares operation "
                f"{operation!r} for {key!r}; known operations are "
                f"'set', 'ensure' and 'remove'"
            )
    return snapshot_path.read_bytes()
