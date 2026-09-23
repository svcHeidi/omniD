from pathlib import Path

from omnidriver.core.case_write import ParameterAssignment

from .mutators import update_foam_entry

#: `system/controlDict` is a fixed, case-relative location -- the same for
#: every OpenFOAM case, never derived from a caller-supplied path. Unlike
#: `cardiacfoam.overrides.resolve_entry_overrides` (which takes `document`
#: from its caller because it has only a bare `file_path` and no case root
#: to make one relative to), `plan_delta_t`/`plan_end_time` need no path
#: argument at all: they are pure and address this document by name alone.
_CONTROL_DICT_DOCUMENT = "system/controlDict"


def set_delta_t(control_dict_path: Path, delta_t_seconds: float) -> None:
    update_foam_entry(control_dict_path, "deltaT", delta_t_seconds)


def set_end_time(control_dict_path: Path, t_s: float) -> None:
    update_foam_entry(control_dict_path, "endTime", t_s)


def plan_delta_t(delta_t_seconds: float, *, owner: str) -> ParameterAssignment:
    """Resolve a `system/controlDict` `deltaT` edit into a typed, pure
    `ParameterAssignment` -- reads nothing, writes nothing (Phase 3 Task 3).

    Beside `set_delta_t`, not a replacement for it yet: `set_delta_t` keeps
    writing directly until Task 6 migrates its eleven tutorial callers onto
    the render/commit channel; both are retired together, in the same commit
    that removes the last caller (this task's own instruction).

    ``owner`` is supplied, not discovered: this module (`omnidriver-openfoam`)
    must not know about cardiacFoam or any other adapter identity (see this
    repository's package table -- `omnidriver-openfoam` "must not know about
    cardiology"), so unlike `dict_builder.py`'s own controlDict-touching
    code, which hardcodes its own `PLUGIN_ID`, this function cannot supply a
    default of its own; the caller's adapter id is the caller's to know.

    ``source`` is unconditionally ``"case"``: unlike `dict_builder.py`'s
    synthesis resolver (which chooses `"case"` vs `"template"` depending on
    whether ITS OWN caller passed `None` and it fell back to a built-in
    default), this function takes no default path of its own -- it has no
    optional parameter and no fallback, so every value it sees is one a
    caller explicitly decided to assign. Matches the same reasoning
    `cardiacfoam.overrides.resolve_entry_overrides` gives for the same
    conclusion.

    No `evidence_refs`: verified against all eleven real tutorial call
    sites (`grep -rn "set_delta_t\\|set_end_time"
    packages/omnidriver-cardiacfoam/src/.../tutorials/`) that every one
    passes an already-native Python `float`, never an already-rendered
    OpenFOAM literal string -- unlike the `dimensioned_scalar`/`vector3`
    entries Task 2's Gap 1 found, a bare `controlDict` scalar has no
    OpenFOAM-specific literal syntax to parse (no dimension brackets), so
    `omnidriver.openfoam.literals` does not apply here and there is no
    original rendered spelling to preserve as evidence.
    """
    return ParameterAssignment(
        qualified_id="deltaT",
        owner=owner,
        document=_CONTROL_DICT_DOCUMENT,
        key_path=("deltaT",),
        binding={},
        value=float(delta_t_seconds),
        value_kind="scalar",
        source="case",
    )


def plan_end_time(t_s: float, *, owner: str) -> ParameterAssignment:
    """`plan_delta_t`'s counterpart for `endTime` -- see its docstring for
    the `owner`/`source`/evidence reasoning, which applies identically."""
    return ParameterAssignment(
        qualified_id="endTime",
        owner=owner,
        document=_CONTROL_DICT_DOCUMENT,
        key_path=("endTime",),
        binding={},
        value=float(t_s),
        value_kind="scalar",
        source="case",
    )



def replace_block_mesh_resolutions(
    block_mesh_dict_path: Path,
    cell_counts_str: str,
    *,
    expected_blocks: int = 1,
) -> None:
    """Rewrite lines starting with ``hex (`` in an existing `block_mesh_dict_path`.
    Replaces the cell counts portion of the hex definition with `cell_counts_str`.
    Validates that exactly `expected_blocks` were replaced.
    """
    if not block_mesh_dict_path.exists():
        raise FileNotFoundError(f"Missing mesh dictionary: {block_mesh_dict_path}")

    lines = block_mesh_dict_path.read_text().splitlines(keepends=True)
    replaced_count = 0

    with block_mesh_dict_path.open("w") as handle:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("hex (") and not stripped.startswith("//"):
                prefix, _, suffix = line.partition(") (")
                if not suffix:
                    handle.write(line)
                    continue
                _, _, trailing = suffix.partition(") simpleGrading")
                handle.write(f"{prefix}) ({cell_counts_str}) simpleGrading{trailing}")
                replaced_count += 1
            else:
                handle.write(line)

    if replaced_count != expected_blocks:
        raise KeyError(
            f"Expected to update {expected_blocks} hex blocks in {block_mesh_dict_path}, "
            f"but found {replaced_count}."
        )
