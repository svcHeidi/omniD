# Test-Core Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the 14 pytest collection errors that occur when
`omnidriver` (core) is installed alone, by moving or splitting each offending
test file so that every test claiming to be a core test actually collects and
passes with only `omnidriver` installed, and every test that genuinely needs
`omnidriver-openfoam` or `omnidriver-cardiacfoam` lives in that package's own
`tests/` tree instead.

**Architecture:** No production code changes — `cli.py` was already fixed in
`f51387b` (test-core collection errors 20 → 14). This plan is pure test-tree
surgery: `git mv` for whole misplaced files, cut/paste splits for files that
mix a clean core test with a sibling-dependent one. Two categories only —
Explore-agent research (recorded below) found **zero** files in the current
14 that meet the "genuine cross-package integration, needs a 4th CI job" bar
GITHUB_MIGRATION.md originally anticipated; everything resolves into
MISPLACED (whole file) or MIXED (split by test function/class).

**Tech Stack:** Python 3.13 (verify on the `requires-python` floor, not the
repo's own `.venv` — see Global Constraints), pytest, unittest.TestCase style
mixed with plain `def test_*` in this codebase.

## Global Constraints

- **Verify with a core-only venv, never this repo's own `.venv`.** The repo's
  `.venv` has all three packages installed and will hide every regression
  this plan is trying to catch. Use:
  ```bash
  rm -rf /tmp/core_only_venv_check
  /opt/homebrew/bin/python3.13 -m venv /tmp/core_only_venv_check
  source /tmp/core_only_venv_check/bin/activate
  cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" pytest
  ```
  Python 3.13, not 3.14 — this repo was previously unimportable on 3.11–3.13
  while green on 3.14 (PEP 649 hid a `NameError`), so 3.13 is the floor worth
  checking against.
- `omnidriver` (core) MUST NOT import `omnidriver.openfoam` or
  `omnidriver.cardiacfoam`, directly or transitively, at module scope or
  inside any function a core-only test calls.
- Do **not** add a 4th "install all three packages" CI job as a shortcut for
  any of these 14 files — that was already rejected once in
  `GITHUB_MIGRATION.md` for `cli.py` and it applies here too: it would go
  green by deleting the only check that core stands alone.
- Every task ends with two runs: `pytest packages/omnidriver/tests -q` in the
  core-only venv above (error count must strictly decrease, never increase),
  and `pytest <destination package>/tests -q` in this repo's own `.venv`
  (already has all three packages — fine for verifying the destination side)
  to confirm the moved/split tests pass in their new home.
- Commit after each task. Do not batch multiple tasks into one commit.
- When a class/function moves to a new file, carry only the imports it
  actually uses — do not copy the entire original import block blind.

## Source-file categorization (from investigation, do not re-derive)

| # | Source file | Category | Fate |
|---|---|---|---|
|1|`tests/core/test_common_blockmesh_resize.py`|MISPLACED (openfoam)|whole-file `git mv`|
|2|`tests/core/test_parallel_execution.py`|MISPLACED (openfoam)|whole-file `git mv`|
|3|`tests/core/test_dict_value_quoting.py`|MIXED|2 tests → openfoam, 1 test → cardiacfoam|
|4|`tests/core/test_dict_entries.py`|MIXED (3-way)|~18 stay in core, `TestReadFoamEntry`+`TestUpdateControlDict` → openfoam, rest (~35 tests across 9 classes + 2 coverage tests) → cardiacfoam|
|5|`tests/core/test_override_round_trip.py`|MISPLACED (cardiacfoam)|whole-file `git mv`|
|6|`tests/core/test_run_document_config_schema.py`|MISPLACED (cardiacfoam)|whole-file `git mv` — `default_driver_context()` is hard-bound to the cardiac plugin (see `core/plugin_interface.py:642-652`), so even the tests with no direct cardiac import still need it|
|7|`tests/core/test_tutorial_keys_are_catalog_addressable.py`|MISPLACED (cardiacfoam)|whole-file `git mv` — only imports `omnidriver.openfoam.apply_overrides`, but its subject matter (electroProperties tutorial dicts, `$ELECTRO_MODEL_COEFFS`) is 100% cardiac vocabulary|
|8|`tests/core/test_remediation.py`|MIXED|6 tests stay in core, 1 test (`test_every_hint_driver_path_is_catalog_addressable`) → cardiacfoam|
|9|`tests/core/test_plugin_profile.py`|MIXED|3 tests stay in core, 9 tests → cardiacfoam|
|10|`tests/core/test_strict_planning.py`|MIXED|7 tests stay in core, 13 tests → cardiacfoam|
|11|`tests/drift_guards/test_rtst_enum_contract.py`|MISPLACED (cardiacfoam)|whole-file `git mv` — RTST = OpenFOAM's runtime-selection-table; every table in this file (`ionicModel`, `purkinjeGraphModelCoeffs`, `ecgSolver`...) is cardiac vocabulary|
|12|`tests/drift_guards/test_source_refs_exist.py`|MISPLACED (cardiacfoam)|whole-file `git mv`|
|13|`tests/regression_equivalence/test_cli_matrix.py`|MISPLACED (cardiacfoam)|whole subpackage `git mv`|
|14|`tests/regression_equivalence/test_round_trip.py`|MISPLACED (cardiacfoam)|whole subpackage `git mv` (same move as #13)|

Two support modules ride along with #13/#14 even though they weren't in the
14-error list themselves (they're only reachable through the two test files
above, which is why they didn't show as independent collection errors):
`tests/regression_equivalence/__main__.py`, `registry.py`, `round_trip.py`,
`dual_run.py`, `staging.py`, `conftest.py`, plus their own
`test_dual_run.py`, `test_registry.py`, `test_staging.py` — all equally
cardiac-coupled (`registry.py`'s `REGRESSION_CASES` is a hardcoded tuple of
literal cardiac tutorial paths, `round_trip.py` imports
`omnidriver.cardiacfoam.dict_builder` directly).

`plugins/minimal_plugin.py` is **not** a blocker for anything in this plan —
core already has its own copy at `packages/omnidriver/tests/plugins/minimal_plugin.py`
(a separate, near-identical copy also exists under
`packages/omnidriver-cardiacfoam/tests/plugins/` — that duplication is
pre-existing and out of scope here). `packages/omnidriver/tests/plugins/cardiacfoam/test_introspection.py`
is also out of scope — despite the misleading directory name it only imports
`omnidriver.cli` and `omnidriver.core.introspection`, no sibling package.

---

### Task 1: Move the two whole-file openfoam misplacements

**Files:**
- Move: `packages/omnidriver/tests/core/test_common_blockmesh_resize.py` → `packages/omnidriver-openfoam/tests/core/test_common_blockmesh_resize.py`
- Move: `packages/omnidriver/tests/core/test_parallel_execution.py` → `packages/omnidriver-openfoam/tests/core/test_parallel_execution.py`

**Interfaces:** None — both files are self-contained, no other test imports them.

- [x] **Step 1: Move both files with git mv (preserves history)**

```bash
cd ~/omnidriver
git mv packages/omnidriver/tests/core/test_common_blockmesh_resize.py \
       packages/omnidriver-openfoam/tests/core/test_common_blockmesh_resize.py
git mv packages/omnidriver/tests/core/test_parallel_execution.py \
       packages/omnidriver-openfoam/tests/core/test_parallel_execution.py
```

- [x] **Step 2: Verify core-only collection error count dropped by 2 (20 → 12 remaining of the original blocker, i.e. 14 → 12 from this plan's starting point)**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -20
```
Expected: `12 errors during collection` (was 14), and neither moved file
appears in the error list.

- [x] **Step 3: Verify the moved tests pass in their new home**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver-openfoam/tests/core/test_common_blockmesh_resize.py \
       packages/omnidriver-openfoam/tests/core/test_parallel_execution.py -q
```
Expected: all pass (4 tests + the `TestReadNumberOfSubdomains`/`TestSolveSteps` unittest methods).

- [x] **Step 4: Commit**

```bash
git add packages/omnidriver-openfoam/tests/core/test_common_blockmesh_resize.py \
        packages/omnidriver-openfoam/tests/core/test_parallel_execution.py
git commit -m "test: move openfoam-only tests out of core's tree

Both files import only omnidriver.openfoam, never core-generic or cardiac.
Part of clearing the 14 test-core collection errors from f51387b."
```

---

### Task 2: Split `test_dict_value_quoting.py`

**Files:**
- Create: `packages/omnidriver-openfoam/tests/core/test_dict_value_quoting.py` (the 2 openfoam-only tests)
- Create: `packages/omnidriver-cardiacfoam/tests/test_dict_value_quoting.py` (the 1 cardiac test)
- Delete: `packages/omnidriver/tests/core/test_dict_value_quoting.py`

**Interfaces:** None.

- [x] **Step 1: Create the openfoam destination**

```python
"""OpenFOAM cannot lex a bare token that starts with a digit but is not a
number: `dimension 3D;` raises a FatalIOError ("expected word, found label 3").
Tutorials write `dimension "3D";`. The emitter must do the same, and must NOT
quote anything else -- quoting a scalar, vector or dimension set would break
dictionaries that work today.
"""

from __future__ import annotations

import pytest

from omnidriver.openfoam.dict_builder import _openfoam_value_token


@pytest.mark.parametrize("value", ["3D", "1D", "2D", "3Dfoo"])
def test_a_word_starting_with_a_digit_is_quoted(value):
    assert _openfoam_value_token(value) == f'"{value}"'


@pytest.mark.parametrize(
    "value",
    [
        "0.5", "1e-5", "-3", "140000", "1.0E+06", ".5", "+2",   # numbers
        "epicardialCells", "TNNP", "godunov", "yes", "no",       # plain words
        "(1 0 0)", "(bath organ)",                               # lists/vectors
        "[ -1 -3 3 0 0 2 0 ] ( 0.11 0 0 )",                      # dimension set
        '"3D"',                                                  # already quoted
        "",                                                      # empty
    ],
)
def test_everything_else_is_left_untouched(value):
    assert _openfoam_value_token(value) == value
```

Save to `packages/omnidriver-openfoam/tests/core/test_dict_value_quoting.py`.

- [x] **Step 2: Create the cardiacfoam destination**

```python
"""End-to-end regression for the OpenFOAM value-quoting fix: this exact
value produced an unparseable dictionary through the cardiac dict builder,
making $ELECTRO_MODEL_COEFFS.dimension unusable through the driver. Found
by running listCellModelsVariables for real."""

from __future__ import annotations

from omnidriver.cardiacfoam.dict_builder import build_electro_properties


def test_dimension_reaches_the_dict_in_a_form_openfoam_can_parse():
    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "singleCellSolver",
            "ionicModel": "monodomainFDAManufactured",
            "tissue": "myocyte",
        },
        overrides={"$ELECTRO_MODEL_COEFFS.dimension": "3D"},
    )
    assert 'dimension "3D";' in text
    assert "dimension 3D;" not in text
```

Save to `packages/omnidriver-cardiacfoam/tests/test_dict_value_quoting.py`.

- [x] **Step 3: Delete the original and verify core-only collection**

```bash
cd ~/omnidriver
git rm packages/omnidriver/tests/core/test_dict_value_quoting.py
source /tmp/core_only_venv_check/bin/activate
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -20
```
Expected: `11 errors during collection`.

- [x] **Step 4: Verify both destinations pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver-openfoam/tests/core/test_dict_value_quoting.py \
       packages/omnidriver-cardiacfoam/tests/test_dict_value_quoting.py -q
```
Expected: 3 passed.

- [x] **Step 5: Commit**

```bash
git add packages/omnidriver-openfoam/tests/core/test_dict_value_quoting.py \
        packages/omnidriver-cardiacfoam/tests/test_dict_value_quoting.py \
        packages/omnidriver/tests/core/test_dict_value_quoting.py
git commit -m "test: split test_dict_value_quoting.py by package

Two tests exercise _openfoam_value_token directly (openfoam-only); the third
round-trips through the cardiac dict builder and belongs with cardiacfoam."
```

---

### Task 3: Merge `test_dict_entries.py`'s openfoam classes into `test_mutators.py`

**Files:**
- Modify: `packages/omnidriver-openfoam/tests/core/test_mutators.py` (append `TestReadFoamEntry`, `TestUpdateControlDict` before the `if __name__ == "__main__":` guard at the end; add `update_control_dict` to the existing `from omnidriver.openfoam.mutators import (...)` block at line 37)
- Modify: `packages/omnidriver/tests/core/test_dict_entries.py` (remove the two classes — lines 629-748 in the current file)

**Interfaces:** `test_mutators.py` already imports `tempfile`, `unittest`,
`Path`, and `read_foam_entry` at module scope — reuse those, do not re-import
inside each test method as the original core copy did.

- [x] **Step 1: Add `update_control_dict` to test_mutators.py's existing import**

Change line 37-42 of `packages/omnidriver-openfoam/tests/core/test_mutators.py` from:
```python
from omnidriver.openfoam.mutators import (
    ensure_foam_dict,
    read_foam_entry,
    remove_foam_dict,
    update_foam_entry,
)
```
to:
```python
from omnidriver.openfoam.mutators import (
    ensure_foam_dict,
    read_foam_entry,
    remove_foam_dict,
    update_control_dict,
    update_foam_entry,
)
```

- [x] **Step 2: Append the two classes before the `__main__` guard**

Insert immediately before the trailing
```python
if __name__ == "__main__":
    unittest.main()
```
of `test_mutators.py`:

```python
class TestReadFoamEntry(unittest.TestCase):
    """read_foam_entry returns the raw value string for a key, or None."""

    def test_reads_top_level_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text("myocardiumSolver monodomainSolver;\n")
            result = read_foam_entry(p, "myocardiumSolver")
            self.assertEqual(result, "monodomainSolver")

    def test_reads_scoped_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text(
                "myocardiumSolver monodomainSolver;\n"
                "monodomainSolverCoeffs\n"
                "{\n"
                "    ionicModel TNNP;\n"
                "    solutionAlgorithm implicit;\n"
                "}\n"
            )
            result = read_foam_entry(p, "ionicModel", scope="monodomainSolverCoeffs")
            self.assertEqual(result, "TNNP")

    def test_reads_nested_scope_key(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text(
                "singleCellSolverCoeffs\n"
                "{\n"
                "    singleCellStimulus\n"
                "    {\n"
                "        stim_amplitude 60;\n"
                "    }\n"
                "}\n"
            )
            result = read_foam_entry(
                p, "stim_amplitude",
                scope=["singleCellSolverCoeffs", "singleCellStimulus"],
            )
            self.assertEqual(result, "60")

    def test_missing_key_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text("myocardiumSolver monodomainSolver;\n")
            result = read_foam_entry(p, "notAKey")
            self.assertIsNone(result)

    def test_missing_scope_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text("myocardiumSolver monodomainSolver;\n")
            result = read_foam_entry(p, "ionicModel", scope="noSuchBlock")
            self.assertIsNone(result)

    def test_strips_inline_comment_from_value(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f"
            p.write_text("solutionAlgorithm implicit; // time discretisation\n")
            result = read_foam_entry(p, "solutionAlgorithm")
            self.assertEqual(result, "implicit")

    def test_nonexistent_file_returns_none(self) -> None:
        result = read_foam_entry(Path("/no/such/file"), "key")
        self.assertIsNone(result)


class TestUpdateControlDict(unittest.TestCase):
    """update_control_dict patches deltaT / endTime in an existing controlDict."""

    @staticmethod
    def _write_control_dict(d: str) -> Path:
        p = Path(d) / "controlDict"
        p.write_text("deltaT    0.05;\nendTime   1.0;\n")
        return p

    def test_updates_delta_t(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_control_dict(d)
            update_control_dict(p, delta_t=0.001)
            self.assertIn("0.001", p.read_text())

    def test_updates_end_time(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_control_dict(d)
            update_control_dict(p, end_time=0.5)
            self.assertIn("0.5", p.read_text())

    def test_updates_both_in_one_call(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_control_dict(d)
            update_control_dict(p, delta_t=0.002, end_time=0.1)
            text = p.read_text()
            self.assertIn("0.002", text)
            self.assertIn("0.1", text)

    def test_none_args_leave_file_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = self._write_control_dict(d)
            original = p.read_text()
            update_control_dict(p)
            self.assertEqual(p.read_text(), original)

    def test_missing_file_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            update_control_dict(Path("/no/such/controlDict"), delta_t=0.001)

```

- [x] **Step 3: Delete lines 629-748 (the two classes) from `packages/omnidriver/tests/core/test_dict_entries.py`**

Use the Edit tool to remove the `TestReadFoamEntry` and `TestUpdateControlDict`
class bodies (from `class TestReadFoamEntry(unittest.TestCase):` through the
blank line right before `class TestControlDictEntries(unittest.TestCase):`).
Do not touch `TestControlDictEntries` — it stays in the file for now (it
moves to cardiacfoam in Task 8).

- [x] **Step 4: Verify test_mutators.py passes standalone**

```bash
cd ~/omnidriver
pytest packages/omnidriver-openfoam/tests/core/test_mutators.py -q
```
Expected: all pass, including the 12 newly-appended tests.

- [x] **Step 5: Commit**

```bash
git add packages/omnidriver-openfoam/tests/core/test_mutators.py \
        packages/omnidriver/tests/core/test_dict_entries.py
git commit -m "test: fold TestReadFoamEntry/TestUpdateControlDict into openfoam's test_mutators.py

Both classes exercised omnidriver.openfoam.mutators exclusively and had no
business living in core's test tree."
```

---

### Task 4: Move the five remaining whole-file cardiacfoam misplacements

**Files:**
- Move: `packages/omnidriver/tests/core/test_override_round_trip.py` → `packages/omnidriver-cardiacfoam/tests/test_override_round_trip.py`
- Move: `packages/omnidriver/tests/core/test_run_document_config_schema.py` → `packages/omnidriver-cardiacfoam/tests/test_run_document_config_schema.py`
- Move: `packages/omnidriver/tests/core/test_tutorial_keys_are_catalog_addressable.py` → `packages/omnidriver-cardiacfoam/tests/test_tutorial_keys_are_catalog_addressable.py`
- Move: `packages/omnidriver/tests/drift_guards/test_rtst_enum_contract.py` → `packages/omnidriver-cardiacfoam/tests/test_rtst_enum_contract.py`
- Move: `packages/omnidriver/tests/drift_guards/test_source_refs_exist.py` → `packages/omnidriver-cardiacfoam/tests/test_source_refs_exist.py`

Note: `omnidriver-cardiacfoam/tests/` is flat (no `drift_guards/` subdir), so
the two drift-guard files land at the top level, matching the existing
layout shown in the Explore report.

**Interfaces:** `test_tutorial_keys_are_catalog_addressable.py` and
`test_rtst_enum_contract.py`/`test_source_refs_exist.py` use the
`skip_without_monorepo` fixture / `monorepo_root` from `conftest.py` — verify
`packages/omnidriver-cardiacfoam/tests/conftest.py` already defines these
(it does, per the layout listing — cardiacfoam's own conftest already backs
other monorepo-gated tests there).

- [x] **Step 1: Move all five files**

```bash
cd ~/omnidriver
git mv packages/omnidriver/tests/core/test_override_round_trip.py \
       packages/omnidriver-cardiacfoam/tests/test_override_round_trip.py
git mv packages/omnidriver/tests/core/test_run_document_config_schema.py \
       packages/omnidriver-cardiacfoam/tests/test_run_document_config_schema.py
git mv packages/omnidriver/tests/core/test_tutorial_keys_are_catalog_addressable.py \
       packages/omnidriver-cardiacfoam/tests/test_tutorial_keys_are_catalog_addressable.py
git mv packages/omnidriver/tests/drift_guards/test_rtst_enum_contract.py \
       packages/omnidriver-cardiacfoam/tests/test_rtst_enum_contract.py
git mv packages/omnidriver/tests/drift_guards/test_source_refs_exist.py \
       packages/omnidriver-cardiacfoam/tests/test_source_refs_exist.py
```

- [x] **Step 2: Fix each moved file's `from conftest import ...` line if it referenced `drift_guards/conftest.py`-specific names**

Read `packages/omnidriver/tests/drift_guards/conftest.py` and
`packages/omnidriver-cardiacfoam/tests/conftest.py` first; if the drift-guard
conftest defined `monorepo_root`/`skip_without_monorepo` identically to
cardiacfoam's own conftest (likely, both ultimately derive `monorepo_root` by
walking up from `__file__`), no import changes are needed beyond what `git
mv` already preserves. If cardiacfoam's conftest is missing a name either
file needs, add it there rather than duplicating logic.

- [x] **Step 3: Verify core-only collection dropped to 6 remaining**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -15
```
Expected: `6 errors during collection` (test_dict_entries.py's remaining
cardiac content, test_remediation.py, test_plugin_profile.py,
test_strict_planning.py, and the two regression_equivalence files — Tasks 5-8
and 10 below still pending at this point).

- [x] **Step 4: Verify all five pass in cardiacfoam's own suite**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver-cardiacfoam/tests/test_override_round_trip.py \
       packages/omnidriver-cardiacfoam/tests/test_run_document_config_schema.py \
       packages/omnidriver-cardiacfoam/tests/test_tutorial_keys_are_catalog_addressable.py \
       packages/omnidriver-cardiacfoam/tests/test_rtst_enum_contract.py \
       packages/omnidriver-cardiacfoam/tests/test_source_refs_exist.py -q
```
Expected: all pass or skip cleanly (the monorepo-gated ones skip unless run
against a full monorepo checkout — a skip is a pass here, a collection error
is not).

- [x] **Step 5: Commit**

```bash
git add packages/omnidriver-cardiacfoam/tests/test_override_round_trip.py \
        packages/omnidriver-cardiacfoam/tests/test_run_document_config_schema.py \
        packages/omnidriver-cardiacfoam/tests/test_tutorial_keys_are_catalog_addressable.py \
        packages/omnidriver-cardiacfoam/tests/test_rtst_enum_contract.py \
        packages/omnidriver-cardiacfoam/tests/test_source_refs_exist.py \
        packages/omnidriver/tests/core/test_override_round_trip.py \
        packages/omnidriver/tests/core/test_run_document_config_schema.py \
        packages/omnidriver/tests/core/test_tutorial_keys_are_catalog_addressable.py \
        packages/omnidriver/tests/drift_guards/test_rtst_enum_contract.py \
        packages/omnidriver/tests/drift_guards/test_source_refs_exist.py
git commit -m "test: move five cardiac-specific tests out of core's tree

All five are cardiac vocabulary (electroProperties dict builder, RTST enum
tables keyed on ionicModel/purkinjeGraphModelCoeffs, or default_driver_context
which is hard-bound to CardiacFoamPlugin) that only imported openfoam/core
symbols incidentally."
```

---

### Task 5: Split `test_remediation.py`

**Files:**
- Modify: `packages/omnidriver/tests/core/test_remediation.py` (delete lines 108-150, the trailing cardiac-catalog import + test)
- Create: `packages/omnidriver-cardiacfoam/tests/test_remediation_catalog_addressability.py`

**Interfaces:** The moved test needs `STATIC_REMEDIATION_HINTS` and
`RemediationHint` from `omnidriver.core.runtime.remediation` (core, fine to
import from cardiacfoam) plus `CONTROL_DICT_ENTRIES`, `PHYSICS_PROPERTY_ENTRIES`,
`get_electro_property_entry_groups` from `omnidriver.dict_entries` (which
resolve to real cardiac catalog data once cardiacfoam is installed).

- [x] **Step 1: Create the cardiacfoam destination**

```python
"""Every STATIC_REMEDIATION_HINTS driver_path must resolve against the live
catalog, so a hint never points an agent at a key the driver cannot set."""

from __future__ import annotations

from omnidriver.core.runtime.remediation import STATIC_REMEDIATION_HINTS, RemediationHint
from omnidriver.dict_entries import (
    CONTROL_DICT_ENTRIES,
    get_electro_property_entry_groups,
    PHYSICS_PROPERTY_ENTRIES,
)

_PREFIX = "$ELECTRO_MODEL_COEFFS."


def _addressable_leaves() -> set[str]:
    leaves: set[str] = set()
    for e in CONTROL_DICT_ENTRIES:
        leaves.add(e.driver_path)
    for e in PHYSICS_PROPERTY_ENTRIES:
        leaves.add(e.driver_path)
    for group in get_electro_property_entry_groups().values():
        for e in group:
            dp = e.driver_path
            leaves.add(dp[len(_PREFIX):] if dp.startswith(_PREFIX) else dp)
    return leaves


def _all_hints() -> list[RemediationHint]:
    hints: list[RemediationHint] = []
    for group in STATIC_REMEDIATION_HINTS.values():
        hints.extend(group)
    return hints


def test_every_hint_driver_path_is_catalog_addressable():
    leaves = _addressable_leaves()
    for h in _all_hints():
        if not h.driver_path:        # advisory hints are exempt
            continue
        assert h.driver_path in leaves, (
            f"hint for {h.diagnostic_code or h.source!r} targets non-catalog "
            f"driver_path {h.driver_path!r}"
        )
```

Save to `packages/omnidriver-cardiacfoam/tests/test_remediation_catalog_addressability.py`.

- [x] **Step 2: Trim `packages/omnidriver/tests/core/test_remediation.py`**

Delete everything from (and including) the line
`from omnidriver.core.runtime.remediation import (` that reappears near the
bottom of the file (the second occurrence — the one immediately followed by
`STATIC_REMEDIATION_HINTS`) through the end of the file. The file should end
after `test_append_never_raises_on_bad_dir`.

- [x] **Step 3: Verify core-only collection dropped to 5 remaining**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -12
```

- [x] **Step 4: Verify both sides pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver/tests/core/test_remediation.py -q
pytest packages/omnidriver-cardiacfoam/tests/test_remediation_catalog_addressability.py -q
```
Expected: 6 passed in core, 1 passed in cardiacfoam.

- [x] **Step 5: Commit**

```bash
git add packages/omnidriver/tests/core/test_remediation.py \
        packages/omnidriver-cardiacfoam/tests/test_remediation_catalog_addressability.py
git commit -m "test: split the one cardiac-catalog test out of test_remediation.py

The other 6 tests exercise build_candidate_remediations/append_remediation_record
generically; only the catalog-addressability check needs the cardiac catalog."
```

---

### Task 6: Split `test_plugin_profile.py`

**Files:**
- Modify: `packages/omnidriver/tests/core/test_plugin_profile.py` (keep only the 3 core-safe tests + trim imports)
- Create: `packages/omnidriver-cardiacfoam/tests/test_plugin_profile.py` (the 9 cardiac tests)

**Interfaces:** Read the full current file first
(`packages/omnidriver/tests/core/test_plugin_profile.py`, 286 lines) to copy
exact test bodies — do not paraphrase. The split is by test name:

- **Stays in core (3):** `test_generic_profile_declares_no_solver_specific_files`,
  `test_profile_rejects_case_path_escape`,
  `test_profile_digest_is_stable_after_payload_mutation`.
- **Moves to cardiacfoam (9):** `test_cardiac_profile_declares_case_files_and_cxx_provenance`,
  `test_cardiac_profile_cxx_source_roots_exist`,
  `test_cardiac_catalog_partitions_entries_by_document`,
  `test_cardiac_runtime_requires_explicit_solids4foam_root`,
  `test_cardiac_runtime_exports_one_validated_solids4foam_root`,
  `test_infer_backend_from_linked_libraries`,
  `test_build_manifest_self_generates_from_compiled_artifacts`,
  `test_build_manifest_self_heals_when_stale`,
  `test_cardiac_runtime_file_selects_backend_and_bashrc`.

- [x] **Step 1: Read the current file in full**

```bash
cd ~/omnidriver
cat -n packages/omnidriver/tests/core/test_plugin_profile.py
```

- [x] **Step 2: Create `packages/omnidriver-cardiacfoam/tests/test_plugin_profile.py`**

Copy the file header, then only the 9 cardiac test functions listed above
plus any module-level helper functions/fixtures they call that aren't shared
with the 3 core-safe tests. Keep the imports:
```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from omnidriver.cardiacfoam import runtime_profile
from omnidriver.cardiacfoam.runtime_profile import configure_runtime_environment
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from conftest import skip_without_monorepo
```
(cardiacfoam's own `conftest.py` must define `skip_without_monorepo` — verify
via `grep -n skip_without_monorepo packages/omnidriver-cardiacfoam/tests/conftest.py`
before assuming; if absent, port the fixture from core's conftest first.)

- [x] **Step 3: Trim `packages/omnidriver/tests/core/test_plugin_profile.py` to the 3 core-safe tests**

Remove the 9 moved test functions and their exclusive helpers. Remove the now
unused imports (`omnidriver.cardiacfoam.*`), keeping only:
```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_profile import PluginProfile, load_plugin_profile
```
(drop `conftest.skip_without_monorepo` here too unless one of the 3 remaining
tests actually uses it — check before removing.)

- [x] **Step 4: Verify core-only collection dropped to 4 remaining**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -10
```

- [x] **Step 5: Verify both sides pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver/tests/core/test_plugin_profile.py -q
pytest packages/omnidriver-cardiacfoam/tests/test_plugin_profile.py -q
```
Expected: 3 passed in core, 9 passed (or skipped, for any monorepo-gated
ones) in cardiacfoam.

- [x] **Step 6: Commit**

```bash
git add packages/omnidriver/tests/core/test_plugin_profile.py \
        packages/omnidriver-cardiacfoam/tests/test_plugin_profile.py
git commit -m "test: split test_plugin_profile.py by package

3 tests exercise GenericOpenFOAMPlugin/PluginProfile generically; the other 9
assert cardiac-specific behavior (solids4foam root validation, build-manifest
self-healing, library-based backend inference) via CardiacFoamPlugin."
```

---

### Task 7: Split `test_strict_planning.py`

**Files:**
- Modify: `packages/omnidriver/tests/core/test_strict_planning.py` (keep only the 7 core-safe tests)
- Create: `packages/omnidriver-cardiacfoam/tests/test_strict_planning.py` (the 13 cardiac tests)

**Interfaces:** Read the full current file first (592 lines). Split by name:

- **Stays in core (7):** `test_report_has_mesh_geometry_field`,
  `test_mesh_adapter_flags_non_si`, `test_mesh_gate_skipped_by_env`,
  `test_exempt_short_circuits_unit_domain`,
  `test_manufactured_entry_is_nondimensional`,
  `test_plain_entry_is_dimensional`,
  `test_dictionary_resolution_audit_text_is_plugin_neutral_for_non_cardiac_plugin`
  (this one imports `from plugins.minimal_plugin import MinimalOpenFOAMPlugin`
  at line 567 — resolves fine from core's own `tests/plugins/minimal_plugin.py`,
  already on `pythonpath`, no change needed).
- **Moves to cardiacfoam (13):** `test_strict_plan_succeeds_for_single_cell`,
  `test_strict_plan_succeeds_for_manufactured_tutorial`,
  `test_cli_plan_strict_prints_json_and_returns_zero`,
  `test_strict_plan_status_ignores_environment_only_errors`,
  `test_cli_run_strict_refuses_environment_errors_before_execution`,
  `test_strict_plan_fails_when_artifact_prediction_is_empty`,
  `test_strict_dict_key_scanner_allowlist_is_current`,
  `test_batched_ionic_model_does_not_require_optional_batched_keys`,
  `test_electromechanics_is_advertised_as_not_working_while_it_is_not`,
  `test_absent_stimulus_block_is_not_invented_from_defaults`,
  `test_strict_plan_fails_on_unknown_workflow_command`,
  `test_strict_plan_fails_on_unknown_workflow_dependency`,
  `test_strict_dict_key_scanner_fails_on_unallowlisted_key`.

  The last three (`_fails_on_unknown_workflow_command`,
  `_fails_on_unknown_workflow_dependency`, `_scanner_fails_on_unallowlisted_key`)
  only use `CardiacFoamPlugin` as a convenient concrete plugin fixture, not
  because the behavior under test is cardiac-specific — move them anyway (do
  not attempt to swap in `GenericOpenFOAMPlugin`/`MinimalOpenFOAMPlugin` as
  part of this plan; that's a separate, judgment-call refactor, not a
  mechanical test-tree move — flag it in the Task 12 doc update instead of
  doing it here).

- [x] **Step 1: Read the current file in full**

```bash
cd ~/omnidriver
cat -n packages/omnidriver/tests/core/test_strict_planning.py
```

- [x] **Step 2: Create `packages/omnidriver-cardiacfoam/tests/test_strict_planning.py`**

Copy the header, the 13 test functions listed above, and every helper/fixture
they exclusively use (check `conftest.monorepo_root`, `skip_without_monorepo`,
`CardiacFoamPlugin`, `main` from `omnidriver.cli`, `_dict_keys_scanner`
imports carry over). Cardiacfoam's own `conftest.py` must supply
`monorepo_root`/`skip_without_monorepo` — verify before assuming.

- [x] **Step 3: Trim `packages/omnidriver/tests/core/test_strict_planning.py` to the 7 core-safe tests**

Remove the 13 moved tests and the now-unused
`from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin`
import (line 48) and `from omnidriver.cli import main` / `_dict_keys_scanner`
imports if nothing remaining uses them — check each import against the 7
kept tests before removing it.

- [x] **Step 4: Verify core-only collection dropped to 3 remaining**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -10
```
Expected: `3 errors` — the remaining cardiac chunk of `test_dict_entries.py`
(Task 8) and the two `regression_equivalence` files (Task 10).

- [x] **Step 5: Verify both sides pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver/tests/core/test_strict_planning.py -q
pytest packages/omnidriver-cardiacfoam/tests/test_strict_planning.py -q
```

- [x] **Step 6: Commit**

```bash
git add packages/omnidriver/tests/core/test_strict_planning.py \
        packages/omnidriver-cardiacfoam/tests/test_strict_planning.py
git commit -m "test: split test_strict_planning.py by package

7 tests exercise generic strict-planning machinery (mesh geometry gate,
manufactured-entry dimensionality); 13 assert cardiac-specific plan behavior
via CardiacFoamPlugin. Three of the 13 use the cardiac plugin only as a
convenient fixture rather than testing cardiac semantics -- swapping them to
a generic test double is worth doing later but is a judgment call, not a
mechanical move; noted in GITHUB_MIGRATION.md."
```

---

### Task 8: Split the remaining cardiac content out of `test_dict_entries.py`

**Files:**
- Modify: `packages/omnidriver/tests/core/test_dict_entries.py` (trim to the ~18 core-safe tests)
- Create: `packages/omnidriver-cardiacfoam/tests/test_dict_entries_catalog.py` (everything else)

**Interfaces:** By this point Task 3 has already removed `TestReadFoamEntry`/
`TestUpdateControlDict`. What remains to split:

- **Stays in core:** `TestDictEntryStructuredConstraints` (all 12 methods
  *except* `test_existing_entries_in_catalog_have_empty_defaults`), plus the
  4 tail tests `test_dict_entry_has_phases_field_accepting_a_frozenset`,
  `test_dict_entry_phases_supports_multi_phase_ownership`,
  `test_dict_entry_phases_default_is_empty_frozenset`,
  `test_phase_literal_values` (these only need `DictEntry`, `Phase` — plain
  dataclass/literal, no catalog).
- **Moves to cardiacfoam (new file):** `TestDictEntryCatalog`,
  `TestDeepElectroOverrides`, `TestConductionSystemSchemaContract`,
  `TestDomainCouplingSchemaContract`,
  `test_existing_entries_in_catalog_have_empty_defaults` (pull this one
  method out of `TestDictEntryStructuredConstraints` into a small standalone
  test or its own class in the new file),
  `TestElectroPropertiesPresenceScans`, `TestDetectActiveTensionModelName`,
  `TestDetectActiveTensionExportList`, `TestEmptyExportListIsKnownEmpty`,
  `TestControlDictEntries`, `test_every_dict_entry_has_at_least_one_phase`,
  `test_every_phase_value_is_a_valid_literal`.

- [x] **Step 1: Read the current file in full (it's a concatenation of three originally-separate modules — three license banners inside one file)**

```bash
cd ~/omnidriver
cat -n packages/omnidriver/tests/core/test_dict_entries.py
```

- [x] **Step 2: Create `packages/omnidriver-cardiacfoam/tests/test_dict_entries_catalog.py`**

Copy every class/function in the "moves to cardiacfoam" list above verbatim,
with this import header:
```python
from __future__ import annotations

import tempfile
import typing
import unittest
from pathlib import Path

from omnidriver.dict_entries import (
    get_electro_property_entry_groups,
    PHYSICS_PROPERTY_ENTRIES,
    all_documented_driver_paths,
    Phase,
)
from omnidriver.cardiacfoam.overrides import apply_electro_property_overrides
from conftest import assert_foam_entry

VALID_PHASES = set(typing.get_args(Phase))
```
Trim unused imports per-class after pasting (e.g. only the two coverage tests
need `VALID_PHASES`/`typing`; only `TestDeepElectroOverrides` needs
`apply_electro_property_overrides`). For `test_existing_entries_in_catalog_have_empty_defaults`,
either keep it as a bare module-level function (it doesn't use `self`
meaningfully beyond `assertGreater`/`assertIsInstance` — convert to plain
`assert` statements) or leave it as a one-method `unittest.TestCase` class —
match whichever is less invasive once you see the exact body.

- [x] **Step 3: Trim `packages/omnidriver/tests/core/test_dict_entries.py`**

Delete every class/function moved in Step 2. What remains: the file header,
`TestDictEntryStructuredConstraints` (minus the one method), and the 4 tail
`Phase`/`DictEntry` tests. Update the top-of-file import to drop
`get_electro_property_entry_groups`, `PHYSICS_PROPERTY_ENTRIES`,
`all_documented_driver_paths`, `apply_electro_property_overrides`,
`assert_foam_entry` (none of the remaining tests use them) — keep only
`from omnidriver.dict_entries import DictEntry, Phase` (imported locally
inside `_build_entry` and at the tail already; consolidate to one top-level
import if it reads cleaner, but a local import is fine too since that's the
existing style in this file for `DictEntry`).

- [x] **Step 4: Verify core-only collection dropped to 2 remaining**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -10
```
Expected: `2 errors` — only the two `regression_equivalence` files left
(Task 10).

- [x] **Step 5: Verify both sides pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver/tests/core/test_dict_entries.py -q
pytest packages/omnidriver-cardiacfoam/tests/test_dict_entries_catalog.py -q
```

- [x] **Step 6: Commit**

```bash
git add packages/omnidriver/tests/core/test_dict_entries.py \
        packages/omnidriver-cardiacfoam/tests/test_dict_entries_catalog.py
git commit -m "test: finish splitting test_dict_entries.py -- cardiac catalog content out

Everything touching PHYSICS_PROPERTY_ENTRIES/CONTROL_DICT_ENTRIES/
get_electro_property_entry_groups is cardiac-bound (they're lazy shims onto
the cardiac plugin's catalog, see dict_entries.py:70-100). What's left in
core tests only the DictEntry/Phase dataclass contract itself."
```

---

### Task 9: Move the `regression_equivalence` subpackage whole

**Files:**
- Move: `packages/omnidriver/tests/regression_equivalence/` (entire directory:
  `__init__.py`, `__main__.py`, `conftest.py`, `registry.py`, `round_trip.py`,
  `dual_run.py`, `staging.py`, `test_cli_matrix.py`, `test_round_trip.py`,
  `test_dual_run.py`, `test_registry.py`, `test_staging.py`) →
  `packages/omnidriver-cardiacfoam/tests/regression_equivalence/`
- Modify: `pyproject.toml` (root) — `pythonpath` entry
  `"packages/omnidriver/tests/regression_equivalence"` no longer exists;
  either remove it (cardiacfoam's own tests dir is already on pythonpath via
  `"packages/omnidriver-cardiacfoam/tests"`, and the subpackage's own
  `__init__.py` makes `regression_equivalence` importable as a proper
  sub-package rather than needing its own pythonpath entry) or point it at
  the new location — check which by testing both ways.

**Interfaces:** `registry.py`'s `REGRESSION_CASES` is a hardcoded tuple of
cardiac tutorial paths; `round_trip.py` imports
`omnidriver.cardiacfoam.dict_builder` directly. None of this framework is
plugin-agnostic despite living under core's tests today — it's cardiac
machinery, full stop.

- [x] **Step 1: Move the whole directory**

```bash
cd ~/omnidriver
git mv packages/omnidriver/tests/regression_equivalence \
       packages/omnidriver-cardiacfoam/tests/regression_equivalence
```

- [x] **Step 2: Check the root pyproject.toml's `pythonpath` list**

```bash
grep -n "pythonpath" -A 5 pyproject.toml
```
Remove the now-stale `packages/omnidriver/tests/regression_equivalence`
entry if present (the directory doesn't exist there anymore); the package now
resolves through `packages/omnidriver-cardiacfoam/tests` being on
`pythonpath` plus its own `__init__.py`.

- [x] **Step 3: Verify core-only collection is now clean**

```bash
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver
pytest packages/omnidriver/tests --collect-only -q 2>&1 | tail -10
```
Expected: **0 errors during collection.** This is the whole point of the
plan — confirm it explicitly here, don't assume.

- [x] **Step 4: Verify the moved subpackage still collects and its non-skipped tests pass**

```bash
deactivate
cd ~/omnidriver
pytest packages/omnidriver-cardiacfoam/tests/regression_equivalence -q
```

- [x] **Step 5: Commit**

```bash
git add -A packages/omnidriver-cardiacfoam/tests/regression_equivalence \
           packages/omnidriver/tests/regression_equivalence pyproject.toml
git commit -m "test: move the regression_equivalence framework to cardiacfoam

registry.py hardcodes cardiac tutorial paths and round_trip.py imports
omnidriver.cardiacfoam.dict_builder directly -- this was never a
plugin-agnostic framework, just misplaced under core's tests. This clears
the last 2 of the original 14 test-core collection errors: core now
installs and collects alone with zero errors."
```

---

### Task 10: Full three-job verification + update GITHUB_MIGRATION.md

**Files:**
- Modify: `GITHUB_MIGRATION.md` (§2 rewritten to reflect 0 collection errors; §3 unchanged — round 2 scope is separate future work)

**Interfaces:** None — this is the closing verification + documentation task.

- [x] **Step 1: Run all three CI jobs locally, in the correct isolation each expects**

```bash
# core alone (fresh venv, Python 3.13 floor)
rm -rf /tmp/core_only_venv_check
/opt/homebrew/bin/python3.13 -m venv /tmp/core_only_venv_check
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" pytest
python -c "import omnidriver.cli; print('cli import OK')"
pytest packages/omnidriver/tests -q
deactivate

# openfoam (core + openfoam)
rm -rf /tmp/openfoam_venv_check
/opt/homebrew/bin/python3.13 -m venv /tmp/openfoam_venv_check
source /tmp/openfoam_venv_check/bin/activate
cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam pytest
pytest packages/omnidriver-openfoam/tests -q
deactivate

# cardiacfoam (all three)
rm -rf /tmp/cardiacfoam_venv_check
/opt/homebrew/bin/python3.13 -m venv /tmp/cardiacfoam_venv_check
source /tmp/cardiacfoam_venv_check/bin/activate
cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam pytest
pytest packages/omnidriver-cardiacfoam/tests -q
deactivate
```
Record the three pass/fail/skip counts. Expected: core-only shows 0 errors
and some N passed; openfoam and cardiacfoam counts should each be at or above
their pre-plan baseline (107 and 292 respectively) plus the tests that moved
in — do not accept a lower count without explaining every missing test.

- [x] **Step 2: Run `scripts/check-import-boundaries.py`**

```bash
cd ~/omnidriver
python3 scripts/check-import-boundaries.py
```
Confirm the waiver count hasn't grown and nothing new is flagged — this plan
touched only `tests/`, never `src/`, so it shouldn't move at all.

- [x] **Step 3: Rewrite GITHUB_MIGRATION.md §2**

Replace the entire "## 2. BLOCKER: core does not stand alone — 20 collection
errors" section (and its "Do not 'fix' this by installing all three packages"
subsection) with a short closed-out note, e.g.:

```markdown
## 2. RESOLVED: core now stands alone

`cli.py`'s module-scope `omnidriver.openfoam` import was fixed in `f51387b`
(20 → 14 collection errors). The remaining 14 were each either misplaced
(tests a sibling's behavior from core's tree) or mixed (a clean core test and
a sibling-dependent one sharing a file) -- no file needed a fourth "all three
packages" CI job. All 14 were resolved by moving or splitting test files; see
`docs/superpowers/plans/2026-08-27-test-core-decoupling.md` for the exact
per-file disposition. `pip install -e "packages/omnidriver[post]"` followed
by `pytest packages/omnidriver/tests` now collects and passes with zero
errors.

Two follow-ups were identified but deliberately not done as part of this
mechanical move (judgment calls, not test-tree surgery):
- Three tests moved into `omnidriver-cardiacfoam/tests/test_strict_planning.py`
  (`test_strict_plan_fails_on_unknown_workflow_command`,
  `test_strict_plan_fails_on_unknown_workflow_dependency`,
  `test_strict_dict_key_scanner_fails_on_unallowlisted_key`) use
  `CardiacFoamPlugin` only as a convenient concrete fixture for generic
  strict-planning/scanner behavior -- swapping them to `GenericOpenFOAMPlugin`
  or `plugins.minimal_plugin.MinimalOpenFOAMPlugin` would let them move back
  to core, but that's a design choice about test doubles, not a mechanical
  move.
- `packages/omnidriver-cardiacfoam/tests/plugins/minimal_plugin.py` duplicates
  `packages/omnidriver/tests/plugins/minimal_plugin.py` byte-for-byte in
  spirit (both implement the same no-domain plugin contract) -- worth
  deduplicating, out of scope here.
```

- [x] **Step 4: Commit**

```bash
cd ~/omnidriver
git add GITHUB_MIGRATION.md
git commit -m "docs: close out the test-core blocker in GITHUB_MIGRATION.md

core now installs and collects alone with zero errors, verified against a
fresh Python 3.13 venv, not this repo's own .venv. Round 2 scope (\$3) is
unaffected and still pending."
```

---

## Self-review notes

- **Spec coverage:** GITHUB_MIGRATION.md §2's three categories (misplaced /
  leaking-but-fixable / genuine-integration) are all addressed — the
  Explore-agent research found zero files meeting the genuine-integration bar
  in the *current* 14, so no 4th CI job task exists in this plan; that's a
  finding, not a gap. §3 (round 2 — `DriverContext` conversion, `get_phases()`,
  legacy branch retirement, dependency cleanup) is explicitly out of scope for
  this plan and called out as such in Task 10's doc update — it needs its own
  plan.
- **Placeholder scan:** no TBD/TODO markers; every split task names the exact
  test functions moving each direction rather than saying "similar tests."
- **Type consistency:** N/A (test-only reorg, no new production interfaces).
