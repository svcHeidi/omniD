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
    """Convert an override value into the type foamlib will serialize.

    Numeric and boolean strings become Python scalars. Other strings are
    parsed with foamlib so structured OpenFOAM values retain their structure.
    Plain words and unparseable strings remain unchanged.
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
    """Return the number of scalar components in a dimensioned value."""
    raw = value.value
    return len(raw) if hasattr(raw, "__len__") else 1


_ENTRY_SEPARATOR_RE = re.compile(r'(?<![\w"])([A-Za-z_]\w*)( )([^\s{};"][^{};]*;)')


def _reformat_separators(line: str) -> str:
    """Widen separators on changed ``key value;`` entries to four spaces."""

    def repl(match: re.Match[str]) -> str:
        key, _space, rest = match.groups()
        return f"{key}    {rest}"

    return _ENTRY_SEPARATOR_RE.sub(repl, line)


def normalize_output(before: str, after: str) -> str:
    """Normalize only lines changed by foamlib and preserve all others."""
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
    """Reject values that could add statements or OpenFOAM directives."""
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
    """Set ``key`` within ``scope``, failing closed when the key is absent."""
    _require_file(file_path)
    if add_if_missing and scope is None:
        raise ValueError("add_if_missing requires a scope")
    _reject_directive_shaped(value)
    path = tuple(_normalize_scope(scope)) + (key,)

    coerced = coerce_value(value)
    if isinstance(coerced, Dimensioned) and _dimensioned_component_count(coerced) > 1:
        # foamlib serializes multi-component Dimensioned values as sized
        # lists, which fixed-arity OpenFOAM vector types reject. Preserve the
        # valid source token instead. The local import avoids a module cycle.
        if add_if_missing:
            raise NotImplementedError(
                "add_if_missing is not supported for a multi-component "
                "dimensioned override; the entry must already exist"
            )
        from omnidriver.openfoam.mutators import splice_raw_entry_text

        if not splice_raw_entry_text(file_path, key, str(value).strip(), scope=scope):
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
            foam_file[path] = coerced
        except KeyError:
            raise
        except (TypeError, ValueError) as exc:
            # Restore the original file and expose one adapter-level error.
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
    """Delete a sub-dictionary block and normalize changed output lines."""
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
