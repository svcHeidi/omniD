from __future__ import annotations

import difflib
import re
import warnings
from pathlib import Path
from typing import Any

from foamlib import Dimensioned, FoamFile

ScopeArg = str | list[str] | tuple[str, ...] | None

_TRUE_TOKENS = {"yes", "true", "on"}
_FALSE_TOKENS = {"no", "false", "off"}


def _normalize_scope(scope: ScopeArg) -> tuple[str, ...]:
    if scope is None:
        return ()
    if isinstance(scope, str):
        stripped = scope.strip()
        if not stripped:
            raise ValueError("scope cannot be an empty string")
        return (stripped,)
    parts = tuple(str(item).strip() for item in scope)
    if not parts or any(not part for part in parts):
        raise ValueError("scope must contain one or more non-empty names")
    return parts


def coerce_value(value: Any) -> Any:
    """Convert an omnidriver override value into a type foamlib will store.

    Override values arrive as strings, but foamlib (confirmed against 1.7.5)
    is type-strict on write and refuses a ``str`` that would read back as
    something else -- a dimensioned literal, a bare vector/list, or a bare
    multi-word scheme spec (e.g. ``"Gauss linear"``) that ``FoamFile.loads``
    parses into a token tuple rather than a single value.

    Everything reaching this point that is not already int/float/bool is
    attempted via ``FoamFile.loads``, foamlib's own deserializer, so its
    grammar decides the type rather than a hand-rolled parser. A token that
    fails to parse, or parses back to a plain ``str``, is returned unchanged.
    """
    if not isinstance(value, str):
        return value

    token = value.strip()
    lowered = token.lower()
    if lowered in _TRUE_TOKENS:
        return True
    if lowered in _FALSE_TOKENS:
        return False

    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass

    try:
        parsed = FoamFile.loads(token)
    except Exception:
        return token
    if not isinstance(parsed, str):
        return parsed

    return token


def _dimensioned_component_count(value: Dimensioned) -> int:
    """1 for a dimensioned scalar; ``len(...)`` for a vector/tensor/symmTensor (a numpy array)."""
    raw = value.value
    return len(raw) if hasattr(raw, "__len__") else 1


_ENTRY_SEPARATOR_RE = re.compile(r'(?<![\w"])([A-Za-z_]\w*)( )([^\s{};"][^{};]*;)')


def _reformat_separators(line: str) -> str:
    """Widen ``key value;`` to ``key    value;`` (tier 1's four-space form); the lookbehind avoids firing inside a quoted string."""

    def repl(match: re.Match[str]) -> str:
        key, _space, rest = match.groups()
        return f"{key}    {rest}"

    return _ENTRY_SEPARATOR_RE.sub(repl, line)


def normalize_output(before: str, after: str) -> str:
    """Reshape foamlib's write into the byte form the line-based tier emits.

    foamlib (confirmed against 1.7.5) writes ``k 250;`` (one space) and
    inserts a blank line before the edited entry and at end-of-file; tier 1
    writes ``k    250;`` and inserts nothing. A whole-file heuristic scan
    would also rewrite lines foamlib never touched (e.g. an existing
    two-space entry), so this diffs ``before`` against ``after`` and only
    reformats separators on, and drops purely-inserted blank lines from,
    the lines the write actually changed.
    """
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines, autojunk=False)

    out: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.extend(after_lines[j1:j2])
            continue
        for line in after_lines[j1:j2]:
            if line.strip() == "":
                continue
            out.append(_reformat_separators(line))
    return "".join(out)


def _require_file(file_path: Path) -> None:
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")


def _reject_directive_shaped(value: Any) -> None:
    """Mirror ``literals._format_value``'s tier-1 guard on this tier too.

    foamlib's own type-strictness does not reject a directive-shaped string
    (e.g. ``'#includeEtcFuncs'``, ``'PCG#calc'``): none of them read back as
    another type, so it has nothing to object to. Stringifies unconditionally
    -- every value type, not only ``str`` -- so a container value (e.g. a
    dict holding a directive-shaped string) cannot bypass the guard either.
    See SECURITY.md.
    """
    value = str(value)
    if ";" in value or "\n" in value:
        raise ValueError(
            f"override value {value!r} contains a statement separator; "
            "a value may not introduce additional dictionary entries"
        )
    if "#" in value:
        raise ValueError(
            f"override value {value!r} contains an OpenFOAM directive; "
            "directives are not permitted in override values"
        )


def update_entry(
    file_path: Path,
    key: str,
    value: Any,
    *,
    scope: ScopeArg = None,
    add_if_missing: bool = False,
) -> None:
    """Set ``key`` within ``scope``, failing closed when the key is absent
    unless ``add_if_missing``, which also creates missing sub-dictionaries
    of ``scope``."""
    _require_file(file_path)
    _reject_directive_shaped(value)
    path = tuple(_normalize_scope(scope)) + (key,)

    coerced = coerce_value(value)
    if isinstance(coerced, Dimensioned) and _dimensioned_component_count(coerced) > 1:
        # foamlib's generic sized-list serialiser writes a multi-component
        # `Dimensioned` as "6(...)", but OpenFOAM's fixed-arity VectorSpace
        # reader for these fields rejects a leading count outright (confirmed:
        # "FOAM FATAL IO ERROR: Expected a '(' while reading VectorSpace").
        # Splice the original, already-valid override string in verbatim
        # instead. Local import to avoid a cycle: mutators imports this
        # module at its own top level.
        from omnidriver.openfoam.mutators import splice_raw_entry_text

        if not splice_raw_entry_text(file_path, key, str(value).strip(), scope=scope):
            if add_if_missing:
                raise NotImplementedError(
                    "add_if_missing is not supported for a multi-component "
                    "dimensioned override; the entry must already exist"
                )
            raise ValueError(
                f"cannot write multi-component dimensioned value {value!r} to "
                f"{key!r}: not found as a single-line scalar entry in "
                f"{file_path} (scope={scope!r})"
            )
        return

    before = file_path.read_text()
    foam_file = FoamFile(file_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        try:
            if not add_if_missing:
                try:
                    foam_file[path]
                except KeyError as exc:
                    raise KeyError(
                        f"Key '{key}' not found in scope '{scope}' in {file_path}"
                        if scope is not None
                        else f"Key '{key}' not found in {file_path}"
                    ) from exc
            else:
                for depth in range(1, len(path)):
                    try:
                        foam_file[path[:depth]]
                    except KeyError:
                        foam_file[path[:depth]] = {}
            foam_file[path] = coerced
        except KeyError:
            raise
        except (TypeError, ValueError) as exc:
            # Catches foamlib's own ValueError (type-inconsistent value) and
            # FoamFileDecodeError (a ValueError subclass raised by a parse
            # failure on either the pre-check read or the write). Neither
            # foamlib exception type is allowed to escape unmapped -- see
            # the spec's Exception contract.
            file_path.write_text(before)
            raise ValueError(f"cannot write value {value!r} to {key!r}: {exc}") from exc

    file_path.write_text(normalize_output(before, file_path.read_text()))


def remove_dict(
    file_path: Path,
    dict_name: str,
    *,
    scope: ScopeArg = None,
    missing_ok: bool = False,
) -> None:
    """Delete a sub-dictionary block.

    foamlib's ``del`` leaves the emptied block as a whitespace-only line
    between its braces (measured: ``solvers\\n{\\n    Vm {...}\\n}\\n`` becomes
    ``solvers\\n{\\n    \\n}\\n``), not a clean removal. Route through
    ``normalize_output`` so the stray line is dropped along with the same
    blank-line class ``update_entry`` already has to handle.
    """
    _require_file(file_path)
    path = tuple(_normalize_scope(scope)) + (dict_name,)

    before = file_path.read_text()
    foam_file = FoamFile(file_path)
    try:
        del foam_file[path]
    except KeyError:
        if missing_ok:
            return
        raise KeyError(f"Dictionary '{dict_name}' not found in {file_path}") from None
    except (TypeError, ValueError) as exc:
        # Mirrors update_entry's mapping: `del` re-parses the whole file, so
        # a FoamFileDecodeError elsewhere in the file (a ValueError subclass)
        # can surface here even when the target path itself is well-formed.
        file_path.write_text(before)
        raise ValueError(f"cannot remove dictionary {dict_name!r}: {exc}") from exc

    file_path.write_text(normalize_output(before, file_path.read_text()))
