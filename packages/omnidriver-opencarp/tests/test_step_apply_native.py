"""``step --apply`` on a real openCARP case: the patches land in the staged ``nversion.par``, and openCARP reruns against them."""
from __future__ import annotations

import pytest

from omnidriver.conformance import record_step
from omnidriver.opencarp.par_format import read_raw
from opencarp_native import opencarp_tutorials_root, require_opencarp_binary

pytestmark = pytest.mark.native_opencarp


def test_apply_edits_the_staged_case_then_openCARP_runs_against_it(tmp_path):
    require_opencarp_binary()
    case_root, payload = record_step(
        tmp_path, plugin="opencarp", record="niedererNVersion", cases_root=opencarp_tutorials_root(),
        study={"dx": 1000.0}, before=("mesh",), step="solve",
        apply={"nversion.par:tend": 10.0, "nversion.par:dt": 50.0},
    )

    assert payload["status"] == "ok", payload
    assert {patch["status"] for patch in payload["applied_patches"]} == {"changed"}
    par = (case_root / "nversion.par").read_text()
    assert float(read_raw(par, "tend")) == 10.0
    assert float(read_raw(par, "dt")) == 50.0
    assert (case_root / "out" / "vm.igb").is_file()
