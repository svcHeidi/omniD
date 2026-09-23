"""Shared, attempt-agnostic transaction primitives.

Phase 2 Task 12 (docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md):
extracted because two consumers now exist -- :mod:`omnidriver.core.
case_transaction` (the write channel's commit executor) and :mod:`omnidriver.
core.runtime.remediation_transaction` (agent-proposed configuration
transactions). Before this extraction, ``case_transaction.py`` already
imported ``_atomic_write_bytes``/``_fsync_directory`` **from**
``remediation_transaction.py`` -- a real, if backwards, coupling: the
generic write channel depended on the attempt-owning module, not the other
way around.

What is here is deliberately narrow: atomic-write-with-fsync primitives only.
Before-image capture/restore and directory-cleanup bookkeeping stay in
``case_transaction.py`` (only one real consumer -- the channel's own
before-images are inline-base64-in-the-journal, a different shape from
remediation's sha256-manifest-plus-backup-file scheme). Remediation's
manifest/backup/compare-and-swap machinery, which exists because of
**attempt ownership** the channel does not have, stays in
``remediation_transaction.py`` unchanged. Unifying either of those would mean
inventing a fake attempt for the channel, or discarding remediation's real
one -- exactly the mistake the refuted draft's Task 2 made (see this task's
own text in the plan).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, content: bytes, *, mode: int | None = None) -> None:
    """Replace ``path`` with ``content``, durably: write-tmp, fsync, rename,
    fsync the containing directory. Never leaves a half-written file at
    ``path`` itself -- a reader sees either the old content or the new,
    never a partial write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """``atomic_write_bytes`` of ``payload``, canonically indented JSON."""
    content = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    atomic_write_bytes(path, content)


def fsync_directory(path: Path) -> None:
    """Durably persist a directory's own entries (a rename inside it, an
    unlink) -- a bare file fsync says nothing about whether the directory
    entry pointing at it survives a crash."""
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
