import numpy as np
import pytest

from omnidriver.cardiaccore.catalogs.purkinje import (
    LV_SEPTAL_AHA_SEGMENTS,
    RV_BASAL_SEPTAL_AHA_SEGMENT,
)
from omnidriver.cardiaccore.operations.purkinje import (
    coverage_report,
    deduce_seeds,
    read_seed_dictionary,
)


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


def _tree_dictionary(tmp_path):
    dictionary = tmp_path / "system" / "generatePurkinjeTreeDict"
    dictionary.parent.mkdir(parents=True, exist_ok=True)
    dictionary.write_text(
        "growthModel surfaceFollow;\n"
        "hisBundleSeed (2.0 0.0 7.0);\n"
        "lv\n{\n    seed (0.0 0.0 7.0);\n    lineEnd (0.0 0.0 6.0);\n}\n"
        "rv\n{\n    seed (4.0 0.0 7.0);\n    lineEnd (4.0 0.0 6.0);\n}\n"
    )
    return dictionary


def test_declared_seeds_are_read_back_from_the_native_dictionary(tmp_path):
    """The inverse of write_seed_dictionary: what did this case actually ask for?"""
    from omnidriver.cardiaccore.operations.purkinje import read_seed_dictionary

    seeds = read_seed_dictionary(_tree_dictionary(tmp_path))

    assert seeds["lv_seed"] == (0.0, 0.0, 7.0)
    assert seeds["rv_seed"] == (4.0, 0.0, 7.0)
    assert seeds["lv_line_end"] == (0.0, 0.0, 6.0)
    assert seeds["his_bundle_seed"] == (2.0, 0.0, 7.0)


def test_a_dictionary_missing_a_seed_says_which_one(tmp_path):
    from omnidriver.cardiaccore.operations.purkinje import read_seed_dictionary

    dictionary = _tree_dictionary(tmp_path)
    dictionary.write_text(dictionary.read_text().replace("    lineEnd (4.0 0.0 6.0);\n", ""))

    with pytest.raises(ValueError, match="rv.lineEnd"):
        read_seed_dictionary(dictionary)


def _fields():
    points, aha, longitudinal, lv_surface, rv_surface = _surface_points()
    return {
        "points": points, "aha_segment": aha,
        "lv_endocardial_mask": lv_surface, "rv_endocardial_mask": rv_surface,
    }


def test_placement_reports_distance_to_the_declared_septal_area(tmp_path):
    """Distance is the primary signal; a hand-placed seed rarely sits on a node.

    This exercises the distance and label arithmetic over a labelled cloud.
    Which segments count as septal is not asserted here -- that comes from
    TREE_VALIDATION_CONTRACT, which is sourced from the native utility.
    """
    from omnidriver.cardiaccore.operations.purkinje import (
        read_seed_dictionary, seed_area_placement_report,
    )

    report = seed_area_placement_report(read_seed_dictionary(_tree_dictionary(tmp_path)), _fields())

    # Both seeds coincide with a labelled candidate in this cloud.
    assert report["lv"]["distance_to_declared_area"] == 0.0
    assert report["rv"]["distance_to_declared_area"] == 0.0
    assert report["lv"]["nearest_surface_aha_segment"] in LV_SEPTAL_AHA_SEGMENTS
    assert report["rv"]["nearest_surface_aha_segment"] == RV_BASAL_SEPTAL_AHA_SEGMENT


def test_a_seed_away_from_the_septum_is_reported_by_distance_and_segment(tmp_path):
    """The rotational mis-placement deduce_seeds exists to repair."""
    from omnidriver.cardiaccore.operations.purkinje import seed_area_placement_report

    seeds = read_seed_dictionary(_tree_dictionary(tmp_path))
    strayed = {**seeds, "lv_seed": (3.0, 0.0, 7.0)}   # AHA 5: lateral, not septal

    report = seed_area_placement_report(strayed, _fields())

    assert report["lv"]["distance_to_declared_area"] > 0.0
    assert report["lv"]["nearest_surface_aha_segment"] == 5
    assert report["lv"]["nearest_surface_aha_segment"] not in LV_SEPTAL_AHA_SEGMENTS


def test_reading_declared_seeds_is_an_advertised_entrypoint():
    """An agent discovers operations through the catalog, not the module."""
    from omnidriver.cardiaccore import CardiacCorePlugin

    operation = CardiacCorePlugin().get_named_catalogs()["cardiaccore_operations"][
        "cardiaccore.purkinje.seed_proposal.v1"
    ]
    entry = operation["entrypoints"]["read_declared"]

    assert entry["callable"].endswith(":read_seed_dictionary")
    assert "dictionary" in entry["inputs"]
    receipt = operation["entrypoints"]["placement_receipt"]
    assert "distance" in receipt["outputs"].lower()


def test_the_dictionary_may_be_given_as_a_path_string(tmp_path):
    """Found by calling it from a real case rather than a fixture."""
    from omnidriver.cardiaccore.operations.purkinje import read_seed_dictionary

    seeds = read_seed_dictionary(str(_tree_dictionary(tmp_path)))
    assert seeds["lv_seed"] == (0.0, 0.0, 7.0)


def test_the_his_root_is_reported_by_distance_from_the_midpoint(tmp_path):
    """A declared His seed round-trips through dictionary text.

    Its coordinates come back rounded, so exact equality with the computed
    midpoint fails on a real case even when the case plainly intends it --
    measured at 9.4e-10 m on the idealized biventricular ellipsoid. The
    boolean stays for deduce_and_write_native_seed_dictionary, which
    compares a proposal it just computed in memory.
    """
    from omnidriver.cardiaccore.operations.purkinje import (
        read_seed_dictionary, seed_area_placement_report,
    )

    dictionary = _tree_dictionary(tmp_path)
    dictionary.write_text(dictionary.read_text().replace(
        "hisBundleSeed (2.0 0.0 7.0);", "hisBundleSeed (2.0000000001 0.0 7.0);"))
    report = seed_area_placement_report(read_seed_dictionary(dictionary), _fields())

    assert report["his_bundle"]["is_midpoint_of_roots"] is False
    assert report["his_bundle"]["distance_from_root_midpoint"] < 1e-9
