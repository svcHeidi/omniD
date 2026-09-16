"""Canonical descriptions of the adapter's Python operations.

References use module:function syntax. Each entrypoint describes exact arguments
and side effects. Catalog discovery never invokes these trusted callables.
"""

from .support_boundary import CARDIACCORE_COBIVECO_TARGET

_PREFIX = "omnidriver.cardiaccore.operations"


def _entry(module, function, inputs, outputs, side_effects="None"):
    return {
        "callable": f"{_PREFIX}.{module}:{function}",
        "inputs": inputs, "outputs": outputs, "side_effects": side_effects,
    }


def _record(operation_id, purpose, applicability, entrypoints, primary, *,
            preconditions, failures, evidence, example, native_reader="pending"):
    first = entrypoints[primary]
    return {
        "id": operation_id, "version": 1,
        "status": {"array_api": "available", "native_file_reader": native_reader,
                   "workflow_integration": "pending"},
        "purpose": purpose, "applicability": applicability,
        "callable": first["callable"], "inputs": first["inputs"],
        "outputs": first["outputs"], "side_effects": first["side_effects"],
        "entrypoints": entrypoints, "preconditions": preconditions,
        "failure_conditions": failures, "evidence": evidence, "example": example,
    }


OPERATIONS = {}


def _add(operation_id, *args, **kwargs):
    OPERATIONS[operation_id] = _record(operation_id, *args, **kwargs)


_add(
    "cardiaccore.cobiveco.normalize.v1",
    "Convert explicitly identified raw CObiveco arrays to the supported cardiacCore UVC convention.",
    "Raw tv/tm/ab aligned to the same mesh entities; target values must match the converter's declared convention.",
    {
        "read_target": _entry("cobiveco", "read_cobiveco_target_convention",
            {"case_root": "Path to the selected case with system/uvcConventionDict."},
            "Literal transmural_min/max and lv_value/rv_value scalar mapping.",
            "Reads the selected dictionary; no writes or directive evaluation."),
        "normalize": _entry("cobiveco", "normalize_cobiveco_coordinates",
            {"tv": "Finite 1D array in [0,1].", "tm": "Finite 1D array in [0,1].",
             "ab": "Finite 1D array, same length as tv/tm.",
             "target_convention": {"description": "Required keyword: mapping read from the selected case.",
                                   "required_values": CARDIACCORE_COBIVECO_TARGET}},
            {"uvc_transmural": "1-tm", "uvc_intraventricular": "2*tv-1", "uvc_longitudinal": "Copy of ab"}),
    }, "normalize",
    preconditions=["Read the selected target case convention first.",
                   "Caller establishes alignment and raw CObiveco origin; this cannot be inferred from array values."],
    failures={"invalid_input": "ValueError for dimensionality, alignment, nonfinite values, tv/tm range or target mismatch; reader I/O errors propagate.",
              "missing_capability": "Native VTU field reading/writing is pending.",
              "scientific_interpretation": "Conversion success does not establish mesh validity or scientific suitability."},
    evidence=["Native cardiacCore coordinatesConvention.H and preparation cases; origins are not a build attestation."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.cobiveco import read_cobiveco_target_convention, normalize_cobiveco_coordinates\ntarget = read_cobiveco_target_convention(Path(case_root))\nfields = normalize_cobiveco_coordinates(tv, tm, ab, target_convention=target)",
)

_add(
    "cardiaccore.electrodes.reference_frame.v1",
    "Transfer explicitly selected comparative-reference electrodes through an anatomical LV frame.",
    "Packaged Strocchi-02 approximation; not patient-specific or default electrode placement.",
    {
        "frame": _entry("electrodes", "compute_lv_frame",
            {"points": "Finite Nx3 coordinates in one caller-declared length unit.",
             "uvc_intraventricular": "Finite length-N vector: negative=LV, positive=RV.",
             "uvc_longitudinal": "Finite length-N vector, 0=apex and 1=base."},
            "LVFrame with centre, orthonormal axes and length scale."),
        "encode": _entry("electrodes", "encode_to_local",
            {"point": "Length-3 coordinate.", "frame": "LVFrame returned by frame."}, "Dimensionless local coordinate."),
        "decode": _entry("electrodes", "decode_from_local",
            {"local_normalized": "Length-3 dimensionless coordinate.", "frame": "LVFrame",
             "axial_shift": "Optional fraction of frame length; default 0.0."}, "Coordinate in the input point unit."),
        "apply_reference": _entry("electrodes", "apply_reference_offsets",
            {"frame": "LVFrame", "axial_shift": "Optional keyword; default 0.0, explicit study choice."},
            "Mapping V1–V6 to coordinate lists in the input point unit."),
        "read_native_fields": _entry("electrodes", "read_native_electrode_fields",
            {"heart_vtk": "Native VTK/VTU path with UVC point or cell data.",
             "intraventricular_field": "Optional caller-selected intraventricular UVC array name; default uvc_intraventricular.",
             "longitudinal_field": "Optional caller-selected longitudinal UVC array name; default uvc_longitudinal."},
            "Points and point-aligned UVC arrays for frame construction."),
        "derive_bundle": _entry("electrodes", "derive_reference_offset_bundle",
            {"reference_heart_vtk": "Native reference VTK/VTU path.",
             "reference_electrodes": "Mapping of electrode names to reference coordinates in one declared unit.",
             "coordinate_unit": "Required source-coordinate-unit label; no conversion is inferred."},
            "Versioned JSON-serializable bundle of dimensionless offsets."),
        "apply_bundle": _entry("electrodes", "apply_offset_bundle_to_native_file",
            {"heart_vtk": "Native target VTK/VTU path.", "bundle": "Validated reference offset bundle.",
             "target_coordinate_unit": "Required target-coordinate-unit label; no conversion is inferred.",
             "axial_shift": "Optional fraction of target LV-frame length; default 0.0."},
            "Unit-labelled target electrode-position JSON payload."),
        "write_positions": _entry("electrodes", "write_electrode_positions",
            {"path": "Destination JSON path.", "positions": "Payload returned by apply_bundle."},
            "Stable JSON record of target electrode coordinates."),
    }, "frame",
    preconditions=["Explicitly select the reference-transfer method for the study.",
                   "Supply both chambers and LV apex/base bands; frame must be nondegenerate.",
                   "Declare the source and target coordinate units explicitly; this operation does not convert them."],
    failures={"invalid_input": "Frame construction rejects invalid shapes, nonfinite values, missing bands/chambers and degenerate axes.",
              "missing_capability": "Native VTK bridge requires the optional omnidriver-cardiaccore[vtk] dependency.",
              "scientific_interpretation": "Round-trip tests do not validate electrode placement for a new anatomy."},
    evidence=["Standalone normalize_electrode_positions.py method; packaged REFERENCE_LOCAL_OFFSETS retains its Strocchi-02 constants."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.electrodes import derive_reference_offset_bundle, apply_offset_bundle_to_native_file, write_electrode_positions\nbundle = derive_reference_offset_bundle(Path('reference.vtu'), reference_electrodes, coordinate_unit='mm')\npositions = apply_offset_bundle_to_native_file(Path('target.vtu'), bundle, target_coordinate_unit='mm')\nwrite_electrode_positions(Path('electrodePositions.json'), positions)",
)

_add(
    "cardiaccore.purkinje.seed_proposal.v1",
    "Propose Purkinje roots and apex-ward line ends from explicitly prepared native surfaces.",
    "Native LVEndoFaces/RVEndoFaces with aligned AHA/longitudinal arrays; not raw-coordinate surface reconstruction.",
    {"propose": _entry("purkinje", "deduce_seeds",
        {"points": "Finite Nx3 boundary points in one length unit.", "aha_segment": "Length-N labels.",
         "uvc_longitudinal": "Length-N vector.", "lv_endocardial_mask": "Length-N boolean mask.",
         "rv_endocardial_mask": "Length-N boolean mask."},
        "lv_seed, rv_seed, his_bundle_seed, lv_line_end and rv_line_end coordinate tuples.")}, "propose",
    preconditions=["Sample native surfaces onto the same points.",
                   "Use the method assumptions in cardiaccore_tree_validation.seed_placement.",
                   "A domain decision establishes whether this proposal method applies to the study."],
    failures={"invalid_input": "Raises on mismatched lengths, absent septal candidates or unavailable local gradient. Array preparation remains the caller's responsibility.",
              "missing_capability": "Native surface sampling and reviewed seed-dictionary mutation are pending.",
              "scientific_interpretation": "Proposal only; does not establish anatomical or electrophysiological acceptance."},
    evidence=["Native generatePurkinjeTree surface conventions and the adapter's packaged seed-proposal method."],
    example="from omnidriver.cardiaccore.operations.purkinje import deduce_seeds\nproposal = deduce_seeds(points, aha, longitudinal, lv_mask, rv_mask)",
)

_add(
    "cardiaccore.purkinje.coverage_observation.v1",
    "Report terminal occupancy and the existing baseline's coverage categories.",
    "Prepared terminal AHA labels and optional native tree-zone/endocardial labels.",
    {
        "report": _entry("purkinje", "coverage_report",
            {"terminal_aha_segment": "Terminal label vector.",
             "endocardial_aha_segment": "Optional actual endocardial labels; default None.",
             "terminal_tree_zone": "Optional aligned native CellZone vector; default None."},
            "Counts, starved/no-endocardium sets, required_missing, basal_warnings, totals and unrecognized labels."),
        "remap_rv": _entry("purkinje", "normalize_rv_septal_segments",
            {"aha_segment": "Label vector.", "tree_zone": "Optional aligned vector; default None."},
            "Copy of labels with native RV-tree recovered-septum mapping applied."),
    }, "report",
    preconditions=["Label sampling must use the selected mesh.",
                   "Without endocardial labels, absence of endocardium is unknown: empty sectors are still listed as starved.",
                   "Without tree-zone labels, no recovered-septum remapping is performed."],
    failures={"invalid_input": "Raises on misaligned tree-zone labels; callers prepare valid label vectors.",
              "missing_capability": "Native VTK sampling is pending.",
              "scientific_interpretation": "required_missing/basal_warnings use cardiaccore_tree_validation.baseline_coverage; these categories are not universal scientific acceptance."},
    evidence=["Standalone coverage method and native RV CellZone convention; preserved baseline categories are exposed in cardiaccore_tree_validation."],
    example="from omnidriver.cardiaccore.operations.purkinje import coverage_report\nreport = coverage_report(terminal_labels, endocardial_labels, terminal_tree_zone=zones)",
)

_add(
    "cardiaccore.coordinates.ring_closure.v1",
    "Check whether coordinate-selected LV/RV endocardial contours are closed at requested longitudinal levels.",
    "A VTK volume or boundary mesh with binary intraventricular, varying longitudinal, and transmural coordinate fields.",
    {
        "report": _entry("coordinates", "coordinate_endocardial_ring_closure_from_vtk",
            {"mesh_path": "Path to a VTK volume or boundary mesh.",
             "intraventricular_field": "Optional explicit binary LV/RV coordinate field name; omit every field/value to report generic topology-supported candidates.",
             "longitudinal_field": "Optional explicit continuous apicobasal coordinate field name.",
             "transmural_field": "Optional explicit continuous transmural coordinate field name.",
             "lv_value": "Optional explicit binary LV value.", "rv_value": "Optional explicit binary RV value.",
             "endocardial_value": "Optional explicit transmural endocardial boundary value.",
             "endocardial_band": "Positive coordinate tolerance selecting the endocardial boundary; default 0.05.",
             "ring_levels": "Finite non-empty longitudinal iso-values to inspect; default (0.2, 0.4, 0.6, 0.8).",
             "binary_tolerance": "Non-negative binary-chamber tolerance; default 1e-9."},
            "Coordinate-contract result and independent LV/RV contour-loop reports.",
            "Reads the supplied mesh only; does not mutate the case."),
    }, "report", native_reader="available_optional",
    preconditions=["Without declared fields, the operation evaluates normalized scalar candidates from their numerical structure and ring topology; field names are not treated as a convention.",
                   "A unique candidate identifies two chamber values but not which is LV or RV; declare every field/value when chamber naming matters.",
                   "Choose requested longitudinal levels away from valve/base openings when a closed ring is anatomically expected.",
                   "Use a VTK export that preserves the three coordinate fields."],
    failures={"invalid_input": "Raises for absent/non-finite fields, invalid values/tolerances, duplicate levels, or a mesh without boundary cells.",
              "missing_capability": "VTK reading requires the optional vtk extra.",
              "scientific_interpretation": "A failed coordinate contract or open contour identifies a geometry/coordinate prerequisite to investigate; it does not prescribe a UVC, CObiveco, or Purkinje-model change."},
    evidence=["CObiveco coordinate-result meshes; native cardiacCore UVC-convention surface preparation; owner-selected coordinate-ring closure criterion."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.coordinates import coordinate_endocardial_ring_closure_from_vtk\nreport = coordinate_endocardial_ring_closure_from_vtk(Path('result.vtu'))\n# Inspect report['coordinate_discovery']; explicitly name fields only when LV/RV labels are needed.",
)
_add(
    "cardiaccore.vtu.cell_set.v1",
    "Read explicit VTU cell IDs and render an OpenFOAM cellSet.",
    "Selections with GlobalCellIds or vtkOriginalCellIds in the target mesh's numbering.",
    {
        "read": _entry("vtu_selection", "read_cell_ids",
            {"path": "Explicit VTU Path.", "preferred_array": "Optional name tried before standard ID names; default None."},
            "Chosen array name and sorted unique IDs.", "Reads the supplied file; no writes."),
        "render": _entry("vtu_selection", "render_cell_set",
            {"object_name": "Valid OpenFOAM object word.", "ids": "List of target mesh cell IDs."},
            "Deterministic cellSet text."),
        "write": _entry("vtu_selection", "write_cell_set",
            {"path": "Explicit destination Path.", "object_name": "Valid object word.", "ids": "List of target mesh cell IDs."},
            "None", "Creates parent directories and overwrites the requested file; use a staged destination."),
    }, "read", native_reader="available",
    preconditions=["Establish that IDs refer to the target mesh; no between-mesh mapping is performed.",
                   "Use a staged destination for writes."],
    failures={"invalid_input": "Missing ID arrays or invalid file content fail; file I/O errors propagate.",
              "missing_capability": "Encoded/appended VTU reading requires optional PyVista.",
              "scientific_interpretation": "Valid cellSet syntax does not establish anatomical meaning."},
    evidence=["Standalone VTU selection conversion and native OpenFOAM cellSet format."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.vtu_selection import read_cell_ids, write_cell_set\narray_name, ids = read_cell_ids(Path(selection_path))\nwrite_cell_set(Path(staged_output), 'selectedCells', ids)",
)

# Retain existing discovery labels, with all content derived from OPERATIONS.
_UTILITY_IDS = {
    "electrode_normalization": "cardiaccore.electrodes.reference_frame.v1",
    "cobiveco_normalization": "cardiaccore.cobiveco.normalize.v1",
    "purkinje_seed_proposal": "cardiaccore.purkinje.seed_proposal.v1",
    "purkinje_coverage": "cardiaccore.purkinje.coverage_observation.v1",
    "vtu_selection_to_cellset": "cardiaccore.vtu.cell_set.v1",
}


def utility_index():
    """Discovery index, not a second set of operation support claims."""
    return {
        name: {
            "operation_id": operation_id,
            "status": "supported" if record["status"]["native_file_reader"] == "available" else "supported_array_method",
            "use": record["purpose"],
        }
        for name, operation_id in _UTILITY_IDS.items()
        for record in (OPERATIONS[operation_id],)
    }
