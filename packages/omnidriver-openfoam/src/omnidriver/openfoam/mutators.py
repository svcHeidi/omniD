from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import foam_backend
from .literals import _format_value


def check_dictionary_word_is_safe(word: str) -> str:
    """Apply `_format_value`'s `;`/`#`/newline refusal to a word that will
    become a dictionary key or sub-block name, not a value -- neither
    `update_foam_entry` otherwise checks that argument. See SECURITY.md.
    """
    return _format_value(word)


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


def _normalize_scope(scope: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if scope is None:
        return []
    if isinstance(scope, str):
        normalized = scope.strip()
        if not normalized:
            raise ValueError("scope cannot be an empty string")
        return [normalized]
    normalized = [str(item).strip() for item in scope]
    if not normalized or any(not item for item in normalized):
        raise ValueError("scope must contain one or more non-empty names")
    return normalized


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
    """``(regex_source, on_disk_name)`` for quoted regex block headers such as ``"Vm|u"``, which the line scanner and foamlib otherwise match literally."""
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

    raise KeyError(f"Scope '{dict_name}' not found")


def _resolve_search_region(
    lines: list[str],
    scope: str | list[str] | tuple[str, ...] | None,
) -> tuple[int, int]:
    scope_path = _normalize_scope(scope)
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


def splice_raw_entry_text(
    file_path: Path,
    key: str,
    raw_text: str,
    *,
    scope: str | list[str] | tuple[str, ...] | None = None,
) -> bool:
    """Replace ``key``'s value with ``raw_text``, written verbatim, bypassing
    the ``"/*" in source`` gate that otherwise routes straight to
    ``foam_backend``. Returns ``False`` if the scope or key isn't found, or
    the matched entry spans multiple lines. Never calls into
    ``foam_backend`` itself: the two tiers must not call each other, or a
    value routed here because ``foam_backend`` needs it would recurse.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")

    key_pattern = re.compile(rf"^\s*{re.escape(key)}(?=\s|;|$)")
    lines = file_path.read_text().splitlines(keepends=True)
    virtual = _explode_inline_blocks_with_spans(lines)
    try:
        search_start, search_end = _resolve_search_region(
            [t for t, _, _, _ in virtual], scope
        )
    except KeyError:
        return False

    direct = _iter_direct_child_lines([t for t, _, _, _ in virtual], search_start, search_end)

    target: tuple[int, int, int] | None = None
    for idx in direct:
        text, line_index, start, end = virtual[idx]
        if text.strip().startswith("//") or not key_pattern.match(text):
            continue
        if not _strip_inline_comment(text).rstrip().endswith(";"):
            return False
        target = (line_index, start, end)
        break

    if target is None:
        return False

    line_index, start, end = target
    line = lines[line_index]
    if start == 0 and end >= len(line.rstrip("\n")):
        indent = line[: len(line) - len(line.lstrip())]
        lines[line_index] = f"{indent}{key}    {raw_text};\n"
    else:
        fragment = line[start:end]
        indent = fragment[: len(fragment) - len(fragment.lstrip())]
        lines[line_index] = line[:start] + indent + f"{key}    {raw_text};" + line[end:]
    file_path.write_text("".join(lines))
    return True


def update_foam_entry(
    file_path: Path,
    key: str,
    value: Any,
    *,
    scope: str | list[str] | tuple[str, ...] | None = None,
    add_if_missing: bool = False,
) -> None:
    """Update a key in an OpenFOAM dictionary-like text file, matching the
    first non-comment line starting with `key` and rewriting it as
    `<indent><key>    <value>;`. If `scope` is given, the update is
    restricted to that dictionary block (or nested path of blocks).

    `add_if_missing=True` appends the entry to the scoped block instead of
    raising when the key isn't present, mirroring foamDictionary's own
    `-set` (which auto-creates a missing key) so behaviour doesn't depend on
    whether OpenFOAM happens to be sourced.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")

    key_pattern = re.compile(rf"^\s*{re.escape(key)}(?=\s|;|$)")
    source = file_path.read_text()
    if "/*" in source:
        # The line writer cannot safely splice entries whose source crosses
        # block comments.
        return foam_backend.update_entry(
            file_path, key, value, scope=scope, add_if_missing=add_if_missing
        )
    lines = source.splitlines(keepends=True)
    virtual = _explode_inline_blocks_with_spans(lines)
    try:
        search_start, search_end = _resolve_search_region(
            [t for t, _, _, _ in virtual], scope
        )
    except KeyError:
        # e.g. a brace inside a quoted value defeats the scanner's brace count.
        return foam_backend.update_entry(
            file_path, key, value, scope=scope, add_if_missing=add_if_missing
        )
    direct = _iter_direct_child_lines([t for t, _, _, _ in virtual], search_start, search_end)

    target: tuple[int, int, int] | None = None
    for idx in direct:
        text, line_index, start, end = virtual[idx]
        if text.strip().startswith("//") or not key_pattern.match(text):
            continue
        if not _strip_inline_comment(text).rstrip().endswith(";"):
            # Replacing only the header of a multiline entry leaves the old
            # value behind as an extra statement.
            return foam_backend.update_entry(
                file_path, key, value, scope=scope, add_if_missing=add_if_missing
            )
        target = (line_index, start, end)
        break

    replaced = target is not None
    if replaced:
        line_index, start, end = target
        line = lines[line_index]
        if start == 0 and end >= len(line.rstrip("\n")):
            # The entry owns the whole line: keep the original indentation.
            indent = line[: len(line) - len(line.lstrip())]
            lines[line_index] = f"{indent}{key}    {_format_value(value)};\n"
        else:
            # Inline block: splice in place so the rest of the line -- sibling
            # entries, closing braces, any trailing comment -- is preserved.
            fragment = line[start:end]
            indent = fragment[:len(fragment) - len(fragment.lstrip())]
            lines[line_index] = line[:start] + indent + f"{key}    {_format_value(value)};" + line[end:]
        file_path.write_text("".join(lines))

    if not replaced:
        own_line = search_end < len(virtual) and not lines[virtual[search_end][1]][: virtual[search_end][2]].strip()
        if add_if_missing and scope is not None and own_line:
            insert_before_index = virtual[search_end][1]
            indent = "    "
            for idx in _iter_direct_child_lines(
                [t for t, _, _, _ in virtual], search_start, search_end
            ):
                text, line_index, _start, _end = virtual[idx]
                if text.strip() and not text.strip().startswith("//"):
                    sibling_line = lines[line_index]
                    indent = sibling_line[: len(sibling_line) - len(sibling_line.lstrip())]
                    break
            lines.insert(insert_before_index, f"{indent}{key}    {_format_value(value)};\n")
            file_path.write_text("".join(lines))
            return
        return foam_backend.update_entry(
            file_path, key, value, scope=scope, add_if_missing=add_if_missing
        )


def remove_foam_dict(
    file_path: Path,
    dict_name: str,
    *,
    scope: str | list[str] | tuple[str, ...] | None = None,
    missing_ok: bool = False,
) -> None:
    """Remove a dictionary block from an OpenFOAM dictionary-like text file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")

    lines = file_path.read_text().splitlines(keepends=True)
    try:
        search_start, search_end = _resolve_search_region(lines, scope)
    except KeyError:
        return foam_backend.remove_dict(
            file_path, dict_name, scope=scope, missing_ok=missing_ok
        )
    # A trailing \b would not match a quoted regex-style block name (its
    # closing quote is non-word), so require whitespace/brace/end-of-line
    # instead; this still rejects a longer name with dict_name as a prefix.
    header_pattern = re.compile(rf"^\s*{re.escape(dict_name)}(?=\s|\{{|$)")

    remove_start: int | None = None
    remove_end: int | None = None

    i = search_start
    while i < search_end:
        candidate = _strip_inline_comment(lines[i])
        if not header_pattern.match(candidate):
            i += 1
            continue

        open_line = i
        while open_line < search_end and "{" not in _strip_inline_comment(lines[open_line]):
            open_line += 1

        if open_line >= search_end:
            return foam_backend.remove_dict(
                file_path, dict_name, scope=scope, missing_ok=missing_ok
            )

        depth = 0
        saw_open = False
        for j in range(open_line, search_end):
            text = _strip_inline_comment(lines[j])
            for ch in text:
                if ch == "{":
                    depth += 1
                    saw_open = True
                elif ch == "}" and saw_open:
                    depth -= 1
                    if depth == 0:
                        remove_start = i
                        remove_end = j + 1
                        break
            if remove_end is not None:
                break
        break

    if remove_start is None or remove_end is None:
        if not dict_name.startswith('"'):
            resolved = _resolve_pattern_scope(
                lines, dict_name, start=search_start, end=search_end
            )
            if resolved is not None:
                return remove_foam_dict(
                    file_path, resolved, scope=scope, missing_ok=missing_ok
                )
        return foam_backend.remove_dict(
            file_path, dict_name, scope=scope, missing_ok=missing_ok
        )

    del lines[remove_start:remove_end]
    file_path.write_text("".join(lines))


def remove_foam_entry(
    file_path: Path,
    entry_name: str,
    *,
    scope: str | list[str] | tuple[str, ...] | None = None,
    missing_ok: bool = False,
) -> None:
    """Remove a scalar entry (``name value;``) from an OpenFOAM dictionary
    file; the scalar counterpart of :func:`remove_foam_dict`, which raises
    if the matched name turns out to open a block instead."""
    if not file_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {file_path}")

    lines = file_path.read_text().splitlines(keepends=True)
    try:
        search_start, search_end = _resolve_search_region(lines, scope)
    except KeyError:
        if missing_ok:
            return
        raise

    header_pattern = re.compile(rf"^\s*{re.escape(entry_name)}(?=\s|;|$)")

    for i in range(search_start, search_end):
        candidate = _strip_inline_comment(lines[i])
        if not header_pattern.match(candidate):
            continue

        # Distinguish a scalar from a block: a block's brace opens either on
        # the header line or before the first ``;``.
        end = i
        while end < search_end and ";" not in _strip_inline_comment(lines[end]):
            if "{" in _strip_inline_comment(lines[end]):
                raise KeyError(
                    f"'{entry_name}' is a dictionary, not a scalar entry; "
                    "use remove_foam_dict"
                )
            end += 1
        if end >= search_end:
            raise KeyError(f"Entry '{entry_name}' has no terminating ';'")
        if "{" in _strip_inline_comment(lines[i]):
            raise KeyError(
                f"'{entry_name}' is a dictionary, not a scalar entry; "
                "use remove_foam_dict"
            )

        del lines[i:end + 1]
        file_path.write_text("".join(lines))
        return

    if missing_ok:
        return
    if scope is None:
        raise KeyError(f"Entry '{entry_name}' not found in {file_path}")
    raise KeyError(f"Entry '{entry_name}' not found in scope '{scope}' in {file_path}")
