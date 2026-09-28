"""OpenFOAM's parallel form of a solve step: ``decomposePar`` -> ``mpirun -np
N <solve> -parallel`` -> ``reconstructPar``, with N the case's own
``system/decomposeParDict:numberOfSubdomains``."""
from __future__ import annotations

from typing import Any, Callable, Mapping

DECOMPOSE_PAR_DICT = "system/decomposeParDict"
_SUBDOMAINS_KEY_PATH = ("numberOfSubdomains",)
_SUBDOMAINS = f"{DECOMPOSE_PAR_DICT}:{_SUBDOMAINS_KEY_PATH[0]}"


def _parallel_form(
    solve: Mapping[str, Any], *, n: int, decompose_id: str, reconstruct_id: str,
) -> list[dict]:
    """``solve`` (a DAG step) as its three parallel steps under ``mpirun -np n``."""
    return [
        {
            "id": decompose_id,
            "command": "decomposePar",
            # -force: a shared case_root across sweep entries can leave a prior
            # case's processor*/ dirs on disk; bare decomposePar refuses to run
            # against those, but -force rmDirs each one first (decomposePar.C).
            # No -time restriction: OpenFOAM's -time <value> matches the
            # *nearest* existing time, not an exact one (timeSelector.C), so a
            # case with no real 0/ could otherwise pick up a leftover
            # reconstructed time from a prior sweep case; clearing stale time
            # dirs between cases is sweep_runner._materialize_entry_case's job.
            "args": ["-force"],
            "depends_on": list(solve["depends_on"]),
        },
        {
            **solve,
            "command": "mpirun",
            "args": ["-np", str(n), solve["command"], *solve.get("args", ()), "-parallel"],
            "depends_on": [decompose_id],
        },
        {"id": reconstruct_id, "command": "reconstructPar", "depends_on": [solve["id"]]},
    ]


def parallel_steps_for_record(
    step: Mapping[str, Any], *, request: Any,
    read_value: Callable[[str, tuple[str, ...]], Any], allocation: Any,
) -> list[dict]:
    """The OpenFOAM layer's ``get_parallel_steps`` (core's
    ``SolverPluginOptionalHooks``): a record's serial solve step as
    ``<id>.decompose`` -> ``<id>`` under ``mpirun -np N ... -parallel`` ->
    ``<id>.reconstruct``; later steps follow the reconstruct step.

    N is read from the case's own ``numberOfSubdomains`` via ``read_value``,
    so the only request understood is ``True`` -- a count would be a second
    source for a fact the case already states. A scheduler allocation that
    disagrees with N is refused rather than overriding either value."""
    if request is not True:
        raise ValueError(
            f"OpenFOAM runs parallel on the {_SUBDOMAINS} subdomains the case states, so the "
            f"request takes no count (got {request!r}); ask with parallel true (or --parallel "
            f"with no value) and set N through {_SUBDOMAINS}"
        )
    raw = read_value(DECOMPOSE_PAR_DICT, _SUBDOMAINS_KEY_PATH)
    if raw is None:
        raise ValueError(
            f"the case states no {_SUBDOMAINS}, so there is no decomposition to run in parallel; "
            f"the native case's {DECOMPOSE_PAR_DICT}, or a study value for {_SUBDOMAINS}, supplies it"
        )
    try:
        n = int(str(raw).strip())
    except ValueError:
        n = 0
    if n < 1:
        raise ValueError(f"{_SUBDOMAINS} is {raw!r}, not a positive integer")
    if allocation is not None and allocation.ranks != n:
        raise ValueError(
            f"the scheduler allocated {allocation.variable}={allocation.ranks} processes, but "
            f"{_SUBDOMAINS} is {n}; set {_SUBDOMAINS} to {allocation.ranks} in the study, or "
            f"request {n} processes from the scheduler"
        )
    steps = _parallel_form(
        step, n=n, decompose_id=f"{step['id']}.decompose", reconstruct_id=f"{step['id']}.reconstruct",
    )
    steps[0]["consumes"] = [DECOMPOSE_PAR_DICT]
    return steps
