"""openCARP's own Niederer tutorial case, committed verbatim (``nversion.par`` and ``singlecell.sv``
of ``02_EP_tissue/03E_study_resolution``): the .par format round-trips it, and a plan refuses a study
by name whichever layer refuses. Scratch goes to ``tmp_path``."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.opencarp.par_format import parse_par, patch_par, read_raw

TUTORIALS = Path(__file__).resolve().parent / "fixtures" / "tutorials"
NIEDERER = "02_EP_tissue/03E_study_resolution"
ENTRY = "niedererNVersion"


def _plan(tmp_path, study, cases_root=TUTORIALS):
    return strict_plan(
        ENTRY, overrides={"cases_root": str(cases_root), **study},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("opencarp"),
    )


def test_the_shipped_par_parses_and_an_empty_patch_returns_it_byte_for_byte():
    text = (TUTORIALS / NIEDERER / "nversion.par").read_text()
    assert parse_par(text)
    assert patch_par(text, {}) == text


def test_an_index_beyond_its_count_is_refused(tmp_path):
    with pytest.raises(TutorialRecordError) as refusal:
        _plan(tmp_path, {"nversion.par:stim[1].pulse.strength": 999.0})
    assert "nversion.par" in str(refusal.value)
    assert "stim[1].pulse.strength: index 1 is outside num_stim = 1 (F2)" in str(refusal.value)


def test_a_command_line_owned_key_is_refused(tmp_path):
    with pytest.raises(TutorialRecordError) as refusal:
        _plan(tmp_path, {"nversion.par:simID": "elsewhere"})
    assert "nversion.par:simID" in str(refusal.value) and "F14" in str(refusal.value)


@pytest.mark.parametrize("action", ["plan", "describe"])
def test_a_native_value_the_reader_refuses_is_refused(tmp_path, action):
    """The config reader refuses an unquoted ``a=b`` string in the native file, which openCARP would
    truncate: a copy of the tutorial with that one line unquoted."""
    cases_root = tmp_path / "tutorials"
    shutil.copytree(TUTORIALS / NIEDERER, cases_root / NIEDERER)
    par = cases_root / NIEDERER / "nversion.par"
    text = par.read_text()
    assert 'imp_region[0].im_param = "flags=EPI"' in text
    par.write_text(text.replace('imp_region[0].im_param = "flags=EPI"', "imp_region[0].im_param = flags=EPI"))
    study = {"nversion.par:imp_region[0].im_param": "flags=ENDO"}
    with pytest.raises(TutorialRecordError) as refusal:
        if action == "plan":
            _plan(tmp_path, study, cases_root)
        else:
            describe_entry(
                ENTRY, overrides={"cases_root": str(cases_root), **study},
                driver_context=load_plugin_context("opencarp"),
            )
    assert "nversion.par:imp_region[0].im_param" in str(refusal.value) and "F10" in str(refusal.value)


def test_apply_adds_a_line_to_the_staged_par_and_keeps_every_other_byte(tmp_path):
    from omnidriver.core.runtime import record_execution
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease

    context = load_plugin_context("opencarp")
    report = strict_plan(ENTRY, overrides={"cases_root": str(TUTORIALS)}, scratch_root=tmp_path / "scratch", driver_context=context)
    case_root = Path(report.launch["case_root"])
    before = (case_root / "nversion.par").read_text()
    with acquire_case_lease(case_root):
        applied = record_execution.apply_record_study(
            context.stack.call("get_tutorial_records")[ENTRY], case_root=case_root, driver_context=context,
            study={"nversion.par:tend": 12.0},
        )
    assert {patch["status"] for patch in applied} == {"changed"}
    after = (case_root / "nversion.par").read_text()
    assert float(read_raw(after, "tend")) == 12.0 and read_raw(before, "tend") is None
    assert after.startswith(before.rstrip("\n"))
