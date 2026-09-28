"""openCARP's parallel form and its launcher check, without the binary. What
the real binary does is settled in docs/solver-learning/opencarp.md, section
I, and by test_parallel_native.py; these pin the rules that follow from it."""
from __future__ import annotations

import stat

import pytest

from omnidriver.core.runtime.record_execution import SchedulerAllocation
from omnidriver.opencarp.environment import opencarp_environment_diagnostics
from omnidriver.opencarp.parallel import launcher_diagnostics, parallel_steps
from omnidriver.opencarp.plugin import OpenCARPPlugin

SOLVE = {"id": "solve", "command": "openCARP", "args": ["+F", "nversion.par", "-simID", "out"],
         "depends_on": ["mesh"], "produces": ["record.solve.0"], "consumes": ["nversion.par"]}
SLURM_4 = SchedulerAllocation(variable="SLURM_NTASKS", ranks=4)


def _form(request, allocation=None):
    return parallel_steps(dict(SOLVE), request=request, read_value=None, allocation=allocation)


def test_the_solve_runs_under_mpirun_with_a_supplied_count():
    (step,) = _form(2)
    assert (step["command"], step["args"]) == ("mpirun", ["-np", "2", "openCARP", "+F", "nversion.par", "-simID", "out"])
    assert {k: step[k] for k in ("id", "depends_on", "produces", "consumes")} == {
        k: SOLVE[k] for k in ("id", "depends_on", "produces", "consumes")}


def test_true_takes_the_count_from_the_allocation():
    (step,) = _form(True, SLURM_4)
    assert step["args"][:2] == ["-np", "4"]


def test_a_count_that_agrees_with_the_allocation_is_accepted():
    (step,) = _form(4, SLURM_4)
    assert step["args"][:2] == ["-np", "4"]


def test_a_count_that_disagrees_with_the_allocation_is_refused():
    with pytest.raises(ValueError, match="SLURM_NTASKS=4"):
        _form(2, SLURM_4)


def test_no_count_and_no_allocation_is_refused_naming_how_to_supply_one():
    with pytest.raises(ValueError, match="--parallel N"):
        _form(True)


@pytest.mark.parametrize("bad", [0, -1, 2.0, "2", [2]])
def test_a_request_that_is_not_true_or_a_positive_count_is_refused(bad):
    with pytest.raises(ValueError, match="true or a positive process count"):
        _form(bad)


def test_the_plugin_declares_openCARP_its_solve_step_and_the_form():
    plugin = OpenCARPPlugin()
    assert plugin.get_solve_step_commands() == frozenset({"openCARP"})
    assert plugin.get_parallel_steps(dict(SOLVE), request=3, read_value=None, allocation=None)[0]["args"][:2] == ["-np", "3"]


def _script(directory, name, body):
    path = directory / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


PARALLEL_DAG = {"steps": [{"id": "solve", "command": "mpirun", "args": ["-np", "2", "openCARP", "+F", "x.par"]}]}


@pytest.mark.parametrize("headers, verdict", [(1, None), (2, "2 separate one-process"), (0, "could not start")])
def test_the_launcher_must_start_one_mpi_world(tmp_path, headers, verdict):
    """A launcher of the MPI openCARP links prints the header once; another
    MPI's prints it once per process; a launcher that cannot start openCARP
    at all prints none."""
    _script(tmp_path, "openCARP", "exit 0\n")
    _script(tmp_path, "mpirun", "".join("echo '*** GIT tag: v18.1'\n" for _ in range(headers)) + "echo 'fatal: host not found' >&2\n")
    diagnostics = launcher_diagnostics(PARALLEL_DAG, {"PATH": str(tmp_path)})
    if verdict is None:
        assert diagnostics == ()
    else:
        (diagnostic,) = diagnostics
        assert diagnostic.code == "opencarp_mpi_launcher_mismatch" and verdict in diagnostic.message


def test_the_probe_never_echoes_a_line_carrying_a_url(tmp_path):
    _script(tmp_path, "openCARP", "exit 0\n")
    _script(tmp_path, "mpirun", "echo 'repo https://user:secret@example.org/x'\necho 'boom'\n")
    (diagnostic,) = launcher_diagnostics(PARALLEL_DAG, {"PATH": str(tmp_path)})
    assert "secret" not in diagnostic.message and "boom" in diagnostic.message


def test_a_serial_dag_probes_no_launcher(tmp_path):
    assert launcher_diagnostics({"steps": [{"id": "solve", "command": "openCARP", "args": ["+F", "x.par"]}]},
                                {"PATH": str(tmp_path)}) == ()


def test_preflight_checks_the_launched_solver_as_a_command(tmp_path):
    """A parallel DAG's solve command is mpirun; openCARP missing from PATH
    is still reported by name (C9)."""
    _script(tmp_path, "mpirun", "exit 0\n")
    messages = [d.message for d in opencarp_environment_diagnostics(PARALLEL_DAG, {"PATH": str(tmp_path)})]
    assert any("'openCARP' is not on PATH" in m for m in messages), messages
