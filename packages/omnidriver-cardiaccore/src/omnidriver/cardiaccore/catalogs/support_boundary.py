"""Adapter-owned field, utility, and support-boundary records."""

# Shared by the usage contract and implementation; this converter supports
# exactly this target, not arbitrary user-defined coordinate conventions.
CARDIACCORE_COBIVECO_TARGET = {
    "transmural_min": 0.0,
    "transmural_max": 1.0,
    "lv_value": -1.0,
    "rv_value": 1.0,
}

FIELD_CONVENTIONS = {
    "authority": "Read system/uvcConventionDict for every case; field names and ranges are case-owned.",
    "current_cardiaccore": {
        "uvc_transmural": "min=endocardium, max=epicardium; checked-in cases use 0=endo, 1=epi",
        "uvc_intraventricular": "checked-in cases use LV=-1, RV=1; native code classifies by nearest declared value",
        "uvc_longitudinal": "checked-in cases use 0=apex, 1=base",
        "coordinate_ring_closure": "The preprocessing coordinate-ring check can infer topology-supported scalar-field candidates without treating names as a convention. When LV/RV naming matters, it expects declared binary values, a varying longitudinal field, and an endocardial transmural value. It uses iso-contours; it does not use AHA angles or pre-exported face sets.",
        "outputs": "setCardiacAnatomy writes AHA_Segment and aha_angle; generatePurkinjeTree writes LVEndoFaces/RVEndoFaces/RVSeptalEndoFaces/EpiFaces",
    },
    "cobiveco_raw": {
        "tv": "0=LV, 1=RV", "tm": "0=epicardium, 1=endocardium", "ab": "approximately 0=apex, 1=base",
        "mapping": "uvc_transmural=1-tm; uvc_intraventricular=2*tv-1; uvc_longitudinal=ab",
        "reason": "Raw CObiveco transmural orientation is opposite cardiacCore's current convention.",
    },
}


SUPPORT_BOUNDARY = {
    "supported_workflows": ("cardiaccore-biv-preprocessing", "cardiaccore-human-endocardial-tree", "cardiaccore-pig-morphometric-tree"),
    "pending": ("VTK adapters for seed and coverage sampling", "CObiveco VTU-to-legacy-VTK conversion with vector-field compatibility", "reviewed seed-dictionary write operation"),
    "retired": "Standalone driverFOAM and agent pipeline/catalog interfaces are not adapter authorities.",
}
