"""What several cardiacFOAM records' steps write, stated once.

Added 2026-09-26 (review 54b M6): ``constant/polyMesh``'s file set was
copied into four records, and ``constant/electroProperties
.withDefaultValues`` was spelled three ways. Each fact below was settled by
a real run, not assumed (``docs/solver-learning/cardiacfoam.md``); a record
imports the ones its own run showed.
"""

from __future__ import annotations

#: The cardiacFoam dictionary every record in this package patches.
ELECTRO_PROPERTIES = "constant/electroProperties"

#: ``electroModel::end`` renames and rewrites the dictionary at the end of a
#: run (plan §5g Q13, corrected by P4's R4). Written by every solver that
#: calls it: bidomain (B2), eikonalECG (E1) and niederer2011's monodomain
#: (N1). Not by ``singleCellSolver`` (restitutionCurves, R4), which
#: overrides ``end`` without calling it. A record declares it only when its
#: own run writes it.
WITH_DEFAULT_VALUES = f"{ELECTRO_PROPERTIES}.withDefaultValues"

#: ``blockMesh`` on one zone-free ``hex (`` block writes exactly these
#: (restitutionCurves R1, bidomain B3, eikonalECG E1, niederer2011 N1).
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

    Observed for a template with the single ``Physical Volume("internal")``
    in real runs through the bidomain, eikonalECG and niederer2011 records
    (bidomain B3; review 54b's tet runs, logged in the same file). A record
    whose template names other volumes confirms its own set in a run
    before declaring it.
    """
    if not physical_volumes:
        raise ValueError("gmsh_to_foam_outputs needs the template's Physical Volume names")
    return POLY_MESH_OUTPUTS + (
        "constant/polyMesh/cellZones",
        "constant/polyMesh/faceZones",
        "constant/polyMesh/pointZones",
    ) + tuple(f"constant/polyMesh/sets/{volume}" for volume in physical_volumes)
