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
includes, and the *absence* of any higher-priority ``#includeEtc`` candidate
that would change which file a later run selects (audit finding F2 -- this is
the entire reason F2 was sequenced before this task). Reuses
:func:`effective_dictionary._inspect_source_closure` for that walk rather than
re-deriving it.
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


def patch_preconditions(
    resolved: Any,
    *,
    case_root: Path,
    execution_env: Mapping[str, str] | None = None,
) -> tuple[Precondition, ...]:
    """Every file a patch's rendering depends on, as preconditions.

    Reuses ``effective_dictionary._inspect_source_closure`` for the include
    set: after audit finding F2 it follows the real ``findEtcFile`` chain, and
    the *absent* higher-priority candidates it reports become ``absence``
    preconditions -- a file appearing at one of them changes which file the
    next run reads, which is exactly why F2 was sequenced before this task.
    """
    case_root = Path(case_root)
    environment: Mapping[str, str] = (
        dict(execution_env) if execution_env is not None else dict(os.environ)
    )
    documents = sorted({str(target["document"]) for target in resolved.targets})
    preconditions: list[Precondition] = []
    seen_files: set[str] = set()
    seen_absent: set[str] = set()
    for document in documents:
        dictionary = case_root / document
        if not dictionary.is_file():
            continue
        inspected, absent_optional, _keys, _error = _inspect_source_closure(
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
    return tuple(preconditions)
