"""Tests the shared decomposePar/mpirun/reconstructPar workflow_dag step
builder, via a tutorial record's solve step through
`parallel_steps_for_record`."""

from __future__ import annotations

import unittest

from omnidriver.core.runtime.record_execution import SchedulerAllocation
from omnidriver.openfoam.parallel_execution import (
    parallel_steps_for_record,
)

class TestRecordParallelForm(unittest.TestCase):
    """The OpenFOAM layer's answer to core's ``get_parallel_steps``, for a
    record's solve step. N is read only from the case's
    ``system/decomposeParDict:numberOfSubdomains``; nothing restates it."""

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

    def test_a_supplied_count_that_agrees_with_the_dictionary_is_accepted(self) -> None:
        self.assertEqual(self._form("6", request=6)[1]["args"][:2], ["-np", "6"])

    def test_a_supplied_count_that_disagrees_with_the_dictionary_is_refused_by_name(self) -> None:
        with self.assertRaises(ValueError) as caught:
            self._form("6", request=4)
        self.assertIn("system/decomposeParDict:numberOfSubdomains", str(caught.exception))

    def test_a_request_that_is_not_true_or_a_count_is_refused(self) -> None:
        for bad in (0, -1, 2.0, "2", False):
            with self.assertRaises(ValueError):
                self._form("6", request=bad)

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
