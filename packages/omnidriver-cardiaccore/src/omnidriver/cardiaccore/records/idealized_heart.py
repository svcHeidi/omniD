"""The idealized-heart records: three variants on cardiacFOAM's own idealized
biventricular mesh, committed natively (``cases/idealized*``, Git LFS); no
``--input`` is needed. They use the ``cobiveco`` convention (``tm``/``tv``/
``apicobasal``), so steps here declare their own field paths rather than
reusing ``anatomy.py``'s ``uvc_*`` constants.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, TutorialRecord

from .anatomy import CONV, MESH, TREE_OUT, step

#: The idealized mesh's own coordinate fields (cobiveco naming): ``tm``
#: 1=endocardium/0=epicardium, ``tv`` 0=LV/1=RV, ``apicobasal`` 0=apex/1=base,
#: per this mesh's own ``coordinatesConventionDict`` (confirmed against its
#: ENDO_LV/ENDO_RV/EPI/BASE boundary patches).
COBIVECO = ("0/tm", "0/tv", "0/apicobasal")

#: generatePurkinjeTree's outputs under ``coordinateSystem cobiveco``: no
#: ``RVSeptalEndoFaces`` set is built, since cobiveco solves transmural/
#: intraventricular membership per chamber, so the septum already reads
#: endocardial from both sides (per the native tutorial's own README).
COBIVECO_TREE_OUT = tuple(path for path in TREE_OUT if "RVSeptalEndoFaces" not in path)

#: This mesh's own polyMesh, in full: `anatomy.MESH` lists only the five
#: files `humanSlab`'s bundle has; this committed mesh also carries
#: `cellZones`/`faceZones`/`pointZones`, which restaging must also copy.
IDEALIZED_MESH = MESH + tuple(
    f"constant/polyMesh/{name}" for name in ("cellZones", "faceZones", "pointZones")
)


def _mesh_input(native_case_relpath: str) -> RecordInput:
    """Declare ``constant/polyMesh`` as a native-location input.

    Staging excludes ``polyMesh`` unconditionally (a mesh is normally
    generated or supplied); this committed mesh has no generating step, so
    it must opt back into staging via a native-location ``RecordInput``,
    which needs no ``--input``.
    """
    return RecordInput(
        name="mesh",
        native_relpath=native_case_relpath,
        files=tuple((path, path) for path in IDEALIZED_MESH),
    )

CONDUCTIVITY = step(
    "conductivity", "setCardiacConductivity",
    # *IDEALIZED_MESH (all eight files, not anatomy.MESH's five): every input
    # destination must map to some step's consumes, and native `createMesh.H`
    # reads the full committed mesh (cellZones/faceZones/pointZones included)
    # as one `fvMesh` construction, never individually by name.
    consumes=(*IDEALIZED_MESH, "0/fiber", "0/sheet"),
    produces=("0/Conductivity",),
)

ANATOMY_STEP = step(
    "anatomy", "setCardiacAnatomy",
    consumes=(CONV, "0/apicobasal", "0/tv"),
    produces=("0/aha_angle", "0/phiRV", "0/groove_interface", "0/AHA_Segment"),
)

MORPHOMETRY = step(
    "purkinje_morphometry", "setPurkinjeMorphometry",
    consumes=(CONV, "0/apicobasal", "0/tv"),
    produces=(
        "0/PurkinjeLongitudinalRegion", "0/PurkinjeCircumferentialRegion",
        "0/PurkinjeTerminalWeightSubendocardial", "0/PurkinjeTerminalWeightIntramural",
    ),
)

#: idealizedHeart: mirrors humanSlab's own workflow (conductivity, anatomy,
#: slab, morphometry), on the idealized mesh instead of the supplied bivCase
#: bundle.
IDEALIZED_HEART = TutorialRecord(
    name="idealizedHeart",
    native_case_relpath="cases/idealizedHeart",
    inputs=(_mesh_input("cases/idealizedHeart"),),
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

#: idealizedHeartEndocardial: mirrors humanEndocardial's own workflow
#: (conductivity, anatomy, generatePurkinjeTree -- LV/RV allLeaves+
#: endocardial, per its own committed system/generatePurkinjeTreeDict).
#: 1DgraphToFoam is left out here too, matching native humanEndocardial.
IDEALIZED_HEART_ENDOCARDIAL = TutorialRecord(
    name="idealizedHeartEndocardial",
    native_case_relpath="cases/idealizedHeartEndocardial",
    inputs=(_mesh_input("cases/idealizedHeartEndocardial"),),
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

#: idealizedHeartPigTransmural: mirrors pigMorphometricTransmural's own
#: workflow (conductivity, anatomy, morphometry, generatePurkinjeTree -- LV
#: weightedField+transmural, RV allLeaves+transmural).
IDEALIZED_HEART_PIG_TRANSMURAL = TutorialRecord(
    name="idealizedHeartPigTransmural",
    native_case_relpath="cases/idealizedHeartPigTransmural",
    inputs=(_mesh_input("cases/idealizedHeartPigTransmural"),),
    workflow_steps=(
        CONDUCTIVITY,
        ANATOMY_STEP,
        MORPHOMETRY,
        # `0/PurkinjeTerminalWeight{Subendocardial,Intramural}` are
        # MORPHOMETRY's own `produces`, not authored inputs, so they are not
        # re-declared as consumed here (same reasoning as `0/Conductivity`
        # in `human_slab.py`).
        step(
            "purkinje_tree", "generatePurkinjeTree",
            consumes=(CONV, *COBIVECO),
            produces=COBIVECO_TREE_OUT,
        ),
    ),
)
