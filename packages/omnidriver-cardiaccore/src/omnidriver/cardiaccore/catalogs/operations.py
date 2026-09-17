"""Canonical descriptions of the adapter's Python operations.

References use module:function syntax. Each entrypoint describes exact arguments
and side effects. Catalog discovery never invokes these trusted callables.
"""


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
    "cardiaccore.electrodes.reference_frame.v1",
    "Transfer explicitly selected comparative-reference electrodes through an anatomical LV frame.",
    "Packaged Strocchi-02 approximation; not patient-specific or default electrode placement.",
    {
        "frame": _entry("electrodes", "compute_lv_frame",
            {"points": "Finite Nx3 coordinates in one caller-declared length unit.",
             "intraventricular": "Finite length-N vector of the case's intraventricular coordinate.",
             "longitudinal": "Finite length-N vector of the case's longitudinal coordinate."},
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
            {"heart_vtk": "Native VTK/VTU path with coordinate point or cell data.",
             "intraventricular_field": "Array name for the intraventricular coordinate; defaults to the canonical name.",
             "longitudinal_field": "Array name for the longitudinal coordinate; defaults to the canonical name."},
            "Points and point-aligned coordinate arrays for frame construction."),
        "derive_bundle": _entry("electrodes", "derive_reference_offset_bundle",
            {"reference_heart_vtk": "Native reference VTK/VTU path.",
             "reference_electrodes": "Mapping of electrode names to reference coordinates in one declared unit.",
             "coordinate_unit": "Required source-coordinate-unit label; no conversion is inferred.",
             "intraventricular_field": "Array name for the intraventricular coordinate; defaults to the canonical name.",
             "longitudinal_field": "Array name for the longitudinal coordinate; defaults to the canonical name."},
            "Versioned JSON-serializable bundle of dimensionless offsets."),
        "apply_bundle": _entry("electrodes", "apply_offset_bundle_to_native_file",
            {"heart_vtk": "Native target VTK/VTU path.", "bundle": "Validated reference offset bundle.",
             "target_coordinate_unit": "Required target-coordinate-unit label; no conversion is inferred.",
             "axial_shift": "Optional fraction of target LV-frame length; default 0.0.",
             "intraventricular_field": "Array name for the intraventricular coordinate; defaults to the canonical name.",
             "longitudinal_field": "Array name for the longitudinal coordinate; defaults to the canonical name."},
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
         "longitudinal": "Length-N vector.", "lv_endocardial_mask": "Length-N boolean mask.",
         "rv_endocardial_mask": "Length-N boolean mask."},
        "lv_seed, rv_seed, his_bundle_seed, lv_line_end and rv_line_end coordinate tuples."),
        "write_seeds": _entry("purkinje", "write_seed_dictionary",
            {"dictionary": "Existing Path to system/generatePurkinjeTreeDict in a staged case.",
             "proposal": "Complete mapping returned by deduce_seeds: five finite length-3 coordinates."},
            "None",
            "Updates only hisBundleSeed, lv.seed, lv.lineEnd, rv.seed and rv.lineEnd; preserves all other native settings."),
        "read_surfaces": _entry("purkinje", "read_native_seed_surface_fields",
            {"lv_surface": "Path to the native LVEndoFaces foamToVTK export.",
             "rv_surface": "Path to the native RVEndoFaces foamToVTK export.",
             "longitudinal_field": "Array name the case declares for its longitudinal coordinate; defaults to the canonical name."},
            "Aligned points, AHA labels, longitudinal values, and LV/RV surface masks for deduce_seeds.",
            "Reads only the supplied VTK files; does not mutate the case."),
        "read_declared": _entry("purkinje", "read_seed_dictionary",
            {"dictionary": "Path to system/generatePurkinjeTreeDict in a staged case."},
            "The five seed coordinates the case declares, as read from the dictionary.",
            "Reads only; the inverse of write_seeds, for checking a hand-placed root."),
        "placement_receipt": _entry("purkinje", "seed_area_placement_report",
            {"proposal": "Five seed coordinates: either read_declared's or deduce_seeds'.",
             "fields": "Aligned fields returned by read_native_seed_surface_fields."},
            "Per ventricle: distance to the declared basal-septal area, the AHA segment "
            "the root actually lands in, distance to the nearest surface point, the "
            "declared candidate count, and whether the root coincides with a candidate.",
            "Observations, not a score: the contract states no threshold for distance, "
            "so a distant root is a subject for review rather than a failure declared here."),
        "deduce_write_native": _entry("purkinje", "deduce_and_write_native_seed_dictionary",
            {"lv_surface": "Path to an explicitly exported native LVEndoFaces surface.",
             "rv_surface": "Path to an explicitly exported native RVEndoFaces surface.",
             "dictionary": "Path to system/generatePurkinjeTreeDict in a staged case."},
            "Seed proposal and placement receipt after updating only the five reviewed dictionary entries.",
            "The native generator has no surface-preparation-only mode: exports come from an explicit prior run, then the caller performs the next tree run."),
    }, "propose", native_reader="available_optional",
    preconditions=["Sample native surfaces onto the same points.",
                   "Use the method assumptions in cardiaccore_tree_validation.seed_placement.",
                   "A domain decision establishes whether this proposal method applies to the study."],
    failures={"invalid_input": "Raises on mismatched lengths, absent septal candidates or unavailable local gradient. Array preparation remains the caller's responsibility.",
              "missing_capability": "Reading supplied native surface exports requires the optional vtk extra; exporting the face sets is an explicit prerequisite. The separate write_seeds entrypoint updates the staged dictionary.",
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
              "missing_capability": "This entrypoint consumes arrays; use cardiaccore.purkinje.coverage_native.v1 for supported native-file sampling with the optional vtk extra.",
              "scientific_interpretation": "required_missing/basal_warnings use cardiaccore_tree_validation.baseline_coverage; these categories are not universal scientific acceptance."},
    evidence=["Standalone coverage method and native RV CellZone convention; preserved baseline categories are exposed in cardiaccore_tree_validation."],
    example="from omnidriver.cardiaccore.operations.purkinje import coverage_report\nreport = coverage_report(terminal_labels, endocardial_labels, terminal_tree_zone=zones)",
)

_add(
    "cardiaccore.coordinates.ring_closure.v1",
    "Check whether coordinate-selected LV/RV endocardial contours are closed at basal longitudinal levels 0.1 and 0.4.",
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
             "ring_levels": "Fixed basal longitudinal iso-values (0.1, 0.4).",
             "binary_tolerance": "Non-negative binary-chamber tolerance; default 1e-9.",
             "basal_ring_spacing_tolerance": "Allowed deviation from the expected 0.3 normalized 0.1-to-0.4 ring separation; default 0.1.",
             "seam_point_fraction_tolerance": "Maximum fraction of point-interpolated values allowed strictly between the two chamber endpoints; default 0.02."},
            "Coordinate-contract result plus independent LV/RV basal-ring closure and spacing reports.",
            "Reads the supplied mesh only; does not mutate the case."),
    }, "report", native_reader="available_optional",
    preconditions=["Without declared fields, the operation evaluates normalized scalar candidates from their numerical structure and ring topology; field names are not treated as a convention.",
                   "A unique candidate identifies two chamber values but not which is LV or RV; declare every field/value when chamber naming matters.",
                   "The 0.1 and 0.4 contours must each contain a closed component. When extra components occur, the closed component closest in physical space to the largest connected endocardial ab=0 reference is selected; their centres must be approximately 0.3 of the selected endocardial span apart.",
                   "Use a VTK export that preserves the three coordinate fields."],
    failures={"invalid_input": "Raises for absent/non-finite fields, invalid values/tolerances, levels other than the fixed basal pair, or a mesh without boundary cells.",
              "missing_capability": "VTK reading requires the optional vtk extra.",
              "scientific_interpretation": "A failed coordinate contract or open contour identifies a geometry/coordinate prerequisite to investigate; it does not prescribe a UVC, CObiveco, or Purkinje-model change."},
    evidence=["CObiveco coordinate-result meshes; native cardiacCore UVC-convention surface preparation; owner-selected coordinate-ring closure criterion."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.coordinates import coordinate_endocardial_ring_closure_from_vtk\nreport = coordinate_endocardial_ring_closure_from_vtk(Path('result.vtu'))\n# Inspect report['coordinate_discovery']; explicitly name fields only when LV/RV labels are needed.",
)

_add(
    "cardiaccore.purkinje.coverage_native.v1",
    "Sample native cardiacCore VTK exports and report the named Purkinje coverage baseline.",
    "A generatePurkinjeTree legacy VTK graph, a foamToVTK internal volume export with AHA_Segment cell data, and optionally paired LVEndoFaces/RVEndoFaces exports.",
    {
        "native_report": _entry("purkinje", "coverage_report_from_native_files",
            {"purkinje_vtk": "Path to postProcessing/generatePurkinjeTree/purkinje.vtk.",
             "volume_vtu": "Path to the foamToVTK internal volume export with AHA_Segment cell data.",
             "lv_endo_faceset_vtp": "Optional Path to the foamToVTK LVEndoFaces surface export.",
             "rv_endo_faceset_vtp": "Optional Path to the foamToVTK RVEndoFaces surface export."},
            "Coverage report with terminal counts, recovered-RV-septum remapping, and optional no-endocardium separation.",
            "Reads only the supplied VTK files; does not mutate the case."),
    }, "native_report", native_reader="available_optional",
    preconditions=["Install the optional vtk extra.",
                   "Export the volume and, when distinguishing absent endocardium matters, both native face sets with foamToVTK.",
                   "The selected VTK artifacts must refer to the same case and mesh."],
    failures={"invalid_input": "Raises when required arrays are absent, files are empty or connectivity/data alignment is invalid.",
              "missing_capability": "PyVista/VTK is optional and must be installed for native-file reading.",
              "scientific_interpretation": "The result is the named baseline observation, not a universal density or electrophysiological acceptance test."},
    evidence=["Native agent/check_purkinje_coverage.py and generatePurkinjeTree/README.md; sampling uses the generator's own CellZone and face-set conventions."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.purkinje import coverage_report_from_native_files\nreport = coverage_report_from_native_files(Path('purkinje.vtk'), Path('internal.vtu'))",
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
    "purkinje_seed_proposal": "cardiaccore.purkinje.seed_proposal.v1",
    "purkinje_coverage": "cardiaccore.purkinje.coverage_observation.v1",
    "coordinate_ring_closure": "cardiaccore.coordinates.ring_closure.v1",
    "purkinje_coverage_native": "cardiaccore.purkinje.coverage_native.v1",
    "vtu_selection_to_cellset": "cardiaccore.vtu.cell_set.v1",
}


def utility_index():
    """Discovery index, not a second set of operation support claims."""
    return {
        name: {
            "operation_id": operation_id,
            "status": {
                "available": "supported",
                "available_optional": "supported_optional",
            }.get(record["status"]["native_file_reader"], "supported_array_method"),
            "use": record["purpose"],
        }
        for name, operation_id in _UTILITY_IDS.items()
        for record in (OPERATIONS[operation_id],)
    }
