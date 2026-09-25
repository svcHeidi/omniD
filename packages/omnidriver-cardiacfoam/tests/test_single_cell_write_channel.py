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
#     test_single_cell_write_channel
#
# Description
#     Phase 3 Task 6, Step 1: single_cell as the migration template.
#
#     Two things are under test:
#
#     1. A characterization of `_apply_case`'s exact output bytes (content
#        digests, not existence). Captured 2026-09-23 against HEAD bcd0ad8
#        from the unmodified writer -- see the capture invocation in this
#        task's report. Must pass before Task 6's change and unchanged
#        after, since `_apply_case` itself keeps writing directly (required
#        by `TutorialSpec.apply_case`, which has no default).
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

from omnidriver.cardiacfoam.tutorials import single_cell
from omnidriver.core.case_write import CaseWriteRecord
from omnidriver.core.runtime.models import CaseConfig

_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver singleCellSolver;",
        "",
        "singleCellSolverCoeffs",
        "{",
        "    ionicModel BuenoOrovio;",
        "    tissue myocyte;",
        "    singleCellStimulus",
        "    {",
        "        stim_amplitude 0.4;",
        "        stim_period_S1 1000;",
        "    }",
        "}",
        "",
    ]
)

_PHYSICS_TEXT = "type electroModel;\n"

_STIMULUS_MAP = {"TNNP": 0.55}

# Captured 2026-09-23 against HEAD bcd0ad8, from the unmodified `_apply_case`.
_ELECTRO_DIGEST_BEFORE = "50b4fceb298a23c9aab487e667842bee1b788ca996c665d1d95cdb1082515bd2"
_PHYSICS_DIGEST_BEFORE = "d09035a6fd22b88cca40153cc5a9f041943fc0e62232b2186895bac7d6713a0b"


def _write_case(root: Path) -> None:
    (root / "constant").mkdir(parents=True)
    (root / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    (root / "constant" / "physicsProperties").write_text(_PHYSICS_TEXT)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case() -> CaseConfig:
    return CaseConfig(case_id="TNNP_myocyte", params={"ionicModel": "TNNP", "tissue": "myocyte"})


def _kwargs() -> dict:
    return dict(
        stimulus_map=_STIMULUS_MAP,
        electro_property_overrides={
            "singleCellSolverCoeffs.singleCellStimulus.stim_period_S1": 900,
        },
        physics_property_overrides={"type": "electroMechanicalModel"},
    )


class TestSingleCellWriteChannelTemplate(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="omnidriver-single-cell-channel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_characterization_apply_case_current_bytes(self) -> None:
        root = self.tmp / "apply"
        _write_case(root)
        single_cell._apply_case(root, _case(), **_kwargs())
        self.assertEqual(
            _digest(root / "constant" / "electroProperties"), _ELECTRO_DIGEST_BEFORE,
        )
        self.assertEqual(
            _digest(root / "constant" / "physicsProperties"), _PHYSICS_DIGEST_BEFORE,
        )

    def test_plan_case_reproduces_apply_case_bytes_exactly(self) -> None:
        apply_root = self.tmp / "apply2"
        plan_root = self.tmp / "plan"
        _write_case(apply_root)
        _write_case(plan_root)

        single_cell._apply_case(apply_root, _case(), **_kwargs())
        record = single_cell._plan_case(plan_root, _case(), **_kwargs())

        self.assertIsInstance(record, CaseWriteRecord)
        self.assertEqual(
            _digest(plan_root / "constant" / "electroProperties"),
            _digest(apply_root / "constant" / "electroProperties"),
        )
        self.assertEqual(
            _digest(plan_root / "constant" / "physicsProperties"),
            _digest(apply_root / "constant" / "physicsProperties"),
        )
        # Exact spelling, not just equal digest -- a digest collision would
        # be astronomically unlikely, but the point is bytes, not hashes.
        self.assertEqual(
            (plan_root / "constant" / "electroProperties").read_bytes(),
            (apply_root / "constant" / "electroProperties").read_bytes(),
        )

    def test_plan_case_is_a_no_op_with_no_overrides_at_all(self) -> None:
        """Mirrors cardiaccore's `apply_input_overrides_planned` no-op
        contract: `single_cell`'s mandatory case_overrides (tissue/
        ionicModel/stim_amplitude) mean this can never actually happen for
        this tutorial, but `_plan_case` must not crash if some future caller
        supplies neither optional override -- captured here as the negative
        space of the byte-parity test above."""
        root = self.tmp / "no_overrides"
        _write_case(root)
        record = single_cell._plan_case(
            root, _case(), stimulus_map=_STIMULUS_MAP,
        )
        self.assertIsInstance(record, CaseWriteRecord)

    def test_stim_amplitude_is_a_template_value_when_stimulus_map_is_the_tutorials_own_default(
        self,
    ) -> None:
        """Phase 3 Task 9's `describe` review, 2026-09-24 (audit finding F4
        again): `stim_amplitude` is looked up from `stimulus_map`, not
        supplied by `_plan_case`'s immediate caller, unless that caller
        replaces the whole table. Using this tutorial's own default table
        (the same object `make_spec`'s own default argument is) must report
        `source="template"`, not `"case"` -- the caller asked for an ionic
        model, not for this specific amplitude."""
        root = self.tmp / "template_amplitude"
        _write_case(root)
        record = single_cell._plan_case(
            root, _case(), stimulus_map=single_cell.STIMULUS_MAP,
        )
        by_id = {p["qualified_id"]: p for p in record.parameters}
        self.assertEqual(
            by_id["singleCellSolverCoeffs.singleCellStimulus.stim_amplitude"]["source"],
            "template",
        )

    def test_stim_amplitude_is_a_case_value_when_the_caller_replaces_the_whole_stimulus_map(
        self,
    ) -> None:
        """A caller that explicitly hands `make_spec`/`_plan_case` its own
        `stimulus_map` (even one with the same values, since a copy is a
        different object) has made a deliberate choice -- `source="case"`."""
        root = self.tmp / "case_amplitude"
        _write_case(root)
        custom_map = dict(single_cell.STIMULUS_MAP)
        record = single_cell._plan_case(root, _case(), stimulus_map=custom_map)
        by_id = {p["qualified_id"]: p for p in record.parameters}
        self.assertEqual(
            by_id["singleCellSolverCoeffs.singleCellStimulus.stim_amplitude"]["source"],
            "case",
        )

    def test_an_explicit_stim_amplitude_override_still_wins_and_is_a_case_value(self) -> None:
        """`electro_property_overrides` naming `stim_amplitude` explicitly
        must still win over the computed default (unchanged "second write
        wins" behaviour) and must itself be `source="case"` -- a genuine
        caller-supplied value, not a lookup."""
        root = self.tmp / "override_amplitude"
        _write_case(root)
        record = single_cell._plan_case(
            root, _case(), stimulus_map=single_cell.STIMULUS_MAP,
            electro_property_overrides={
                "singleCellSolverCoeffs.singleCellStimulus.stim_amplitude": 0.9,
            },
        )
        by_id = {p["qualified_id"]: p for p in record.parameters}
        changed = by_id["singleCellSolverCoeffs.singleCellStimulus.stim_amplitude"]
        self.assertEqual(changed["source"], "case")
        self.assertEqual(changed["value"], 0.9)


if __name__ == "__main__":
    unittest.main()
