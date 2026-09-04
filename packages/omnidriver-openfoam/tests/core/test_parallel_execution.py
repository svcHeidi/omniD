"""Tests the shared decomposePar/mpirun/reconstructPar workflow_dag step
builder used by every manufactured-solution tutorial's _workflow_dag_for.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from omnidriver.openfoam.parallel_execution import (
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

    def test_an_explicit_rank_count_needs_no_case_on_disk(self) -> None:
        """The rank count is a property of the run, not only of the case.

        Reading it from the case's decomposeParDict is a legitimate way to
        DISCOVER an ambient fact, but making it the only way couples planning
        to the case already existing: four manufactured-solution tutorials
        could not build a spec at all without a decomposeParDict on disk. An
        explicit count is supplied, so no case is needed.
        """
        steps, last_id = solve_steps(
            solve_id="solve",
            solve_command="cardiacFoam",
            depends_on=[],
            run_in_parallel=True,
            case_root=None,
            num_subdomains=8,
        )
        assert [s["id"] for s in steps] == ["decomposePar", "solve", "reconstructPar"]
        assert steps[1]["args"] == ["-np", "8", "cardiacFoam", "-parallel"]
        assert last_id == "reconstructPar"

    def test_the_case_dictionary_wins_over_an_explicit_count(self) -> None:
        """Deliberately this way round, and the contrast is the point.

        `decomposePar` reads the same decomposeParDict. If an explicit count
        overrode it, decomposePar would create six processor directories while
        the solve ran `mpirun -np 2` against them. The dictionary is the one
        place both commands agree, so it wins whenever it exists; the explicit
        count is only for when there is no case yet."""
        with TemporaryDirectory() as tmp:
            case_root = Path(tmp)
            (case_root / "system").mkdir()
            (case_root / "system" / "decomposeParDict").write_text(
                "FoamFile { version 2.0; format ascii; class dictionary; "
                "object decomposeParDict; }\nnumberOfSubdomains 6;\n"
            )
            steps, _ = solve_steps(
                solve_id="solve", solve_command="cardiacFoam", depends_on=[],
                run_in_parallel=True, case_root=case_root, num_subdomains=2,
            )
        assert steps[1]["args"] == ["-np", "6", "cardiacFoam", "-parallel"]


if __name__ == "__main__":
    unittest.main()
