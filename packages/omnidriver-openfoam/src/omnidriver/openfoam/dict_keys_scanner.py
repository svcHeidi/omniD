"""Scanner for OpenFOAM dictionary-read call sites in C++ source.

For each `.C` / `.H` file under a given `src_root` (skipping `lnInclude/`,
`Make/`, and `*_Names.H` files), this module detects patterns of the form:

    <receiver>.lookup("key")
    <receiver>.lookupOrDefault<T>("key", default)
    <receiver>.get<T>("key")
    <receiver>.getOrDefault<T>("key", default)
    <receiver>.found("key")
    <receiver>.readEntry("key", out)
    <receiver>.subDict("name")
    <receiver>.subOrEmptyDict("name")
    <receiver>.optionalSubDict("name")
    readScalar(<receiver>.lookup("key"))
    readLabel(<receiver>.lookup("key"))
    readBool(<receiver>.lookup("key"))

Returns a flat list of `DictRead` records.  Sub-dict opens are flagged with
``kind="subdict"``; all other patterns use ``kind="key"``.

Comments are stripped before scanning so commented-out code is never matched.

Catalogue-side helpers receive an explicit plugin catalogue and parse each
entry's `driver_path` into a structured form for comparison against the
scanner output. This module deliberately has no default solver catalogue or
allowlist: both are plugin-owned provenance inputs.

Accuracy is ~80%; false positives/negatives are expected.  The output is for
human review only.
"""

from __future__ import annotations

import re
import json
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry


# ---------------------------------------------------------------------------
# Comment stripping

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    # Preserve offsets/lines so a source reference points to the original
    # file, and a comment cannot concatenate two otherwise separate tokens.
    def mask(match: re.Match[str]) -> str:
        return "".join(c if c in "\r\n" else " " for c in match.group())

    text = _BLOCK_COMMENT.sub(mask, text)
    text = _LINE_COMMENT.sub(mask, text)
    return text


# ---------------------------------------------------------------------------
# Patterns for dictionary key reads
#
# Strategy: focused regexes with named groups.  The receiver is captured to
# recover the read's sub-dictionary scope (``DictRead.scope``).
#
# The string literal is always a double-quoted token without embedded quotes.
# We allow arbitrary whitespace (including newlines) between the method name,
# the opening paren, and the first argument.

_STRING_LIT = r'"(?P<name>[^"]+)"'

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

# A receiver is a dotted name optionally followed by chained sub-dictionary
# opens, e.g. ``dict.subDict("inner")`` in
# ``dict.subDict("inner").getOrDefault<vector>(...)``. The chained
# opens are part of the read's scope, so they are captured, not skipped.
_SUBDICT_CALL = r"\s*\.\s*" + _SUBDICT_METHOD + r"\s*\(\s*[^()]*?\s*\)"
_DOTTED = r"[A-Za-z_]\w*(?:\s*\.\s*[A-Za-z_]\w*)*"
_RECEIVER = r"(?P<base>" + _DOTTED + r")(?P<chain>(?:" + _SUBDICT_CALL + r")*)"

_KEY_RE = re.compile(
    _RECEIVER + r"\s*\.\s*(?P<meth>" + _KEY_METHOD + r")\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)

_WRAP_RE = re.compile(
    r"(?:" + _WRAP_FUNC + r")\s*\(\s*"
    + _RECEIVER + r"\s*\.\s*(?P<meth>lookup)\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)

_SUB_RE = re.compile(
    _RECEIVER + r"\s*\.\s*(?P<meth>" + _SUBDICT_METHOD + r")\s*\(\s*" + _STRING_LIT,
    re.DOTALL,
)

# ``dictionary& name = <receiver>.subDict(arg)`` or the constructor form
# ``dictionary& name(<receiver>.subDict(arg))``: binds a local name to a scope.
_BIND_RE = re.compile(
    r"\bdictionary\s*&?\s*(?P<var>[A-Za-z_]\w*)\s*(?:=|\()\s*"
    r"(?P<base>" + _DOTTED + r")(?P<chain>(?:" + _SUBDICT_CALL + r")+)",
    re.DOTALL,
)

_CHAIN_ARG_RE = re.compile(r"\.\s*" + _SUBDICT_METHOD + r"\s*\(\s*(?P<arg>[^()]*?)\s*\)")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")


# ---------------------------------------------------------------------------
# Public dataclass

@dataclass(frozen=True)
class DictRead:
    kind: str       # "key" | "subdict"
    name: str       # the string literal
    source_file: Path
    line: int       # 1-based
    # Enclosing sub-dictionary names, outermost first. A sub-dictionary opened
    # with a runtime name (``subDict(blockName)``) appears as ``<blockName>``, the
    # same placeholder shape catalogue paths use. Resolved per file from local
    # ``dictionary&`` bindings; a read through a function parameter or an
    # unbound name gets ``()``, meaning "not recovered", not "top level".
    scope: tuple[str, ...] = ()
    method: str = ""  # e.g. "getOrDefault", "subDict" (template argument dropped)
    # Match start in the comment-masked source. Offsets are preserved by
    # ``_strip_comments`` and disambiguate repeated same-name reads on a line.
    offset: int = -1


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


def _chain_segments(chain: str) -> tuple[str, ...]:
    segments = []
    for match in _CHAIN_ARG_RE.finditer(chain):
        arg = match.group("arg")
        if len(arg) >= 2 and arg[0] == arg[-1] == '"':
            segments.append(arg[1:-1])
        elif _IDENTIFIER_RE.fullmatch(arg):
            segments.append(f"<{arg}>")
        else:
            segments.append("<name>")
    return tuple(segments)


def _block_scope_resolver(text: str):
    """Return the lexical brace path at a source offset.

    This is deliberately a small C++ lexer, not a parser. Braces inside quoted
    string/character literals are ignored; each real opening brace receives a
    stable id so a binding is visible only inside its declaring block and
    descendants.
    """
    offsets = [0]
    paths: list[tuple[int, ...]] = [()]
    stack: list[int] = []
    next_block = 0
    quote: str | None = None
    escaped = False

    for index, char in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            next_block += 1
            stack.append(next_block)
            offsets.append(index + 1)
            paths.append(tuple(stack))
        elif char == "}" and stack:
            stack.pop()
            offsets.append(index + 1)
            paths.append(tuple(stack))

    def block_scope(pos: int) -> tuple[int, ...]:
        return paths[bisect_right(offsets, pos) - 1]

    return block_scope


def _scope_resolver(text: str):
    """Return ``scope(base, chain, pos)`` using bindings made before ``pos``.

    Bindings are matched by name and lexical C++ brace scope. The latest
    earlier binding visible from the read site wins.
    """
    block_scope = _block_scope_resolver(text)
    bindings: list[tuple[int, str, tuple[str, ...], tuple[int, ...]]] = []

    def scope(base: str, chain: str, pos: int) -> tuple[str, ...]:
        name = re.sub(r"\s+", "", base)
        outer: tuple[str, ...] = ()
        current_block = block_scope(pos)
        for bound_at, var, bound_scope, bound_block in reversed(bindings):
            visible = bound_block == current_block[:len(bound_block)]
            if bound_at < pos and var == name and visible:
                outer = bound_scope
                break
        return outer + _chain_segments(chain)

    for m in _BIND_RE.finditer(text):
        bindings.append((
            m.start(),
            m.group("var"),
            scope(m.group("base"), m.group("chain"), m.start()),
            block_scope(m.start()),
        ))
    return scope


def _method_name(raw: str) -> str:
    return raw.split("<", 1)[0].strip()


def _read_matches(text: str):
    """Yield ``(kind, match)`` for every read site in comment-stripped *text*."""
    for m in _KEY_RE.finditer(text):
        yield "key", m
    for m in _WRAP_RE.finditer(text):
        yield "key", m
    for m in _SUB_RE.finditer(text):
        yield "subdict", m


def scan_dict_reads(src_root: Path) -> list[DictRead]:
    """Return all dictionary-read sites found under *src_root*.

    Files in ``lnInclude/``, ``Make/``, and ``*Names.H`` are skipped.
    Comments are stripped before scanning.
    """
    results: list[DictRead] = []

    for source in _iter_src_files(src_root):
        raw = source.read_text(encoding="utf-8", errors="replace")
        text = _strip_comments(raw)
        scope = _scope_resolver(text)
        # One record per string literal: a chained open such as
        # a.subDict("x").get<T>("k") is also found on its own by _SUB_RE.
        seen: set[tuple[str, int]] = set()

        for kind, m in _read_matches(text):
            for segment in _CHAIN_ARG_RE.finditer(m.group("chain")):
                arg = segment.group("arg")
                offset = m.start("chain") + segment.start("arg")
                if len(arg) >= 2 and arg[0] == arg[-1] == '"' and ("subdict", offset) not in seen:
                    seen.add(("subdict", offset))
                    results.append(
                        DictRead(
                            kind="subdict",
                            name=arg[1:-1],
                            source_file=source,
                            line=_line_of(text, m.start()),
                            scope=scope(m.group("base"), m.group("chain")[: segment.start()], m.start()),
                            method=_method_name(segment.group().split("(", 1)[0].lstrip(".")),
                            offset=m.start(),
                        )
                    )
            literal_at = m.start("name") - 1
            if (kind, literal_at) in seen:
                continue
            seen.add((kind, literal_at))
            results.append(
                DictRead(
                    kind=kind,
                    name=m.group("name"),
                    source_file=source,
                    line=_line_of(text, m.start()),
                    scope=scope(m.group("base"), m.group("chain"), m.start()),
                    method=_method_name(m.group("meth")),
                    offset=m.start(),
                )
            )

    return results


_DEFAULT_METHODS = frozenset({"lookupOrDefault", "getOrDefault"})
_CLOSERS = {")": "(", "]": "[", "}": "{"}


def _default_expression(text: str, start: int) -> str | None:
    """Read one C++ argument without interpreting its expression."""
    stack: list[str] = []
    quote: str | None = None
    escaped = False

    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in _CLOSERS:
            if not stack:
                return text[start:index].strip()
            if stack[-1] != _CLOSERS[char]:
                return None
            stack.pop()
        elif char == "," and not stack:
            return text[start:index].strip()
    return None


def dict_read_default(read: DictRead) -> str | None:
    """Return the C++ default expression of an ``*OrDefault`` read, verbatim.

    The text is the source argument (``vector(0.30, 0.05, 0.05)``,
    ``defaultValue``), not an evaluated value: a named variable or
    computed expression still needs a human or the source to interpret it.
    Returns ``None`` for reads without a default.
    """
    if read.method not in _DEFAULT_METHODS:
        return None
    text = _strip_comments(read.source_file.read_text(encoding="utf-8", errors="replace"))
    for kind, m in _read_matches(text):
        same_site = read.offset >= 0 and m.start() == read.offset
        line_site = (
            read.offset < 0
            and m.group("name") == read.name
            and _line_of(text, m.start()) == read.line
        )
        if kind != read.kind or not (same_site or line_site):
            continue
        pos = m.end("name") + 1  # past the closing quote
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text) or text[pos] != ",":
            return None
        return _default_expression(text, pos + 1)
    return None


# ---------------------------------------------------------------------------
# Catalogue-side vocabulary -- owned by core, re-exported here.
#
# These helpers parse ``DictEntry.driver_path`` and are re-exported for the
# adapter's drift checks.
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
    """Allowlist-backed comparison of C++ reads and catalogue entries.

    ``unmatched_cxx_reads`` contains scanned literals not represented by the
    catalogue or allowlist. ``unused_allowlist`` identifies exceptions with no
    corresponding scanned read.
    """

    status: str
    unmatched_cxx_reads: tuple[str, ...]
    stale_paths: tuple[str, ...]
    unmatched_subdicts: tuple[str, ...]
    unused_allowlist: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "unmatched_cxx_reads": list(self.unmatched_cxx_reads),
            "stale_paths": list(self.stale_paths),
            "unmatched_subdicts": list(self.unmatched_subdicts),
            "unused_allowlist": list(self.unused_allowlist),
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
    """Load the reviewed strict-scanner allowlist.

    The file is intentionally JSON so a plugin can review and distribute its
    own scanner exceptions without coupling this core utility to that plugin.
    """
    payload = json.loads(path.read_text())
    return {
        "unmatched_cxx_reads": set(payload.get("unmatched_cxx_reads", [])),
        "stale_paths": set(payload.get("stale_paths", [])),
        "unmatched_subdicts": set(payload.get("unmatched_subdicts", [])),
    }



def catalogued_names(entries: Iterable["DictEntry"]) -> set[str]:
    """Every name the catalogue knows anywhere, as a flat set.

    Leaves of concrete AND wildcard paths, plus every non-wildcard container
    segment. This is the "does the catalogue know this name?" set, shared by
    both drift directions:

      * :func:`compute_dict_key_drift` -- C++ reads with no catalogue match
      * ``core/specs/case_dict_keys.py`` -- case-file keys with no match

    This differs from the concrete-only leaf set used for ``stale_paths``.
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
    # Stale-path checks use concrete leaves; unmatched-read checks also need
    # wildcard leaves and non-wildcard container names.
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
    """Return the allowlist-backed strict scanner result."""
    drift = compute_dict_key_drift(src_root, entries=entries)
    allowlist = load_dict_key_allowlist(allowlist_path)

    unexpected: dict[str, set[str]] = {}
    unused: set[str] = set()
    for key in ("unmatched_cxx_reads", "stale_paths", "unmatched_subdicts"):
        unexpected[key] = drift[key] - allowlist[key]
        unused.update(f"{key}:{item}" for item in sorted(allowlist[key] - drift[key]))

    status = "ok" if not any(unexpected.values()) and not unused else "failed"
    return DictKeyStrictReport(
        status=status,
        unmatched_cxx_reads=tuple(sorted(unexpected["unmatched_cxx_reads"])),
        stale_paths=tuple(sorted(unexpected["stale_paths"])),
        unmatched_subdicts=tuple(sorted(unexpected["unmatched_subdicts"])),
        unused_allowlist=tuple(sorted(unused)),
    )
