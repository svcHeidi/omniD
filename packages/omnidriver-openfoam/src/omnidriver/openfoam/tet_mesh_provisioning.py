"""Renders a resolution-specific gmsh `.geo` file for a tet-mesh sweep case.

Mirrors `mesh_provisioning.py`'s split for the hex/blockMesh case: that
module only *writes* `blockMeshDict` with a resolved cell count, it never
runs `blockMesh` itself -- `blockMesh` runs later as a `workflow_dag` step.
This module keeps the same split for tet: `render_tet_geo` only substitutes
the `__LC__` characteristic-length placeholder and writes `box.geo`; `gmsh`/
`gmshToFoam`/`checkMesh` are workflow_dag steps declared by the tutorial's
own spec, executed only when the strict workflow actually runs, never during
`apply_case`/materialization.

Each tutorial with a tet variant keeps its own copy of
`setup/studies/tetConvergence/box.geo.template`. Those copies are typically functionally
equivalent (the same gmsh geometry commands: `SetFactory`, `Box`,
`Physical Volume`/`Surface`, `Mesh.*` settings) but not byte-identical --
each carries a header comment written from its own tutorial's perspective.
This function renders whichever template belongs to the case at hand; it
never assumes one canonical file services them all.
"""

from __future__ import annotations

from pathlib import Path

_LC_PLACEHOLDER = "__LC__"


def render_tet_geo(
    case_root: Path,
    n: int,
    *,
    template_relpath: Path = Path("setup/studies/tetConvergence/box.geo.template"),
    geo_relpath: Path = Path("setup/studies/tetConvergence/box.geo"),
) -> Path:
    """Write `geo_relpath` with `__LC__` substituted by `1/n`.

    Raises `TypeError` if `n` is not an integer, `ValueError` if it is not
    positive, `FileNotFoundError` if the template is missing, and
    `ValueError` if the template does not contain exactly one `__LC__`
    placeholder (catches a stale/edited template silently producing zero or
    two resolved characteristic lengths). Never invokes gmsh -- this is a
    pure file render, consumed later by an actual `gmsh` workflow step.
    """
    if not isinstance(n, int) or isinstance(n, bool):
        raise TypeError(f"n must be an integer; got {n!r}")
    if n <= 0:
        raise ValueError(f"n must be positive; got {n}")

    template_path = case_root / template_relpath
    if not template_path.exists():
        raise FileNotFoundError(f"tet mesh template not found: {template_path}")

    text = template_path.read_text()

    # gmsh's .geo comment syntax is C++-style (//); the real templates
    # document the substitution mechanism in a comment that names the
    # placeholder literally ("__LC__ is substituted by ..."). Counting and
    # substituting on the raw text would (a) reject a valid template because
    # the comment's mention looks like a second occurrence, and (b) mangle
    # that comment's own text with the resolved number if it went ahead
    # anyway. Only the code portion of each line (before any //) counts.
    lc = 1.0 / n
    occurrences = 0
    rendered_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        comment_at = line.find("//")
        code_part = line if comment_at == -1 else line[:comment_at]
        comment_part = "" if comment_at == -1 else line[comment_at:]
        occurrences += code_part.count(_LC_PLACEHOLDER)
        rendered_lines.append(code_part.replace(_LC_PLACEHOLDER, str(lc)) + comment_part)

    if occurrences != 1:
        raise ValueError(
            f"expected exactly one {_LC_PLACEHOLDER!r} placeholder in "
            f"{template_path}, found {occurrences}"
        )

    rendered = "".join(rendered_lines)

    geo_path = case_root / geo_relpath
    geo_path.parent.mkdir(parents=True, exist_ok=True)
    geo_path.write_text(rendered)
    return geo_path
