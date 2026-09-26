"""OpenFOAM restart-time selection for adapter-owned provenance."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path


def selected_start_time(
    case_root: Path,
    *,
    control_dict_relpath: str,
    read_value: Callable[[Path, str], str | None],
    instance_directory_pattern: str,
) -> str:
    """Resolve OpenFOAM ``startFrom``/``startTime`` to one time directory.

    ``instance_directory_pattern`` is the stack's merged
    ``CaseRuntimeConventions.instance_directory_pattern`` -- the same regex
    staging, discovery and snapshots use to recognise a time/instance
    directory. **Corrected 2026-09-26 (final review M5):** this used to
    decide "is this a candidate time directory" with a bare ``float(name)``,
    a second, independent rule that disagreed with the conventions regex on
    names like ``inf``, ``nan``, ``1_0``, ``+1``, ``.5`` or ``1E-05``
    (regex: not an instance; ``float()``: parses, so ``latestTime`` could
    pick ``inf``). The time-directory rule is now stated once, here, by
    reading the same value staging/discovery already read instead of
    re-deriving it.

    **M5's other half -- refusing a missing ``controlDict``/``startTime``
    instead of answering the silent default ``"0"`` -- was attempted and
    reverted the same day.** It broke a real, pre-existing capability:
    `omnidriver-cardiaccore`'s `test_controlled_allrun_executes_without_
    domain_claims` runs `omnidriver run --strict` against a case that is
    deliberately NOT OpenFOAM-shaped (an `Allrun`-only folder, no
    `controlDict` at all) through the composed
    `OpenFOAMEnvironmentPlugin`+`CardiacCorePlugin` stack, and it must keep
    succeeding -- that is the test's whole point ("without domain claims").
    Refusing here would break every such case, not just a malformed one;
    core cannot tell "this case is missing a file it needs" from "this case
    was never OpenFOAM-shaped and `get_input_roots` should say so quietly"
    without more context than this function has. Left for an owner decision
    (final-fix-report.md, concerns) rather than silently reintroduced or
    silently dropped.
    """
    default = "0"
    control_dict = case_root / control_dict_relpath
    if not control_dict.is_file():
        return default

    start_from = (read_value(control_dict, "startFrom") or "startTime").strip()
    if start_from not in {"latestTime", "firstTime"}:
        value = read_value(control_dict, "startTime")
        return value.strip() if value is not None else default

    pattern = re.compile(instance_directory_pattern)
    candidates: list[str] = []
    try:
        children = case_root.iterdir()
    except OSError:
        return default
    for child in children:
        if not child.is_dir():
            continue
        if not pattern.fullmatch(child.name):
            continue
        candidates.append(child.name)
    if not candidates:
        return default
    selector = max if start_from == "latestTime" else min
    return selector(candidates, key=float)
