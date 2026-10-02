"""Render case-write-channel mutations into OpenFOAM dictionary bytes.

``clone_and_patch`` edits documents that already exist; ``synthesize``
authors them from scratch. Every rendering happens against a copy under
``snapshot_root``; the real case is only ever read, never written, here.
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
    _digest_bytes,
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


def _document_edits(resolved: Any) -> dict[str, list[Mapping[str, Any]]]:
    """Group a resolution's targets by the document each one edits."""
    by_document: dict[str, list[Mapping[str, Any]]] = {}
    for target in resolved.targets:
        by_document.setdefault(str(target["document"]), []).append(target)
    return by_document


def _target_for_parameter(parameter: ParameterAssignment) -> dict[str, Any]:
    """One :func:`render_patch_case_files` edit target for ``parameter``.

    A parameter at ``HEX_CELL_COUNTS_KEY_PATH`` is not a key/value edit: it
    rewrites every ``hex (`` line, so it becomes ``plan_block_mesh_resolution``'s
    structural target, with the block count the path itself encodes. A
    ``remove`` carries no ``"value"``.
    """
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
    return target


def patch_mutation(request: CaseMutationRequest, *, owner_id: str) -> ResolvedMutation:
    """The semantic owner's answer for a ``clone_and_patch`` request, for
    every OpenFOAM-based plugin: pure, every parameter already addressed by
    its builder. ``owner_id`` is the calling plugin's id."""
    if request.mode != "clone_and_patch":
        raise ValueError(f"{owner_id} resolves clone_and_patch requests here, not {request.mode!r}")
    return ResolvedMutation(
        request=request,
        targets=tuple(_target_for_parameter(parameter) for parameter in request.parameters),
        expected_effects=tuple(
            f"{parameter.operation} {parameter.qualified_id!r} in {parameter.document}"
            for parameter in request.parameters
        ),
        semantic_owner_id=owner_id,
    )


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

    - ``"content"`` -- the document's exact bytes, supplied by the caller
      rather than assembled from a key/value edit.
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
    ``"remove"`` deletes it with ``missing_ok=True``.
    """
    del driver_context, execution_env
    case_root = Path(resolved.request.case_root)
    snapshot_root = Path(snapshot_root)
    rendered: list[RenderedFile] = []
    for document, edits in sorted(_document_edits(resolved).items()):
        content_edits = [edit for edit in edits if "content" in edit]
        if len(content_edits) > 1:
            raise ValueError(
                f"patch target {document!r} carries {len(content_edits)} "
                f"whole-document contents; a document's body is authored "
                f"once, by one target"
            )
        remaining_edits = [edit for edit in edits if "content" not in edit]

        source = case_root / document
        exists_before = source.is_file()

        if content_edits:
            # mode is only known when the document already existed; a freshly
            # authored one gets none, matching render_synthesis_case_files.
            body = content_edits[0]["content"]
            if isinstance(body, str):
                body = body.encode()
            before_digest = _digest_bytes(source.read_bytes()) if exists_before else None
            if content_edits[0].get("executable"):
                # a script (e.g. Allrun): fold exec bits onto the existing
                # mode, or 0o644 (this environment's default new-file mode).
                base_mode = (source.stat().st_mode & 0o7777) if exists_before else 0o644
                mode = base_mode | 0o111
            else:
                mode = (source.stat().st_mode & 0o7777) if exists_before else None
            snapshot_path = snapshot_root / document
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_bytes(body)
        elif not exists_before:
            raise ValueError(
                f"patch target {document!r} does not exist under {case_root}; "
                f"clone_and_patch edits a document that already exists"
            )
        else:
            before_digest = _digest_bytes(source.read_bytes())
            mode = source.stat().st_mode & 0o7777
            snapshot_path = _snapshot_copy(case_root, snapshot_root, document)

        hex_edits = [edit for edit in remaining_edits if "hex_cell_counts" in edit]
        dict_edits = [edit for edit in remaining_edits if "dict_operation" in edit]
        value_edits = [
            edit for edit in remaining_edits
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
            if operation == "remove":
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
        rendered.append(RenderedFile(
            path=document, content=snapshot_path.read_bytes(), mode=mode,
            exists_before=exists_before, before_digest=before_digest,
            renderer_id=renderer_id, format=FORMAT,
        ))
    return tuple(rendered)


def render_synthesis_case_files(
    resolved: Any,
    *,
    snapshot_root: Path,
    driver_context: Any,
    execution_env: Any | None = None,
    renderer_id: str,
) -> tuple[RenderedFile, ...]:
    """Render a ``synthesize`` resolution.

    A document may carry a ``"content"`` target (a whole document body,
    authored by the semantic owner -- this module only turns it into bytes)
    and/or an edit target (``"expanded_key_path"``/``"value"``), applied
    after the content target, if any, is decided.

    A ``"content"`` target marked ``"skip_if_present": True`` does not
    replace an already-present file, but any edit targets for that document
    still apply atop it. A document with only edit targets and no existing
    file is refused: there is nothing to fold them onto.
    """
    del driver_context, execution_env
    case_root = Path(resolved.request.case_root)
    snapshot_root = Path(snapshot_root)
    rendered: list[RenderedFile] = []
    for document, edits in sorted(_document_edits(resolved).items()):
        content_edits = [edit for edit in edits if "content" in edit]
        patch_edits = [edit for edit in edits if "content" not in edit]
        if len(content_edits) > 1:
            raise ValueError(
                f"synthesis target {document!r} carries {len(content_edits)} "
                f"whole-document contents; a document's body is authored "
                f"once, by one target"
            )
        content_edit = content_edits[0] if content_edits else None
        source = case_root / document
        file_exists = source.is_file()

        use_content = content_edit is not None and not (
            content_edit.get("skip_if_present") and file_exists
        )
        if use_content:
            body = content_edit["content"]
            if isinstance(body, str):
                body = body.encode()
            exists_before = file_exists
            before_digest = _digest_bytes(source.read_bytes()) if file_exists else None
            if content_edit.get("executable"):
                # same rule as render_patch_case_files's executable branch.
                base_mode = (source.stat().st_mode & 0o7777) if file_exists else 0o644
                mode = base_mode | 0o111
            else:
                mode = None
            snapshot_path = snapshot_root / document
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot_path.write_bytes(body)
        else:
            if not patch_edits:
                # The content target was skipped (already present) and
                # nothing else touches this document: nothing to render.
                continue
            if not file_exists:
                raise ValueError(
                    f"synthesis target {document!r} carries an edit but no "
                    f"content and no existing file to fold it onto"
                )
            exists_before = True
            before_digest = _digest_bytes(source.read_bytes())
            snapshot_path = _snapshot_copy(case_root, snapshot_root, document)
            mode = None

        for edit in patch_edits:
            key_path = tuple(edit["expanded_key_path"])
            scope = key_path[:-1] or None
            key = key_path[-1]
            # add_if_missing defaults False: a synthesis edit targets a key
            # its own just-authored template always declares (e.g.
            # deltaT/endTime in controlDict), unlike a patch's key.
            update_foam_entry(
                snapshot_path, key, edit["value"], scope=scope,
                add_if_missing=edit.get("add_if_missing", False),
            )

        rendered.append(RenderedFile(
            path=document, content=snapshot_path.read_bytes(), mode=mode,
            exists_before=exists_before, before_digest=before_digest,
            renderer_id=renderer_id, format=FORMAT,
        ))
    return tuple(rendered)
