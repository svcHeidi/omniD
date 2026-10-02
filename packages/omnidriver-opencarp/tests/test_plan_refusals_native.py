"""Strict planning refuses openCARP studies by name, whichever layer refuses.

The index-bound refusal comes from the renderer (``check_indices``), not the
key validator; a key the record's command line owns is refused by the
validator instead. Both reach an agent as the same ``TutorialRecordError``,
which the CLI prints as JSON.
Scratch goes to tmp_path; the native tree is only read."""
from __future__ import annotations

import pytest

from omnidriver.core.introspection import describe_entry
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import TutorialRecordError
from opencarp_native import NIEDERER_RELPATH, opencarp_tutorials_root

pytestmark = pytest.mark.native_opencarp

_ENTRY = "niedererNVersion"


def _plan(tmp_path, study, cases_root=None):
    return strict_plan(
        _ENTRY, overrides={"cases_root": str(cases_root or opencarp_tutorials_root()), **study},
        scratch_root=tmp_path / "scratch", driver_context=load_plugin_context("opencarp"),
    )


def test_an_index_beyond_its_count_is_refused_F2_I2(tmp_path):
    with pytest.raises(TutorialRecordError) as refusal:
        _plan(tmp_path, {"nversion.par:stim[1].pulse.strength": 999.0})
    assert "nversion.par" in str(refusal.value)
    assert "stim[1].pulse.strength: index 1 is outside num_stim = 1 (F2)" in str(refusal.value)


def test_a_command_line_owned_key_is_refused_F14_I1(tmp_path):
    with pytest.raises(TutorialRecordError) as refusal:
        _plan(tmp_path, {"nversion.par:simID": "elsewhere"})
    assert "nversion.par:simID" in str(refusal.value) and "F14" in str(refusal.value)


@pytest.mark.parametrize("action", ["plan", "describe"])
def test_a_native_value_the_reader_refuses_is_refused_F10_S_M1(tmp_path, action):
    """The config reader refuses an unquoted ``a=b`` string in the native
    file, which openCARP would truncate. A copy of the tutorial with that
    one line unquoted; the native tree is only read."""
    import shutil

    cases_root = tmp_path / "tutorials"
    case = cases_root / NIEDERER_RELPATH
    shutil.copytree(opencarp_tutorials_root() / NIEDERER_RELPATH, case)
    par = case / "nversion.par"
    text = par.read_text()
    assert 'imp_region[0].im_param = "flags=EPI"' in text
    par.write_text(text.replace('imp_region[0].im_param = "flags=EPI"', "imp_region[0].im_param = flags=EPI"))
    study = {"nversion.par:imp_region[0].im_param": "flags=ENDO"}
    with pytest.raises(TutorialRecordError) as refusal:
        if action == "plan":
            _plan(tmp_path, study, cases_root)
        else:
            describe_entry(
                _ENTRY, overrides={"cases_root": str(cases_root), **study},
                driver_context=load_plugin_context("opencarp"),
            )
    assert "nversion.par:imp_region[0].im_param" in str(refusal.value) and "F10" in str(refusal.value)
