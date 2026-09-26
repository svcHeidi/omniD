"""Tests the shared decomposePar/mpirun/reconstructPar workflow_dag step
builder used by every manufactured-solution tutorial's _workflow_dag_for.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from omnidriver.core.runtime.record_execution import SchedulerAllocation
from omnidriver.openfoam.parallel_execution import (
    parallel_steps_for_record,
    read_number_of_subdomains,
    solve_steps,
)

_DECOMPOSE_PAR_DICT = """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      decomposeParDict;
}
numberOfSubdomains  6;
method          scotch;
"""


class TestReadNumberOfSubdomains(unittest.TestCase):
    def test_reads_committed_value(self) -> None:
        with TemporaryDirectory() as tmp:
            case_root = Path(tmp)
            (case_root / "system").mkdir()
            (case_root / "system" / "decomposeParDict").write_text(_DECOMPOSE_PAR_DICT)
            self.assertEqual(read_number_of_subdomains(case_root), 6)


class TestSolveSteps(unittest.TestCase):
    def test_serial_is_a_single_solve_step(self) -> None:
        steps, last_id = solve_steps(
            solve_id="solve", solve_command="cardiacFoam",
            depends_on=["setConductivity"], run_in_parallel=False, case_root=None,
        )
        self.assertEqual(steps, [
            {"id": "solve", "command": "cardiacFoam", "depends_on": ["setConductivity"]},
        ])
        self.assertEqual(last_id, "solve")

    def test_parallel_wraps_decompose_mpirun_reconstruct(self) -> None:
        with TemporaryDirectory() as tmp:
            case_root = Path(tmp)
            (case_root / "system").mkdir()
            (case_root / "system" / "decomposeParDict").write_text(_DECOMPOSE_PAR_DICT)

            steps, last_id = solve_steps(
                solve_id="solve", solve_command="cardiacFoam",
                depends_on=["setConductivity"], run_in_parallel=True, case_root=case_root,
            )
            self.assertEqual([s["id"] for s in steps], ["decomposePar", "solve", "reconstructPar"])
            self.assertEqual(steps[0]["command"], "decomposePar")
            self.assertEqual(steps[0]["depends_on"], ["setConductivity"])
            self.assertEqual(steps[1]["command"], "mpirun")
            self.assertEqual(steps[1]["args"], ["-np", "6", "cardiacFoam", "-parallel"])
            self.assertEqual(steps[1]["depends_on"], ["decomposePar"])
            self.assertEqual(steps[2]["command"], "reconstructPar")
            self.assertEqual(steps[2]["depends_on"], ["solve"])
            self.assertEqual(last_id, "reconstructPar")

    def test_parallel_requires_case_root(self) -> None:
        with self.assertRaises(ValueError):
            solve_steps(
                solve_id="solve", solve_command="cardiacFoam",
                depends_on=[], run_in_parallel=True, case_root=None,
            )


class TestRecordParallelForm(unittest.TestCase):
    """PAR (owner Q6, 2026-09-26): the OpenFOAM layer's answer to core's
    ``get_parallel_steps``, for a record's solve step. N is read only from
    the case's ``system/decomposeParDict:numberOfSubdomains``, as the run
    will see it; nothing restates it."""

    SOLVE = {
        "id": "solve", "command": "cardiacFoam", "args": ["-noFunctionObjects"],
        "depends_on": ["mesh"], "produces": ["record.solve.0"], "consumes": ["system/controlDict"],
    }

    @staticmethod
    def _reader(value):
        def read_value(document, key_path):
            assert (document, tuple(key_path)) == ("system/decomposeParDict", ("numberOfSubdomains",))
            return value
        return read_value

    def _form(self, value="6", *, request=True, allocation=None):
        return parallel_steps_for_record(
            dict(self.SOLVE), request=request, read_value=self._reader(value), allocation=allocation,
        )

    def test_decompose_run_on_n_ranks_reconstruct(self) -> None:
        steps = self._form("6")
        self.assertEqual([s["id"] for s in steps], ["solve.decompose", "solve", "solve.reconstruct"])
        decompose, solve, reconstruct = steps
        self.assertEqual((decompose["command"], decompose["args"]), ("decomposePar", ["-force"]))
        self.assertEqual(decompose["depends_on"], ["mesh"])
        self.assertEqual(decompose["consumes"], ["system/decomposeParDict"])
        self.assertEqual(solve["command"], "mpirun")
        self.assertEqual(solve["args"], ["-np", "6", "cardiacFoam", "-noFunctionObjects", "-parallel"])
        self.assertEqual(solve["depends_on"], ["solve.decompose"])
        self.assertEqual(solve["produces"], ["record.solve.0"])
        self.assertEqual(solve["consumes"], ["system/controlDict"])
        self.assertEqual((reconstruct["command"], reconstruct["depends_on"]), ("reconstructPar", ["solve"]))

    def test_a_study_that_changes_the_dictionary_changes_n(self) -> None:
        self.assertEqual(self._form(2)[1]["args"][:2], ["-np", "2"])

    def test_a_supplied_count_is_refused_the_dictionary_states_it(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._form("6", request=6)
        self.assertIn("system/decomposeParDict:numberOfSubdomains", str(caught.exception))

    def test_a_case_without_the_dictionary_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._form(None)
        self.assertIn("system/decomposeParDict:numberOfSubdomains", str(caught.exception))

    def test_a_malformed_count_is_refused_by_name(self) -> None:
        for bad in ("six", "0", "-1", "2.5"):
            with self.assertRaises(ValueError):
                self._form(bad)

    def test_an_allocation_that_agrees_is_accepted(self) -> None:
        steps = self._form("4", allocation=SchedulerAllocation(variable="SLURM_NTASKS", ranks=4))
        self.assertEqual(steps[1]["args"][:2], ["-np", "4"])

    def test_an_allocation_that_disagrees_is_refused_and_overrides_neither(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._form("6", allocation=SchedulerAllocation(variable="SLURM_NTASKS", ranks=4))
        message = str(caught.exception)
        self.assertIn("SLURM_NTASKS=4", message)
        self.assertIn("numberOfSubdomains", message)
        self.assertIn("6", message)

    def test_the_openfoam_provider_declares_the_hook(self) -> None:
        from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

        self.assertTrue(callable(getattr(OpenFOAMEnvironmentPlugin(), "get_parallel_steps", None)))


if __name__ == "__main__":
    unittest.main()
