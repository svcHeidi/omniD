"""The idealized-heart records: three variants under ``idealizedHeart`` in the tutorials root on its one shared mesh (Git LFS), needing no ``--input``.
The mesh is the native ``mesh`` input, overlaid onto the staged variant as each variant's ``Allrun`` copies it. They use the ``cobiveco`` convention, so steps declare their own field paths instead of ``anatomy.py``'s ``uvc_*``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, TutorialRecord
from omnidriver.openfoam.polymesh import POLY_MESH_FILES

from .anatomy import CONV, step

#: The idealized mesh's coordinate fields, as its own ``coordinatesConventionDict`` names and orients them.
COBIVECO = ("0/tm", "0/tv", "0/apicobasal")

#: This mesh's polyMesh in full: it also carries `cellZones`/`faceZones`/`pointZones`.
IDEALIZED_MESH = POLY_MESH_FILES + tuple(
    f"constant/polyMesh/{name}" for name in ("cellZones", "faceZones", "pointZones")
)

#: The variants' shared mesh and fields: a variant folder has none until its
#: `Allrun` copies `../mesh` in, so the record reads it from the native
#: location, as a supplied input would be read.
MESH_INPUT = RecordInput(
    name="mesh",
    files=tuple((path, path) for path in (*IDEALIZED_MESH, "0/fiber", "0/sheet", *COBIVECO)),
    native_relpath="idealizedHeart/mesh",
)

CONDUCTIVITY = step(
    "conductivity", "setCardiacConductivity",
    # All eight mesh files: native `createMesh.H` reads the full mesh as one `fvMesh`.
    consumes=(*IDEALIZED_MESH, "0/fiber", "0/sheet"),
)

ANATOMY_STEP = step(
    "anatomy", "setCardiacAnatomy",
    consumes=(CONV, "0/apicobasal", "0/tv"),
)

#: Its AHA fields are ANATOMY_STEP's `produces`, not authored inputs.
MORPHOMETRY = step(
    "purkinje_morphometry", "setPurkinjeMorphometry",
    consumes=(CONV,),
)

#: Mirrors the native humanSlab variant's workflow (conductivity, anatomy, slab, morphometry).
IDEALIZED_HEART = TutorialRecord(
    name="idealizedHeart",
    native_case_relpath="idealizedHeart/humanSlab",
    inputs=(MESH_INPUT,),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        step(
            "purkinje_slab", "setPurkinjeSlab",
            consumes=(CONV, "0/tm"),
        ),
        MORPHOMETRY,
    ),
)

#: Mirrors humanEndocardial's workflow (conductivity, anatomy,
#: generatePurkinjeTree with LV/RV allLeaves+endocardial); the graph conversion
#: its Allrun ends with is not a step, since no manifest declares it.
IDEALIZED_HEART_ENDOCARDIAL = TutorialRecord(
    name="idealizedHeartEndocardial",
    native_case_relpath="idealizedHeart/humanEndocardial",
    inputs=(MESH_INPUT,),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        step(
            "purkinje_tree", "generatePurkinjeTree",
            consumes=(CONV, *COBIVECO),
        ),
    ),
)

#: Mirrors pigMorphometricTransmural's workflow (conductivity, anatomy,
#: morphometry, generatePurkinjeTree).
IDEALIZED_HEART_PIG_TRANSMURAL = TutorialRecord(
    name="idealizedHeartPigTransmural",
    native_case_relpath="idealizedHeart/pigMorphometricTransmural",
    inputs=(MESH_INPUT,),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        MORPHOMETRY,
        # `0/PurkinjeTerminalWeight{Subendocardial,Intramural}` are
        # MORPHOMETRY's `produces`, not authored inputs, so they are not
        # consumed here.
        step(
            "purkinje_tree", "generatePurkinjeTree",
            consumes=(CONV, *COBIVECO),
        ),
    ),
)
