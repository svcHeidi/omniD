import numpy as np

from omnidriver.cardiaccore.tree_validation import coverage_report, deduce_seeds


def _surface_points():
    """Small boundary-like cloud with unambiguous LV/RV septal candidates."""
    points = []
    aha = []
    transmural = []
    intraventricular = []
    longitudinal = []
    for z in range(6, 9):
        for x, segment in ((0.0, 2), (1.0, 3), (2.0, 5), (3.0, 5)):
            points.append((x, 0.0, float(z)))
            aha.append(segment)
            transmural.append(0.0)
            intraventricular.append(-1.0)
            longitudinal.append(z / 10)
        # This is the generator's recovered RV septal convention, not an
        # ordinary RV AHA label.
        points.append((4.0, 0.0, float(z)))
        aha.append(20)
        transmural.append(0.95)
        intraventricular.append(-1.0)
        longitudinal.append(z / 10)
    return tuple(np.asarray(values) for values in (
        points, aha, transmural, intraventricular, longitudinal,
    ))


def test_seed_deduction_uses_lv_aha_and_recovered_rv_septum_contract():
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
