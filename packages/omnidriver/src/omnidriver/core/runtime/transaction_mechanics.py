"""Atomic write-with-fsync primitives for the case transaction."""
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
