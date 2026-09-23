"""Read ParaView VTU selections and render native OpenFOAM ``cellSet`` files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path


def _read_with_pyvista(path: Path):
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ValueError(
            f"{path}: encoded or multi-piece VTU requires omnidriver-cardiaccore[vtk]"
        ) from exc
    return pv.read(path).cell_data


def _cell_ids(values) -> list[int]:
    """Reject invalid IDs instead of truncating them or emitting invalid sets."""
    result = set()
    for value in values:
        try:
            cell_id = int(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid cell ID {value!r}") from exc
        if isinstance(value, bool) or cell_id < 0 or (not isinstance(value, str) and value != cell_id):
            raise ValueError(f"Invalid cell ID {value!r}; expected a nonnegative integer")
        result.add(cell_id)
    return sorted(result)


def read_cell_ids(path: Path, preferred_array: str | None = None) -> tuple[str, list[int]]:
    """Read ASCII VTU IDs; delegate encoded/multi-piece payloads to PyVista."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        arrays = _read_with_pyvista(path)
    else:
        cell_data = root.find(".//CellData")
        if cell_data is None:
            raise ValueError(f"{path}: no CellData block")
        arrays = {
            item.attrib.get("Name"): item.text or ""
            for item in cell_data.findall("DataArray") if item.attrib.get("Name")
        }
        # Encoded arrays can be valid XML with empty text. Treating that text
        # as IDs silently produced an empty cellSet for a nonempty selection.
        if len(root.findall(".//Piece")) > 1 or any(
            item.attrib.get("format", "ascii") != "ascii"
            for item in cell_data.findall("DataArray")
        ):
            arrays = _read_with_pyvista(path)
    candidates = ([preferred_array] if preferred_array else []) + ["GlobalCellIds", "vtkOriginalCellIds"]
    for name in candidates:
        if name in arrays:
            values = arrays[name]
            ids = values if not isinstance(values, str) else values.split()
            return name, _cell_ids(ids)
    raise ValueError(f"{path}: no usable cell ID array; tried {candidates}")


def render_cell_set(object_name: str, ids: list[int]) -> str:
    """Render an OpenFOAM ``cellSet`` with deterministic sorted IDs."""
    selected = _cell_ids(ids)
    body = "\n".join(str(cell_id) for cell_id in selected)
    return f'''FoamFile
{{
    version     2.0;
    format      ascii;
    class       cellSet;
    location    "constant/polyMesh/sets";
    object      {object_name};
}}

{len(selected)}
(
{body}
)
'''


def write_cell_set(path: Path, object_name: str, ids: list[int]) -> None:
    """Write a rendered `cellSet` to an explicit, caller-chosen destination.

    **Classified 2026-09-23 (Phase 2 Task 12, batch P2-H): a case input, not
    yet migrated onto the case-write channel.** A `cellSet` under a real
    case's `constant/polyMesh/sets/` is a framework-authored input a native
    utility reads -- the value shape already fits (`value_kind="integer_list"`
    exists in `core.contracts.dictionary.VALUE_KINDS`) -- but there is no
    renderer registered for the `cellSet` format; `openfoam/case_rendering.py`
    owns `openfoam_dictionary` (key=value documents) only, and a `cellSet` is
    a different native format entirely. This function also has no
    `case_root`/adapter addressing to resolve `path` against -- it renders to
    whatever destination the caller names, which is why its own catalog entry
    (`catalogs/operations.py`, `cardiaccore.vtu.cell_set.v1`) already says
    "use a staged destination for writes" rather than a live case path.
    Registering a `cellSet` renderer and giving this an addressed,
    channel-routed sibling (mirroring `overrides.apply_input_overrides_planned`)
    is design work beyond this task's stated files; left as an open bypass
    for the mutation-path inventory.
    """
    rendered = render_cell_set(object_name, ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
