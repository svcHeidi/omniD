"""The idealized-heart records: three variants under ``idealizedHeart`` in the tutorials root on its one shared mesh (Git LFS), needing no ``--input``.
The mesh is the native ``mesh`` input, overlaid onto the staged variant as each variant's ``Allrun`` copies it. They use the ``cobiveco`` convention, so steps declare their own field paths instead of ``anatomy.py``'s ``uvc_*``.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, TutorialRecord

from .anatomy import CONV, MESH, TREE_OUT, step

#: The idealized mesh's coordinate fields (cobiveco naming): ``tm``
#: 1=endocardium/0=epicardium, ``tv`` 0=LV/1=RV, ``apicobasal`` 0=apex/1=base,
#: per this mesh's own ``coordinatesConventionDict``.
COBIVECO = ("0/tm", "0/tv", "0/apicobasal")

#: generatePurkinjeTree's outputs under ``coordinateSystem cobiveco``: no
#: ``RVSeptalEndoFaces`` set is built, since cobiveco solves transmural/
#: intraventricular membership per chamber, so the septum already reads
#: endocardial from both sides.
COBIVECO_TREE_OUT = tuple(path for path in TREE_OUT if "RVSeptalEndoFaces" not in path)

#: This mesh's polyMesh in full: it also carries `cellZones`/`faceZones`/
#: `pointZones`, which `anatomy.MESH`'s five files omit.
IDEALIZED_MESH = MESH + tuple(
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
    produces=("0/Conductivity",),
)

ANATOMY_STEP = step(
    "anatomy", "setCardiacAnatomy",
    consumes=(CONV, "0/apicobasal", "0/tv"),
    produces=("0/aha_angle", "0/aha_z", "0/phiRV", "0/groove_interface", "0/AHA_Segment"),
)

MORPHOMETRY = step(
    "purkinje_morphometry", "setPurkinjeMorphometry",
    consumes=(CONV, "0/apicobasal", "0/tv"),
    produces=(
        "0/PurkinjeLongitudinalRegion", "0/PurkinjeCircumferentialRegion",
        "0/PurkinjeTerminalWeightSubendocardial", "0/PurkinjeTerminalWeightIntramural",
    ),
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
            produces=("0/PurkinjeLayer", "0/Conductivity"),
        ),
        MORPHOMETRY,
    ),
)

#: Mirrors humanEndocardial's workflow (conductivity, anatomy,
#: generatePurkinjeTree with LV/RV allLeaves+endocardial); `1DgraphToFoam` is
#: not a step.
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
            produces=COBIVECO_TREE_OUT,
        ),
    ),
)

#: Mirrors pigMorphometricTransmural's workflow (conductivity, anatomy,
#: morphometry, generatePurkinjeTree with LV weightedField+transmural and RV
#: allLeaves+transmural).
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
            produces=COBIVECO_TREE_OUT,
        ),
    ),
)
