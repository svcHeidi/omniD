"""``manufacturedMonodomain1D3D``, the coupled 1D-3D monodomain manufactured-solution record.
Native case: ``manufacturedSolutions/monodomain1D3D``; a ``coupled`` and a ``graphOnly`` variant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, TutorialRecord, WorkflowStep,
)
from omnidriver.openfoam.axes import block_mesh_resolution_axis

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .routes import block_mesh_step

GRAPH_FILE_AXIS_NAME = "graphFile"
NUMBER_CELLS_AXIS_NAME = "numberCells"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict.3D"
_CONTROL_DICT_DOCUMENT = "system/controlDict"

#: The conduction-network scope of `myocardiumSolver monodomainSolver` where
#: the native case's one `purkinjeNetwork` entry lives.
_PURKINJE_GRAPH_MODEL_COEFFS = (
    "monodomainSolverCoeffs", "conductionNetworkDomains", "purkinjeNetwork", "purkinjeGraphModelCoeffs",
)

#: Every graph file the native case ships, plus the plain default, so the
#: solve steps' `consumes` covers whichever one a study names.
GRAPH_FILES: tuple[str, ...] = (
    "purkinjeGraph",
    "purkinjeGraph.nodes003", "purkinjeGraph.nodes011", "purkinjeGraph.nodes021",
    "purkinjeGraph.nodes041", "purkinjeGraph.nodes081", "purkinjeGraph.nodes161",
)

COUPLED_SOLVE_STEP_ID = "solve"
GRAPH_ONLY_SOLVE_STEP_ID = "solveGraphOnly"
VARIANT_SELECTOR_NAME = "solver"
COUPLED_VARIANT = "coupled"
GRAPH_ONLY_VARIANT = "graphOnly"


def _graph_file_axis(name: str) -> AxisContract:
    """The study value must name a file under the staged case's ``constant/``; it is patched unquoted onto ``graphFile``."""

    def resolve(value: Any, staged_case_root: Path) -> AxisResult:
        graph_file = str(value)
        candidate = Path(staged_case_root) / "constant" / graph_file
        if not candidate.is_file():
            raise ValueError(
                f"graph-file axis {name!r}: no constant/{graph_file!r} in the staged case"
            )
        return AxisResult(patches=(
            AxisPatch(
                document=ELECTRO_PROPERTIES,
                key_path=_PURKINJE_GRAPH_MODEL_COEFFS + ("graphFile",),
                value=graph_file, value_kind="word",
            ),
        ))

    return AxisContract(name=name, value_kind="word", resolve=resolve)


def _isotropic_cell_counts(
    n: Any, current: tuple[int, int, int], extents: tuple[float, float, float] | None,
) -> tuple[int, int, int]:
    """The one ``hex (`` block is a cube with no direction fixed at 1 cell, so ``n`` expands isotropically."""
    del current, extents
    return (n, n, n)


AXES = (
    _graph_file_axis(GRAPH_FILE_AXIS_NAME),
    block_mesh_resolution_axis(
        NUMBER_CELLS_AXIS_NAME, documents=(_BLOCK_MESH_DICT_DOCUMENT,),
        resolution=_isotropic_cell_counts, expected_blocks=1, value_kind="integer",
    ),
)

#: `GRAPH_FILES` as case-relative paths, which `consumes` requires; the native
#: `graphFile` word stays a bare filename.
_GRAPH_FILE_PATHS: tuple[str, ...] = tuple(f"constant/{name}" for name in GRAPH_FILES)

#: `cardiacFoam` (coupled) reads the myocardium solver's usual set, plus
#: whichever graph file `graphFile` names. `runPurkinjeGraph` (graphOnly)
#: reads only `controlDict`/`electroProperties`/the graph files.
_COUPLED_SOLVE_CONSUMES = (
    _CONTROL_DICT_DOCUMENT, "system/fvSchemes", "system/fvSolution",
    "constant/physicsProperties", ELECTRO_PROPERTIES,
) + _GRAPH_FILE_PATHS
_GRAPH_ONLY_SOLVE_CONSUMES = (_CONTROL_DICT_DOCUMENT, ELECTRO_PROPERTIES) + _GRAPH_FILE_PATHS

#: Written by both solve routes.
_GRAPH_VERIFIER_OUTPUTS = (
    "postProcessing/graph_1D_*_nodes.dat",
    "postProcessing/purkinjeNetwork.dat",
    "postProcessing/purkinjeNetworkVTK/*",
)

RECORD = TutorialRecord(
    name="manufacturedMonodomain1D3D",
    native_case_relpath="manufacturedSolutions/monodomain1D3D",
    axes=AXES,
    workflow_steps=(
        block_mesh_step(
            (_BLOCK_MESH_DICT_DOCUMENT, _CONTROL_DICT_DOCUMENT), default_dict=_BLOCK_MESH_DICT_DOCUMENT,
        ),
        WorkflowStep(
            step_id=COUPLED_SOLVE_STEP_ID, command=("cardiacFoam",),
            consumes=_COUPLED_SOLVE_CONSUMES,
            produces=(
                WITH_DEFAULT_VALUES,
                "postProcessing/*_cells.dat",
            ) + _GRAPH_VERIFIER_OUTPUTS + (
                # Both the directory and the file: staging does not drop
                # `verification/` wholesale like `postProcessing/`, so
                # restaging would carry the now-empty directory forward even
                # once its file is excluded.
                "verification",
                "verification/coupled1D3DMonodomain_diagnostics.csv",
            ),
        ),
        WorkflowStep(
            step_id=GRAPH_ONLY_SOLVE_STEP_ID, command=("runPurkinjeGraph",),
            consumes=_GRAPH_ONLY_SOLVE_CONSUMES,
            produces=_GRAPH_VERIFIER_OUTPUTS,
        ),
    ),
    workflow_variants={
        COUPLED_VARIANT: ("mesh", COUPLED_SOLVE_STEP_ID),
        GRAPH_ONLY_VARIANT: ("mesh", GRAPH_ONLY_SOLVE_STEP_ID),
    },
    variant_selector=VARIANT_SELECTOR_NAME,
    default_variant=COUPLED_VARIANT,
)
