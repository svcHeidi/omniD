"""What OpenFOAM's own fatal message says about a case: the key a solver
could not find and the dictionary it looked in, or else the message itself.

Only a fatal OpenFOAM exited on counts: a warning, or a fatal printed inside
a warning, is followed by more output and no exit banner."""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .dict_keys_scanner import cached_scan, scan_cache_root

_MISSING = re.compile(
    r"""(?:Entry\s+'(?P<entry>[^']+)'\s+not\s+found|keyword\s+(?P<keyword>\S+)\s+is\s+undefined)"""
    r"""\s+in\s+dictionary\s+"(?P<dictionary>[^"]+)"""
)

# A message runs to the exit banner without crossing another "-->" line; a parallel run prefixes each line with its rank.
_RANK = r"(?:\[\d+\]\s*)?"
_FATAL = re.compile(
    rf"^{_RANK}--> FOAM FATAL (?:IO )?ERROR[^\n]*\n(?P<message>(?:(?!^{_RANK}-->).)*?)\n\s*{_RANK}FOAM (?:parallel run )?(?:exiting|aborting)",
    re.DOTALL | re.MULTILINE,
)
_RANK_PREFIX = re.compile(r"^\[\d+\]\s?", re.MULTILINE)
_FATAL_CHARACTERS = 600

REBUILD_HINT = (
    "the solver binary reads keys the scanned source does not; it was built from "
    "different source: rescan the repository it was built from"
)


def _file_and_scope(path: Path, stop: Path | None) -> tuple[Path, list[str]] | None:
    scope: list[str] = []
    while path != stop and path.parent != path and not path.is_file():
        scope.insert(0, path.name)
        path = path.parent
    return (path, scope) if path.is_file() else None


def _document_and_scope(dictionary: str, case_root: Path) -> tuple[str, list[str]]:
    """The case file a dictionary path names (relative to the case when inside it) and the sub-dictionaries below it."""
    path = Path(dictionary)
    found = _file_and_scope(path, None) if path.is_absolute() else None
    # A log read after its case moved names the old place; its tail still names this case's files.
    tails = path.parts[1:] if path.is_absolute() else path.parts
    for start in range(len(tails)):
        if found is not None:
            break
        found = _file_and_scope(case_root.joinpath(*tails[start:]), case_root)
    if found is None:
        return dictionary, []
    file, scope = found
    try:
        return file.resolve().relative_to(case_root.resolve()).as_posix(), scope
    except ValueError:
        return str(file), scope


def _missing_entry_diagnostics(message: str, case_root: Path, driver_context: Any) -> tuple[StrictDiagnostic, ...]:
    """The key and dictionary a fatal's ``message`` names and, for a document a
    provider's catalogue owns, whose supplied C++ source reads no such key, that
    the solver was built from other source."""
    match = _MISSING.search(message)
    if match is None:
        return ()
    key = match.group("entry") or match.group("keyword")
    document, scope = _document_and_scope(match.group("dictionary"), Path(case_root))
    where = f"{'.'.join(scope)} in {document}" if scope else document
    message = f"the solver stopped: {key} is missing from {where}; set it there."
    mapping = driver_context.stack.call("get_profile").cxx_mapping
    source = mapping.source_root(os.environ) if mapping is not None else None
    owned = PurePosixPath(document).name in driver_context.stack.call("get_owned_documents")
    if owned and source is not None and source.is_dir():
        scan = cached_scan(source, cache_root=scan_cache_root())
        if not any(read.key == key for read in scan.reads):
            message += f" {key} is read nowhere in the scanned source ({source}): {REBUILD_HINT}."
    return (diagnostic("error", "solver_entry_missing", message, source=document, field=key),)


def fatal_error_diagnostics(log_text: str, case_root: Path, driver_context: Any) -> tuple[StrictDiagnostic, ...]:
    """What the first fatal OpenFOAM exited on in ``log_text`` says: the missing
    entry when it is one, else the message itself."""
    match = _FATAL.search(log_text)
    if match is None:
        return ()
    message = _RANK_PREFIX.sub("", match.group("message"))
    found = _missing_entry_diagnostics(message, case_root, driver_context)
    if found:
        return found
    message = " ".join(message.split())[:_FATAL_CHARACTERS]
    return (diagnostic("error", "solver_fatal_error", f"the solver stopped with an OpenFOAM fatal error: {message}"),)
