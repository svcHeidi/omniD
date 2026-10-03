"""What several cardiacFOAM records' steps write, stated once; a record imports the facts its own run showed."""

from __future__ import annotations

#: The cardiacFoam dictionary every record in this package patches.
ELECTRO_PROPERTIES = "constant/electroProperties"

#: ``electroModel::end`` renames and rewrites the dictionary at the end of a
#: run. Written by every solver that calls it (bidomain, eikonalECG, the
#: monodomain solver), not by ``singleCellSolver``, which overrides ``end``
#: without calling it. A record declares it only when its own run writes it.
WITH_DEFAULT_VALUES = f"{ELECTRO_PROPERTIES}.withDefaultValues"

#: ``blockMesh`` on one zone-free ``hex (`` block writes exactly these.
POLY_MESH_OUTPUTS: tuple[str, ...] = (
    "constant/polyMesh",
    "constant/polyMesh/boundary",
    "constant/polyMesh/faces",
    "constant/polyMesh/neighbour",
    "constant/polyMesh/owner",
    "constant/polyMesh/points",
)


def gmsh_to_foam_outputs(*physical_volumes: str) -> tuple[str, ...]:
    """What ``gmshToFoam <mesh>.msh`` writes for a gmsh template whose
    ``Physical Volume``s are ``physical_volumes``: :data:`POLY_MESH_OUTPUTS`,
    the three zone files, and one ``constant/polyMesh/sets/<volume>`` cell
    set per volume.

    A record whose template names volumes other than the single
    ``Physical Volume("internal")`` confirms its own set in a run before
    declaring it.
    """
    if not physical_volumes:
        raise ValueError("gmsh_to_foam_outputs needs the template's Physical Volume names")
    return POLY_MESH_OUTPUTS + (
        "constant/polyMesh/cellZones",
        "constant/polyMesh/faceZones",
        "constant/polyMesh/pointZones",
    ) + tuple(f"constant/polyMesh/sets/{volume}" for volume in physical_volumes)
