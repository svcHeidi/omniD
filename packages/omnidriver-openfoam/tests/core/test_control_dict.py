"""``system/controlDict``'s catalogue, shared by every OpenFOAM-based plugin."""

from __future__ import annotations

from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES


def test_the_catalogue_lists_the_keys_foam_time_reads_in_seconds():
    by_path = {entry.driver_path: entry for entry in CONTROL_DICT_ENTRIES}
    assert {"deltaT", "endTime", "startTime", "writeInterval"} <= set(by_path)
    for name in ("deltaT", "endTime", "startTime", "writeInterval"):
        assert by_path[name].unit.startswith("s")
    assert all("solver" in entry.phases for entry in by_path.values())
