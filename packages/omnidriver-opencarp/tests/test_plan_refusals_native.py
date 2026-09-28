"""`plan --strict` refuses openCARP studies as JSON, whichever layer refuses.

The index-bound refusal comes from the renderer (``check_indices``), not the
key validator; a key the record's command line owns is refused by the
validator instead. Both must reach an agent through the same JSON.
Scratch goes to tmp_path; the native tree is only read."""
from __future__ import annotations

import json

import pytest

from omnidriver.cli import main
from opencarp_native import NIEDERER_RELPATH, opencarp_tutorials_root

pytestmark = pytest.mark.native_opencarp


def _plan(tmp_path, capsys, study):
    config = tmp_path / "study.json"
    config.write_text(json.dumps(study))
    exit_code = main([
        "plan", "--strict", "--plugin", "opencarp", "--entry", "niedererNVersion",
        "--cases-root", str(opencarp_tutorials_root()), "--config", str(config),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])
    return exit_code, json.loads(capsys.readouterr().out)


def test_an_index_beyond_its_count_is_refused_as_json_F2_I2(tmp_path, capsys):
    exit_code, payload = _plan(tmp_path, capsys, {"nversion.par:stim[1].pulse.strength": 999.0})
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "nversion.par" in payload["error"]
    assert "stim[1].pulse.strength: index 1 is outside num_stim = 1 (F2)" in payload["error"]


def test_a_command_line_owned_key_is_refused_as_json_F14_I1(tmp_path, capsys):
    exit_code, payload = _plan(tmp_path, capsys, {"nversion.par:simID": "elsewhere"})
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "nversion.par:simID" in payload["error"] and "F14" in payload["error"]


@pytest.mark.parametrize("action", [["plan", "--strict"], ["describe"]])
def test_a_native_value_the_reader_refuses_comes_back_as_json_F10_S_M1(tmp_path, capsys, action):
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
    config = tmp_path / "study.json"
    config.write_text(json.dumps({"nversion.par:imp_region[0].im_param": "flags=ENDO"}))
    exit_code = main([
        *action, "--plugin", "opencarp", "--entry", "niedererNVersion",
        "--cases-root", str(cases_root), "--config", str(config),
        "--scratch-dir", str(tmp_path / "scratch"),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert "nversion.par:imp_region[0].im_param" in payload["error"] and "F10" in payload["error"]
