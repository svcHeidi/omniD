"""``cable1DRestitution``'s ``s1s2SpatialProtocol`` axis (tutorials-are-
pointers plan §5e, step 5.2), replacing
``cardiacfoam.tutorials.cable_1d_restitution._build_cases``/``_plan_case``
(deleted alongside this record) -- and the tests those functions had,
``test_cable_restitution_di90.py`` (deleted in the same commit). That file's
central claim survives here: conflating a coupling interval with a
requested DI90 produced a restitution table whose abscissae were mislabelled,
so the two modes must stay distinguishable in the axis's own resolved
patches. Stimulus-list sub-timestep precision is
``spatial_pacing.generate_spatial_stimulus_lists``'s own claim, already
covered by ``test_spatial_pacing.py``; not re-tested here.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.records.cable_1d_restitution import (
    S1_S2_PROTOCOL_AXIS_NAME, _s1_s2_protocol_axis,
)

_ELECTRO_DOCUMENT = "constant/electroProperties"
_CONTROL_DICT_DOCUMENT = "system/controlDict"
_SCOPE = ("monodomainSolverCoeffs",)


def _axis():
    return _s1_s2_protocol_axis(
        S1_S2_PROTOCOL_AXIS_NAME, electro_document=_ELECTRO_DOCUMENT, scope=_SCOPE,
    )


def _patches(protocol):
    result = _axis().resolve(protocol, None)
    return {patch.key_path: patch for patch in result.patches}


def _postprocess_args(protocol):
    result = _axis().resolve(protocol, None)
    return result.command_arguments["postprocess"]


def _start_time_list(by_key_path):
    key = _SCOPE + ("externalStimulus", "stimulusStartTimeList")
    patch = by_key_path[key]
    assert patch.value_kind == "scalar_list"
    return list(patch.value)


def test_axis_declares_a_mapping_value_kind():
    assert _axis().value_kind == "mapping"


def test_coupling_interval_mode_schedules_S2_after_the_last_S1_and_adds_a_propagation_margin():
    """One extra S1 interval past the last S2 (a 1D cable needs propagation
    time a 0-D single cell does not -- module docstring)."""
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1, "s2_interval_ms": 700.0,
    })
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.7])
    end_time = by_key_path[("endTime",)]
    assert end_time.document == _CONTROL_DICT_DOCUMENT
    assert end_time.value == pytest.approx(4.7 + 1.0 + 0.1)


def test_coupling_interval_mode_with_two_S2_beats():
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 2, "end_time_buffer_s": 0.1, "s2_interval_ms": 500.0,
    })
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.5, 5.0])
    assert by_key_path[("endTime",)].value == pytest.approx(5.0 + 1.0 + 0.1)


def test_requested_di90_mode_schedules_S2_at_the_reference_plus_the_requested_interval():
    reference_repolarization90_s = 4.304086260869566
    by_key_path = _patches({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 1.0,
        "requested_di90_ms": 330.0,
        "reference_repolarization90_s": reference_repolarization90_s,
    })
    times = _start_time_list(by_key_path)
    expected_s2 = reference_repolarization90_s + 0.330
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, expected_s2])
    # No extra S1-interval margin in this mode (unlike coupling_interval):
    # the old module's own arithmetic, reproduced exactly.
    assert by_key_path[("endTime",)].value == pytest.approx(expected_s2 + 1.0)


def test_requested_di90_mode_rejects_more_than_one_S2():
    with pytest.raises(ValueError, match="n_s2 == 1"):
        _patches({
            "n_s1": 5, "n_s2": 2, "end_time_buffer_s": 1.0,
            "requested_di90_ms": 330.0, "reference_repolarization90_s": 4.3,
        })


def test_a_case_with_no_S2_schedules_only_the_drive_train():
    """The automaticity control branch: n_s2 == 0 applies no premature
    beat. endTime still carries the one-S1-interval propagation margin."""
    by_key_path = _patches({"n_s1": 5, "n_s2": 0, "end_time_buffer_s": 1.5})
    times = _start_time_list(by_key_path)
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    assert by_key_path[("endTime",)].value == pytest.approx(4.0 + 1.0 + 1.5)


def test_n_s2_greater_than_zero_requires_one_of_the_two_pacing_keys():
    with pytest.raises(ValueError, match="n_s2 > 0 requires"):
        _patches({"n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1})


def test_the_axis_passes_the_S1_S2_split_to_the_postprocess_step():
    """The postprocess step has no other way to know where the case's own
    concatenated ``stimulusStartTimeList`` splits into S1 versus S2 --
    this axis is the only thing that resolved that split."""
    args = _postprocess_args({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 0.1, "s2_interval_ms": 700.0,
    })
    assert args == ("--n-s1", "5", "--n-s2", "1")


def test_the_axis_passes_the_di90_reference_when_this_run_has_one():
    args = _postprocess_args({
        "n_s1": 5, "n_s2": 1, "end_time_buffer_s": 1.0,
        "requested_di90_ms": 330.0, "reference_repolarization90_s": 4.304086260869566,
    })
    assert args == ("--n-s1", "5", "--n-s2", "1", "--reference-repolarization90-s", "4.304086260869566")
