"""``manufacturedMonodomainPseudoECG``: a tutorial record for
``manufacturedSolutions/monodomainPseudoECG``, a manufactured-solution
verification of the monodomain stack with pseudo-ECG electrode output.

The native ``Allrun`` does not mesh at all; the mesh step's ``-dict``
default and the gmsh tet route are both copied from
``regression/regressionTest.sh`` and ``setup/studies/tetConvergence/``
respectively, not invented. The ``dimension`` axis models a two-key
relation: one study value drives both ``monodomainSolverCoeffs.dimension``
and the pseudo-ECG verifier's own nested
``...verificationModel.dimension`` (``ecg_verification_scope``). The tet
``fvSchemes`` overlay is a native quirk left unmodelled -- every entry it
sets already equals ``system/fvSchemes``'s own value. What each step reads
and writes, every old-factory write's fate, and the electrode-table
reasoning were all settled by real runs: ``docs/solver-learning
/cardiacfoam.md`` section PE.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import TutorialRecord

from .case_outputs import ELECTRO_PROPERTIES, WITH_DEFAULT_VALUES
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)
from .routes import block_mesh_step, gmsh_route, solve_step

#: This tutorial's own `monodomainSolverCoeffs` scope, and the pseudo-ECG
#: verifier's own nested echo of the tissue dimension: this axis keeps
#: `verificationModel.dimension` in step with the tissue `dimension`.
_MONODOMAIN_SOLVER_COEFFS = ("monodomainSolverCoeffs",)
_ECG_VERIFICATION_MODEL = ("ecgDomains", "ECG", "verificationModel")

_TET_TEMPLATE = "setup/studies/tetConvergence/box.geo.template"
_TET_MESH = "box.msh"

#: The mesh step's default argument, copied verbatim from
#: `regression/regressionTest.sh`: there is no native `Allrun` mesh step at
#: all, the same gap bidomain's record found.
_MESH_DICT_DEFAULT = "system/blockMeshDict.3D"

AXES = (
    dimension_axis(
        "dimension", mesh_step_id="mesh",
        solver_coefficients=(ELECTRO_PROPERTIES, _MONODOMAIN_SOLVER_COEFFS),
        ecg_verification_scope=_ECG_VERIFICATION_MODEL,
    ),
    hex_number_cells_axis("numberCells"),
    tet_number_cells_axis("tetNumberCells", gmsh_step_id="gmsh"),
)

#: Settled by a real run (module docstring, PE1/PE3): every cardiacFoam
#: solve step here writes `.withDefaultValues` (the pseudo-ECG verifier's
#: myocardium domain does call `electroModel::end()`).
_SOLVE_OUTPUTS = (
    WITH_DEFAULT_VALUES,
    "postProcessing/*_cells.dat",
    "postProcessing/pseudoECG.dat",
    "postProcessing/manufacturedPseudoECG_ECG.dat",
    "postProcessing/manufacturedPseudoECGSummary_ECG.dat",
)

RECORD = TutorialRecord(
    name="manufacturedMonodomainPseudoECG",
    native_case_relpath="manufacturedSolutions/monodomainPseudoECG",
    axes=AXES,
    workflow_steps=(
        block_mesh_step(
            BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",), default_dict=_MESH_DICT_DEFAULT,
        ),
        *gmsh_route(_TET_TEMPLATE, _TET_MESH, "internal"),
        solve_step(_SOLVE_OUTPUTS),
    ),
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
    },
    variant_selector="mesh",
    default_variant="hex",
)
