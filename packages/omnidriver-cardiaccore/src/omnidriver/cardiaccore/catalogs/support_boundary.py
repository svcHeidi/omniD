"""Adapter-owned field, utility, and support-boundary records."""

FIELD_CONVENTIONS = {
    "authority": (
        "Every case declares its own convention in system/coordinatesConventionDict: "
        "a required coordinateSystem (uvc or cobiveco), an optional coordinates block "
        "naming its coordinate fields, the transmural endocardium/epicardium values, and "
        "the intraventricularChambers LV/RV values. Read it with "
        "omnidriver.cardiaccore.operations.coordinates_convention.read_coordinates_convention "
        "and choose field paths and dictionary entries from what it says. There is no "
        "package-wide field naming or numeric orientation to assume."
    ),
    "canonical_field_names": {
        "transmural": "Default name when the case's coordinates block omits transmuralField.",
        "intraventricular": "Default name when it omits intraventricularField.",
        "apicobasal": "Default name when it omits longitudinalField.",
    },
    "reading_values": {
        "transmural": (
            "Named by anatomy, not by numeric order: endocardium may be the larger value. "
            "UVC cases typically read 0=endocardium, 1=epicardium and CObiveco cases the "
            "reverse. Use transmural_lower/transmural_upper/transmural_range for a plain "
            "numeric bound rather than assuming which end is which."
        ),
        "intraventricular": (
            "Classify a chamber by nearest declared value (is_left_ventricle), not by sign: "
            "LV=-1/RV=1 is one case's declaration, not a rule."
        ),
        "longitudinal": "Orientation is case-declared; apex-to-base direction is not guaranteed.",
    },
    "coordinate_system_effects": {
        "uvc": (
            "generatePurkinjeTree recovers the RV-facing septum and applies the per-vertex "
            "transmural flip, because UVC solves transmural distance and chamber membership "
            "together against the LV boundary."
        ),
        "cobiveco": (
            "Neither step runs: CObiveco solves per chamber, so the septum already reads "
            "endocardial from both sides. A CObiveco case is declared as cobiveco and used "
            "directly; converting its values into UVC spelling would not change how the "
            "field was solved and would invite a correction the geometry does not need."
        ),
    },
    "surface_source": (
        "generatePurkinjeTree uses named LV/RV endocardial patches when present; otherwise it "
        "constructs face sets from the declared convention."
    ),
    "angles": (
        "setCardiacAnatomy writes AHA_Segment and aha_angle in separate LV/RV angle frames; "
        "do not compare their raw angles across chambers."
    ),
    "coordinate_ring_closure": (
        "The preprocessing coordinate-ring check can infer topology-supported scalar-field "
        "candidates without treating names as a convention. When LV/RV naming matters, it "
        "expects declared binary values, a varying longitudinal field, and an endocardial "
        "transmural value. It selects the closed basal 0.1/0.4 component nearest the largest "
        "connected ab=0 region and requires approximately 0.3 normalized spacing; it does not "
        "use AHA angles or pre-exported face sets."
    ),
    "outputs": "generatePurkinjeTree writes LVEndoFaces/RVEndoFaces/RVSeptalEndoFaces/EpiFaces",
    "cobiveco_raw": {
        "tv": "0=LV, 1=RV", "tm": "0=epicardium, 1=endocardium",
        "ab": "approximately 0=apex, 1=base",
        "use": (
            "Declare these in the case's coordinatesConventionDict -- coordinateSystem "
            "cobiveco, the field names under coordinates, transmural endocardium 1 and "
            "epicardium 0, and the chamber values -- rather than remapping the arrays."
        ),
    },
}


SUPPORT_BOUNDARY = {
    "supported_workflows": (
        "cardiaccore-human-purkinje-slab",
        "cardiaccore-human-purkinje-endocardial",
        "cardiaccore-pig-morphometric-purkinje",
        "cardiaccore-pig-transmural-purkinje",
    ),
    "pending": ("Automatic workflow integration of seed proposal, coverage, and coordinate-ring operations", "CObiveco VTU-to-legacy-VTK conversion with vector-field compatibility", "Workflow step for the refine1Dgraph/1DgraphToFoam graph hand-off, with -maxEdgeLength scaled from the mesh length unit"),
    "retired": "Standalone driverFOAM and agent pipeline/catalog interfaces are not adapter authorities.",
}
