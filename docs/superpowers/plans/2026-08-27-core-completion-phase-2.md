# Core Completion — Phase 2 Implementation Plan

> ## Progress: Tasks 1, 2, 4 landed. Task 5 RESCOPED — read §"Task 5, remeasured" before starting it.
>
> Core-only failures **160 → 140**; all-packages still **1469 passed / 0 failed**.
> Two of the four failure categories are now zero: `regression_equivalence` (Task 1)
> and `omnidriver.openfoam` (Task 4). Remaining: 129 `omnidriver.cardiacfoam`,
> 11 subprocess.
>
> | task | state |
> |---|---|
> | 1 equivalence regression | ✅ `9df738b` |
> | 2 relocate four modules | ✅ `1bde1a5`, corrected by `2e7ac99` |
> | 3 `get_phases()` | ✅ landed |
> | 4 neutral environment plugin | ✅ `4a96c18` |
> | 5 explicit `DriverContext` | **rescoped — see below** |
> | 6 openfoam context sites | ✅ landed |
> | 7 delete the 20 gates | ✅ landed |
>
> **Corrected 2026-09-03.** Tasks 3, 6 and 7 were marked "not started" in this
> table long after they landed, and their step checkboxes below are likewise
> still unchecked. Do not read an unchecked box here as outstanding work —
> verify against the code. Evidence: `legacy_phases()` in `compatibility.py`
> and `get_phases()` in `plugin_interface.py` (Task 3); `apply_overrides.py`
> taking a required `driver_context` (Task 6); `grep -c 'org.cardiacfoam'
> compatibility.py` returning 0, with `test_no_cardiac_gate_is_reached.py`
> asserting the gated set is empty (Task 7). The core-only failure count in
> this banner is also long superseded — it is now zero. Task 7 Step 2's
> instruction to leave `legacy_generic_case_mutation` "permanent-for-now" is
> superseded too: that function was deleted on 2026-09-03.
>
> **Merging 2 and 4 produced 3 failures neither had alone.** Both were cut from
> the same base; Task 2 added `legacy_dict_key_scanner` afterwards, and
> `strict_plan()` calls `catalogued_paths` *eagerly* to build an argument, so the
> openfoam import fires before the capability can dispatch to a plugin's hook.
> Root cause was that Task 2 moved too much: `catalogued_paths` parses core's own
> `DictEntry`, reads no file and knows no C++. Extracted to
> `core/contracts/catalogue_paths.py` in `2e7ac99`. **Lesson for the remaining
> waves: parallel tasks that both touch `compatibility.py` need a combined run
> before either is called done.**
>
> Also fixed: the wheel guard could be poisoned by a stale setuptools
> `build/lib` cache, which is gitignored so nothing cleaned it (`d6566a1`).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `omnidriver` stand alone — its own test suite passes with only
`omnidriver` installed, its CLI works with no plugin package present, and no
string in it names cardiacFoam.

**Architecture:** No new abstractions. Four of the seven tasks are ports of work
the legacy `driverFoam` tree has already done and validated; two are
relocations; one deletes code that Phase 1 proved unreachable. The design rule
they serve is
[`future/ENVIRONMENT_CONTRACT.md`](../../../future/ENVIRONMENT_CONTRACT.md) §4.

**Tech Stack:** Python ≥3.11 (verify on 3.13), pytest, `ast` (for the static
guards), the existing `compatibility.track_fallback_calls()` contextmanager.

---

## Where Phase 1 left things

Phase 1 landed on branch `phase1-core-completion` (9 commits, `a57eac4`..`8418365`).

| Goal | State | Owner |
|---|---|---|
| G1 core imports from a wheel | ✅ done, guarded | Phase 1 Task 4 |
| G2 plugin resolves by entry-point name | ✅ done, guarded | Phase 1 Task 1 |
| **G3 core's suite runs alone, zero failures** | ✗ **160 failed** | **this plan** |
| **G4 core's CLI usable alone** | ✗ dies in `build_parser()` | **this plan** |
| **G5 no `"org.cardiacfoam"` in core** | ✗ 20 occurrences | **this plan** |
| G6 deps, licence, CI | ✗ | Phase 3 |

Also delivered in Phase 1 and depended on here: the role vocabulary is a
validated enum (`plugin_profile.KNOWN_ROLES`), the case entrypoint is resolved
by declared role, and `test_no_cardiac_gate_is_reached.py` is the standing
census that makes Task 7's deletion safe.

## The 160, broken down *(as first measured; now 140 — see the progress banner)*

Measured on the Phase 1 tip in a core-only 3.13 venv. Every task below names
which slice it removes.

| count | cause | task |
|---|---|---|
| 129 | `omnidriver.cardiacfoam` — `legacy_default_driver_context()` behind `resolve_public_driver_context()` | 5, 6 |
| 12 | `omnidriver.openfoam` — the two **ungated** fallbacks (`legacy_config_value_reader`, `legacy_environment_diagnostics`) plus one direct test import | 4 |
| 11 | subprocess failures — 10 `CalledProcessError` from `scripts/export-*.py`, 1 `JSONDecodeError` from a CLI test. All resolve the implicit context one layer out | 5 (follows) |
| 8 | `regression_equivalence` — a regression introduced by `f1651b7` | 1 |

*Re-measured 2026-08-27 on `fb0b91d` with a `pytest_runtest_logreport` hook,
not by pairing `--tb=line` output: that pairing silently misaligns, because the
11 subprocess failures do not emit a cause line. An earlier count in this plan
split the openfoam slice 8/3/1 across the wrong files. Trust the hook.*

The 11 export-script failures are not a separate defect: those scripts call
core APIs without a context, so they resolve automatically once Task 5 lands.
Verify rather than assume.

---

## Global Constraints

- **Verify in a clean 3.13 virtualenv, never `~/omnidriver/.venv`** (that one
  runs 3.14, whose PEP 649 deferred annotations hide bugs the 3.11/3.12 CI
  matrix catches):
  ```bash
  rm -rf /tmp/od_core /tmp/od_all
  /opt/homebrew/bin/python3.13 -m venv /tmp/od_core
  /opt/homebrew/bin/python3.13 -m venv /tmp/od_all
  /tmp/od_core/bin/pip install -q -e "packages/omnidriver[post]" pytest
  /tmp/od_all/bin/pip install -q -e "packages/omnidriver[post]" \
      -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam pytest
  ```
- **Run installed-behaviour checks from a neutral cwd (`cd /tmp`).** A Python
  process started from a repo root puts stray `.egg-info` metadata on
  `sys.path`; that is what hid Phase 1's entry-point bug for a whole migration.
- **Two baselines, and both matter.** All-packages
  (`/tmp/od_all`, `pytest packages/ -m "not slow"`) must stay at **0 failed**
  throughout — that is the behaviour-preservation bar. Core-only
  (`/tmp/od_core`, `pytest packages/omnidriver/tests -m "not slow"`) starts at
  **160 failed, 514 passed, 91 skipped** and is what this plan drives to zero.
  Quote both in every report.
- **No `git commit` steps appear in this plan.** Committing is the operator's
  call.
- **Never weaken a test to make it pass.** If an existing test fails after your
  change, read it and decide which of two things it pins. If it pins *behaviour
  you are preserving*, your change is wrong — fix the change. If it pins *the
  coupling you are removing*, rewrite it against the new mechanism and say so
  explicitly in your report. If you cannot tell, **stop and report** rather than
  editing the assertion.
- **Stay inside your task's file list — and if it is wrong, say so.** Phase 1
  produced two file lists that were genuinely incomplete; in both cases the
  right move was to make the edit and report it prominently, not to leave the
  suite red. Do that, but never silently.
- **Report plan discrepancies rather than routing around them.** Five real
  defects in the Phase 1 plan were found this way, every one worth having.
- **Existing file conventions:** core source files carry a cardiacFoam GPLv3
  header block; leave them alone (the licence question is Phase 3). Tests are
  plain `def test_*` with `from __future__ import annotations`; `unittest.TestCase`
  appears in older files — do not convert them.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `packages/omnidriver/tests/equivalence/protocol.py` | drop the cross-package test import | 1 |
| `pyproject.toml` (root) | stop putting sibling test roots on `pythonpath` | 1 |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/spatial_pacing.py` | **moved** from core | 2 |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/rtst_scanner.py` | **moved** from `core/scripts/` | 2 |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/names_parser.py` | **moved** from `core/scripts/` | 2 |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_keys_scanner.py` | **moved** from `core/scripts/` | 2 |
| `packages/omnidriver/tests/core/test_wheel_install_imports.py` | delete the now-stale exclusion | 2 |
| `packages/omnidriver/src/omnidriver/core/specs/validation.py` | `phase_order` threading | 3 |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | `phases()` on the dictionary adapter | 3 |
| `packages/omnidriver/src/omnidriver/core/compatibility.py` | `legacy_phases`; later, 20 deletions | 3, 7 |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | `get_phases()` | 3 |
| `packages/omnidriver/tests/plugins/neutral_environment_plugin.py` | **new** — test double implementing the environment hooks | 4 |
| 7 files under `core/` | required `driver_context` | 5 |
| `packages/omnidriver/tests/core/test_core_context_is_explicit.py` | **new** — static guard | 5 |
| `packages/omnidriver/tests/core/test_fallback_census.py` | **new** — runtime guard | 5 |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py`, `dict_builder.py` | required `driver_context` | 6 |
| `scripts/check-import-boundaries.py` | stop exempting `compatibility.py` from the cardiac prefix | 7 |

---

### Task 1: Repair the `tests/equivalence` regression

`f1651b7` moved the `regression_equivalence` package to cardiacfoam's test tree
and left `packages/omnidriver/tests/equivalence/protocol.py:28` importing it.
Eight core tests fail. It went unnoticed because `test_protocol.py` does its
imports **inside test methods**, so `--collect-only` — the command used to
declare that blocker closed — reports clean, and because the root
`pyproject.toml` puts all three test roots on `pythonpath`, so a whole-repo run
resolves it anyway.

**Files:**
- Modify: `packages/omnidriver/tests/equivalence/protocol.py:28`
- Modify: `pyproject.toml` (root) — `[tool.pytest.ini_options] pythonpath`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing importable. `protocol.py` gains a local
  `parse_columnar_reference`.

- [ ] **Step 1: Confirm the failure and see exactly what is used**

```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/equivalence -q
```
Expected: **8 failed**, `ModuleNotFoundError: No module named 'regression_equivalence'`.

Then read what is actually imported:
```bash
grep -n "regression_equivalence" packages/omnidriver/tests/equivalence/protocol.py
```
Expected: one import, of `parse_columnar_reference` from
`regression_equivalence.dual_run`.

- [ ] **Step 2: Read the function being borrowed**

```bash
sed -n '/def parse_columnar_reference/,/^def /p' \
  packages/omnidriver-cardiacfoam/tests/regression_equivalence/dual_run.py
```

Decide between two dispositions and **state which in your report**:

- **(a)** the function is generic (parses a whitespace-columnar
  `file time variable expected tolerance` table with no cardiac knowledge) →
  copy it into `protocol.py` as a module-level private helper, with a comment
  naming where it came from and why it is duplicated rather than imported.
- **(b)** it carries cardiac knowledge → then `protocol.py` itself is
  misplaced, and the whole `tests/equivalence/` directory moves to cardiacfoam
  alongside `regression_equivalence`.

Evidence from the audit points to (a): the file is a `.reference`-format parser
and `protocol.py`'s own docstring describes a format, not a solver. Verify
rather than assume.

- [ ] **Step 3: Apply the chosen disposition, then re-run**

```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/equivalence -q
```
Expected: **21 passed** (or, under (b), `no tests ran` in core and 21 passed in
cardiacfoam).

- [ ] **Step 4: Remove the sibling test roots from the root config**

In the root `pyproject.toml`, `[tool.pytest.ini_options]`, reduce:

```toml
pythonpath = [
    "packages/omnidriver/tests",
    "packages/omnidriver-openfoam/tests",
    "packages/omnidriver-cardiacfoam/tests",
]
```

to only the root belonging to the package under test — i.e. delete the entry
for any package whose tests are not being collected. Since a whole-repo run
collects all three, the correct change is to **delete the `pythonpath` key
entirely** and rely on each package's own
`[tool.pytest.ini_options] pythonpath = ["tests"]`, which all three already
declare.

This is the point of the task: with all three roots on the path, a core test
importing a cardiacfoam test helper passes, and CI's isolation claim is
fiction.

- [ ] **Step 5: Verify both baselines**

```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
```
Expected: all-packages **0 failed** (unchanged); core-only **152 failed** (160
minus these 8).

If the all-packages run drops tests or errors on collection, the `pythonpath`
deletion went too far — restore the key with only the entries that are actually
needed and report which.

---

### Task 2: Relocate the four misplaced modules

Four modules in core belong to a sibling package. Three parse **OpenFOAM or
cardiacFoam C++ source**; one generates a cardiac electrophysiology pacing
protocol. One of them, `_rtst_scanner`, is also the last entry in the wheel
guard's `KNOWN_UNIMPORTABLE` exclusion — moving it deletes the exclusion.

| module | what it is | destination |
|---|---|---|
| `core/specs/spatial_pacing.py` | S1–S2 restitution pacing protocol, emitting OpenFOAM list syntax. Sole consumer: `cardiacfoam/tutorials/cable_1d_restitution.py:26` | cardiacfoam |
| `scripts/_rtst_scanner.py` | parses `addToRunTimeSelectionTable(...)` in C++; imports `PHYSICS_PROPERTY_ENTRIES` from `dict_entries`, which PEP 562-resolves into cardiacfoam | cardiacfoam |
| `scripts/_names_parser.py` | parses ionic-model `*_Names.H` headers | cardiacfoam |
| `scripts/_dict_keys_scanner.py` | parses OpenFOAM dictionary-read call sites in C++ | openfoam |

**Files:** the four above plus their importers —
`scripts/regenerate-ionic-catalog.py`, `scripts/scan-dict-keys.py`,
`core/strict_planning.py:64`, and the six test files that import them
(`omnidriver/tests/core/test_dict_keys_scanner.py`,
`omnidriver-openfoam/tests/core/test_case_dict_keys.py:173`,
`omnidriver-cardiacfoam/tests/test_strict_planning.py:16`,
`test_rtst_enum_contract.py:50`, `test_ionic_catalog_audit.py:57`,
`test_ionic_catalog_contract.py:48`). Plus
`packages/omnidriver/tests/core/test_wheel_install_imports.py`.

**Interfaces:**
- Consumes: nothing.
- Produces: `omnidriver.cardiacfoam.spatial_pacing`,
  `omnidriver.cardiacfoam.rtst_scanner`, `omnidriver.cardiacfoam.names_parser`,
  `omnidriver.openfoam.dict_keys_scanner`. Drop the leading underscore on
  relocation: these become public modules of their new packages.

- [ ] **Step 1: Move `spatial_pacing` — the zero-risk one first**

```bash
git mv packages/omnidriver/src/omnidriver/core/specs/spatial_pacing.py \
       packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/spatial_pacing.py
```
Update its one importer,
`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/tutorials/cable_1d_restitution.py:26`:

```python
from omnidriver.cardiacfoam.spatial_pacing import generate_spatial_s1_s2_stimulus_lists
```

Verify: `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"` → 0 failed.

- [ ] **Step 2: Move the two cardiac C++ scanners**

```bash
git mv packages/omnidriver/src/omnidriver/scripts/_rtst_scanner.py \
       packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/rtst_scanner.py
git mv packages/omnidriver/src/omnidriver/scripts/_names_parser.py \
       packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/names_parser.py
```

`rtst_scanner.py` imports from `omnidriver.dict_entries`. Now that it lives in
cardiacfoam, point it at the real source instead of the deprecated re-export:

```python
from omnidriver.cardiacfoam.common_dict_entries import PHYSICS_PROPERTY_ENTRIES
from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.dict_entries import get_electro_property_entry_groups
```

Check `common_dict_entries.py` actually exports `PHYSICS_PROPERTY_ENTRIES`
before relying on it; if the name differs there, use the real one and report.

Update importers: `scripts/regenerate-ionic-catalog.py:47`,
`packages/omnidriver-cardiacfoam/tests/test_rtst_enum_contract.py:50`,
`test_ionic_catalog_audit.py:57`, `test_ionic_catalog_contract.py:48`.

- [ ] **Step 3: Move the OpenFOAM dict-key scanner — the one with a core consumer**

```bash
git mv packages/omnidriver/src/omnidriver/scripts/_dict_keys_scanner.py \
       packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_keys_scanner.py
```

`core/strict_planning.py:64` imports from it and is the only core consumer. Core
must not import `omnidriver.openfoam` directly, so route it exactly as the
existing ungated fallbacks do — add to `core/compatibility.py`:

```python
@_instrumented
def legacy_dict_key_scanner():
    """Plugins predating a C++ dict-key scanner hook. strict_planning has
    always scanned OpenFOAM C++ sources for dictionary-read call sites, for
    every plugin -- the same was-never-actually-solver-neutral situation as
    legacy_case_dict_key_diagnostics, which parses the dicts themselves.
    Preserved as-is; a non-OpenFOAM plugin implements this itself."""

    from omnidriver.openfoam.dict_keys_scanner import (
        catalogued_names, scan_source_tree,
    )

    return catalogued_names, scan_source_tree
```

Import the real symbol names `strict_planning.py:64` uses — read that import
statement rather than trusting the two named above.

**Report this honestly:** it moves the import from core into `compatibility.py`,
which the boundary gate exempts. That is a real improvement (core's own module
tree stops parsing C++) and it is *not* a full decoupling — `strict_planning`
still reaches OpenFOAM at runtime. It joins the eight ungated fallbacks the
`ENVIRONMENT_CONTRACT` names as the honest cost of core owning the OpenFOAM
execution model. Do not describe it as removing the dependency.

Update importers: `scripts/scan-dict-keys.py:52`,
`packages/omnidriver/tests/core/test_dict_keys_scanner.py:10` (which should move
to openfoam's suite — it tests an openfoam module now),
`packages/omnidriver-openfoam/tests/core/test_case_dict_keys.py:173`,
`packages/omnidriver-cardiacfoam/tests/test_strict_planning.py:16`.

- [ ] **Step 4: Delete the wheel guard's exclusion**

In `packages/omnidriver/tests/core/test_wheel_install_imports.py`, remove the
entry from `KNOWN_UNIMPORTABLE`, leaving an empty set. The guard's stale-entry
check will fail if you remove the module but not the entry, and vice versa —
that is the check working.

- [ ] **Step 5: Verify, including the wheel guard**

```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_wheel_install_imports.py -q -m slow
/tmp/od_all/bin/python scripts/check-import-boundaries.py
```
Expected: 0 failed; wheel guard passes with an empty exclusion set; boundary gate
exit 0. Core-only should be **152 failed** still (this task removes none of the
160 — it is an ownership fix, not a failure fix). Say so rather than expecting
a drop.

---

### Task 3: Port `get_phases()` — the one silent-wrong defect

`primary_phase(entry)` walks `_PHASE_ORDER = get_args(Phase)`, and
`Phase = Literal["anatomy","physics","stimulus","solver"]` is cardiacFoam's
vocabulary sitting in `core/runtime/run_model.py:44`. For any plugin whose
phase words differ, `primary_phase()` returns `None` — and
`validation.py:353` and `:371` both then say `continue`. Required-field and
enum checks are **silently skipped**, and `_evaluate_structured` at `:412`
writes entries into a `"physics"` slice the plugin never declared.

The legacy `driverFoam` tree already fixed this. Port its shape.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/specs/validation.py:62,73,121,144,352,370,402,412`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` — `_DictionaryCatalogAdapter`
- Modify: `packages/omnidriver/src/omnidriver/core/compatibility.py` — add `legacy_phases`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py` — document `get_phases` in `SolverPluginOptionalHooks`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py:239`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/run_document_config.py:96`
- Create: `packages/omnidriver/tests/core/test_phases_are_plugin_declared.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `primary_phase(entry, phase_order: tuple[str, ...]) -> str | None`
  (signature change — a second **positional** parameter, matching legacy);
  `capabilities.dictionaries.phases() -> tuple[str, ...]`;
  `compatibility.legacy_phases(plugin) -> tuple[str, ...]`;
  `CardiacFoamPlugin.get_phases() -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_phases_are_plugin_declared.py`:

```python
"""A plugin's dictionary phases are its own, not cardiacFoam's four.

core's Phase literal spells anatomy/physics/stimulus/solver. While
primary_phase() walked that literal, every entry of a plugin using different
phase words returned None -- and validation's required-field and enum checks
both read None as "skip". A plugin got a clean bill of health because core
could not see its entries at all. That is the only silently-wrong defect in
the compatibility set.
"""
from __future__ import annotations

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context
from omnidriver.core.specs.validation import primary_phase


class _Entry:
    def __init__(self, phases):
        self.phases = phases
        self.driver_path = "some/path"


def test_primary_phase_uses_the_order_it_is_given() -> None:
    entry = _Entry(("solve", "setup"))
    assert primary_phase(entry, ("setup", "solve")) == "setup"
    assert primary_phase(entry, ("solve", "setup")) == "solve"


def test_an_entry_claiming_no_declared_phase_returns_none() -> None:
    assert primary_phase(_Entry(("mesh",)), ("setup", "solve")) is None


def test_the_generic_plugin_declares_the_phases_its_entries_use() -> None:
    """It has no entries, so it declares no phases -- and must not inherit
    cardiacFoam's four."""
    phases = generic_openfoam_context().capabilities.dictionaries.phases()
    assert phases == ()


def test_cardiacfoam_declares_its_four_in_order() -> None:
    import pytest

    cardiacfoam_plugin = pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason="omnidriver-cardiacfoam is not installed",
    )
    context = driver_context(
        cardiacfoam_plugin.CardiacFoamPlugin(), source="test:phases",
    )
    assert context.capabilities.dictionaries.phases() == (
        "anatomy", "physics", "stimulus", "solver",
    )
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_phases_are_plugin_declared.py -v`

Expected: the first two FAIL with `TypeError: primary_phase() takes 1 positional
argument but 2 were given`; the third FAILS with `AttributeError: ... no
attribute 'phases'`; the fourth SKIPS in core-only.

- [ ] **Step 3: Add the fallback**

In `core/compatibility.py`, beside the other `legacy_*` functions:

```python
@_instrumented
def legacy_phases(plugin) -> tuple[str, ...]:
    """The dictionary phases for a plugin that does not implement
    ``get_phases()``: those its own ``DictEntry`` values declare, sorted for
    determinism.

    Sorted, not ordered -- and the order is the semantics, since
    ``primary_phase()`` returns the first phase in it that an entry claims. A
    plugin with multi-phase entries should implement ``get_phases()`` rather
    than accept an alphabetical guess. What this must never do is hand back
    cardiacFoam's four to a plugin that never declared them: that was the
    silent defect this replaces."""

    declared: set[str] = set()
    for entry in plugin.get_dict_entries():
        declared.update(entry.phases)
    return tuple(sorted(declared))
```

Note this one is **ungated** — no `plugin_id` check. It derives from the
plugin's own data, so it is correct for every plugin. Do not add a gate.

- [ ] **Step 4: Add the adapter method**

In `core/plugin_capabilities.py`, on `_DictionaryCatalogAdapter` (beside
`entries`, `catalog`, `groups`):

```python
    def phases(self) -> tuple[str, ...]:
        hook = getattr(self.plugin, "get_phases", None)
        if callable(hook):
            return tuple(hook())
        from .compatibility import legacy_phases

        return legacy_phases(self.plugin)
```

Add `phases` to the `DictionaryCatalogCapability` Protocol in the same file, and
extend that Protocol's `:adapts:` field to include `get_phases` — the
`test_capability_seam_documentation.py` conformance test and
`scripts/export-capability-seams.py --check` both read those fields, so
`ARCHITECTURE.md`'s generated table must be regenerated in the same edit:

```bash
/tmp/od_all/bin/python scripts/export-capability-seams.py
```

- [ ] **Step 5: Thread `phase_order` through validation**

In `core/specs/validation.py`:

```python
def primary_phase(entry, phase_order: tuple[str, ...]) -> str | None:
    """Return the editing phase for a (possibly multi-phase) entry.

    Walks ``phase_order`` -- the ACTIVE PLUGIN's declared phases, from
    ``capabilities.dictionaries.phases()`` -- and returns the first phase the
    entry claims; every other declared phase is a read-only mirror.

    The order is passed in rather than read from the core ``Phase`` literal
    because that literal spells cardiacFoam's vocabulary. Reading it made every
    entry of a plugin with different phase words return ``None`` here, which the
    required-field and enum checks then treated as "skip".
    """
    for ph in phase_order:
        if ph in entry.phases:
            return ph
    return None
```

Delete `_PHASE_ORDER` (line 62) and the now-unused `get_args` import. At the
function that owns the validation run, bind once:

```python
    phase_order = driver_context.capabilities.dictionaries.phases()
```

and pass it to `_non_mapping_phase_errors(run, phase_order)` and to every
`primary_phase(e, phase_order)` call (lines ~352, ~370, ~412). At line 144
replace `phase if phase in _PHASE_ORDER else "physics"` with
`phase if phase in phase_order else (phase_order[0] if phase_order else "")`,
and at line 412 replace `primary_phase(e) or "physics"` with
`primary_phase(e, phase_order) or (phase_order[0] if phase_order else "")`.

- [ ] **Step 6: Turn the silent skip into a diagnostic**

This is the behavioural half of the fix, and the reason the defect was
"silently wrong" rather than merely wrong. At lines ~353 and ~371, replace:

```python
        ph = primary_phase(e)
        if ph is None:
            continue
```

with:

```python
        ph = primary_phase(e, phase_order)
        if ph is None:
            errors.append(ValidationError(
                phase=phase_order[0] if phase_order else "",
                field=e.driver_path,
                message=(
                    f"{e.driver_path} declares phases {sorted(e.phases)}, none "
                    f"of which the active plugin declares: {list(phase_order)}. "
                    "It cannot be validated. Add the phase to get_phases() or "
                    "correct the entry."
                ),
                level="error",
            ))
            continue
```

`ValidationError`'s fields are `phase`, `field`, `message`, `level` — verified.
But note **`phase` is annotated `Phase`**, the cardiac `Literal`
(`validation_types.py:8`). Passing a plugin-declared phase string is correct at
runtime (dataclasses do not validate annotations) and wrong to a type checker,
so widen it in the same edit:

```python
@dataclass(frozen=True)
class ValidationError:
    phase: str          # a plugin-declared phase, not core's Phase literal
    field: str
    message: str
    level: str  # "error" | "warning"
```

and drop the now-unused `Phase` import there. `validation.py:115`'s
`_slice_value(run, phase: Phase, ...)` needs the same widening; those three
annotations plus `primary_phase`'s return type are every use of `Phase` in
core outside `run_model.py`, so after this task `Phase` types only the
`RunDocument` slices.

- [ ] **Step 7: Update the two out-of-core callers**

`packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py:239` and
`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/run_document_config.py:96`
both call `primary_phase(entry) or "physics"`. Each has a `driver_context` in
scope or can take one; pass
`driver_context.capabilities.dictionaries.phases()` and replace the `"physics"`
literal with `phase_order[0] if phase_order else ""`.

If either genuinely has no context available, **stop and report** — that is a
threading problem Task 5 may need to solve first, not something to paper over
with a default.

- [ ] **Step 8: Implement the hook on cardiacFoam**

In `cardiacfoam_plugin.py`:

```python
    def get_phases(self) -> tuple[str, ...]:
        """This plugin's four editing phases, in the order the RunDocument
        config and the validation slices use."""
        return ("anatomy", "physics", "stimulus", "solver")
```

- [ ] **Step 9: Document the hook**

Add `get_phases` to `SolverPluginOptionalHooks` in `core/plugin_interface.py`,
under a `# -- DictionaryCatalogCapability` heading, with legacy's docstring —
the ORDER-is-the-semantics point is the part a plugin author must not miss:

```python
    def get_phases(self) -> tuple[str, ...]:
        """This plugin's dictionary editing phases, in order.

        The ORDER is the semantics, not decoration: ``primary_phase()`` returns
        the first phase in this tuple that an entry claims, and every other
        phase the entry declares is a read-only mirror. These strings are also
        the top-level keys of ``RunDocument.config``.

        Absent -> the phases the plugin's own ``DictEntry`` values declare,
        which is correct but unordered. Declare this hook if any entry is
        multi-phase, because otherwise which phase is "primary" is arbitrary."""
        ...
```

Update the class docstring's hook count (it says fourteen) and
`SolverPlugin`'s if it names a number.

- [ ] **Step 10: Verify**

```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_phases_are_plugin_declared.py -v
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od_all/bin/python scripts/export-capability-seams.py --check
```
Expected: 4 passed (3 in core-only, 1 skipped); all-packages **0 failed**; seam
table up to date.

`Phase` in `run_model.py:44` stays for now — it still types `RunDocument`
slices. Removing it is a separate change; note in your report whether anything
still reads it.

---

### Task 4: Neutral test doubles for the ungated environment fallbacks

Twelve core-only failures have nothing to do with the cardiac default. Eleven
come from two **ungated** fallbacks that import `omnidriver.openfoam`
unconditionally whenever a plugin does not implement the hook:

- `compatibility.py:545` `legacy_config_value_reader` — 8 failures
- `compatibility.py:278` `legacy_environment_diagnostics` — 3 failures

The twelfth is `tests/core/test_sweep_materialize.py:98` importing
`omnidriver.openfoam` directly.

Per `ENVIRONMENT_CONTRACT.md` §4, those fallbacks are a legitimate documented
default that a plugin may override — so the fix is not to delete them. It is
that **core's own tests must exercise core with a plugin that overrides them**,
which is also the only way core's suite proves core works without OpenFOAM.

**Files:**
- Create: `packages/omnidriver/tests/plugins/neutral_environment_plugin.py`
- Modify: the core test files that currently trip the fallbacks
- Modify or move: `packages/omnidriver/tests/core/test_sweep_materialize.py`

- [ ] **Step 1: Confirm the worklist**

Measured on `fb0b91d`. These are the 12, in four files:

| file | n | tests |
|---|---|---|
| `tests/core/test_provenance_inputs.py` | 8 | `test_selected_start_time_directory_is_included_others_excluded`, `test_latest_time_selects_the_latest_written_time_directory`, `test_postprocessing_and_workflow_logs_are_excluded`, `test_generic_plugin_still_requires_unknown_files`, `test_an_allrun_named_by_the_dag_is_included`, `test_a_parallel_step_includes_both_mpirun_and_its_payload`, `test_a_required_but_unresolved_step_executable_is_unavailable_not_omitted`, `test_processor_selected_time_is_included_other_processor_times_excluded` |
| `tests/core/test_generic_plan_has_no_cardiac_semantics.py` | 2 | `test_generic_plan_contains_no_cardiac_semantics`, `test_generic_plan_still_produces_a_usable_contract` |
| `tests/core/test_core_generic_case.py` | 1 | `test_plain_allrun_case_works_with_the_no_domain_context` |
| `tests/core/test_sweep_materialize.py` | 1 | `test_materialize_case_honours_dx_for_spatial_solver` |

Confirm with the hook rather than by grepping tracebacks — a `--tb=line` pairing
misaligns here:

```python
# /tmp/failcause.py
import collections
_rows = []
def pytest_runtest_logreport(report):
    if report.failed and report.when == "call":
        text = str(report.longrepr)
        for pat in ("omnidriver.cardiacfoam", "omnidriver.openfoam",
                    "regression_equivalence"):
            if f"No module named '{pat}'" in text:
                _rows.append((report.nodeid, pat)); return
        _rows.append((report.nodeid, "other"))
def pytest_sessionfinish(session, exitstatus):
    print(collections.Counter(c for _, c in _rows))
    for nid, c in _rows:
        if c == "omnidriver.openfoam": print(nid)
```
```bash
PYTHONPATH=/tmp /tmp/od_core/bin/python -m pytest packages/omnidriver/tests \
  -q -p failcause -m "not slow"
```

**Two of these are worth reading before you touch them.**
`test_generic_plan_has_no_cardiac_semantics.py` is an *architecture guard* —
that it cannot run in a core-only install is itself a finding, and the guard is
the kind of test that must keep asserting exactly what it asserts today.
`test_provenance_inputs.py` owns 8 of the 12 and contains `_FakePlugin`, a
subclass of `MinimalOpenFOAMPlugin` that overrides `__init__` without calling
`super()` — Phase 1 Task 3 had to accommodate it. Expect it to need the neutral
hooks too, and prefer giving `_FakePlugin` the hooks over rewriting each test.

- [ ] **Step 2: Write the neutral plugin**

Create `packages/omnidriver/tests/plugins/neutral_environment_plugin.py`,
subclassing the existing minimal plugin and implementing the two environment
hooks with genuinely non-OpenFOAM answers:

```python
"""A plugin that answers the environment hooks itself, with no OpenFOAM.

core's compatibility fallbacks for these two hooks import omnidriver.openfoam
unconditionally -- a documented default (future/ENVIRONMENT_CONTRACT.md §4),
not a defect. But it means a core test that omits them is not testing core, it
is testing core-plus-OpenFOAM. This double is what lets core's own suite prove
core runs without a sibling package installed.
"""
from __future__ import annotations

from pathlib import Path

from plugins.minimal_plugin import MinimalOpenFOAMPlugin


class NeutralEnvironmentPlugin(MinimalOpenFOAMPlugin):
    """Implements every hook whose fallback reaches omnidriver.openfoam."""

    @property
    def plugin_id(self) -> str:
        return "org.driverfoam.test-neutral-environment"

    def get_config_value_reader(self):
        """A reader for a trivial ``key value`` line format -- deliberately
        NOT OpenFOAM syntax, so a test passing this plugin proves core never
        assumed one."""
        def _read(path: Path, key: str) -> str | None:
            try:
                for line in Path(path).read_text().splitlines():
                    name, _, value = line.strip().partition(" ")
                    if name == key:
                        return value.strip().rstrip(";") or None
            except OSError:
                return None
            return None

        return _read

    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, openfoam_bashrc=None, driver_context=None,
    ) -> tuple:
        """No environment preconditions: this plugin's steps need no sourced
        profile. Returning () is a real answer, not a stub."""
        del workflow_dag, env, openfoam_bashrc, driver_context
        return ()
```

- [ ] **Step 3: Point the failing tests at it**

For each test recorded in Step 1, replace the context it builds with one over
`NeutralEnvironmentPlugin`. **Read each test first.** Two outcomes are legitimate
and you must say which you chose per test:

- the test is exercising **core** logic and merely needed a plugin → swap the
  plugin, keep every assertion.
- the test is exercising **OpenFOAM** behaviour (it asserts on `controlDict`
  contents, bashrc sourcing, `foamlib` parsing) → it belongs in
  `packages/omnidriver-openfoam/tests/`; move it whole.

`test_sweep_materialize.py:98` imports `omnidriver.openfoam` directly, so it is
almost certainly the second kind. Verify by reading it.

- [ ] **Step 4: Verify**

```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
```
Expected: core-only **140 failed** (152 minus these 12); all-packages 0 failed.
Every remaining core-only failure should now name `omnidriver.cardiacfoam`
— confirm with the `--tb=line` breakdown and quote it.

---

### Task 5, remeasured — it is not one task, and it is not mostly mechanical

**Read this before Task 5 as written below.** The task description assumes the
129 remaining failures are a threading problem that converting 21 signatures
fixes. Measured on `d6566a1`, that is wrong.

**Where the 129 enter core** (last core frame before `compatibility.py`):

| n | entry point |
|---|---|
| 43 | `plugin_interface.py:652 default_driver_context()` — the **test itself** asked for the cardiac context |
| 17 | `sweep_runner.py:368 sweep_run()` |
| 12 | `registry.py:483 _get_plugin_tutorials()` |
| 12 | `sweep_routing.py:43 route_case_values()` — a module Task 5 deliberately does **not** convert |
| 10 | `validation.py:324 validate_run()` |
| 8 | `sweep_runner.py:263 sweep_plan()` |
| 4 | `sweep_materialize.py:42 materialize_case()` — likewise **not** converted |
| 23 | the remaining core sites |

**Why signature conversion alone fixes almost none of them.** Making
`driver_context` required does not give a test a plugin; it changes
`ModuleNotFoundError` into `TypeError: missing required argument`. Every one of
the 129 still needs a decision: *which plugin should this test run under?*

**And for many, no context makes them pass.** `test_sweep_runner.py` — 23 of the
129 — has 79 lines of cardiac vocabulary and a shared fixture defaulting to
`entry="niederer2012"`. There is no `niederer2012` tutorial without
`omnidriver-cardiacfoam` installed. Threading a context cannot help; the file is
a core test written against cardiacFoam's tutorial catalogue.

**Classified by what each failing test file already does:**

| n | the file … | disposition |
|---|---|---|
| 17 | builds a non-cardiac context and still fails | genuine threading gap — mechanical |
| 19 | builds only the cardiac context | ownership decision |
| 27 | builds both | per-test decision |
| 77 | builds no context at all | ownership decision |

**~13% mechanical, ~87% per-test judgement.**

### Split Task 5 in two

**Task 5a — thread explicit context through `core/` (mechanical).** The 21
signature sites, the transformation below, and both guards. Legacy's diff is a
faithful template. Expect it to fix ~17 failures and to convert most of the rest
from `ModuleNotFoundError` to `TypeError`, which is *progress*: the guard test
then names every site that still lacks a context, instead of the failure being
invisible until cardiacfoam is uninstalled. Safe to hand to an agent.

**Task 5b — adjudicate the test suite (judgement).** For each remaining failing
test, decide: does it exercise **core** behaviour using cardiacFoam as a
convenient concrete fixture (→ give it `GenericOpenFOAMPlugin` or
`NeutralEnvironmentPlugin`, keep it in core), or does it exercise **cardiacFoam**
behaviour (→ move it to `packages/omnidriver-cardiacfoam/tests/`)?

**This is the one task in either phase that must not be batch-delegated without
per-file review.** Its failure mode is silent and it is not the usual one. The
"never weaken a test" rule catches an assertion being softened; here the
assertions survive intact and simply stop being exercised against anything
meaningful — swap `niederer2012` for a generic plugin and the test goes green
while testing nothing. A green suite would then certify an isolation the code
does not have, which is precisely the class of false reassurance this repository
has produced three times already (an import gate scanning the wrong directory, a
collection check blind to function-scoped imports, a wheel guard reading a stale
build cache).

Two rules for 5b:

1. **A test that goes green under a generic plugin must still fail if the
   behaviour it names regresses.** Mutation-check a sample, do not assume.
2. **Moving to cardiacfoam is the default, not the fallback.** If a test needs
   cardiacFoam's tutorial catalogue, ionic models, or dictionary vocabulary to
   mean anything, it is a cardiacFoam test that was written in the wrong tree.
   `test_sweep_runner.py` and `test_sweep_routing.py` are the obvious
   candidates; read them before deciding.

---

### Task 5: Explicit `DriverContext` through `core/`

The load-bearing task. `resolve_public_driver_context(None)` returns the cardiac
context, and 18 call sites across 7 files under `core/` call it whenever a
caller omits one. Measured across a full suite run: **35,395 implicit
resolutions against 915 explicit ones**, 97.5% implicit. Legacy's own census
recorded 51,540 before its conversion and asserts zero after.

**This is not a mechanical search-and-replace.** Legacy has **zero**
`resolve_public_driver_context` calls under `core/` and still carries **11**
`DriverContext | None` annotations there. The rule is: the function that *uses*
`.capabilities` demands a real context; a pure pass-through keeps the optional
annotation and hands it down. Copy that shape.

**Files (18 sites, 7 files):**

| file | lines | notes |
|---|---|---|
| `core/runtime/registry.py` | 105, 122, 216, 389, 483 | legacy's diff for `_is_case_directory` / `_case_is_runnable` is the template |
| `core/introspection.py` | 144, 155, 176, 248 | describe/catalog surface |
| `core/strict_planning.py` | 297, 318, 390 | the planner must never guess a plugin |
| `core/specs/validation.py` | 69, 324 | Task 3 already threads `phase_order` here |
| `core/runtime/sweep_runner.py` | 263, 368 | |
| `core/runtime/artifacts.py` | 181 | |
| `core/runtime/run_document_exec.py` | 132 | the document already carries a `plugin` block |

Plus create: `tests/core/test_core_context_is_explicit.py`,
`tests/core/test_fallback_census.py`.

**Do NOT convert:** `dict_entries.py` (3 sites), `sweep_routing.py`,
`sweep_materialize.py`, `cli.py`, or `cardiacfoam/dict_builder.py`. Those are
the public compatibility edge where "no plugin supplied" genuinely means "the
built-in one", and legacy keeps every one of them.

- [ ] **Step 1: Write the static guard first — it is the acceptance criterion**

Create `packages/omnidriver/tests/core/test_core_context_is_explicit.py`,
ported from legacy verbatim:

```python
"""core/ must receive an explicit DriverContext, never resolve one implicitly.

`resolve_public_driver_context(None)` returns the cardiac context. A core module
that calls it silently becomes cardiacFoam for any plugin that failed to thread a
context through -- and it does so without raising, which is why this guard is
static rather than behavioural.

The cardiac default is legitimate at the public edge (omnidriver/*.py and
cli.py), where "no plugin supplied" genuinely means "the built-in one". It is not
legitimate inside core/.
"""
from __future__ import annotations

import ast
import pathlib

import omnidriver.core

_CORE_ROOT = pathlib.Path(omnidriver.core.__file__).resolve().parent

# compatibility.py defines the function; it is allowed to mention its own name.
_EXEMPT = {_CORE_ROOT / "compatibility.py"}


def _calls_resolve_public(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "resolve_public_driver_context":
            lines.append(node.lineno)
    return lines


def test_core_never_resolves_an_implicit_driver_context() -> None:
    offenders: dict[str, list[int]] = {}
    for path in sorted(_CORE_ROOT.rglob("*.py")):
        if path in _EXEMPT or "__pycache__" in path.parts:
            continue
        hits = _calls_resolve_public(path)
        if hits:
            offenders[str(path.relative_to(_CORE_ROOT))] = hits
    assert offenders == {}, (
        "core/ modules resolving an implicit (cardiac) DriverContext:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nMake driver_context a required parameter instead."
    )
```

Run it: expected **FAIL**, listing all 7 files and 18 lines. That list is your
worklist, and it shrinks as you go.

- [ ] **Step 2: Convert one file, using this exact transformation**

Worked example — `core/runtime/registry.py::_case_is_runnable`, which is
legacy's own diff. Before:

```python
def _case_is_runnable(
    case_root: Path,
    *,
    driver_context: "DriverContext | None" = None,
) -> bool:
    from ..compatibility import resolve_public_driver_context
    from ..plugin_capabilities import CaseCompatibilityRequest

    driver_context = resolve_public_driver_context(driver_context)
    if _has_entrypoint(case_root, driver_context):
        return True
    return driver_context.capabilities.case_compatibility.is_runnable_without_workflow(
        CaseCompatibilityRequest(case_root),
    )
```

After:

```python
def _case_is_runnable(
    case_root: Path,
    *,
    driver_context: "DriverContext",
) -> bool:
    from ..plugin_capabilities import CaseCompatibilityRequest

    if _has_entrypoint(case_root, driver_context):
        return True
    return driver_context.capabilities.case_compatibility.is_runnable_without_workflow(
        CaseCompatibilityRequest(case_root),
    )
```

Three edits: drop the `| None = None`, drop the `resolve_public_driver_context`
import, drop the reassignment. Then fix every caller the type checker or the
suite surfaces — pushing the requirement outward until it reaches a public
entry point that legitimately has a context.

**Judgement, per site:** if a function never touches `.capabilities` and only
hands the context down, leave its annotation `"DriverContext | None" = None`
and let the leaf demand a real one. Legacy keeps 11 such annotations. Converting
those too is the mechanical over-reach this task must avoid.

- [ ] **Step 3: Repeat per file, verifying after each**

Convert in this order — fewest callers first, so each step's fallout is small:
`artifacts.py` (1), `run_document_exec.py` (1), `sweep_runner.py` (2),
`validation.py` (2), `strict_planning.py` (3), `introspection.py` (4),
`registry.py` (5).

After each file:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_core_context_is_explicit.py -q
```
All-packages must stay at **0 failed** the whole way. The guard's offender list
must shrink by exactly the file you just converted.

- [ ] **Step 4: Add the runtime census guard**

Create `packages/omnidriver/tests/core/test_fallback_census.py`. The
machinery — `compatibility.track_fallback_calls()` — already exists:

```python
"""An explicitly-contexted operation must never fall back to the cardiac default.

The static guard in test_core_context_is_explicit.py proves core contains no
implicit resolution syntactically. This proves the runtime consequence: an
operation driven by a named plugin fires legacy_default_driver_context zero
times.
"""
from __future__ import annotations

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context

import plugins.minimal_plugin as minimal_plugin


def assert_no_default_context_fallback(operation) -> None:
    with compatibility.track_fallback_calls() as calls:
        operation()
        fired = [n for n in calls if n == "legacy_default_driver_context"]
    assert fired == [], (
        f"operation resolved the built-in cardiac context {len(fired)} time(s); "
        "it should use the DriverContext it was given"
    )


def test_capability_reads_under_an_explicit_generic_context_use_no_default() -> None:
    ctx = generic_openfoam_context()

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.dictionaries.groups()
        caps.dictionaries.phases()
        caps.manifest.manifest()
        caps.tutorials.displays()

    assert_no_default_context_fallback(op)


def test_capability_reads_under_an_explicit_minimal_context_use_no_default() -> None:
    ctx = driver_context(minimal_plugin.MinimalOpenFOAMPlugin(), source="test:census")

    def op() -> None:
        caps = ctx.capabilities
        caps.dictionaries.entries()
        caps.dictionaries.phases()
        caps.case_files.required_files()

    assert_no_default_context_fallback(op)
```

`caps.dictionaries.phases()` requires Task 3. If Task 3 has not landed, drop
that line and note it.

- [ ] **Step 5: Verify G3 and G4**

```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
cd /tmp && /tmp/od_core/bin/python -m omnidriver --help
cd /tmp && /tmp/od_core/bin/python -m omnidriver list
cd /tmp && /tmp/od_core/bin/python -m omnidriver plugins
```

Expected: core-only **0 failed** (G3), and all three CLI commands exit 0 (G4).

`--help` currently dies at `cli.py:604`, where `build_parser()` calls
`list_tutorials()`. Once `registry.py` requires an explicit context, that call
must pass one — `generic_openfoam_context()` is the right choice at a
parser-construction boundary where no `--plugin` has been parsed yet. If the
tutorial list is genuinely plugin-dependent, the honest fix is for `--help` to
stop enumerating tutorials; **report which you chose and why.**

Also re-run the 11 export-script tests and confirm they now pass without
change. If they do not, they need their own explicit context — say so.

---

### Task 6: Explicit `DriverContext` in `omnidriver-openfoam`

Three sites in the OpenFOAM package call core's
`resolve_public_driver_context`, so `apply_overrides(…, driver_context=None)`
raises `ModuleNotFoundError: omnidriver.cardiacfoam` in a core+openfoam install.
A wrong-direction dependency the import gate cannot see, because openfoam
imports *core* and core does the cardiac import.

**Files:**
- `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py:150` (`_catalog_entries`), `:288` (`apply_overrides`)
- `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py:278`

- [ ] **Step 1: Reproduce the leak**

```bash
cd /tmp && /tmp/od_of/bin/python -c "
from pathlib import Path
from omnidriver.openfoam.apply_overrides import apply_overrides
apply_overrides([], case_root=Path('/tmp'))"
```
(Build `/tmp/od_of` with core + openfoam only.) Expected:
`ModuleNotFoundError: No module named 'omnidriver.cardiacfoam'`.

- [ ] **Step 2: Convert all three, same transformation as Task 5**

Make `driver_context` required. Push the requirement out to callers —
`cli.py`'s `--apply` path already holds one (Phase 1's `f51387b` put it on
`_ExecutionContext`), and `cardiacfoam/dict_builder.py` is a cardiac module that
may legitimately resolve the cardiac default.

- [ ] **Step 3: Extend the static guard to cover openfoam**

In `test_core_context_is_explicit.py`, add a second root so the guard is not
core-only. `omnidriver.openfoam` is not importable in the core-only venv, so
resolve the path from the repo rather than the module, and skip cleanly when
the directory is absent:

```python
_OPENFOAM_ROOT = (
    pathlib.Path(omnidriver.core.__file__).resolve().parents[4]
    / "omnidriver-openfoam" / "src" / "omnidriver" / "openfoam"
)
```

`parents[4]`, verified — `core/__init__.py`'s ancestors are `core`, `omnidriver`,
`src`, `omnidriver` (the package directory), `packages`. `parents[3]` lands on
`packages/omnidriver/` and silently yields a path that does not exist, which
would make the guard pass by finding nothing. Assert `_OPENFOAM_ROOT.is_dir()`
before walking it, or skip the openfoam half explicitly when it is absent — a
guard that silently checks zero files is worse than no guard, and this
repository already has one documented instance of exactly that.

- [ ] **Step 4: Verify**

Step 1's command must now raise `TypeError` for the missing required argument,
not `ModuleNotFoundError`. Then:
```bash
/tmp/od_of/bin/python -m pytest packages/omnidriver-openfoam/tests -q
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
```
Expected: openfoam suite passes with only core+openfoam installed; all-packages
0 failed.

---

### Task 7: Delete the twenty cardiac gates

`core/compatibility.py` has 20 branches on `plugin_id == "org.cardiacfoam"`. Phase 1
measured which are reachable: across the whole suite the cardiac branch was taken
by exactly one function, and Phase 1 Task 5 closed it by implementing the hook.
`test_no_cardiac_gate_is_reached.py` is the standing proof.

**Do this last.** Before Tasks 3, 5 and 6 land, some of these are load-bearing.

**Files:**
- `packages/omnidriver/src/omnidriver/core/compatibility.py`
- `scripts/check-import-boundaries.py`
- `packages/omnidriver/tests/core/test_capability_fallback_neutrality.py` (docstring counts)

- [ ] **Step 1: Re-run the census with every hook now implemented**

```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py -v
```
Expected: passes. If it does not, **stop** — a gate is still reachable and
deleting it changes behaviour. Name it and report.

- [ ] **Step 2: Delete each gate's cardiac branch, keeping the neutral return**

For each of the 20, remove the `if getattr(plugin, "plugin_id", "") == "org.cardiacfoam":`
block and its import, leaving the neutral value. Example —
`legacy_solver_commands` becomes:

```python
@_instrumented
def legacy_solver_commands(plugin) -> frozenset[str]:
    """v1 plugins predate get_solver_commands(). A plugin that does not declare
    its commands gets none; authorizing a binary it never named is not a safe
    default."""

    del plugin
    return frozenset()
```

Two are different and must **keep refusing**: `legacy_route_sweep_case` and
`legacy_materialize_sweep_case` raise `SweepValidationError` naming the missing
hook, because an empty routing silently produces a case that is not the one the
sweep asked for. Delete only their cardiac branch; keep the `raise`.

Two more are ungated already and are **not** part of this set:
`legacy_default_driver_context` and `legacy_generic_case_mutation` still import
cardiacfoam unconditionally. They serve the public compatibility edge Task 5
deliberately preserved. Leave them, and say so in your report.

- [ ] **Step 3: Tighten the boundary gate**

In `scripts/check-import-boundaries.py`, `compatibility.py` is currently exempt
from both sibling prefixes. Narrow it to openfoam only:

```python
    for path in CORE_SRC.rglob("*.py"):
        if path == COMPATIBILITY_FILE:
            # Still exempt for omnidriver.openfoam: the ungated environment
            # fallbacks are a documented, overridable default
            # (future/ENVIRONMENT_CONTRACT.md §4). NOT exempt for
            # omnidriver.cardiacfoam any more -- after Phase 2 the only cardiac
            # imports left serve the public compatibility edge, and any new one
            # is a regression.
            forbidden = ("foamlib",)
        else:
            forbidden = ("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam")
```

`legacy_default_driver_context` and `legacy_generic_case_mutation` will now be
flagged. Add exactly those two to `KNOWN_VIOLATIONS` with a comment naming why
they are permanent-for-now rather than debt. The list is shrink-only, so the
gate fails if either stops matching — which is what you want.

- [ ] **Step 4: Verify G5 and everything else**

```bash
grep -c 'org.cardiacfoam' packages/omnidriver/src/omnidriver/core/compatibility.py
/tmp/od_all/bin/python scripts/check-import-boundaries.py; echo "exit=$?"
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
```
Expected: `0` occurrences (G5); gate exit 0 with exactly two waivers;
all-packages 0 failed; core-only 0 failed.

`test_no_cardiac_gate_is_reached.py` asserts the gate set is exactly 20 — that
assertion now reads 0. Update it to assert **zero** gated fallbacks exist,
keeping the second test as the standing behavioural check. Say in your report
that you inverted it, and why.

---

## Phase 2 exit criteria

- [ ] `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"` → **0 failed** *(G3)*
- [ ] `cd /tmp && /tmp/od_core/bin/python -m omnidriver --help && … list && … plugins` → all exit 0 *(G4)*
- [ ] `grep -rc 'org.cardiacfoam' packages/omnidriver/src` → **0** *(G5)*
- [ ] `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"` → **0 failed**
- [ ] `test_core_context_is_explicit.py` passes over `core/` **and** `openfoam/`
- [ ] `test_fallback_census.py` passes — zero implicit resolutions under an explicit context
- [ ] `python3 scripts/check-import-boundaries.py` → exit 0, `compatibility.py` no longer exempt from the cardiac prefix, exactly two named waivers
- [ ] `pytest …/test_wheel_install_imports.py -m slow` → passes with an **empty** `KNOWN_UNIMPORTABLE`
- [ ] A plugin declaring non-cardiac phases gets its own phases from `primary_phase()`, and an entry claiming an undeclared phase produces an **error**, not a skip
- [ ] `scripts/export-capability-seams.py --check` → up to date

Explicitly **not** expected to change in Phase 2, and each is Phase 3: the
trust boundary (`CASE_SCRIPT_COMMANDS`, `CORE_NEUTRAL_COMMANDS`,
`_is_installed_openfoam_app`), `ArtifactFormat`'s closed enum, the
`processor*` glob, the `GenericOpenFOAMPlugin` → `GenericEnvironmentPlugin`
rename, the unused `numpy`/`gmsh` dependencies, the missing `LICENSE`, and the
false claims in `packages/omnidriver/README.md`.

## Suggested execution split

Tasks 1–4 are independent of each other and of 5; 5 → 6 → 7 is a chain.

| wave | tasks | notes |
|---|---|---|
| 1 | 1, 2, 3, 4 in parallel | disjoint file sets. **Create worktrees from this branch's tip, not `main`** — Phase 1 lost that check and three agents branched from a commit without the plan file in it |
| 2 | 5 | solo, in the main tree. The judgement-heavy one: which sites genuinely need a context and which are pass-throughs |
| 3 | 6, then 7 | 7 must go last; its safety proof is the census, which needs 3, 5 and 6 landed |

Task 3 touches `compatibility.py` (adding `legacy_phases`) and Task 7 rewrites
it. Sequencing 3 in wave 1 and 7 in wave 3 keeps them apart.

## Related

- [`future/ENVIRONMENT_CONTRACT.md`](../../../future/ENVIRONMENT_CONTRACT.md) — §4's rule, and §5b's deferral of the trust boundary
- [`2026-08-27-core-completion.md`](2026-08-27-core-completion.md) — Phase 1, landed
- `GITHUB_MIGRATION.md` §3 — the round-2 scope this plan closes
- The legacy tree at `noFrontendCardiacFoam/applications/scripts/driverFoam` — Tasks 3, 5 and 7 are ports of work already validated there
