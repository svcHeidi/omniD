from __future__ import annotations

import json
from pathlib import Path

import pytest
from torchcor_testing import context_of, repository_with_runner

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.torchcor.catalog import Catalog
from omnidriver.torchcor.validation import case_diagnostics, validate_key

FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = Catalog.from_describe(json.loads((FIXTURES / "describe.json").read_text()))
CASE = json.loads((FIXTURES / "case.json").read_text())


def _errors(tmp_path: Path, edit=lambda case: None) -> list:
    case = json.loads(json.dumps(CASE))
    edit(case)
    (tmp_path / "case.json").write_text(json.dumps(case))
    return [d for d in case_diagnostics(tmp_path, CATALOG) if d.level == "error"]


def test_the_real_case_passes(tmp_path):
    assert _errors(tmp_path) == []


def test_an_unknown_key_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.update(chi_per_m=140))
    assert error.field == "chi_per_m" and "not a key" in error.message


def test_a_missing_required_key_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.pop("theta"))
    assert error.field == "theta" and "required" in error.message


def test_a_value_of_the_wrong_kind_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.update(mass_lumping="no"))
    assert error.field == "mass_lumping" and "boolean" in error.message


def test_a_value_beyond_its_bounds_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.update(theta=1.5))
    assert error.field == "theta" and "maximum" in error.message
    (error,) = _errors(tmp_path, lambda c: c.update(dx_mm=0))
    assert error.field == "dx_mm" and "exceed" in error.message


def test_an_ionic_model_torchcor_does_not_export_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.update(ionic_model="TenTusscher"))
    assert error.field == "ionic_model" and "TenTusscherPanfilov" in error.message


def test_an_option_the_model_does_not_take_or_a_value_off_its_menu_is_refused(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c["ionic_options"].update(sex="MALE"))
    assert error.field == "ionic_options.sex"
    (error,) = _errors(tmp_path, lambda c: c["ionic_options"].update(cell_type="EPIC"))
    assert error.field == "ionic_options.cell_type" and "'MCELL'" in error.message


def test_an_initial_value_the_model_does_not_hold_is_refused_B6(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c["ionic_init"].update(V_int=-85.23))
    assert error.field == "ionic_init.V_int"


def test_a_device_this_host_cannot_run_is_refused_naming_the_ones_it_can_D12(tmp_path):
    (error,) = _errors(tmp_path, lambda c: c.update(device="mps"))
    assert error.field == "device" and "['cpu']" in error.message


def test_the_key_validator_takes_catalogued_keys_and_model_fields():
    assert validate_key(CATALOG, "case.json", ("conductivity_S_per_m", "et"), 0.2) == ("scalar", True)
    assert validate_key(CATALOG, "case.json", ("ionic_init", "Ki_init"), 138.3) == ("scalar", True)
    assert validate_key(CATALOG, "case.json", ("ionic_options", "cell_type"), "ENDO") == ("string", True)


@pytest.mark.parametrize("document, key_path, value, named", [
    ("case.json", ("chi_per_m",), 140, "chi_per_m"),
    ("other.json", ("dx_mm",), 0.5, "other.json"),
    ("case.json", ("theta",), 2, "theta"),
    ("case.json", ("ionic_init", "V_int"), 1.0, "V_int"),
    ("case.json", ("dtype",), "float16", "dtype"),
])
def test_the_key_validator_refuses_by_name(document, key_path, value, named):
    with pytest.raises(TutorialRecordError, match=named):
        validate_key(CATALOG, document, key_path, value)


def test_without_a_runner_a_key_is_written_unvalidated():
    assert validate_key(None, "case.json", ("chi_per_m",), 140) == ("integer", False)


def test_without_a_repository_the_plan_says_so_once_and_judges_nothing(tmp_path):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    (tmp_path / "case.json").write_text(json.dumps({**CASE, "chi_per_m": 140}))
    plugin, context = TorchCorPlugin(), context_of()
    assert plugin.validate_run_semantics(tmp_path, driver_context=context) == ()
    (note,) = plugin.get_plan_diagnostics(tmp_path, workflow_dag={}, env={}, scratch_root=tmp_path, driver_context=context)
    assert note.code == "torchcor_runner_not_supplied" and note.level == "info" and "--repo" in note.message


def test_the_key_validator_judges_by_the_contexts_repository(tmp_path, monkeypatch):
    from omnidriver.torchcor.plugin import TorchCorPlugin

    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "scratch"))
    validate = TorchCorPlugin().get_record_key_validator(driver_context=context_of(repository_with_runner(tmp_path)))
    assert validate("case.json", ("dx_mm",), 0.25) == ("scalar", True)
    with pytest.raises(TutorialRecordError, match="chi_per_m"):
        validate("case.json", ("chi_per_m",), 140)
    unvalidated = TorchCorPlugin().get_record_key_validator(driver_context=context_of())
    assert unvalidated("case.json", ("chi_per_m",), 140) == ("integer", False)
