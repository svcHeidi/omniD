"""cardiacCore's shared anatomy input and workflow steps.

``ANATOMY`` (mesh, ``0/fiber``, ``0/sheet``, ``uvc_*``) has no native case
location, so a study always supplies ``--input anatomy=<bundle dir>``.
``step()`` mirrors native ``Allrun``'s own ``<utility> -case .`` invocation;
every utility reads ``system/coordinatesConventionDict`` (``CONV``) even
though native ``Allrun`` never declares it as a dependency.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, WorkflowStep

#: constant/polyMesh's five files, restated here rather than imported from
#: cardiacFOAM, which cardiacCore must not know about (package boundary).
MESH = tuple(f"constant/polyMesh/{name}" for name in ("boundary", "faces", "neighbour", "owner", "points"))

#: The three convention-named fields every utility reads via
#: ``coordinatesConventionDict``'s ``uvc_*`` names (native README's "Local
#: case contract").
UVC = ("0/uvc_transmural", "0/uvc_intraventricular", "0/uvc_longitudinal")

#: The one input every cardiacCore record needs: no native location, so
#: ``--input anatomy=<bundle dir>`` is always required.
ANATOMY = RecordInput(
    name="anatomy",
    files=tuple((path, path) for path in (*MESH, "0/fiber", "0/sheet", *UVC)),
)

#: Every utility reads this, even though no native ``Allrun``/factory
#: ``consumes`` declaration ever names it.
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

#: ``setCardiacAnatomy`` also writes ``0/phiRV`` and ``0/groove_interface``,
#: which every record's produces must declare.
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

#: ``generatePurkinjeTree``'s outputs, shared by ``humanEndocardial``/
#: ``pigMorphometricTransmural``. Declared here though unused by
#: ``humanSlab``, so those records need not restate them.
TREE_OUT = (
    *(f"constant/polyMesh/sets/{name}" for name in ("LVEndoFaces", "RVEndoFaces", "EpiFaces", "RVSeptalEndoFaces")),
    *(f"postProcessing/generatePurkinjeTree/{name}" for name in (
        "purkinje.vtk", "lv-purkinje.vtk", "rv-purkinje.vtk", "generation_params.txt",
    )),
)
