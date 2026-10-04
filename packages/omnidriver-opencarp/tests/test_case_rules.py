"""A bound that names another parameter is evaluated against the resolved case; an expression is reported as unchecked."""
from __future__ import annotations

from omnidriver.opencarp.case_rules import case_diagnostics
from omnidriver.opencarp.plugin import OpenCARPPlugin


def _case(tmp_path, text):
    (tmp_path / "nversion.par").write_text(text)
    return tmp_path


def _by_level(case_root):
    found = {"error": [], "warning": []}
    for item in case_diagnostics(case_root):
        found[item.level].append(item)
    return found


def test_a_value_beyond_a_bound_that_names_a_parameter_is_an_error_at_that_parameters_value(tmp_path):
    (error,) = _by_level(_case(tmp_path, "tend = 150\nspacedt = 1000\n"))["error"]
    assert (error.field, error.message) == ("spacedt", "spacedt = 1000 is beyond its maximum, tend = 150")


def test_the_bound_takes_the_catalogue_default_of_a_parameter_the_case_leaves_out(tmp_path):
    (error,) = _by_level(_case(tmp_path, "spacedt = 1000\n"))["error"]
    assert error.message == "spacedt = 1000 is beyond its maximum, tend = 100"


def test_a_value_within_its_bound_is_no_error(tmp_path):
    assert _by_level(_case(tmp_path, "tend = 150\nspacedt = 100\n"))["error"] == []


def test_a_bound_written_as_an_expression_is_reported_as_not_checked(tmp_path):
    warnings = _by_level(_case(tmp_path, "tend = 150\n"))["warning"]
    assert [(item.code, item.field) for item in warnings] == [("opencarp_bound_not_checked", "tend")]
    assert "'dt/1000.'" in warnings[0].message and "was not checked" in warnings[0].message


def test_a_value_the_case_does_not_set_is_not_judged(tmp_path):
    assert case_diagnostics(_case(tmp_path, "num_stim = 1\n")) == ()


def test_the_plan_carries_the_warnings_and_the_rules_the_errors(tmp_path):
    case = _case(tmp_path, "tend = 150\nspacedt = 1000\n")
    plugin = OpenCARPPlugin()
    assert {item.level for item in plugin.validate_run_semantics(case)} == {"error", "warning"}
    planned = plugin.get_plan_diagnostics(case, workflow_dag=None, env={}, scratch_root=None, driver_context=None)
    assert planned and all(item.level == "warning" for item in planned)
