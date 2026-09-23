import numpy as np

from omnidriver.cardiaccore.operations.purkinje import coverage_report


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
