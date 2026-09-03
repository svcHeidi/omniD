import pytest
from omnidriver.core.sweep.sweep_derivation_catalog import get_derivation, SWEEP_DERIVATION_CATALOG
from omnidriver.core.sweep.sweep_expansion import SweepValidationError


def test_case_id_template_joins_named_values():
    fn = get_derivation("case_id_template")
    result = fn({"ionicModel": "TNNP", "deltaT": 1e-6})
    assert result == {"caseId": "TNNP_1e-06"}


def test_case_id_template_is_registered():
    assert "case_id_template" in SWEEP_DERIVATION_CATALOG


def test_get_derivation_rejects_unknown_name():
    with pytest.raises(SweepValidationError, match="notARealDerivation"):
        get_derivation("notARealDerivation")


def test_case_id_template_rejects_path_unsafe_values():
    fn = get_derivation("case_id_template")
    with pytest.raises(SweepValidationError, match="path-safe|caseId"):
        fn({"ionicModel": "../TNNP"})


def test_get_derivation_rejects_non_string_name():
    with pytest.raises(SweepValidationError, match="derive"):
        get_derivation(["x"])


def test_output_dir_name_template_joins_named_values():
    fn = get_derivation("output_dir_name_template")
    result = fn({"dx": 0.5, "solver": "implicit"})
    assert result == {"output_dir_name": "0.5_implicit"}


def test_output_dir_name_template_is_registered():
    assert "output_dir_name_template" in SWEEP_DERIVATION_CATALOG


def test_output_dir_name_template_rejects_path_unsafe_values():
    fn = get_derivation("output_dir_name_template")
    with pytest.raises(SweepValidationError, match="path-safe|output_dir_name"):
        fn({"dx": "../escape"})


def test_output_dir_name_template_flattens_list_valued_axes():
    # Entry-based sweep axes are often list-shaped to match a registered
    # tutorial's own make_spec kwargs directly (e.g. niederer_2012.py's
    # dx_values=[0.5]) -- str([0.5]) == "[0.5]" is not path-safe, so list/
    # tuple values must be flattened into the label instead of stringified
    # as a Python literal.
    fn = get_derivation("output_dir_name_template")
    result = fn({"dx_values": [0.5], "dt_values": [0.01, 0.005]})
    assert result == {"output_dir_name": "0.5_0.01-0.005"}


def test_case_id_template_flattens_list_valued_axes():
    fn = get_derivation("case_id_template")
    result = fn({"dx_values": [0.5]})
    assert result == {"caseId": "0.5"}
