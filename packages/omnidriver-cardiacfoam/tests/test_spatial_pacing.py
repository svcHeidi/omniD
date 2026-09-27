"""Guards for the cardiacFOAM stimulus-schedule emitters.

The regression these exist for: `generate_spatial_s1_s2_stimulus_lists` once
formatted its own times with `.6g` instead of delegating, so a derived stimulus
time was silently truncated. Nothing tested this module at all, which is why it
survived the driverFOAM -> OmniD migration unnoticed.

Corrected 2026-09-27 (tutorials-are-pointers plan §5e, step 5.2): both
emitters now return native Python sequences (catalogued
``scalar_list``/``vector3_list``), not pre-joined OpenFOAM list text --
these tests were rewritten for that shape, not the formatting bug they
guard.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.spatial_pacing import (
    generate_spatial_s1_s2_stimulus_lists,
    generate_spatial_stimulus_lists,
)

BOUNDS_MIN = (0.0, 0.0, 0.0)
BOUNDS_MAX = (2e-3, 2e-4, 2e-4)
DURATION_S = 4e-3
INTENSITY = 50000.0


def test_a_derived_stimulus_time_survives_to_sub_timestep_accuracy():
    # The DI90 protocol's reference: repolarization90 at 4.304086260869566 s
    # plus a requested DI90 of 330 ms.
    scheduled = 4.304086260869566 + 0.330
    lists = generate_spatial_stimulus_lists(
        [scheduled], BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    written = lists["stimulusStartTimeList"][0]
    assert abs(written - scheduled) < 1.0e-9, (
        "a scheduled stimulus must survive as a real float, not a truncated string"
    )


def test_the_s1_s2_emitter_shares_that_precision():
    # Drive it with a cycle length that does not land on a round number of
    # seconds.
    lists = generate_spatial_s1_s2_stimulus_lists(
        s1_interval_ms=1000.0 / 3.0, n_s1=4,
        s2_interval_ms=333.0 + 1.0 / 7.0, n_s2=1,
        bounds_min=BOUNDS_MIN, bounds_max=BOUNDS_MAX,
        duration_s=DURATION_S, intensity=INTENSITY,
    )
    written = lists["stimulusStartTimeList"]
    expected = [i * (1000.0 / 3.0) / 1000.0 for i in range(4)]
    expected.append(expected[-1] + (333.0 + 1.0 / 7.0) / 1000.0)
    for got, want in zip(written, expected, strict=True):
        assert abs(got - want) < 1.0e-9


def test_every_list_is_as_long_as_the_schedule():
    times = [0.0, 1.0, 2.0, 2.5]
    lists = generate_spatial_stimulus_lists(
        times, BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    assert lists["stimulusStartTimeList"] == times
    # cardiacFOAM reads these as parallel lists; a short one is a silent
    # misalignment rather than an error, so the count is worth asserting.
    assert lists["stimulusLocationMinList"] == [BOUNDS_MIN] * len(times)
    assert lists["stimulusLocationMaxList"] == [BOUNDS_MAX] * len(times)
    assert lists["stimulusDurationList"] == [DURATION_S] * len(times)
    assert lists["stimulusIntensityList"] == [INTENSITY] * len(times)


def test_the_s1_s2_emitter_places_s2_after_the_last_s1():
    lists = generate_spatial_s1_s2_stimulus_lists(
        s1_interval_ms=1000.0, n_s1=5, s2_interval_ms=500.0, n_s2=1,
        bounds_min=BOUNDS_MIN, bounds_max=BOUNDS_MAX,
        duration_s=DURATION_S, intensity=INTENSITY,
    )
    # This is the schedule the committed cable sweep specs assume.
    assert lists["stimulusStartTimeList"] == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.5])


def test_the_s1_s2_emitter_with_no_s2_emits_the_drive_train_alone():
    lists = generate_spatial_s1_s2_stimulus_lists(
        s1_interval_ms=1000.0, n_s1=5, s2_interval_ms=500.0, n_s2=0,
        bounds_min=BOUNDS_MIN, bounds_max=BOUNDS_MAX,
        duration_s=DURATION_S, intensity=INTENSITY,
    )
    assert lists["stimulusStartTimeList"] == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])


def test_an_empty_schedule_emits_empty_lists_rather_than_malformed_ones():
    lists = generate_spatial_stimulus_lists(
        [], BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    assert lists["stimulusStartTimeList"] == []
    assert lists["stimulusLocationMinList"] == []
