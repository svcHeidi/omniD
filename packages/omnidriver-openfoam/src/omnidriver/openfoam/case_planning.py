"""Pure OpenFOAM case-edit planners: resolve a requested edit into a raw
`render_patch_case_files` target, reading and writing nothing.

Enforced by `scripts/check-case-writes.py`: this module never writes a case
directly.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Mapping

from .literals import _format_value

#: Synthetic key path for a blockMeshDict's hex-block cell counts -- there is
#: no real key_path for rewriting every "hex (" line, so this stands in for
#: one. Shared by the axis, the writer, and :func:`read_hex_cell_counts` so
#: all three use one spelling. Bare form implies ``expected_blocks=1``; see
#: :func:`hex_cell_counts_key_path` for the multi-block form.
HEX_CELL_COUNTS_KEY_PATH: tuple[str, ...] = ("hex_cell_counts",)


def hex_cell_counts_key_path(*, expected_blocks: int) -> tuple[str, ...]:
    """Key path for a hex-cell-counts patch, encoding `expected_blocks` in
    the path itself so the reader and writer never independently default it
    to 1 -- the cause of a real multi-block misread (bathBidomain's
    three-block `blockMeshDict.<dim>` files).

    ``expected_blocks=1`` returns :data:`HEX_CELL_COUNTS_KEY_PATH` unchanged;
    otherwise a second segment names the count, parsed back by
    :func:`hex_cell_counts_expected_blocks`.
    """
    if expected_blocks == 1:
        return HEX_CELL_COUNTS_KEY_PATH
    return (*HEX_CELL_COUNTS_KEY_PATH, str(expected_blocks))


def hex_cell_counts_expected_blocks(key_path: Sequence[str]) -> int:
    """Inverse of :func:`hex_cell_counts_key_path`.

    Raises ``ValueError`` naming `key_path` if it was not built by that
    function (e.g. a non-integer or non-positive second segment).
    """
    segments = tuple(key_path)
    if segments == HEX_CELL_COUNTS_KEY_PATH:
        return 1
    if len(segments) == 2 and segments[0] == HEX_CELL_COUNTS_KEY_PATH[0]:
        try:
            expected_blocks = int(segments[1])
        except ValueError:
            expected_blocks = None
        if expected_blocks is not None and expected_blocks > 0:
            return expected_blocks
    raise ValueError(
        f"{segments!r} is not a hex-cell-counts key path built by "
        "hex_cell_counts_key_path -- expected either "
        f"{HEX_CELL_COUNTS_KEY_PATH!r} (one block) or that plus one "
        "positive-integer segment naming expected_blocks"
    )

def _rewrite_hex_block_lines(
    text: str, cell_counts_str: str, expected_blocks: int, *, label: str,
) -> str:
    """Rewrites every `hex (` block declaration in a blockMeshDict body;
    raises ``KeyError`` if the number of lines rewritten does not equal
    `expected_blocks`. `label` names the checked document in that error."""
    lines = text.splitlines(keepends=True)
    rewritten: list[str] = []
    replaced_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("hex (") and not stripped.startswith("//"):
            prefix, _, suffix = line.partition(") (")
            if not suffix:
                rewritten.append(line)
                continue
            _, _, trailing = suffix.partition(") simpleGrading")
            rewritten.append(f"{prefix}) ({cell_counts_str}) simpleGrading{trailing}")
            replaced_count += 1
        else:
            rewritten.append(line)

    if replaced_count != expected_blocks:
        raise KeyError(
            f"Expected to update {expected_blocks} hex blocks in {label}, "
            f"but found {replaced_count}."
        )
    return "".join(rewritten)


def plan_block_mesh_resolution(
    document: str,
    cell_counts_str: str,
    *,
    expected_blocks: int = 1,
) -> Mapping[str, Any]:
    """Resolve a block-mesh-resolution edit into a
    `case_rendering.render_patch_case_files` target.

    Not a `ParameterAssignment`: rewriting every `hex (` line has no single
    key_path, and `expected_blocks` is itself part of what is asserted, not
    a value being assigned. Pure -- does not check `expected_blocks` against
    a real file; that check is `case_rendering.render_patch_case_files`'s
    job. `cell_counts_str` goes through `literals._format_value` for its
    `;`/`#`/newline refusal (SECURITY.md).
    """
    return {
        "document": document,
        "format": _patch_format(),
        "hex_cell_counts": _format_value(cell_counts_str),
        "expected_blocks": expected_blocks,
    }


def read_hex_cell_counts(
    document_path: Path, *, expected_blocks: int = 1,
) -> str | None:
    """Current cell counts of a blockMeshDict's `hex (` block(s), in the
    same string shape :func:`plan_block_mesh_resolution` writes (e.g.
    ``"80 80 80"``). Mirrors `_rewrite_hex_block_lines`'s own grammar; a
    change to one must be mirrored in the other.

    ``None`` if `document_path` does not exist. Raises ``KeyError`` if the
    number of `hex (` lines found does not equal `expected_blocks`, or if
    they disagree on the count (compared as whitespace-normalised tokens,
    not raw substrings).
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = path.read_text()
    counts: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("hex (") and not stripped.startswith("//"):
            _prefix, _, suffix = line.partition(") (")
            if not suffix:
                continue
            counts_text, _, _trailing = suffix.partition(") simpleGrading")
            counts.append(counts_text)
    if len(counts) != expected_blocks:
        raise KeyError(
            f"expected {expected_blocks} hex ( block(s) in {path}, found "
            f"{len(counts)}"
        )
    distinct = {tuple(one_count.split()) for one_count in counts}
    if len(distinct) > 1:
        raise KeyError(
            f"{path}'s {len(counts)} hex ( blocks do not share one cell "
            f"count: {sorted(set(counts))!r}"
        )
    return counts[0]


_VERTICES_BLOCK = re.compile(r"vertices\s*\(\s*((?:\([^)]*\)\s*)+)\)\s*;")
_ONE_VERTEX = re.compile(r"\(\s*([^()]*)\)")
#: Keywords blockMesh reads its vertex scale from, in lookup order: OpenFOAM's
#: dictionary::csearchCompat (blockMesh.C, dictionaryCompat.C) tries "scale"
#: before falling back to "convertToMeters".
_SCALE_KEYWORDS: tuple[str, ...] = ("scale", "convertToMeters")
_SCALAR = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _scale_line(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*{keyword}\s+([^;]*?)\s*;", re.MULTILINE)


def _block_mesh_scale(text: str, path: Path) -> float:
    """Uniform scale blockMesh applies to `vertices`: the first of
    `_SCALE_KEYWORDS` present, else 1.0. A scalar `<= 0` is no scaling, as
    in blockMesh.C's `readScaling`, which also accepts a per-component
    vector; this reader takes a scalar only and refuses anything else by
    name."""
    for keyword in _SCALE_KEYWORDS:
        match = _scale_line(keyword).search(text)
        if match is None:
            continue
        value = match.group(1)
        if not _SCALAR.fullmatch(value):
            raise ValueError(
                f"{path}: {keyword!r} is {value!r}; this reader takes a single number "
                "(blockMesh also accepts a per-component vector, which it cannot read)"
            )
        scale = float(value)
        return scale if scale > 0 else 1.0
    return 1.0


def read_hex_block_extent_m(document_path: Path) -> tuple[float, float, float] | None:
    """A blockMeshDict's own physical bounding-box extent in metres: the
    `vertices` block's per-axis max-min, scaled by `_block_mesh_scale`.

    ``None`` if the document does not exist or has no `vertices ( ... );`
    block to parse. Text-level only, the same grammar as
    `_rewrite_hex_block_lines`/`read_hex_cell_counts` -- no nested comments
    or `#include` expansion.
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = path.read_text()
    match = _VERTICES_BLOCK.search(text)
    if match is None:
        return None
    scale = _block_mesh_scale(text, path)
    points: list[tuple[float, float, float]] = []
    for vertex_match in _ONE_VERTEX.finditer(match.group(1)):
        tokens = vertex_match.group(1).split()
        if len(tokens) != 3:
            continue
        points.append(tuple(float(token) for token in tokens))  # type: ignore[arg-type]
    if not points:
        return None
    extents = []
    for axis in range(3):
        values = [point[axis] for point in points]
        extents.append((max(values) - min(values)) * scale)
    return tuple(extents)  # type: ignore[return-value]


_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _named_block_body(text: str, name: str) -> str | None:
    """Body of `name { ... }` in `text`, brace-depth aware; `None` if absent.
    First match only."""
    match = re.search(rf"(?<![\w.]){re.escape(name)}\s*\{{", text)
    if match is None:
        return None
    depth = 1
    index = match.end()
    while index < len(text) and depth > 0:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    return text[match.end():index - 1]


def read_nested_entry(document_path: Path, key: str, *, scope: Sequence[str]) -> str | None:
    """`key`'s raw value text (trailing `;` and comments stripped) inside a
    nested dictionary `scope` (e.g. `("monodomainSolverCoeffs",
    "externalStimulus")`). `None` if the document, scope, or key is absent.

    Text-level only, deliberately not `mutators.read_foam_entry`, which this
    package's axes/records may not import (`scripts/check-case-writes.py`
    bans the whole module).
    """
    path = Path(document_path)
    if not path.is_file():
        return None
    text = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", path.read_text()))
    for name in scope:
        text = _named_block_body(text, name)
        if text is None:
            return None
    match = re.search(rf"(?<![\w.]){re.escape(key)}\s+(.*?);", text, re.DOTALL)
    if match is None:
        return None
    return match.group(1).strip()


def plan_verbatim_content(
    document: str, content: str, *, executable: bool = False,
) -> Mapping[str, Any]:
    """Resolve a whole document's exact bytes into a
    `render_patch_case_files`/`render_synthesis_case_files` content target.

    `executable=True` also folds `S_IEXEC|S_IXGRP|S_IXOTH` into the mode
    each renderer computes (for a hand-runnable script such as `Allrun`);
    defaults `False` so an ordinary dictionary template is unaffected. Not a
    `ParameterAssignment`: this replaces a document's whole structure, not
    one key's value. `content` must be `str`, not `bytes` --
    `ResolvedMutation.__post_init__` freezes targets JSON-shaped and refuses
    `bytes` with `TypeError`; a caller holding raw bytes must decode them
    first.
    """
    target: dict[str, Any] = {
        "document": document,
        "format": _patch_format(),
        "content": content,
    }
    if executable:
        target["executable"] = True
    return target


def _patch_format() -> str:
    """`case_rendering.FORMAT`, imported lazily to avoid a module cycle
    (`case_rendering.py` imports `_rewrite_hex_block_lines` from here)."""
    from .case_rendering import FORMAT

    return FORMAT
