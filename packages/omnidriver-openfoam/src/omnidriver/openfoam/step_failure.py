"""What OpenFOAM's own fatal message says about a case: the key a solver
could not find, and the dictionary it looked in."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .dict_keys_scanner import cached_scan, scan_cache_root

_MISSING = re.compile(
    r"""(?:Entry\s+'(?P<entry>[^']+)'\s+not\s+found|keyword\s+(?P<keyword>\S+)\s+is\s+undefined)"""
    r"""\s+in\s+dictionary\s+"(?P<dictionary>[^"]+)"""
)

REBUILD_HINT = (
    "the solver binary reads keys the scanned source does not; it was built from "
    "different source: rescan the repository it was built from"
)


def _document_and_scope(dictionary: str, case_root: Path) -> tuple[str, list[str]]:
    """The case file a dictionary path names, relative to the case when it
    lies in it, and the sub-dictionaries below it."""
    scope: list[str] = []
    path = Path(dictionary)
    if not path.is_absolute():
        path = case_root / path
    while path.parent != path and not path.is_file():
        scope.insert(0, path.name)
        path = path.parent
    if not path.is_file():
        return dictionary, []
    try:
        return path.resolve().relative_to(case_root.resolve()).as_posix(), scope
    except ValueError:
        return str(path), scope


def missing_entry_diagnostics(log_text: str, case_root: Path, driver_context: Any) -> tuple[StrictDiagnostic, ...]:
    """The key and dictionary of the first missing-entry fatal in ``log_text``
    and, when a provider's C++ source is supplied and reads no such key, that
    the solver was built from other source."""
    match = _MISSING.search(log_text)
    if match is None:
        return ()
    key = match.group("entry") or match.group("keyword")
    document, scope = _document_and_scope(match.group("dictionary"), Path(case_root))
    where = f"{'.'.join(scope)} in {document}" if scope else document
    message = f"the solver stopped: {key} is missing from {where}; set it there."
    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    source = mapping.source_root(os.environ) if mapping is not None else None
    if source is not None and source.is_dir():
        scan = cached_scan(source, cache_root=scan_cache_root())
        if not any(read.key == key for read in scan.reads):
            message += f" {key} is read nowhere in the scanned source ({source}): {REBUILD_HINT}."
    return (diagnostic("error", "solver_entry_missing", message, source=document, field=key),)
