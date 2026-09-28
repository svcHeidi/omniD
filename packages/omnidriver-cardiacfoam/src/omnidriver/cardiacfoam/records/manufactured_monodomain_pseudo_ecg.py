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

from omnidriver.core.tutorial_records import DefaultArgument, TutorialRecord, WorkflowStep

from .case_outputs import ELECTRO_PROPERTIES, POLY_MESH_OUTPUTS, WITH_DEFAULT_VALUES, gmsh_to_foam_outputs
from .manufactured_solution_axes import (
    BLOCK_MESH_DICT_DOCUMENTS, MESH_DICT_KEY, TET_DIMENSIONS,
    dimension_axis, hex_number_cells_axis, tet_number_cells_axis,
)

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
        WorkflowStep(
            step_id="mesh", command=("blockMesh",),
            default_arguments=(DefaultArgument(key=MESH_DICT_KEY, values=(_MESH_DICT_DEFAULT,)),),
            consumes=BLOCK_MESH_DICT_DOCUMENTS + ("system/controlDict",),
            produces=POLY_MESH_OUTPUTS,
        ),
        WorkflowStep(
            step_id="gmsh",
            command=("gmsh", "-3", _TET_TEMPLATE, "-o", _TET_MESH, "-format", "msh2"),
            consumes=(_TET_TEMPLATE,),
            produces=(_TET_MESH,),
        ),
        WorkflowStep(
            step_id="gmshToFoam", command=("gmshToFoam", _TET_MESH),
            consumes=(_TET_MESH,),
            produces=gmsh_to_foam_outputs("internal"),
        ),
        WorkflowStep(step_id="checkMesh", command=("checkMesh",)),
        WorkflowStep(
            step_id="solve", command=("cardiacFoam",),
            consumes=(
                "system/controlDict", "system/fvSchemes", "system/fvSolution",
                "constant/physicsProperties", ELECTRO_PROPERTIES,
            ),
            produces=_SOLVE_OUTPUTS,
        ),
    ),
    workflow_variants={
        "hex": ("mesh", "solve"),
        "tet": ("gmsh", "gmshToFoam", "checkMesh", "solve"),
    },
    variant_selector="mesh",
    default_variant="hex",
    variant_constraints={"tet": {"dimension": TET_DIMENSIONS}},
)
