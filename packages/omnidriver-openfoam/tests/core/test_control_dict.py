"""``system/controlDict``'s catalogue, shared by every OpenFOAM-based plugin."""

from __future__ import annotations

from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES


def test_the_catalogue_lists_the_keys_foam_time_reads_in_seconds():
    by_path = {entry.driver_path: entry for entry in CONTROL_DICT_ENTRIES}
    assert {"deltaT", "endTime", "startTime", "writeInterval"} <= set(by_path)
    for name in ("deltaT", "endTime", "startTime", "writeInterval"):
        assert by_path[name].unit.startswith("s")
    assert all("solver" in entry.phases for entry in by_path.values())


def _violations(context):
    from omnidriver.openfoam.case_rules import rule_diagnostics

    return {item.message for item in rule_diagnostics(CONTROL_DICT_ENTRIES, context, document="system/controlDict")}


def test_only_deltat_and_a_write_interval_are_always_required():
    assert _violations({}) == {
        "deltaT is required.", "one of writeFrequency, writeInterval is required.",
    }
    assert _violations({"deltaT": 1e-3, "writeFrequency": 5}) == set()


def test_start_time_and_end_time_are_required_only_where_foam_time_reads_them():
    base = {"deltaT": 1e-3, "writeInterval": 5}
    assert _violations({**base, "startFrom": "startTime", "stopAt": "endTime"}) == {
        "startTime is required when startFrom=startTime.", "endTime is required when stopAt=endTime.",
    }
    assert _violations({**base, "startFrom": "latestTime", "stopAt": "writeNow"}) == set()
    assert _violations(base) == set()
