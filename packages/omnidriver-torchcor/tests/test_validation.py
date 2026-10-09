from __future__ import annotations

import json

import pytest
from torchcor_testing import FIXTURES, context_of, repository_with_runner

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.torchcor.catalog import Catalog
from omnidriver.torchcor.plugin import TorchCorPlugin
from omnidriver.torchcor.validation import validate_key

CATALOG = Catalog.from_describe(json.loads((FIXTURES / "describe.json").read_text()))
CASE = (FIXTURES / "case.json").read_text()


def _staged(tmp_path):
    root = repository_with_runner(tmp_path)
    case = tmp_path / "staged"
    case.mkdir()
    (case / "case.json").write_text(CASE)
    return root, case


def test_the_case_rules_are_the_runners_check_each_refusal_an_error(tmp_path):
    root, case = _staged(tmp_path)
    found = TorchCorPlugin().validate_run_semantics(case, driver_context=context_of(root))
    refused = json.loads((FIXTURES / "check-refused.json").read_text())["refusals"]
    assert [(d.level, d.code, d.field) for d in found] == [("error", "torchcor_case_refused", r["key"]) for r in refused]
    assert all(r["message"] in d.message for d, r in zip(found, refused))


def test_a_check_that_cannot_run_refuses_the_case_naming_the_command_and_its_stderr(tmp_path):
    root, case = _staged(tmp_path)
    (root / "scripts" / "run_case.py").write_text("import sys\nsys.exit('no torchcor here')\n")
    (error,) = TorchCorPlugin().validate_run_semantics(case, driver_context=context_of(root))
    assert error.level == "error" and error.code == "torchcor_check_failed"
    assert "--check" in error.message and "no torchcor here" in error.message


def test_the_key_validator_takes_catalogued_keys_and_model_fields_with_the_runners_kinds():
    assert validate_key(CATALOG, "case.json", ("conductivity_S_per_m", "et"), 0.2) == ("scalar", True)
    assert validate_key(CATALOG, "case.json", ("ionic_init", "Ki_init"), 138.3) == ("scalar", True)
    assert validate_key(CATALOG, "case.json", ("ionic_options", "cell_type"), "ENDO") == ("string", True)


@pytest.mark.parametrize("document, key_path, value, named", [
    ("case.json", ("chi_per_m",), 140, "chi_per_m"),
    ("other.json", ("dx_mm",), 0.5, "other.json"),
    ("case.json", ("mass_lumping",), "no", "boolean"),
    ("case.json", ("ionic_init", "V_int"), 1.0, "V_int"),
    ("case.json", ("ionic_init", "Ki_init"), "high", "scalar"),
    ("case.json", ("ionic_options", "cell_type"), 1, "string"),
])
def test_the_key_validator_refuses_by_name(document, key_path, value, named):
    with pytest.raises(TutorialRecordError, match=named):
        validate_key(CATALOG, document, key_path, value)


def test_without_a_runner_a_key_is_written_unvalidated():
    assert validate_key(None, "case.json", ("chi_per_m",), 140) == ("integer", False)


def test_without_a_repository_the_plan_says_so_once_and_judges_nothing(tmp_path):
    (tmp_path / "case.json").write_text(json.dumps({**json.loads(CASE), "chi_per_m": 140}))
    plugin, context = TorchCorPlugin(), context_of()
    assert plugin.validate_run_semantics(tmp_path, driver_context=context) == ()
    (note,) = plugin.get_plan_diagnostics(tmp_path, workflow_dag={}, env={}, scratch_root=tmp_path, driver_context=context)
    assert note.code == "torchcor_runner_not_supplied" and note.level == "info" and "--repo" in note.message


def test_the_key_validator_judges_by_the_contexts_repository(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "scratch"))
    validate = TorchCorPlugin().get_record_key_validator(driver_context=context_of(repository_with_runner(tmp_path)))
    assert validate("case.json", ("dx_mm",), 0.25) == ("scalar", True)
    with pytest.raises(TutorialRecordError, match="chi_per_m"):
        validate("case.json", ("chi_per_m",), 140)
    unvalidated = TorchCorPlugin().get_record_key_validator(driver_context=context_of())
    assert unvalidated("case.json", ("chi_per_m",), 140) == ("integer", False)
