"""Read-only access to an OpenFOAM dictionary's text: a key's raw value, as written.

It writes nothing, so a record or axis module may import it. Deliberately not ``foamDictionary``, which
re-serialises values (``0.0`` -> ``0``) and evaluates ``#calc``/``#codeStream``.
"""
from __future__ import annotations

import re
from pathlib import Path

from omnidriver.core.case_write import CaseKeyNotFound

ScopeArg = str | list[str] | tuple[str, ...] | None


def normalize_scope(scope: ScopeArg) -> tuple[str, ...]:
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


def _strip_inline_comment(line: str) -> str:
    # Whole-file block comments are handled before line scanning. Preserve
    # comment-like text inside strings (for example a URL).
    quoted = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and line.startswith("//", index):
            return line[:index]
    return line


def _mask_comments(text: str) -> str:
    """Blank comments in place, preserving offsets, so the scope scanner ignores commented entries while writes keep the file verbatim."""
    result = list(text)
    index = 0
    quoted = False
    while index < len(text):
        if quoted:
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == '"':
                quoted = False
        elif text[index] == '"':
            quoted = True
        elif text.startswith("//", index) or text.startswith("/*", index):
            block = text.startswith("/*", index)
            end = text.find("*/" if block else "\n", index + 2)
            if end < 0:
                if block:
                    raise ValueError("Unterminated block comment in dictionary")
                end = len(text)
            elif block:
                end += 2
            for position in range(index, end):
                if text[position] not in "\r\n":
                    result[position] = " "
            index = end
            continue
        index += 1
    return "".join(result)


def _structural_text(line: str) -> str:
    """Only unquoted braces and separators participate in scope discovery."""
    return re.sub(r'"(?:\\.|[^"\\])*"', lambda m: " " * len(m.group()), _strip_inline_comment(line))


def _explode_inline_blocks_with_spans(
    lines: list[str],
) -> list[tuple[str, int, int, int]]:
    """Rewrite ``a { b 1; }`` as one ``(text, line_index, start_col, end_col)`` per virtual line so a write can splice into the original line."""
    exploded: list[tuple[str, int, int, int]] = []
    for index, line in enumerate(lines):
        code = _strip_inline_comment(line)
        if not any(char in _structural_text(code) for char in "{};"):
            exploded.append((line, index, 0, len(line)))
            continue

        buffer = ""
        start = 0
        quoted = False
        escaped = False
        for position, char in enumerate(code):
            if escaped:
                buffer += char
                escaped = False
            elif quoted and char == "\\":
                buffer += char
                escaped = True
            elif char == '"':
                buffer += char
                quoted = not quoted
            elif not quoted and char in "{}":
                if buffer.strip():
                    exploded.append((buffer.strip() + "\n", index, start, position))
                exploded.append((char + "\n", index, position, position + 1))
                buffer = ""
                start = position + 1
            elif not quoted and char == ";":
                buffer += char
                exploded.append((buffer.strip() + "\n", index, start, position + 1))
                buffer = ""
                start = position + 1
            else:
                buffer += char
        if buffer.strip():
            exploded.append((buffer.strip() + "\n", index, start, len(code)))
    return exploded


def _explode_inline_blocks(lines: list[str]) -> list[str]:
    """The virtual-line texts of :func:`_explode_inline_blocks_with_spans`."""
    return [text for text, _, _, _ in _explode_inline_blocks_with_spans(lines)]


def _iter_direct_child_lines(lines: list[str], start: int, end: int):
    """Yield indices in ``[start, end)`` at the span's own level, skipping nested sub-dictionaries; braces in comments don't count."""
    depth = 0
    for idx in range(start, end):
        # Yield before this line's braces, so a sub-dictionary's header and
        # its closing brace both count as part of the nested block.
        if depth == 0:
            yield idx
        for ch in _structural_text(lines[idx]):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1


def _quoted_pattern_headers(
    lines: list[str], start: int, end: int
) -> list[tuple[str, str]]:
    """``(regex_source, on_disk_name)`` for quoted regex block headers such as ``"p|U"``, which the line scanner and foamlib otherwise match literally."""
    headers: list[tuple[str, str]] = []
    for index in _iter_direct_child_lines(lines, start, end):
        candidate = _strip_inline_comment(lines[index]).strip()
        if not candidate.startswith('"'):
            continue
        closing = candidate.find('"', 1)
        if closing <= 0:
            continue
        headers.append((candidate[1:closing], candidate[: closing + 1]))
    return headers


def _resolve_pattern_scope(
    lines: list[str], dict_name: str, *, start: int, end: int
) -> str | None:
    """Map a member name to the quoted-regex block header that matches it (exact literal wins, else the last match), or ``None``."""
    for regex_source, on_disk in reversed(
        _quoted_pattern_headers(lines, start, end)
    ):
        try:
            if re.fullmatch(regex_source, dict_name):
                return on_disk
        except re.error:
            continue
    return None


def _find_dict_block_bounds(
    lines: list[str],
    dict_name: str,
    *,
    start: int,
    end: int,
) -> tuple[int, int]:
    # A trailing \b would not match a quoted regex-style block name (its
    # closing quote is non-word), so require whitespace/brace/end-of-line
    # instead; this still rejects a longer name with dict_name as a prefix.
    header_pattern = re.compile(rf"^\s*{re.escape(dict_name)}(?=\s|\{{|$)")

    for i in _iter_direct_child_lines(lines, start, end):
        candidate = _strip_inline_comment(lines[i])
        if not header_pattern.match(candidate):
            continue

        stripped = candidate.strip()
        if stripped.endswith(";") and "{" not in stripped:
            # A scalar entry (name value;) sharing dict_name, not a block
            # header; keep looking rather than walk into a sibling block.
            continue

        open_line = i
        while open_line < end and "{" not in _structural_text(lines[open_line]):
            open_line += 1

        if open_line >= end:
            raise KeyError(f"Scope '{dict_name}' has no opening brace")

        depth = 0
        saw_open = False
        close_line: int | None = None
        for j in range(open_line, end):
            text = _structural_text(lines[j])
            for ch in text:
                if ch == "{":
                    depth += 1
                    saw_open = True
                elif ch == "}" and saw_open:
                    depth -= 1
                    if depth == 0:
                        close_line = j
                        break
            if close_line is not None:
                break

        if close_line is None:
            raise KeyError(f"Scope '{dict_name}' has unbalanced braces")

        return open_line + 1, close_line

    if not dict_name.startswith('"'):
        resolved = _resolve_pattern_scope(lines, dict_name, start=start, end=end)
        if resolved is not None:
            return _find_dict_block_bounds(lines, resolved, start=start, end=end)

    raise CaseKeyNotFound(f"Scope '{dict_name}' not found")


def _resolve_search_region(
    lines: list[str],
    scope: str | list[str] | tuple[str, ...] | None,
) -> tuple[int, int]:
    scope_path = normalize_scope(scope)
    if not scope_path:
        return 0, len(lines)

    start, end = 0, len(lines)
    for dict_name in scope_path:
        start, end = _find_dict_block_bounds(lines, dict_name, start=start, end=end)
    return start, end


def read_foam_entry(
    file_path: Path,
    key: str,
    *,
    scope: str | list[str] | tuple[str, ...] | None = None,
) -> str | None:
    """Read the value of a key from an OpenFOAM dictionary-like text file.
    Returns the raw value string -- trailing semicolon and inline comments
    stripped -- or ``None`` if the key or its scope block is absent.

    Deliberately does not shell out to foamDictionary: it re-serialises
    values (``0.0`` -> ``0``) and evaluates ``#calc``/``#codeStream``
    entries, neither of which is acceptable for a read that feeds
    dict-builder provenance digests.
    """
    if not file_path.exists():
        return None

    key_pattern = re.compile(rf"^\s*{re.escape(key)}(?=\s|;|$)")
    lines = _explode_inline_blocks(_mask_comments(file_path.read_text()).splitlines(keepends=True))
    try:
        search_start, search_end = _resolve_search_region(lines, scope)
    except KeyError:
        return None

    for idx in _iter_direct_child_lines(lines, search_start, search_end):
        line = lines[idx]
        stripped = _strip_inline_comment(line).strip()
        if stripped.startswith("//"):
            continue
        if not key_pattern.match(line):
            continue
        value_part = stripped[len(key):].strip()
        if not value_part.endswith(";"):
            # A legal scalar/list entry can span lines.
            for continuation in lines[idx + 1:search_end]:
                if "{" in _structural_text(continuation) or "}" in _structural_text(continuation):
                    return None
                value_part += " " + continuation.strip()
                if value_part.rstrip().endswith(";"):
                    break
            else:
                return None
        value_part = value_part.strip().removesuffix(";").strip()
        return value_part if value_part else None

    return None


#: A quoted string, kept, or a comment or ``#`` directive line, blanked: one regex pass, not a character loop.
_STRING_OR_COMMENT = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/|^[ \t]*#[^\n]*', re.S | re.M)
#: A uniform list ``N{value}``, whose braces open no sub-dictionary.
_UNIFORM_LIST = re.compile(r"(?<![\w.])\d+\s*\{[^{}]*\}")


def _blank(match: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", match.group())


def read_foam_entries(file_path: Path, keys: "tuple[str, ...] | list[str]") -> dict[str, str]:
    """The raw value text of each of ``keys`` that ``file_path`` sets at its top level, from one pass over the file.

    For a large data dictionary, such as a graph of tens of thousands of edges, which
    :func:`read_foam_entry` scans line by line for each key. A value keeps its spelling without the
    trailing semicolon; a sub-dictionary is no value, and an ``#include`` is not followed."""
    if not file_path.exists():
        return {}
    text = _STRING_OR_COMMENT.sub(lambda match: match.group() if match.group().startswith('"') else _blank(match), file_path.read_text())
    structure = _STRING_OR_COMMENT.sub(_blank, _UNIFORM_LIST.sub(lambda match: match.group().replace("{", " ").replace("}", " "), text))
    wanted = set(keys)
    found: dict[str, str] = {}
    depth, start = 0, 0
    for match in re.finditer(r"[{};]", structure):
        at = match.start()
        if match.group() == "{":
            depth += 1
        elif match.group() == "}":
            depth -= 1
            start = at + 1 if depth == 0 else start
        elif depth == 0:
            parts = text[start:at].split(None, 1)
            start = at + 1
            if len(parts) == 2 and parts[0] in wanted:
                found[parts[0]] = parts[1].strip()
    return found
