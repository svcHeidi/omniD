"""Render case-write-channel mutations into OpenFOAM dictionary bytes.

The only place OpenFOAM dictionary syntax appears in the case-write channel
(``docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md``, Tasks 8
and 9). Two creation modes land here:

``clone_and_patch``  edits one or more keys in documents that already exist.
``synthesize``       authors documents from scratch, optionally folding a
                     later patch onto one of them into a single rendering
                     (the ``repeated_edits_to_one_file`` conformance case, in
                     its real setting -- see :func:`render_synthesis_case_files`).

Reuses :func:`mutators.update_foam_entry` for every key/value edit; this module
does not implement a second dictionary writer. **Corrected 2026-09-23 (Phase 3
Task 4):** a `clone_and_patch` edit is not always a key/value set -- a target
carrying ``"hex_cell_counts"`` (see :func:`utils.plan_block_mesh_resolution`)
is a structural rewrite of an existing document's ``hex (`` block
declarations instead, and :func:`render_patch_case_files` reuses
:func:`utils._rewrite_hex_block_lines` for it the same way it reuses
`update_foam_entry` for everything else -- one implementation of the ``hex (``
grammar, not a second one living beside this module's key/value path.

Every rendering happens against a copy
under ``snapshot_root`` -- the real case is read only to seed that copy (and,
for a patch, to discover what the edit's precondition set must cover), never
written to directly. Core reads the returned bytes and commits them through
the transaction channel (:mod:`omnidriver.core.case_transaction`).

Preconditions -- everything a rendering's correctness depends on staying
true -- are a separate concern from the bytes themselves, because
``render_case_files`` returns only ``RenderedFile`` objects per the
``CaseWriterCapability`` protocol. :func:`patch_preconditions` is the sibling
an orchestrator calls directly (cardiacCore's ``workflows.overrides``, Task 8)
to build the complete set: the document itself, every file it transitively
includes, the *absence* of any higher-priority ``#includeEtc`` candidate
that would change which file a later run selects (audit finding F2 -- this is
the entire reason F2 was sequenced before this task), and every environment
key that selection depended on (``WM_PROJECT_DIR``, ``FOAM_ETC`` and
siblings -- recorded, since F2, as ``environment`` preconditions rather than
discarded; corrected 2026-09-23, R3 finding 3, which found them bound to `_`
and dropped). Reuses :func:`effective_dictionary._inspect_source_closure` for
that walk rather than re-deriving it.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.case_write import Precondition, RenderedFile, _digest_bytes

from .effective_dictionary import _inspect_source_closure
from .mutators import ensure_foam_dict, remove_foam_dict, remove_foam_entry, update_foam_entry
from .utils import _rewrite_hex_block_lines

#: The one format this module renders. Declared truthfully by whichever
#: provider composes it in (``OpenFOAMEnvironmentPlugin.get_rendered_formats``)
#: -- ``_CaseWriterAdapter.render`` refuses a ``RenderedFile`` whose format its
#: returning provider did not declare, so this string must match exactly.
FORMAT = "openfoam_dictionary"


def _snapshot_copy(case_root: Path, snapshot_root: Path, relpath: str) -> Path:
    """Copy ``relpath`` from the real case into the snapshot, preserving mode.

    ``render_case_files`` must write nothing outside ``snapshot_root``; this
    is the one read of the real case a patch renderer performs, and it reads,
    never writes, ``case_root``.
    """
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


def render_patch_case_files(
    resolved: Any,
    *,
    snapshot_root: Path,
    driver_context: Any,
    execution_env: Any | None = None,
    renderer_id: str,
) -> tuple[RenderedFile, ...]:
    """Render a ``clone_and_patch`` resolution: one file per edited document.

    Two parameters landing in one document are folded into a single
    ``update_foam_entry`` pass over one snapshot copy, because
    ``CaseWritePlan`` refuses two ``RenderedFile``s claiming one path (the
    ``repeated_edits_to_one_file`` conformance case).

    **A target may instead carry ``"content"``** (Phase 3 Task 7,
    :func:`utils.plan_verbatim_content`) -- a whole document's exact bytes,
    supplied by the caller rather than assembled from a key/value edit. See
    the inline comment where it is applied, below, for the full reasoning;
    the short version is that this mirrors :func:`render_synthesis_case_files`'s
    own ``"content"`` target, widened to a mode whose document may already
    exist.

    **A target may instead carry ``"hex_cell_counts"``** (Phase 3 Task 4,
    :func:`utils.plan_block_mesh_resolution`) rather than
    ``"expanded_key_path"``/``"value"``: a structural rewrite of every
    ``hex (`` block declaration in the document, not a key/value edit.
    Applied via :func:`utils._rewrite_hex_block_lines` -- reused, the same
    grammar `replace_block_mesh_resolutions` still writes directly today --
    instead of ``update_foam_entry``, and validated against that target's
    own ``expected_blocks`` the same way that function always has: silently
    replacing the wrong number of blocks is exactly the failure this check
    exists to prevent. At most one such target per document is accepted;
    two would make "how many blocks changed" depend on application order,
    the same duplicate-slot reasoning ``CaseMutationRequest`` already applies
    to ``ParameterAssignment``\\ s.

    **A target may instead carry ``"dict_operation"``** (Phase 3 Task 6's
    completion, 2026-09-23) -- ``"ensure"`` with a ``"block_text"``, or
    ``"remove"`` -- a whole sub-dictionary inserted or deleted verbatim,
    rather than one key set to one value. Not a ``ParameterAssignment``: like
    the hex rewrite above, there is no single ``key_path`` a typed value sits
    at -- ``block_text`` is hand-authored OpenFOAM text a tutorial supplies
    (e.g. an ``ecgDomains`` block with several nested sub-dictionaries), and
    inventing a ``value_kind`` to carry that through core's vocabulary would
    be the same layering mistake the hex case's own docstring already
    rejects. Delegates to :func:`mutators.ensure_foam_dict`/
    :func:`mutators.remove_foam_dict` -- reused, not reimplemented, same as
    every other edit this function applies. Applied **before** the ordinary
    key/value edits below, not after: a real caller
    (``manufactured_bath_bidomain``'s ``ecgDomains`` block, inserted via this
    path and then immediately patched at ``ecgDomains.bodyECG.ecgSolver`` by
    an ordinary ``set`` in the same commit) depends on the block existing
    before a scoped key inside it can be found at all -- the reverse order
    would have the ``set`` fail against a scope that does not exist yet. A
    document whose ``ecgDomains`` block is being *removed* in the same
    commit never also sets a key inside it (the caller's own branch is
    exclusive on ``ecg_enabled``), so this fixed order never conflicts with
    the removal case either. ``remove`` is idempotent -- always applied with
    ``missing_ok=True`` -- because a `ParameterAssignment`-shaped removal
    asserts the document's *final* state (the block is gone), not that a
    deletion action occurred; a block already absent already satisfies that
    assertion.

    **A value edit's ``"operation"``** (same 2026-09-23 decision) selects
    which write `mutators.update_foam_entry`/`mutators.remove_foam_entry`
    performs, defaulting to ``"set"`` for a target built before the field
    existed:

    - ``"set"`` -- ``add_if_missing=False``. The key must already be there;
      a typo fails loudly. **Corrected 2026-09-23:** before this, every edit
      here was applied with ``add_if_missing=True`` regardless, which made a
      channel-routed ``set`` silently more permissive than the direct writer
      it replaces (`cardiacfoam.overrides.apply_entry_overrides`, which has
      never allowed a missing key). No currently-migrated tutorial's real
      template was missing any of its overridden keys, so tightening this
      changed no test's outcome -- confirmed by running the full suite
      after the change, not assumed.
    - ``"ensure"`` -- ``add_if_missing=True``, the typed counterpart of an
      upsert (e.g. a bath-boundary patch entry whose presence varies with
      which boundary variant a reused ``case_root`` was last written for).
    - ``"remove"`` -- :func:`mutators.remove_foam_entry`, not
      ``update_foam_entry`` at all, also with ``missing_ok=True`` for the
      same "final-state assertion, not an action" reasoning ``dict_operation``
      removal gives above.
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
            # **A target may instead carry ``"content"`` (Phase 3 Task 7)** --
            # a whole document's exact bytes, supplied by the caller rather
            # than composed from a key/value edit -- e.g. a whole
            # solver-variant template file, copied in verbatim rather than
            # patched key by key. Mirrors
            # `render_synthesis_case_files`'s own ``"content"`` target
            # (this module carries no cardiac vocabulary and does not author
            # that text, only turns it into bytes), widened to `clone_and_patch`
            # because the document here may or may not already exist under
            # `case_root` -- unlike every other patch target, which always
            # edits a document already there. `mode` is only known when the
            # document already existed; a freshly authored one gets none, the
            # same as synthesis.
            body = content_edits[0]["content"]
            if isinstance(body, str):
                body = body.encode()
            before_digest = _digest_bytes(source.read_bytes()) if exists_before else None
            if content_edits[0].get("executable"):
                # Phase 3 Task 10: a script (``Allrun``) rather than a
                # dictionary -- fold the execute bits onto whatever mode
                # the file already had (a reused case_root), or 0o755 for
                # one authored fresh (0o644, this environment's standard
                # 022-umask default for a new file, with the same bits
                # added) -- matching sweep.py's pre-migration
                # `write_text` + `chmod(mode | S_IEXEC|S_IXGRP|S_IXOTH)`.
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
            if edit["dict_operation"] == "ensure":
                ensure_foam_dict(
                    snapshot_path, edit["dict_name"], edit["block_text"], scope=scope,
                )
            elif edit["dict_operation"] == "remove":
                remove_foam_dict(
                    snapshot_path, edit["dict_name"], scope=scope, missing_ok=True,
                )
            else:
                raise ValueError(
                    f"patch target {document!r} declares dict_operation "
                    f"{edit['dict_operation']!r}; known operations are "
                    f"'ensure' and 'remove'"
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


def _case_relative(case_root: Path, path: Path) -> str:
    """A read dependency's precondition target: case-relative when it is
    under the case, the resolved absolute path otherwise (an ``etc`` file,
    typically). ``Precondition`` carries no case-relative constraint --
    unlike ``RenderedFile``/``ParameterAssignment``, a read dependency is
    legitimately outside the case -- and ``Path(case_root) / target`` in
    ``case_transaction._check_preconditions`` resolves an absolute ``target``
    to itself, so both forms are checked correctly at commit time.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(case_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def render_synthesis_case_files(
    resolved: Any,
    *,
    snapshot_root: Path,
    driver_context: Any,
    execution_env: Any | None = None,
    renderer_id: str,
) -> tuple[RenderedFile, ...]:
    """Render a ``synthesize`` resolution.

    Two kinds of target may land on one document, and both may be present at
    once -- this is the ``repeated_edits_to_one_file`` conformance case in
    its real setting, ``system/controlDict`` synthesized from a template and
    then patched with an explicit ``deltaT``/``endTime`` (characterized
    against the pre-migration ``build_and_launch``, which produced exactly
    this by writing the file and then calling ``update_control_dict`` on it
    a second time -- reproduced here as one rendering, not two writes):

    * a ``"content"`` target -- a whole document body, authored from scratch
      by the semantic owner (e.g. cardiacFoam's ``build_electro_properties``
      and siblings). This module carries no cardiac vocabulary and does not
      generate that text, only turns it into bytes.
    * an edit target (``"expanded_key_path"``/``"value"``, no ``"content"``)
      -- one key folded into the document's current body via
      ``update_foam_entry``, applied after the content target (if any) is
      decided.

    A ``"content"`` target marked ``"skip_if_present": True`` does not
    replace an already-present file (``mesh_provisioning.provision_mesh``
    never overwrites a hand-authored ``blockMeshDict``, and a resolution
    that always proposes one must not force it back through the channel
    where the real case already has one) -- but any edit targets for that
    same document still apply, atop the existing file, exactly as they would
    atop freshly authored content. A document with only edit targets and no
    already-existing file is refused: there is nothing to fold them onto.
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
                # Phase 3 Task 10: same rule as render_patch_case_files's
                # own "executable" content target -- a synthesized script
                # (``Allrun``) gets the execute bits folded onto whatever
                # mode a reused case_root's file already had, or 0o755 for
                # one authored fresh.
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
            # Unlike a patch's declared-but-possibly-absent key (Task 8,
            # `render_patch_case_files`), a synthesis edit targets a key its
            # own just-authored template always declares (`deltaT`/`endTime`
            # in `controlDict`) -- `add_if_missing` defaults False here,
            # matching the pre-migration `update_control_dict`'s own
            # `update_foam_entry(path, key, value)` call exactly. Requesting
            # it anyway with no scope is refused by the structured-editor
            # tier before it even looks for the key (every template's
            # FoamFile header's `/*...*/` banner routes it there), for a key
            # that would have been found regardless.
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


def _environment_preconditions(
    keys: tuple[str, ...], environment: Mapping[str, str],
) -> tuple[Precondition, ...]:
    """One ``environment`` precondition per key the resolution depended on
    (R3 finding 3, 2026-09-23).

    A key present at planning time is recorded as a value precondition
    (``digest`` of its value, ``must_be_absent=False``); a key absent at
    planning time is recorded as an absence precondition (``digest=None``,
    ``must_be_absent=True``) rather than skipped. Skipping it would lose the
    dependency entirely: an absent ``FOAM_CONFIG_ETC`` (say) can change which
    file ``findEtcFile`` selects exactly as much as a changed one can (the
    same "absence is a dependency" principle audit finding F2 established for
    include candidates -- a candidate that does not exist yet is still part
    of what the resolution depends on staying true).
    """
    preconditions: list[Precondition] = []
    for key in sorted(set(keys)):
        value = environment.get(key)
        if value is None:
            preconditions.append(Precondition(
                kind="environment", target=key, digest=None, must_be_absent=True,
            ))
        else:
            preconditions.append(Precondition(
                kind="environment", target=key, digest=_digest_bytes(value.encode()),
                must_be_absent=False,
            ))
    return tuple(preconditions)


def patch_preconditions(
    resolved: Any,
    *,
    case_root: Path,
    execution_env: Mapping[str, str] | None = None,
) -> tuple[Precondition, ...]:
    """Every file -- and every environment value -- a patch's rendering
    depends on, as preconditions.

    Reuses ``effective_dictionary._inspect_source_closure`` for the include
    set: after audit finding F2 it follows the real ``findEtcFile`` chain, and
    the *absent* higher-priority candidates it reports become ``absence``
    preconditions -- a file appearing at one of them changes which file the
    next run reads, which is exactly why F2 was sequenced before this task.

    The closure also reports the environment keys resolution actually
    consulted (``WM_PROJECT_DIR``, ``FOAM_ETC`` and siblings, recorded since
    audit finding F2 precisely so this could be done) -- these become
    ``environment`` preconditions (R3 finding 3, 2026-09-23) rather than
    being bound to ``_`` and discarded: a changed ``WM_PROJECT_DIR`` between
    planning and commit is exactly the kind of drift a patch that reads
    ``#includeEtc`` needs to notice, and until now it could not.
    """
    case_root = Path(case_root)
    environment: Mapping[str, str] = (
        dict(execution_env) if execution_env is not None else dict(os.environ)
    )
    documents = sorted({str(target["document"]) for target in resolved.targets})
    preconditions: list[Precondition] = []
    seen_files: set[str] = set()
    seen_absent: set[str] = set()
    seen_env_keys: set[str] = set()
    for document in documents:
        dictionary = case_root / document
        if not dictionary.is_file():
            continue
        inspected, absent_optional, environment_keys, _error = _inspect_source_closure(
            dictionary, environment,
        )
        dictionary_resolved = dictionary.resolve()
        for path in inspected:
            target = _case_relative(case_root, path)
            if target in seen_files:
                continue
            seen_files.add(target)
            kind = "file" if path.resolve() == dictionary_resolved else "include"
            preconditions.append(Precondition(
                kind=kind, target=target, digest=_digest_bytes(path.read_bytes()),
                must_be_absent=False,
            ))
        for path in absent_optional:
            target = _case_relative(case_root, path)
            if target in seen_absent:
                continue
            seen_absent.add(target)
            preconditions.append(Precondition(
                kind="absence", target=target, digest=None, must_be_absent=True,
            ))
        new_env_keys = tuple(key for key in environment_keys if key not in seen_env_keys)
        seen_env_keys.update(new_env_keys)
        preconditions.extend(_environment_preconditions(new_env_keys, environment))
    return tuple(preconditions)
