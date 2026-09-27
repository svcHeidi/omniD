"""``manufacturedMonodomain1D3D``: a tutorial record for
``manufacturedSolutions/monodomain1D3D``, replacing two old factory
tutorials that both pointed at this one native case:
``manufactured_monodomain_1d3d`` (the coupled 1D-3D solve) and
``manufactured_purkinje_graph`` (the graph-only diagnostic). One native
case, one record; the old graph-only diagnostic is now this record's
``graphOnly`` variant, not a second tutorial (owner decision).

**Graph selection is a dictionary key, not a file copy.**
``conductionSystemDomain::readGraphFile`` (native
``src/electroModels/electroDomains/conductionSystemDomain/
conductionSystemDomain.C``) opens ``constant/<graphFile value>`` directly as
an ``IOdictionary`` -- the catalogued
``$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs
.graphFile`` key already documents this ("the value may name any graph
dictionary ... in constant/"). The old modules' ``purkinjeGraph.<id>`` ->
``purkinjeGraph`` ``shutil.copy2`` is gone: :func:`_graph_file_axis` instead
patches ``graphFile`` to name whichever committed graph the study picks,
checking only that the file exists in the staged case (never a hardcoded
name list -- one source of truth). The plain ``constant/purkinjeGraph``
stays the native default (native ``graphFile purkinjeGraph;``), reachable by
simply not naming this axis.

**The pre-processing stage.** The native ``Allrun`` already meshes (unlike
bidomain/pseudo-ECG): ``blockMesh -dict system/blockMeshDict.3D`` then
``cardiacFoam`` -- copied here verbatim as the ``mesh``/``solve`` steps.
``system/blockMeshDict.3D`` is already a valid, literal dictionary (native
commit ``f374818``, "one explicit blockMeshDict convention, .3D = 20^3");
the ``Allrun``'s own ``sed 's/NCELLS/.../''`` was already dead (the file has
held no ``NCELLS`` token since that commit, so ``N_CELLS`` silently did
nothing) and is deleted natively alongside this migration, not carried into
the record. ``numberCells`` reuses
``openfoam.axes.block_mesh_resolution_axis`` directly (owner: "don't write
a new one"), isotropic since the one ``hex (`` block is a cube.

**The ``graphOnly`` variant** is the README's own "Graph-Only Diagnostic"
(``blockMesh``; ``runPurkinjeGraph``), the old ``manufactured_purkinje_graph``
tutorial's entire reason to exist. ``runPurkinjeGraph`` (a real installed
utility, ``applications/utilities/runPurkinjeGraph``) advances the graph
alone, with no myocardium coupling: a real run shows it reads no
``physicsProperties``/``fvSchemes``/``fvSolution`` (neither file is even
opened -- ``grep`` over both its source and ``conductionSystemDomain.C``
finds no such reference) and writes no
``constant/electroProperties.withDefaultValues`` (it calls
``conductionSystemDomain::end`` directly, never ``electroModel::end``,
matching ``restitutionCurves``'s own ``singleCellSolver`` precedent). The
default route is still ``coupled`` (owner Q2: "blockMesh is always the
default"; the native ``Allrun`` runs the coupled solve, not the diagnostic).

**Every step's produces/consumes below is observed, not assumed**, logged in
full under "manufacturedMonodomain1D3D" in
``docs/solver-learning/cardiacfoam.md``:

- ``blockMesh -dict system/blockMeshDict.3D`` on the one zone-free ``hex (``
  block writes exactly :data:`.case_outputs.POLY_MESH_OUTPUTS`'s five files;
- a real ``cardiacFoam`` (coupled) run writes
  ``constant/electroProperties.withDefaultValues``,
  ``postProcessing/<dim>_<N>_cells.dat`` (the myocardium verifier, the same
  naming ``manufactured_solution_axes``'s own docstring cites for bidomain/
  eikonalECG/niederer2011), ``postProcessing/graph_1D_<n>_nodes.dat`` (the
  graph verifier, named by the SELECTED graph's own node count -- 41 for the
  plain default), ``postProcessing/purkinjeNetwork.dat`` (per-node Vm/PVJ
  current time series) and ``postProcessing/purkinjeNetworkVTK/*`` (one
  ``.vtk`` per written instance plus its ``.vtk.series`` index), and
  ``verification/coupled1D3DMonodomain_diagnostics.csv`` -- a directory
  ``postProcessing`` does not drop by convention, so it must be declared or
  a restage would carry it forward as if authored (C11);
- a real ``runPurkinjeGraph`` (graphOnly) run writes the same
  ``postProcessing/graph_1D_*_nodes.dat``/``purkinjeNetwork.dat``/
  ``purkinjeNetworkVTK/*`` triad, and nothing else -- no
  ``withDefaultValues``, no ``verification/`` (that CSV is
  ``domainCouplings.couplingA``'s own verifier, never constructed when no
  myocardium domain exists), no ``*_cells.dat`` (no myocardium verifier
  either).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from omnidriver.core.tutorial_records import (
    AxisContract, AxisPatch, AxisResult, DefaultArgument, TutorialRecord, WorkflowStep,
)
from omnidriver.openfoam.axes import block_mesh_resolution_axis

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES

GRAPH_FILE_AXIS_NAME = "graphFile"
NUMBER_CELLS_AXIS_NAME = "numberCells"

_BLOCK_MESH_DICT_DOCUMENT = "system/blockMeshDict.3D"
_CONTROL_DICT_DOCUMENT = "system/controlDict"

#: `myocardiumSolver monodomainSolver`'s own conduction-network scope this
#: tutorial's one native `purkinjeNetwork` entry lives at -- never varied
#: (the native case already names it `purkinjeNetwork`).
_PURKINJE_GRAPH_MODEL_COEFFS = (
    "monodomainSolverCoeffs", "conductionNetworkDomains", "purkinjeNetwork", "purkinjeGraphModelCoeffs",
)

#: Every graph file the native case ships (README: "Creates:
#: constant/purkinjeGraph.nodes003 through .nodes161"), plus the plain
#: default -- declared once so the solve steps' `consumes` covers whichever
#: one a study names, the same "declare every document a study might pick"
#: shape `manufactured_solution_axes.BLOCK_MESH_DICT_DOCUMENTS` already uses
#: for `dimension`.
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
    """A named ``graphFile`` axis: the study value must name a file that
    exists under the staged case's ``constant/`` (checked live, never a
    hardcoded name list -- one source of truth), patched directly onto
    ``purkinjeGraphModelCoeffs.graphFile`` -- a bare native word, unquoted
    (native: ``graphFile purkinjeGraph;``, unlike the quoted
    ``dimension "3D";``)."""

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
    """The one ``hex (`` block in ``blockMeshDict.3D`` is a cube with no
    direction fixed at 1 cell (unlike bidomain's per-dimension files), so
    every study value expands isotropically."""
    del current, extents
    return (n, n, n)


AXES = (
    _graph_file_axis(GRAPH_FILE_AXIS_NAME),
    block_mesh_resolution_axis(
        NUMBER_CELLS_AXIS_NAME, documents=(_BLOCK_MESH_DICT_DOCUMENT,),
        resolution=_isotropic_cell_counts, expected_blocks=1, value_kind="integer",
    ),
)

#: `GRAPH_FILES`, as case-relative paths under `constant/` (a `consumes`
#: entry is a full case-relative path; `GRAPH_FILES` itself stays bare
#: filenames, matching the native `graphFile` word's own shape).
_GRAPH_FILE_PATHS: tuple[str, ...] = tuple(f"constant/{name}" for name in GRAPH_FILES)

#: `cardiacFoam` (coupled) reads the myocardium solver's usual set, plus
#: whichever graph file `graphFile` names. `runPurkinjeGraph` (graphOnly)
#: reads only `controlDict`/`electroProperties`/the graph files -- a real
#: run of each confirms neither opens the other's extra documents.
_COUPLED_SOLVE_CONSUMES = (
    _CONTROL_DICT_DOCUMENT, "system/fvSchemes", "system/fvSolution",
    "constant/physicsProperties", ELECTRO_PROPERTIES,
) + _GRAPH_FILE_PATHS
_GRAPH_ONLY_SOLVE_CONSUMES = (_CONTROL_DICT_DOCUMENT, ELECTRO_PROPERTIES) + _GRAPH_FILE_PATHS

#: Written by both solve routes (a real run of each, section MD1D3D).
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
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            default_arguments=(
                DefaultArgument(key=("-dict",), values=(_BLOCK_MESH_DICT_DOCUMENT,)),
            ),
            consumes=(_BLOCK_MESH_DICT_DOCUMENT, _CONTROL_DICT_DOCUMENT),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id=COUPLED_SOLVE_STEP_ID, command=("cardiacFoam",),
            consumes=_COUPLED_SOLVE_CONSUMES,
            produces=(
                WITH_DEFAULT_VALUES,
                "postProcessing/*_cells.dat",
            ) + _GRAPH_VERIFIER_OUTPUTS + (
                # Both the directory and the file: `verification/` is not
                # `postProcessing/` (no staging convention drops it wholesale),
                # so restaging would otherwise carry the now-empty directory
                # forward even once its file is excluded (C11 -- the same
                # shape `case_outputs.POLY_MESH_OUTPUTS` already declares
                # `constant/polyMesh` alongside its five files).
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
