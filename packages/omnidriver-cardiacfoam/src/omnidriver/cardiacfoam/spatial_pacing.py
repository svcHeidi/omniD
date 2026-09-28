from __future__ import annotations

Vector3 = tuple[float, float, float]


def generate_spatial_stimulus_lists(
    times_s: list[float], bounds_min: Vector3, bounds_max: Vector3,
    duration_s: float, intensity: float,
) -> dict[str, list]:
    """Build the cardiacFOAM ``externalStimulus`` lists from explicit
    absolute times, as native Python sequences -- ``$ELECTRO_MODEL_COEFFS
    .externalStimulus.stimulusStartTimeList``/``stimulusDurationList``/
    ``stimulusIntensityList`` are catalogued ``scalar_list``, and
    ``stimulusLocationMinList``/``MaxList`` are catalogued ``vector3_list``
    (``dict_entries_catalog.py``); a record-key-validated patch must be a
    real sequence of that shape, not pre-joined OpenFOAM list text, or
    ``resolve_case_patches`` refuses it ("must be a sequence").

    Prefer this over `generate_spatial_s1_s2_stimulus_lists` whenever a
    stimulus time is *derived* rather than counted off a cycle length -- a
    DI90 protocol schedules S2 at `t(repolarization90) + requestedDI90`,
    which is not a round number and does not survive being reconstructed
    from an interval.
    """
    count = len(times_s)
    return {
        "stimulusStartTimeList": list(times_s),
        "stimulusLocationMinList": [tuple(bounds_min)] * count,
        "stimulusLocationMaxList": [tuple(bounds_max)] * count,
        "stimulusDurationList": [duration_s] * count,
        "stimulusIntensityList": [intensity] * count,
    }


def generate_spatial_s1_s2_stimulus_lists(
    s1_interval_ms: float, n_s1: int, s2_interval_ms: float, n_s2: int,
    bounds_min: Vector3, bounds_max: Vector3, duration_s: float, intensity: float,
) -> dict[str, list]:
    """Build the stimulus lists for an S1 drive train plus an S2 coupling
    train (n_s2 == 0 emits the drive train alone)."""
    times = []
    for i in range(n_s1):
        times.append(i * (s1_interval_ms / 1000.0))
    last_s1_time_s = (n_s1 - 1) * (s1_interval_ms / 1000.0) if n_s1 else 0.0
    for i in range(n_s2):
        times.append(last_s1_time_s + (i + 1) * (s2_interval_ms / 1000.0))

    return generate_spatial_stimulus_lists(
        times, bounds_min, bounds_max, duration_s, intensity
    )
