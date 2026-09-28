"""Scans OpenFOAM C++ source for dictionary-read call sites (`.lookup`,
`.get<T>`, `subDict`, etc.) and reports drift against a plugin-supplied
catalogue. Heuristic (~80% accurate); output is for human review only.
"""

from __future__ import annotations

import re
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry


# ---------------------------------------------------------------------------
# Comment stripping  (the pattern rtst_scanner.py also uses)

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    # Mask with spaces (not delete) to keep line numbers and avoid concatenating tokens.
    def mask(match: re.Match[str]) -> str:
        return "".join(c if c in "\r\n" else " " for c in match.group())

    text = _BLOCK_COMMENT.sub(mask, text)
    text = _LINE_COMMENT.sub(mask, text)
    return text


# ---------------------------------------------------------------------------
# Patterns for dictionary key reads
#
# The string literal is always a double-quoted token without embedded quotes;
# arbitrary whitespace (including newlines) is allowed between the method
# name, the opening paren, and the first argument.

_STRING_LIT = r'"([^"]+)"'

# Methods that read a *key* from a dictionary.
_KEY_METHOD = (
    r"(?:"
    r"lookupOrDefault(?:\s*<[^>]+>)?"      # lookupOrDefault<T>( or lookupOrDefault(
    r"|lookup"                               # lookup(
    r"|getOrDefault(?:\s*<[^>]+>)?"         # getOrDefault<T>(
    r"|get(?:\s*<[^>]+>)"                   # get<T>(   (require type param to avoid false-positives on e.g. get())
    r"|found"                               # found(
    r"|readEntry"                           # readEntry(
    r")"
)

# Methods that open a *sub-dictionary*.
_SUBDICT_METHOD = r"(?:subDict|subOrEmptyDict|optionalSubDict)"

# readScalar/readLabel/readBool wrapping a .lookup("key")
_WRAP_FUNC = r"(?:readScalar|readLabel|readBool)"

# Three focused regexes rather than one combined (hard to maintain); each
# captures the string literal as the last group in the pattern.

_KEY_RE = re.compile(
    r"[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*"
    r"\s*\.\s*" + _KEY_METHOD + r"\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)

_WRAP_RE = re.compile(
    r"(?:" + _WRAP_FUNC + r")\s*\(\s*"
    r"[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*"
    r"\s*\.\s*lookup\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)

_SUB_RE = re.compile(
    r"[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*"
    r"\s*\.\s*(?P<meth>" + _SUBDICT_METHOD + r")\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Public dataclass

@dataclass(frozen=True)
class DictRead:
    kind: str       # "key" | "subdict"
    name: str       # the string literal
    source_file: Path
    line: int       # 1-based


# ---------------------------------------------------------------------------
# Scanner implementation

def _iter_src_files(src_root: Path) -> Iterable[Path]:
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".C", ".H"}:
            continue
        parts = path.parts
        if "lnInclude" in parts or "Make" in parts:
            continue
        # Skip *_Names.H headers — they contain enum identifiers, not dict keys.
        if path.name.endswith("_Names.H") or path.name.endswith("Names.H"):
            continue
        yield path


def _line_of(text: str, pos: int) -> int:
    """Return 1-based line number for character position *pos* in *text*."""
    return text.count("\n", 0, pos) + 1


def scan_dict_reads(src_root: Path) -> list[DictRead]:
    """Return all dictionary-read sites found under `src_root`, skipping
    `lnInclude/`, `Make/`, `*Names.H`, and comments. Heuristic (~80%
    accurate); for human review, not automated enforcement."""
    results: list[DictRead] = []

    for source in _iter_src_files(src_root):
        raw = source.read_text(encoding="utf-8", errors="replace")
        text = _strip_comments(raw)

        # Key reads
        for m in _KEY_RE.finditer(text):
            key = m.group(m.lastindex)   # last capture group = the string literal
            results.append(
                DictRead(
                    kind="key",
                    name=key,
                    source_file=source,
                    line=_line_of(text, m.start()),
                )
            )

        # Wrapped reads: readScalar/readLabel/readBool(recv.lookup("key"))
        for m in _WRAP_RE.finditer(text):
            key = m.group(m.lastindex)
            results.append(
                DictRead(
                    kind="key",
                    name=key,
                    source_file=source,
                    line=_line_of(text, m.start()),
                )
            )

        # Sub-dict opens
        for m in _SUB_RE.finditer(text):
            key = m.group(m.lastindex)
            results.append(
                DictRead(
                    kind="subdict",
                    name=key,
                    source_file=source,
                    line=_line_of(text, m.start()),
                )
            )

    return results


# ---------------------------------------------------------------------------
# Catalogue-side vocabulary, owned by core: re-exported so this module's own
# drift checks (and its tests) can keep using these names without pulling
# omnidriver.openfoam into core's strict_planning.
from omnidriver.core.contracts.catalogue_paths import (  # noqa: F401
    _WILDCARD_RE,
    CataloguePath,
    _as_paths,
    _parse_path,
    catalogued_paths,
    iter_catalogue_paths,
)


@dataclass(frozen=True)
class DictKeyStrictReport:
    """Allowlist-backed catalogue drift report used by strict planning.

    `unmatched_cxx_reads` is not "absent keys": the scanner can fail to match
    a C++ string literal to the catalogue for reasons other than a catalogue
    bug -- the key may belong to another dictionary file, to upstream
    OpenFOAM (e.g. `nNonOrthogonalCorrectors` from a `pimpleDict`), or to a
    string comparison rather than an actual dict read. Only a reviewed
    allowlist can tell those apart from a genuinely uncatalogued key, which is
    why the report subtracts it, and why `unused_allowlist` catches waivers
    whose underlying read has since disappeared.
    """

    status: str
    unmatched_cxx_reads: tuple[str, ...]
    stale_paths: tuple[str, ...]
    unmatched_subdicts: tuple[str, ...]
    unused_allowlist: tuple[str, ...]
    #: ``rtst_scanner.runtime_selection_report``'s answer; empty when the
    #: allowlist has no ``runtime_selection`` section.
    runtime_selection: dict[str, object] = field(default_factory=dict)

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "unmatched_cxx_reads": list(self.unmatched_cxx_reads),
            "stale_paths": list(self.stale_paths),
            "unmatched_subdicts": list(self.unmatched_subdicts),
            "unused_allowlist": list(self.unused_allowlist),
            **self.runtime_selection,
        }


IGNORED_FOAMFILE_KEYS: frozenset[str] = frozenset(
    {
        "version",
        "format",
        "class",
        "object",
        "location",
        "dimensions",
        "internalField",
        "boundaryField",
        "FoamFile",
        "note",
        "arch",
        "root",
        "case",
        "time",
        "path",
    }
)


def load_dict_key_allowlist(path: Path) -> dict[str, set[str]]:
    """Load the reviewed strict-scanner allowlist (JSON, so a plugin can own
    its exceptions without coupling this utility to that plugin)."""
    payload = json.loads(path.read_text())
    return {
        "unmatched_cxx_reads": set(payload.get("unmatched_cxx_reads", [])),
        "stale_paths": set(payload.get("stale_paths", [])),
        "unmatched_subdicts": set(payload.get("unmatched_subdicts", [])),
    }


def catalogued_names(entries: Iterable["DictEntry"]) -> set[str]:
    """Every name the catalogue knows anywhere: leaves of concrete and
    wildcard paths, plus every non-wildcard container segment.

    Shared, not reimplemented, by both `compute_dict_key_drift` (C++ reads)
    and `case_dict_keys.py` (case-file keys) -- a second, subtly different
    set is what produced a large false-positive rate before. Deliberately
    not `cat_leaves` (concrete-only), which is the correct, narrower set for
    `stale_paths`.
    """
    names: set[str] = set()
    for path in _as_paths(entries):
        names.add(path.leaf)
        for seg in path.parents:
            if not _WILDCARD_RE.fullmatch(seg):
                names.add(seg)
    return names


def compute_dict_key_drift(
    src_root: Path,
    *,
    entries: Iterable["DictEntry"],
) -> dict[str, set[str]]:
    """Compute approximate C++ reader drift against an explicit plugin catalogue."""
    reads = scan_dict_reads(src_root)
    cat_paths = list(iter_catalogue_paths(entries))

    key_reads: dict[str, list[DictRead]] = defaultdict(list)
    subdict_reads: dict[str, list[DictRead]] = defaultdict(list)
    for read in reads:
        if read.kind == "key":
            key_reads[read.name].append(read)
        else:
            subdict_reads[read.name].append(read)

    code_keys_set: set[str] = set(key_reads.keys())
    # Two different catalogue views for two different checks: cat_leaves is
    # concrete-only, since stale_paths must not expect the C++ to read a
    # literal "<name>"; catalogued_names also counts wildcard leaves and
    # parent segments, since unmatched_cxx_reads must recognize a real read
    # like "sigmaExtracellular" under ecgDomains.<name>.sigmaExtracellular.
    # Sharing one set between the two produces false positives.
    cat_leaves: set[str] = set()
    cat_parent_segs: set[str] = set()
    for path in cat_paths:
        if not (path.has_wildcard and path.dynamic_path):
            cat_leaves.add(path.leaf)
        for seg in path.parents:
            if not _WILDCARD_RE.fullmatch(seg):
                cat_parent_segs.add(seg)
    known = catalogued_names(cat_paths)

    unmatched_cxx_reads = {
        key
        for key in code_keys_set
        if key not in known and key not in IGNORED_FOAMFILE_KEYS
    }
    stale_paths = {
        path.driver_path
        for path in cat_paths
        if not (path.has_wildcard and path.dynamic_path)
        and path.leaf not in code_keys_set
    }
    unmatched_subdicts = {
        name
        for name in set(subdict_reads) | cat_parent_segs
        if (name in subdict_reads) != (name in cat_parent_segs)
    }

    return {
        "unmatched_cxx_reads": unmatched_cxx_reads,
        "stale_paths": stale_paths,
        "unmatched_subdicts": unmatched_subdicts,
    }


def strict_dict_key_report(
    src_root: Path,
    *,
    allowlist_path: Path,
    entries: Iterable["DictEntry"],
) -> DictKeyStrictReport:
    """Return the allowlist-backed strict scanner result, with the
    runtime-selection check when the allowlist carries its mapping."""
    entries = tuple(entries)
    drift = compute_dict_key_drift(src_root, entries=entries)
    allowlist = load_dict_key_allowlist(allowlist_path)
    selection_mapping = json.loads(Path(allowlist_path).read_text()).get("runtime_selection")
    runtime_selection: dict[str, object] = {}
    if selection_mapping is not None:
        from .rtst_scanner import runtime_selection_report

        runtime_selection = runtime_selection_report(
            src_root, entries=entries, mapping=selection_mapping,
        )

    unexpected: dict[str, set[str]] = {}
    unused: set[str] = set()
    for key in ("unmatched_cxx_reads", "stale_paths", "unmatched_subdicts"):
        unexpected[key] = drift[key] - allowlist[key]
        unused.update(f"{key}:{item}" for item in sorted(allowlist[key] - drift[key]))

    selection_failed = any(
        items for items in runtime_selection.values() if isinstance(items, list)
    )
    status = "ok" if not any(unexpected.values()) and not unused and not selection_failed else "failed"
    return DictKeyStrictReport(
        status=status,
        unmatched_cxx_reads=tuple(sorted(unexpected["unmatched_cxx_reads"])),
        stale_paths=tuple(sorted(unexpected["stale_paths"])),
        unmatched_subdicts=tuple(sorted(unexpected["unmatched_subdicts"])),
        unused_allowlist=tuple(sorted(unused)),
        runtime_selection=runtime_selection,
    )
