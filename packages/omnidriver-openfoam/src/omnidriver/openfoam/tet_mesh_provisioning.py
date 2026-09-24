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

**Why the rendered `.geo` is still a direct write, not a case-write channel
target (decided 2026-09-24, Phase 3 Task 7 follow-up).** By classification
it belongs on the channel. It is small, per-case content rendered into
`case_root` from a template and a case parameter, the same class of content
as the tet numerics overlays that now reach `system/` through
`plan_verbatim_content`. Its consumer being `gmsh` (a separate `workflow_dag`
step) rather than cardiacFoam changes nothing: the hex family's equivalent,
`blockMeshDict`, is read only by the `blockMesh` step and is already a
channel target (`utils.plan_block_mesh_resolution`). What blocks it is the
format. The only channel renderer these tutorials reach,
`case_rendering.render_patch_case_files`, stamps every `RenderedFile` it
returns with `format="openfoam_dictionary"`, and the renderer adapter checks
that stamp against what the provider declares (`get_rendered_formats()`).
A gmsh geometry script routed through it would be recorded as an OpenFOAM
dictionary, which is a false audit record rather than a missing one. Doing
this properly needs a per-target format in that renderer and a gmsh-geometry
format declared by the provider. That is new vocabulary, deliberately not
added in passing.
"""

from __future__ import annotations

import math
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
    return render_tet_geo_at_length(
        case_root, 1.0 / n, template_relpath=template_relpath, geo_relpath=geo_relpath,
    )


def render_tet_geo_at_length(
    case_root: Path,
    lc: float,
    *,
    template_relpath: Path = Path("setup/studies/tetConvergence/box.geo.template"),
    geo_relpath: Path = Path("setup/studies/tetConvergence/box.geo"),
) -> Path:
    """Write `geo_relpath` with `__LC__` substituted by `lc` itself.

    `render_tet_geo`'s `1/n` is one tutorial family's convention (a unit
    cube, `n` cells per edge), not the geometry's: `niederer_2012`'s slab is
    sized in metres and its sweep is a physical `dx`, so its characteristic
    length is `dx_mm * 1e-3`, not a reciprocal cell count. Added 2026-09-24
    so that tutorial could stop hand-rolling its own substitution -- a blind
    `str.replace` that also rewrote the placeholder's name inside the real
    `slab.geo.template`'s own explanatory comment (see the comment handling
    below). `render_tet_geo` delegates here; the rendering rules are
    identical.

    Raises `TypeError` if `lc` is not a real number, `ValueError` if it is
    not finite and positive, and otherwise exactly what `render_tet_geo`
    raises for the template.
    """
    if isinstance(lc, bool) or not isinstance(lc, (int, float)):
        raise TypeError(f"lc must be a real number; got {lc!r}")
    if not math.isfinite(lc) or lc <= 0:
        raise ValueError(f"lc must be finite and positive; got {lc}")

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
