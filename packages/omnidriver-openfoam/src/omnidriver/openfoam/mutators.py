from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from omnidriver.core.case_write import CaseKeyNotFound
from omnidriver.core.tutorial_records import TutorialRecordError

from . import foam_backend
from .dictionary_reader import (
    _strip_inline_comment,
    _mask_comments,
    _explode_inline_blocks_with_spans,
    _explode_inline_blocks,
    _iter_direct_child_lines,
    _resolve_pattern_scope,
    _resolve_search_region,
    normalize_scope,
)
from .literals import _format_value


def check_dictionary_word_is_safe(word: str) -> str:
    """Apply `_format_value`'s `;`/`#`/newline refusal to a word that will
    become a dictionary key or sub-block name, not a value -- neither
    `update_foam_entry` otherwise checks that argument. See SECURITY.md.
    """
    return _format_value(word)


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


#: A character a pattern reads as more than itself, once its escaped characters are taken out.
_PATTERN_SYNTAX = re.compile(r"[.^$*+?{}\[\]|()\\]")


def _shadowing_words(name: str) -> tuple[str, ...]:
    """The words whose literal entry shadows a quoted ``name``: its text as written (``"ddt(U)"`` meant as the term
    ``ddt(U)``), and the one word a pattern of escaped characters only can match (``"div\\(phi\\)"``)."""
    body = name[1:-1]
    words = [body]
    if not _PATTERN_SYNTAX.search(re.sub(r"\\.", "", body)):
        words.append(re.sub(r"\\(.)", r"\1", body))
    return tuple(dict.fromkeys(words))


def _refuse_a_shadowed_pattern(file_path: Path, key: str, scope: str | list[str] | tuple[str, ...] | None) -> None:
    """Refuse a quoted ``key``, or a quoted segment of ``scope``, whose unquoted twin the dictionary already holds there.

    OpenFOAM reads a quoted key as a pattern and looks a word up literally before it tries any pattern
    (:func:`_resolve_pattern_scope` mirrors that), so the quoted entry would be written beside the literal one and
    never read in its place."""
    path = normalize_scope(scope) + (key,)
    lines = None
    for depth, name in enumerate(path):
        if len(name) < 3 or not (name.startswith('"') and name.endswith('"')):
            continue
        if lines is None:
            lines = _explode_inline_blocks(_mask_comments(file_path.read_text()).splitlines(keepends=True))
        try:
            start, end = _resolve_search_region(lines, path[:depth] or None)
        except KeyError:
            return
        held = [
            word for word in _shadowing_words(name)
            if any(
                re.match(rf"^\s*{re.escape(word)}(?=\s|;|\{{|$)", lines[index])
                for index in _iter_direct_child_lines(lines, start, end)
            )
        ]
        if held:
            where = ".".join(path[:depth])
            raise TutorialRecordError(
                f"{name} in {where + ' of ' if where else ''}{file_path.name}: the dictionary holds {held[0]} unquoted, "
                f"and OpenFOAM looks a word up literally before it tries a quoted pattern, so the quoted entry would "
                f"never be read; name it unquoted ({held[0]}) to edit the entry the dictionary holds",
                code="shadowed_key",
            )


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
    _refuse_a_shadowed_pattern(file_path, key, scope)

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
        raise CaseKeyNotFound(f"Entry '{entry_name}' not found in {file_path}")
    raise CaseKeyNotFound(f"Entry '{entry_name}' not found in scope '{scope}' in {file_path}")
