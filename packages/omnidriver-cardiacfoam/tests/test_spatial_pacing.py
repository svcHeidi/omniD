"""Guards for the cardiacFOAM stimulus-schedule emitters.

The regression these exist for: `generate_spatial_s1_s2_stimulus_lists` once
formatted its own times with `.6g` instead of delegating, so a derived stimulus
time was silently truncated. Nothing tested this module at all, which is why it
survived the driverFOAM -> OmniD migration unnoticed.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.spatial_pacing import (
    generate_spatial_s1_s2_stimulus_lists,
    generate_spatial_stimulus_lists,
)

BOUNDS_MIN = "(0 0 0)"
BOUNDS_MAX = "(2e-3 2e-4 2e-4)"
DURATION_S = "4e-3"
INTENSITY = "50000"


def _times(lists: dict[str, str]) -> list[float]:
    return [float(token) for token in lists["stimulusStartTimeList"].strip("()").split()]


def test_a_derived_stimulus_time_survives_to_sub_timestep_accuracy():
    # The DI90 protocol's reference: repolarization90 at 4.304086260869566 s
    # plus a requested DI90 of 330 ms. Under `.6g` this rendered as 4.63409,
    # a 3.74 us error -- nearly four steps at the protocol's deltaT = 1e-6 s.
    scheduled = 4.304086260869566 + 0.330
    lists = generate_spatial_stimulus_lists(
        [scheduled], BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    written = _times(lists)[0]
    assert abs(written - scheduled) < 1.0e-9, (
        "a scheduled stimulus must survive formatting to well inside one 1e-6 s step"
    )


def test_the_s1_s2_emitter_shares_that_precision():
    # The defect was that this entry point did its own formatting. Drive it with
    # a cycle length that does not land on a round number of seconds.
    lists = generate_spatial_s1_s2_stimulus_lists(
        s1_interval_ms=1000.0 / 3.0, n_s1=4,
        s2_interval_ms=333.0 + 1.0 / 7.0, n_s2=1,
        bounds_min=BOUNDS_MIN, bounds_max=BOUNDS_MAX,
        duration_s=DURATION_S, intensity=INTENSITY,
    )
    written = _times(lists)
    expected = [i * (1000.0 / 3.0) / 1000.0 for i in range(4)]
    expected.append(expected[-1] + (333.0 + 1.0 / 7.0) / 1000.0)
    for got, want in zip(written, expected, strict=True):
        assert abs(got - want) < 1.0e-9


def test_every_list_is_as_long_as_the_schedule():
    times = [0.0, 1.0, 2.0, 2.5]
    lists = generate_spatial_stimulus_lists(
        times, BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    assert _times(lists) == times
    # cardiacFOAM reads these as parallel lists; a short one is a silent
    # misalignment rather than an error, so the count is worth asserting.
    assert lists["stimulusLocationMinList"].count(BOUNDS_MIN) == len(times)
    assert lists["stimulusLocationMaxList"].count(BOUNDS_MAX) == len(times)
    assert lists["stimulusDurationList"].count(DURATION_S) == len(times)
    assert lists["stimulusIntensityList"].count(INTENSITY) == len(times)


def test_the_s1_s2_emitter_places_s2_after_the_last_s1():
    lists = generate_spatial_s1_s2_stimulus_lists(
        s1_interval_ms=1000.0, n_s1=5, s2_interval_ms=500.0, n_s2=1,
        bounds_min=BOUNDS_MIN, bounds_max=BOUNDS_MAX,
        duration_s=DURATION_S, intensity=INTENSITY,
    )
    # This is the schedule the committed cable sweep specs assume.
    assert _times(lists) == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.5])


def test_an_empty_schedule_emits_empty_lists_rather_than_malformed_ones():
    lists = generate_spatial_stimulus_lists(
        [], BOUNDS_MIN, BOUNDS_MAX, DURATION_S, INTENSITY
    )
    assert lists["stimulusStartTimeList"] == "()"
    assert lists["stimulusLocationMinList"] == "()"
