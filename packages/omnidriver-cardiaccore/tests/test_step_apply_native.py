"""``step --apply`` on a real cardiacCore case: the patch lands in the staged case's utility dictionary, and the utility reruns against it."""
from __future__ import annotations

import pytest

from omnidriver.conformance import record_step, require_commands
from omnidriver.openfoam.mutators import read_foam_entry
from cardiaccore_native import native_cardiaccore_tree

pytestmark = pytest.mark.native_cardiaccore


def test_apply_edits_the_staged_case_then_the_utility_runs_against_it(tmp_path):
    require_commands("setCardiacConductivity", "setCardiacAnatomy")
    case_root, payload = record_step(
        tmp_path, plugin="cardiaccore", record="idealizedHeart", cases_root=native_cardiaccore_tree(),
        before=("conductivity",), step="anatomy",
        apply={"system/setCardiacAnatomyDict:zApicalMid": 0.30},
    )

    assert payload["status"] == "ok", payload
    assert [patch["status"] for patch in payload["applied_patches"]] == ["changed"]
    assert read_foam_entry(case_root / "system" / "setCardiacAnatomyDict", "zApicalMid") == "0.3"
    assert (case_root / "0" / "aha_angle").is_file()
