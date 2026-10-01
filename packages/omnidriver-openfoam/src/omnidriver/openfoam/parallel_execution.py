"""OpenFOAM's parallel form of a solve step: ``decomposePar`` -> ``mpirun -np
N <solve> -parallel`` -> ``reconstructPar``, with N the case's own
``system/decomposeParDict:numberOfSubdomains``."""
from __future__ import annotations

from typing import Any, Callable, Mapping

from omnidriver.core.runtime import mpi

DECOMPOSE_PAR_DICT = "system/decomposeParDict"
_SUBDOMAINS_KEY_PATH = ("numberOfSubdomains",)
_SUBDOMAINS = f"{DECOMPOSE_PAR_DICT}:{_SUBDOMAINS_KEY_PATH[0]}"


def parallel_steps_for_record(
    step: Mapping[str, Any], *, request: Any,
    read_value: Callable[[str, tuple[str, ...]], Any], allocation: Any,
) -> list[dict]:
    """The OpenFOAM layer's ``get_parallel_steps`` (core's
    ``SolverPluginOptionalHooks``): a record's serial solve step as
    ``<id>.decompose`` -> ``<id>`` under ``mpirun -np N ... -parallel`` ->
    ``<id>.reconstruct``; later steps follow the reconstruct step.

    N is the case's own ``numberOfSubdomains``, read through ``read_value``.
    A count in the request must equal it, and a scheduler allocation must
    agree with it; neither overrides the other."""
    supplied = mpi.requested(request)
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
    if supplied is not None and supplied != n:
        raise ValueError(
            f"the request asks for {supplied} processes, but {_SUBDOMAINS} is {n}; the "
            f"decomposition and the launched ranks are one number, so set {_SUBDOMAINS} to "
            f"{supplied} in the study, or ask with parallel true"
        )
    mpi.agree(n, allocation, stated_by=_SUBDOMAINS)
    id_ = step["id"]
    solve = mpi.wrap({**step, "args": [*step.get("args", ()), "-parallel"], "depends_on": [f"{id_}.decompose"]}, n)
    return [
        {
            "id": f"{id_}.decompose",
            "command": "decomposePar",
            # -force: a shared case_root across sweep entries can leave a prior
            # case's processor*/ dirs on disk; bare decomposePar refuses to run
            # against those, but -force rmDirs each one first (decomposePar.C).
            # No -time restriction: OpenFOAM's -time <value> matches the
            # *nearest* existing time, not an exact one (timeSelector.C), so a
            # case with no real 0/ could otherwise pick up a leftover
            # reconstructed time from a prior sweep case.
            "args": ["-force"],
            "depends_on": list(step["depends_on"]),
            "consumes": [DECOMPOSE_PAR_DICT],
        },
        solve,
        {"id": f"{id_}.reconstruct", "command": "reconstructPar", "depends_on": [id_]},
    ]
