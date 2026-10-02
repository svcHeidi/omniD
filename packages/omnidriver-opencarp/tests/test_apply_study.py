"""openCARP accepts ``step --apply``'s patches as a study does: they go through its own key validator, comparison and ``.par`` renderer."""
from __future__ import annotations

import pytest

from omnidriver.core.plugin_discovery import load_discovered_plugin
from omnidriver.core.runtime.record_execution import apply_record_study
from omnidriver.core.runtime.attempt_lease import acquire_case_lease
from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.opencarp.par_format import read_raw
from omnidriver.opencarp.records.niederer_n_version import RECORD

PAR = "tend = 5\ndt = 25\n"


@pytest.fixture
def case(tmp_path):
    (tmp_path / "nversion.par").write_text(PAR)
    return tmp_path


def _apply(case, study):
    with acquire_case_lease(case):
        return apply_record_study(RECORD, case_root=case, study=study, driver_context=load_discovered_plugin("opencarp"))


def test_a_patch_edits_the_par_file_and_leaves_the_rest(case):
    patches = _apply(case, {"nversion.par:tend": 10.0, "nversion.par:dt": 25.0})

    assert {(p["key_path"][0], p["status"]) for p in patches} == {("tend", "changed"), ("dt", "unchanged")}
    text = (case / "nversion.par").read_text()
    assert float(read_raw(text, "tend")) == 10.0
    assert float(read_raw(text, "dt")) == 25.0


def test_a_key_openCARP_does_not_have_is_refused_and_the_file_is_untouched(case):
    with pytest.raises(TutorialRecordError, match="tendd"):
        _apply(case, {"nversion.par:tend": 10.0, "nversion.par:tendd": 1.0})

    assert (case / "nversion.par").read_text() == PAR


def test_an_axis_is_refused_because_it_changes_the_plan(case):
    with pytest.raises(TutorialRecordError, match="plan again"):
        _apply(case, {"dx": 500.0})
