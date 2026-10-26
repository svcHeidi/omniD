"""cardiacCore's shared anatomy input and workflow steps.
``step()`` mirrors native ``Allrun``'s ``<utility> -case .``; ``ANATOMY`` has no native case location, so a study supplies ``--input anatomy=<bundle dir>``; no record declares it today.
"""

from __future__ import annotations

from omnidriver.core.tutorial_records import RecordInput, WorkflowStep
from omnidriver.openfoam.polymesh import POLY_MESH_FILES

#: The three convention-named fields every utility reads via
#: ``coordinatesConventionDict``'s ``uvc_*`` names.
UVC = ("0/uvc_transmural", "0/uvc_intraventricular", "0/uvc_longitudinal")

#: A bring-your-own anatomy input: no native location, so
#: ``--input anatomy=<bundle dir>`` is always required of a record that declares it.
ANATOMY = RecordInput(
    name="anatomy",
    files=tuple((path, path) for path in (*POLY_MESH_FILES, "0/fiber", "0/sheet", *UVC)),
)

#: Every utility reads this convention dictionary, though native ``Allrun``
#: never declares it as a dependency.
CONV = "system/coordinatesConventionDict"


def step(step_id: str, utility: str, *, consumes: tuple[str, ...], produces: tuple[str, ...]) -> WorkflowStep:
    return WorkflowStep(
        step_id=step_id,
        command=(utility, "-case", "."),
        consumes=(f"system/{utility}Dict", *consumes),
        produces=produces,
    )


#: ``generatePurkinjeTree``'s outputs, shared by the endocardial and pig-transmural records.
TREE_OUT = (
    *(f"constant/polyMesh/sets/{name}" for name in ("LVEndoFaces", "RVEndoFaces", "EpiFaces", "RVSeptalEndoFaces")),
    *(f"postProcessing/generatePurkinjeTree/{name}" for name in (
        "purkinje.vtk", "lv-purkinje.vtk", "rv-purkinje.vtk", "generation_params.txt",
    )),
)
