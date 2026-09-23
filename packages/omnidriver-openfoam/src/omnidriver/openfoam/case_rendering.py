"""Render case-write-channel mutations into OpenFOAM dictionary bytes.

The only place OpenFOAM dictionary syntax appears in the case-write channel
(``docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md``, Tasks 8
and 9). Two creation modes land here:

``clone_and_patch``  edits one or more keys in documents that already exist.
``synthesize``       authors documents from scratch, optionally folding a
                     later patch onto one of them into a single rendering
                     (the ``repeated_edits_to_one_file`` conformance case, in
                     its real setting -- see :func:`render_synthesis_case_files`).

Reuses :func:`mutators.update_foam_entry` for every edit; this module does not
implement a second dictionary writer. Every rendering happens against a copy
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
from .mutators import update_foam_entry

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
    """
    del driver_context, execution_env
    case_root = Path(resolved.request.case_root)
    snapshot_root = Path(snapshot_root)
    rendered: list[RenderedFile] = []
    for document, edits in sorted(_document_edits(resolved).items()):
        source = case_root / document
        exists_before = source.is_file()
        if not exists_before:
            raise ValueError(
                f"patch target {document!r} does not exist under {case_root}; "
                f"clone_and_patch edits a document that already exists"
            )
        before_digest = _digest_bytes(source.read_bytes())
        mode = source.stat().st_mode & 0o7777
        snapshot_path = _snapshot_copy(case_root, snapshot_root, document)
        for edit in edits:
            key_path = tuple(edit["expanded_key_path"])
            scope = key_path[:-1] or None
            key = key_path[-1]
            update_foam_entry(
                snapshot_path, key, edit["value"], scope=scope, add_if_missing=True,
            )
        rendered.append(RenderedFile(
            path=document, content=snapshot_path.read_bytes(), mode=mode,
            exists_before=True, before_digest=before_digest,
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
            path=document, content=snapshot_path.read_bytes(), mode=None,
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
