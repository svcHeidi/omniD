import numpy as np

from omnidriver.cardiaccore.operations.purkinje import coverage_report, deduce_seeds


def _surface_points():
    """Small boundary-like cloud with unambiguous LV/RV septal candidates."""
    points = []
    aha = []
    longitudinal = []
    lv_surface = []
    rv_surface = []
    for z in range(6, 9):
        for x, segment in ((0.0, 2), (1.0, 3), (2.0, 5), (3.0, 5)):
            points.append((x, 0.0, float(z)))
            aha.append(segment)
            longitudinal.append(z / 10)
            lv_surface.append(True)
            rv_surface.append(False)
        # CObiveco-compatible: native RVEndoFaces plus C++ AHA 21 identifies
        # the basal RV septum without a leaked LV coordinate value.
        points.append((4.0, 0.0, float(z)))
        aha.append(21)
        longitudinal.append(z / 10)
        lv_surface.append(False)
        rv_surface.append(True)
    return tuple(np.asarray(values) for values in (
        points, aha, longitudinal, lv_surface, rv_surface,
    ))


def test_seed_deduction_uses_native_surfaces_and_aha_segments():
    result = deduce_seeds(*_surface_points())

    assert result["lv_seed"][0] in {0.0, 1.0}
    assert result["rv_seed"][0] == 4.0
    assert result["his_bundle_seed"] == tuple(
        (left + right) / 2
        for left, right in zip(result["lv_seed"], result["rv_seed"])
    )


def test_coverage_requires_present_mid_apical_segments_but_only_warns_for_basal():
    # AHA 7 and 22 have real endocardium but no terminals; segment 1 is also
    # empty but belongs to the intentionally warning-only basal band.
    report = coverage_report(
        terminal_aha_segment=np.array([8, 13, 17, 23, 26, 29]),
        endocardial_aha_segment=np.array([1, 7, 8, 13, 17, 22, 23, 26, 29]),
    )

    assert report["required_missing"] == (7, 22)
    assert report["basal_warnings"] == (1,)
    assert 2 not in report["starved"]  # no endocardial surface was supplied


def test_rv_tree_terminal_on_recovered_septum_is_credited_to_rv_segment():
    report = coverage_report(
        terminal_aha_segment=np.array([14, 14]),
        terminal_tree_zone=np.array([1, 2]),
    )
    assert report["counts"][14] == 1
    assert report["counts"][29] == 1
