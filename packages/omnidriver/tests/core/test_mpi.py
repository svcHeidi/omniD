"""The solver-neutral MPI helper."""
from __future__ import annotations

import pytest

from omnidriver.core.runtime import mpi
from omnidriver.core.runtime.record_execution import SchedulerAllocation

SLURM_4 = SchedulerAllocation(variable="SLURM_NTASKS", ranks=4)


def test_program_is_the_first_token_that_is_not_a_launcher_flag():
    assert mpi.program(()) is None
    assert mpi.program(("-np",)) is None
    assert mpi.program(("-np", "4")) is None
    assert mpi.program(("--oversubscribe", "prog")) == "prog"
    assert mpi.program(("-np", "4", "cardiacFoam")) == "cardiacFoam"


def test_ranks_reads_any_of_the_three_spellings():
    assert [mpi.ranks(("-np", "4", "x")), mpi.ranks(("-n", "2")), mpi.ranks(("--np", "3"))] == [4, 2, 3]
    assert (mpi.ranks(("x",)), mpi.ranks(("-np", "four")), mpi.ranks(("-np",))) == (None, None, None)


def test_wrap_keeps_the_step_and_runs_it_under_the_launcher():
    step = {"id": "solve", "command": "solver", "args": ["-a"], "produces": ["p"]}
    assert mpi.wrap(step, 2) == {"id": "solve", "command": "mpirun", "args": ["-np", "2", "solver", "-a"], "produces": ["p"]}
    assert mpi.wrap({"id": "s", "command": "x"}, 3, "mpiexec")["args"] == ["-np", "3", "x"]


def test_a_request_is_true_or_a_positive_count():
    assert (mpi.requested(True), mpi.requested(3)) == (None, 3)
    for bad in (0, -1, 2.0, "2", False, [2]):
        with pytest.raises(ValueError, match="true or a positive process count"):
            mpi.requested(bad)


def test_the_count_comes_from_the_request_or_the_allocation_never_both_disagreeing():
    assert mpi.agree(2, None) == 2
    assert mpi.agree(None, SLURM_4) == 4
    assert mpi.agree(4, SLURM_4) == 4
    with pytest.raises(ValueError, match="SLURM_NTASKS=4"):
        mpi.agree(2, SLURM_4)
    with pytest.raises(ValueError, match="--parallel N"):
        mpi.agree(None, None)


def test_identity_names_the_launcher_and_its_first_lines(tmp_path):
    launcher = tmp_path / "mpirun"
    launcher.write_text("#!/bin/sh\necho 'mpirun (Toy MPI) 1.0'\n")
    launcher.chmod(0o755)
    found = mpi.identity("mpirun", {"PATH": str(tmp_path)})
    assert found["version"] == ["mpirun (Toy MPI) 1.0"] and found["path"] == str(launcher)
    assert mpi.identity("mpirun", {"PATH": ""})["path"] is None
