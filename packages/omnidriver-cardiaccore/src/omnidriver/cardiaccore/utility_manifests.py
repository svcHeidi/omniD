"""The four ``bivCase/Allrun`` utilities, declared from native source/docs."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.utility_catalog import ProducesEntry, UtilityManifest


_SOURCE = Path(__file__).resolve()


def _manifest(
    name: str,
    description: str,
    inputs: tuple[str, ...],
    produces: tuple[ProducesEntry, ...],
) -> UtilityManifest:
    return UtilityManifest(
        name=name,
        description=description,
        purpose="Declared from cardiacCore's native bivCase wrapper and utility documentation.",
        inputs=inputs,
        requires_mesh=True,
        flags=(),
        example=f"{name} -case <case>",
        category="field-setup",
        source_path=_SOURCE,
        produces=produces,
    )


UTILITY_MANIFESTS = {
    "setCardiacConductivity": _manifest(
        "setCardiacConductivity",
        "Build orthotropic conductivity tensors from fiber and sheet fields.",
        ("system/setCardiacConductivityDict", "0/fiber", "0/sheet"),
        (
            ProducesEntry("conductivity", "0/Conductivity", "openfoam_field", "Conductivity tensor", "setCardiacConductivity"),
            ProducesEntry("conductivity_intracellular", "0/ConductivityIntracellular", "openfoam_field", "Optional intracellular tensor", "setCardiacConductivity", optional=True),
            ProducesEntry("conductivity_extracellular", "0/ConductivityExtracellular", "openfoam_field", "Optional extracellular tensor", "setCardiacConductivity", optional=True),
        ),
    ),
    "setCardiacAnatomy": _manifest(
        "setCardiacAnatomy",
        "Assign AHA segment labels and their short-axis angle.",
        ("system/setCardiacAnatomyDict", "0/uvc_longitudinal", "0/uvc_intraventricular"),
        (
            ProducesEntry("aha_segment", "0/AHA_Segment", "openfoam_field", "AHA segment label", "setCardiacAnatomy"),
            ProducesEntry("aha_angle", "0/aha_angle", "openfoam_field", "Short-axis polar angle", "setCardiacAnatomy"),
        ),
    ),
    "setPurkinjeSlab": _manifest(
        "setPurkinjeSlab",
        "Mark the sub-endocardial Purkinje slab and scale conductivity there.",
        ("system/setPurkinjeSlabDict", "0/uvc_transmural", "0/Conductivity"),
        (
            ProducesEntry("purkinje_layer", "0/PurkinjeLayer", "openfoam_field", "Purkinje slab mask", "setPurkinjeSlab"),
            ProducesEntry("conductivity", "0/Conductivity", "openfoam_field", "Conductivity tensor updated in the Purkinje slab", "setPurkinjeSlab"),
        ),
    ),
    "setPurkinjeMorphometry": _manifest(
        "setPurkinjeMorphometry",
        "Prepare Purkinje morphometry regions and terminal-weight fields.",
        ("system/setPurkinjeMorphometryDict", "0/uvc_longitudinal", "0/uvc_intraventricular"),
        (
            ProducesEntry("purkinje_longitudinal_region", "0/PurkinjeLongitudinalRegion", "openfoam_field", "Longitudinal region labels", "setPurkinjeMorphometry"),
            ProducesEntry("purkinje_circumferential_region", "0/PurkinjeCircumferentialRegion", "openfoam_field", "Circumferential region labels", "setPurkinjeMorphometry"),
            ProducesEntry("purkinje_terminal_weight_subendocardial", "0/PurkinjeTerminalWeightSubendocardial", "openfoam_field", "Sub-endocardial terminal weights", "setPurkinjeMorphometry"),
            ProducesEntry("purkinje_terminal_weight_intramural", "0/PurkinjeTerminalWeightIntramural", "openfoam_field", "Intramural terminal weights", "setPurkinjeMorphometry"),
        ),
    ),
    "generatePurkinjeTree": _manifest(
        "generatePurkinjeTree",
        "Generate explicit LV/RV endocardial Purkinje trees and inspection VTKs.",
        (
            "system/generatePurkinjeTreeDict",
            "system/uvcConventionDict",
            "0/uvc_transmural",
            "0/uvc_intraventricular",
            "0/uvc_longitudinal",
        ),
        (
            ProducesEntry("lv_endo_faces", "constant/polyMesh/sets/LVEndoFaces", "openfoam_face_set", "Generated LV endocardial face set", "generatePurkinjeTree"),
            ProducesEntry("rv_endo_faces", "constant/polyMesh/sets/RVEndoFaces", "openfoam_face_set", "Generated RV endocardial face set", "generatePurkinjeTree"),
            ProducesEntry("epi_faces", "constant/polyMesh/sets/EpiFaces", "openfoam_face_set", "Generated epicardial face set", "generatePurkinjeTree"),
            ProducesEntry("rv_septal_endo_faces", "constant/polyMesh/sets/RVSeptalEndoFaces", "openfoam_face_set", "Generated RV septal-recovery face set", "generatePurkinjeTree"),
            ProducesEntry("purkinje_vtk", "postProcessing/generatePurkinjeTree/purkinje.vtk", "vtk_polydata", "Glued solver-facing Purkinje tree", "generatePurkinjeTree"),
            ProducesEntry("lv_purkinje_vtk", "postProcessing/generatePurkinjeTree/lv-purkinje.vtk", "vtk_polydata", "LV inspection tree", "generatePurkinjeTree"),
            ProducesEntry("rv_purkinje_vtk", "postProcessing/generatePurkinjeTree/rv-purkinje.vtk", "vtk_polydata", "RV inspection tree", "generatePurkinjeTree"),
            ProducesEntry("purkinje_generation_parameters", "postProcessing/generatePurkinjeTree/generation_params.txt", "text", "Effective native tree-generation parameters", "generatePurkinjeTree"),
        ),
    ),
}
