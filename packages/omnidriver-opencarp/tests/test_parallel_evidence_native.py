"""A parallel ``niedererNVersion`` ran as one MPI world of the requested size: C13 compares values,
and this is the evidence those values did not come from N one-process runs into one directory
(docs/solver-learning/opencarp.md). ``-log_view`` makes PETSc state its world size in the solve log."""
from __future__ import annotations

import pytest

from opencarp_native import niederer_run, require_opencarp_mpi_launcher

pytestmark = pytest.mark.native_opencarp

RANKS = 2


def test_the_parallel_run_was_one_mpi_world_of_the_requested_size(tmp_path, monkeypatch):
    require_opencarp_mpi_launcher()
    monkeypatch.setenv("PETSC_OPTIONS", "-log_view")
    run = niederer_run(tmp_path, dx=1000.0, tend=10.0, extra={"parallel": RANKS})
    log = (run.case_root / "workflow_logs" / "solve.attempt1.stdout.log").read_text()
    assert f"with {RANKS} processors" in log
    assert log.count("GIT tag") == 1
