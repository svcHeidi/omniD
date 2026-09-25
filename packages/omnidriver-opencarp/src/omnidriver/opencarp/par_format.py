"""openCARP's .par format: parse, patch in place, and spell values.

Pure text in, text out; nothing here touches the filesystem. Behaviour is
taken from the binary (docs/solver-learning/opencarp.md):
- F1: a Flag is off only for ``0`` or ``false``; ``no``/``off`` mean on,
  so omniD writes ``1``/``0`` only.
- F8: when a key is assigned twice, openCARP uses the last assignment.
- F9: the separator is ``=`` or whitespace alone (``spacedt 2``); both are
  read, and a patch keeps whichever the line used.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

APPENDED_BLOCK_HEADER = "# --- set by omniD: keys the native file does not assign ---"

_KEY = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*)*"
_ASSIGNMENT = re.compile(
    rf'^(?P<lead>\s*)(?P<key>{_KEY})(?P<eq>\s*=\s*|\s+)(?P<value>"[^"]*"|[^#\s](?:[^#]*[^#\s])?)?(?P<trail>\s*(?:#.*)?)$'
)


class ParFormatError(ValueError):
    """A .par text or value omniD refuses to read or write, naming why."""


@dataclass(frozen=True)
class ParAssignment:
    line_index: int
    key: str
    value: str | None


def parse_par(text: str) -> tuple[ParAssignment, ...]:
    assignments = []
    for index, line in enumerate(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if match is None:
            raise ParFormatError(f"line {index + 1} is not a .par assignment: {line!r}")
        assignments.append(ParAssignment(index, match["key"], match["value"]))
    return tuple(assignments)


def read_raw(text: str, key: str) -> str | None:
    """The raw value openCARP uses for ``key``: the last assignment (F8), or None if absent."""
    value = None
    for assignment in parse_par(text):
        if assignment.key == key:
            value = assignment.value
    return value


def unquote(raw: str) -> str:
    return raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] == '"' else raw


def patch_par(text: str, values: Mapping[str, str]) -> str:
    """Rewrite each key's value where it stands; append keys the text does not assign.

    ``values`` maps a key to its already-spelled value (``format_value``).
    A key assigned more than once is refused: openCARP would read the last
    one (F8), so which one a patch means is ambiguous."""
    by_key: dict[str, list[ParAssignment]] = {}
    for assignment in parse_par(text):
        by_key.setdefault(assignment.key, []).append(assignment)
    lines = text.splitlines(keepends=True)
    appended: list[str] = []
    for key, new_value in values.items():
        if _breaks_a_line(new_value):
            # Review B-I5, defence in depth: values arrive already spelled,
            # and one with a line break would write a second assignment.
            raise ParFormatError(f"{key}: the value {new_value!r} contains a line break; refusing to write it")
        found = by_key.get(key, [])
        if len(found) > 1:
            raise ParFormatError(
                f"{key} is assigned {len(found)} times; openCARP uses the last one (F8), "
                "so which one a patch means is ambiguous -- refusing"
            )
        if not found:
            appended.append(f"{key} = {new_value}\n")
            continue
        index = found[0].line_index
        line = lines[index]
        body = line.rstrip("\r\n")
        ending = line[len(body):]
        match = _ASSIGNMENT.match(body)
        lines[index] = f'{match["lead"]}{match["key"]}{match["eq"]}{new_value}{match["trail"]}{ending}'
    if appended:
        text_so_far = "".join(lines)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        if APPENDED_BLOCK_HEADER not in text_so_far:
            lines.append(f"\n{APPENDED_BLOCK_HEADER}\n")
        lines.extend(appended)
    return "".join(lines)


def _breaks_a_line(text: str) -> bool:
    """Whether ``text`` holds anything ``str.splitlines`` -- and so ``parse_par`` -- splits on."""
    return len(f"x{text}x".splitlines()) > 1


def _control_characters(text: str) -> list[str]:
    return [c for c in text if unicodedata.category(c) in ("Cc", "Zl", "Zp")]


def format_value(value: Any, value_kind: str) -> str:
    if value_kind == "boolean":
        if not isinstance(value, bool):
            raise ParFormatError(f"a Flag takes true or false, got {value!r} (openCARP reads 'no' as on: F1)")
        return "1" if value else "0"
    if value_kind == "integer":
        if isinstance(value, bool) or int(value) != value:
            raise ParFormatError(f"expected an integer, got {value!r}")
        return str(int(value))
    if value_kind == "scalar":
        if isinstance(value, bool):
            raise ParFormatError(f"expected a number, got {value!r}")
        return repr(float(value))
    if value_kind == "string":
        text = str(value)
        if _control_characters(text):
            # Review B-I5: "x\nnum_stim = 0" was spelled '"x\nnum_stim = 0"',
            # and patch_par then wrote a second assignment. No run settles how
            # openCARP reads a control character inside a value, so none is
            # written.
            raise ParFormatError(
                f"a .par string cannot contain a control character "
                f"({', '.join(repr(c) for c in _control_characters(text))}): {text!r}"
            )
        if '"' in text:
            raise ParFormatError(f"a .par string cannot contain a double quote: {text!r}")
        return f'"{text}"' if (not text or "#" in text or any(c.isspace() for c in text)) else text
    raise ParFormatError(f"no .par spelling for value kind {value_kind!r}")


def values_agree(value_kind: str, requested: Any, current: Any) -> bool:
    """Whether ``current`` (raw .par text, as the reader returns it) equals ``requested``."""
    if current is None:
        return False
    text = unquote(str(current))
    try:
        if value_kind == "boolean":
            return text in ("0", "1") and (text == "1") == bool(requested)
        if value_kind == "integer":
            return int(text) == int(requested)
        if value_kind == "scalar":
            return float(text) == float(requested)
    except (TypeError, ValueError):
        return False
    return text == str(requested)
