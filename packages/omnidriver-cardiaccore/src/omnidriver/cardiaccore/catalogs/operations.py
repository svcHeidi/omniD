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
        "write_bundle": _entry("electrodes", "write_reference_offset_bundle",
            {"path": "Destination JSON path.", "bundle": "Validated bundle returned by derive_bundle."},
            "None", "Overwrites the requested file; does not create parent directories, so use a staged destination."),
        "read_bundle": _entry("electrodes", "read_reference_offset_bundle",
            {"path": "Path to a bundle previously written by write_bundle."},
            "The same validated bundle shape derive_bundle produces, for a later or separate apply_bundle call.",
            "Reads only; raises on a missing schema version or malformed payload."),
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
    "cardiaccore.coordinates.convention.v1",
    "Read a case's declared ventricular coordinate convention and derive its coordinate field paths.",
    "Any staged case with system/coordinatesConventionDict; every other operation that needs a transmural, intraventricular or longitudinal field name reads this first rather than assuming one.",
    {
        "read": _entry("coordinates_convention", "read_coordinates_convention",
            {"case_root": "Path to a staged case."},
            "CoordinatesConvention: coordinate_system, the three field names, and the transmural/intraventricular reference values, with transmural_lower/upper/range, chamber_seam and is_left_ventricle derived on it."),
        "field_paths": _entry("coordinates_convention", "coordinate_field_paths",
            {"convention": "CoordinatesConvention from read, or None for the canonical default names.",
             "time_dir": "Optional time directory; default '0'."},
            "Mapping of transmural/intraventricular/longitudinal to their case-relative field paths."),
    }, "read",
    preconditions=["The case declares system/coordinatesConventionDict with coordinateSystem, the transmural endocardium/epicardium values and the intraventricularChambers LV/RV values.",
                   "Classify a chamber with is_left_ventricle (nearest declared value), not by sign or a hardcoded LV/RV convention.",
                   "Transmural endocardium is not always the smaller value: use transmural_lower/upper/range for a plain numeric bound."],
    failures={"invalid_input": "Raises when the dictionary is absent or a required key is missing, non-scalar, or not one of the accepted coordinate systems.",
              "missing_capability": "None; this operation reads only the plain-text case dictionary.",
              "scientific_interpretation": "This reads the case's declaration; it does not check that declaration against the mesh's actual fields (see cardiaccore.coordinates.ring_closure.v1 for that check)."},
    evidence=["Mirrors src/coordinatesConvention/coordinatesConvention.H in native cardiacCore; native is the authority where the two could drift."],
    example="from pathlib import Path\nfrom omnidriver.cardiaccore.operations.coordinates_convention import read_coordinates_convention, coordinate_field_paths\nconvention = read_coordinates_convention(Path(case_root))\npaths = coordinate_field_paths(convention)",
    native_reader="available",
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
    "purkinje_coverage": "cardiaccore.purkinje.coverage_observation.v1",
    "coordinate_convention": "cardiaccore.coordinates.convention.v1",
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
