# Core Generality Implementation Plan (topic A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace core's OpenFOAM-shaped concepts with the smallest general forms that serve both an OpenFOAM stack and openCARP:
- an opaque `environment_source` instead of a sourced `bashrc`;
- plugin-declared instance and replica directories instead of time and `processor*` directories;
- a plugin-owned provenance hook instead of core knowing "start time";
- optional dictionary members instead of required stubs;
- core declaring its own run records;
- no cardiac names, and no exemption by name, in core.

**Architecture:**
- Every change is a rename or a relocation. The old name is deleted in the same commit, in every package and test. There are no shims.
- The work runs as three parallel tracks (A6+A7, A5, A3), then A1 alone, then A2 alone. A2 is split into three sequenced tasks, each green.
- Two new proofs are added:
  - conformance check **C11**: restaging a case a run has written carries nothing that run wrote;
  - a native proof that the plugin hook covers every case the deleted name rule exempted.

**Tech Stack:** Python ≥ 3.11, pytest, uv, foamlib (cardiacfoam and openfoam only), openCARP v18.1 (`openCARP`, `mesher`).

**Spec:** `docs/superpowers/specs/2026-09-26-core-generality-design.md`.
**Code map:** `.superpowers/sdd/map-A.md`. It was made at `3c6b615`; this plan re-verified every symbol against `main` at `fd21fe7`.
**Previous plan (format and binding rules):** `docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md`.

## Global Constraints

- Python floor 3.11; CI matrixes 3.11/3.12/3.13.
- Core names no solver or physics:
  - `scripts/check-import-boundaries.py` keeps an empty waiver list;
  - `scripts/check-core-shape.py` accepts no new token.
  - The shape baseline (`scripts/core-shape-baseline.txt`) is **edited down by hand in the commit that pays the debt**. `--write-baseline` is never used to hide growth.
- **No skips.** A check that cannot run is a failure that names why. `native` and `native_opencarp` tests **fail, not skip**, when their environment variable is unset. Never weaken a guard or add a skip to make a task pass.
- **No fallbacks, no shims, no aliases.** Every rename deletes the old name in the same commit, across every package, test plugin and test.
  - "The old name" means the renamed symbol. Each task ends with a grep gate that lists exactly what, if anything, may still match.
- **Supplied, never discovered** (`future/ENVIRONMENT_CONTRACT.md` §12):
  - native trees come from `OMNIDRIVER_NATIVE_TUTORIALS` (cardiacFOAM) and `OMNIDRIVER_OPENCARP_TUTORIALS` (openCARP);
  - openCARP's library path comes from the ambient `DYLD_LIBRARY_PATH`;
  - the scratch root is always supplied. Tests pass `scratch_root=`/`--scratch-dir`, or set `OMNIDRIVER_SCRATCH_DIR` in a child env dict, never in `os.environ`.
- Evaluate defaults lazily (CLAUDE.md). Name a symbol rather than a line number.
- Correct a docstring, comment or document claim **with a date**. Never overwrite it silently.
- Claims about openCARP come from the real binary. Every probe goes into `docs/solver-learning/opencarp.md` as command, observed output and conclusion.
- The native tree is never written. Every run works in a staged copy under a scratch directory.
- Never hand-build an `omnidriver run` command: use `core.runtime.run_command.omnidriver_run_command(ctx, *args)`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Working beside the tutorial stream.** These core files are shared ground: `tutorial_records.py`, `record_execution.py`, `registry.py`, `sweep_runner.py`, `strict_planning.py`, `plugin_capabilities.py`, `case_transaction.py`. Every task that touches one:
  - lands on `main` as **its own small commit**;
  - adds **a generality-log row** to `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5, with stream `core generality (A)` and the row text the task gives;
  - lands by fast-forward only (`git -C /Users/simaocastro/omnidriver merge --ff-only <branch>`). Never force; nothing goes to `origin` without the owner's go-ahead.
  
  The tutorial stream rebases on these commits.
- **One venv set per worktree** (memory: a shared venv imports another checkout and gives a false green). With `W` the worktree root and `N` its name:
  ```bash
  uv venv --python 3.11 /tmp/odA-$N && VIRTUAL_ENV=/tmp/odA-$N uv pip install -q \
    -e "$W/packages/omnidriver[post]" -e $W/packages/omnidriver-openfoam \
    -e $W/packages/omnidriver-cardiacfoam -e $W/packages/omnidriver-cardiaccore \
    -e $W/packages/omnidriver-opencarp pytest build
  uv venv --python 3.11 /tmp/odAcore-$N && VIRTUAL_ENV=/tmp/odAcore-$N uv pip install -q \
    -e "$W/packages/omnidriver[post]" pytest
  /tmp/odA-$N/bin/python -c "import omnidriver.core, pathlib; print(pathlib.Path(omnidriver.core.__file__).resolve())"
  ```
  Expected: the printed path is inside `$W`. If it is not, stop: every result from that venv is a false green.
- **The verification shapes.** Run them before any commit that claims "done". The durable claim is **0 failed**; never quote totals.
  ```bash
  # V1 all packages
  /tmp/odA-$N/bin/python -m pytest $W/packages/ -q -m "not slow and not native and not native_opencarp"
  # V2 core alone
  /tmp/odAcore-$N/bin/python -m pytest $W/packages/omnidriver/tests -q
  # V3 installed wheel (rebuild after every source change)
  rm -rf /tmp/odAwheel-$N && mkdir -p /tmp/odAwheel-$N
  /tmp/odA-$N/bin/python -m build -q --outdir /tmp/odAwheel-$N/dist $W/packages/omnidriver
  uv venv --python 3.11 /tmp/odAwheel-$N/env
  VIRTUAL_ENV=/tmp/odAwheel-$N/env uv pip install -q "$(ls /tmp/odAwheel-$N/dist/omnidriver-*.whl)[post]" pytest
  (cd $W && /tmp/odAwheel-$N/env/bin/python scripts/check-wheel-artifact.py)
  (cd $W && /tmp/odAwheel-$N/env/bin/python -m pytest packages/omnidriver/tests -q)
  # V4 native cardiacFOAM
  OMNIDRIVER_NATIVE_TUTORIALS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials \
    /tmp/odA-$N/bin/python -m pytest $W/packages/ -q -m native
  # V5 native openCARP
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odA-$N/bin/python -m pytest $W/packages/omnidriver-opencarp/tests -q -m native_opencarp
  # V6 static gates (each must exit 0; check-core-shape prints nothing)
  (cd $W && /tmp/odA-$N/bin/python scripts/check-import-boundaries.py \
    && /tmp/odA-$N/bin/python scripts/export-capability-seams.py --check \
    && /tmp/odA-$N/bin/python scripts/check-case-writes.py \
    && /tmp/odA-$N/bin/python scripts/check-core-shape.py)
  ```
  Expected: V1–V5 end in a summary with `passed` and no `failed` and no `error`; V6 exits 0.
- **Reviews** (spec §5). An Opus reviewer is dispatched (Agent tool, `model: "opus"`) at three points:
  - Checkpoint R1, after the parallel tracks;
  - Checkpoint R2, after A2;
  - a final whole-topic review (Task 9).
  
  The implementers use Sonnet (memory: subagent model choice). Don't stop between batches.

## Spec items and where they land

| spec item | task |
|---|---|
| §2/§3 A6: cardiac names out of core (`get_heterogeneity_models`, `get_electro_property_entry_groups`, `cardiacfoam_monorepo_root`, CLI help) | Task 1 |
| §2/§3 A7: delete the name heuristic after proving the hook covers it; rename `SKIP_MESH_DIAGNOSTICS` | Task 2 |
| §2/§3 A5: `CORE_RUNTIME_RECORDS`, `with_core_runtime_records`, merged in `_CaseRuntimeConventionsAdapter.conventions`; record staging excludes `produces` | Task 3 |
| §4: the staging-leak check (new C11) | Task 3 |
| §2/§3 A3: four members optional-neutral; empty fallbacks in adapters, merges and identity; a stable "none" digest; stubs deleted; `get_tutorial_catalog` stays required | Task 4 |
| §4: A3's "a plugin that implements none of the four loads, composes, describes and runs" | Task 4 |
| §2/§3 A1: `environment_source` / `--environment-source`, opaque to core, removed from `generic_case` | Task 5 |
| §4: the baseline loses all `bashrc` lines | Task 5 |
| §2/§3 A2: instance directories and `{instance}` | Task 6 (A2a) |
| §2/§3 A2: replica directories | Task 7 (A2b) |
| §2/§3 A2: provenance hook `input_roots`; core stops knowing "start time" | Task 8 (A2c) |
| §4: the baseline loses the `processor` hits | Task 7 |
| §4: A2's vocabulary-only tests, and "a stack that declares none behaves as openCARP does" | Tasks 6–8 |
| §4: C1–C10 (now C1–C11) pass for the toy and openCARP; cardiacFOAM native 0 failed | V1, V4, V5 in every task |
| §5: order, parallelism, Opus reviews | the order table below; R1, R2, Task 9 |
| §3 "later" (A4, Task 15's OpenFOAM half) | not done here. Task 3 records that Task 15's core half is done |

## Order and parallelism

| phase | tasks | worktree | runs beside |
|---|---|---|---|
| 1 | Task 1 (A6), then Task 2 (A7) | `core-gen-p1` | Tasks 3 and 4 |
| 1 | Task 3 (A5) | `core-gen-p2` | Tasks 1–2 and 4 |
| 1 | Task 4 (A3) | `core-gen-p3` | Tasks 1–3 |
| — | Checkpoint R1 | — | nothing |
| 2 | Task 5 (A1) | `core-gen-a1` | nothing (it touches every package) |
| 3 | Tasks 6, 7, 8 (A2a, A2b, A2c), in order | `core-gen-a2` | nothing |
| — | Checkpoint R2, then Task 9 | — | nothing |

**Where the parallel tracks overlap.** Their files are disjoint except in two places:
- `core/plugin_capabilities.py`, at separate hunks:
  - Task 1: `CapabilityManifestCapability`'s `:consumed-by:`;
  - Task 3: `_CaseRuntimeConventionsAdapter`;
  - Task 4: `TutorialCatalogCapability` and `DictionaryCatalogCapability` and their adapters.
- The generated seam table in `ARCHITECTURE.md` (Tasks 1 and 4).

Land them in the order they finish. The later task rebases on `main`. On a conflict in `ARCHITECTURE.md`'s generated table, take either side, run `/tmp/odA-$N/bin/python scripts/export-capability-seams.py`, and amend. Then rerun V1–V6.

## File structure

```
packages/omnidriver/src/omnidriver/
  core/runtime_records.py            CREATE (T3): CORE_RUNTIME_RECORDS, with_core_runtime_records
  conformance/checks.py              MODIFY (T3): C11 check_restage_is_clean
  dict_entries.py                    MODIFY (T1): keeps only all_documented_driver_paths
  core/specs/paths.py                MODIFY (T1): cardiacfoam_monorepo_root deleted
  cli.py                             MODIFY (T1 help; T5 --environment-source; T6 reconciler call)
  core/strict_planning.py            MODIFY (T2 _mesh_geometry_exempt; T5 environment_source)
  core/runtime/strict_audit.py       MODIFY (T2): SKIP_GEOMETRY_DIAGNOSTICS_ENV
  core/plugin_capabilities.py        MODIFY (T1, T3, T4, T5, T6, T7, T8)
  core/plugin_interface.py           MODIFY (T4, T5, T8)
  core/provider_stack.py             MODIFY (T8): get_input_roots replaces get_selected_start_time
  core/compatibility.py              MODIFY (T4 legacy_phases; T5 legacy shims)
  core/plugin_profile.py             MODIFY (T7): replica_directory_globs, is_replica_directory_name
  core/runtime/attempt_lease.py      MODIFY (T3): ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME
  core/runtime/record_execution.py   MODIFY (T3): record_generated_relpaths, _stage
  core/runtime/sweep_runner.py       MODIFY (T3 excluded_relpaths; T6 instances; T7 replicas)
  core/runtime/generic_case.py       MODIFY (T5): explicit_bashrc removed
  core/runtime/models.py             MODIFY (T6): instance_indexed, {instance}
  core/runtime/reconciler.py         MODIFY (T6): declared_instance_names, instance_names
  core/runtime/workflow_runner.py    MODIFY (T6, T7)
  core/runtime/registry.py           MODIFY (T7)
  core/runtime/provenance_inputs.py  MODIFY (T7, T8)
  core/runtime/artifacts.py, core/runtime/resume.py, core/utility_catalog.py, core/tutorial_records.py (docstring)   MODIFY (T6)
  schemas/run-document.json          MODIFY (T6); also the repo-root copy schemas/run-document.json
packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/
  dict_entries.py                    CREATE (T1): the two moved functions
  monorepo.py                        CREATE (T1): cardiacfoam_monorepo_root
  planning_policy.py                 MODIFY (T2): region-split electroProperties
  artifacts_predictor.py, utilities/*/utility.manifest.toml   MODIFY (T6)
  case_provenance.py, cardiacfoam_plugin.py, plugin.yaml (comment), run_document_config.py (docstring)   MODIFY (T5, T8)
packages/omnidriver-openfoam/src/omnidriver/openfoam/
  case_runtime_conventions.py        MODIFY (T6, T7)
  environment.py                     MODIFY (T4 stubs deleted; T5; T8 get_input_roots)
  openfoam_environment.py, environment_preflight.py   MODIFY (T5): bashrc_path
packages/omnidriver-opencarp/src/omnidriver/opencarp/
  plugin.py                          MODIFY (T4 stubs deleted; T5)
  records/niederer_n_version.py      MODIFY (T3): complete produces (F15)
scripts/  check-wheel-artifact.py, export-dict-catalog.py, scan-dict-keys.py, regenerate-ionic-catalog.py (T1);
          export-tutorials-catalog.py (T4); export-utility-catalog.py (T6); core-shape-baseline.txt (T5, T7)
```

---

### Task 1: A6, cardiac names out of core

**Worktree:** `core-gen-p1`. **Parallel with:** Tasks 3 and 4.
**Shared core file touched:** `plugin_capabilities.py` (one docstring field). So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Files:**
- Create:
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_entries.py`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/monorepo.py`
  - `packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py`
- Modify, core:
  - `packages/omnidriver/src/omnidriver/dict_entries.py`
  - `packages/omnidriver/src/omnidriver/core/specs/paths.py` (delete `cardiacfoam_monorepo_root`)
  - `packages/omnidriver/src/omnidriver/cli.py` (`build_parser`: `--plugin`, `--dry-run` and `--config` help)
  - `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` (`CapabilityManifestCapability` `:consumed-by:`)
  - `ARCHITECTURE.md` (regenerated)
- Modify, callers in `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/`: `dict_builder.py`, `validation.py`, `rtst_scanner.py`.
- Modify, cardiacfoam tests: `test_validation.py`, `test_ionic_heterogeneity.py`, `test_dict_entries_catalog.py`, `test_source_refs_exist.py`, `test_remediation_catalog_addressability.py`.
- Modify, scripts: `export-dict-catalog.py`, `check-wheel-artifact.py`, `scan-dict-keys.py`, `regenerate-ionic-catalog.py`.
- Modify, conftests: `packages/omnidriver/tests/conftest.py`, `packages/omnidriver-openfoam/tests/conftest.py`, `packages/omnidriver-cardiacfoam/tests/conftest.py`.
- Modify: `packages/omnidriver/tests/core/test_core_context_is_explicit.py` (`_CONTEXT_TAKING_PUBLIC_EDGE`, `_ROOT_INVENTING`).

**Interfaces:**
- Produces:
  - `omnidriver.cardiacfoam.dict_entries.get_heterogeneity_models(driver_context=None) -> tuple[str, ...]`;
  - `omnidriver.cardiacfoam.dict_entries.get_electro_property_entry_groups(driver_context=None) -> dict[str, tuple[DictEntry, ...]]`;
  - `omnidriver.cardiacfoam.monorepo.cardiacfoam_monorepo_root(start: Path | None = None) -> Path | None`.
  
  All three have bodies unchanged. `omnidriver.dict_entries` keeps `all_documented_driver_paths`, and its re-exports `DictEntry` and `build_group`.
- Produces for Task 5: `_SOLVER_WORDS` in `test_core_carries_no_cardiac_names.py`, which Task 5 extends with `"bashrc"`.

- [ ] **Step 1: Set up the worktree and venvs** (Global Constraints). Use `N=core-gen-p1`, on branch `core-gen-p1` from `main`.

- [ ] **Step 2: Write the failing test**

  `packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py`:
  ```python
  """Core carries no cardiac or solver name (spec 2026-09-26-core-generality-design.md §2, A6)."""
  from __future__ import annotations

  import importlib

  import pytest

  from omnidriver.cli import build_parser

  _MOVED_OUT = (
      ("omnidriver.dict_entries", "get_heterogeneity_models"),
      ("omnidriver.dict_entries", "get_electro_property_entry_groups"),
      ("omnidriver.core.specs.paths", "cardiacfoam_monorepo_root"),
  )


  @pytest.mark.parametrize(("module", "name"), _MOVED_OUT)
  def test_a_cardiac_symbol_is_not_defined_in_core(module, name):
      assert not hasattr(importlib.import_module(module), name), (
          f"{module}.{name} is cardiac vocabulary; it lives in omnidriver-cardiacfoam"
      )


  def test_the_neutral_dictionary_view_stays_in_core():
      from omnidriver.dict_entries import all_documented_driver_paths

      assert callable(all_documented_driver_paths)


  #: Solver and tutorial names the CLI help used to carry. Task 5 (A1) adds
  #: "bashrc" when --environment-bashrc is renamed.
  _SOLVER_WORDS = (
      "OpenFOAM", "openfoam", "cardiac", "singleCell", "niederer", "manufactured",
      "restitutionCurves", "genericCase", "randomCase",
  )


  def test_cli_help_names_no_solver_or_tutorial():
      help_text = build_parser().format_help()
      assert [word for word in _SOLVER_WORDS if word in help_text] == []
  ```

- [ ] **Step 3: Run it to verify it fails**

  Run: `/tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py -v`
  
  Expected:
  - the three `test_a_cardiac_symbol_is_not_defined_in_core` cases FAIL;
  - `test_cli_help_names_no_solver_or_tutorial` FAILs listing `['OpenFOAM', 'singleCell', 'niederer', 'manufactured', 'restitutionCurves', 'genericCase', 'randomCase']`;
  - `test_the_neutral_dictionary_view_stays_in_core` PASSes.

- [ ] **Step 4: Move the two dictionary functions**

  Create `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_entries.py`:
  ```python
  """cardiacFOAM's own views of its dictionary vocabulary.

  Moved from core's ``omnidriver.dict_entries`` 2026-09-26 (spec
  2026-09-26-core-generality-design.md §2, A6). A list of
  ionic-heterogeneity models and the electroProperties groupings are cardiac
  vocabulary, and core names none. The bodies are unchanged.
  ``all_documented_driver_paths`` stays in core: it is solver-neutral.
  """
  from __future__ import annotations

  from typing import TYPE_CHECKING

  from omnidriver.core.contracts.dictionary import DictEntry

  if TYPE_CHECKING:
      from omnidriver.core.plugin_interface import DriverContext


  def get_heterogeneity_models(
      driver_context: "DriverContext | None" = None,
  ) -> tuple[str, ...]:
      """Ionic models that implement transmural tissue heterogeneity
      (configureIonicHeterogeneity, endo/M/epi blend and/or namedRegions) on
      CPU and/or GPU, as the stack's capability manifest declares them."""
      from omnidriver.core.compatibility import resolve_public_driver_context

      driver_context = resolve_public_driver_context(driver_context)
      return driver_context.capabilities.manifest.manifest().get("heterogeneity_models", ())


  def get_electro_property_entry_groups(
      driver_context: "DriverContext | None" = None,
  ) -> dict[str, tuple[DictEntry, ...]]:
      """The stack's dictionary entries, grouped by cardiacFOAM's own group names."""
      from omnidriver.core.compatibility import resolve_public_driver_context

      driver_context = resolve_public_driver_context(driver_context)
      return driver_context.capabilities.dictionaries.groups()
  ```

  Replace the whole of `packages/omnidriver/src/omnidriver/dict_entries.py` with:
  ```python
  """Core's solver-neutral view of the stack's dictionary vocabulary.

  Corrected 2026-09-26 (spec 2026-09-26-core-generality-design.md §2, A6):
  ``get_heterogeneity_models`` and ``get_electro_property_entry_groups``
  lived here. They are cardiac vocabulary and moved to
  ``omnidriver.cardiacfoam.dict_entries``. ``DictEntry`` and ``build_group``
  stay re-exported for existing importers.
  """
  from __future__ import annotations

  from typing import TYPE_CHECKING
  from .core.contracts.dictionary import DictEntry, build_group
  if TYPE_CHECKING:
      from omnidriver.core.plugin_interface import DriverContext

  __all__ = ["DictEntry", "all_documented_driver_paths", "build_group"]


  def all_documented_driver_paths(
      driver_context: "DriverContext | None" = None,
  ) -> tuple[str, ...]:
      from omnidriver.core.compatibility import resolve_public_driver_context

      driver_context = resolve_public_driver_context(driver_context)
      paths = [
          entry.driver_path
          for entry in driver_context.capabilities.dictionaries.entries()
      ]
      return tuple(dict.fromkeys(paths))
  ```

  Update every importer. In each file, replace the import shown on the left with the one on the right; every other line stays as it is.

  | file | old import | new import |
  |---|---|---|
  | `cardiacfoam/dict_builder.py` (top) | `from omnidriver.dict_entries import (DictEntry, get_electro_property_entry_groups,)` | `from omnidriver.dict_entries import DictEntry` and `from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups` |
  | `cardiacfoam/dict_builder.py` (inside the heterogeneity block) | `from omnidriver.dict_entries import get_heterogeneity_models` | `from omnidriver.cardiacfoam.dict_entries import get_heterogeneity_models` |
  | `cardiacfoam/validation.py`, `cardiacfoam/rtst_scanner.py` | `from omnidriver.dict_entries import get_electro_property_entry_groups` | `from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups` |
  | cardiacfoam tests `test_validation.py` (both sites), `test_ionic_heterogeneity.py`, `test_source_refs_exist.py`, `test_remediation_catalog_addressability.py` | same as the row above | same as the row above |
  | cardiacfoam `test_dict_entries_catalog.py` | `from omnidriver.dict_entries import (get_electro_property_entry_groups, all_documented_driver_paths,)` | `from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups` and `from omnidriver.dict_entries import all_documented_driver_paths` |
  | `scripts/export-dict-catalog.py` | `from omnidriver.dict_entries import get_electro_property_entry_groups` | `from omnidriver.cardiacfoam.dict_entries import get_electro_property_entry_groups` |

  In `scripts/check-wheel-artifact.py`, replace check 3's `try` block with the neutral public edge:
  ```python
      try:
          from omnidriver.dict_entries import all_documented_driver_paths

          all_documented_driver_paths()
      except LookupError as exc:
          print(f"public edge without context : {type(exc).__name__}: {exc}")
      except Exception as exc:  # noqa: BLE001
          failures.append(f"all_documented_driver_paths() raised {type(exc).__name__}, not LookupError: {exc}")
      else:
          failures.append("all_documented_driver_paths() unexpectedly answered without an adapter")
  ```

  In `CapabilityManifestCapability`'s docstring (`core/plugin_capabilities.py`), change `:consumed-by: omnidriver/dict_entries.py, omnidriver/core/introspection.py, omnidriver/core/strict_planning.py` to:
  ```
      :consumed-by: omnidriver/cardiacfoam/dict_entries.py, omnidriver/core/introspection.py, omnidriver/core/strict_planning.py
  ```
  
  In `test_core_context_is_explicit.py`, replace `_CONTEXT_TAKING_PUBLIC_EDGE` with:
  ```python
  # Corrected 2026-09-26 (spec 2026-09-26 A6): get_heterogeneity_models and
  # get_electro_property_entry_groups were listed here; they moved to
  # omnidriver.cardiacfoam.dict_entries, so core has none of theirs to call.
  _CONTEXT_TAKING_PUBLIC_EDGE = {
      "materialize_case": "omnidriver.sweep_materialize",
      "route_case_values": "omnidriver.sweep_routing",
      "all_documented_driver_paths": "omnidriver.dict_entries",
  }
  ```

- [ ] **Step 5: Move `cardiacfoam_monorepo_root`**

  Create `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/monorepo.py`:
  ```python
  """Where the cardiacFoam monorepo is, when this checkout sits inside one.

  Moved from core's ``core.specs.paths`` 2026-09-26 (spec
  2026-09-26-core-generality-design.md §2, A6). Its only users are cardiac
  scripts and tests; shipped core names no solver. Body unchanged.
  """
  from __future__ import annotations

  from pathlib import Path


  def cardiacfoam_monorepo_root(start: Path | None = None) -> Path | None:
      """Walk parent directories looking for the full cardiacFoam monorepo root.

      Returns the first ancestor of ``start`` (default: this file) that has
      both ``tutorials/`` and ``applications/`` siblings, or ``None`` in a
      standalone checkout (the normal case)."""
      current = (start or Path(__file__)).resolve()
      for parent in current.parents:
          if (parent / "tutorials").exists() and (parent / "applications").exists():
              return parent
      return None
  ```

  Delete `cardiacfoam_monorepo_root` from `packages/omnidriver/src/omnidriver/core/specs/paths.py` (the whole function).

  In `test_core_context_is_explicit.py`, replace the `_ROOT_INVENTING` line with:
  ```python
  # Corrected 2026-09-26 (spec A6): cardiacfoam_monorepo_root was listed here;
  # it moved to omnidriver.cardiacfoam.monorepo, so core cannot call it.
  _ROOT_INVENTING = {"repo_root_default"}
  ```

  `packages/omnidriver-cardiacfoam/tests/conftest.py`: replace `from omnidriver.core.specs.paths import cardiacfoam_monorepo_root` with `from omnidriver.cardiacfoam.monorepo import cardiacfoam_monorepo_root`.

  `scripts/scan-dict-keys.py` and `scripts/regenerate-ionic-catalog.py`: replace `from omnidriver.core.specs.paths import cardiacfoam_monorepo_root, repo_root_default` with these two lines:
  ```python
  from omnidriver.cardiacfoam.monorepo import cardiacfoam_monorepo_root
  from omnidriver.core.specs.paths import repo_root_default
  ```

  Core's and openfoam's conftests cannot import `omnidriver-cardiacfoam`: the core-alone shape has no such package, and openfoam must not know cardiology. Each gets a test-local walk.
  - In `packages/omnidriver/tests/conftest.py`:
    - change the import to `from omnidriver.core.specs.paths import repo_root_default`;
    - replace the `monorepo_root` assignment and its comment block with the code below.
  - In `packages/omnidriver-openfoam/tests/conftest.py`:
    - delete the `cardiacfoam_monorepo_root` import;
    - replace the assignment and its comment the same way.
  ```python
  def _cardiacfoam_monorepo_root() -> Path | None:
      """The cardiacFoam monorepo this repository was extracted from, if this
      checkout sits inside one: the first ancestor holding both ``tutorials/``
      and ``applications/``. Test-local since 2026-09-26 (spec A6): shipped
      core names no solver, and this package's tests cannot import
      omnidriver-cardiacfoam's copy (``omnidriver.cardiacfoam.monorepo``)."""
      for parent in Path(__file__).resolve().parents:
          if (parent / "tutorials").exists() and (parent / "applications").exists():
              return parent
      return None


  #: The monorepo root resolved once at collection time.  ``None`` in standalone.
  monorepo_root: Path | None = _cardiacfoam_monorepo_root()
  ```

- [ ] **Step 6: Scrub the CLI help** (`cli.build_parser`)

  - `--plugin`: replace `"with whatever it requires (e.g. an OpenFOAM environment "` `"adapter); explicit selection ..."` with `"with whatever it requires (e.g. an environment adapter it names "` `"in requires:); explicit selection ..."`. Leave the rest of the string unchanged.
  - `--dry-run`: `help="Plan and print simulation cases without running the solver."`.
  - `--config`:
    ```python
        help=(
            "Path to JSON file with make_spec overrides: either a top-level map "
            "keyed by entry name (the names `describe` lists for the selected "
            "plugin) or a direct parameter object for the selected entry."
        ),
    ```

- [ ] **Step 7: Regenerate the seam table and run the tests**

  ```bash
  cd $W && /tmp/odA-core-gen-p1/bin/python scripts/export-capability-seams.py
  /tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py $W/packages/omnidriver/tests/core/test_core_context_is_explicit.py $W/packages/omnidriver/tests/core/test_capability_seam_documentation.py -v
  grep -rn "cardiacfoam_monorepo_root\|get_heterogeneity_models\|get_electro_property_entry_groups" $W/packages/omnidriver/src $W/packages/omnidriver-openfoam $W/scripts/check-wheel-artifact.py | grep -v /build/
  ```
  Expected:
  - every test passes;
  - the grep prints nothing (the `build/` trees are stale build output and are ignored).

- [ ] **Step 8: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0.
  
  Append this row to the generality log (§5):
  ```
  | 2026-09-26 | core generality (A) | A6: `get_heterogeneity_models`, `get_electro_property_entry_groups` move to `omnidriver.cardiacfoam.dict_entries`, and `cardiacfoam_monorepo_root` to `omnidriver.cardiacfoam.monorepo` (core and openfoam conftests keep a test-local walk); CLI help names no solver or tutorial; `check-wheel-artifact.py` probes `all_documented_driver_paths` | core carried cardiac vocabulary with no core caller | neutral: guarded by `test_core_carries_no_cardiac_names.py` |
  ```
  ```bash
  git -C $W add -A packages scripts ARCHITECTURE.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: cardiac names leave core (A6)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 2: A7, the name heuristic

**Worktree:** `core-gen-p1`, after Task 1. **Parallel with:** Tasks 3 and 4.
**Shared core file touched:** `strict_planning.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Evidence gathered while planning (2026-09-26, `main` at `fd21fe7`, the native tree above).** For each registered cardiacfoam tutorial and record, the old name rule was compared with the plugin hook. Everything the rule exempts, the hook exempts too, except **`manufacturedMonodomainTotalLagrangianEM`**:
- the rule exempts it;
- `planning_policy.is_nondimensional_case` does not, because it reads only `constant/electroProperties`.

That case is region-split. Its `constant/electroMechanicalProperties` says `sequentialElectroMechanicalCoeffs { electroRegion electro; }`, and `constant/electro/electroProperties` declares `verificationModel { type manufacturedFDAMonodomainVerifier; }`.

So the hook is taught to read the electro region that the case itself declares. The electromechanical case keeps the exemption it has today; this task does not make that case plan. The EM warning in `AGENT_GUIDE.md` still stands.

**Amended 2026-09-26 (owner, before execution).** The region is not read by a one-off lookup inside the hook. It comes from a small **physics layout table**, `cardiacfoam/physics_layout.json`: one row per `constant/physicsProperties` `type`, saying which region roles that type has and which entry of which document names each role's region. The table never copies the region names (all three native EM cases use `electro`/`solid`, but the case owns that fact). FSI later is one more row. This task uses the table only in the hook; making electromechanics plan is a later topic, settled by a real EM run. A native drift test checks every native case's physics type is in the table and every region it resolves exists.

**Files:**
- Create:
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.json`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.py`
  - `packages/omnidriver-cardiacfoam/tests/test_physics_layout_native.py`
  - `packages/omnidriver-cardiacfoam/tests/test_nondimensional_hook_covers_the_name_rule_native.py`
  - `packages/omnidriver/tests/core/test_mesh_geometry_exemption.py`
- Modify: `packages/omnidriver-cardiacfoam/pyproject.toml` (package-data gains `physics_layout.json`)
- Modify:
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/planning_policy.py`
  - `packages/omnidriver/src/omnidriver/core/strict_planning.py` (`_is_nondimensional_entry` deleted; `_mesh_geometry_exempt` added; `_mesh_geometry_diagnostics`; the call site in `_strict_plan_for_spec`)
  - `packages/omnidriver/src/omnidriver/core/runtime/strict_audit.py` (`SKIP_GEOMETRY_DIAGNOSTICS_ENV`)
  - tests: `test_describe_write_surface.py`, `test_generic_plan_has_no_cardiac_semantics.py`, `test_coverage_is_evidence.py` (the docstring)

**Interfaces:**
- Produces:
  - `strict_planning._mesh_geometry_exempt(spec, driver_context) -> bool`;
  - `strict_audit.SKIP_GEOMETRY_DIAGNOSTICS_ENV = "SKIP_GEOMETRY_DIAGNOSTICS"`;
  - `physics_layout.region_document(case_root: Path, role: str, name: str) -> Path | None` (`constant/<region>/<name>` for a region-split type, `constant/<name>` for a single-region one, `None` when the type has no such role);
  - `physics_layout.physics_type(case_root: Path) -> str` and `PhysicsLayoutError` (an unknown type is refused by name).

- [ ] **Step 1: Write the native proof test first**

  `packages/omnidriver-cardiacfoam/tests/test_nondimensional_hook_covers_the_name_rule_native.py`:
  ```python
  """Every case the old name rule exempted is exempted by the plugin hook.

  spec 2026-09-26-core-generality-design.md §2, A7.
  ``strict_planning._is_nondimensional_entry`` exempted a case from
  mesh-scale checks when its entry name or workflow family contained
  "manufactured" or "verification". That rule is deleted. This proves that
  the plugin's own hook (``planning_policy.is_nondimensional_case``, which
  reads the case's files) exempts every case the rule did. It runs against
  the real native tree, supplied only through OMNIDRIVER_NATIVE_TUTORIALS
  and never discovered.
  """
  from __future__ import annotations

  import os
  from pathlib import Path

  import pytest

  from omnidriver.core.plugin_discovery import load_discovered_plugin
  from omnidriver.core.runtime.record_execution import record_case_spec
  from omnidriver.core.runtime.registry import list_tutorials, load_entry_spec

  pytestmark = pytest.mark.native


  def _native_tutorials_root() -> Path:
      value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
      if not value:
          pytest.fail(
              "OMNIDRIVER_NATIVE_TUTORIALS is not set. A test marked "
              "@pytest.mark.native needs the native cardiacFOAM tutorials tree "
              "supplied explicitly, e.g. OMNIDRIVER_NATIVE_TUTORIALS="
              "/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials"
          )
      return Path(value)


  def _name_rule(spec) -> bool:
      """The deleted rule, verbatim: whatever it exempted, the hook must exempt."""
      metadata = spec.metadata or {}
      haystack = (
          f"{metadata.get('entry_name', '') or ''} "
          f"{metadata.get('workflow_family', '') or ''}"
      ).lower()
      return "manufactured" in haystack or "verification" in haystack


  def test_every_case_the_name_rule_exempted_is_exempted_by_the_hook():
      root = _native_tutorials_root()
      ctx = load_discovered_plugin("cardiacfoam")
      specs = [
          load_entry_spec(name, overrides={"cases_root": str(root)}, driver_context=ctx)
          for name in list_tutorials(ctx)
      ]
      specs += [
          record_case_spec(
              record, case_id=name, staged_case_root=root / record.native_case_relpath,
              workflow_step_ids=(), command_arguments={},
          )
          for name, record in (ctx.capabilities.tutorial_records.catalog() or {}).items()
      ]
      exempted_by_name = [spec for spec in specs if _name_rule(spec)]
      assert exempted_by_name, "the name rule exempted nothing here, so this proves nothing"
      missed = sorted(
          spec.metadata["entry_name"] for spec in exempted_by_name
          if not ctx.capabilities.mesh_diagnostic_policy.is_nondimensional(spec)
      )
      assert missed == [], f"the plugin hook does not exempt {missed}, which the name rule did"
  ```

- [ ] **Step 2: Run it to verify it fails**

  Run: `OMNIDRIVER_NATIVE_TUTORIALS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials /tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver-cardiacfoam/tests/test_nondimensional_hook_covers_the_name_rule_native.py -v -m native`
  
  Expected: FAIL with `the plugin hook does not exempt ['manufacturedMonodomainTotalLagrangianEM'], which the name rule did`.
  
  If it names a different or longer list, stop. The Evidence paragraph above no longer describes the tree; report the list to the owner before changing the hook.

- [ ] **Step 3: Teach the hook the region the case declares, through the physics layout table**

  `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.json`:
  ```json
  {
    "_comment": "One row per constant/physicsProperties `type`. `regions` maps a role to the entry that names its region inside `names_in` (`{model}` is that document's own `model_key` value). A type with no `regions` is single-region: its documents sit directly under constant/ and system/. The table never copies region names; the case owns them. Added 2026-09-26 (spec 2026-09-26 A7, owner amendment).",
    "electroModel": {},
    "electroMechanicalModel": {
      "names_in": "constant/electroMechanicalProperties",
      "model_key": "electroMechanicalModel",
      "regions": {"electro": "electroRegion", "solid": "solidRegion"}
    }
  }
  ```

  `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/physics_layout.py`:
  ```python
  """Where a cardiacFoam case keeps each region's documents, as the case says.

  ``constant/physicsProperties`` names the physics ``type``. ``physics_layout.json``
  says, per type, which region roles exist and which entry names each role's
  region. A single-region type keeps its documents under ``constant/``; a
  region-split one under ``constant/<region>/``. Added 2026-09-26 (spec
  2026-09-26-core-generality-design.md A7, owner amendment): the table replaces
  a one-off lookup, so electromechanics and later FSI are one row each.
  """

  from __future__ import annotations

  import json
  from functools import cache
  from importlib.resources import files
  from pathlib import Path

  from foamlib import FoamFile


  class PhysicsLayoutError(ValueError):
      """The case names a physics type the layout table does not know."""


  @cache
  def _table() -> dict:
      raw = json.loads(files(__package__).joinpath("physics_layout.json").read_text())
      return {key: value for key, value in raw.items() if not key.startswith("_")}


  def physics_type(case_root: Path) -> str:
      return str(FoamFile(Path(case_root) / "constant" / "physicsProperties")["type"])


  def _layout(case_root: Path) -> dict:
      kind = physics_type(case_root)
      try:
          return _table()[kind]
      except KeyError:
          raise PhysicsLayoutError(
              f"physics type {kind!r} is not in physics_layout.json; add its row "
              f"(known: {sorted(_table())})"
          ) from None


  def region_of(case_root: Path, role: str) -> str | None:
      """The region the case names for ``role``; ``None`` for a single-region type."""
      layout = _layout(case_root)
      if not layout.get("regions"):
          return None
      entry = layout["regions"].get(role)
      if entry is None:
          raise PhysicsLayoutError(
              f"physics type {physics_type(case_root)!r} has no region role {role!r}"
          )
      document = FoamFile(Path(case_root) / layout["names_in"])
      model = str(document[layout["model_key"]])
      return str(document[f"{model}Coeffs"][entry])


  def region_document(case_root: Path, role: str, name: str) -> Path | None:
      """``constant/<region>/<name>`` or ``constant/<name>``; ``None`` if absent."""
      region = region_of(case_root, role)
      base = Path(case_root) / "constant"
      path = base / region / name if region else base / name
      return path if path.exists() else None
  ```

  Add `"physics_layout.json",` to `[tool.setuptools.package-data]` `"omnidriver.cardiacfoam"` in `packages/omnidriver-cardiacfoam/pyproject.toml`, after `"dict_key_allowlist.json",`.

  Replace the whole of `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/planning_policy.py`:
  ```python
  """cardiacFoam-specific strict-planning policy decisions."""

  from __future__ import annotations

  from pathlib import Path

  from omnidriver.cardiacfoam.detection import (
      detect_myocardium_solver_name,
      detect_verification_model_type,
  )
  from omnidriver.cardiacfoam.physics_layout import region_document


  def is_nondimensional_case(spec) -> bool:
      """Corrected 2026-09-26 (spec 2026-09-26 A7): this read only
      ``constant/electroProperties``, so a region-split case such as
      ``monodomainTotalLagrangianEM`` was missed, and core's name rule hid it.
      The electro region now comes from ``physics_layout``."""
      try:
          electro_path = region_document(Path(spec.case_root), "electro", "electroProperties")
          if electro_path is None:
              return False
          return (
              detect_myocardium_solver_name(electro_path) == "singleCellSolver"
              or detect_verification_model_type(electro_path) is not None
          )
      except Exception:
          return False
  ```

  `packages/omnidriver-cardiacfoam/tests/test_physics_layout_native.py` (the drift gate against the real tree):
  ```python
  """physics_layout.json covers every native case, and every region it
  resolves exists (spec 2026-09-26 A7, owner amendment). Supplied only
  through OMNIDRIVER_NATIVE_TUTORIALS, never discovered."""
  from __future__ import annotations

  import os
  from pathlib import Path

  import pytest

  from omnidriver.cardiacfoam.physics_layout import _table, physics_type, region_of

  pytestmark = pytest.mark.native


  def _cases() -> list[Path]:
      value = os.environ.get("OMNIDRIVER_NATIVE_TUTORIALS")
      if not value:
          pytest.fail("OMNIDRIVER_NATIVE_TUTORIALS is not set; a native test needs it supplied")
      return sorted(
          p.parent.parent for p in Path(value).rglob("constant/physicsProperties")
          if "results" not in p.relative_to(value).parts
      )


  def test_every_native_physics_type_has_a_row_and_its_regions_exist():
      cases = _cases()
      assert cases, "no native case found, so this proves nothing"
      split = 0
      for case in cases:
          layout = _table()[physics_type(case)]
          for role in layout.get("regions", {}):
              region = region_of(case, role)
              assert (case / "constant" / region).is_dir(), (case, role, region)
              split += 1
      assert split, "no region-split case found, so the region path is unproved"
  ```

  Run: `OMNIDRIVER_NATIVE_TUTORIALS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials /tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver-cardiacfoam/tests/test_physics_layout_native.py -v -m native`. Expected: PASS. (Reinstall the worktree venv's cardiacfoam package first if package-data changed: `VIRTUAL_ENV=/tmp/odA-core-gen-p1 uv pip install -q -e $W/packages/omnidriver-cardiacfoam`.) If a native type is missing from the table, stop and report it; do not add a row without evidence from that case.

- [ ] **Step 4: Run the proof to verify it passes**

  Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Write the failing core tests**

  `packages/omnidriver/tests/core/test_mesh_geometry_exemption.py`:
  ```python
  """A case is exempt from mesh-scale checks by the plugin's hook, never by its
  name (spec 2026-09-26-core-generality-design.md §2, A7)."""
  from __future__ import annotations

  from pathlib import Path
  from types import SimpleNamespace

  import pytest

  from omnidriver.core import strict_planning
  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.core.runtime.models import TutorialSpec
  from plugins.minimal_plugin import MinimalTestPlugin


  def _spec(root: Path, **metadata) -> TutorialSpec:
      return TutorialSpec(
          name="t", case_root=root, setup_root=root, output_dir=root,
          build_cases=lambda: [], metadata=dict(metadata),
      )


  class _Nondimensional(MinimalTestPlugin):
      def is_nondimensional_case(self, spec):
          return True


  class _HasGeometryChecks(MinimalTestPlugin):
      def get_base_mesh_geometry_diagnostics(self, case_root):
          return (SimpleNamespace(level="warning", code="toy_geometry", message="toy", region="r"),)


  def test_the_name_heuristic_is_gone():
      assert not hasattr(strict_planning, "_is_nondimensional_entry")


  @pytest.mark.parametrize("name", ["manufacturedToy", "toyVerification"])
  def test_a_name_no_longer_exempts_a_case(name, tmp_path):
      ctx = driver_context(MinimalTestPlugin(), source="test")
      spec = _spec(tmp_path, entry_name=name, workflow_family=name)
      assert strict_planning._mesh_geometry_exempt(spec, ctx) is False


  def test_the_plugin_hook_exempts(tmp_path):
      ctx = driver_context(_Nondimensional(), source="test")
      assert strict_planning._mesh_geometry_exempt(_spec(tmp_path), ctx) is True


  def test_a_generic_case_is_exempt(tmp_path):
      ctx = driver_context(MinimalTestPlugin(), source="test")
      assert strict_planning._mesh_geometry_exempt(_spec(tmp_path, generic_case=True), ctx) is True


  def test_the_geometry_skip_variable_declines_the_checks(tmp_path, monkeypatch):
      ctx = driver_context(_HasGeometryChecks(), source="test")
      monkeypatch.delenv("SKIP_GEOMETRY_DIAGNOSTICS", raising=False)
      assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) != ()
      monkeypatch.setenv("SKIP_GEOMETRY_DIAGNOSTICS", "1")
      assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) == ()


  def test_the_old_variable_name_is_not_read(tmp_path, monkeypatch):
      ctx = driver_context(_HasGeometryChecks(), source="test")
      monkeypatch.delenv("SKIP_GEOMETRY_DIAGNOSTICS", raising=False)
      monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
      assert strict_planning._mesh_geometry_diagnostics(tmp_path, driver_context=ctx) != ()
  ```

- [ ] **Step 6: Run them to verify they fail**

  Run: `/tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_mesh_geometry_exemption.py -v`
  
  Expected:
  - FAIL: `test_the_name_heuristic_is_gone`;
  - FAIL with `AttributeError: ... _mesh_geometry_exempt`: `test_a_name_no_longer_exempts_a_case`, `test_the_plugin_hook_exempts`, `test_a_generic_case_is_exempt`;
  - FAIL: `test_the_geometry_skip_variable_declines_the_checks`;
  - FAIL, because the old name is still read: `test_the_old_variable_name_is_not_read`.

- [ ] **Step 7: Delete the heuristic and rename the switch**

  In `core/runtime/strict_audit.py`, below the imports, add:
  ```python
  #: The operator's switch for declining mesh-scale checks. Renamed from
  #: ``SKIP_MESH_DIAGNOSTICS`` 2026-09-26 (spec 2026-09-26 §2, A7): the checks
  #: are the plugin's ``*_geometry_diagnostics`` hooks, and "mesh" named one
  #: kind of discretisation. The old name is not read.
  SKIP_GEOMETRY_DIAGNOSTICS_ENV = "SKIP_GEOMETRY_DIAGNOSTICS"
  ```
  In the `mesh_geometry` audit item:
  - replace each of the three `"SKIP_MESH_DIAGNOSTICS" in os.environ` with `SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ`;
  - replace the literal `SKIP_MESH_DIAGNOSTICS is` in the `uncovered_summary` text with `SKIP_GEOMETRY_DIAGNOSTICS is`.

  In `core/strict_planning.py`:
  1. Change `from .runtime.strict_audit import _build_simulation_audit` to `from .runtime.strict_audit import SKIP_GEOMETRY_DIAGNOSTICS_ENV, _build_simulation_audit`.
  2. Replace the whole of `_is_nondimensional_entry` with:
     ```python
     def _mesh_geometry_exempt(spec, driver_context: "DriverContext") -> bool:
         """Whether the SI mesh-scale gate is not meaningful for this case.

         Two answers only: the plugin's own ``is_nondimensional_case``, read
         from the case's files, or a generic case, whose conventions core
         does not know.

         Corrected 2026-09-26 (spec 2026-09-26 A7): a third answer exempted
         any case whose entry name or workflow family contained
         "manufactured" or "verification", an exemption by *name*. It is
         deleted. ``test_every_case_the_name_rule_exempted_is_exempted_by_the_hook``
         (cardiacfoam, native) proved the hook covers every case it exempted.
         """
         return (
             driver_context.capabilities.mesh_diagnostic_policy.is_nondimensional(spec)
             or bool(spec.metadata.get("generic_case"))
         )
     ```
  3. In `_mesh_geometry_diagnostics`:
     - replace `if exempt or "SKIP_MESH_DIAGNOSTICS" in os.environ:` with `if exempt or SKIP_GEOMETRY_DIAGNOSTICS_ENV in os.environ:`;
     - replace the docstring sentence "Core classifies every polyMesh region's scale; the active plugin may add" with "The active plugin's base geometry check classifies its mesh regions' scale (corrected 2026-09-26: this said core did); the plugin may add".
  4. In `_strict_plan_for_spec`, replace the `mesh_geometry_exempt = (...)` expression with `mesh_geometry_exempt = _mesh_geometry_exempt(spec, driver_context)`.

  In the tests:
  - replace `monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")` with `monkeypatch.setenv("SKIP_GEOMETRY_DIAGNOSTICS", "1")`. That is one site in `test_describe_write_surface.py` and four in `test_generic_plan_has_no_cardiac_semantics.py`;
  - in `test_coverage_is_evidence.py`'s docstring, replace `SKIP_MESH_DIAGNOSTICS` with `SKIP_GEOMETRY_DIAGNOSTICS (renamed 2026-09-26)`.

- [ ] **Step 8: Run the tests and the grep gate**

  ```bash
  /tmp/odA-core-gen-p1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_mesh_geometry_exemption.py $W/packages/omnidriver/tests/core/test_coverage_is_evidence.py $W/packages/omnidriver/tests/core/test_generic_plan_has_no_cardiac_semantics.py $W/packages/omnidriver/tests/core/test_describe_write_surface.py -q
  grep -rn "SKIP_MESH_DIAGNOSTICS\|_is_nondimensional_entry" $W/packages $W/scripts --include='*.py' | grep -v /build/
  ```
  Expected:
  - 0 failed.
  - The grep prints exactly four lines:
    - `strict_audit.py`'s dated comment "Renamed from ``SKIP_MESH_DIAGNOSTICS``";
    - `test_mesh_geometry_exemption.py`'s `setenv("SKIP_MESH_DIAGNOSTICS", ...)`, which proves the old name is ignored;
    - `test_mesh_geometry_exemption.py`'s `hasattr(strict_planning, "_is_nondimensional_entry")`;
    - the native proof's module docstring.
    
    Any other line is a surviving use. Fix it.

- [ ] **Step 9: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0. V4 now includes the Step 1 proof.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A7: `strict_planning._is_nondimensional_entry` (exempted a case by "manufactured"/"verification" in its name) deleted; `_mesh_geometry_exempt` asks only the plugin hook and `generic_case`; `SKIP_MESH_DIAGNOSTICS` renamed `SKIP_GEOMETRY_DIAGNOSTICS` (`strict_audit.SKIP_GEOMETRY_DIAGNOSTICS_ENV`); cardiacfoam's hook finds electroProperties through the new physics layout table (`physics_layout.json`, one row per physics type; region names read from the case) | an exemption by name is solver vocabulary in core; the native proof found the hook missed `manufacturedMonodomainTotalLagrangianEM` | neutral: proved first by `test_every_case_the_name_rule_exempted_is_exempted_by_the_hook` (native) |
  ```
  ```bash
  git -C $W add -A packages docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: mesh-scale exemption comes from the plugin hook, never a name (A7)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  
  Land Tasks 1 and 2 on `main`, one fast-forward per commit, as described in Global Constraints.

---

### Task 3: A5, core declares its own records; record staging excludes step outputs; C11

**Worktree:** `core-gen-p2`. **Parallel with:** Tasks 1, 2 and 4.
**Shared core files touched:** `plugin_capabilities.py`, `sweep_runner.py`, `record_execution.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Why C11, and not a C7 extension.** C7 is a sweep, and every sweep case is staged from the untouched native case, so C7 never sees the leak. The leak appears only when the staging *source* is a case a run has already written. That happens when a native case has been run in, or when an earlier stage is used as a source.

That is a separate property, so it gets its own check id, its own verdict and its own bite test. Folding it into C7 would make one verdict answer two questions.

**What a run really leaves** (observed while planning, 2026-09-26, openCARP v18.1, `main` at `fd21fe7`). Restaging the run case copied everything below:
- **the toy:** `.omnidriver-attempt.lock.guard`, `case_record.json`, `run_document.json`, `solved.marker`, `workflow_logs/…`, `workflow_state.json`;
- **openCARP**, all of the toy's core files plus:
  - `.omnidriver/case-transactions/<id>.json`;
  - `slab.pts`, `slab.elem`, `slab.lon`, `slab.vec`, `slab.vpts`;
  - all of `out/`: `vm.igb`, `init_acts_vm_act-thresh.dat`, `IO_stats.dat`, `ODE_stats.dat`, `Stimulus_0.trc`, `electrics.log`, `par_stats.dat`, `parameters.par`, `petsc_err_log.txt`.

The spec's fix, as literally written, would still leak most of this:
- it names four core files, while core writes seven, plus a directory;
- it excludes each `produces` path exactly, and the record declares only 5 of the 16 files openCARP writes.

So:
- `CORE_RUNTIME_RECORDS` lists every name core writes into a case;
- openCARP's record declares everything it produces (F15, Step 8);
- C11 is strict: the restaged case may hold only paths the native case has.

**Files:**
- Create:
  - `packages/omnidriver/src/omnidriver/core/runtime_records.py`
  - `packages/omnidriver/tests/core/test_core_runtime_records.py`
- Modify, core:
  - `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` (`_CaseRuntimeConventionsAdapter.conventions`; `CaseRuntimeConventions` and `CaseRuntimeConventionsCapability` prose)
  - `packages/omnidriver/src/omnidriver/core/runtime/attempt_lease.py`
  - `packages/omnidriver/src/omnidriver/core/runtime/sweep_runner.py` (`_stage_entry_case`)
  - `packages/omnidriver/src/omnidriver/core/runtime/record_execution.py` (`record_generated_relpaths`, `_stage`)
  - `packages/omnidriver/src/omnidriver/conformance/checks.py`
- Modify, tests:
  - `packages/omnidriver/tests/plugins/conformance_toy.py`
  - `packages/omnidriver/tests/core/test_conformance_toy.py`
  - `packages/omnidriver/tests/core/test_case_file_contract.py`
- Modify, openCARP: `packages/omnidriver-opencarp/src/omnidriver/opencarp/records/niederer_n_version.py`
- Modify, docs:
  - `docs/solver-learning/opencarp.md` (§F, row F15)
  - `docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md` (a dated note on Task 15)

**Interfaces:**
- Produces:
  - `runtime_records.CORE_RUNTIME_RECORDS: CaseRuntimeConventions`;
  - `runtime_records.with_core_runtime_records(conventions: CaseRuntimeConventions) -> CaseRuntimeConventions`;
  - `attempt_lease.ATTEMPT_LOCK_FILENAME = ".omnidriver-attempt.lock"` and `ATTEMPT_LOCK_GUARD_FILENAME = ".omnidriver-attempt.lock.guard"`;
  - `record_execution.record_generated_relpaths(record: TutorialRecord) -> frozenset[str]`;
  - `sweep_runner._stage_entry_case(source_case_root, staged_case_root, *, driver_context=None, excluded_relpaths: frozenset[str] = frozenset())`;
  - `checks.check_restage_is_clean(target) -> CheckVerdict`, registered as `"C11"`.
- Consumes:
  - `case_transaction._JOURNAL_RELATIVE_PATH` (read only; `case_transaction.py` is not edited);
  - `checks._plan`, `_execute`, `_record`, `_context`, `commit_record_case`.

- [ ] **Step 1: Set up the worktree and venvs.** Use `N=core-gen-p2`.

- [ ] **Step 2: Write C11 and the toy's failing tests**

  In `conformance/checks.py`:
  - change the module docstring's first words `C1-C10.` to `C1-C11.`;
  - add, above `CHECKS`:
  ```python
  def _relpaths(root: Path) -> set[str]:
      return {path.relative_to(root).as_posix() for path in root.rglob("*")}


  def check_restage_is_clean(target: ConformanceTarget) -> CheckVerdict:
      """C11: staging a record from a case one run has written carries nothing
      that run wrote (spec 2026-09-26-core-generality-design.md §4, A5).

      A native case someone has already run in, or a copy of an earlier
      stage, holds that run's state (core's run records) and its outputs.
      Staging it again must give only paths the untouched native case has.
      Every other path is named."""
      ctx = _context(target)
      record = _record(ctx, target.record)
      report = _plan(target, ctx)
      if report.status != "ok":
          return _verdict("C11", False, f"cannot check: plan failed: {_plan_errors(report)}")
      try:
          proc, payload = _execute(target, ctx, report)
      except subprocess.TimeoutExpired:
          return _verdict("C11", False, f"the first run timed out after {target.timeout_s}s (ConformanceTarget.timeout_s)")
      if payload is None or payload.get("status") != "ok":
          return _verdict("C11", False, f"cannot check: the first run did not complete (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
      work = target.scratch_root / "conformance" / "C11"
      if work.exists():
          shutil.rmtree(work)
      ran_cases_root = work / "ran"
      shutil.copytree(Path(report.launch["case_root"]), ran_cases_root / record.native_case_relpath, symlinks=True)
      restaged = work / "restaged" / record.name
      commit_record_case(
          record, cases_root=ran_cases_root, staged_case_root=restaged,
          study_by_source={"base": {}}, driver_context=ctx,
      )
      carried = sorted(_relpaths(restaged) - _relpaths(target.cases_root / record.native_case_relpath))
      if carried:
          shown = carried[:20] + ([f"... {len(carried) - 20} more"] if len(carried) > 20 else [])
          return _verdict("C11", False, f"restaging a case the first run wrote carried {len(carried)} path(s) the native case does not have: {shown}")
      return _verdict("C11", True, "restaged from a run case; nothing the run wrote was carried")
  ```
  and register it with `"C11": check_restage_is_clean,` after `"C10"` in `CHECKS`.

  In `tests/plugins/conformance_toy.py`, append:
  ```python
  UNDECLARED_OUTPUT_PLUGIN = "plugins.conformance_toy:UndeclaredOutputPlugin"


  class UndeclaredOutputPlugin(E2ERecordPlugin):
      """Its solve step writes a file it does not declare in ``produces``, so
      staging cannot know the file is generated. C11 must name it."""

      def __init__(self) -> None:
          super().__init__()
          self._solver_commands = frozenset({"touch", "sh"})

      def get_tutorial_records(self):
          return {"toyTutorial": TutorialRecord(
              name="toyTutorial", native_case_relpath="toyTutorial",
              allowed_axes=frozenset({"number_cells"}),
              workflow_steps=(WorkflowStep(
                  step_id="solve", command=("sh", "-c", "touch solved.marker undeclared.out"),
                  consumes=("constant/mesh.json",), produces=("solved.marker",),
              ),),
          )}
  ```

  In `tests/core/test_conformance_toy.py`:
  - add `UNDECLARED_OUTPUT_PLUGIN` to the `plugins.conformance_toy` import;
  - change `test_toy_passes`'s parametrize list to `["C1", "C2", "C3", "C5", "C6", "C7", "C8", "C9", "C10", "C11"]`;
  - append:
  ```python
  def test_c11_names_an_output_the_record_does_not_declare(tmp_path):
      verdict = run_check("C11", toy_conformance_target(tmp_path, plugin=UNDECLARED_OUTPUT_PLUGIN))
      assert not verdict.passed
      assert "undeclared.out" in verdict.detail
      assert "workflow_state.json" not in verdict.detail   # core's own records are never carried
  ```

- [ ] **Step 3: Run them to verify they fail today, for the toy and for openCARP**

  ```bash
  /tmp/odA-core-gen-p2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_conformance_toy.py -v -k "C11"
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
    /tmp/odA-core-gen-p2/bin/python -m pytest $W/packages/omnidriver-opencarp/tests/test_conformance_native.py -v -m native_opencarp -k C11
  ```
  Expected:
  - `test_toy_passes[C11]` FAILs with `restaging a case the first run wrote carried 8 path(s) the native case does not have: ['.omnidriver-attempt.lock.guard', 'case_record.json', 'run_document.json', 'solved.marker', 'workflow_logs', 'workflow_logs/solve.attempt1.stderr.log', 'workflow_logs/solve.attempt1.stdout.log', 'workflow_state.json']`;
  - `test_c11_names_an_output_the_record_does_not_declare` FAILs on its last assertion, because `workflow_state.json` is carried;
  - `test_niederer_passes[C11]` FAILs, naming `.omnidriver`, `case_record.json`, `out`, `run_document.json`, `slab.elem` and `workflow_state.json` among 27 paths (the count observed while planning).
  
  This is the leak, reproduced. `test_niederer_passes` is parametrized over `sorted(CHECKS)`, so it picked up C11 automatically.

- [ ] **Step 4: Write the failing unit tests**

  `packages/omnidriver/tests/core/test_core_runtime_records.py`:
  ```python
  """Core declares its own run records, and record staging drops a record's
  step outputs (spec 2026-09-26-core-generality-design.md §2, A5)."""
  from __future__ import annotations

  from pathlib import Path

  from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.core.runtime.record_execution import record_generated_relpaths
  from omnidriver.core.runtime.sweep_runner import _stage_entry_case
  from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS, with_core_runtime_records
  from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep
  from plugins.minimal_plugin import MinimalTestPlugin


  def _tree(root: Path) -> list[str]:
      return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


  def test_core_names_every_file_it_writes_into_a_case():
      assert set(CORE_RUNTIME_RECORDS.generated_file_names) == {
          "workflow_state.json", "run_document.json", "sweep_manifest.json", "case_record.json",
          ".omnidriver-attempt.lock", ".omnidriver-attempt.lock.guard",
      }
      assert set(CORE_RUNTIME_RECORDS.generated_directory_names) == {"workflow_logs", ".omnidriver"}


  def test_a_stack_that_declares_nothing_still_knows_cores_records():
      ctx = driver_context(MinimalTestPlugin(), source="test")
      assert ctx.capabilities.case_runtime_conventions.conventions() == CORE_RUNTIME_RECORDS


  def test_merging_keeps_the_plugins_names_first_and_adds_cores_once():
      merged = with_core_runtime_records(
          CaseRuntimeConventions(generated_file_names=("run_document.json", "log.x")),
      )
      assert merged.generated_file_names[:2] == ("run_document.json", "log.x")
      assert merged.generated_file_names.count("run_document.json") == 1
      assert set(CORE_RUNTIME_RECORDS.generated_file_names) <= set(merged.generated_file_names)


  def test_a_records_generated_paths_are_what_it_produces_and_does_not_consume():
      record = TutorialRecord(
          name="r", native_case_relpath="r", allowed_axes=frozenset(),
          workflow_steps=(
              WorkflowStep(step_id="mesh", command=("m",), produces=("mesh.pts", "out")),
              WorkflowStep(step_id="fix", command=("f",), consumes=("in_place.par",), produces=("in_place.par",)),
          ),
      )
      assert record_generated_relpaths(record) == frozenset({"mesh.pts", "out"})


  def test_staging_drops_excluded_paths_at_any_depth_and_cores_records(tmp_path):
      source = tmp_path / "source"
      for relpath in ("out/a.dat", "keep/b.txt", "keep/gen.txt", "workflow_state.json", "workflow_logs/s.log", "input.par"):
          (source / relpath).parent.mkdir(parents=True, exist_ok=True)
          (source / relpath).write_text(relpath)
      staged = tmp_path / "staged"
      _stage_entry_case(
          source, staged, driver_context=driver_context(MinimalTestPlugin(), source="test"),
          excluded_relpaths=frozenset({"out", "keep/gen.txt"}),
      )
      assert _tree(staged) == ["input.par", "keep", "keep/b.txt"]
  ```

  Run: `/tmp/odA-core-gen-p2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_core_runtime_records.py -v`
  
  Expected: a collection error, `ModuleNotFoundError: No module named 'omnidriver.core.runtime_records'`.

- [ ] **Step 5: Core declares its own records**

  In `core/runtime/attempt_lease.py`, add below `_LOCAL_LEASES`:
  ```python
  #: The attempt lease's file in an output directory, and the guard file
  #: ``_acquire_local_lease`` keeps beside it. Named once here so core's run
  #: records (``core.runtime_records``) can name them too (spec 2026-09-26 A5).
  ATTEMPT_LOCK_FILENAME = ".omnidriver-attempt.lock"
  ATTEMPT_LOCK_GUARD_FILENAME = f"{ATTEMPT_LOCK_FILENAME}.guard"
  ```
  Then replace the two literals: `path = Path(output_dir).resolve() / ATTEMPT_LOCK_FILENAME` in `attempt_lease_is_held`, and `filename=ATTEMPT_LOCK_FILENAME,` in `acquire_attempt_lease`.

  Create `packages/omnidriver/src/omnidriver/core/runtime_records.py`:
  ```python
  """The files omniD itself writes into a case, declared once, by core (K3).

  Spec 2026-09-26-core-generality-design.md §2 (A5): the core half of K3
  (openCARP plan Task 15). These names used to be declared only by
  ``openfoam_case_runtime_conventions()``, so a stack without the OpenFOAM
  layer (openCARP) did not know them. Staging a case a run had written then
  copied that run's state into the next stage (conformance C11).
  ``_CaseRuntimeConventionsAdapter.conventions`` merges these into whatever
  a stack declares. The OpenFOAM layer's own copies are removed in Task 15.
  """
  from __future__ import annotations

  from dataclasses import replace

  from .case_transaction import _JOURNAL_RELATIVE_PATH
  from .plugin_capabilities import CaseRuntimeConventions
  from .runtime.attempt_lease import ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME

  #: ``case_transaction``'s per-case journal directory, named by its owner.
  _CASE_TRANSACTION_DIRECTORY = _JOURNAL_RELATIVE_PATH.parts[0]

  CORE_RUNTIME_RECORDS = CaseRuntimeConventions(
      generated_directory_names=("workflow_logs", _CASE_TRANSACTION_DIRECTORY),
      generated_file_names=(
          "workflow_state.json", "run_document.json", "sweep_manifest.json", "case_record.json",
          ATTEMPT_LOCK_FILENAME, ATTEMPT_LOCK_GUARD_FILENAME,
      ),
      generated_case_markers=("workflow_state.json", "workflow_logs", "run_document.json"),
  )


  def _union(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
      return first + tuple(name for name in second if name not in first)


  def with_core_runtime_records(conventions: CaseRuntimeConventions) -> CaseRuntimeConventions:
      """``conventions`` plus core's own records; the plugin's names stay first."""
      return replace(
          conventions,
          generated_directory_names=_union(conventions.generated_directory_names, CORE_RUNTIME_RECORDS.generated_directory_names),
          generated_file_names=_union(conventions.generated_file_names, CORE_RUNTIME_RECORDS.generated_file_names),
          generated_case_markers=_union(conventions.generated_case_markers, CORE_RUNTIME_RECORDS.generated_case_markers),
      )
  ```
  The `.omnidriver` literal is not written here. `test_nothing_rebuilds_a_dot_omnidriver_scratch_default` exempts only `case_transaction.py`, which owns that directory, so the name is taken from there.

  In `core/plugin_capabilities.py`, replace `_CaseRuntimeConventionsAdapter.conventions` with:
  ```python
      def conventions(self) -> CaseRuntimeConventions:
          """The stack's declared generated paths, plus core's own run records
          (``runtime_records.CORE_RUNTIME_RECORDS``), whatever the plugin
          declares. Corrected 2026-09-26 (spec 2026-09-26 A5): a plugin
          without the hook used to receive an empty declaration, so staging a
          case a run had written carried core's own state into the next stage."""
          from .runtime_records import with_core_runtime_records

          hook = getattr(self.plugin, "get_case_runtime_conventions", None)
          if callable(hook):
              result = hook()
              if not isinstance(result, CaseRuntimeConventions):
                  raise TypeError(
                      f"{self.plugin.plugin_id}.get_case_runtime_conventions() must "
                      f"return CaseRuntimeConventions, got {result!r}"
                  )
              return with_core_runtime_records(result)
          from .compatibility import legacy_case_runtime_conventions

          return with_core_runtime_records(legacy_case_runtime_conventions())
  ```
  In the `CaseRuntimeConventionsCapability` docstring, replace "A plugin without the optional hook receives an empty declaration: Core preserves every path and does not collect a convention-specific tree." with "A plugin without the optional hook receives only core's own run records (``runtime_records.CORE_RUNTIME_RECORDS``, merged into every answer since 2026-09-26, spec A5): Core preserves every authored path and does not collect a convention-specific tree."

  `_CaseCompatibilityAdapter.is_case` reads the hook directly and is **not** changed. Registry case discovery keeps its current answers; only staging reads the merged names.

  In `tests/core/test_case_file_contract.py::test_minimal_plugin_declares_no_case_files`:
  - replace `== CaseRuntimeConventions()` with `== CORE_RUNTIME_RECORDS`;
  - add `from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS`;
  - remove `CaseRuntimeConventions` from that file's imports, if nothing else there uses it.

- [ ] **Step 6: Record staging drops step outputs**

  In `core/runtime/sweep_runner.py`, replace `_stage_entry_case` with the version below. The body is unchanged apart from the resolved roots, which move above the nested function, and the new first test in `ignore_generated`.
  ```python
  def _stage_entry_case(
      source_case_root: Path, staged_case_root: Path, *, driver_context=None,
      excluded_relpaths: frozenset[str] = frozenset(),
  ) -> None:
      """Copy a registered case into scratch storage without old run output.

      Registered tutorial folders contain source dictionaries and scripts next
      to OpenFOAM's generated mesh, time, processor, log, and post-processing
      trees.  Copying those generated trees would reintroduce the stale-state
      bug this staging boundary is meant to prevent, so the filter is explicit
      and conservative: keep authored inputs (including ``0/``) and omit only
      known derived artifacts.

      ``excluded_relpaths`` names further case-relative paths (files, or whole
      directories, at any depth) that the caller knows are generated: a
      tutorial record's step outputs (``record_execution
      .record_generated_relpaths``, spec 2026-09-26 A5). Core's own run
      records need no listing here, because every stack's conventions carry
      them (``runtime_records.CORE_RUNTIME_RECORDS``).
      """
      from ..plugin_capabilities import CaseRuntimeConventions

      conventions = (
          driver_context.capabilities.case_runtime_conventions.conventions()
          if driver_context is not None else CaseRuntimeConventions()
      )
      decomposition_prefix = (
          decomposition_dirname_prefix(driver_context)
          if driver_context is not None else None
      )
      source_case_root = Path(source_case_root).resolve()
      staged_case_root = Path(staged_case_root).resolve()

      def ignore_generated(_directory: str, names: list[str]) -> set[str]:
          ignored: set[str] = set()
          relative_directory = Path(_directory).relative_to(source_case_root)
          for name in names:
              candidate = Path(_directory) / name
              if (relative_directory / name).as_posix() in excluded_relpaths:
                  ignored.add(name)
                  continue
              # A previous driverFOAM case can have a descriptive directory name
              # (for example ``gauss_linear_40_*``) rather than a numeric
              # generated numeric-time name. Its workflow markers are the reliable
              # boundary between authored tutorial content and generated case
              # content, so omit the whole directory when they are present.
              if candidate.is_dir() and any(
                  (candidate / marker).exists()
                  for marker in conventions.generated_case_markers
              ):
                  ignored.add(name)
                  continue
              if name in conventions.generated_directory_names or name in conventions.generated_file_names:
                  ignored.add(name)
                  continue
              if (
                  candidate.is_dir()
                  and (
                      (decomposition_prefix is not None and name.startswith(decomposition_prefix))
                      or any(name.startswith(prefix) for prefix in conventions.generated_directory_prefixes)
                  )
              ):
                  ignored.add(name)
                  continue
              if (
                  any(name.startswith(prefix) for prefix in conventions.generated_file_prefixes)
                  or (
                      any(name.endswith(suffix) for suffix in conventions.generated_file_suffixes)
                      and not any(
                          name.endswith(suffix)
                          for suffix in conventions.preserved_file_suffixes
                      )
                  )
              ):
                  ignored.add(name)
                  continue
              path = Path(name)
              if _is_declared_generated_time_directory(path.name, conventions):
                  ignored.add(name)
          return ignored

      if not source_case_root.is_dir():
          raise FileNotFoundError(f"Registered case root does not exist: {source_case_root}")
      with acquire_case_staging_lease(staged_case_root):
          _recover_interrupted_case_staging(staged_case_root)
          _copy_and_promote_staged_case(
              source_case_root,
              staged_case_root,
              ignore=ignore_generated,
          )
  ```

  In `core/runtime/record_execution.py`:
  - add `PurePosixPath` to the existing `from pathlib import ...` line;
  - add, above `_stage`:
  ```python
  def record_generated_relpaths(record: TutorialRecord) -> frozenset[str]:
      """The case-relative paths a record's steps write, which staging must
      not carry from one run into the next stage (spec 2026-09-26 A5).

      A path some step also ``consumes`` is an input updated in place, so it
      is never excluded: excluding it would drop an authored input."""
      produced = {PurePosixPath(p).as_posix() for step in record.workflow_steps for p in step.produces}
      consumed = {PurePosixPath(p).as_posix() for step in record.workflow_steps for p in step.consumes}
      return frozenset(produced - consumed)
  ```
  - in `_stage`, change the call to:
  ```python
      _stage_entry_case(
          native_case_root, staged_case_root, driver_context=driver_context,
          excluded_relpaths=record_generated_relpaths(record),
      )
  ```

- [ ] **Step 7: Run the unit tests and the toy**

  ```bash
  /tmp/odA-core-gen-p2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_core_runtime_records.py $W/packages/omnidriver/tests/core/test_conformance_toy.py $W/packages/omnidriver/tests/core/test_case_file_contract.py $W/packages/omnidriver/tests/core/test_sweep_runner.py $W/packages/omnidriver/tests/core/test_core_context_is_explicit.py -q
  ```
  Expected: 0 failed. `test_toy_passes[C11]` passes, and `test_c11_names_an_output_the_record_does_not_declare` passes: it names `undeclared.out` and not `workflow_state.json`.

- [ ] **Step 8: Probe what openCARP produces, then declare it**

  Re-run the planning probe against the real binary:
  ```bash
  cd $W && OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib /tmp/odA-core-gen-p2/bin/python - <<'EOF'
  import sys, tempfile
  from pathlib import Path
  sys.path.insert(0, "packages/omnidriver-opencarp/tests")
  from opencarp_native import niederer_conformance_target
  from omnidriver.conformance import run_check
  target = niederer_conformance_target(Path(tempfile.mkdtemp(prefix="odA-F15-")))
  print(run_check("C6", target))
  case = target.scratch_root / "records" / "niedererNVersion"
  print(sorted(p.relative_to(case).as_posix() for p in case.rglob("*")))
  EOF
  ```
  Expected: C6 passes, and the listing matches "What a run really leaves" above. If the binary writes something else, record what it wrote; the row below and the `produces` follow the binary, not this plan.

  Append row F15 to `docs/solver-learning/opencarp.md` §F:
  ```
  | F15 | What does one record run leave in the case beyond its declared outputs? (spec 2026-09-26 A5, conformance C11) | C6's run of `niedererNVersion` (dx 1000, tend 10, dt 50) on the staged `03E_study_resolution`, then a listing of the staged case | `mesher` wrote `slab.pts`, `slab.elem`, `slab.lon`, **`slab.vec`, `slab.vpts`**; `openCARP ... -simID out` wrote `out/` holding `vm.igb`, `init_acts_vm_act-thresh.dat`, **`IO_stats.dat`, `ODE_stats.dat`, `Stimulus_0.trc`, `electrics.log`, `par_stats.dat`, `parameters.par`, `petsc_err_log.txt`** | **the `-simID` directory is wholly generated, and `mesher` writes five files, not three.** The record declares `out` and all five mesh files in `produces`, so record staging never carries them into a new stage (C11) |
  ```

  In `records/niederer_n_version.py`, the mesh step becomes:
  ```python
              produces=("slab.pts", "slab.elem", "slab.lon", "slab.vec", "slab.vpts"),   # F15
  ```
  and the solve step becomes:
  ```python
              produces=("out", "out/vm.igb", "out/init_acts_vm_act-thresh.dat"),   # F6; the whole -simID directory: F15
  ```

- [ ] **Step 9: Run openCARP native to verify C1–C11 pass**

  Run V5. Expected: 0 failed, `test_niederer_passes[C11]` included.

- [ ] **Step 10: Record that Task 15's core half is done**

  Under `### Task 15` in `docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md`, add as its first paragraph:
  ```
  **Corrected 2026-09-26 (topic A, A5):** Step 3's core half landed early in `docs/superpowers/plans/2026-09-26-core-generality.md` Task 3: `core/runtime_records.py` (`CORE_RUNTIME_RECORDS`, which names every file core writes, not only the four listed below) and the merge in `_CaseRuntimeConventionsAdapter.conventions`. This task keeps only the OpenFOAM half: deleting core's names from `openfoam_case_runtime_conventions()`, and the two guards.
  ```

- [ ] **Step 11: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A5: `core/runtime_records.py` -- `CORE_RUNTIME_RECORDS` (every file core writes into a case: `workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `case_record.json`, the attempt lock and its guard, `workflow_logs/`, the case-transaction directory) merged into every stack's conventions by `_CaseRuntimeConventionsAdapter.conventions`; record staging also drops each step's `produces` (`record_generated_relpaths`, minus paths a step consumes); conformance C11; openCARP's record declares its full outputs (F15) | openCARP declares no conventions, so staging a case a run had written carried that run's state and `out/` into the new stage | neutral: no solver vocabulary; C11 fails first for the toy and openCARP (`test_toy_passes[C11]`, `test_niederer_passes[C11]`) and passes after |
  ```
  ```bash
  git -C $W add -A packages docs/solver-learning/opencarp.md docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "fix(core): core declares its own run records; record staging drops step outputs; conformance C11 (A5)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Task 4: A3, the dictionary-shaped members become optional-neutral

**Worktree:** `core-gen-p3`. **Parallel with:** Tasks 1–3.
**Shared core file touched:** `plugin_capabilities.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**The stable "none" digest.** A provider that does not implement `get_dict_entries` digests with `dictionary_entries = ()`. That is the same input a stub returning `()` produced, so **every provider digest is unchanged**.

Stack digests:
- **Unchanged** for every stack with a real implementer: `cardiacfoam`, `cardiaccore`. There, `resolutions()` already named the solver as the `dictionaries` winner, and the OpenFOAM layer's empty stub contributed `()` to the composed tuple.
- **Changed once** for `opencarp` and standalone `openfoam-environment`. Each one's stub was the only "implementer", so it was recorded as the `dictionaries` winner. That is the false provenance claim `openfoam-environment.yaml`'s own comment documents. With the stub gone, the existing rule records `<unclaimed>`, as it does for every capability no provider implements (audit C3). The plan does not fake a winner to keep the old digest.

**Files:**
- Create:
  - `packages/omnidriver/tests/core/test_dictionary_members_are_optional.py`
  - `packages/omnidriver-cardiacfoam/tests/test_optional_dictionary_members_digest.py`
- Modify, core:
  - `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` (`TutorialCatalogCapability`, `DictionaryCatalogCapability`, `_TutorialCatalogAdapter`, `_DictionaryCatalogAdapter`)
  - `packages/omnidriver/src/omnidriver/core/plugin_interface.py` (the four members move from `SolverPlugin` to `SolverPluginOptionalHooks`; `_declared_dict_entries`; `_validate_one_provider`; `_provider_identity`)
  - `packages/omnidriver/src/omnidriver/core/compatibility.py` (`legacy_phases`)
- Modify, plugins:
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` (delete four stubs)
  - `packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py` (delete four stubs)
- Modify, test plugins and tests:
  - `packages/omnidriver/tests/plugins/minimal_plugin.py`
  - `packages/omnidriver-cardiacfoam/tests/plugins/minimal_plugin.py`
  - `packages/omnidriver/tests/core/test_plugin_api_version.py`
  - `packages/omnidriver/tests/core/test_plugin_capabilities.py`
  - `packages/omnidriver-cardiacfoam/tests/test_plugin_architecture.py`
- Modify, scripts and docs:
  - `scripts/export-tutorials-catalog.py`
  - `AGENT_GUIDE.md` ("Required Members (all plugins)")
  - `ARCHITECTURE.md` (regenerated)

**Interfaces:**
- Produces:
  - `plugin_interface._declared_dict_entries(provider) -> tuple[Any, ...]`;
  - tiers: `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog`, `get_tutorial_displays` are `optional-neutral`; `get_tutorial_catalog` stays `required`.
- Adapter empty answers: `entries() -> ()`, `groups() -> {}`, `catalog() -> DictionaryCatalog({})`, `displays() -> ()`.

- [ ] **Step 1: Set up the worktree and venvs** (`N=core-gen-p3`). Record today's identities for Step 8:
  ```bash
  cd $W && /tmp/odA-core-gen-p3/bin/python - > /tmp/odA-core-gen-p3-identity-before.txt <<'EOF'
  from omnidriver.core.plugin_discovery import load_discovered_plugin
  for stack in ("cardiacfoam", "cardiaccore", "opencarp", "openfoam-environment"):
      identity = load_discovered_plugin(stack).identity
      print(stack, identity.capability_digest, identity.resolutions["dictionaries"],
            identity.resolutions["tutorials"], [p.provider_digest for p in identity.providers])
  EOF
  ```

- [ ] **Step 2: Write the failing tests**

  `packages/omnidriver/tests/core/test_dictionary_members_are_optional.py`:
  ```python
  """The dictionary-shaped members are optional-neutral
  (spec 2026-09-26-core-generality-design.md §2, A3)."""
  from __future__ import annotations

  import pytest

  from omnidriver.conformance import run_check
  from omnidriver.core import provider_stack
  from omnidriver.core.capability_seams import members_by_tier
  from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
  from omnidriver.core.plugin_interface import driver_context
  from plugins.conformance_toy import toy_conformance_target
  from plugins.e2e_record_plugin import E2ERecordPlugin
  from plugins.minimal_plugin import MinimalTestPlugin

  _NOW_OPTIONAL = ("get_dict_entries", "get_dict_groups", "get_dictionary_catalog", "get_tutorial_displays")


  def test_the_four_are_optional_neutral_and_the_tutorial_catalog_stays_required():
      tiers = members_by_tier()
      assert set(_NOW_OPTIONAL) <= tiers["optional-neutral"]
      assert "get_tutorial_catalog" in tiers["required"]


  @pytest.mark.parametrize("member", _NOW_OPTIONAL)
  def test_the_toy_implements_none_of_them(member):
      """Non-vacuity: the proofs below drive a plugin that really lacks them."""
      assert not callable(getattr(E2ERecordPlugin(), member, None))


  def test_a_plugin_without_them_loads_and_composes_to_empty_answers():
      ctx = driver_context(MinimalTestPlugin(), source="test")
      assert ctx.capabilities.dictionaries.entries() == ()
      assert ctx.capabilities.dictionaries.groups() == {}
      assert dict(ctx.capabilities.dictionaries.catalog().documents) == {}
      assert ctx.capabilities.dictionaries.phases() == ()
      assert ctx.capabilities.tutorials.displays() == ()


  @pytest.mark.parametrize("check_id", ["C1", "C2", "C6", "C10"])
  def test_a_plugin_without_them_loads_describes_and_runs(check_id, tmp_path):
      verdict = run_check(check_id, toy_conformance_target(tmp_path))
      assert verdict.passed, verdict.detail


  class _EmptyStubs(MinimalTestPlugin):
      """The stubs as the openfoam and opencarp plugins carried them before A3."""

      def get_dict_entries(self):
          return ()

      def get_dictionary_catalog(self):
          return DictionaryCatalog({})

      def get_dict_groups(self):
          return {}

      def get_tutorial_displays(self):
          return ()


  def test_no_dictionary_entries_digests_exactly_as_an_empty_stub_did():
      absent = driver_context(MinimalTestPlugin(), source="test").identity.providers[0].provider_digest
      stubbed = driver_context(_EmptyStubs(), source="test").identity.providers[0].provider_digest
      assert absent == stubbed


  def test_a_stack_with_no_dictionary_implementer_records_the_capability_unclaimed():
      assert driver_context(MinimalTestPlugin(), source="test").identity.resolutions["dictionaries"] == provider_stack.UNCLAIMED
      assert driver_context(_EmptyStubs(), source="test").identity.resolutions["dictionaries"] == "org.driverfoam.test-minimal"
  ```

  `packages/omnidriver-cardiacfoam/tests/test_optional_dictionary_members_digest.py`:
  ```python
  """Deleting the OpenFOAM layer's empty dictionary stubs changes no cardiac
  stack's identity (spec 2026-09-26-core-generality-design.md §2, A3)."""
  from __future__ import annotations

  from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
  from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin


  class _EnvironmentWithStubs(OpenFOAMEnvironmentPlugin):
      """The OpenFOAM layer as it was before A3."""

      def get_dict_entries(self):
          return ()

      def get_dictionary_catalog(self):
          return DictionaryCatalog({})

      def get_dict_groups(self):
          return {}

      def get_tutorial_displays(self):
          return ()


  def test_the_cardiac_stack_identity_is_unchanged_by_deleting_the_stubs():
      with_stubs = driver_context(_EnvironmentWithStubs(), CardiacFoamPlugin(), source="test").identity
      without = driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test").identity
      assert without.to_json() == with_stubs.to_json()
  ```

- [ ] **Step 3: Run them to verify they fail**

  Run: `/tmp/odA-core-gen-p3/bin/python -m pytest $W/packages/omnidriver/tests/core/test_dictionary_members_are_optional.py $W/packages/omnidriver-cardiacfoam/tests/test_optional_dictionary_members_digest.py -v`
  
  Expected:
  - FAIL: `test_the_four_are_optional_neutral...`, all four `test_the_toy_implements_none_of_them`, and `test_a_stack_with_no_dictionary_implementer...` (the tiers are still required and `MinimalTestPlugin` still stubs them);
  - PASS today, and kept as guards: `test_a_plugin_without_them_loads_and_composes...`, the C1/C2/C6/C10 runs, the digest-equality test and the cardiac test. They pass because the stubs return empty.

- [ ] **Step 4: Demote the tiers, make the adapters and identity probe, delete the stubs**

  In `core/plugin_capabilities.py`, change the `TutorialCatalogCapability` docstring:
  - replace "Both are required v1 members, so there is no fallback: a plugin that registers no tutorials returns empty rather than omitting the member." with "``catalog`` is required: a plugin that registers no tutorials returns empty rather than omitting it. ``displays`` is optional-neutral since 2026-09-26 (spec A3); absent, it answers ``()``, and core has no runtime consumer of it.";
  - set `:status: get_tutorial_catalog=required, get_tutorial_displays=optional-neutral`.

  Change the `DictionaryCatalogCapability` docstring:
  - replace "All three are required v1 members with no fallback." with "All three are optional-neutral since 2026-09-26 (spec A3). A plugin without dictionaries (openCARP, the toy) omits them, and each answers empty: ``()``, ``DictionaryCatalog({})``, ``{}``. Corrected that day: they were required, so every plugin had to stub them.";
  - set `:status: optional-neutral`.

  Replace both adapters:
  ```python
  @dataclass(frozen=True)
  class _TutorialCatalogAdapter:
      plugin: "SolverPlugin"

      def catalog(self) -> dict[str, Any]:
          return self.plugin.get_tutorial_catalog()

      def displays(self) -> tuple[Any, ...]:
          hook = getattr(self.plugin, "get_tutorial_displays", None)
          return tuple(hook()) if callable(hook) else ()


  @dataclass(frozen=True)
  class _DictionaryCatalogAdapter:
      plugin: "SolverPlugin"

      def entries(self) -> tuple[Any, ...]:
          hook = getattr(self.plugin, "get_dict_entries", None)
          return tuple(hook()) if callable(hook) else ()

      def catalog(self) -> Any:
          hook = getattr(self.plugin, "get_dictionary_catalog", None)
          if callable(hook):
              return hook()
          from .contracts.dictionary_catalog import DictionaryCatalog

          return DictionaryCatalog({})

      def groups(self) -> dict[str, tuple[Any, ...]]:
          hook = getattr(self.plugin, "get_dict_groups", None)
          return dict(hook()) if callable(hook) else {}

      def phases(self) -> tuple[str, ...]:
          hook = getattr(self.plugin, "get_phases", None)
          if callable(hook):
              return tuple(hook())
          from .compatibility import legacy_phases

          return legacy_phases(self.plugin)
  ```

  In `core/compatibility.py::legacy_phases`, replace `for entry in plugin.get_dict_entries():` with:
  ```python
      hook = getattr(plugin, "get_dict_entries", None)
      for entry in (hook() if callable(hook) else ()):
  ```

  In `core/plugin_interface.py`:
  1. Delete `get_dict_entries`, `get_dictionary_catalog`, `get_dict_groups` and `get_tutorial_displays` from the `SolverPlugin` Protocol body. Add them to `SolverPluginOptionalHooks` under this heading:
     ```python
         # -- DictionaryCatalogCapability / TutorialCatalogCapability ----------------
         # Optional-neutral since 2026-09-26 (spec 2026-09-26 A3).
         def get_dict_entries(self) -> tuple[DictEntry, ...]:
             """The plugin's dictionary entries. Absent -> ``()``; the identity
             digest then hashes ``()``, exactly as an empty stub did."""
             ...

         def get_dictionary_catalog(self):
             """Entries partitioned by plugin-owned document name. Absent -> an
             empty ``DictionaryCatalog``."""
             ...

         def get_dict_groups(self) -> dict[str, tuple[DictEntry, ...]]:
             """Entries by the plugin's own group names. Absent -> ``{}``."""
             ...

         def get_tutorial_displays(self) -> tuple[TutorialDisplay, ...]:
             """Display cards for the registered tutorials. Absent -> ``()``."""
             ...
     ```
  2. Add, above `_validate_one_provider`:
     ```python
     def _declared_dict_entries(provider: Any) -> tuple[Any, ...]:
         """A provider's dictionary entries, or ``()`` when it declares none.

         ``()`` is the identity digest's input for "none" (spec 2026-09-26 A3).
         A provider without ``get_dict_entries`` digests exactly as one whose
         stub returned ``()`` did, so deleting such a stub changes no provider
         digest."""
         hook = getattr(provider, "get_dict_entries", None)
         return tuple(hook()) if callable(hook) else ()
     ```
  3. In `_validate_one_provider`:
     - replace `entries = tuple(checked.get_dict_entries())` with `entries = _declared_dict_entries(checked)`;
     - update the comment in `validate_plugin` from "before get_dict_entries()" to "before any catalog member".
  4. In `_provider_identity`, replace `dictionary_entries=tuple(provider.get_dict_entries()),` with `dictionary_entries=_declared_dict_entries(provider),`.

  Delete the four stubs (`get_dict_entries`, `get_dictionary_catalog`, `get_dict_groups`, `get_tutorial_displays`) from:
  - `OpenFOAMEnvironmentPlugin` (`openfoam/environment.py`), and its `DictionaryCatalog` import;
  - `OpenCARPPlugin` (`opencarp/plugin.py`), and its `DictionaryCatalog` import. Change the comment `# -- required contract; the dictionary-shaped members are empty (spec K5 deferred)` to `# -- required contract (the dictionary-shaped members are optional since 2026-09-26, spec A3, so none are stubbed)`;
  - `MinimalTestPlugin` (`packages/omnidriver/tests/plugins/minimal_plugin.py`), and its `DictionaryCatalog` import;
  - `MinimalOpenFOAMPlugin` (`packages/omnidriver-cardiacfoam/tests/plugins/minimal_plugin.py`), and its `DictionaryCatalog` import, if nothing else there uses it.

  In `tests/core/test_plugin_api_version.py`:
  - `HalfMigratedPlugin`: replace `get_dictionary_catalog = None` with `validate_configuration = None`. In its comment, note that `get_dictionary_catalog` became optional on 2026-09-26;
  - `MissingTwo`: use `get_capabilities = None` and `get_tutorial_catalog = None`, and assert `"get_capabilities" in message` and `"get_tutorial_catalog" in message`.

  In `tests/core/test_plugin_capabilities.py`, replace `assert context.capabilities.dictionaries.entries() == plugin.get_dict_entries()` with `assert context.capabilities.dictionaries.entries() == ()`.

  In `packages/omnidriver-cardiacfoam/tests/test_plugin_architecture.py`, replace the two `assert plugin.get_dict_entries() == ()` lines with `assert ctx.capabilities.dictionaries.entries() == ()`.

  In `scripts/export-tutorials-catalog.py`:
  - replace both `selected.get_tutorial_displays()` with `context.capabilities.tutorials.displays()`;
  - delete the `selected = context.providers[-1]` line and its comment.

  In `AGENT_GUIDE.md` "Required Members (all plugins)":
  - delete the four lines `get_dict_entries()`, `get_dictionary_catalog()`, `get_dict_groups()`, `get_tutorial_displays()`;
  - add below the block: "Corrected 2026-09-26 (spec A3): `get_dict_entries`, `get_dictionary_catalog`, `get_dict_groups` and `get_tutorial_displays` are optional; absent, each answers empty. A plugin without dictionaries (openCARP) omits them."

  Regenerate the table: `cd $W && /tmp/odA-core-gen-p3/bin/python scripts/export-capability-seams.py`.

- [ ] **Step 5: Run the tests to verify they pass**

  ```bash
  /tmp/odA-core-gen-p3/bin/python -m pytest $W/packages/omnidriver/tests/core/test_dictionary_members_are_optional.py $W/packages/omnidriver-cardiacfoam/tests/test_optional_dictionary_members_digest.py $W/packages/omnidriver/tests/core/test_contract_tier_coherence.py $W/packages/omnidriver/tests/core/test_capability_seam_documentation.py $W/packages/omnidriver/tests/core/test_plugin_api_version.py $W/packages/omnidriver-cardiacfoam/tests/test_plugin_architecture.py -q
  grep -rn "def get_dict_entries\|def get_dict_groups\|def get_dictionary_catalog\|def get_tutorial_displays" $W/packages/omnidriver-openfoam/src $W/packages/omnidriver-opencarp/src $W/packages/omnidriver/tests/plugins
  ```
  Expected: 0 failed, and the grep prints nothing.

- [ ] **Step 6: Run the tutorial-catalog export**

  Run: `/tmp/odA-core-gen-p3/bin/python -m pytest $W/packages/omnidriver-cardiacfoam/tests/test_tutorials_catalog_export.py -q`
  
  Expected: 0 failed. The composed `displays()` is the OpenFOAM layer's former `()` plus cardiacFOAM's cards: the same rows.

- [ ] **Step 7: Run V1–V6.** Expected: 0 failed in V1–V5, and V6 exits 0.

- [ ] **Step 8: Compare identities before and after**

  ```bash
  cd $W && /tmp/odA-core-gen-p3/bin/python - > /tmp/odA-core-gen-p3-identity-after.txt <<'EOF'
  from omnidriver.core.plugin_discovery import load_discovered_plugin
  for stack in ("cardiacfoam", "cardiaccore", "opencarp", "openfoam-environment"):
      identity = load_discovered_plugin(stack).identity
      print(stack, identity.capability_digest, identity.resolutions["dictionaries"],
            identity.resolutions["tutorials"], [p.provider_digest for p in identity.providers])
  EOF
  diff /tmp/odA-core-gen-p3-identity-before.txt /tmp/odA-core-gen-p3-identity-after.txt
  ```
  Expected:
  - the `cardiacfoam` and `cardiaccore` lines are identical;
  - the `opencarp` and `openfoam-environment` lines differ only in the capability digest and in `dictionaries` (now `<unclaimed>`);
  - every provider digest is identical on every line.
  
  Put the diff in the commit message body.

- [ ] **Step 9: Commit**

  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A3: `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog`, `get_tutorial_displays` are optional-neutral (adapters answer `()`/`{}`/`DictionaryCatalog({})`/`()`; `_declared_dict_entries` feeds validation and identity); the stubs in the OpenFOAM layer, openCARP and both minimal test plugins are deleted; `get_tutorial_catalog` stays required | every plugin had to stub dictionary-shaped members core has no record-path need for | neutral: every provider digest unchanged and the cardiac stacks' identities unchanged (`test_the_cardiac_stack_identity_is_unchanged_by_deleting_the_stubs`); `opencarp` and standalone `openfoam-environment` now record `dictionaries` as `<unclaimed>` -- their stub had been its false winner |
  ```
  ```bash
  git -C $W add -A packages scripts AGENT_GUIDE.md ARCHITECTURE.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor(core): dictionary-shaped plugin members are optional-neutral (A3)

  <paste the Step 8 diff here>

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

### Checkpoint R1: Opus review of the parallel tracks

- [ ] Once Tasks 1–4 are all on `main`, dispatch one reviewer (Agent tool, `model: "opus"`) over `git diff fd21fe7..main -- packages scripts docs`. Its brief:
  - check each change against spec §2/§4 and this plan's Global Constraints;
  - look for any survivor of the old names (the grep gates of Tasks 1–4);
  - look for any silently weakened guard;
  - check that C11 is strict (the restaged case ⊆ the native case);
  - look for any digest change beyond the one Task 4 predicts.
- [ ] Fix each finding in its own commit with a dated correction, rerun V1–V6, land.
- [ ] Bring the owner two decisions to confirm:
  - Task 2's hook reads a region-split electroProperties;
  - Task 4's one-time change to the `opencarp` and `openfoam-environment` digests.

---

### Task 5: A1, `environment_source`, opaque to core

**Worktree:** `core-gen-a1`, from `main` after R1. **Runs alone**, because it touches every package.
**Shared core files touched:** `strict_planning.py`, `plugin_capabilities.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Naming.** The contract name `explicit_bashrc`, the CLI dest `environment_bashrc` and the flag `--environment-bashrc` become `environment_source` and `--environment-source` everywhere, and `generic_case` loses the parameter entirely.

Inside `omnidriver-openfoam`, the value really is a shell script to source. OpenFOAM's own helpers there were also spelled `explicit_bashrc`; they are renamed `bashrc_path`, so no grep can confuse them with the old contract name.

**Files:**
- Create:
  - `packages/omnidriver/tests/core/test_environment_source_is_opaque.py`
  - `packages/omnidriver/tests/core/test_cli_environment_source_flag.py` (`git mv` from `test_cli_environment_bashrc_flag.py`)
- Modify, core:
  - `cli.py` (the flag; its action check; `_context_from_run_document` ×2; `_context_from_entry`'s parameter and its four uses; `main`'s plan/step/run ×3)
  - `core/strict_planning.py` (`strict_plan`, `_strict_plan_for_record`, `_strict_plan_for_spec`)
  - `core/plugin_capabilities.py` (`EnvironmentPreflightCapability`; `_EnvironmentPreflightAdapter.diagnostics` and `.load`)
  - `core/plugin_interface.py` (`get_environment_diagnostics`, `get_loaded_environment`)
  - `core/compatibility.py` (`legacy_environment_diagnostics`, `legacy_load_environment`)
  - `core/runtime/generic_case.py` (`make_spec`, `_normalize_case_specs`)
- Modify, plugins:
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py`
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment_preflight.py`
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam_environment.py`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_builder.py`
  - `packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py`
- Modify, test plugins: `tests/plugins/declared_case_plugin.py`, `e2e_record_plugin.py`, `conformance_toy.py`.
- Modify, core tests: `test_core_generic_case.py`, `test_strict_plan_contract.py`, `test_coverage_blocks_dispatch.py`, `test_scratch_root_is_supplied.py`, `test_generic_plugin_execution.py`, `test_cli_config_plugin_context.py`, `test_wheel_install_imports.py`, `test_core_carries_no_cardiac_names.py`.
- Modify, openfoam tests: `test_case_dict_keys.py`, `test_environment_preflight.py`, `test_code_contract_repairs.py`, `test_apply_through_the_channel.py`.
- Modify, cardiacfoam tests: `test_strict_planning.py`, `test_environment_preflight_composition.py`, `test_reference_experiment_manifests.py`, and the fixtures `fixtures/reference_experiments/niederer_tissue.json` and `single_cell_tworld.json`.
- Modify: `scripts/core-shape-baseline.txt` (delete all six `bashrc` lines).
- Modify: `future/ENVIRONMENT_CONTRACT.md` (a dated note).

**Interfaces:**
- Produces:
  - `strict_plan(..., environment_source: str | None = None, ...)`;
  - `EnvironmentPreflightCapability.diagnostics(workflow_dag, *, env=None, environment_source: str | None = None, driver_context=None)` and `.load(*, environment_source: str | None, driver_context)`;
  - plugin hooks `get_environment_diagnostics(workflow_dag, *, env=None, environment_source=None, driver_context=None)` and `get_loaded_environment(*, environment_source=None, driver_context=None)`;
  - CLI `--environment-source` (dest `environment_source`);
  - OpenFOAM: `load_openfoam_environment(*, bashrc_path=None, base_env=None, driver_context=None, timeout_s=20.0)`, `discover_openfoam_bashrc(*, bashrc_path=None, base_env=None)`, `_environment_diagnostics(workflow_dag, *, env=None, bashrc_path=None, driver_context=None)`.

- [ ] **Step 1: Set up the worktree and venvs** (`N=core-gen-a1`).

- [ ] **Step 2: Write the failing tests**

  `git mv packages/omnidriver/tests/core/test_cli_environment_bashrc_flag.py packages/omnidriver/tests/core/test_cli_environment_source_flag.py`, then replace its content:
  ```python
  """The environment-sourcing flag is --environment-source, opaque to core
  (spec 2026-09-26-core-generality-design.md §2, A1). It was
  --openfoam-bashrc, then --environment-bashrc; both names are gone, not
  aliased: this codebase has no external callers to protect yet."""

  from __future__ import annotations

  import pytest

  from omnidriver.cli import build_parser


  def _parse(argv: list[str]):
      return build_parser().parse_args(argv)


  def test_the_flag_sets_environment_source() -> None:
      args = _parse(["plan", "--entry", "x", "--environment-source", "anything the plugin reads"])
      assert args.environment_source == "anything the plugin reads"


  def test_no_flag_leaves_environment_source_none() -> None:
      assert _parse(["plan", "--entry", "x"]).environment_source is None


  @pytest.mark.parametrize("old", ["--environment-bashrc", "--openfoam-bashrc"])
  def test_the_old_flag_names_are_not_recognised(old: str) -> None:
      with pytest.raises(SystemExit):
          _parse(["plan", "--entry", "x", old, "/path/to/bashrc"])
  ```

  `packages/omnidriver/tests/core/test_environment_source_is_opaque.py`:
  ```python
  """Core passes the environment source through, unread and unchanged
  (spec 2026-09-26-core-generality-design.md §2, A1)."""
  from __future__ import annotations

  import pytest

  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.core.strict_planning import strict_plan
  from plugins.conformance_toy import write_toy_native_case
  from plugins.e2e_record_plugin import E2ERecordPlugin

  _OPAQUE = "not-a-path: {anything} ; what it means is the plugin's"


  class _RecordingPlugin(E2ERecordPlugin):
      def __init__(self) -> None:
          super().__init__()
          self.seen: list[tuple[str, object]] = []

      def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
          self.seen.append(("diagnostics", environment_source))
          return ()

      def get_loaded_environment(self, *, environment_source=None, driver_context=None):
          self.seen.append(("load", environment_source))
          return super().get_loaded_environment(environment_source=environment_source, driver_context=driver_context)


  def test_the_preflight_adapter_hands_the_value_over_unchanged():
      plugin = _RecordingPlugin()
      ctx = driver_context(plugin, source="test")
      ctx.capabilities.environment_preflight.diagnostics(None, environment_source=_OPAQUE, driver_context=ctx)
      ctx.capabilities.environment_preflight.load(environment_source=_OPAQUE, driver_context=ctx)
      assert plugin.seen == [("diagnostics", _OPAQUE), ("load", _OPAQUE)]


  def test_strict_plan_threads_it_to_the_plugin_unchanged(tmp_path):
      plugin = _RecordingPlugin()
      ctx = driver_context(plugin, source="test")
      cases_root = tmp_path / "native"
      write_toy_native_case(cases_root)
      strict_plan(
          "toyTutorial", overrides={"cases_root": str(cases_root)}, environment_source=_OPAQUE,
          scratch_root=tmp_path / "scratch", driver_context=ctx,
      )
      assert ("diagnostics", _OPAQUE) in plugin.seen


  @pytest.mark.parametrize("old", ["explicit_bashrc", "environment_bashrc"])
  def test_the_old_keyword_is_refused(old):
      ctx = driver_context(_RecordingPlugin(), source="test")
      with pytest.raises(TypeError, match=old):
          strict_plan("toyTutorial", overrides={}, driver_context=ctx, **{old: "x"})
  ```

  In `test_core_carries_no_cardiac_names.py`, append `"bashrc"` to `_SOLVER_WORDS` and update its comment to say that A1 added it on 2026-09-26.

- [ ] **Step 3: Run them to verify they fail**

  Run: `/tmp/odA-core-gen-a1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_cli_environment_source_flag.py $W/packages/omnidriver/tests/core/test_environment_source_is_opaque.py $W/packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py -v`
  
  Expected:
  - FAIL (`SystemExit`, unrecognised argument): the two flag-setting tests;
  - PASS: `test_the_old_flag_names_are_not_recognised[--openfoam-bashrc]`;
  - FAIL, because the parser still knows the flag: `[--environment-bashrc]`;
  - FAIL with `TypeError: unexpected keyword 'environment_source'`: the adapter and strict_plan tests;
  - FAIL, because `explicit_bashrc` is still accepted: `test_the_old_keyword_is_refused[explicit_bashrc]`;
  - FAIL: the help test, naming `bashrc`.

- [ ] **Step 4: Rename through core**

  `cli.build_parser`, replacing the `--environment-bashrc` argument:
  ```python
      parser.add_argument(
          "--environment-source",
          dest="environment_source",
          default=None,
          help=(
              "An opaque value handed to the active plugin's environment hooks "
              "for strict plan/step/run; core never reads it. What it names is "
              "the plugin's own business (a script to source, or nothing). "
              "Absent, the plugin uses whatever its tool's ambient environment is."
          ),
      )
  ```
  The action check in `main`:
  ```python
      if args.environment_source and args.action not in {"plan", "step", "run"}:
          parser.error(
              "--environment-source is only valid with action=plan, action=step, or action=run"
          )
  ```
  In the rest of `cli.py`, apply this table; each replacement keeps the rest of its line.

  | site | old | new |
  |---|---|---|
  | `_context_from_run_document`: `.load(...)` and `.diagnostics(...)` | `explicit_bashrc=args.environment_bashrc` | `environment_source=args.environment_source` |
  | `_context_from_entry`: signature | `explicit_bashrc: str \| None,` | `environment_source: str \| None,` |
  | `_context_from_entry`: 3 `strict_plan(...)` calls and `.load(...)` | `explicit_bashrc=explicit_bashrc` | `environment_source=environment_source` |
  | `main`: plan `strict_plan`, and the step and run `_context_from_entry` | `explicit_bashrc=args.environment_bashrc` | `environment_source=args.environment_source` |

  `core/strict_planning.py`:
  - in `strict_plan`, `_strict_plan_for_record` and `_strict_plan_for_spec`, replace the parameter `explicit_bashrc: str | Path | None = None` (in `_strict_plan_for_record`: `explicit_bashrc: str | Path | None,`) with `environment_source: str | None = None` (in `_strict_plan_for_record`: `environment_source: str | None,`);
  - replace every `explicit_bashrc=explicit_bashrc` with `environment_source=environment_source`;
  - in `_strict_plan_for_spec`, replace the diagnostics keyword `explicit_bashrc=str(explicit_bashrc) if explicit_bashrc is not None else None,` with `environment_source=environment_source,`. The value passes through unconverted.

  `core/plugin_capabilities.py`, `EnvironmentPreflightCapability`: replace the paragraph starting "``diagnostics`` and ``load`` both take an explicit path" through "...both disprove." with:
  ```
      ``diagnostics`` and ``load`` both take ``environment_source``: one opaque
      string, or ``None``, the operator supplies with ``--environment-source``.
      Core passes it through and never reads it; what it names is the plugin's
      business. The OpenFOAM layer sources it as a shell script; openCARP
      ignores it.

      Renamed 2026-09-26 (spec 2026-09-26-core-generality-design.md §2, A1)
      from ``explicit_bashrc``/``--environment-bashrc``, a shell-profile word
      in a parameter every environment shares. It was ``openfoam_bashrc`` /
      ``--openfoam-bashrc`` before that (future/ENVIRONMENT_CONTRACT.md §10).
      No old name is aliased.
  ```
  The protocol's `diagnostics` signature takes `environment_source: str | None = None,` in place of `explicit_bashrc: str | None = None,`.
  
  `_EnvironmentPreflightAdapter.diagnostics` becomes:
  ```python
      def diagnostics(
          self,
          workflow_dag: dict[str, Any] | None,
          *,
          env: dict[str, str] | None = None,
          environment_source: str | None = None,
          driver_context: Any | None = None,
      ) -> tuple[Any, ...]:
          hook = getattr(self.plugin, "get_environment_diagnostics", None)
          if callable(hook):
              return tuple(hook(
                  workflow_dag, env=env, environment_source=environment_source,
                  driver_context=driver_context,
              ))
          from .compatibility import legacy_environment_diagnostics

          return tuple(legacy_environment_diagnostics(
              workflow_dag, env=env, environment_source=environment_source,
              driver_context=driver_context,
          ))
  ```
  In `_EnvironmentPreflightAdapter.load`:
  - the signature becomes `def load(self, *, environment_source: str | None, driver_context: Any | None) -> dict[str, str]:`;
  - its two calls pass `environment_source=environment_source`. The docstring is unchanged.

  `core/plugin_interface.py`:
  ```python
      def get_environment_diagnostics(
          self, workflow_dag, *, env=None, environment_source=None, driver_context=None,
      ) -> tuple[Any, ...]:
          """Preflight the runtime environment a plan's workflow_dag will run
          in. Absent -> no adapter-specific environment evidence is claimed.
          ``environment_source`` is the operator's opaque ``--environment-source``
          value; this plugin decides what it means (renamed from
          ``explicit_bashrc`` 2026-09-26, spec A1)."""
          ...
  ```
  and
  ```python
      def get_loaded_environment(
          self, *, environment_source: str | None, driver_context: Any,
      ) -> dict[str, str]:
          """Build the execution environment from scratch, e.g. by sourcing
          whatever ``environment_source`` names. Distinct from
          ``get_configured_environment``, which overlays a plugin contract onto
          an environment that already exists.

          Absent -> the current process environment is used unchanged."""
          ...
  ```

  `core/compatibility.py`:
  ```python
  @_instrumented
  def legacy_environment_diagnostics(
      workflow_dag, *, env=None, environment_source=None, driver_context=None,
  ) -> tuple:
  ```
  with `del workflow_dag, env, environment_source, driver_context` in the body; the rest of the body is unchanged. And:
  ```python
  @_instrumented
  def legacy_load_environment(*, environment_source, driver_context) -> dict:
  ```
  with `del environment_source, driver_context`.

  `core/runtime/generic_case.py`: delete the parameter entirely.
  - `_normalize_case_specs`: delete the `explicit_bashrc` parameter, the payload's `"explicit_bashrc": ...` entry, `item_bashrc = item.get("explicit_bashrc")`, and the per-case `"explicit_bashrc": (...)` entry.
  - `make_spec`: delete `explicit_bashrc: str | Path | None = None,` and `explicit_bashrc=explicit_bashrc,` in its `_normalize_case_specs(...)` call.

- [ ] **Step 5: Rename through every plugin**

  `openfoam/openfoam_environment.py`:
  - rename the keyword `explicit_bashrc` to `bashrc_path` in `_candidate_bashrcs`, `discover_openfoam_bashrc` and `load_openfoam_environment`. That covers their signatures, bodies and internal calls. The error becomes `error=f"OpenFOAM bashrc not found: {bashrc_path}"`.

  `openfoam/environment_preflight.py::_environment_diagnostics`:
  - the parameter becomes `bashrc_path: str | None = None,`;
  - its call becomes `load_openfoam_environment(bashrc_path=bashrc_path, driver_context=driver_context)`;
  - the diagnostic becomes `field=loaded_environment.bashrc or bashrc_path or "",`.

  `openfoam/environment.py`:
  ```python
      def get_environment_diagnostics(
          self, workflow_dag, *, env=None, environment_source=None, driver_context=None,
      ):
          """``environment_source`` is, for OpenFOAM, a bashrc to source."""
          from .environment_preflight import _environment_diagnostics

          return _environment_diagnostics(
              workflow_dag,
              env=env,
              bashrc_path=environment_source,
              driver_context=driver_context,
          )
  ```
  and
  ```python
      def get_loaded_environment(self, *, environment_source=None, driver_context=None):
          """``environment_source`` is, for OpenFOAM, a bashrc to source."""
          from .openfoam_environment import load_openfoam_environment

          return dict(
              load_openfoam_environment(
                  bashrc_path=environment_source,
                  driver_context=driver_context,
              ).env
          )
  ```

  `cardiacfoam/cardiacfoam_plugin.py::get_loaded_environment`:
  ```python
      def get_loaded_environment(self, *, environment_source=None, driver_context=None):
          """Resolve this plugin's configured bashrc, then source it via OpenFOAM.

          ``environment_source``, when supplied, is the bashrc to source;
          absent, this plugin's configured one (``runtime_profile
          .configured_openfoam_bashrc``) is used. ``get_loaded_environment``
          is ``single`` in `provider_stack.py` (first non-``None``,
          most-specific provider first), so this provider resolves the bashrc
          itself rather than rely on the generic OpenFOAM provider to ask it.
          """
          from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

          if environment_source is None:
              import os

              from omnidriver.cardiacfoam.runtime_profile import (
                  configured_openfoam_bashrc,
              )

              environment_source = configured_openfoam_bashrc(os.environ)

          return OpenFOAMEnvironmentPlugin().get_loaded_environment(
              environment_source=environment_source,
              driver_context=driver_context,
          )
  ```

  `cardiacfoam/dict_builder.py::build_and_launch`:
  - delete `explicit_bashrc=openfoam_bashrc,` from the `make_spec(...)` call (`generic_case` no longer takes it);
  - replace `load_openfoam_environment(explicit_bashrc=openfoam_bashrc)` with `load_openfoam_environment(bashrc_path=openfoam_bashrc)`.

  `opencarp/plugin.py`:
  ```python
      def get_environment_diagnostics(self, workflow_dag, *, env=None, environment_source=None, driver_context=None):
          del environment_source, driver_context      # openCARP needs no environment source (evidence A4-A8)
          return opencarp_environment_diagnostics(workflow_dag, env if env is not None else os.environ)

      def get_loaded_environment(self, *, environment_source=None, driver_context=None):
          del environment_source, driver_context
          return dict(os.environ)
  ```

  Test plugins: in `declared_case_plugin.py`, `e2e_record_plugin.py` and `conformance_toy.py`, change the four hook signatures:
  - `explicit_bashrc=None` becomes `environment_source=None`;
  - each `del ... explicit_bashrc ...` becomes `del ... environment_source ...`.
  
  The four hooks are `get_environment_diagnostics`/`get_loaded_environment` in the first two, and `SilentPreflightPlugin`/`AuxiliaryOnlyPreflightPlugin` in `conformance_toy.py`.

  Tests:

  | file | change |
  |---|---|
  | `test_core_generic_case.py` | replace `test_explicit_bashrc_kwarg_reaches_case_params` with `test_generic_case_takes_no_environment_parameter` (below); in `test_per_case_openfoam_bashrc_key_is_silently_unused` replace `assert case.params["explicit_bashrc"] is None` with `assert "explicit_bashrc" not in case.params` |
  | `test_strict_plan_contract.py` | `explicit_bashrc="/no/such/openfoam/bashrc"` becomes `environment_source="/no/such/openfoam/bashrc"`; `"--environment-bashrc"` becomes `"--environment-source"` |
  | `test_coverage_blocks_dispatch.py` (×2), `test_cli_config_plugin_context.py`, `test_scratch_root_is_supplied.py` | `explicit_bashrc=None` becomes `environment_source=None` |
  | `test_generic_plugin_execution.py` | `environment_bashrc=None` becomes `environment_source=None` |
  | `test_wheel_install_imports.py` | in the two generated source lines, `explicit_bashrc=None` becomes `environment_source=None` |
  | openfoam `test_case_dict_keys.py` (×2) | `explicit_bashrc="/no/such/openfoam/bashrc"` becomes `environment_source="/no/such/openfoam/bashrc"` |
  | openfoam `test_environment_preflight.py`, `test_code_contract_repairs.py`, `test_apply_through_the_channel.py` | `load_openfoam_environment(explicit_bashrc=bashrc` becomes `load_openfoam_environment(bashrc_path=bashrc` |
  | cardiacfoam `test_strict_planning.py` (×2) | `explicit_bashrc="/no/such/openfoam/bashrc"` becomes `environment_source="/no/such/openfoam/bashrc"` |
  | cardiacfoam `test_environment_preflight_composition.py` | `explicit_bashrc=str(bashrc)` becomes `environment_source=str(bashrc)` |
  | cardiacfoam `fixtures/reference_experiments/niederer_tissue.json`, `single_cell_tworld.json` | `"--environment-bashrc"` becomes `"--environment-source"` |
  | cardiacfoam `test_reference_experiment_manifests.py` | `["--environment-bashrc", "{openfoam_bashrc}"]` becomes `["--environment-source", "{openfoam_bashrc}"]` |

  ```python
  def test_generic_case_takes_no_environment_parameter(tmp_path: Path) -> None:
      """A1 (2026-09-26): the environment source is the plugin's, passed at
      plan and run time; a generic case never stored it (it was dead data)."""
      import pytest

      assert "explicit_bashrc" not in _spec(tmp_path).build_cases()[0].params
      with pytest.raises(TypeError, match="explicit_bashrc"):
          _spec(tmp_path, explicit_bashrc="/opt/openfoam/etc/bashrc")
  ```

- [ ] **Step 6: Edit the shape baseline down**

  Delete these six lines from `scripts/core-shape-baseline.txt`, and nothing else: `cli.py bashrc 26`, `core/compatibility.py bashrc 4`, `core/plugin_capabilities.py bashrc 11`, `core/plugin_interface.py bashrc 2`, `core/runtime/generic_case.py bashrc 14`, `core/strict_planning.py bashrc 12`. Do not run `--write-baseline`.
  
  Then run `cd $W && /tmp/odA-core-gen-a1/bin/python scripts/check-core-shape.py`. Expected: exit 0, no output.
  - A `GREW`/`NEW` line means a rename introduced a token; fix the code, not the baseline.
  - A `shrank ... bashrc` line means a `bashrc` string survives in a non-docstring; find it with the grep below.

- [ ] **Step 7: Run the tests and the grep gates**

  ```bash
  /tmp/odA-core-gen-a1/bin/python -m pytest $W/packages/omnidriver/tests/core/test_cli_environment_source_flag.py $W/packages/omnidriver/tests/core/test_environment_source_is_opaque.py $W/packages/omnidriver/tests/core/test_core_carries_no_cardiac_names.py $W/packages/omnidriver/tests/core/test_core_generic_case.py -v
  grep -rn "explicit_bashrc\|environment_bashrc\|environment-bashrc" $W/packages $W/scripts --include='*.py' --include='*.json' --include='*.yaml' --include='*.toml' | grep -v /build/
  ```
  Expected:
  - all tests pass.
  - The grep prints lines only from three test files, each naming an old name to prove it is refused or absent:
    - `test_core_generic_case.py` (`test_generic_case_takes_no_environment_parameter`, `test_per_case_openfoam_bashrc_key_is_silently_unused`);
    - `test_environment_source_is_opaque.py` (the `old` parametrize);
    - `test_cli_environment_source_flag.py` (its docstring and the `old` parametrize).
    
    Nothing under any `src/`, `scripts/` or `fixtures/` may match. `grep ... | grep -v "/tests/"` must print nothing.

- [ ] **Step 8: Record the rename in the environment contract**

  Append to `future/ENVIRONMENT_CONTRACT.md` §10:
  ```
  **2026-09-26 (topic A, A1):** `explicit_bashrc` / `--environment-bashrc` became `environment_source` / `--environment-source`: one opaque value core passes to the plugin's environment hooks and never reads. The OpenFOAM layer sources it as a bashrc (its own helpers now take `bashrc_path`); openCARP ignores it. `generic_case` no longer stores it (it was dead data). No alias.
  ```

- [ ] **Step 9: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0, with the shape gate silent.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A1: `explicit_bashrc`/`--environment-bashrc` renamed `environment_source`/`--environment-source` in every hook, adapter, CLI path and test; removed from `generic_case`; OpenFOAM's own helpers take `bashrc_path` | a shell-profile word named a parameter every environment shares | neutral: core passes the value through unchanged (`test_environment_source_is_opaque.py`); the shape baseline loses all six `bashrc` lines (69 hits) |
  ```
  ```bash
  git -C $W add -A packages scripts future/ENVIRONMENT_CONTRACT.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: the environment source is opaque to core (A1)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Land on `main` by fast-forward.

---

### A2 as three tasks

The A2 blast radius is about 40 files. It spans:
- a persisted run-document schema key;
- the utility-manifest TOML;
- cardiacfoam's artifact predictor;
- five core runtime modules;
- a provenance capability signature.

A one-shot rename would put every OpenFOAM behaviour at risk in a single commit, with no way to see which part broke. So it lands in three commits, each green. All three run in worktree `core-gen-a2`, one after another.

**The vocabulary-only rule for A2's existing tests.** Tasks 6–8 edit these tests:
- `test_reconciler.py`, `test_workflow_runner.py`, `test_artifact_freshness.py`, `test_sweep_runner.py`, `test_provenance_inputs.py`, `test_data_artifact.py`, `test_models_artifact_json.py`, `test_artifacts_predictor.py`, `test_fresh.py`;
- openfoam `test_case_runtime_conventions.py` and `test_provenance_integration.py`;
- cardiacfoam `test_manufactured_bath_bidomain_tet.py`.

In those files, a change may rename vocabulary only: an identifier, a keyword, a placeholder or a field name. No expected value, path, count or assertion changes. That is what lets them prove OpenFOAM's behaviour is unchanged. The reviewer checks it with `git diff --word-diff` on those files.

Where a test's *fake plugin* changes shape (Task 8), what it asserts about which files are walked stays byte-identical.

### Task 6: A2a, instance directories and `{instance}`

**Shared core files touched:** `sweep_runner.py`, `plugin_capabilities.py`, `tutorial_records.py` (docstring). So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Files:**
- Create: `packages/omnidriver/tests/core/test_instance_directories.py`
- Modify, core:
  - `core/plugin_capabilities.py` (`CaseRuntimeConventions`)
  - `core/runtime/models.py`
  - `schemas/run-document.json` (the packaged copy under `packages/omnidriver/src/omnidriver/`, and the repo-root copy)
  - `core/utility_catalog.py`
  - `core/runtime/artifacts.py`
  - `core/runtime/reconciler.py`
  - `core/runtime/workflow_runner.py` (`_artifact_snapshot`)
  - `core/runtime/sweep_runner.py`
  - `cli.py`, `core/runtime/resume.py` (their reconciler calls)
  - `core/tutorial_records.py` (the `WorkflowStep` docstring)
- Modify, plugins:
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_runtime_conventions.py`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/artifacts_predictor.py`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/utilities/runPurkinjeGraph/utility.manifest.toml`
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/utilities/recomputePseudoECG/utility.manifest.toml`
- Modify: `scripts/export-utility-catalog.py`.
- Modify: the vocabulary-only tests listed above that name time, and `packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py` (one new test).

**Interfaces:**
- Produces:
  - `CaseRuntimeConventions.instance_directory_pattern: str | None = None` and `.preserved_instance_names: tuple[str, ...] = ()`. They replace `time_directory_name_pattern` and `preserved_time_directory_names`;
  - `DataArtifact.instance_indexed: bool = False`, replacing `time_indexed`, and the same on `utility_catalog.ProducesEntry`;
  - the placeholder `{instance}`, replacing `{time}`; `_KNOWN_PATH_PLACEHOLDERS == {"case_id", "instance"}`;
  - `expand_path_pattern(pattern, *, case_id=None, instance=None)`;
  - `reconciler.declared_instance_names(case_root, *, driver_context) -> tuple[str, ...]`, replacing `declared_time_directory_names`;
  - `reconcile_artifacts(case_root, predicted, *, case_id=None, instance_names=())`;
  - `sweep_runner._is_declared_generated_instance(name, conventions) -> bool` and `_clean_stale_instances(case_root, *, conventions) -> None`;
  - run-document JSON key `instance_indexed`, and utility-manifest TOML key `instance_indexed`.

- [ ] **Step 1: Set up the worktree and venvs** (`N=core-gen-a2`, from `main` after Task 5).

- [ ] **Step 2: Write the failing tests**

  `packages/omnidriver/tests/core/test_instance_directories.py`:
  ```python
  """Instance directories are plugin-declared vocabulary
  (spec 2026-09-26-core-generality-design.md §2, A2). A stack that declares
  none (openCARP) has none; a stack that declares a pattern gets exactly
  what that pattern matches."""
  from __future__ import annotations

  from pathlib import Path

  import pytest

  from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.core.runtime.models import DataArtifact, expand_path_pattern
  from omnidriver.core.runtime.reconciler import declared_instance_names, reconcile_artifacts
  from omnidriver.core.runtime.sweep_runner import _clean_stale_instances
  from plugins.minimal_plugin import MinimalTestPlugin

  _DECLARED = CaseRuntimeConventions(instance_directory_pattern=r"^step-\d+$", preserved_instance_names=("step-0",))


  class _DeclaresInstances(MinimalTestPlugin):
      def get_case_runtime_conventions(self):
          return _DECLARED


  def _dirs(root: Path, *names: str) -> None:
      for name in names:
          (root / name).mkdir(parents=True)
          (root / name / "out.dat").write_text(name)


  _ARTIFACT = DataArtifact(artifact_id="a", path_pattern="{instance}/out.dat", format="x", instance_indexed=True)


  def test_a_stack_that_declares_no_instances_has_none(tmp_path):
      _dirs(tmp_path, "0", "0.5", "step-1")
      ctx = driver_context(MinimalTestPlugin(), source="test")
      names = declared_instance_names(tmp_path, driver_context=ctx)
      assert names == ()
      assert reconcile_artifacts(tmp_path, (_ARTIFACT,), instance_names=names).missing_count == 1


  def test_declared_instances_are_exactly_what_the_plugins_pattern_matches(tmp_path):
      _dirs(tmp_path, "0", "step-0", "step-1", "step-x")
      ctx = driver_context(_DeclaresInstances(), source="test")
      names = declared_instance_names(tmp_path, driver_context=ctx)
      assert names == ("step-0", "step-1")
      report = reconcile_artifacts(tmp_path, (_ARTIFACT,), instance_names=names)
      assert sorted(Path(m["path"]).parent.name for m in report.artifacts[0]["matched_files"]) == ["step-0", "step-1"]


  def test_cleaning_removes_generated_instances_and_keeps_preserved_ones(tmp_path):
      _dirs(tmp_path, "step-0", "step-1", "0.5")
      _clean_stale_instances(tmp_path, conventions=_DECLARED)
      assert sorted(p.name for p in tmp_path.iterdir()) == ["0.5", "step-0"]


  def test_a_stack_that_declares_no_instances_cleans_nothing(tmp_path):
      _dirs(tmp_path, "0", "0.5")
      _clean_stale_instances(tmp_path, conventions=CaseRuntimeConventions())
      assert sorted(p.name for p in tmp_path.iterdir()) == ["0", "0.5"]


  def test_the_time_vocabulary_is_gone():
      with pytest.raises(ValueError, match="time"):
          DataArtifact(artifact_id="a", path_pattern="{time}/x", format="x")
      assert expand_path_pattern("{instance}/x", instance="7") == "7/x"
      assert not hasattr(DataArtifact(artifact_id="a", path_pattern="x", format="x"), "time_indexed")
      assert not hasattr(CaseRuntimeConventions(), "time_directory_name_pattern")
  ```

  In `packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py`:
  - add `from omnidriver.core.runtime.reconciler import declared_instance_names`;
  - append:
  ```python
  def test_openfoam_time_directories_are_its_instances(tmp_path: Path) -> None:
      """OpenFOAM declares its numeric time directories as instances, and
      "0" as preserved (spec 2026-09-26 A2): byte-for-byte the old rule."""
      for name in ("0", "0.001", "1e-05", "constant", "processor0", "postProcessing"):
          (tmp_path / name).mkdir()
      assert declared_instance_names(tmp_path, driver_context=openfoam_environment_context()) == ("0", "0.001", "1e-05")
      assert openfoam_case_runtime_conventions().preserved_instance_names == ("0",)
  ```

  Run: `/tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_instance_directories.py $W/packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py -v`
  
  Expected: `ImportError: cannot import name 'declared_instance_names'` (a collection error in both files).

- [ ] **Step 3: Rename the conventions and the artifact vocabulary**

  `core/plugin_capabilities.py`, `CaseRuntimeConventions`: replace the two time fields with:
  ```python
      #: Regex a case-root directory name matches when it is one of the
      #: solver's output instances (OpenFOAM: a time directory). ``None``: the
      #: environment declares no instances, and core treats no directory as
      #: one. Renamed 2026-09-26 from ``time_directory_name_pattern`` (spec A2).
      instance_directory_pattern: str | None = None
      #: Instance names that are authored input and never cleaned (OpenFOAM:
      #: ``"0"``). Renamed 2026-09-26 from ``preserved_time_directory_names``.
      preserved_instance_names: tuple[str, ...] = ()
  ```
  In its docstring, replace "rules for numeric time directories" with "rules for which directories are output instances (for OpenFOAM, numeric time directories)".

  `core/runtime/models.py`:
  - in the `DataArtifact` docstring, the recognised placeholders are "``{case_id}`` (the sweep case identifier) and ``{instance}`` (one of the environment's declared instance directories; for OpenFOAM, a time directory)";
  - the `path_pattern` field docstring becomes `"""Case-relative path; may contain ``{case_id}`` / ``{instance}`` placeholders."""`;
  - the field becomes:
  ```python
      instance_indexed: bool = False
      """True for an output written once per solver-declared instance (for
      OpenFOAM, a time directory). ``path_pattern`` then contains
      ``{instance}``, which reconciliation substitutes with each directory the
      environment's ``CaseRuntimeConventions.instance_directory_pattern``
      matches. Renamed from ``time_indexed`` 2026-09-26 (spec
      2026-09-26-core-generality-design.md §2, A2)."""
  ```
  - `_KNOWN_PATH_PLACEHOLDERS: Final[frozenset[str]] = frozenset({"case_id", "instance"})`;
  - `expand_path_pattern`: the signature becomes `(pattern: str, *, case_id: str | None = None, instance: str | None = None) -> str`, and `values = {"case_id": case_id, "instance": instance}`. In the docstring, `{time}` becomes `{instance}` and `time=` becomes `instance=`;
  - `data_artifact_from_json`: `instance_indexed=bool(data.get("instance_indexed", False)),`.

  Both `run-document.json` schemas: in `dataArtifact.properties`, `"time_indexed": {"type": "boolean"}` becomes `"instance_indexed": {"type": "boolean"}`. This is a **run-document schema change**: a document written before this commit with `time_indexed` no longer validates, because `additionalProperties` is false. It is pre-publication, so there is no migration.

  `core/utility_catalog.py`:
  - in the module docstring, `{time}` becomes `{instance}`, and `time_indexed  (bool, default False)` becomes `instance_indexed  (bool, default False)`;
  - in the allowed-key set, `"time_indexed",` becomes `"instance_indexed",`;
  - the `ProducesEntry` field becomes `instance_indexed: bool = False` with docstring `"""True for an output written once per declared instance (renamed from time_indexed 2026-09-26, spec A2)."""`, and the path_pattern docstring `{time}` becomes `{instance}`;
  - the parser line becomes `instance_indexed=bool(raw.get("instance_indexed", False)),`.
  
  A manifest that still says `time_indexed` is refused by the existing unknown-key check. That is intended: no alias.

  `core/runtime/artifacts.py`: `instance_indexed=entry.instance_indexed,`. `scripts/export-utility-catalog.py`: `"instance_indexed": pr.instance_indexed,`.

  The TOML manifests:
  - `runPurkinjeGraph`: `path_pattern = "{instance}/"` and `instance_indexed = true`;
  - `recomputePseudoECG`: `instance_indexed = false`.

  `core/tutorial_records.py`, `WorkflowStep` docstring: `the ``{case_id}``/``{time}`` placeholders are not supported here` becomes `the ``{case_id}``/``{instance}`` placeholders are not supported here`.

- [ ] **Step 4: Rename the consumers**

  `core/runtime/reconciler.py`:
  - module docstring: `{time}` becomes `{instance}`; the directories bullet now reads that predictors emit `path_pattern="{instance}"`, an environment-declared instance directory itself; "Time-indexed iteration receives time directory names" becomes "Instance-indexed iteration receives instance directory names";
  - `declared_time_directory_names` is replaced by:
  ```python
  def declared_instance_names(case_root: Path, *, driver_context) -> tuple[str, ...]:
      """The case's instance directories, only when the environment declares their form."""
      if driver_context is None:
          return ()
      conventions = driver_context.capabilities.case_runtime_conventions.conventions()
      if conventions.instance_directory_pattern is None:
          return ()
      pattern = re.compile(conventions.instance_directory_pattern)
      return tuple(sorted(
          child.name for child in case_root.iterdir()
          if child.is_dir() and pattern.match(child.name)
      ))
  ```
  - in `_reconcile_artifact`, the keyword becomes `instance_names: tuple[str, ...]` and the body:
  ```python
      if artifact.instance_indexed:
          for instance_name in instance_names:
              resolved = artifact.path_pattern.replace("{instance}", instance_name)
              resolved = _substitute_case_id(resolved, case_id)
              matched_files.extend(_glob_under(case_root, resolved))
      else:
          resolved = _substitute_case_id(artifact.path_pattern, case_id)
          # Defensive: a pattern that is not instance-indexed shouldn't contain
          # {instance}, but if it does, accept any instance name via wildcard.
          resolved = resolved.replace("{instance}", "*")
          matched_files.extend(_glob_under(case_root, resolved))
  ```
  - in `reconcile_artifacts`, the keyword becomes `instance_names: Iterable[str] = (),`, the docstring arg becomes "instance_names: environment-declared names available for an ``{instance}`` artifact. The neutral default is empty.", and the body is `declared_instances = tuple(sorted(set(instance_names)))` passed as `instance_names=declared_instances`.

  `cli.py` (the artifact-reconciliation helper) and `core/runtime/resume.py`:
  - import `declared_instance_names` in place of `declared_time_directory_names`;
  - the call becomes `instance_names=declared_instance_names(case_root, driver_context=driver_context),`.

  `core/runtime/workflow_runner.py::_artifact_snapshot`:
  - `expanded = artifact.path_pattern.format(case_id=case_root.name, instance="*")`;
  - `if artifact.instance_indexed:`;
  - docstring: "Instance-indexed contracts accept both serial and decomposed locations."

  `core/runtime/sweep_runner.py`: replace the two helpers:
  ```python
  def _is_declared_generated_instance(name: str, conventions) -> bool:
      """Apply the environment's declared instance-directory rule without naming it."""
      pattern = conventions.instance_directory_pattern
      return (
          pattern is not None
          and name not in conventions.preserved_instance_names
          and re.match(pattern, name) is not None
      )


  def _clean_stale_instances(case_root: Path, *, conventions) -> None:
      """Remove prior generated instance directories when the environment declares them.

      Entry-based sweeps reuse one shared case_root across cases (see
      _materialize_entry_case's docstring). A case with no authored initial
      instance can otherwise consume a prior run's generated one. Clearing
      declared generated instances before materialization prevents that
      stale-state reuse. Renamed 2026-09-26 from _clean_stale_time_directories (spec A2).
      """
      if conventions.instance_directory_pattern is None or not case_root.is_dir():
          return
      for child in case_root.iterdir():
          if child.is_dir() and _is_declared_generated_instance(child.name, conventions):
              shutil.rmtree(child)
  ```
  Then:
  - `_materialize_entry_case` calls `_clean_stale_instances(spec.case_root, conventions=conventions)`;
  - `_stage_entry_case`'s last check becomes `if _is_declared_generated_instance(path.name, conventions):`.

  `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_runtime_conventions.py`, the last two lines:
  ```python
          instance_directory_pattern=r"^-?\d+(\.\d+)?(e[+\-]?\d+)?$",
          preserved_instance_names=("0",),
  ```
  Values unchanged: OpenFOAM's instances are exactly its old time directories.

  `cardiacfoam/artifacts_predictor.py`:
  - rename `_time_indexed_field_artifact` to `_instance_indexed_field_artifact` (the definition and five call sites);
  - `path_pattern=f"{{time}}/{field_name}"` becomes `path_pattern=f"{{instance}}/{field_name}"`, and `path_pattern=f"{{time}}/{var}"` becomes `path_pattern=f"{{instance}}/{var}"`;
  - every `time_indexed=` becomes `instance_indexed=`.
  
  The artifact `format="openfoam_time_dirs"` is cardiacFOAM's own format vocabulary and stays.

  The vocabulary-only tests: apply exactly these renames and nothing else.

  | old | new |
  |---|---|
  | `{time}` | `{instance}` |
  | `time_indexed` | `instance_indexed` |
  | `time_directory_names=` | `instance_names=` |
  | `declared_time_directory_names` | `declared_instance_names` |
  | `time_directory_name_pattern=` | `instance_directory_pattern=` |
  | `preserved_time_directory_names=` | `preserved_instance_names=` |
  | `time=` (in `expand_path_pattern(...)` calls) | `instance=` |
  | `_clean_stale_time_directories` / `_is_declared_generated_time_directory` | `_clean_stale_instances` / `_is_declared_generated_instance` |

  Test *function names* that say "time" may stay: they describe OpenFOAM's case, which is still time directories.

- [ ] **Step 5: Run the tests and the grep gate**

  ```bash
  /tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_instance_directories.py $W/packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py $W/packages/omnidriver/tests/core/test_reconciler.py $W/packages/omnidriver/tests/core/test_workflow_runner.py $W/packages/omnidriver/tests/core/test_artifact_freshness.py $W/packages/omnidriver/tests/core/test_sweep_runner.py $W/packages/omnidriver/tests/core/test_data_artifact.py $W/packages/omnidriver/tests/core/test_models_artifact_json.py $W/packages/omnidriver/tests/core/test_artifacts_predictor.py $W/packages/omnidriver/tests/core/test_fresh.py $W/packages/omnidriver-cardiacfoam/tests/test_artifacts_predictor.py $W/packages/omnidriver-cardiacfoam/tests/test_utility_catalog_export.py $W/packages/omnidriver-cardiacfoam/tests/test_manufactured_bath_bidomain_tet.py -q
  grep -rn "time_indexed\|{time}\|time_directory_name_pattern\|preserved_time_directory_names\|declared_time_directory_names\|time_directory_names\|_clean_stale_time_directories\|_is_declared_generated_time_directory" $W/packages $W/scripts $W/schemas --include='*.py' --include='*.json' --include='*.toml' | grep -v /build/
  git -C $W diff --word-diff -- packages/omnidriver/tests/core/test_reconciler.py packages/omnidriver/tests/core/test_workflow_runner.py packages/omnidriver/tests/core/test_artifact_freshness.py packages/omnidriver/tests/core/test_sweep_runner.py | grep -E "^\[-|\{\+" | head -50
  ```
  Expected:
  - 0 failed.
  - Every line the grep prints is one of these:
    1. the `{time}` refusal and the `time_directory_name_pattern` absence check in `test_instance_directories.py::test_the_time_vocabulary_is_gone`;
    2. a dated "Renamed ... from ..." note: in `CaseRuntimeConventions` (2), `DataArtifact.instance_indexed`, `ProducesEntry.instance_indexed`, and `_clean_stale_instances`.
    
    Any other line is a surviving use. Fix it.
  - The word-diff shows only the renames in the table.

- [ ] **Step 6: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0. V4 includes the cardiacFOAM real runs, whose reconciliation now goes through `{instance}`.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A2a: instance directories -- `CaseRuntimeConventions.instance_directory_pattern`/`preserved_instance_names` replace the time-directory fields; `DataArtifact.instance_indexed` and the `{instance}` placeholder replace `time_indexed`/`{time}` (run-document schema and utility-manifest key renamed); `reconciler.declared_instance_names`, `sweep_runner._clean_stale_instances` | core named OpenFOAM's time directories; openCARP has none | neutral: OpenFOAM declares the same regex and `"0"`, and the vocabulary-only tests keep every assertion; a stack declaring none has none (`test_instance_directories.py`) |
  ```
  ```bash
  git -C $W add -A packages scripts schemas docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: outputs are plugin-declared instances, {instance} replaces {time} (A2a)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Land on `main` by fast-forward.

---

### Task 7: A2b, replica directories

**Shared core files touched:** `sweep_runner.py`, `registry.py`, `plugin_capabilities.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Files:**
- Create: `packages/omnidriver/tests/core/test_replica_directories.py`
- Modify, core:
  - `core/plugin_capabilities.py` (`CaseRuntimeConventions`)
  - `core/plugin_profile.py` (`decomposition_dirname_prefix` becomes `replica_directory_globs`, plus `is_replica_directory_name`)
  - `core/runtime/sweep_runner.py` (`_stage_entry_case`)
  - `core/runtime/workflow_runner.py` (`_artifact_snapshot`)
  - `core/runtime/registry.py` (`_iter_case_directories_recursive`)
  - `core/runtime/provenance_inputs.py` (the replica walk)
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_runtime_conventions.py`.
- Modify, tests (vocabulary only): `test_provenance_inputs.py`, `test_artifact_freshness.py`, `test_workflow_runner.py`, `test_sweep_runner.py`, and openfoam `test_case_runtime_conventions.py` (one assertion added).
- Modify: `scripts/core-shape-baseline.txt` (delete the `processor` line).

**Interfaces:**
- Produces:
  - `CaseRuntimeConventions.replica_directory_globs: tuple[str, ...] = ()`, replacing `decomposition_directory_prefix`;
  - `plugin_profile.replica_directory_globs(driver_context) -> tuple[str, ...]`;
  - `plugin_profile.is_replica_directory_name(name: str, globs: tuple[str, ...]) -> bool`, which matches with `fnmatch.fnmatchcase`.
- Equivalence: `fnmatchcase(name, "processor*")` holds exactly when `name.startswith("processor")`, because `*` matches any run of characters, including none, and `processor` has no glob metacharacters. Where the old code globbed `f"{prefix}*"`, the new code globs `"processor*"`: the identical pattern.

- [ ] **Step 1: Write the failing tests**

  `packages/omnidriver/tests/core/test_replica_directories.py`:
  ```python
  """Replica directories are plugin-declared vocabulary
  (spec 2026-09-26-core-generality-design.md §2, A2). A stack that declares
  none (openCARP) treats a processor0/ like any other directory."""
  from __future__ import annotations

  from pathlib import Path

  from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
  from omnidriver.core.plugin_interface import driver_context
  from omnidriver.core.plugin_profile import is_replica_directory_name
  from omnidriver.core.runtime.registry import list_entries
  from omnidriver.core.runtime.sweep_runner import _stage_entry_case
  from plugins.minimal_plugin import MinimalTestPlugin


  class _DeclaresReplicas(MinimalTestPlugin):
      def get_case_runtime_conventions(self):
          return CaseRuntimeConventions(replica_directory_globs=("rank*",))


  def _source(tmp_path: Path) -> Path:
      source = tmp_path / "source"
      for relpath in ("rank0/f", "processor0/f", "input.txt"):
          (source / relpath).parent.mkdir(parents=True, exist_ok=True)
          (source / relpath).write_text(relpath)
      return source


  def test_the_name_rule_is_the_declared_globs():
      assert is_replica_directory_name("processor12", ("processor*",))
      assert not is_replica_directory_name("postProcessing", ("processor*",))
      assert not is_replica_directory_name("processor0", ())


  def test_a_stack_that_declares_no_replicas_stages_every_directory(tmp_path):
      staged = tmp_path / "staged"
      _stage_entry_case(_source(tmp_path), staged, driver_context=driver_context(MinimalTestPlugin(), source="test"))
      assert (staged / "processor0" / "f").is_file() and (staged / "rank0" / "f").is_file()


  def test_declared_replicas_are_not_staged(tmp_path):
      staged = tmp_path / "staged"
      _stage_entry_case(_source(tmp_path), staged, driver_context=driver_context(_DeclaresReplicas(), source="test"))
      assert not (staged / "rank0").exists()
      assert (staged / "processor0" / "f").is_file()


  def test_a_stack_that_declares_no_replicas_discovers_cases_inside_them(tmp_path):
      case_root = tmp_path / "processor0" / "nestedCase"
      case_root.mkdir(parents=True)
      (case_root / "run-case").write_text("")
      ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test")
      assert list_entries(tmp_path, driver_context=ctx) != []
  ```
  In openfoam `test_case_runtime_conventions.py::test_openfoam_hides_parallel_decomposition_output`, add as the first line:
  `assert openfoam_case_runtime_conventions().replica_directory_globs == ("processor*",)`.

  Run: `/tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_replica_directories.py $W/packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py -v`
  
  Expected: `ImportError: cannot import name 'is_replica_directory_name'`, and the openfoam assertion fails with `AttributeError`.

- [ ] **Step 2: Implement**

  `core/plugin_capabilities.py`, `CaseRuntimeConventions`: replace `decomposition_directory_prefix: str | None = None` with:
  ```python
      #: fnmatch globs naming a case-root directory that holds one replica of
      #: the case per parallel rank (OpenFOAM: ``processor*``). Core skips them
      #: when staging and discovering cases, and looks inside them for an
      #: instance-indexed output. Empty: the environment declares no replicas.
      #: Renamed 2026-09-26 from ``decomposition_directory_prefix`` (spec A2).
      replica_directory_globs: tuple[str, ...] = ()
  ```

  `core/plugin_profile.py`:
  - add `import fnmatch`;
  - replace `decomposition_dirname_prefix` with:
  ```python
  def replica_directory_globs(driver_context: Any | None) -> tuple[str, ...]:
      """Parallel-replica directory globs declared by the active environment."""
      if driver_context is None:
          return ()
      return tuple(
          driver_context.capabilities.case_runtime_conventions.conventions()
          .replica_directory_globs
      )


  def is_replica_directory_name(name: str, globs: tuple[str, ...]) -> bool:
      """Whether a case-root directory name is one of the declared replicas."""
      return any(fnmatch.fnmatchcase(name, pattern) for pattern in globs)
  ```

  `core/runtime/sweep_runner.py`:
  - the import becomes `from omnidriver.core.plugin_profile import is_replica_directory_name, replica_directory_globs`;
  - in `_stage_entry_case`, replace the `decomposition_prefix = (...)` block with `replica_globs = replica_directory_globs(driver_context)`;
  - replace the condition `(decomposition_prefix is not None and name.startswith(decomposition_prefix))` with `is_replica_directory_name(name, replica_globs)`.

  `core/runtime/workflow_runner.py`:
  - the import becomes `from ..plugin_profile import replica_directory_globs`;
  - in `_artifact_snapshot`:
  ```python
      if artifact.instance_indexed:
          for replica_glob in replica_directory_globs(driver_context):
              patterns.append(str(case_root / replica_glob / expanded))
  ```

  `core/runtime/registry.py`:
  - the import becomes `is_replica_directory_name, replica_directory_globs,` in place of `decomposition_dirname_prefix,`;
  - in `_iter_case_directories_recursive`, `decomposition_prefix = decomposition_dirname_prefix(driver_context)` becomes `replica_globs = replica_directory_globs(driver_context)`;
  - the filter clause becomes `and not is_replica_directory_name(dirname, replica_globs)`.

  `core/runtime/provenance_inputs.py`:
  - the import becomes `from ..plugin_profile import replica_directory_globs`;
  - replace the replica block with:
  ```python
      if selected_start_time is not None:
          for replica_glob in replica_directory_globs(driver_context):
              for replica_dir in sorted(case_root.glob(replica_glob)):
                  if replica_dir.is_dir():
                      walk_roots.append(replica_dir / selected_start_time)
  ```
  
  Task 8 moves this block into the OpenFOAM layer. It is renamed here so that the old field can be deleted now. `processor_dir` goes, and with it core's last `processor` token.

  `openfoam/case_runtime_conventions.py`: `decomposition_directory_prefix="processor",` becomes `replica_directory_globs=("processor*",),`.

  Tests, vocabulary only: `CaseRuntimeConventions(decomposition_directory_prefix="processor")` becomes `CaseRuntimeConventions(replica_directory_globs=("processor*",))` in `test_artifact_freshness.py`, `test_workflow_runner.py` and `test_sweep_runner.py`.
  
  In `test_provenance_inputs.py`:
  - in `_FakePlugin`, `decomposition_directory_prefix="processor"` becomes `replica_directory_globs=("processor*",)`;
  - `_ForeignEnvironmentPlugin.__init__`: the parameter `decomposition_prefix: str = "processor"` becomes `replica_glob: str = "processor*"`, stored as `self._replica_glob`, and returned as `CaseRuntimeConventions(replica_directory_globs=(self._replica_glob,))`;
  - `test_plugin_implemented_decomposition_prefix_hook_overrides_processor` constructs it with `replica_glob="rank*"`.

  `scripts/core-shape-baseline.txt`: delete the line `core/runtime/provenance_inputs.py	processor	3	...`, by hand.

- [ ] **Step 3: Run the tests, the gate and the grep**

  ```bash
  /tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver/tests/core/test_replica_directories.py $W/packages/omnidriver-openfoam/tests/core/test_case_runtime_conventions.py $W/packages/omnidriver/tests/core/test_provenance_inputs.py $W/packages/omnidriver/tests/core/test_workflow_runner.py $W/packages/omnidriver/tests/core/test_artifact_freshness.py $W/packages/omnidriver/tests/core/test_sweep_runner.py -q
  cd $W && /tmp/odA-core-gen-a2/bin/python scripts/check-core-shape.py
  grep -rn "decomposition_directory_prefix\|decomposition_dirname_prefix\|decomposition_prefix\|processor_dir" $W/packages $W/scripts --include='*.py' | grep -v /build/
  ```
  Expected:
  - 0 failed;
  - the shape gate exits 0 and prints nothing.
  - The grep prints exactly two lines:
    - the dated note "Renamed 2026-09-26 from ``decomposition_directory_prefix``" in `CaseRuntimeConventions`;
    - the test name `test_plugin_implemented_decomposition_prefix_hook_overrides_processor`.
  
  Any other line is a surviving use. Fix it.

- [ ] **Step 4: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A2b: replica directories -- `CaseRuntimeConventions.replica_directory_globs` replaces `decomposition_directory_prefix`; `plugin_profile.replica_directory_globs`/`is_replica_directory_name` replace `decomposition_dirname_prefix` in staging, discovery, step snapshots and provenance | core named OpenFOAM's `processor*` layout | neutral: OpenFOAM declares `("processor*",)`, equivalent to its old prefix; a stack declaring none stages and discovers inside `processor0/` (`test_replica_directories.py`); the shape baseline loses its `processor` line |
  ```
  ```bash
  git -C $W add -A packages scripts docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: parallel replicas are plugin-declared globs (A2b)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Land on `main` by fast-forward.

---

### Task 8: A2c, the provenance hook `input_roots`; core stops knowing "start time"

**Shared core file touched:** `plugin_capabilities.py`. So it lands on `main` as its own small commit, plus a generality-log row in `docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5.

**Files:**
- Modify, core:
  - `core/plugin_capabilities.py` (`CaseIntrospectionCapability` and `_CaseIntrospectionAdapter` lose `selected_start_time`; `CaseProvenanceCapability` and `_CaseProvenanceAdapter` gain `input_roots` and drop the `selected_start_time` argument)
  - `core/plugin_interface.py` (`get_selected_start_time` deleted; `get_input_roots` added; `get_required_inputs`/`get_generated_output_globs` signatures)
  - `core/provider_stack.py` (`_SHAPE`; the module docstring)
  - `core/runtime/provenance_inputs.py`
- Modify, plugins:
  - `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` (`get_selected_start_time` becomes `get_input_roots`)
  - `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/case_provenance.py`, `cardiacfoam_plugin.py`, `plugin.yaml` (comment), `run_document_config.py` (docstring)
  - `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py`
- Modify, tests:
  - `packages/omnidriver/tests/core/test_provenance_inputs.py`
  - `packages/omnidriver/tests/core/test_case_file_contract.py`
  - `packages/omnidriver/tests/core/test_resolution_provenance.py`
  - `packages/omnidriver/tests/core/test_wheel_install_imports.py`
  - `packages/omnidriver/tests/core/test_case_provenance_capability.py`
  - `packages/omnidriver-openfoam/tests/core/test_provenance_integration.py`
  - `packages/omnidriver-cardiacfoam/tests/test_case_provenance_capability.py`
  - `packages/omnidriver-cardiaccore/tests/test_biv_preprocessing_contract.py`
- Modify, docs: `ARCHITECTURE.md` (regenerated table; the `single` examples row), `future/ENVIRONMENT_CONTRACT.md` (a dated note).

**Interfaces:**
- Produces:
  - `CaseProvenanceCapability.input_roots(case_root: Path, resolved_case: dict[str, Any]) -> tuple[str, ...]`, whose hook is `get_input_roots(case_root, resolved_case)`, composed `sequence`;
  - `CaseProvenanceCapability.required_inputs(case_root, resolved_case)` and `.generated_output_globs(case_root, resolved_case)`, with no third argument;
  - `CaseIntrospectionCapability` members `resolve_case_models` and `samplable_fields` only;
  - `OpenFOAMEnvironmentPlugin.get_input_roots(case_root, resolved_case) -> tuple[str, ...]`, which returns the selected start time and `<replica>/<start>` for each directory matching `replica_directory_globs`, sorted.
- Consumes: `plugin_profile.is_replica_directory_name`, `openfoam_case_runtime_conventions().replica_directory_globs` (Task 7).

- [ ] **Step 1: Record the native provenance before the change**

  This parity dump is not committed:
  ```bash
  cat > /tmp/odA-core-gen-a2-provenance.py <<'EOF'
  import json, sys
  from pathlib import Path
  from omnidriver.core.plugin_discovery import load_discovered_plugin
  from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs
  from omnidriver.core.runtime.registry import list_tutorials, load_entry_spec
  root = Path("/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials")
  out = {}
  for stack in ("cardiacfoam", "cardiaccore"):
      ctx = load_discovered_plugin(stack)
      for name in list_tutorials(ctx):
          spec = load_entry_spec(name, overrides={"cases_root": str(root)}, driver_context=ctx)
          components = enumerate_case_inputs(Path(spec.case_root), workflow_dag={"steps": []}, driver_context=ctx)
          out[f"{stack}:{name}"] = [[c.kind, c.path, c.role, c.method, c.strength, getattr(c, "digest", None)] for c in components]
  json.dump(out, open(sys.argv[1], "w"), indent=1, sort_keys=True)
  EOF
  cd $W && /tmp/odA-core-gen-a2/bin/python /tmp/odA-core-gen-a2-provenance.py /tmp/odA-core-gen-a2-provenance-before.json
  ```
  Expected: the file is written, with one key per registered tutorial.

- [ ] **Step 2: Write the characterization test, which passes on today's code**

  Append to `packages/omnidriver-openfoam/tests/core/test_provenance_integration.py`:
  ```python
  def _write(case_root: Path, relpath: str) -> None:
      path = case_root / relpath
      path.parent.mkdir(parents=True, exist_ok=True)
      path.write_text(relpath)


  def test_the_start_time_is_walked_serially_and_in_every_replica(tmp_path: Path) -> None:
      """What an OpenFOAM stack fingerprints from its time and replica
      directories (I9). A characterization: it passes before A2c moves the
      rule out of core, and must pass unchanged after."""
      _write_control_dict(tmp_path, "startFrom startTime;\nstartTime 0;\n")
      for relpath in ("0/Vm", "0.5/Vm", "processor0/0/Vm", "processor0/0.5/Vm", "processor1/0/Vm"):
          _write(tmp_path, relpath)
      included = {c.path for c in _components(tmp_path) if c.kind == "case_file"}
      assert {"0/Vm", "processor0/0/Vm", "processor1/0/Vm"} <= included
      assert not {"0.5/Vm", "processor0/0.5/Vm"} & included
  ```
  Run: `/tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver-openfoam/tests/core/test_provenance_integration.py -v`
  
  Expected: PASS. Today's core walk produces exactly this.

- [ ] **Step 3: Write the failing tests for the hook**

  Append to the same file:
  ```python
  def test_openfoam_declares_its_start_time_and_replicas_as_input_roots(tmp_path: Path) -> None:
      _write_control_dict(tmp_path, "startFrom latestTime;\nstartTime 0;\n")
      for relpath in ("0/Vm", "0.5/Vm", "processor1/0.5/Vm", "processor0/0.5/Vm", "processorX.txt"):
          _write(tmp_path, relpath)
      assert OpenFOAMEnvironmentPlugin().get_input_roots(tmp_path, {}) == ("0.5", "processor0/0.5", "processor1/0.5")
  ```
  In `packages/omnidriver/tests/core/test_provenance_inputs.py`, rewrite the two fakes to declare input roots instead of a start time. `_FakePlugin`:
  - delete `get_selected_start_time`;
  - `get_required_inputs(self, case_root, resolved_case)` and `get_generated_output_globs(self, case_root, resolved_case)` drop the third parameter;
  - add:
  ```python
      def get_input_roots(self, case_root, resolved_case):
          """The toy's state directory "0", serially and in each processor*
          replica: the shape an OpenFOAM stack declares, stated by hand."""
          del resolved_case
          replicas = sorted(p.name for p in Path(case_root).glob("processor*") if p.is_dir())
          return ("0", *(f"{name}/0" for name in replicas))
  ```
  Replace `_ForeignEnvironmentPlugin` with:
  ```python
  class _ForeignEnvironmentPlugin(MinimalTestPlugin):
      """A plugin that declares its input roots without case-file roles."""

      def __init__(self, *, roots: tuple[str, ...]) -> None:
          self._roots = roots

      def get_profile(self) -> PluginProfile:
          return PluginProfile(
              path=Path(__file__),
              plugin_id=self.plugin_id,
              api_version=self.plugin_api_version,
              case_files=(),
              cxx_mapping=None,
              payload={
                  "schema_version": 1,
                  "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                  "case_profile": {"dictionaries": []},
              },
          )

      def get_input_roots(self, case_root, resolved_case):
          return self._roots
  ```
  Then:
  - `test_plugin_implemented_start_time_hook_overrides_the_openfoam_default` constructs `_ForeignEnvironmentPlugin(roots=("0.5",))`. Its assertions are unchanged.
  - Replace `test_start_time_hook_must_return_a_non_empty_string` with:
  ```python
  @pytest.mark.parametrize("bad", ["", ".", "/abs", "../up", 3])
  def test_an_input_root_must_be_a_case_relative_path_inside_the_case(tmp_path: Path, bad) -> None:
      """A blank root would walk the whole case tree (``case_root / ""``); an
      absolute or escaping one would walk outside it. The adapter refuses
      each by name instead."""
      plugin = _ForeignEnvironmentPlugin(roots=(bad,))
      with pytest.raises(TypeError, match="get_input_roots"):
          enumerate_case_inputs(
              tmp_path, workflow_dag={"steps": []}, driver_context=driver_context(plugin, source="test"),
          )
  ```
  - `test_plugin_implemented_decomposition_prefix_hook_overrides_processor` constructs `_ForeignEnvironmentPlugin(roots=("0", "rank0/0"))`. Its assertions are unchanged: `rank0/0/Vm` is in, `processor0/0/Vm` is out.

  In `test_case_file_contract.py::test_minimal_plugin_declares_no_case_files`, replace the `selected_start_time(...) is None` assertion with:
  ```python
      assert context.capabilities.case_provenance.input_roots(Path("case"), {}) == ()
  ```

  In `test_resolution_provenance.py`, replace every `get_selected_start_time` (the fixture methods and the `resolve_with_provenance` member names) with `get_config_value_reader`, another `single`-shaped member. Add a sentence to the module docstring: "Corrected 2026-09-26 (spec A2): the provenance-only tests used `get_selected_start_time`, which left the contract; they use `get_config_value_reader`, also `single`-shaped."

  In `test_wheel_install_imports.py`, replace the generated plugin source's two lines `def get_selected_start_time(self, case_root, resolved_case):` / `return '0'` with `def get_input_roots(self, case_root, resolved_case):` / `return ('0',)`.

  Drop the third positional argument `"0"` from every `required_inputs(...)`/`generated_output_globs(...)` call in these files, and nothing else:
  - `packages/omnidriver/tests/core/test_case_provenance_capability.py`: 4 calls, e.g. `generic.required_inputs(tmp_path, {}, "0")` becomes `generic.required_inputs(tmp_path, {})`;
  - `packages/omnidriver-cardiacfoam/tests/test_case_provenance_capability.py`: 2 calls;
  - `packages/omnidriver-cardiaccore/tests/test_biv_preprocessing_contract.py`: `generated_output_globs(tmp_path, {}, "0")` becomes `generated_output_globs(tmp_path, {})`.

  Run: `/tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver-openfoam/tests/core/test_provenance_integration.py $W/packages/omnidriver/tests/core/test_provenance_inputs.py $W/packages/omnidriver/tests/core/test_case_file_contract.py -v`
  
  Expected: FAIL. `get_input_roots` is not an adapted member yet, so:
  - `OpenFOAMEnvironmentPlugin` has no `get_input_roots` (`AttributeError`);
  - the fake plugins' roots are not walked, so the included-path assertions fail;
  - `case_provenance.input_roots` does not exist.

- [ ] **Step 4: Implement the hook and remove "start time" from core**

  `core/plugin_capabilities.py`, `CaseIntrospectionCapability`:
  - delete the paragraph on ``selected_start_time`` and the `selected_start_time` protocol method;
  - set `:adapts: get_samplable_fields, resolve_case_models`;
  - add to the prose: "Corrected 2026-09-26 (spec A2): this also answered ``selected_start_time``, the directory a run resumes from. That was an OpenFOAM interpretation core only used to walk provenance; the plugin now declares the walk itself, through ``CaseProvenanceCapability.input_roots``."
  
  Delete `_CaseIntrospectionAdapter.selected_start_time`.

  `CaseProvenanceCapability`:
  - replace "Both take the resolved case dictionaries (not just the model name) and the selected start time, because" with "Each takes the resolved case dictionaries (not just the model name), because";
  - add a paragraph: "``input_roots`` names the case-relative directories, beyond the case-file roots, whose files a run reads as state. For OpenFOAM, that is the selected start-time directory and the same directory in every parallel replica. Core walks each and classifies its files by the same precedence. Added 2026-09-26 (spec A2) to replace core's own start-time and ``processor*`` walk. Absent: ``()``, and core walks no state directory.";
  - set `:adapts: get_generated_output_globs, get_input_roots, get_required_inputs`;
  - the protocol methods become:
  ```python
      def input_roots(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[str, ...]: ...

      def required_inputs(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[ResolvedInput, ...]: ...

      def generated_output_globs(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[str, ...]: ...
  ```
  `_CaseProvenanceAdapter` becomes:
  ```python
  @dataclass(frozen=True)
  class _CaseProvenanceAdapter:
      plugin: "SolverPlugin"

      def input_roots(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[str, ...]:
          hook = getattr(self.plugin, "get_input_roots", None)
          if not callable(hook):
              return ()
          roots = tuple(hook(case_root, resolved_case))
          for root in roots:
              # A blank root is not "no opinion": ``case_root / ""`` is the whole
              # case tree. An absolute or escaping root walks outside the case.
              # Refused by name, never silently misclassified.
              parts = PurePosixPath(root).parts if isinstance(root, str) else None
              if not parts or PurePosixPath(root).is_absolute() or ".." in parts:
                  raise TypeError(
                      f"{self.plugin.plugin_id}.get_input_roots() must return non-empty "
                      f"case-relative paths inside the case, got {root!r}"
                  )
          return roots

      def required_inputs(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[ResolvedInput, ...]:
          hook = getattr(self.plugin, "get_required_inputs", None)
          if callable(hook):
              return tuple(hook(case_root, resolved_case))
          return ()

      def generated_output_globs(
          self, case_root: Path, resolved_case: dict[str, Any],
      ) -> tuple[str, ...]:
          hook = getattr(self.plugin, "get_generated_output_globs", None)
          if callable(hook):
              return tuple(hook(case_root, resolved_case))
          return ()
  ```
  and `from pathlib import Path` becomes `from pathlib import Path, PurePosixPath` at the top of the module. `PurePosixPath(".").parts == ()`, so `"."` is refused along with `""`.

  `core/plugin_interface.py`, `SolverPluginOptionalHooks`:
  - delete `get_selected_start_time` and its `# -- CaseIntrospectionCapability` heading;
  - `get_required_inputs` and `get_generated_output_globs` drop the `selected_start_time: str,` parameter;
  - add under `# -- CaseProvenanceCapability`:
  ```python
      def get_input_roots(
          self, case_root: "Path", resolved_case: dict[str, Any],
      ) -> tuple[str, ...]:
          """Case-relative directories whose files a run reads as state, beyond
          the case-file roots: for example the directory a run resumes from,
          and that directory inside each parallel replica. Absent -> ``()``:
          core walks no state directory. Each must be a non-empty case-relative
          path inside the case (added 2026-09-26, spec A2)."""
          ...
  ```

  `core/provider_stack.py`:
  - in `_SHAPE`, delete `"get_selected_start_time": "single",` and add `"get_input_roots": "sequence",` after `"get_generated_output_globs": "sequence",`;
  - the module docstring's first paragraph ends "`get_config_value_reader` returned a different callable from each and a start-time hook was copy-pasted into both (that hook left the contract 2026-09-26, spec A2)."

  `core/runtime/provenance_inputs.py`:
  - remove the `replica_directory_globs` import;
  - in `enumerate_case_inputs`, replace everything from `selected_start_time = ...` through the replica block with:
  ```python
      consumed_relpaths = _collect_consumed_relpaths(workflow_dag)
      required_inputs = capabilities.case_provenance.required_inputs(case_root, resolved_case)
      generated_globs = capabilities.case_provenance.generated_output_globs(case_root, resolved_case)

      components: dict[tuple[str, str], ProvenanceComponent] = {}
      add = _ComponentAdder(components)

      # -- every top-level directory the active plugin declares a case file
      # under, plus every input root the plugin declares (for OpenFOAM: the
      # selected start time, serially and in each replica, I9), classified
      # by precedence steps 1 (consumes), 3 (generated_output_globs) and 4
      # (fallback required). Step 2 (plugin required_inputs) is applied
      # uniformly below instead, since a resolved input's path need not fall
      # under any of these directories.
      walk_roots = [case_root / d for d in _case_root_dirnames(driver_context)]
      walk_roots.extend(
          case_root / root
          for root in capabilities.case_provenance.input_roots(case_root, resolved_case)
      )
  ```
  - in the module docstring, replace "the **selected** start-time directory (as answered by its ``CaseIntrospectionCapability.selected_start_time``), and each declared parallel-decomposition directory's ``<selected-time>/**`` during a decomposed restart are walked" with "and every input root the plugin declares (``CaseProvenanceCapability.input_roots``; for OpenFOAM, the selected start time serially and in each replica) are walked. Corrected 2026-09-26 (spec A2): core used to compute the start time and the replica walk itself."

  `openfoam/environment.py`: replace `get_selected_start_time` with:
  ```python
      def get_input_roots(self, case_root, resolved_case) -> tuple[str, ...]:
          """The state a run resumes from: the selected start-time directory,
          and the same directory in every parallel replica (I9). OpenFOAM's
          convention, moved here 2026-09-26 from core's provenance walk (spec
          2026-09-26-core-generality-design.md §2, A2); core no longer knows
          "start time" or replicas."""
          del resolved_case
          from omnidriver.core.plugin_profile import is_replica_directory_name

          from .mutators import read_foam_entry
          from .time_selection import selected_start_time

          control_dict = next(
              rule.path
              for rule in self.get_profile().case_files
              if rule.role == "openfoam.control_dict"
          )
          start = selected_start_time(
              case_root,
              control_dict_relpath=control_dict,
              read_value=read_foam_entry,
          )
          globs = openfoam_case_runtime_conventions().replica_directory_globs
          replicas = sorted(
              child.name for child in Path(case_root).iterdir()
              if child.is_dir() and is_replica_directory_name(child.name, globs)
          ) if Path(case_root).is_dir() else []
          return (start, *(f"{name}/{start}" for name in replicas))
  ```
  This is equivalent to the old walk. The old walk took `sorted(case_root.glob("processor*"))`, kept only directories, and appended `<replica>/<start>`. `iterdir()` filtered by the same `fnmatchcase` rule yields the same names, and `sorted` gives the same order. The provenance result is sorted by path anyway.

  cardiacfoam:
  - `case_provenance.required_inputs(case_root, resolved_case)` and `generated_output_globs(case_root, resolved_case)` drop `selected_start_time`, including from their `del` lines;
  - `CardiacFoamPlugin.get_required_inputs(self, case_root, resolved_case)` and `get_generated_output_globs(self, case_root, resolved_case)` drop it and call `required_inputs(case_root, resolved_case)` / `generated_output_globs(case_root, resolved_case)`;
  - in the `plugin.yaml` comment, `del case_root, resolved_case, selected_start_time; return ()` becomes `del case_root, resolved_case; return ()`;
  - in the `run_document_config._read_control_dict_values` docstring, the sentence "``CardiacFoamPlugin.get_selected_start_time`` already resolves the same file the same way." becomes "``OpenFOAMEnvironmentPlugin.get_input_roots`` resolves the same file the same way (corrected 2026-09-26: this named ``CardiacFoamPlugin.get_selected_start_time``, which that class never had, and which left the contract in spec A2)."

  cardiaccore `plugin.py::get_generated_output_globs`: drop the `selected_start_time: str,` parameter, and drop it from the `del`.

  `ARCHITECTURE.md`, the `single` row of the composition table: replace the example `get_selected_start_time` with `get_case_runtime_conventions`. Regenerate the seam table: `cd $W && /tmp/odA-core-gen-a2/bin/python scripts/export-capability-seams.py`.

  Append to `future/ENVIRONMENT_CONTRACT.md` §10:
  ```
  **2026-09-26 (topic A, A2):** the Tier 3 "bare optional hooks" `selected_start_time` and `decomposition_dirname_prefix` are gone. Core now reads only plugin-declared vocabulary: `CaseRuntimeConventions.instance_directory_pattern`/`preserved_instance_names`/`replica_directory_globs`, the `{instance}` placeholder, and `CaseProvenanceCapability.input_roots`, through which the OpenFOAM layer declares its start time and replicas.
  ```

- [ ] **Step 5: Run the tests to verify they pass**

  ```bash
  /tmp/odA-core-gen-a2/bin/python -m pytest $W/packages/omnidriver-openfoam/tests/core/test_provenance_integration.py $W/packages/omnidriver/tests/core/test_provenance_inputs.py $W/packages/omnidriver/tests/core/test_case_file_contract.py $W/packages/omnidriver/tests/core/test_resolution_provenance.py $W/packages/omnidriver/tests/core/test_case_provenance_capability.py $W/packages/omnidriver/tests/core/test_capability_seam_documentation.py $W/packages/omnidriver/tests/core/test_contract_tier_coherence.py $W/packages/omnidriver-cardiacfoam/tests/test_case_provenance_capability.py $W/packages/omnidriver-cardiacfoam/tests/test_provenance_inputs.py $W/packages/omnidriver-cardiaccore/tests/test_biv_preprocessing_contract.py -q
  grep -rn "selected_start_time" $W/packages --include='*.py' --include='*.yaml' | grep -v /build/
  ```
  Expected:
  - 0 failed.
  - Every line the grep prints is one of these:
    1. OpenFOAM's own function and its callers: `openfoam/time_selection.py`, `openfoam/environment.py::get_input_roots`, and `test_provenance_integration.py`'s direct test of it;
    2. a dated note naming the removed hook: the `CaseIntrospectionCapability` prose, and the `run_document_config` and `test_resolution_provenance.py` docstrings;
    3. the test function name `test_selected_start_time_directory_is_included_others_excluded`, which describes the case, not the API.
  
  Any other line is a surviving use. Fix it.

- [ ] **Step 6: Check native provenance parity**

  ```bash
  cd $W && /tmp/odA-core-gen-a2/bin/python /tmp/odA-core-gen-a2-provenance.py /tmp/odA-core-gen-a2-provenance-after.json
  diff /tmp/odA-core-gen-a2-provenance-before.json /tmp/odA-core-gen-a2-provenance-after.json && echo IDENTICAL
  ```
  Expected: `IDENTICAL`. Every real native case is fingerprinted byte-for-byte as before.

- [ ] **Step 7: Run V1–V6, then commit**

  Expected: 0 failed in V1–V5, and V6 exits 0. The shape gate stays silent, and V5 still passes C1–C11.
  
  Generality-log row:
  ```
  | 2026-09-26 | core generality (A) | A2c: provenance hook `CaseProvenanceCapability.input_roots(case_root, resolved_case)` (member `get_input_roots`, `sequence`); `CaseIntrospectionCapability.selected_start_time` and `get_selected_start_time` deleted; `required_inputs`/`generated_output_globs` lose the start-time argument; the OpenFOAM layer declares its start time and replicas | core computed OpenFOAM's restart directory and walked its replicas | neutral: characterization test `test_the_start_time_is_walked_serially_and_in_every_replica` passes before and after; native provenance of every registered cardiacFOAM/cardiacCore tutorial is byte-identical; a stack declaring no roots walks only its case-file roots |
  ```
  ```bash
  git -C $W add -A packages ARCHITECTURE.md future/ENVIRONMENT_CONTRACT.md docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md
  git -C $W commit -m "refactor: the plugin declares its provenance input roots; core stops knowing start time (A2c)

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```
  Land on `main` by fast-forward.

---

### Checkpoint R2: Opus review of A2

- [ ] Dispatch one reviewer (Agent tool, `model: "opus"`) over the three A2 commits. Its brief:
  - check the vocabulary-only rule on the listed tests (`git diff --word-diff`);
  - check the OpenFOAM equivalence arguments: the regex and `"0"`; `processor*` against the prefix; `iterdir`+`fnmatchcase` against `glob`;
  - check that no core module reads an OpenFOAM term;
  - check the run-document schema change is recorded;
  - check that openCARP declares none of the new vocabulary: `grep -rn "instance_directory_pattern\|replica_directory_globs\|get_input_roots" packages/omnidriver-opencarp` prints nothing.
- [ ] Fix each finding in its own commit with a dated correction, rerun V1–V6, land.

---

### Task 9: Close-out

**Files:**
- Modify: `docs/superpowers/specs/2026-09-26-core-generality-design.md` (status; dated corrections).
- Modify: `scripts/core-shape-baseline.txt`, only if the final gate reports a shrink.
- Modify, for the owner to approve: `CLAUDE.md`'s conformance invariant row.

- [ ] **Step 1: Confirm the debt the spec targets.**

  Run `cd /Users/simaocastro/omnidriver && python3 scripts/check-core-shape.py && cut -f1,2,3 scripts/core-shape-baseline.txt | grep -v '^#'`.
  
  Expected output lines:
  - `core/runtime/generic_case.py	case.foam	9` (A4 debt, later);
  - `core/runtime/run_document_exec.py	FOAM_	1`.
  
  The second is the project's own former name, `DRIVERFOAM_ALLOWED_RUNS_ROOT`. It is neither A1, A2 nor A4. See Step 2.

- [ ] **Step 2: Correct the spec in place, with dates.** Append to its §4:
  ```
  **Corrected 2026-09-26 (implementation, topic A):**
  - "only the A4 debt remains" is not reachable as written: `run_document_exec.py`'s `FOAM_` hit is the legacy `DRIVERFOAM_ALLOWED_RUNS_ROOT` variable (the project's former name), no OpenFOAM coupling, and outside A1/A2/A4. It remains until the owner decides to drop that legacy variable.
  - The A5 check is C11, not a C7 extension (plan Task 3). It is strict: a restaged case holds only native paths. Meeting it needed `CORE_RUNTIME_RECORDS` to list every file core writes (seven files and two directories, not four) and openCARP's record to declare its full outputs (F15).
  - A3's stable digest: every provider digest and the cardiac stacks' identities are unchanged; `opencarp` and standalone `openfoam-environment` record `dictionaries` as `<unclaimed>` once, because their stub had been its false winner.
  - A7: the hook did not cover `manufacturedMonodomainTotalLagrangianEM`; it now reads the electro region that case declares (plan Task 2).
  - A2 landed as three commits (A2a instances, A2b replicas, A2c input roots); the run-document schema key `time_indexed` became `instance_indexed`.
  ```
  In the spec header, set `**Status:**` to `implemented 2026-09-26 (plan docs/superpowers/plans/2026-09-26-core-generality.md)`, keeping the approval sentence after it.

- [ ] **Step 3: Propose the CLAUDE.md edit to the owner. Do not commit it without their yes.**

  In the invariants table, the row "every conformance target passes C1-C10 (...)" becomes "every conformance target passes C1-C11 (...; C11 added 2026-09-26: restaging a run case carries nothing the run wrote)".

- [ ] **Step 4: Final whole-topic Opus review.**
  - Dispatch one reviewer (Agent tool, `model: "opus"`) over `git diff fd21fe7..main`, against the spec, this plan and CLAUDE.md's invariants.
  - Fix, rerun, land.
  - Then run V1–V6 once more on `main`, from a fresh worktree with its own venvs. Expected: 0 failed everywhere; V6 exits 0.

- [ ] **Step 5: Commit the close-out.**
  ```bash
  git -C $W add docs/superpowers/specs/2026-09-26-core-generality-design.md
  git -C $W commit -m "docs: core generality (topic A) implemented; dated spec corrections

  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  ```

---

## Self-review

**Spec coverage.**

| spec requirement | where |
|---|---|
| A1: `environment_source`/`--environment-source`, opaque, removed from `generic_case`, every package and test in one commit | Task 5 Steps 4–5; the opacity tests in Step 2; the grep gate in Step 7 |
| A1: baseline loses all `bashrc` lines, edited down, no `--write-baseline` | Task 5 Step 6 |
| A2: `instance_directory_pattern`, `preserved_instance_names`, `{instance}`, `DataArtifact.instance_indexed` | Task 6 |
| A2: `replica_directory_globs` | Task 7 |
| A2: `input_roots(case_root, resolved_case)`; core stops knowing start time and processor | Task 8; the `processor` baseline line goes in Task 7 |
| A2: OpenFOAM byte-for-byte unchanged (named tests); openCARP declares nothing | Tasks 6–8 (the vocabulary-only rule; `test_openfoam_time_directories_are_its_instances`, `test_openfoam_hides_parallel_decomposition_output`, `test_the_start_time_is_walked_serially_and_in_every_replica`; native parity Task 8 Step 6); R2's openCARP grep |
| A2: a stack declaring none behaves as openCARP does | `test_instance_directories.py`, `test_replica_directories.py`, `test_case_file_contract` (`input_roots == ()`) |
| A2: cardiacFOAM native and openCARP native verification | V4 and V5 in Tasks 6–8 |
| A2: split if unsafe | "A2 as three tasks" |
| A3: four members optional-neutral; empty fallbacks in adapters, merges and identity; stubs deleted; `get_tutorial_catalog` required | Task 4 Step 4 |
| A3: stable "none" digest specified and tested; unchanged for existing stacks | Task 4, "The stable none digest"; `test_no_dictionary_entries_digests_exactly_as_an_empty_stub_did`; `test_the_cardiac_stack_identity_is_unchanged_by_deleting_the_stubs`; Step 8 before/after |
| A3: a plugin implementing none loads, composes, describes and runs | `test_dictionary_members_are_optional.py` (C1/C2/C6/C10 over the toy, which lacks all four) |
| A5: `CORE_RUNTIME_RECORDS`, `with_core_runtime_records`, the adapter merge, staging excludes `produces` | Task 3 Steps 5–6 |
| A5: failing-first staging-leak check, failing for openCARP native and a toy with no conventions | Task 3 Steps 2–3 (C11) |
| A6: two functions moved, `check-wheel-artifact.py` neutral, `cardiacfoam_monorepo_root` moved, CLI help | Task 1 |
| A7: prove first, delete the heuristic, rename `SKIP_MESH_DIAGNOSTICS` with a dated note, fix the stale docstring | Task 2 |
| §5: order, parallel tracks, shared-file landing and generality-log rows, Opus reviews | the order table; each task's header and last step; R1, R2, Task 9 Step 4 |
| Global: no skips, fallbacks or shims; supplied not discovered; a venv per worktree; dated corrections; never hand-build `omnidriver run`; supplied scratch root; trailer | Global Constraints; C11 uses `_execute` (`omnidriver_run_command`) and `target.scratch_root` |

**Placeholder scan.**
- No "TBD", "TODO", "implement later", "similar to Task N" or "add appropriate …".
- One literal placeholder remains: `<paste the Step 8 diff here>` in Task 4's commit body. It stands for a command output that Step 8 itself produces.
- Every code step shows its code. Mechanical renames are given as exact old → new tables, each closed by a grep gate whose expected output is stated.

**Type consistency.** Checked across tasks:
- `environment_source: str | None`: Task 5 everywhere, and in Task 1's `_SOLVER_WORDS` extension.
- `excluded_relpaths: frozenset[str]`: Task 3 `_stage_entry_case`, fed by `record_generated_relpaths`.
- `CORE_RUNTIME_RECORDS` and `with_core_runtime_records`: Task 3, and the `test_case_file_contract` assertion.
- `instance_names`: the `reconcile_artifacts` keyword; `declared_instance_names` in Task 6, used by `cli.py` and `resume.py`.
- `replica_directory_globs` is both a field (Task 7) and a function name in `plugin_profile`. They are deliberately the same word: the function returns the field.
- `is_replica_directory_name(name, globs)`: Task 7, then Task 8's OpenFOAM `get_input_roots`.
- `input_roots(case_root, resolved_case) -> tuple[str, ...]` and hook `get_input_roots`: Task 8, in the protocol, adapter, `_SHAPE`, the OpenFOAM layer, and the test fakes.
- `_mesh_geometry_exempt(spec, driver_context)` and `SKIP_GEOMETRY_DIAGNOSTICS_ENV`: Task 2.
- `_declared_dict_entries(provider)`: Task 4.
- `check_restage_is_clean`, registered as `"C11"`: Task 3.
- `ATTEMPT_LOCK_FILENAME` and `ATTEMPT_LOCK_GUARD_FILENAME`: Task 3.
