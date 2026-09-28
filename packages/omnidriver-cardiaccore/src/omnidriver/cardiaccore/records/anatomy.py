"""cardiacCore's shared anatomy input and workflow steps (step S: supplied
inputs, docs/superpowers/specs/2026-09-28-supplied-inputs-design.md §1.3).

Every native cardiacCore case reads a patient's mesh and five fields
(the mesh, ``0/fiber``, ``0/sheet`` and the three ``uvc_*`` convention
fields) that are NOT in the native case folder (``system/`` only) --
they live only in a bundle the owner's checkout carries, git-ignored
(design §1.2). ``ANATOMY`` is the one input every cardiacCore record needs;
it has no native location, so a study must always supply
``--input anatomy=<bundle dir>``.

``step()`` builds one utility's ``WorkflowStep`` the way every native
``Allrun`` runs it: ``<utility> -case .``, with ``system/<utility>Dict``
plus whatever fields it reads named in ``consumes`` (design §1.3). Every
utility also reads ``system/coordinatesConventionDict`` (``CONV``) -- the
native ``Allrun`` never names it as a dependency, but every utility's
source does (design §1.1's "two drifts the records must fix").
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, WorkflowStep

#: ``constant/polyMesh``'s five files -- the shape every OpenFOAM mesh
#: takes, reused verbatim from cardiacFOAM's own declaration would import
#: cardiac vocabulary into a shared module; restated here instead (one
#: reality is about the OpenFOAM-owned *validator/catalog* half, not about
#: importing across the two cardiac packages, which CLAUDE.md's package
#: table forbids either way -- cardiacCore must not know cardiacFOAM).
MESH = tuple(f"constant/polyMesh/{name}" for name in ("boundary", "faces", "neighbour", "owner", "points"))

#: The native README's "Local case contract" (design §1.3): the three
#: convention-named fields every utility reads via
#: ``coordinatesConventionDict``'s ``uvc_*`` names.
UVC = ("0/uvc_transmural", "0/uvc_intraventricular", "0/uvc_longitudinal")

#: The one input every cardiacCore record needs: no native location, so
#: ``--input anatomy=<bundle dir>`` is always required (design §1.3, D5).
ANATOMY = RecordInput(
    name="anatomy",
    files=tuple((path, path) for path in (*MESH, "0/fiber", "0/sheet", *UVC)),
)

#: Every utility reads this, even though no native ``Allrun``/factory
#: ``consumes`` declaration ever named it (design §1.2's first drift).
CONV = "system/coordinatesConventionDict"


def step(step_id: str, utility: str, *, consumes: tuple[str, ...], produces: tuple[str, ...]) -> WorkflowStep:
    return WorkflowStep(
        step_id=step_id,
        command=(utility, "-case", "."),
        consumes=(f"system/{utility}Dict", *consumes),
        produces=produces,
    )


CONDUCTIVITY = step(
    "conductivity", "setCardiacConductivity",
    consumes=(*MESH, "0/fiber", "0/sheet"),
    produces=("0/Conductivity",),
)

#: Design §1.2's second drift: ``setCardiacAnatomy`` also writes
#: ``0/phiRV`` and ``0/groove_interface`` -- omitted from the old factory's
#: ``UTILITY_MANIFESTS``/README, but a real one every record's restage (C11)
#: must carry.
ANATOMY_STEP = step(
    "anatomy", "setCardiacAnatomy",
    consumes=(CONV, "0/uvc_longitudinal", "0/uvc_intraventricular"),
    produces=("0/aha_angle", "0/phiRV", "0/groove_interface", "0/AHA_Segment"),
)

MORPHOMETRY = step(
    "purkinje_morphometry", "setPurkinjeMorphometry",
    consumes=(CONV, "0/uvc_longitudinal", "0/uvc_intraventricular"),
    produces=(
        "0/PurkinjeLongitudinalRegion", "0/PurkinjeCircumferentialRegion",
        "0/PurkinjeTerminalWeightSubendocardial", "0/PurkinjeTerminalWeightIntramural",
    ),
)

#: ``generatePurkinjeTree``'s outputs (design §1.3), shared by
#: ``humanEndocardial``/``pigMorphometricTransmural`` (S4). Declared here,
#: unused by ``humanSlab`` (S3), so the S4 records need not restate them.
TREE_OUT = (
    *(f"constant/polyMesh/sets/{name}" for name in ("LVEndoFaces", "RVEndoFaces", "EpiFaces", "RVSeptalEndoFaces")),
    *(f"postProcessing/generatePurkinjeTree/{name}" for name in (
        "purkinje.vtk", "lv-purkinje.vtk", "rv-purkinje.vtk", "generation_params.txt",
    )),
)
