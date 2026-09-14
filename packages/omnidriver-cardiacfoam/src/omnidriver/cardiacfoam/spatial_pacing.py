from __future__ import annotations


def generate_spatial_stimulus_lists(
    times_s: list[float], bounds_min: str, bounds_max: str,
    duration_s: str, intensity: str,
) -> dict[str, str]:
    """Build the cardiacFOAM externalStimulus lists from explicit absolute times.

    Prefer this over `generate_spatial_s1_s2_stimulus_lists` whenever a
    stimulus time is *derived* rather than counted off a cycle length -- a DI90
    protocol schedules S2 at `t(repolarization90) + requestedDI90`, which is not
    a round number and does not survive being reconstructed from an interval.

    Times are written with twelve significant figures. Six is not enough: a
    reference S2 time of 4.634086260869566 s renders as 4.63409 under `.6g`,
    a 3.74 us error, which is nearly four steps at deltaT = 1e-6 s. The cable
    restitution protocol schedules against a measured repolarization time to
    sub-step accuracy, so that rounding lands the premature beat in the wrong
    place on the restitution curve.
    """
    count = len(times_s)
    return {
        "stimulusStartTimeList": "(" + " ".join(f"{time:.12g}" for time in times_s) + ")",
        "stimulusLocationMinList": "(" + " ".join([bounds_min] * count) + ")",
        "stimulusLocationMaxList": "(" + " ".join([bounds_max] * count) + ")",
        "stimulusDurationList": "(" + " ".join([duration_s] * count) + ")",
        "stimulusIntensityList": "(" + " ".join([intensity] * count) + ")",
    }


def generate_spatial_s1_s2_stimulus_lists(
    s1_interval_ms: float, n_s1: int, s2_interval_ms: float, n_s2: int,
    bounds_min: str, bounds_max: str, duration_s: str, intensity: str
) -> dict[str, str]:
    """Build the stimulus lists for an S1 drive train plus an S2 coupling train.

    2026-09-14: this used to format its own times with `.6g` rather than
    delegating, so the precision fix that `generate_spatial_stimulus_lists`
    documents was absent from the only pacing helper any tutorial called. The
    defect was latent for round cycle lengths -- a (0 1 2 3 4 4.5) schedule is
    exact in six figures -- and only appears once a time needs more.
    """
    times = []
    for i in range(n_s1):
        times.append(i * (s1_interval_ms / 1000.0))
    last_s1_time_s = (n_s1 - 1) * (s1_interval_ms / 1000.0)
    for i in range(n_s2):
        times.append(last_s1_time_s + (i + 1) * (s2_interval_ms / 1000.0))

    return generate_spatial_stimulus_lists(
        times, bounds_min, bounds_max, duration_s, intensity
    )
