import pytest

from omnidriver.core.plugin_interface import generic_openfoam_context
from omnidriver.openfoam.apply_overrides import OverrideError, apply_overrides


def _case(tmp_path):
    case = tmp_path / "case"
    (case / "system").mkdir(parents=True)
    (case / "system/controlDict").write_text("deltaT 0.01;\n")
    (case / "system/fvSolution").write_text("solvers { V { tolerance 1e-6; } }\n")
    return case


def test_later_missing_key_restores_all_prior_dictionary_edits(tmp_path):
    case = _case(tmp_path)
    originals = {path: path.read_bytes() for path in (case / "system").iterdir()}
    with pytest.raises(OverrideError, match="missingKey"):
        apply_overrides([
            {"driver_path": "system/controlDict:deltaT", "value": "0.02"},
            {"driver_path": "system/fvSolution:solvers/V/tolerance", "value": "1e-8"},
            {"driver_path": "system/controlDict:missingKey", "value": "1"},
        ], case_root=case, driver_context=generic_openfoam_context())
    assert {path: path.read_bytes() for path in originals} == originals


def test_successful_multi_file_override_is_retained(tmp_path):
    case = _case(tmp_path)
    apply_overrides([
        {"driver_path": "system/controlDict:deltaT", "value": "0.02"},
        {"driver_path": "system/fvSolution:solvers/V/tolerance", "value": "1e-8"},
    ], case_root=case, driver_context=generic_openfoam_context())
    assert "0.02" in (case / "system/controlDict").read_text()
    assert "1e-8" in (case / "system/fvSolution").read_text()


def test_external_symlink_target_is_rejected_before_any_edit(tmp_path):
    case = _case(tmp_path)
    outside = tmp_path / "external"
    outside.write_text("value 1;\n")
    (case / "system/shared").symlink_to(outside)
    with pytest.raises(OverrideError, match="outside the case"):
        apply_overrides([
            {"driver_path": "system/controlDict:deltaT", "value": "0.02"},
            {"driver_path": "system/shared:value", "value": "2"},
        ], case_root=case, driver_context=generic_openfoam_context())
    assert (case / "system/controlDict").read_text() == "deltaT 0.01;\n"
    assert outside.read_text() == "value 1;\n"
