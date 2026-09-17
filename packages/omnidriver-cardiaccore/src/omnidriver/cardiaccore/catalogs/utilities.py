"""Native cardiacCore utilities, declared from native source/docs."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.utility_catalog import (
    PositionalArg,
    ProducesEntry,
    UtilityFlag,
    UtilityManifest,
)


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
    "newVtkUnstructuredToFoam": UtilityManifest(
        name="newVtkUnstructuredToFoam",
        description="Import a legacy ASCII VTK unstructured grid as an OpenFOAM mesh and cell fields.",
        purpose=(
            "Reads an ASCII VTK UNSTRUCTURED_GRID, writes constant/polyMesh with a "
            "single default boundary patch, and imports scalar, vector, and tensor "
            "CELL_DATA into current-time volume fields. Equivalent POINT_DATA is "
            "averaged onto cells; unit-vector point data is renormalized after averaging. "
            "The import does not scale geometry and writes every imported field "
            "dimensionless, because VTK carries no OpenFOAM dimensions."
        ),
        inputs=("<vtk-file>",),
        requires_mesh=False,
        flags=(),
        example="newVtkUnstructuredToFoam myMesh.vtk -case ./myCase",
        category="io-conversion",
        source_path=_SOURCE,
        positional_args=(
            PositionalArg(
                "vtk_file",
                "path",
                "Input legacy ASCII VTK UNSTRUCTURED_GRID file.",
            ),
        ),
        produces=(
            ProducesEntry(
                "vtk_imported_polymesh",
                "constant/polyMesh",
                "openfoam_polymesh",
                "Imported OpenFOAM mesh; all faces are assigned to the default patch.",
                "newVtkUnstructuredToFoam",
            ),
            ProducesEntry(
                "vtk_imported_fields",
                "<current-time>/<vtk-cell-data-name>",
                "openfoam_field",
                "One dimensionless volume field for each supported VTK CELL_DATA or POINT_DATA array.",
                "newVtkUnstructuredToFoam",
                optional=True,
            ),
        ),
    ),
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
        ("system/setCardiacAnatomyDict", "0/apicobasal", "0/intraventricular"),
        (
            ProducesEntry("aha_segment", "0/AHA_Segment", "openfoam_field", "AHA segment label", "setCardiacAnatomy"),
            ProducesEntry("aha_angle", "0/aha_angle", "openfoam_field", "Short-axis polar angle", "setCardiacAnatomy"),
        ),
    ),
    "setPurkinjeSlab": _manifest(
        "setPurkinjeSlab",
        "Mark the sub-endocardial Purkinje slab and scale conductivity there.",
        ("system/setPurkinjeSlabDict", "0/transmural", "0/Conductivity"),
        (
            ProducesEntry("purkinje_layer", "0/PurkinjeLayer", "openfoam_field", "Purkinje slab mask", "setPurkinjeSlab"),
            ProducesEntry("conductivity", "0/Conductivity", "openfoam_field", "Conductivity tensor updated in the Purkinje slab", "setPurkinjeSlab"),
        ),
    ),
    "setPurkinjeMorphometry": _manifest(
        "setPurkinjeMorphometry",
        "Prepare Purkinje morphometry regions and terminal-weight fields.",
        ("system/setPurkinjeMorphometryDict", "0/apicobasal", "0/intraventricular"),
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
            "system/coordinatesConventionDict",
            "0/transmural",
            "0/intraventricular",
            "0/apicobasal",
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
    "refine1Dgraph": UtilityManifest(
        name="refine1Dgraph",
        description="Subdivide VTK line-graph segments longer than a maximum edge length.",
        purpose=(
            "Reads a legacy ASCII VTK line graph and splits every segment longer than "
            "-maxEdgeLength into ceil(length/maxEdgeLength) equal straight sub-segments, "
            "writing VTK POLYDATA 2-point lines. Inserted points lie on the chord between the "
            "segment endpoints. Original node ids are kept; inserted nodes "
            "get interpolated point data and the internal node role, and sub-segments "
            "inherit parent cell data plus parentCellId. -maxEdgeLength is in metres; "
            "scale it to the mesh's length unit (e.g. 0.3 for a millimetre mesh)."
        ),
        inputs=("<input-vtk>",),
        requires_mesh=False,
        flags=(
            UtilityFlag(
                "-maxEdgeLength",
                "Maximum segment length after refinement, in metres; scale it for non-metre meshes.",
                takes_value=True,
                argument_kind="scalar",
                default="3e-4",
            ),
            UtilityFlag(
                "-internalRole",
                "Node-role value written on inserted nodes (default: 1 for NodeType, 0 for nodeRole/node_role/role).",
                takes_value=True,
                argument_kind="label",
            ),
        ),
        example=(
            "refine1Dgraph postProcessing/generatePurkinjeTree/purkinje.vtk "
            "postProcessing/generatePurkinjeTree/purkinje-refined.vtk -maxEdgeLength 3e-4"
        ),
        category="io-conversion",
        source_path=_SOURCE,
        positional_args=(
            PositionalArg("input", "path", "Input legacy ASCII VTK line graph."),
            PositionalArg("output", "path", "Output legacy ASCII VTK POLYDATA line graph."),
        ),
        produces=(
            ProducesEntry("refined_purkinje_vtk", "<output-vtk>", "vtk_polydata", "Refined line graph at the caller-selected output path", "refine1Dgraph"),
        ),
    ),
    "1DgraphToFoam": UtilityManifest(
        name="1DgraphToFoam",
        description="Convert a VTK line graph into the cardiacFoam Purkinje graph dictionary.",
        purpose=(
            "Reads a legacy ASCII VTK line graph and writes constant/<name> with rootNode, "
            "pvjNodes, pvjLocations, conductionEdges, points, edges, pointFields and edgeFields. "
            "Each VTK line segment becomes one conductionEdges entry; refine1Dgraph sets a "
            "maximum edge length beforehand."
        ),
        inputs=("<vtk-file>",),
        requires_mesh=False,
        flags=(
            UtilityFlag(
                "-name",
                "Graph object name written under constant/.",
                takes_value=True,
                argument_kind="word",
                default="purkinjeGraph",
            ),
        ),
        example="1DgraphToFoam postProcessing/generatePurkinjeTree/purkinje.vtk -case . -name purkinjeGraph",
        category="io-conversion",
        source_path=_SOURCE,
        positional_args=(
            PositionalArg("vtk_file", "path", "Input legacy ASCII VTK line graph (VTK_LINE, VTK_POLY_LINE or POLYDATA LINES)."),
        ),
        produces=(
            ProducesEntry("purkinje_graph", "constant/<name>", "openfoam_dict", "Solver-facing Purkinje graph dictionary; name defaults to purkinjeGraph", "1DgraphToFoam"),
        ),
    ),
    "foamTo1Dgraph": UtilityManifest(
        name="foamTo1Dgraph",
        description="Export an OpenFOAM Purkinje graph dictionary as a legacy VTK line graph.",
        purpose=(
            "Reads constant/<graphName>, requiring points and conductionEdges, and writes "
            "postProcessing/foamTo1Dgraph/<graphName>.vtk. The VTK contains line cells, "
            "per-edge conductance and length, and per-node PVJ resistance when the graph "
            "contains matching pvjNodes and pvjResistances."
        ),
        inputs=("constant/<graphName>",),
        requires_mesh=False,
        flags=(),
        example="foamTo1Dgraph purkinjeGraphScar -case .",
        category="io-conversion",
        source_path=_SOURCE,
        positional_args=(
            PositionalArg(
                "graphName",
                "word",
                "Name of the graph dictionary read from constant/.",
            ),
        ),
        produces=(
            ProducesEntry(
                "purkinje_graph_vtk",
                "postProcessing/foamTo1Dgraph/<graphName>.vtk",
                "vtk_unstructured_grid",
                "VTK inspection export of the graph dictionary.",
                "foamTo1Dgraph",
            ),
        ),
    ),
    "setCardiacScar": UtilityManifest(
        name="setCardiacScar",
        description="Create myocardial scar severity fields from a selected cell region and optionally scale conductivity.",
        purpose=(
            "Reads system/setCardiacScarDict and resolves its required selection as an "
            "OpenFOAM cellSet or a VTU cell-data selection. It always writes Scar and "
            "ScarSeverity (or their configured names), writes depth/channel/region debug "
            "fields only when writeDebugFields is true, and optionally updates Conductivity "
            "plus existing intracellular/extracellular conductivity tensors. The source "
            "supports topological or centre-to-centre euclidean depth; euclidean depth has "
            "length dimensions, while topological depth is dimensionless."
        ),
        inputs=(
            "system/setCardiacScarDict",
            "<selection named by system/setCardiacScarDict>",
        ),
        requires_mesh=True,
        flags=(),
        example="setCardiacScar -case .",
        category="field-setup",
        source_path=_SOURCE,
        positional_args=(),
        produces=(
            ProducesEntry("scar", "<current-time>/Scar", "openfoam_field", "Scar-selection mask; the configured field name may differ.", "setCardiacScar"),
            ProducesEntry("scar_severity", "<current-time>/ScarSeverity", "openfoam_field", "Dimensionless scar severity field; the configured field name may differ.", "setCardiacScar"),
            ProducesEntry("scar_depth", "<current-time>/ScarDepth", "openfoam_field", "Scar depth; length for euclidean mode and dimensionless for topological mode. Written only with writeDebugFields true.", "setCardiacScar", optional=True),
            ProducesEntry("scar_normalized_depth", "<current-time>/ScarNormalizedDepth", "openfoam_field", "Per-component normalized scar depth, written only with writeDebugFields true.", "setCardiacScar", optional=True),
            ProducesEntry("scar_channel", "<current-time>/ScarChannel", "openfoam_field", "Channel-selection mask, written only with writeDebugFields true.", "setCardiacScar", optional=True),
            ProducesEntry("scar_region_id", "<current-time>/ScarRegionID", "openfoam_field", "Scar connected-component identifier, written only with writeDebugFields true.", "setCardiacScar", optional=True),
            ProducesEntry("scar_channel_region_id", "<current-time>/ScarChannelRegionID", "openfoam_field", "Channel connected-component identifier, written only with writeDebugFields true.", "setCardiacScar", optional=True),
            ProducesEntry("conductivity", "<current-time>/Conductivity", "openfoam_field", "Conductivity tensor updated when scaleConductivity is true.", "setCardiacScar", optional=True),
            ProducesEntry("conductivity_intracellular", "<current-time>/ConductivityIntracellular", "openfoam_field", "Existing intracellular tensor updated when conductivity scaling is enabled.", "setCardiacScar", optional=True),
            ProducesEntry("conductivity_extracellular", "<current-time>/ConductivityExtracellular", "openfoam_field", "Existing extracellular tensor updated when conductivity scaling is enabled.", "setCardiacScar", optional=True),
        ),
    ),
    "setPurkinjeScar": UtilityManifest(
        name="setPurkinjeScar",
        description="Map myocardial scar severity and region fields onto a Purkinje graph.",
        purpose=(
            "Reads system/setPurkinjeScarDict, current-time severity and region fields, "
            "and a graph dictionary from constant/. It updates each graph edge's conductance "
            "from endpoint scar severity and adds PVJ resistances, writing constant/<outputGraph>. "
            "Without outputGraph, the native default is <inputGraph>Scar."
        ),
        inputs=(
            "system/setPurkinjeScarDict",
            "<current-time>/<severityField named by system/setPurkinjeScarDict>",
            "<current-time>/<regionField named by system/setPurkinjeScarDict>",
            "constant/<inputGraph named by system/setPurkinjeScarDict>",
        ),
        requires_mesh=True,
        flags=(),
        example="setPurkinjeScar -case .",
        category="field-setup",
        source_path=_SOURCE,
        positional_args=(),
        produces=(
            ProducesEntry(
                "scar_coupled_purkinje_graph",
                "constant/<outputGraph>",
                "openfoam_dict",
                "Purkinje graph with scar-adjusted conductionEdges and pvjResistances; defaults to <inputGraph>Scar.",
                "setPurkinjeScar",
            ),
        ),
    ),
}
