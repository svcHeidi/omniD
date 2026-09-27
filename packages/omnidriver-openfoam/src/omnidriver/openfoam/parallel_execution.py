"""OpenFOAM's parallel form of a solve step: ``decomposePar`` -> ``mpirun -np
N <solve> -parallel`` -> ``reconstructPar``, with N the case's own
``system/decomposeParDict:numberOfSubdomains``.

One caller shares :func:`_parallel_form`: a tutorial record's solve step
through core's optional ``get_parallel_steps`` hook
(:func:`parallel_steps_for_record`; PAR, owner Q6, 2026-09-26).

Corrected 2026-09-27 (5.4b-P): the factory path's own ``solve_steps`` was
deleted here, ahead of step C, once its last caller (the
``manufactured_monodomain_pseudo_ecg`` tutorial module) migrated onto a
tutorial record -- no factory tutorial calls it any more (§1's "look one
level further").
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from omnidriver.openfoam.mutators import read_foam_entry

DECOMPOSE_PAR_DICT = "system/decomposeParDict"
_DECOMPOSE_PAR_DICT_RELPATH = Path(DECOMPOSE_PAR_DICT)
_SUBDOMAINS_KEY_PATH = ("numberOfSubdomains",)
_SUBDOMAINS = f"{DECOMPOSE_PAR_DICT}:{_SUBDOMAINS_KEY_PATH[0]}"


def read_number_of_subdomains(
    case_root: Path,
    decompose_par_dict_relpath: Path = _DECOMPOSE_PAR_DICT_RELPATH,
) -> int:
    """Read ``numberOfSubdomains`` from the case's own decomposeParDict."""
    dict_path = case_root / decompose_par_dict_relpath
    value = read_foam_entry(dict_path, "numberOfSubdomains")
    if value is None:
        raise ValueError(
            f"numberOfSubdomains not found in {dict_path} "
            "(required to build a parallel solve step)"
        )
    return int(value)


def _parallel_form(
    solve: Mapping[str, Any], *, n: int, decompose_id: str, reconstruct_id: str,
) -> list[dict]:
    """``solve`` (a DAG step) as its three parallel steps; the solve keeps
    its id and every other field, and runs under ``mpirun -np n``."""
    return [
        {
            "id": decompose_id,
            "command": "decomposePar",
            # -force: entry-based sweeps reuse one shared case_root across
            # cases, so a prior case's processor*/ dirs are still on disk --
            # bare decomposePar refuses to run against those. -force deletes
            # them before decomposing (confirmed via decomposePar.C: a full
            # rmDir per processor* dir, not a merge -- no stale data survives
            # to be read back).
            # Deliberately no -time restriction here: OpenFOAM's -time
            # <value> selects the *nearest* existing time to that value, not
            # an exact match (timeSelector.C) -- for case families with no
            # real 0/ (e.g. manufactured-solution verifiers, whose IC is
            # computed by the solver, not read from disk), "-time 0" would
            # silently match a leftover reconstructed time directory from a
            # prior sweep case instead. Removing any such stale time
            # directories between cases is the sweep runner's job (see
            # sweep_runner._materialize_entry_case), not this step's.
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
    """The OpenFOAM layer's ``get_parallel_steps`` (contract on core's
    ``SolverPluginOptionalHooks``): a record's serial solve step as
    ``<id>.decompose`` -> ``<id>`` under ``mpirun -np N ... -parallel`` ->
    ``<id>.reconstruct``. The steps after it (a ``postProcess -latestTime``)
    follow the reconstruct step, so they read the reconstructed case.

    N is the case's ``numberOfSubdomains``, read through ``read_value`` as
    the run will see it, so a study that sets
    ``system/decomposeParDict:numberOfSubdomains`` changes N; nothing
    restates it. Hence the only request understood is ``True``: a count
    supplied with the request would be a second source for a fact the case
    already states. A scheduler allocation that disagrees with N is refused,
    and neither value overrides the other. The decompose step consumes the
    dictionary, so a run's provenance fingerprints the value N came from.
    """
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
