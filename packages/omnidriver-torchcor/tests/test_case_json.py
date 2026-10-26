from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.torchcor.case_json import CaseJsonError, patch, read_value, values_agree

CASE = (Path(__file__).parent / "fixtures" / "case.json").read_text()


def test_a_dotted_key_reads_into_nested_objects():
    assert read_value(CASE, "conductivity_S_per_m.et") == 0.24
    assert read_value(CASE, "dx_mm") == 0.5
    assert read_value(CASE, "conductivity_S_per_m.ex") is None
    assert read_value(CASE, "dx_mm.x") is None


def test_a_patch_sets_a_nested_scalar_and_keeps_everything_else_in_order():
    patched = patch(CASE, {"conductivity_S_per_m.et": 0.2, "dx_mm": 0.25})
    before, after = json.loads(CASE), json.loads(patched)
    assert after["conductivity_S_per_m"] == {**before["conductivity_S_per_m"], "et": 0.2}
    assert after["dx_mm"] == 0.25
    assert list(after) == list(before)
    assert {k: v for k, v in after.items() if k not in ("conductivity_S_per_m", "dx_mm")} == {
        k: v for k, v in before.items() if k not in ("conductivity_S_per_m", "dx_mm")
    }
    assert patched.endswith("}\n")


def test_a_patch_may_add_a_field_to_an_existing_object():
    assert json.loads(patch(CASE, {"ionic_init.Ki_init": 138.3}))["ionic_init"]["Ki_init"] == 138.3


def test_a_list_element_is_refused_by_name():
    with pytest.raises(CaseJsonError, match="slab_mm.0"):
        patch(CASE, {"slab_mm.0": 10})


def test_values_agree_compares_numbers_as_floats_and_booleans_as_booleans():
    assert values_agree("scalar", 1e-3, 0.001)
    assert values_agree("scalar", 1, 1.0)
    assert not values_agree("scalar", 0.24, 0.2)
    assert not values_agree("boolean", True, 1)
    assert values_agree("vector3", [20, 7, 3], [20, 7, 3])


def test_the_renderer_writes_the_patched_document_with_the_digest_of_the_bytes_before(tmp_path):
    from omnidriver.core.case_write import digest_bytes
    from omnidriver.torchcor.plugin import TorchCorPlugin

    (tmp_path / "case.json").write_text(CASE)
    resolved = type("Resolved", (), {"targets": (
        {"document": "case.json", "key_path": ["dx_mm"], "value": 0.25, "operation": "ensure"},
    )})()
    (rendered,) = TorchCorPlugin().render_case_files(resolved, snapshot_root=tmp_path, driver_context=None)
    assert rendered.format == "torchcor_case_json"
    assert rendered.path == "case.json" and rendered.exists_before
    assert rendered.before_digest == digest_bytes(CASE.encode())
    assert json.loads(rendered.content)["dx_mm"] == 0.25


def _rendered(tmp_path, key, value, operation):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    (tmp_path / "case.json").write_text(CASE)
    resolved = type("Resolved", (), {"targets": (
        {"document": "case.json", "key_path": key.split("."), "value": value, "operation": operation},
    )})()
    (rendered,) = TorchCorPlugin().render_case_files(resolved, snapshot_root=tmp_path, driver_context=None)
    return json.loads(rendered.content)


def test_a_validated_key_may_add_a_field_of_the_ionic_model_the_case_rules_then_judge(tmp_path):
    assert _rendered(tmp_path, "ionic_init.GKs_init", 0.392, "ensure")["ionic_init"]["GKs_init"] == 0.392
    assert _rendered(tmp_path, "ionic_options.sex", "MALE", "ensure")["ionic_options"]["sex"] == "MALE"


def test_an_unvalidated_key_only_replaces_one_the_document_holds(tmp_path):
    assert _rendered(tmp_path, "ionic_init.V_init", -85.0, "set")["ionic_init"]["V_init"] == -85.0
    with pytest.raises(CaseJsonError, match=r"ionic_init.V_int.*no runner to judge keys.*--repo"):
        _rendered(tmp_path, "ionic_init.V_int", -85.0, "set")
