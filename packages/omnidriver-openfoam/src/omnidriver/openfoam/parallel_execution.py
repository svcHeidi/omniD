from __future__ import annotations

from pathlib import Path

from omnidriver.openfoam.mutators import read_foam_entry

_DECOMPOSE_PAR_DICT_RELPATH = Path("system/decomposeParDict")


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


def solve_steps(
    *,
    solve_id: str,
    solve_command: str,
    depends_on: list[str],
    run_in_parallel: bool,
    case_root: Path | None,
    num_subdomains: int | None = None,
    decompose_par_dict_relpath: Path = _DECOMPOSE_PAR_DICT_RELPATH,
) -> tuple[list[dict], str]:
    """Build the workflow_dag step(s) for a solve, serial or parallel.

    ``num_subdomains`` supplies the MPI rank count directly; when it is
    ``None`` the count is read from the case's own ``decomposeParDict``, which
    requires ``case_root``.

    Returns ``(steps, final_step_id)`` — callers whose next workflow_dag
    step depends on the solve (e.g. bath's ``interfaceMetrics``, which needs
    the reconstructed mesh) must depend on ``final_step_id``, not on
    ``solve_id`` directly, since that differs between the two modes.
    """
    if not run_in_parallel:
        return (
            [{"id": solve_id, "command": solve_command, "depends_on": depends_on}],
            solve_id,
        )

    # The case's own decomposeParDict is AUTHORITATIVE whenever it exists, and
    # num_subdomains is the fallback for when it does not -- deliberately that
    # way round, not "explicit wins".
    #
    # `decomposePar` reads the same dictionary. If the dict says 6 and this
    # built `mpirun -np 2`, decomposePar would create six processor
    # directories and the solve would fail against them. A caller who wants a
    # different rank count must change the dictionary, which is the single
    # place both commands agree on.
    #
    # Reading it is a legitimate way to DISCOVER an ambient fact -- the case
    # really does say how it is decomposed. Making it the *only* way is what
    # coupled planning to the case already existing: four manufactured-solution
    # tutorials default to run_in_parallel=True and so could not build a spec
    # at all without a decomposeParDict on disk, which is why they cannot be
    # planned from an installed wheel. See docs/superpowers/specs/
    # 2026-09-04-a-case-is-a-path-design.md on supplied-versus-discovered.
    dict_path = None if case_root is None else case_root / decompose_par_dict_relpath
    if dict_path is not None and dict_path.is_file():
        n = read_number_of_subdomains(case_root, decompose_par_dict_relpath)
    elif num_subdomains is not None:
        n = int(num_subdomains)
    else:
        raise ValueError(
            "a parallel solve step needs either a case with "
            f"{decompose_par_dict_relpath} on disk, or an explicit "
            "num_subdomains"
        )
    steps = [
        {
            "id": "decomposePar",
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
            "depends_on": depends_on,
        },
        {
            "id": solve_id,
            "command": "mpirun",
            "args": ["-np", str(n), solve_command, "-parallel"],
            "depends_on": ["decomposePar"],
        },
        {"id": "reconstructPar", "command": "reconstructPar", "depends_on": [solve_id]},
    ]
    return steps, "reconstructPar"
