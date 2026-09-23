#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_heart_solver_comparison_write_channel
#
# Description
#     Phase 3 Task 7: `heart_solver_comparison` is one of the two tutorials
#     Task 6 could not migrate ("resists -- not migrated"), because its
#     `_apply_case` has no `ParameterAssignment`-shaped mutation at all --
#     four whole template files (`electroProperties`, `fvSchemes`,
#     `fvSolution`, `controlDict`) copied in verbatim from a fixed
#     per-solver-variant template directory. Classified here as a
#     `RenderedFile` (`plan_verbatim_content`), not a source artifact -- see
#     that function's own docstring for the argument.
#
#     Two things are under test, mirroring
#     `test_single_cell_write_channel.py`'s own template:
#
#     1. A characterization of `_apply_case`'s exact output bytes (content
#        digests, not existence). These digests are trivially derivable
#        (the pre-Task-7 `_apply_case` was a byte-for-byte `shutil.copy`,
#        so the written bytes are exactly the fixture's own template text),
#        but are still pinned by digest per this repo's "characterize by
#        content digest, never file existence" rule. Verified by reverting:
#        `git stash` on `heart_solver_comparison.py` alone reproduces an
#        `AttributeError: module has no attribute '_plan_case'` for every
#        `test_plan_case_*` test below, while
#        `test_characterization_apply_case_current_bytes` still passes
#        unchanged (the direct-copy `_apply_case` this task replaced wrote
#        the identical bytes) -- restoring the change returns all to green.
#
#     2. `_plan_case` -- the `TutorialSpec.plan_case` `invoke_case_mutation`
#        now prefers -- reproduces those exact bytes through
#        `commit_case_write`, not through a second, independent writer.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from omnidriver.cardiacfoam.tutorials import heart_solver_comparison
from omnidriver.core import case_write
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig

_TEMPLATE_FILES = ("electroProperties", "fvSchemes", "fvSolution", "controlDict")

# Digest of `f"// {variant} {name}\n"` for each (variant, name) pair -- the
# exact fixture text `_write_case` below writes into each template
# directory. Captured 2026-09-23; the pre-Task-7 `_apply_case` was a
# byte-for-byte `shutil.copy`, so these are also this task's "before"
# characterization.
_EXPECTED_DIGESTS = {
    ("eikonal", "electroProperties"): "3d5b9814d6e1b9c8a5bf6032579a97990cab87948bef8eae080760100d34d886",
    ("eikonal", "fvSchemes"): "c25cfb73b9c805c45185cf76c8b6d89f2dde2ec0eb7701f896029398a9676eac",
    ("eikonal", "fvSolution"): "8c96a29ba6f7f3e24ccea521e1ac10e90725308cdbb8b82b6e59a369825b7f9c",
    ("eikonal", "controlDict"): "c234a401e2987d2d1c040193f61cc7e7e67e40eaa9a93b4f9732bc2dd9227aef",
    ("monodomain", "electroProperties"): "e8f44cb0eb15453e8f6bd1a3c350e066b342b4a3bae87362f1c8d796a80dbcd5",
    ("monodomain", "fvSchemes"): "2a6e86bb3138d17ff7e575f007962025643543dc25fb355649ea2144e0a28b14",
    ("monodomain", "fvSolution"): "83c90f0e9cf0bce1f322cbcfda66467d0f75832342cf3f7d4a5b5e23f8699e8e",
    ("monodomain", "controlDict"): "99139df3a8818f86a79a761a6ad86f0e49b84e434e5b08892c84fd719c4a6d28",
    ("monodomain-eikonal", "electroProperties"): "24730ea6c998606674fcb9d2b7a83d65131457da5977aeafd068d4593bdca587",
    ("monodomain-eikonal", "fvSchemes"): "ca7c5075fb0b4c25395202b3534c9bf4ae13f7260d593a6a20952562f6693a5b",
    ("monodomain-eikonal", "fvSolution"): "71a3cc4c6e2fbe5d353f9e72b173a5ce96e21b8386814bbf9d7a8d09e0393eb0",
    ("monodomain-eikonal", "controlDict"): "5702cce5d7a4ab270aeed597d31151ad608cecdfc23c4c712b13c69ff52d5e64",
    ("bidomain", "electroProperties"): "93ea9c4ea584717e5a28b22e8bd6dcedcbacd51b5948dcded935a62c240a6cfe",
    ("bidomain", "fvSchemes"): "b6a359fe0d5da753cf7f5023e2eb4c06ad0b66bde4ac3fe1b25ce80e4de1ae84",
    ("bidomain", "fvSolution"): "76570343fa0b56d9a28bf5b10e372b411eda71293582a02e782e5a1315804f24",
    ("bidomain", "controlDict"): "a564a669fe1345d10c0f779cd0eb5e898a12319e5a7f49da90eccec827a40b63",
}

_DESTINATION_RELPATH = {
    "electroProperties": Path("constant") / "electroProperties",
    "fvSchemes": Path("system") / "fvSchemes",
    "fvSolution": Path("system") / "fvSolution",
    "controlDict": Path("system") / "controlDict",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_case(case_root: Path, variant: str) -> None:
    (case_root / "constant").mkdir(parents=True, exist_ok=True)
    (case_root / "system").mkdir(parents=True, exist_ok=True)
    template_dir = case_root / "setup" / "solverVariants" / variant
    template_dir.mkdir(parents=True, exist_ok=True)
    for name in _TEMPLATE_FILES:
        (template_dir / name).write_text(f"// {variant} {name}\n")
        # Every real case already has these destinations populated (this
        # tutorial reuses one case_root across all four variants in place);
        # give the fixture a plausible prior variant's content so `content`
        # targets that already-exist and ones that don't are both exercised
        # across the four parametrized variants below.
        destination = case_root / _DESTINATION_RELPATH[name]
        if not destination.exists():
            destination.write_text("// placeholder\n")


def _case(variant: str) -> CaseConfig:
    return CaseConfig(case_id=variant, params={"solver_variant": variant})


class TestHeartSolverComparisonWriteChannel(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-heart-solver-comparison-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_apply_case_current_bytes(self) -> None:
        for variant in heart_solver_comparison.HEART_SOLVER_VARIANTS:
            with self.subTest(variant=variant):
                root = self.tmp / f"apply_{variant}"
                _write_case(root, variant)
                heart_solver_comparison._apply_case(root, _case(variant))
                for name in _TEMPLATE_FILES:
                    self.assertEqual(
                        _digest(root / _DESTINATION_RELPATH[name]),
                        _EXPECTED_DIGESTS[(variant, name)],
                    )

    def test_plan_case_reproduces_apply_case_bytes_exactly(self) -> None:
        for variant in heart_solver_comparison.HEART_SOLVER_VARIANTS:
            with self.subTest(variant=variant):
                apply_root = self.tmp / f"apply2_{variant}"
                plan_root = self.tmp / f"plan_{variant}"
                _write_case(apply_root, variant)
                _write_case(plan_root, variant)

                heart_solver_comparison._apply_case(apply_root, _case(variant))
                record = heart_solver_comparison._plan_case(plan_root, _case(variant))

                self.assertIsInstance(record, CaseWriteRecord)
                for name in _TEMPLATE_FILES:
                    relpath = _DESTINATION_RELPATH[name]
                    self.assertEqual(
                        (plan_root / relpath).read_bytes(),
                        (apply_root / relpath).read_bytes(),
                    )
                    self.assertEqual(
                        _digest(plan_root / relpath), _EXPECTED_DIGESTS[(variant, name)],
                    )

    def test_plan_case_declares_the_solver_variant_as_a_source_artifact(self) -> None:
        """The channel-routed request has zero `ParameterAssignment`s (no
        key/value edit at all), so it must declare what it did through
        `source_artifacts` instead -- `CaseMutationRequest`'s 2026-09-23
        (Task 7) widened invariant. `CaseWriteRecord` carries no reference
        back to the request it committed, so the constructed request is
        captured with a wrapped mock rather than inferred from the record."""
        root = self.tmp / "declares"
        _write_case(root, "bidomain")
        with mock.patch(
            "omnidriver.cardiacfoam.overrides.CaseMutationRequest",
            wraps=case_write.CaseMutationRequest,
        ) as mocked_request:
            record = heart_solver_comparison._plan_case(root, _case("bidomain"))
        self.assertIsInstance(record, CaseWriteRecord)
        _, kwargs = mocked_request.call_args
        self.assertEqual(kwargs["parameters"], ())
        self.assertIn(
            "heart_solver_comparison.solverVariants:bidomain",
            kwargs["source_artifacts"],
        )


if __name__ == "__main__":
    unittest.main()
