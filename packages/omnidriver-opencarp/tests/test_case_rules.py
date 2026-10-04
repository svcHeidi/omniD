"""A bound is evaluated against the resolved case where its grammar allows; any other is reported as unchecked."""
from __future__ import annotations

from omnidriver.opencarp.case_rules import case_diagnostics
from omnidriver.opencarp.plugin import OpenCARPPlugin


def _case(tmp_path, text):
    (tmp_path / "nversion.par").write_text(text)
    return tmp_path


def _by_level(case_root):
    found = {"error": [], "info": []}
    for item in case_diagnostics(case_root):
        found[item.level].append(item)
    return found


def test_a_value_beyond_a_bound_that_names_a_parameter_is_an_error_at_that_parameters_value(tmp_path):
    (error,) = _by_level(_case(tmp_path, "tend = 150\nspacedt = 1000\n"))["error"]
    assert (error.field, error.message) == ("spacedt", "spacedt = 1000 is beyond its maximum, tend = 150")


def test_the_bound_takes_the_catalogue_default_of_a_parameter_the_case_leaves_out(tmp_path):
    (error,) = _by_level(_case(tmp_path, "spacedt = 1000\n"))["error"]
    assert error.message == "spacedt = 1000 is beyond its maximum, tend = 100"


def test_a_value_within_its_bounds_is_no_error_and_no_note(tmp_path):
    assert case_diagnostics(_case(tmp_path, "tend = 150\nspacedt = 100\n")) == ()


def test_arithmetic_over_parameters_is_evaluated(tmp_path):
    (error,) = _by_level(_case(tmp_path, "dt = 10\nspacedt = 0.005\n"))["error"]
    assert error.message == "spacedt = 0.005 is beyond its minimum, dt/1000. = 0.01"
    assert _by_level(_case(tmp_path, "dt = 10\nspacedt = 0.01\n"))["error"] == []


def test_a_parent_index_stands_for_the_index_of_the_key_being_judged(tmp_path):
    text = "num_stim = 2\nstim[1].ptcl.start = 40\nstim[1].ptcl.duration = 70\n"
    (error,) = _by_level(_case(tmp_path, text))["error"]
    assert error.message == "stim[1].ptcl.duration = 70 is beyond its maximum, tend-stim[PrMelem1].ptcl.start = 60"


def test_a_bound_outside_the_grammar_is_a_note_not_a_judgement(tmp_path):
    found = _by_level(_case(tmp_path, "stimulus[0].npls = 3\n"))
    assert found["error"] == []
    (note,) = found["info"]
    assert (note.code, note.field) == ("opencarp_bound_not_checked", "stimulus[0].npls")
    assert "was not checked" in note.message


def test_a_value_the_case_does_not_set_is_not_judged(tmp_path):
    assert case_diagnostics(_case(tmp_path, "num_stim = 1\n")) == ()


def test_the_rules_carry_the_errors_and_the_plan_the_notes(tmp_path):
    case = _case(tmp_path, "tend = 150\nspacedt = 1000\nstimulus[0].npls = 3\n")
    plugin = OpenCARPPlugin()
    assert {item.level for item in plugin.validate_run_semantics(case)} == {"error"}
    planned = plugin.get_plan_diagnostics(case, workflow_dag=None, env={}, scratch_root=None, driver_context=None)
    assert planned and all(item.level == "info" for item in planned)


def test_the_unmodified_native_case_judges_clean():
    from pathlib import Path

    native = Path(__file__).parent / "fixtures" / "tutorials" / "02_EP_tissue" / "03E_study_resolution"
    assert case_diagnostics(native) == ()
