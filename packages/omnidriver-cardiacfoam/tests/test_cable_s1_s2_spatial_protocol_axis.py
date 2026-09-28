"""``cable1DRestitution``'s ``s1s2SpatialProtocol`` axis: coupling-interval and requested-DI90
modes must stay distinguishable, or the restitution table's abscissae are mislabelled. The fixture
reproduces the native ``externalStimulus`` defaults, which the axis reads instead of a Python constant."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.cardiacfoam.records.cable_1d_restitution import (
    S1_S2_PROTOCOL_AXIS_NAME, _s1_s2_protocol_axis,
)

_ELECTRO_DOCUMENT = "constant/electroProperties"
_CONTROL_DICT_DOCUMENT = "system/controlDict"
_SCOPE = ("monodomainSolverCoeffs",)

_NATIVE_ELECTRO_PROPERTIES = """\
monodomainSolverCoeffs
{
    externalStimulus
    {
        stimulusLocationMinList    ((0 0 0) (0 0 0) (0 0 0) (0 0 0) (0 0 0) (0 0 0));
        stimulusLocationMaxList    ((2e-3 2e-4 2e-4) (2e-3 2e-4 2e-4) (2e-3 2e-4 2e-4) (2e-3 2e-4 2e-4) (2e-3 2e-4 2e-4) (2e-3 2e-4 2e-4));
        stimulusDurationList    (4e-3 4e-3 4e-3 4e-3 4e-3 4e-3);
        stimulusIntensityList    (50000 50000 50000 50000 50000 50000);
        stimulusStartTimeList    (0 1 2 3 4 4.5);
    }
}
"""


def _staged_case(tmp_path: Path) -> Path:
    case_root = tmp_path / "case"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "electroProperties").write_text(_NATIVE_ELECTRO_PROPERTIES)
    return case_root


def _axis():
    return _s1_s2_protocol_axis(
        S1_S2_PROTOCOL_AXIS_NAME, electro_document=_ELECTRO_DOCUMENT, scope=_SCOPE,
    )


def _patches(protocol, staged_case_root):
    result = _axis().resolve(protocol, staged_case_root)
    return {patch.key_path: patch for patch in result.patches}


def _postprocess_args(protocol, staged_case_root):
    result = _axis().resolve(protocol, staged_case_root)
    return result.command_arguments["postprocess"]


def _start_time_list(by_key_path):
    key = _SCOPE + ("externalStimulus", "stimulusStartTimeList")
    patch = by_key_path[key]
    assert patch.value_kind == "scalar_list"
    return list(patch.value)


def test_axis_declares_a_mapping_value_kind():
    assert _axis().value_kind == "mapping"


def test_coupling_interval_mode_schedules_S2_after_the_last_S1_and_adds_a_propagation_margin(tmp_path):
    """A 1D cable needs propagation time, one S1 interval past the last S2, that a 0-D single cell does not."""
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1, "s2_interval_ms": 700.0,
    }, _staged_case(tmp_path))
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.7])
    end_time = by_key_path[("endTime",)]
    assert end_time.document == _CONTROL_DICT_DOCUMENT
    assert end_time.value == pytest.approx(4.7 + 1.0 + 0.1)


def test_coupling_interval_mode_with_two_S2_beats(tmp_path):
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 2, "end_time_buffer_s": 0.1, "s2_interval_ms": 500.0,
    }, _staged_case(tmp_path))
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.0])
    assert by_key_path[("endTime",)].value == pytest.approx(5.0 + 1.0 + 0.1)


def test_requested_di90_mode_schedules_S2_at_the_reference_plus_the_requested_interval(tmp_path):
    reference_repolarization90_s = 4.304086260869566
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 1.0,
        "requested_di90_ms": 330.0,
        "reference_repolarization90_s": reference_repolarization90_s,
    }, _staged_case(tmp_path))
    times = _start_time_list(by_key_path)
    expected_s2 = reference_repolarization90_s + 0.330
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, expected_s2])
    # No extra S1-interval margin in this mode, unlike coupling_interval.
    assert by_key_path[("endTime",)].value == pytest.approx(expected_s2 + 1.0)


def test_requested_di90_mode_rejects_more_than_one_S2(tmp_path):
    with pytest.raises(ValueError, match="n_s2 == 1"):
        _patches({
            "n_s1": 5, "n_s2": 2, "end_time_buffer_s": 1.0,
            "requested_di90_ms": 330.0, "reference_repolarization90_s": 4.3,
        }, _staged_case(tmp_path))


def test_a_case_with_no_S2_schedules_only_the_drive_train(tmp_path):
    """The automaticity control (n_s2 == 0) still carries the one-S1-interval endTime margin."""
    by_key_path = _patches({"n_s1": 5, "n_s2": 0, "end_time_buffer_s": 1.5}, _staged_case(tmp_path))
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    assert by_key_path[("endTime",)].value == pytest.approx(4.0 + 1.0 + 1.5)


def test_n_s2_greater_than_zero_requires_one_of_the_two_pacing_keys(tmp_path):
    with pytest.raises(ValueError, match="n_s2 > 0 requires"):
        _patches({"n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1}, _staged_case(tmp_path))


def test_the_axis_passes_the_S1_S2_split_to_the_postprocess_step(tmp_path):
    """Only this axis knows where the concatenated ``stimulusStartTimeList`` splits into S1 versus S2."""
    args = _postprocess_args({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1, "s2_interval_ms": 700.0,
    }, _staged_case(tmp_path))
    assert args == ("--n-s1", "5", "--n-s2", "1")


def test_the_axis_passes_the_di90_reference_when_this_run_has_one(tmp_path):
    args = _postprocess_args({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 1.0,
        "requested_di90_ms": 330.0, "reference_repolarization90_s": 4.304086260869566,
    }, _staged_case(tmp_path))
    assert args == ("--n-s1", "5", "--n-s2", "1", "--reference-repolarization90-s", "4.304086260869566")


def test_a_non_uniform_native_list_is_refused_by_name(tmp_path):
    """The axis takes a list's first entry as the shared geometry, so it refuses rather than guesses."""
    case_root = _staged_case(tmp_path)
    text = (case_root / "constant" / "electroProperties").read_text()
    text = text.replace(
        "stimulusIntensityList    (50000 50000 50000 50000 50000 50000);",
        "stimulusIntensityList    (50000 60000 50000 50000 50000 50000);",
    )
    (case_root / "constant" / "electroProperties").write_text(text)
    with pytest.raises(ValueError, match="not uniform"):
        _patches({"n_s1": 5, "n_s2": 0, "end_time_buffer_s": 1.5}, case_root)


def test_a_start_time_list_with_fewer_than_two_entries_is_refused_by_name(tmp_path):
    case_root = _staged_case(tmp_path)
    text = (case_root / "constant" / "electroProperties").read_text()
    text = text.replace(
        "stimulusStartTimeList    (0 1 2 3 4 4.5);",
        "stimulusStartTimeList    (0);",
    )
    (case_root / "constant" / "electroProperties").write_text(text)
    with pytest.raises(ValueError, match="fewer than 2"):
        _patches({"n_s1": 1, "n_s2": 0, "end_time_buffer_s": 1.5}, case_root)
