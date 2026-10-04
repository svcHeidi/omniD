from __future__ import annotations

import shutil
import sys
from pathlib import Path

from .run_document_exec import ALLOWED_RUNS_ROOT_ENV, RUN_DOCUMENT_FILENAME
from .sweep_manifest import SWEEP_MANIFEST_FILENAME
from .workflow_orchestrator import STATE_FILENAME

#: Deliberately distinct from
#: ``runtime_records.CORE_RUNTIME_RECORDS.generated_case_markers``: that set
#: checks a case root for run-touched markers; this one checks an
#: ``output_dir`` (a sweep root, for sweeps) for what ``--fresh`` may safely
#: delete.
_OMNIDRIVER_MARKER_NAMES = (STATE_FILENAME, SWEEP_MANIFEST_FILENAME, RUN_DOCUMENT_FILENAME)


def _has_omnidriver_marker(output_dir: Path) -> bool:
    """Whether ``output_dir`` itself holds a marker: one in a subdirectory says nothing about the rest of the tree."""
    return any((output_dir / name).exists() for name in _OMNIDRIVER_MARKER_NAMES)


def check_fresh_deletion_allowed(output_dir: Path, *, allowed_root: Path | None) -> str | None:
    """Return an error message if deleting output_dir would be unsafe, else None.

    output_dir need not exist -- a nonexistent directory always passes (there
    is nothing to lose).
    """
    resolved = output_dir.resolve()
    if resolved.parent == resolved:
        return f"--fresh refuses to delete the filesystem root ({resolved})."
    if resolved == Path.home().resolve():
        return f"--fresh refuses to delete the home directory ({resolved})."
    depth = len(resolved.parts) - 1
    if depth < 3:
        return (
            f"--fresh refuses to delete {resolved}: fewer than 3 path segments "
            "beneath the filesystem root (too shallow to be a case/sweep output "
            "directory)."
        )
    if allowed_root is not None and not resolved.is_relative_to(allowed_root):
        return (
            f"--fresh refuses to delete {resolved}: outside "
            f"{ALLOWED_RUNS_ROOT_ENV} ({allowed_root})."
        )
    if resolved.exists() and not _has_omnidriver_marker(resolved):
        return (
            f"--fresh refuses to delete {resolved}: directory exists but contains "
            "no recognizable omnidriver artifact (workflow_state.json, "
            "sweep_manifest.json, or run_document.json) at its top level. Check "
            "--output-dir for a typo."
        )
    return None


def ensure_fresh_output_dir(
    output_dir: Path,
    *,
    fresh: bool,
    allowed_root: Path | None = None,
    preserve_names: frozenset[str] = frozenset(),
) -> str | None:
    """Delete output_dir when fresh=True and the safety guards allow it.

    Returns an error message (leaving output_dir untouched) if a guard
    refuses; returns None on success, including the fresh=False no-op and the
    "didn't exist" no-op. Prints the resolved path to stderr before deleting
    it -- the only audit trail, since there is no interactive prompt. Stderr
    (not stdout) so the CLI's stdout stays pure JSON.
    """
    if not fresh:
        return None
    error = check_fresh_deletion_allowed(output_dir, allowed_root=allowed_root)
    if error is not None:
        return error
    resolved = output_dir.resolve()
    if resolved.exists():
        print(f"--fresh: deleting {resolved}", file=sys.stderr)
        if preserve_names:
            for child in resolved.iterdir():
                if child.name in preserve_names:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        else:
            shutil.rmtree(resolved)
    return None
