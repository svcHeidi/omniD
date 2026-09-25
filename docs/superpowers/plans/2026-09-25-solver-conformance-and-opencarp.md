# Solver Conformance and openCARP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that omniD can drive a solver outside OpenFOAM, and that an agent can use it without knowing which solver it faces. The proof has three parts:
- a packaged solver conformance suite (checks C1–C10; C10 is agent discovery);
- the core changes that suite forces;
- a shape gate, plus an `omnidriver-opencarp` plugin whose Niederer N-version record passes every check against the real openCARP binary.

**Architecture:**
- `omnidriver.conformance` holds plain check functions that return verdicts, parametrized per package over `ConformanceTarget`s.
- Core changes are made only when a check or a test fails without them.
- openCARP is one self-contained plugin (no `requires:`). Its native case is openCARP's own `02_EP_tissue/03E_study_resolution` (a `.par` file plus a mesh made by `mesher`).
- Its parameter catalog is generated from `openCARP +Help` and drift-gated against the binary.

**Tech Stack:** Python ≥ 3.11, pytest, PyYAML (already a core dependency), openCARP v18.1 (`openCARP`, `mesher`), uv.

**Spec:** `docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md`.
**Evidence:** `docs/solver-learning/opencarp.md` (A–G, F1–F8).
**Method:** `docs/solver-learning/method.md`.

## Global Constraints

- Python floor 3.11; CI matrixes 3.11/3.12/3.13.
- Core names no solver or physics: `scripts/check-import-boundaries.py` has an empty waiver list, and after Task 7 `scripts/check-core-shape.py` accepts no new token.
- No skips. A check that cannot run is a **failure that names why**. `native` tests **fail, not skip**, when their environment variable is unset.
- Supplied, never discovered:
  - native trees come from `OMNIDRIVER_OPENCARP_TUTORIALS` (openCARP) and `OMNIDRIVER_NATIVE_TUTORIALS` (cardiacFOAM);
  - openCARP's library path comes from the ambient `DYLD_LIBRARY_PATH`;
  - scratch space comes from the target's `scratch_root`.
- Claims about openCARP come from the real binary. Every probe goes into `docs/solver-learning/opencarp.md` (command, observed output, conclusion).
- The native tree is never written. Every run works in a staged copy under a scratch directory.
- Evaluate defaults lazily (CLAUDE.md). Prefer naming a symbol to citing a line number. Correct a docstring or comment claim with a date; don't silently overwrite it.
- Redact secrets found in tool output: openCARP's build header embeds a CI token (G3).
- Verify in all shapes before any "done":
  - all packages;
  - core alone;
  - the installed wheel;
  - `-m native`;
  - static gates.
  
  The durable claim is **0 failed**. Suite totals are never quoted.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Working beside the tutorial stream** (the briefing from `main` at `eb47f6e`, 2026-09-25):
  - Core files are shared ground: `tutorial_records.py`, `record_execution.py`, `registry.py`, `sweep_runner.py`, `strict_planning.py`, `plugin_capabilities.py`, `case_transaction.py`. `WorkflowStep` is this plan's to change; the tutorial stream rebases on it.
  - Every core change here lands on `main` as its own small commit, soon after review. Each one also adds a row to the generality log (`docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5): stream `openCARP`, what the change is, why, and a verdict.
  - Never hand-build an `omnidriver run` command; use `core.runtime.run_command.omnidriver_run_command(ctx, *args)`.
  - Run documents carry the required `configurationSource`. Record runs are `"case"` with an empty config. `strict_plan` sets it, so nothing here builds a run document by hand.
  - Record execution refuses without a key validator, value comparator and config reader, and there are no fallbacks. openCARP provides all three.
  - `main` changes only by fast-forward, never force. Nothing goes to `origin` without the owner's go-ahead.
- **One venv per worktree.** A shared venv imports another checkout and gives false greens. Each executing agent builds `/tmp/odconf-<worktree-name>` (all packages) and `/tmp/odconfcore-<worktree-name>` (core only) from its own worktree, and uses them wherever this plan writes `/tmp/odconf` and `/tmp/odconfcore`.
- **Sequencing.** Start only after `claude/festive-cray-9d30ca` (tutorials-are-pointers) is merged into `main`; P1 and P2 landed there as `156b80d` and `56d89d7`. Task 14 (the cardiacFoam target) starts only after that branch's step 5 is finished, because its records are owned there until then.

## Spec items and where they land

| spec item | where |
|---|---|
| P1, P2 (records through strict plan/run; seeded snapshots) | landed upstream; verified in Task 1 Step 1 |
| §4 suite, C1–C9 | Tasks 1–6 (C10: Task 10a) |
| K4 record steps declare `produces`/`consumes` | Task 3 |
| new K8: sweep records each case's artifact reconciliation (the digest found `sweep-run` discards it) | Task 4 |
| K6 `string` value kind | Task 9 |
| K7 gates learn the new package (reduced: extend the existing lists) | Task 8 |
| new K9: log redaction (G3) | Task 12 |
| §6 shape gate | Task 7 |
| §7 openCARP package | Tasks 8–11 |
| §8 testing, CI | Task 13 |
| cardiacFoam target | Task 14 (after step 5) |
| **owner, 2026-09-25: agent agnosticism, gap 1**: an agent finds any record's axes and keys the same way | new **C10** + the `record_surface` capability, Task 10a; openCARP passes it in Task 11 |
| **gap 3**: guidance an installed agent can read, per solver and per case | `record_surface` carries plugin guidance and the case's own documentation (Task 10a); openCARP's `guidance.md` (Task 11) |
| **gap 2**: every file declared by the layer that reads it | Task 15 (after step 5): two guards force it, and K3 is done there |

**Deliberately not done, by the spec's own rule "a K-change no check forces is not made here":**
- **K3 (core declares its own bookkeeping names)** is *not* deferred any more. Owner decision 2026-09-25 (gap 2): Task 15 adds a guard that forces it. Without that guard no check would fail: records name their inputs through `consumes` (Task 3), so provenance never walks core's files.
- **K5 (demote the dictionary trio to optional).** The openCARP plugin stubs these members exactly as `MinimalTestPlugin` does, and C1 passes. Deferred.

Task 13 records K5 as a dated correction in the spec.

## File structure

```
packages/omnidriver/src/omnidriver/conformance/
  __init__.py            re-exports ConformanceTarget, CheckVerdict, CHECKS, run_check
  target.py              ConformanceTarget, CheckVerdict (data only)
  checks.py              C1–C10 and their private helpers (plan once, run once, tree digest)
packages/omnidriver/src/omnidriver/core/
  tutorial_records.py    MODIFY: WorkflowStep gains produces/consumes (K4)
  runtime/record_execution.py   MODIFY: DAG io + expected_artifacts from record steps (K4)
  runtime/sweep_runner.py       MODIFY: per-case artifact_reconciliation (K8)
  runtime/workflow_runner.py    MODIFY: redact step logs (K9)
  plugin_capabilities.py        MODIFY: runtime_evidence gains log_redaction_patterns (K9)
  plugin_interface.py, provider_stack.py   MODIFY: register the K9 hook
  contracts/dictionary.py       MODIFY: "string" value kind (K6)
packages/omnidriver/tests/
  plugins/e2e_record_plugin.py  MODIFY: step io, real preflight
  plugins/conformance_toy.py    CREATE: toy target + deliberately broken plugins
  core/test_conformance_toy.py  CREATE: C1–C10 over the toy, plus "the check bites" tests
  core/test_record_step_io.py   CREATE: K4 unit tests
  core/test_check_core_shape.py CREATE: shape-gate tests
scripts/check-core-shape.py, scripts/core-shape-baseline.txt   CREATE (Task 7)
scripts/generate-opencarp-catalog.py                           CREATE (Task 9)
packages/omnidriver-opencarp/
  pyproject.toml
  src/omnidriver/opencarp/
    __init__.py
    opencarp.yaml                 plugin profile
    par_format.py                 parse / patch / format .par (pure; F1, F8)
    catalog.py                    ParameterSpec, load_catalog, template_name (pure)
    catalog_generation.py         build the catalog from the binary (F-evidence B1–B5, G6)
    opencarp_parameters.json      generated, committed
    validation.py                 record-key validator, index-bound check (F1, F2)
    environment.py                preflight, redaction patterns (A4–A8, G3)
    plugin.py                     OpenCARPPlugin
    records/__init__.py           TUTORIAL_RECORDS, AXIS_CATALOG
    records/niederer_n_version.py RECORD, DX_AXIS (F3–F6)
  tests/
    opencarp_native.py            uniquely named helper: native root, target builder
    test_par_format.py            pure rules
    test_par_format_native.py     round-trip every shipped .par byte for byte
    test_catalog.py               on the committed JSON
    test_catalog_native.py        drift gate against the binary
    test_validation.py            on the committed JSON
    test_plugin_contract.py       C1 in every shape
    test_conformance_native.py    C1–C10 against the real binary
```

---

### Task 1: Conformance skeleton, and C1–C3 over the toy target

**Files:**
- Create: `packages/omnidriver/src/omnidriver/conformance/__init__.py`, `target.py`, `checks.py`
- Create: `packages/omnidriver/tests/plugins/conformance_toy.py`
- Create: `packages/omnidriver/tests/core/test_conformance_toy.py`

**Interfaces:**
- Produces:
  - `ConformanceTarget` and `CheckVerdict(check_id: str, passed: bool, detail: str)`;
  - `check_load(target) -> CheckVerdict`, `check_describe_noop(target)`, `check_refuses_unknown(target)`;
  - `CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]]` and `run_check(check_id: str, target) -> CheckVerdict`;
  - the private helpers `_context(target)`, `_record(ctx, name)` and `_scratch_environment(target)`;
  - in tests, `toy_conformance_target(tmp_path) -> ConformanceTarget`.
- Consumes, all verified on the branch:
  - `load_plugin_context(target: str) -> DriverContext` (core `plugin_interface`);
  - `describe_entry(entry, *, overrides, driver_context) -> dict`, whose record payload has `["record_preview"]["patches"]` with `status` `"changed"` or `"unchanged"`;
  - `TutorialRecordError` (core `tutorial_records`);
  - `ctx.capabilities.tutorial_records.catalog() -> dict | None`.

- [ ] **Step 1: Preconditions (no code)**

  Run:
  ```bash
  git -C /Users/simaocastro/omnidriver log --oneline main | grep -E "156b80d|56d89d7" || echo MISSING
  grep -n "_seed_snapshot_root\|def commit_and_build_record_spec" packages/omnidriver/src/omnidriver/core/runtime/record_execution.py
  grep -n "^    [a-z_]*: [A-Z][A-Za-z]*Capability" packages/omnidriver/src/omnidriver/core/plugin_capabilities.py
  ```
  Expected:
  - both commits are present (no `MISSING`);
  - both symbols print;
  - the capability field list includes `tutorial_records`, `axes`, `record_key_validation`, `case_value_comparison`, `config_value`, `case_writer`, `environment_preflight` and `runtime_evidence`.
  
  If any field name differs, use the printed name everywhere this plan writes `ctx.capabilities.<name>`, and note the difference in the task's commit message.

  Create a branch and venvs for it (memory: a worktree needs its own venv):
  ```bash
  git switch -c solver-conformance main
  uv venv --python 3.11 /tmp/odconf && VIRTUAL_ENV=/tmp/odconf uv pip install -q -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam -e packages/omnidriver-cardiaccore pytest
  uv venv --python 3.11 /tmp/odconfcore && VIRTUAL_ENV=/tmp/odconfcore uv pip install -q -e "packages/omnidriver[post]" pytest
  /tmp/odconf/bin/python -c "import omnidriver, pathlib; print(pathlib.Path(omnidriver.__path__[0]).resolve())"
  ```
  Expected: the printed path is inside the current checkout, not another worktree.

- [ ] **Step 2: Write the target data**

  `packages/omnidriver/src/omnidriver/conformance/target.py`:
  ```python
  """What one solver hands the conformance suite, and what each check returns.

  Design: docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md §4.
  Everything here is supplied by the caller; the suite discovers nothing
  (future/ENVIRONMENT_CONTRACT.md §12).
  """
  from __future__ import annotations

  from dataclasses import dataclass
  from pathlib import Path
  from typing import Any, Mapping


  @dataclass(frozen=True)
  class ConformanceTarget:
      """One solver record, and the study values that exercise it.

      ``environment`` is an overlay on the calling process's environment for
      every child process a check starts. ``scratch_root`` receives every
      stage, plan and sweep: the native tree under ``cases_root`` is never
      written. ``base_study`` pins values that keep a real run short (for
      openCARP, mesh resolution and time step; evidence G7).
      """

      plugin: str
      record: str
      cases_root: Path
      scratch_root: Path
      base_study: Mapping[str, Any]
      patch: tuple[str, Any]
      untouched: tuple[str, tuple[str, ...]]
      sweep_name: str
      sweep_values: tuple[Any, Any]
      unknown_name: str
      solver_command: str
      environment: Mapping[str, str]


  @dataclass(frozen=True)
  class CheckVerdict:
      check_id: str
      passed: bool
      detail: str
  ```

- [ ] **Step 3: Write the toy target and the failing tests**

  `packages/omnidriver/tests/plugins/conformance_toy.py`:
  ```python
  """The toy conformance target: E2ERecordPlugin's toyTutorial.

  The native case is written into tmp_path by the caller's test, the same way
  test_sweep_run_plugin_propagation builds it, but with a second key
  (``label``). A one-key document cannot show a sibling key being lost; that
  is how P2 hid.
  """
  from __future__ import annotations

  import json
  import os
  from pathlib import Path

  from omnidriver.conformance import ConformanceTarget

  TESTS_ROOT = Path(__file__).resolve().parents[1]
  TOY_PLUGIN = "plugins.e2e_record_plugin:E2ERecordPlugin"


  def write_toy_native_case(cases_root: Path) -> Path:
      native = cases_root / "toyTutorial"
      (native / "constant").mkdir(parents=True)
      (native / "constant" / "mesh.json").write_text(json.dumps({"cells": "1", "label": "toy"}))
      return native


  def toy_conformance_target(tmp_path: Path, *, plugin: str = TOY_PLUGIN) -> ConformanceTarget:
      cases_root = tmp_path / "native"
      write_toy_native_case(cases_root)
      return ConformanceTarget(
          plugin=plugin,
          record="toyTutorial",
          cases_root=cases_root,
          scratch_root=tmp_path / "scratch",
          base_study={},
          patch=("constant/mesh.json:cells", 7),
          untouched=("constant/mesh.json", ("label",)),
          sweep_name="number_cells",
          sweep_values=(2, 3),
          unknown_name="cell_count",
          solver_command="touch",
          environment={
              "PYTHONPATH": os.pathsep.join([str(TESTS_ROOT), os.environ.get("PYTHONPATH", "")]),
          },
      )
  ```

  `packages/omnidriver/tests/core/test_conformance_toy.py`:
  ```python
  """The conformance suite over the toy target (core-alone and wheel shapes).

  Every check must pass for the toy. Checks with a known historical defect
  also get a deliberately broken plugin, to prove the check bites.
  """
  from __future__ import annotations

  import pytest

  from omnidriver.conformance import run_check
  from plugins.conformance_toy import toy_conformance_target


  @pytest.mark.parametrize("check_id", ["C1", "C2", "C3"])
  def test_toy_passes(check_id, tmp_path):
      verdict = run_check(check_id, toy_conformance_target(tmp_path))
      assert verdict.passed, verdict.detail
  ```

- [ ] **Step 4: Run it to verify it fails**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v`
  
  Expected: collection error, `ModuleNotFoundError: No module named 'omnidriver.conformance'`.

- [ ] **Step 5: Write C1–C3**

  `packages/omnidriver/src/omnidriver/conformance/__init__.py`:
  ```python
  """The solver conformance suite: an executable definition of "a solver can
  plug into omniD". Design: docs/superpowers/specs/2026-09-25-solver-
  conformance-and-opencarp-design.md §4. Shipped in the core wheel so a
  third-party solver's authors can run it against their own plugin."""
  from .checks import CHECKS, run_check
  from .target import CheckVerdict, ConformanceTarget

  __all__ = ["CHECKS", "CheckVerdict", "ConformanceTarget", "run_check"]
  ```

  `packages/omnidriver/src/omnidriver/conformance/checks.py`:
  ```python
  """C1–C10. Each check is self-contained: it builds its own context, stages
  its own copy, and returns a verdict naming what it saw. No check skips; a
  check that cannot run is a failure saying why."""
  from __future__ import annotations

  import contextlib
  import os
  from pathlib import Path
  from typing import Any, Callable, Iterator

  from omnidriver.core.introspection import describe_entry
  from omnidriver.core.plugin_interface import load_plugin_context
  from omnidriver.core.tutorial_records import TutorialRecordError

  from .target import CheckVerdict, ConformanceTarget

  _SCRATCH_VARIABLE = "OMNIDRIVER_SCRATCH_DIR"


  def _verdict(check_id: str, passed: bool, detail: str) -> CheckVerdict:
      return CheckVerdict(check_id=check_id, passed=passed, detail=detail)


  def _context(target: ConformanceTarget):
      return load_plugin_context(target.plugin)


  def _record(ctx, name: str):
      records = ctx.capabilities.tutorial_records.catalog() or {}
      if name not in records:
          raise LookupError(f"{name!r} is not a tutorial record of this stack; it has {sorted(records)}")
      return records[name]


  @contextlib.contextmanager
  def _scratch_environment(target: ConformanceTarget) -> Iterator[None]:
      """Point core's scratch space at the target's scratch_root for an
      in-process call. Without it, planning a record writes
      ``<cases_root>/.omnidriver`` -- inside the caller's native tree."""
      previous = os.environ.get(_SCRATCH_VARIABLE)
      os.environ[_SCRATCH_VARIABLE] = str(target.scratch_root)
      try:
          yield
      finally:
          if previous is None:
              os.environ.pop(_SCRATCH_VARIABLE, None)
          else:
              os.environ[_SCRATCH_VARIABLE] = previous


  def check_load(target: ConformanceTarget) -> CheckVerdict:
      """C1: the stack is its root plus exactly what the root requires.

      A provider no one requires (for example an OpenFOAM environment layer a
      non-FOAM solver never asked for) means the stack depends on something
      it does not declare."""
      try:
          ctx = _context(target)
      except Exception as exc:  # the verdict names every load failure
          return _verdict("C1", False, f"stack did not load: {type(exc).__name__}: {exc}")
      ids = [provider.plugin_id for provider in ctx.providers]
      required = {rid for provider in ctx.providers for rid in provider.get_profile().requires}
      roots = [pid for pid in ids if pid not in required]
      if len(roots) != 1:
          return _verdict("C1", False, f"stack {ids} has {len(roots)} unrequired providers {roots}; expected exactly one root")
      return _verdict("C1", True, f"stack {ids}, root {roots[0]}")


  def check_describe_noop(target: ConformanceTarget) -> CheckVerdict:
      """C2: with no study values, describe proposes no change to the native case."""
      ctx = _context(target)
      with _scratch_environment(target):
          payload = describe_entry(
              target.record, overrides={"cases_root": str(target.cases_root)}, driver_context=ctx,
          )
      preview = payload.get("record_preview")
      if preview is None:
          return _verdict("C2", False, f"{target.record!r} did not resolve as a tutorial record (resolution={payload.get('resolution')!r})")
      changed = [p for p in preview["patches"] if p["status"] != "unchanged"]
      if changed:
          return _verdict("C2", False, f"describe proposes {len(changed)} change(s) to the untouched native case: {changed}")
      return _verdict("C2", True, "no changes proposed")


  def check_refuses_unknown(target: ConformanceTarget) -> CheckVerdict:
      """C3: an unknown study name is refused, by that name, before anything runs."""
      ctx = _context(target)
      overrides = {"cases_root": str(target.cases_root), target.unknown_name: 1}
      try:
          with _scratch_environment(target):
              describe_entry(target.record, overrides=overrides, driver_context=ctx)
      except (TutorialRecordError, KeyError, ValueError) as exc:
          named = target.unknown_name in str(exc)
          return _verdict("C3", named, f"refused: {exc}" if named else f"refused without naming {target.unknown_name!r}: {exc}")
      return _verdict("C3", False, f"{target.unknown_name!r} was accepted")


  CHECKS: dict[str, Callable[[ConformanceTarget], CheckVerdict]] = {
      "C1": check_load,
      "C2": check_describe_noop,
      "C3": check_refuses_unknown,
  }


  def run_check(check_id: str, target: ConformanceTarget) -> CheckVerdict:
      if check_id not in CHECKS:
          raise KeyError(f"no conformance check {check_id!r}; known: {sorted(CHECKS)}")
      return CHECKS[check_id](target)
  ```

- [ ] **Step 6: Run the tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v`
  
  Expected: 3 passed.
  
  If C3 fails because the refusal does not contain the name, read the message. A refusal that doesn't name the key is a core defect: fix it in `sort_study_name`, not in the check.

- [ ] **Step 7: Run the check in core-alone and commit**

  ```bash
  /tmp/odconfcore/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -q
  git add packages/omnidriver/src/omnidriver/conformance packages/omnidriver/tests/plugins/conformance_toy.py packages/omnidriver/tests/core/test_conformance_toy.py
  git commit -m "feat(core): the solver conformance suite, C1-C3 over the toy target"
  ```

---

### Task 2: C4, the patch preserves its siblings, and a check that bites

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/conformance/checks.py`
- Modify: `packages/omnidriver/tests/plugins/conformance_toy.py`
- Modify: `packages/omnidriver/tests/core/test_conformance_toy.py`

**Interfaces:**
- Consumes:
  - `commit_record_case(record, *, cases_root, staged_case_root, study_by_source, driver_context, execution_env=None, requested_by="tutorial_record") -> RecordCommitResult`;
  - `ctx.capabilities.config_value.reader() -> (path, key_path) -> value | None`;
  - `ctx.capabilities.case_value_comparison.comparator() -> (value_kind, requested, current) -> bool`;
  - `ctx.capabilities.record_key_validation.validator() -> (document, key_path, value) -> (value_kind, validated)`.
- Produces: `check_patch_preserves(target)`, `_stage(target, record, label) -> Path`, and `ReplacingRendererPlugin` in `conformance_toy.py`.

- [ ] **Step 1: Write the failing tests**

  Append to `test_conformance_toy.py`:
  ```python
  from plugins.conformance_toy import REPLACING_PLUGIN


  def test_toy_passes_c4(tmp_path):
      verdict = run_check("C4", toy_conformance_target(tmp_path))
      assert verdict.passed, verdict.detail


  def test_c4_bites_a_renderer_that_replaces_the_document(tmp_path):
      """The P2 class of defect: a renderer that writes only the patched keys."""
      verdict = run_check("C4", toy_conformance_target(tmp_path, plugin=REPLACING_PLUGIN))
      assert not verdict.passed
      assert "label" in verdict.detail
  ```

  Append to `conformance_toy.py`:
  ```python
  import json as _json

  from omnidriver.core.case_write import RenderedFile, _digest_bytes

  from plugins.e2e_record_plugin import E2ERecordPlugin, _FORMAT, _deep_set

  REPLACING_PLUGIN = "plugins.conformance_toy:ReplacingRendererPlugin"


  class ReplacingRendererPlugin(E2ERecordPlugin):
      """Truthful about exists_before, but writes a document holding only the
      patched keys. case_transaction accepts it; only C4 can catch it."""

      def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
          rendered = []
          for target in resolved.targets:
              path = Path(snapshot_root) / target["document"]
              exists_before = path.exists()
              content_obj: dict = {}
              _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
              rendered.append(RenderedFile(
                  path=target["document"], content=(_json.dumps(content_obj) + "\n").encode(),
                  mode=None, exists_before=exists_before,
                  before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                  renderer_id=self.plugin_id, format=_FORMAT,
              ))
          return tuple(rendered)
  ```

- [ ] **Step 2: Run the tests to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v -k c4`
  
  Expected: `KeyError: "no conformance check 'C4'"`.

- [ ] **Step 3: Write C4**

  Add to `checks.py`, after `check_refuses_unknown`:
  ```python
  import shutil

  from omnidriver.core.runtime.record_execution import commit_record_case


  def _stage(target: ConformanceTarget, record, label: str) -> Path:
      """A fresh copy of the record's native case under scratch_root."""
      staged = target.scratch_root / "conformance" / label / record.name
      if staged.exists():
          shutil.rmtree(staged)
      shutil.copytree(target.cases_root / record.native_case_relpath, staged)
      return staged


  def _split_study_key(name: str) -> tuple[str, tuple[str, ...]]:
      document, separator, dotted = name.partition(":")
      if not separator or not dotted:
          raise ValueError(f"{name!r} is not a document:key study name")
      return document, tuple(dotted.split("."))


  def check_patch_preserves(target: ConformanceTarget) -> CheckVerdict:
      """C4: a one-key patch changes that key and leaves ``untouched`` as it was."""
      ctx = _context(target)
      record = _record(ctx, target.record)
      staged = _stage(target, record, "C4")
      reader = ctx.capabilities.config_value.reader()
      comparator = ctx.capabilities.case_value_comparison.comparator()
      validator = ctx.capabilities.record_key_validation.validator()
      if reader is None or comparator is None or validator is None:
          return _verdict("C4", False, "the stack lacks a config reader, comparator or key validator")
      untouched_doc, untouched_key = target.untouched
      before = reader(staged / untouched_doc, untouched_key)
      if before is None:
          return _verdict("C4", False, f"target misconfigured: {untouched_doc}:{'.'.join(untouched_key)} is absent from the native case")
      patch_name, patch_value = target.patch
      patch_doc, patch_key = _split_study_key(patch_name)
      value_kind, _validated = validator(patch_doc, patch_key, patch_value)
      if comparator(value_kind, patch_value, reader(staged / patch_doc, patch_key)):
          return _verdict("C4", False, f"target misconfigured: the native case already holds {patch_name} = {patch_value!r}")
      with _scratch_environment(target):
          commit_record_case(
              record, cases_root=target.cases_root, staged_case_root=staged,
              study_by_source={"base": {patch_name: patch_value}}, driver_context=ctx,
          )
      after_patched = reader(staged / patch_doc, patch_key)
      after_untouched = reader(staged / untouched_doc, untouched_key)
      problems = []
      if not comparator(value_kind, patch_value, after_patched):
          problems.append(f"{patch_name} reads {after_patched!r} after patching it to {patch_value!r}")
      if after_untouched != before:
          problems.append(f"{untouched_doc}:{'.'.join(untouched_key)} changed from {before!r} to {after_untouched!r}")
      return _verdict("C4", not problems, "; ".join(problems) or "patched one key; its sibling is unchanged")
  ```
  Register it: add `"C4": check_patch_preserves,` to `CHECKS`.

- [ ] **Step 4: Run the tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v`
  
  Expected: 5 passed. The bite test fails C4 with a detail naming `label`.

- [ ] **Step 5: Commit**

  ```bash
  git add -u packages/omnidriver && git add packages/omnidriver/tests/plugins/conformance_toy.py
  git commit -m "feat(core): conformance C4 -- a patch preserves its sibling keys, with a check that bites"
  ```

---

### Task 3: Record steps declare what they read and write (K4), then C5 and C6

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/tutorial_records.py` (`WorkflowStep`)
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/record_execution.py` (`_workflow_dag_for_record`, `record_case_spec`, new `record_step_artifacts`, `record_artifact_id`)
- Modify: `packages/omnidriver/tests/plugins/e2e_record_plugin.py` (`_TOY_RECORD`)
- Create: `packages/omnidriver/tests/core/test_record_step_io.py`
- Modify: `checks.py`, `test_conformance_toy.py`

**Interfaces:**
- Produces:
  - `WorkflowStep(step_id, command, produces: tuple[str, ...] = (), consumes: tuple[str, ...] = ())`. Both fields hold case-relative paths.
  - `record_artifact_id(step_id: str, index: int) -> str`, which returns `f"record.{step_id}.{index}"`.
  - `record_step_artifacts(record, workflow_step_ids) -> tuple[DataArtifact, ...]`.
  - In the DAG, each step dict carries `"produces"` (artifact ids) and `"consumes"` (paths).
  - `check_strict_plan`, `check_run`, and the helpers `_plan(target, ctx)` and `_child_env(target)`.
- Consumes:
  - `strict_plan(entry, *, overrides, driver_context) -> StrictPlanReport` (`.status`, `.launch`, `.workflow_dag`, `.to_json()`);
  - `DataArtifact(artifact_id, path_pattern, format, variables=(), description="", produced_by="", optional=False, time_indexed=False)`;
  - core's `predict_data_artifacts` merges `spec.metadata["expected_artifacts"]`.

- [ ] **Step 1: Write the failing K4 unit tests**

  `packages/omnidriver/tests/core/test_record_step_io.py`:
  ```python
  """K4: a record step names the case files it reads and writes."""
  from __future__ import annotations

  from pathlib import Path

  import pytest

  from omnidriver.core.runtime.record_execution import (
      _workflow_dag_for_record, record_artifact_id, record_case_spec, record_step_artifacts,
  )
  from omnidriver.core.tutorial_records import TutorialRecord, TutorialRecordError, WorkflowStep

  RECORD = TutorialRecord(
      name="io",
      native_case_relpath="io",
      allowed_axes=frozenset(),
      workflow_steps=(
          WorkflowStep(step_id="mesh", command=("m",), produces=("a.pts", "a.elem")),
          WorkflowStep(step_id="solve", command=("s",), consumes=("in.par",), produces=("out/v.igb",)),
      ),
  )


  def test_artifacts_come_from_produces():
      artifacts = record_step_artifacts(RECORD, ("mesh", "solve"))
      assert [(a.artifact_id, a.path_pattern, a.produced_by) for a in artifacts] == [
          ("record.mesh.0", "a.pts", "mesh"),
          ("record.mesh.1", "a.elem", "mesh"),
          ("record.solve.0", "out/v.igb", "solve"),
      ]


  def test_unselected_steps_declare_nothing():
      assert [a.artifact_id for a in record_step_artifacts(RECORD, ("solve",))] == ["record.solve.0"]


  def test_dag_carries_ids_and_consumed_paths():
      dag = _workflow_dag_for_record(RECORD, workflow_step_ids=("mesh", "solve"), command_arguments={})
      by_id = {step["id"]: step for step in dag["steps"]}
      assert by_id["mesh"]["produces"] == [record_artifact_id("mesh", 0), record_artifact_id("mesh", 1)]
      assert by_id["solve"]["consumes"] == ["in.par"]


  def test_spec_declares_expected_artifacts(tmp_path: Path):
      spec = record_case_spec(RECORD, case_id="io", staged_case_root=tmp_path,
                              workflow_step_ids=("mesh", "solve"), command_arguments={})
      assert [a.artifact_id for a in spec.metadata["expected_artifacts"]] == [
          "record.mesh.0", "record.mesh.1", "record.solve.0",
      ]


  @pytest.mark.parametrize("bad", ["/abs/path", "../escape"])
  def test_paths_must_be_case_relative(bad):
      with pytest.raises(TutorialRecordError, match="case-relative"):
          WorkflowStep(step_id="x", command=("c",), produces=(bad,))
  ```

- [ ] **Step 2: Run them to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_record_step_io.py -v`
  
  Expected: `ImportError: cannot import name 'record_artifact_id'`.

- [ ] **Step 3: Extend `WorkflowStep`**

  In `core/tutorial_records.py`, change `WorkflowStep` to:
  ```python
  @dataclass(frozen=True)
  class WorkflowStep:
      """One named step in a tutorial record's workflow.

      (existing paragraph about ``command`` and axis arguments stays.)

      ``produces`` and ``consumes`` are case-relative paths the step writes
      and reads (K4, docs/superpowers/specs/2026-09-25-solver-conformance-
      and-opencarp-design.md §5). ``produces`` becomes the record's expected
      artifacts; ``consumes`` becomes the step's DAG ``consumes``, which
      provenance fingerprints. Paths here, never artifact ids: the ids are
      derived (``record_execution.record_artifact_id``).
      """

      step_id: str
      command: tuple[str, ...]
      produces: tuple[str, ...] = ()
      consumes: tuple[str, ...] = ()

      def __post_init__(self) -> None:
          object.__setattr__(self, "command", tuple(self.command))
          object.__setattr__(self, "produces", tuple(self.produces))
          object.__setattr__(self, "consumes", tuple(self.consumes))
          # (keep the existing step_id / command refusals exactly as they are)
          for field_name in ("produces", "consumes"):
              for path in getattr(self, field_name):
                  try:
                      _check_case_relative(path)
                  except Exception as exc:
                      raise TutorialRecordError(
                          f"workflow step {self.step_id!r} {field_name} {path!r} must be case-relative: {exc}"
                      ) from exc
  ```
  Check `_check_case_relative`'s behaviour first: `grep -n "def _check_case_relative" -A 15 packages/omnidriver/src/omnidriver/core/case_write.py`. If it returns a message instead of raising, raise `TutorialRecordError` when the message is non-empty, and keep the wording "must be case-relative".

- [ ] **Step 4: Derive artifacts and DAG fields**

  In `core/runtime/record_execution.py`, add near `record_case_spec`:
  ```python
  from omnidriver.core.runtime.models import DataArtifact


  def record_artifact_id(step_id: str, index: int) -> str:
      """The artifact id a record step's ``index``-th ``produces`` path gets."""
      return f"record.{step_id}.{index}"


  def record_step_artifacts(record: TutorialRecord, workflow_step_ids: Sequence[str]) -> tuple[DataArtifact, ...]:
      """The record's expected artifacts: one per ``produces`` path of each selected step (K4)."""
      selected = set(workflow_step_ids)
      artifacts: list[DataArtifact] = []
      for step in record.workflow_steps:
          if step.step_id not in selected:
              continue
          for index, path in enumerate(step.produces):
              artifacts.append(DataArtifact(
                  artifact_id=record_artifact_id(step.step_id, index),
                  path_pattern=path,
                  format="file",
                  description=f"{record.name} step {step.step_id!r} writes {path}",
                  produced_by=step.step_id,
              ))
      return tuple(artifacts)
  ```
  In `record_case_spec`, add `"expected_artifacts": record_step_artifacts(record, workflow_step_ids),` to the `metadata` dict.

  In `_workflow_dag_for_record`, find the loop that builds each step dict (the dict with keys `id`, `command`, `args` and `depends_on`). After that dict is built and before it is appended, add:
  ```python
          record_step = steps_by_id[step_id]
          step_entry["produces"] = [record_artifact_id(step_id, i) for i in range(len(record_step.produces))]
          step_entry["consumes"] = list(record_step.consumes)
  ```
  Use the function's own names for the step dict and the per-id lookup. If it has no `steps_by_id`, add `steps_by_id = {s.step_id: s for s in record.workflow_steps}` at the top of the function.

- [ ] **Step 5: Run the K4 tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_record_step_io.py packages/omnidriver/tests/core/test_tutorial_records.py -q`
  
  Expected: 0 failed.

- [ ] **Step 6: Declare the toy's io, and write the C5/C6 tests**

  In `e2e_record_plugin.py`, change `_TOY_RECORD`'s step to:
  ```python
      workflow_steps=(WorkflowStep(
          step_id="solve", command=("touch", "solved.marker"),
          consumes=("constant/mesh.json",), produces=("solved.marker",),
      ),),
  ```
  Change the parametrize list in `test_conformance_toy.py` to `["C1", "C2", "C3", "C5", "C6"]`.

- [ ] **Step 7: Run it to verify C5/C6 fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v -k "C5 or C6"`
  
  Expected: `KeyError: "no conformance check 'C5'"`.

- [ ] **Step 8: Write C5 and C6**

  Add to `checks.py`:
  ```python
  import json
  import subprocess
  import sys

  from omnidriver.core.runtime.run_command import omnidriver_run_command
  from omnidriver.core.strict_planning import strict_plan

  _PLAN_DIAGNOSTIC_GROUPS = (
      "validation_diagnostics", "workflow_diagnostics", "catalog_coverage_errors",
      "artifact_diagnostics", "mesh_geometry_diagnostics", "configuration_diagnostics",
  )


  def _plan(target: ConformanceTarget, ctx):
      with _scratch_environment(target):
          return strict_plan(
              target.record,
              overrides={"cases_root": str(target.cases_root), **dict(target.base_study)},
              driver_context=ctx,
          )


  def _plan_errors(report) -> list[str]:
      payload = report.to_json()
      return [
          f"{d.get('code')}: {d.get('message')}"
          for group in _PLAN_DIAGNOSTIC_GROUPS
          for d in payload.get(group, ()) or ()
          if d.get("level") == "error"
      ]


  def _child_env(target: ConformanceTarget) -> dict[str, str]:
      env = dict(os.environ)
      env.update(target.environment)
      env[_SCRATCH_VARIABLE] = str(target.scratch_root)
      return env


  def _run_document_path(report) -> Path:
      return Path(report.launch["output_dir"]) / "run_document.json"


  def check_strict_plan(target: ConformanceTarget) -> CheckVerdict:
      """C5: plan --strict on the record has no errors, and its launch command is runnable as written."""
      report = _plan(target, _context(target))
      errors = _plan_errors(report)
      command = list(report.launch.get("command") or ())
      problems = list(errors)
      if report.status != "ok":
          problems.append(f"plan status {report.status!r}")
      if "--run-document" not in command:
          problems.append(f"launch command {command} does not run the planned document")
      elif not _run_document_path(report).is_file():
          problems.append(f"launch names {_run_document_path(report)}, which was not written")
      return _verdict("C5", not problems, "; ".join(problems) or f"ok; launch {command}")


  def _execute(target: ConformanceTarget, ctx, report) -> tuple[subprocess.CompletedProcess, dict[str, Any] | None]:
      # Never hand-build a run command (main, 2026-09-25): the canonical builder
      # carries --plugin from ctx.plugin_selector, set by load_plugin_context.
      proc = subprocess.run(
          omnidriver_run_command(ctx, "--run-document", str(_run_document_path(report))),
          capture_output=True, text=True, env=_child_env(target),
      )
      try:
          payload = json.loads(proc.stdout)
      except ValueError:
          payload = None
      return proc, payload


  def check_run(target: ConformanceTarget) -> CheckVerdict:
      """C6: the planned document runs, and every artifact the record declares is present."""
      ctx = _context(target)
      report = _plan(target, ctx)
      if report.status != "ok":
          return _verdict("C6", False, f"cannot run: plan failed: {_plan_errors(report)}")
      proc, payload = _execute(target, ctx, report)
      if payload is None:
          return _verdict("C6", False, f"run printed no JSON (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
      reconciliation = payload.get("artifact_reconciliation") or {}
      artifacts = reconciliation.get("artifacts", ())
      declared = [a for a in artifacts if a["artifact_id"].startswith("record.")]
      missing = [a["artifact_id"] for a in artifacts if a["status"] == "missing" and not a.get("optional")]
      problems = []
      if proc.returncode != 0 or payload.get("status") != "ok":
          problems.append(f"run status {payload.get('status')!r}, rc={proc.returncode}")
      if not declared:
          problems.append("the record declares no artifacts (no step `produces`), so a run proves nothing about outputs")
      if missing:
          problems.append(f"missing artifacts {missing}")
      return _verdict("C6", not problems, "; ".join(problems) or f"{len(declared)} declared artifact(s) present")
  ```
  Register `"C5": check_strict_plan, "C6": check_run,`.

- [ ] **Step 9: Run the tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v`
  
  Expected: all pass. If C5 reports a diagnostic, read its code: a real plan error on the toy is a defect to fix in core, never a reason to loosen the check.

- [ ] **Step 10: Commit**

  ```bash
  git add -A packages/omnidriver
  git commit -m "feat(core): record steps declare produces/consumes (K4); conformance C5, C6"
  ```

---

### Task 4: The sweep records each case's reconciliation (K8), then C7

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/sweep_runner.py` (`_record_sweep_run`, new `_child_reconciliation`)
- Modify: `checks.py`, `test_conformance_toy.py`

**Interfaces:**
- Produces:
  - `_child_reconciliation(stdout: str) -> dict | None`;
  - each record-sweep case summary gains `"artifact_reconciliation"` (the child `run --run-document` payload's `artifact_reconciliation`), when the child printed one;
  - `check_sweep`, `_tree_digest(root) -> str`.
- Consumes: the `sweep-run` CLI (`--plugin P --spec S --output-dir D`), whose output has `completed_count`, `failed_count` and `cases[]`.

- [ ] **Step 1: Write the failing tests**

  Change the parametrize list to `["C1", "C2", "C3", "C5", "C6", "C7"]`. Append:
  ```python
  from omnidriver.core.runtime.sweep_runner import _child_reconciliation


  def test_child_reconciliation_reads_the_run_payload():
      assert _child_reconciliation('{"artifact_reconciliation": {"missing_count": 0}}') == {"missing_count": 0}
      assert _child_reconciliation("not json") is None
      assert _child_reconciliation('{"status": "ok"}') is None
  ```

- [ ] **Step 2: Run them to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v -k "C7 or child"`
  
  Expected: `ImportError: cannot import name '_child_reconciliation'`.

- [ ] **Step 3: Keep the child's reconciliation**

  In `sweep_runner.py`, add below `_run_case_process`:
  ```python
  def _child_reconciliation(stdout: str) -> dict[str, Any] | None:
      """The child ``run --run-document``'s artifact reconciliation.

      K8 (docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-
      design.md): the child prints it, and a sweep used to discard it with
      the rest of the child's stdout, so no record of a sweep said whether a
      case produced its declared outputs."""
      try:
          payload = json.loads(stdout)
      except (TypeError, ValueError):
          return None
      value = payload.get("artifact_reconciliation") if isinstance(payload, dict) else None
      return value if isinstance(value, dict) else None
  ```
  In `_record_sweep_run`:
  - Initialise `artifact_reconciliation = None` next to the other per-case locals (`plan_error`, `timeout_error`, …).
  - Right after `result = _run_case_process(...)`, add `artifact_reconciliation = _child_reconciliation(result.stdout)`.
  - After `case_summary` is built, add:
    ```python
            if artifact_reconciliation is not None:
                case_summary["artifact_reconciliation"] = artifact_reconciliation
    ```

- [ ] **Step 4: Write C7**

  Add to `checks.py`:
  ```python
  import hashlib


  def _tree_digest(root: Path) -> str:
      digest = hashlib.sha256()
      for path in sorted(p for p in root.rglob("*") if p.is_file()):
          digest.update(path.relative_to(root).as_posix().encode())
          digest.update(path.read_bytes())
      return digest.hexdigest()


  def check_sweep(target: ConformanceTarget) -> CheckVerdict:
      """C7: a two-point sweep stages, runs and reconciles both cases, and
      leaves the native case byte-identical."""
      ctx = _context(target)
      record = _record(ctx, target.record)
      native = target.cases_root / record.native_case_relpath
      before = _tree_digest(native)
      work = target.scratch_root / "conformance" / "C7"
      if work.exists():
          shutil.rmtree(work)
      work.mkdir(parents=True)
      base = {k: v for k, v in target.base_study.items() if k != target.sweep_name}
      spec = {
          "base": {"entry": target.record, "cases_root": str(target.cases_root), **base},
          "sweep": {"mode": "cross_product", "independent": {target.sweep_name: list(target.sweep_values)}},
      }
      spec_path = work / "sweep.json"
      spec_path.write_text(json.dumps(spec))
      proc = subprocess.run(
          [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", target.plugin,
           "--spec", str(spec_path), "--output-dir", str(work / "out")],
          capture_output=True, text=True, env=_child_env(target),
      )
      try:
          payload = json.loads(proc.stdout)
      except ValueError:
          return _verdict("C7", False, f"sweep printed no JSON (rc={proc.returncode}); stderr tail: {proc.stderr[-800:]}")
      problems = []
      if payload.get("completed_count") != 2 or payload.get("failed_count"):
          problems.append(f"completed {payload.get('completed_count')}, failed {payload.get('failed_count')}")
      for case in payload.get("cases", ()):
          rec = case.get("artifact_reconciliation")
          if rec is None:
              problems.append(f"case {case.get('case_id')} has no artifact reconciliation")
          elif rec.get("missing_count"):
              problems.append(f"case {case.get('case_id')} is missing {rec.get('missing_count')} artifact(s)")
      if _tree_digest(native) != before:
          problems.append(f"the native case {native} changed")
      return _verdict("C7", not problems, "; ".join(problems) or "2 cases completed and reconciled; native tree unchanged")
  ```
  Register `"C7": check_sweep,`.

- [ ] **Step 5: Run the tests to verify they pass, then the existing sweep suites**

  Run:
  ```bash
  /tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py packages/omnidriver/tests/core/test_sweep_runner.py packages/omnidriver/tests/core/test_sweep_run_plugin_propagation.py -q
  ```
  Expected: 0 failed.

- [ ] **Step 6: Commit**

  ```bash
  git add -u packages/omnidriver
  git commit -m "feat(core): sweeps keep each case's artifact reconciliation (K8); conformance C7"
  ```

---

### Task 5: C8, what a step reads is fingerprinted

**Files:**
- Modify: `checks.py`, `conformance_toy.py`, `test_conformance_toy.py`

**Interfaces:**
- Consumes: `enumerate_case_inputs(case_root, *, workflow_dag, driver_context, env=None) -> tuple[ProvenanceComponent, ...]` (fields `kind` and `path`, where `path` is case-relative POSIX).
- Produces: `check_provenance`, and `NoConsumesPlugin` in `conformance_toy.py`.

- [ ] **Step 1: Write the failing tests**

  Add `"C8"` to the parametrize list. Append to `test_conformance_toy.py`:
  ```python
  from plugins.conformance_toy import NO_CONSUMES_PLUGIN


  def test_c8_bites_a_record_that_declares_no_inputs(tmp_path):
      verdict = run_check("C8", toy_conformance_target(tmp_path, plugin=NO_CONSUMES_PLUGIN))
      assert not verdict.passed
      assert "consumes" in verdict.detail
  ```
  Append to `conformance_toy.py`:
  ```python
  from omnidriver.core.tutorial_records import TutorialRecord, WorkflowStep

  NO_CONSUMES_PLUGIN = "plugins.conformance_toy:NoConsumesPlugin"


  class NoConsumesPlugin(E2ERecordPlugin):
      def get_tutorial_records(self):
          return {"toyTutorial": TutorialRecord(
              name="toyTutorial", native_case_relpath="toyTutorial",
              allowed_axes=frozenset({"number_cells"}),
              workflow_steps=(WorkflowStep(step_id="solve", command=("touch", "solved.marker"),
                                           produces=("solved.marker",)),),
          )}
  ```

- [ ] **Step 2: Run them to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v -k C8`
  
  Expected: `KeyError: "no conformance check 'C8'"`.

- [ ] **Step 3: Write C8**

  ```python
  from omnidriver.core.runtime.provenance_inputs import enumerate_case_inputs


  def check_provenance(target: ConformanceTarget) -> CheckVerdict:
      """C8: every file a planned step consumes is fingerprinted."""
      ctx = _context(target)
      report = _plan(target, ctx)
      if report.status != "ok" or report.workflow_dag is None:
          return _verdict("C8", False, f"cannot check: plan failed: {_plan_errors(report)}")
      consumed = sorted({str(e) for s in report.workflow_dag.get("steps", ()) for e in s.get("consumes", ()) or ()})
      if not consumed:
          return _verdict("C8", False, "no step declares `consumes`, so provenance cannot be shown to cover the record's inputs")
      case_root = Path(report.launch["case_root"])
      components = enumerate_case_inputs(case_root, workflow_dag=report.workflow_dag, driver_context=ctx, env=_child_env(target))
      fingerprinted = {c.path for c in components if c.kind == "case_file"}
      missing = [p for p in consumed if p not in fingerprinted]
      return _verdict("C8", not missing, f"consumed but not fingerprinted: {missing}" if missing else f"{len(consumed)} consumed file(s) fingerprinted")
  ```
  Register `"C8": check_provenance,`.

- [ ] **Step 4: Run the tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v`
  
  Expected: all pass, including the C8 bite test.

- [ ] **Step 5: Commit**

  ```bash
  git add -u packages/omnidriver && git commit -m "feat(core): conformance C8 -- consumed inputs are fingerprinted"
  ```

---

### Task 6: C9, the environment, and a real toy preflight

**Files:**
- Modify: `e2e_record_plugin.py` (`get_environment_diagnostics`), `checks.py`, `test_conformance_toy.py`

**Interfaces:**
- Consumes: `ctx.capabilities.environment_preflight.diagnostics(workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None)`. Check its signature first with `grep -n "def diagnostics" packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`, and use exactly what it prints. `StrictDiagnostic(level, code, message, source="", field="")` comes from `omnidriver.core.planning_types`.
- Produces: `check_environment`.

- [ ] **Step 1: Write the failing test.** Add `"C9"` to the parametrize list.

- [ ] **Step 2: Run it.** `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v -k C9`. Expected: `KeyError: "no conformance check 'C9'"`.

- [ ] **Step 3: Give the toy a real preflight**

  In `E2ERecordPlugin`, replace `get_environment_diagnostics` with:
  ```python
      def get_environment_diagnostics(self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None) -> tuple:
          """The toy's one real check: its solver command resolves on the supplied PATH."""
          del workflow_dag, explicit_bashrc, driver_context
          import shutil
          from omnidriver.core.planning_types import StrictDiagnostic

          path = (env or os.environ).get("PATH", "")
          return tuple(
              StrictDiagnostic(level="error", code="e2e_command_not_found",
                               message=f"{command!r} is not on PATH={path!r}")
              for command in sorted(self._solver_commands)
              if shutil.which(command, path=path) is None
          )
  ```

- [ ] **Step 4: Write C9**

  ```python
  def _levels(diagnostics) -> list[tuple[str, str]]:
      out = []
      for d in diagnostics:
          level = getattr(d, "level", None) or (d.get("level") if isinstance(d, dict) else None)
          message = getattr(d, "message", None) or (d.get("message") if isinstance(d, dict) else str(d))
          out.append((level, message))
      return out


  def check_environment(target: ConformanceTarget) -> CheckVerdict:
      """C9: preflight is clean in the supplied environment, and names the
      solver when the solver cannot be found."""
      ctx = _context(target)
      report = _plan(target, ctx)
      if report.workflow_dag is None:
          return _verdict("C9", False, f"cannot check: plan failed: {_plan_errors(report)}")
      preflight = ctx.capabilities.environment_preflight
      env = _child_env(target)
      clean = [m for level, m in _levels(preflight.diagnostics(report.workflow_dag, env=env, driver_context=ctx)) if level == "error"]
      empty = target.scratch_root / "conformance" / "C9-empty-path"
      empty.mkdir(parents=True, exist_ok=True)
      broken = [m for level, m in _levels(preflight.diagnostics(report.workflow_dag, env={**env, "PATH": str(empty)}, driver_context=ctx)) if level == "error"]
      problems = []
      if clean:
          problems.append(f"errors in the supplied environment: {clean}")
      if not any(target.solver_command in m for m in broken):
          problems.append(f"with {target.solver_command!r} off PATH, preflight said {broken or 'nothing'}")
      return _verdict("C9", not problems, "; ".join(problems) or "clean; names the missing solver")
  ```
  Register `"C9": check_environment,`.

- [ ] **Step 5: Run and verify in every core shape**

  ```bash
  /tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v
  /tmp/odconfcore/bin/python -m pytest packages/omnidriver/tests -q
  ```
  Expected: every toy check passes; core alone has 0 failed.

- [ ] **Step 6: Commit**

  ```bash
  git add -u packages/omnidriver && git commit -m "feat(core): conformance C9 -- preflight names a missing solver"
  ```

---

### Task 7: The shape gate

**Files:**
- Create: `scripts/check-core-shape.py`, `scripts/core-shape-baseline.txt`, `packages/omnidriver/tests/core/test_check_core_shape.py`
- Modify: `CLAUDE.md` (invariants table, static-gates row), `.github/workflows/ci.yml` (static-gates job)

**Interfaces:**
- Produces: `python3 scripts/check-core-shape.py [--core-src DIR] [--baseline FILE] [--write-baseline]`. It exits 0 when the counts match the baseline, and 1 on any new (file, token) pair, any higher count, or any baseline entry that no longer holds.

- [ ] **Step 1: Write the failing test**

  `packages/omnidriver/tests/core/test_check_core_shape.py`:
  ```python
  """The shape gate: core gains no new OpenFOAM layout token, and its recorded debt only shrinks."""
  from __future__ import annotations

  import subprocess
  import sys
  from pathlib import Path

  import pytest


  def _script() -> Path:
      """The gate script, found by marker from this test file. Tests always
      run from a checkout (they are not in the wheel), so a miss is a failure."""
      for parent in Path(__file__).resolve().parents:
          candidate = parent / "scripts" / "check-core-shape.py"
          if candidate.is_file():
              return candidate
      pytest.fail("no ancestor of this test holds scripts/check-core-shape.py")


  def _gate(*args: str) -> subprocess.CompletedProcess:
      return subprocess.run([sys.executable, str(_script()), *args], capture_output=True, text=True)


  def test_repository_matches_its_baseline():
      result = _gate()
      assert result.returncode == 0, result.stdout + result.stderr


  def test_a_new_token_fails(tmp_path: Path):
      core = tmp_path / "core"
      core.mkdir()
      (core / "m.py").write_text('PATH = "system/controlDict"\n')
      baseline = tmp_path / "baseline.txt"
      baseline.write_text("")
      result = _gate("--core-src", str(core), "--baseline", str(baseline))
      assert result.returncode == 1
      assert "controlDict" in result.stdout


  def test_comments_and_docstrings_do_not_count(tmp_path: Path):
      core = tmp_path / "core"
      core.mkdir()
      (core / "m.py").write_text('"""Mentions polyMesh."""\n# and blockMesh\nX = 1\n')
      baseline = tmp_path / "baseline.txt"
      baseline.write_text("")
      assert _gate("--core-src", str(core), "--baseline", str(baseline)).returncode == 0


  def test_a_shrunk_count_must_be_recorded(tmp_path: Path):
      core = tmp_path / "core"
      core.mkdir()
      (core / "m.py").write_text("X = 1\n")
      baseline = tmp_path / "baseline.txt"
      baseline.write_text("m.py\tbashrc\t2\ttest debt\n")
      result = _gate("--core-src", str(core), "--baseline", str(baseline))
      assert result.returncode == 1
      assert "shrank" in result.stdout
  ```

- [ ] **Step 2: Run it to verify it fails**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_check_core_shape.py -v`
  
  Expected: all four fail, because the script does not exist.

- [ ] **Step 3: Write the gate**

  `scripts/check-core-shape.py`:
  ```python
  #!/usr/bin/env python3
  """Core must not assume the world is an OpenFOAM case (spec 2026-09-25 §6).

  Counts OpenFOAM layout tokens in core's identifiers and string literals
  (comments and docstrings are prose, not coupling) per (file, token), and
  compares them with scripts/core-shape-baseline.txt. The baseline is recorded
  debt, not a waiver list:
  - a new (file, token) pair fails;
  - a higher count fails;
  - a count that shrank also fails until the baseline is edited to match, so
    the debt can only go down.
  Baseline line format: ``<path relative to core src>\\t<token>\\t<count>\\t<reason>``.
  """
  from __future__ import annotations

  import argparse
  import ast
  import sys
  from collections import Counter
  from pathlib import Path

  REPO_ROOT = Path(__file__).resolve().parents[1]
  CORE_SRC = REPO_ROOT / "packages/omnidriver/src/omnidriver"
  BASELINE = REPO_ROOT / "scripts/core-shape-baseline.txt"
  TOKENS = (
      "controlDict", "fvSchemes", "fvSolution", "polyMesh", "blockMesh", "decomposePar",
      "reconstructPar", "processor", "case.foam", "Allrun", "Allclean", "bashrc",
      "WM_PROJECT", "FOAM_", "foamlib",
  )


  def _docstring_ids(tree: ast.AST) -> set[int]:
      ids = set()
      for node in ast.walk(tree):
          if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
              body = getattr(node, "body", [])
              if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                  ids.add(id(body[0].value))
      return ids


  def _texts(tree: ast.AST):
      skip = _docstring_ids(tree)
      for node in ast.walk(tree):
          if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
              yield node.value
          elif isinstance(node, ast.Name):
              yield node.id
          elif isinstance(node, ast.Attribute):
              yield node.attr
          elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
              yield node.name
          elif isinstance(node, ast.arg):
              yield node.arg
          elif isinstance(node, ast.keyword) and node.arg:
              yield node.arg
          elif isinstance(node, ast.alias):
              yield node.name


  def count(core_src: Path) -> Counter:
      counts: Counter = Counter()
      for path in sorted(core_src.rglob("*.py")):
          tree = ast.parse(path.read_text(), filename=str(path))
          rel = path.relative_to(core_src).as_posix()
          for text in _texts(tree):
              for token in TOKENS:
                  hits = text.count(token)
                  if hits:
                      counts[(rel, token)] += hits
      return counts


  def read_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
      entries = {}
      for line in path.read_text().splitlines():
          if not line.strip() or line.startswith("#"):
              continue
          rel, token, number, *reason = line.split("\t")
          entries[(rel, token)] = (int(number), reason[0] if reason else "")
      return entries


  def main() -> int:
      parser = argparse.ArgumentParser()
      parser.add_argument("--core-src", type=Path, default=CORE_SRC)
      parser.add_argument("--baseline", type=Path, default=BASELINE)
      parser.add_argument("--write-baseline", action="store_true",
                          help="record today's counts; every reason must then be written by hand")
      args = parser.parse_args()
      counts = count(args.core_src)
      if args.write_baseline:
          lines = [f"{rel}\t{token}\t{n}\tTODO-reason" for (rel, token), n in sorted(counts.items())]
          args.baseline.write_text("\n".join(lines) + "\n")
          return 0
      baseline = read_baseline(args.baseline)
      problems = []
      for key, n in sorted(counts.items()):
          recorded = baseline.get(key)
          if recorded is None:
              problems.append(f"NEW    {key[0]}: {key[1]} x{n} -- core must not name OpenFOAM layout")
          elif n > recorded[0]:
              problems.append(f"GREW   {key[0]}: {key[1]} {recorded[0]} -> {n}")
          elif n < recorded[0]:
              problems.append(f"shrank {key[0]}: {key[1]} {recorded[0]} -> {n}; edit the baseline to {n}")
      for key, (n, _reason) in sorted(baseline.items()):
          if key not in counts:
              problems.append(f"shrank {key[0]}: {key[1]} {n} -> 0; delete this baseline line")
      for problem in problems:
          print(problem)
      return 1 if problems else 0


  if __name__ == "__main__":
      sys.exit(main())
  ```

- [ ] **Step 4: Record the baseline with reasons written by hand**

  Run `python3 scripts/check-core-shape.py --write-baseline`, then open `scripts/core-shape-baseline.txt`.
  - Replace every `TODO-reason` with the real reason: the symbol, and why core still names the token. For example, `explicit_bashrc parameter threaded through strict_plan and the CLI; the environment-loading seam predates §12`.
  - Add a header comment pointing to spec §6.
  - Then run `grep -c TODO-reason scripts/core-shape-baseline.txt`. Expected: `0`.
  
  The measured size on the branch was about 10 files and 104 hits, 77 of them `bashrc`.

- [ ] **Step 5: Run the tests to verify they pass**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_check_core_shape.py -v && python3 scripts/check-core-shape.py`
  
  Expected: 4 passed; the gate exits 0.

- [ ] **Step 6: Wire it in, and commit**

  - In `.github/workflows/ci.yml`'s static-gates job, add the line `python3 scripts/check-core-shape.py` after `check-import-boundaries.py`.
  - In `CLAUDE.md`'s invariants table, add the row `| core names no OpenFOAM layout beyond its recorded, shrinking debt | scripts/check-core-shape.py (baseline scripts/core-shape-baseline.txt; new tokens never added) |`.
  - Add the script to the static-gates row of the verification table.
  
  ```bash
  git add scripts/check-core-shape.py scripts/core-shape-baseline.txt packages/omnidriver/tests/core/test_check_core_shape.py CLAUDE.md .github/workflows/ci.yml
  git commit -m "feat: the core shape gate -- OpenFOAM layout debt is recorded and can only shrink"
  ```

---

### Task 8: The `omnidriver-opencarp` package and its `.par` format

**Files:**
- Create: `packages/omnidriver-opencarp/pyproject.toml`
- Create: `src/omnidriver/opencarp/__init__.py`, `par_format.py`
- Create: `tests/opencarp_native.py`, `tests/test_par_format.py`, `tests/test_par_format_native.py`
- Modify: root `pyproject.toml` (`pythonpath`), `scripts/check-import-boundaries.py`, `scripts/check-case-writes.py` (K7, reduced)

**Interfaces:**
- Produces:
  - `ParFormatError(ValueError)`;
  - `ParAssignment(line_index: int, key: str, value: str | None)`;
  - `parse_par(text) -> tuple[ParAssignment, ...]`;
  - `read_raw(text, key) -> str | None` (the last assignment wins, F8);
  - `unquote(raw) -> str`;
  - `patch_par(text, values: Mapping[str, str]) -> str`;
  - `format_value(value, value_kind) -> str`;
  - `values_agree(value_kind, requested, current) -> bool`;
  - `APPENDED_BLOCK_HEADER`.
  - In tests: `opencarp_tutorials_root() -> Path` and `require_opencarp_binary() -> None`.

- [ ] **Step 1: Package metadata**

  `packages/omnidriver-opencarp/pyproject.toml`:
  ```toml
  [build-system]
  requires = ["setuptools>=68", "wheel"]
  build-backend = "setuptools.build_meta"

  [project]
  name = "omnidriver-opencarp"
  version = "0.1.0"
  description = "openCARP cardiac electrophysiology plugin for OmniD, driven as binary + .par + mesh."
  requires-python = ">=3.11"
  dependencies = ["omnidriver>=0.1.0"]

  [project.entry-points."omnidriver.plugins"]
  opencarp = "omnidriver.opencarp.plugin:OpenCARPPlugin"

  [tool.setuptools.packages.find]
  where = ["src"]

  [tool.setuptools.package-data]
  "omnidriver.opencarp" = ["opencarp.yaml", "opencarp_parameters.json"]

  [tool.pytest.ini_options]
  testpaths = ["tests"]
  pythonpath = ["tests"]
  addopts = "--import-mode=importlib"
  markers = [
      "native: needs OMNIDRIVER_OPENCARP_TUTORIALS and the openCARP binary; fails (not skips) if unset",
  ]
  ```
  `src/omnidriver/opencarp/__init__.py`: `"""openCARP plugin for OmniD. Evidence: docs/solver-learning/opencarp.md."""`

  Add `"packages/omnidriver-opencarp/tests",` to the root `pyproject.toml`'s `pythonpath` list. Make sure the `native` marker text there also mentions `OMNIDRIVER_OPENCARP_TUTORIALS`.

  Install it:
  ```bash
  VIRTUAL_ENV=/tmp/odconf uv pip install -q -e packages/omnidriver-opencarp
  ```

- [ ] **Step 2: The native helper (uniquely named, not in conftest; CLAUDE.md traps)**

  `packages/omnidriver-opencarp/tests/opencarp_native.py`:
  ```python
  """Supplied inputs for native openCARP tests. Nothing here is discovered:
  the tutorials tree comes from OMNIDRIVER_OPENCARP_TUTORIALS, and the binary
  from the ambient PATH and DYLD_LIBRARY_PATH (evidence A4-A6)."""
  from __future__ import annotations

  import os
  import shutil
  import subprocess
  from pathlib import Path

  import pytest

  NIEDERER_RELPATH = "02_EP_tissue/03E_study_resolution"


  def opencarp_tutorials_root() -> Path:
      value = os.environ.get("OMNIDRIVER_OPENCARP_TUTORIALS")
      if not value:
          pytest.fail(
              "OMNIDRIVER_OPENCARP_TUTORIALS is not set. A @pytest.mark.native openCARP test "
              "needs openCARP's tutorials tree supplied explicitly, e.g.\n"
              "  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials "
              "DYLD_LIBRARY_PATH=/opt/homebrew/lib pytest -m native"
          )
      root = Path(value)
      if not (root / NIEDERER_RELPATH / "nversion.par").is_file():
          pytest.fail(f"OMNIDRIVER_OPENCARP_TUTORIALS={value!r} has no {NIEDERER_RELPATH}/nversion.par")
      return root


  def require_opencarp_binary() -> None:
      binary = shutil.which("openCARP")
      if binary is None:
          pytest.fail("openCARP is not on PATH")
      proc = subprocess.run([binary, "-buildinfo"], capture_output=True, text=True)
      if "GIT tag" not in proc.stdout:
          pytest.fail("openCARP cannot start (on macOS, set DYLD_LIBRARY_PATH to the directory "
                      "holding libsundials_cvode; evidence A4-A6): " + proc.stderr[-400:])
  ```

- [ ] **Step 3: Write the failing format tests**

  `packages/omnidriver-opencarp/tests/test_par_format.py`:
  ```python
  """The .par rules, each one tied to a line of evidence in docs/solver-learning/opencarp.md."""
  from __future__ import annotations

  import pytest

  from omnidriver.opencarp.par_format import (
      APPENDED_BLOCK_HEADER, ParFormatError, format_value, parse_par, patch_par, read_raw, unquote, values_agree,
  )

  TEXT = 'num_stim = 1 \nstim[0].name = "S1"\t# label\n# comment\n\ngregion[0].g_il = 0.17\n'


  def test_parse_keys_and_raw_values():
      assert [(a.key, a.value) for a in parse_par(TEXT)] == [
          ("num_stim", "1"), ("stim[0].name", '"S1"'), ("gregion[0].g_il", "0.17"),
      ]


  def test_whitespace_separator_F9():
      text = "stim[0].elec.p0[2] 0\n"
      assert read_raw(text, "stim[0].elec.p0[2]") == "0"
      assert patch_par(text, {"stim[0].elec.p0[2]": "5"}) == "stim[0].elec.p0[2] 5\n"


  def test_last_assignment_wins_F8():
      assert read_raw("spacedt = 1\nspacedt = 2\n", "spacedt") == "2"


  def test_patch_in_place_keeps_everything_else():
      patched = patch_par(TEXT, {"gregion[0].g_il": "0.2"})
      assert patched == TEXT.replace("0.17", "0.2")


  def test_patch_keeps_an_inline_comment():
      assert patch_par(TEXT, {"stim[0].name": '"S2"'}).splitlines()[1] == 'stim[0].name = "S2"\t# label'


  def test_patch_appends_an_absent_key_in_a_marked_block():
      patched = patch_par(TEXT, {"tend": "20.0"})
      assert patched.startswith(TEXT)
      assert patched.endswith(f"\n{APPENDED_BLOCK_HEADER}\ntend = 20.0\n")


  def test_patch_is_idempotent():
      once = patch_par(TEXT, {"tend": "20.0"})
      assert patch_par(once, {"tend": "20.0"}) == once


  def test_patch_refuses_a_repeated_key_F8():
      with pytest.raises(ParFormatError, match="spacedt"):
          patch_par("spacedt = 1\nspacedt = 2\n", {"spacedt": "3"})


  def test_unparseable_line_is_refused_by_line_number():
      # Any "<key><space><value>" is valid syntax (F9), so only a line with no
      # key at its start is malformed.
      with pytest.raises(ParFormatError, match="line 2"):
          parse_par("a = 1\n= 5\n")


  @pytest.mark.parametrize(("value", "kind", "text"), [
      (True, "boolean", "1"), (False, "boolean", "0"),       # F1: only 0 and false mean off
      (3, "integer", "3"), (0.17, "scalar", "0.17"), (500, "scalar", "500.0"),
      ("tenTusscherPanfilov", "string", "tenTusscherPanfilov"), ("flags=EPI", "string", "flags=EPI"),
      ("two words", "string", '"two words"'), ("", "string", '""'),
  ])
  def test_format_value(value, kind, text):
      assert format_value(value, kind) == text


  def test_format_refuses_a_non_bool_flag():
      with pytest.raises(ParFormatError):
          format_value("no", "boolean")


  def test_values_agree_numerically_and_unquoted():
      assert values_agree("scalar", 0.001, "1e-3")
      assert values_agree("integer", 2, "2")
      assert values_agree("string", "S1", '"S1"')
      assert values_agree("boolean", True, "1") and not values_agree("boolean", True, "0")
      assert not values_agree("scalar", 0.2, None)


  def test_unquote():
      assert unquote('"S1"') == "S1" and unquote("S1") == "S1"
  ```

  `packages/omnidriver-opencarp/tests/test_par_format_native.py`:
  ```python
  """Every .par openCARP ships parses, and an empty patch returns it byte for byte."""
  from __future__ import annotations

  import pytest

  from omnidriver.opencarp.par_format import parse_par, patch_par
  from opencarp_native import opencarp_tutorials_root

  pytestmark = pytest.mark.native


  def test_every_shipped_par_round_trips():
      files = sorted(opencarp_tutorials_root().rglob("*.par"))
      assert len(files) >= 20, f"expected openCARP's shipped .par files, found {len(files)}"
      for path in files:
          text = path.read_text()
          parse_par(text)
          assert patch_par(text, {}) == text, path
  ```

- [ ] **Step 4: Run them to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_par_format.py -v`
  
  Expected: `ModuleNotFoundError: No module named 'omnidriver.opencarp.par_format'`.

- [ ] **Step 5: Write `par_format.py`**

  ```python
  """openCARP's .par format: parse, patch in place, and spell values.

  Pure text in, text out; nothing here touches the filesystem. Behaviour is
  taken from the binary (docs/solver-learning/opencarp.md):
  - F1: a Flag is off only for ``0`` or ``false``; ``no``/``off`` mean on,
    so omniD writes ``1``/``0`` only.
  - F8: when a key is assigned twice, openCARP uses the last assignment.
  - F9: the separator is ``=`` or whitespace alone (``spacedt 2``); both are
    read, and a patch keeps whichever the line used.
  """
  from __future__ import annotations

  import re
  from dataclasses import dataclass
  from typing import Any, Mapping

  APPENDED_BLOCK_HEADER = "# --- set by omniD: keys the native file does not assign ---"

  _KEY = r"[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])*)*"
  _ASSIGNMENT = re.compile(
      rf'^(?P<lead>\s*)(?P<key>{_KEY})(?P<eq>\s*=\s*|\s+)(?P<value>"[^"]*"|[^#\s](?:[^#]*[^#\s])?)?(?P<trail>\s*(?:#.*)?)$'
  )


  class ParFormatError(ValueError):
      """A .par text or value omniD refuses to read or write, naming why."""


  @dataclass(frozen=True)
  class ParAssignment:
      line_index: int
      key: str
      value: str | None


  def parse_par(text: str) -> tuple[ParAssignment, ...]:
      assignments = []
      for index, line in enumerate(text.splitlines()):
          stripped = line.strip()
          if not stripped or stripped.startswith("#"):
              continue
          match = _ASSIGNMENT.match(line)
          if match is None:
              raise ParFormatError(f"line {index + 1} is not a .par assignment: {line!r}")
          assignments.append(ParAssignment(index, match["key"], match["value"]))
      return tuple(assignments)


  def read_raw(text: str, key: str) -> str | None:
      """The raw value openCARP uses for ``key``: the last assignment (F8), or None if absent."""
      value = None
      for assignment in parse_par(text):
          if assignment.key == key:
              value = assignment.value
      return value


  def unquote(raw: str) -> str:
      return raw[1:-1] if len(raw) >= 2 and raw[0] == raw[-1] == '"' else raw


  def patch_par(text: str, values: Mapping[str, str]) -> str:
      """Rewrite each key's value where it stands; append keys the text does not assign.

      ``values`` maps a key to its already-spelled value (``format_value``).
      A key assigned more than once is refused: openCARP would read the last
      one (F8), so which one a patch means is ambiguous."""
      by_key: dict[str, list[ParAssignment]] = {}
      for assignment in parse_par(text):
          by_key.setdefault(assignment.key, []).append(assignment)
      lines = text.splitlines(keepends=True)
      appended: list[str] = []
      for key, new_value in values.items():
          found = by_key.get(key, [])
          if len(found) > 1:
              raise ParFormatError(
                  f"{key} is assigned {len(found)} times; openCARP uses the last one (F8), "
                  "so which one a patch means is ambiguous -- refusing"
              )
          if not found:
              appended.append(f"{key} = {new_value}\n")
              continue
          index = found[0].line_index
          line = lines[index]
          body = line.rstrip("\r\n")
          ending = line[len(body):]
          match = _ASSIGNMENT.match(body)
          lines[index] = f'{match["lead"]}{match["key"]}{match["eq"]}{new_value}{match["trail"]}{ending}'
      if appended:
          text_so_far = "".join(lines)
          if lines and not lines[-1].endswith("\n"):
              lines[-1] += "\n"
          if APPENDED_BLOCK_HEADER not in text_so_far:
              lines.append(f"\n{APPENDED_BLOCK_HEADER}\n")
          lines.extend(appended)
      return "".join(lines)


  def format_value(value: Any, value_kind: str) -> str:
      if value_kind == "boolean":
          if not isinstance(value, bool):
              raise ParFormatError(f"a Flag takes true or false, got {value!r} (openCARP reads 'no' as on: F1)")
          return "1" if value else "0"
      if value_kind == "integer":
          if isinstance(value, bool) or int(value) != value:
              raise ParFormatError(f"expected an integer, got {value!r}")
          return str(int(value))
      if value_kind == "scalar":
          if isinstance(value, bool):
              raise ParFormatError(f"expected a number, got {value!r}")
          return repr(float(value))
      if value_kind == "string":
          text = str(value)
          if '"' in text:
              raise ParFormatError(f"a .par string cannot contain a double quote: {text!r}")
          return f'"{text}"' if (not text or "#" in text or any(c.isspace() for c in text)) else text
      raise ParFormatError(f"no .par spelling for value kind {value_kind!r}")


  def values_agree(value_kind: str, requested: Any, current: Any) -> bool:
      """Whether ``current`` (raw .par text, as the reader returns it) equals ``requested``."""
      if current is None:
          return False
      text = unquote(str(current))
      try:
          if value_kind == "boolean":
              return text in ("0", "1") and (text == "1") == bool(requested)
          if value_kind == "integer":
              return int(text) == int(requested)
          if value_kind == "scalar":
              return float(text) == float(requested)
      except (TypeError, ValueError):
          return False
      return text == str(requested)
  ```
  The header check keeps the appended block single: a key appended once is
  found in place by the next patch (see `test_patch_is_idempotent`).

- [ ] **Step 6: Run the tests to verify they pass, including against the real tree**

  ```bash
  /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_par_format.py -v
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_par_format_native.py -v -m native
  ```
  Expected: all pass. If a shipped file does not parse, that is new evidence:
  1. Log it as a new F-entry in `docs/solver-learning/opencarp.md`, with the file and the line.
  2. Settle what openCARP does with that line using a real run.
  3. Only then extend `_ASSIGNMENT`.

- [ ] **Step 7: The gates learn the package (K7, reduced)**

  - In `scripts/check-import-boundaries.py`, define `OPENCARP_SRC = REPO_ROOT / "packages/omnidriver-opencarp/src/omnidriver/opencarp"`. In `main()`, add a check block for it modelled on `CARDIACCORE_SRC`'s, forbidding `("foamlib", "omnidriver.openfoam", "omnidriver.cardiacfoam", "omnidriver.cardiaccore")`.
  - In `scripts/check-case-writes.py`:
    - add `OPENCARP_RECORDS_SRC = REPO_ROOT / "packages/omnidriver-opencarp/src/omnidriver/opencarp/records"`;
    - append it to `SCANNED_ROOTS`;
    - add `"omnidriver.opencarp.plugin"` to `FORBIDDEN_IMPORT_MODULES` (the plugin module holds the renderer).

  Prove the new boundary block bites: temporarily add `import foamlib` to `par_format.py`, run `python3 scripts/check-import-boundaries.py` (expected: exit 1, naming the file), then remove the import.

- [ ] **Step 8: Commit**

  ```bash
  git add packages/omnidriver-opencarp pyproject.toml scripts/check-import-boundaries.py scripts/check-case-writes.py
  git commit -m "feat(opencarp): package skeleton and the .par format (F1, F8), round-tripped on every shipped file"
  ```

---

### Task 9: The parameter catalog from the binary, and the `string` value kind (K6)

**Files:**
- Create: `src/omnidriver/opencarp/catalog.py`, `catalog_generation.py`, `opencarp_parameters.json` (generated)
- Create: `scripts/generate-opencarp-catalog.py`
- Create: `tests/test_catalog.py`, `tests/test_catalog_native.py`
- Modify: `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py` (K6), plus every parallel enumeration of value kinds (Step 5)

**Interfaces:**
- Produces:
  - `ParameterSpec(name, opencarp_type, value_kind, default, minimum, maximum, menu, allocates, description)`;
  - `load_catalog() -> Catalog`, where `Catalog.parameters: dict[str, ParameterSpec]` and `Catalog.identity: dict[str, str]`;
  - `template_name(key) -> str`;
  - `build_catalog(binary="openCARP", env=None) -> dict`, `parse_help_list(text)`, `parse_help_detail(concrete, text)`;
  - `"string"` in `VALUE_KINDS`.

- [ ] **Step 1: Write the failing tests**

  `tests/test_catalog.py`:
  ```python
  """The committed catalog, as generated from openCARP v18.1's +Help (evidence B1-B5, G6)."""
  from __future__ import annotations

  from omnidriver.opencarp.catalog import load_catalog, template_name


  def test_identity_is_the_binary_and_carries_no_repository_url():
      identity = load_catalog().identity
      assert identity["tag"] == "v18.1"
      assert set(identity) == {"tag", "hash"}      # never the CI URL (G3)


  def test_template_names():
      assert template_name("stim[0].pulse.strength") == "stim[Int].pulse.strength"
      assert template_name("phys_region[1].ID[3]") == "phys_region[Int].ID[Int]"


  def test_known_parameters_B2_B5():
      p = load_catalog().parameters
      assert (p["bidomain"].value_kind, p["bidomain"].default, p["bidomain"].menu) == ("integer", "0", ("2", "1", "0"))
      assert (p["num_stim"].default, p["num_stim"].allocates) == ("2", ("stim", "stimulus"))
      assert p["compute_APD"].value_kind == "boolean"
      assert p["imp_region[Int].im"].value_kind == "string"
      assert p["tend"].minimum == "dt/1000."


  def test_whole_array_shorthand_has_no_value_kind():
      p = load_catalog().parameters
      shorthand = [s for s in p.values() if s.opencarp_type.startswith("{")]
      assert shorthand and all(s.value_kind is None for s in shorthand)


  def test_all_266_parameters():
      assert len(load_catalog().parameters) == 266
  ```

  `tests/test_catalog_native.py`:
  ```python
  """Drift gate: the committed catalog is exactly what the installed binary says."""
  from __future__ import annotations

  import json
  from importlib import resources

  import pytest

  from omnidriver.opencarp.catalog_generation import build_catalog
  from opencarp_native import require_opencarp_binary

  pytestmark = pytest.mark.native


  def test_committed_catalog_matches_the_binary():
      require_opencarp_binary()
      committed = json.loads(resources.files("omnidriver.opencarp").joinpath("opencarp_parameters.json").read_text())
      assert build_catalog() == committed, "regenerate: python scripts/generate-opencarp-catalog.py"
  ```

  Append to core's `packages/omnidriver/tests/core/test_tutorial_records.py`, or to a new `test_value_kinds.py` beside it:
  ```python
  from omnidriver.core.contracts.dictionary import VALUE_KINDS, validate_value_shape


  def test_string_value_kind_K6():
      assert "string" in VALUE_KINDS
      assert validate_value_shape("string", "") == ()
      assert validate_value_shape("string", "two words") == ()
      assert validate_value_shape("string", 3) == ("must be a string",)
  ```

- [ ] **Step 2: Run them to verify they fail**

  Run: `/tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_catalog.py -q; /tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core -q -k string_value_kind`
  
  Expected: `ModuleNotFoundError` for the catalog; an assertion failure for `"string"`.

- [ ] **Step 3: Write K6**

  In `core/contracts/dictionary.py`, add `"string"` to `VALUE_KINDS`. In `validate_value_shape`, add before the `word`/`enum` branch:
  ```python
      if kind == "string":
          # K6 (spec 2026-09-25 §5): any text, including empty or with spaces.
          # openCARP's String/RFile/WFile parameters need it; ``word`` refuses both.
          return () if isinstance(value, str) else ("must be a string",)
  ```
  Find parallel enumerations and add `"string"` to each one that lists every kind:
  ```bash
  grep -rn '"integer_list"' packages/*/src packages/omnidriver/src/omnidriver/schemas scripts
  ```
  A JSON schema `enum` of value kinds is the likely one. Then run `/tmp/odconf/bin/python scripts/export-capability-seams.py --check`; expected exit 0.

- [ ] **Step 4: Write the catalog code**

  `src/omnidriver/opencarp/catalog.py`:
  ```python
  """openCARP's parameter catalog, generated from the binary (catalog_generation.py).

  Names are +Help's template form (``stim[Int].pulse.strength``). A whole-array
  shorthand (type ``{ 3 x Float }``) has no value kind; the validator asks for
  its indexed elements instead."""
  from __future__ import annotations

  import json
  import re
  from dataclasses import dataclass
  from functools import cache
  from importlib import resources

  VALUE_KIND_BY_TYPE = {
      "Int": "integer", "Short": "integer", "Long": "integer",
      "Float": "scalar", "Double": "scalar",
      "Flag": "boolean",                               # written 1/0 only (F1)
      "String": "string", "RFile": "string", "WFile": "string",
  }
  _INDEX = re.compile(r"\[\d+\]")


  @dataclass(frozen=True)
  class ParameterSpec:
      name: str
      opencarp_type: str
      value_kind: str | None
      default: str | None
      minimum: str | None
      maximum: str | None
      menu: tuple[str, ...]
      allocates: tuple[str, ...]
      description: str


  @dataclass(frozen=True)
  class Catalog:
      identity: dict[str, str]
      parameters: dict[str, ParameterSpec]


  def template_name(key: str) -> str:
      return _INDEX.sub("[Int]", key)


  @cache
  def load_catalog() -> Catalog:
      payload = json.loads(resources.files(__package__).joinpath("opencarp_parameters.json").read_text())
      parameters = {
          entry["name"]: ParameterSpec(
              name=entry["name"], opencarp_type=entry["type"],
              value_kind=VALUE_KIND_BY_TYPE.get(entry["type"]),
              default=entry["default"], minimum=entry["minimum"], maximum=entry["maximum"],
              menu=tuple(entry["menu"]), allocates=tuple(entry["allocates"]),
              description=entry["description"],
          )
          for entry in payload["parameters"]
      }
      return Catalog(identity=dict(payload["opencarp"]), parameters=parameters)
  ```

  `src/omnidriver/opencarp/catalog_generation.py`:
  ```python
  """Build the catalog by asking the installed binary (evidence B1-B6, G6).

  +Help lists every parameter with its type. +Help <name> gives the detail,
  and needs a concrete index (``stim[0]...``, not ``stim[Int]...``; B3/B4).
  Build identity comes from -buildinfo's tag and hash lines only: its
  repository line embeds a CI token (A8, G3)."""
  from __future__ import annotations

  import re
  import shutil
  import subprocess
  from typing import Any, Mapping

  _LIST_LINE = re.compile(r"^\s+'?-(?P<name>[^' ]+)'?\s+(?P<type>.+?)\s*$")
  _FIELD = re.compile(r"^\t(type|default|min|max):\s*(.*)$")
  _TYPED = re.compile(r"^\((\w+)\)\((.*)\)$")
  _BLOCK = re.compile(r"^\t(menu|Depends on|Changes the allocation of|Changes the default value of): \{$")
  _MENU_ITEM = re.compile(r"^\t\t\((\w+)\)\((.*?)\)\t(.*)$")


  class CatalogError(RuntimeError):
      pass


  def _run(binary: str, args: list[str], env: Mapping[str, str] | None) -> str:
      proc = subprocess.run([binary, *args], capture_output=True, text=True, env=dict(env) if env else None)
      return proc.stdout + proc.stderr


  def parse_help_list(text: str) -> list[tuple[str, str]]:
      lines = text.splitlines()
      try:
          start = lines.index("Parameters:") + 1
      except ValueError as exc:
          raise CatalogError("+Help printed no 'Parameters:' section") from exc
      out = []
      for line in lines[start:]:
          match = _LIST_LINE.match(line)
          if match:
              out.append((match["name"], match["type"].strip("'")))
      return out


  def _typed(value: str | None) -> str | None:
      if value is None:
          return None
      match = _TYPED.match(value)
      return match[2] if match else value


  def parse_help_detail(concrete: str, text: str) -> dict[str, Any]:
      lines = text.splitlines()
      try:
          start = lines.index(f"{concrete}:")
      except ValueError as exc:
          raise CatalogError(f"+Help {concrete} printed no detail block") from exc
      description: list[str] = []
      fields: dict[str, str] = {}
      blocks: dict[str, list[str]] = {}
      block = None
      for line in lines[start + 1:]:
          if block is not None:
              if line == "\t}":
                  block = None
              else:
                  blocks[block].append(line)
              continue
          if (m := _BLOCK.match(line)):
              block = m[1]
              blocks[block] = []
          elif (m := _FIELD.match(line)):
              fields[m[1]] = m[2].strip()
          elif not fields and line.strip():
              description.append(line.strip())
      menu = tuple(m[2] for item in blocks.get("menu", []) if (m := _MENU_ITEM.match(item)))
      allocates = tuple(i.strip() for i in blocks.get("Changes the allocation of", []) if i.strip() and "[" not in i)
      return {
          "default": _typed(fields.get("default")), "minimum": _typed(fields.get("min")),
          "maximum": _typed(fields.get("max")), "menu": list(menu), "allocates": list(allocates),
          "description": " ".join(description),
      }


  def build_identity(binary: str, env: Mapping[str, str] | None) -> dict[str, str]:
      identity = {}
      for line in _run(binary, ["-buildinfo"], env).splitlines():
          if line.startswith("*** GIT tag:"):
              identity["tag"] = line.split(":", 1)[1].strip()
          elif line.startswith("*** GIT hash:"):
              identity["hash"] = line.split(":", 1)[1].strip()
      if set(identity) != {"tag", "hash"}:
          raise CatalogError("-buildinfo printed no tag/hash; is DYLD_LIBRARY_PATH set? (A4-A6)")
      return identity


  def build_catalog(binary: str = "openCARP", env: Mapping[str, str] | None = None) -> dict[str, Any]:
      resolved = shutil.which(binary, path=(env or {}).get("PATH")) if env else shutil.which(binary)
      if resolved is None:
          raise CatalogError(f"{binary} is not on PATH")
      parameters = []
      for name, opencarp_type in parse_help_list(_run(resolved, ["+Help"], env)):
          if opencarp_type.startswith("{"):
              # B8: a whole-array shorthand has no detail block under any
              # spelling; only its elements do. It is kept so the validator
              # can name it and ask for elements.
              detail = {"default": None, "minimum": None, "maximum": None,
                        "menu": [], "allocates": [], "description": ""}
          else:
              concrete = name.replace("[Int]", "[0]")
              detail = parse_help_detail(concrete, _run(resolved, ["+Help", concrete], env))
          parameters.append({"name": name, "type": opencarp_type, **detail})
      return {"opencarp": build_identity(resolved, env), "parameters": parameters}
  ```

  `scripts/generate-opencarp-catalog.py`:
  ```python
  #!/usr/bin/env python3
  """Regenerate packages/omnidriver-opencarp/.../opencarp_parameters.json from the
  installed openCARP (needs DYLD_LIBRARY_PATH on macOS). The native drift test
  fails until the committed file matches the binary."""
  import json
  from pathlib import Path

  from omnidriver.opencarp.catalog_generation import build_catalog

  TARGET = Path(__file__).resolve().parents[1] / "packages/omnidriver-opencarp/src/omnidriver/opencarp/opencarp_parameters.json"
  TARGET.write_text(json.dumps(build_catalog(), indent=1, sort_keys=True) + "\n")
  print(f"wrote {TARGET}")
  ```

- [ ] **Step 5: Generate, inspect, run**

  ```bash
  DYLD_LIBRARY_PATH=/opt/homebrew/lib /tmp/odconf/bin/python scripts/generate-opencarp-catalog.py
  grep -c '"name"' packages/omnidriver-opencarp/src/omnidriver/opencarp/opencarp_parameters.json
  grep -i "gitlab\|token" packages/omnidriver-opencarp/src/omnidriver/opencarp/opencarp_parameters.json || echo "no secrets"
  /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_catalog.py -v
  DYLD_LIBRARY_PATH=/opt/homebrew/lib /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_catalog_native.py -v -m native
  ```
  Expected: `266`; `no secrets`; all pass.
  
  Each parameter's detail takes one `+Help` call: measured at about 35 s for all 266 (2026-09-25 dry run). The drift test is `native`, never in the fast tier. Record the time and the counts in the log (next step).
  
  If `test_known_parameters_B2_B5` fails on a detail (for example, the menu order), the binary is right. Correct the test and the log, not the parser.

- [ ] **Step 6: Log it and commit**

  Add a `B7` row to `docs/solver-learning/opencarp.md`: the generation command, the parameter count, the time taken, and the type histogram (53 Float, 52 Int, 40 Short, 35 Double, 30 String, 18 RFile, 14 WFile, 7 Flag, 1 Long, and 16 whole-array forms).
  ```bash
  git add packages/omnidriver-opencarp scripts/generate-opencarp-catalog.py packages/omnidriver/src packages/omnidriver/tests docs/solver-learning/opencarp.md
  git commit -m "feat(opencarp): the parameter catalog, generated from +Help and drift-gated; core gains a string value kind (K6)"
  ```

---

### Task 10: The record-key validator and the index-bound check

**Files:**
- Create: `src/omnidriver/opencarp/validation.py`, `tests/test_validation.py`

**Interfaces:**
- Produces:
  - `record_key_validator(document: str, key_path: tuple[str, ...], value) -> tuple[str, bool]`, which raises `TutorialRecordError` naming the key;
  - `check_indices(text: str) -> None`, which raises `ParFormatError` naming the key (F2).
- Consumes: `load_catalog`, `template_name`, `validate_value_shape`, and `parse_par`/`unquote`.

- [ ] **Step 1: Write the failing tests**

  ```python
  """Validation against the generated catalog (F1, F2, B4, G1)."""
  from __future__ import annotations

  import pytest

  from omnidriver.core.tutorial_records import TutorialRecordError
  from omnidriver.opencarp.par_format import ParFormatError
  from omnidriver.opencarp.validation import check_indices, record_key_validator


  def test_known_keys_get_their_kind():
      assert record_key_validator("nversion.par", ("gregion[0]", "g_il"), 0.2) == ("scalar", True)
      assert record_key_validator("nversion.par", ("tend",), 20.0) == ("scalar", True)
      assert record_key_validator("nversion.par", ("imp_region[0]", "im"), "tenTusscherPanfilov") == ("string", True)
      assert record_key_validator("nversion.par", ("compute_APD",), True) == ("boolean", True)


  @pytest.mark.parametrize(("document", "key_path", "value", "named"), [
      ("nversion.par", ("gregion[0]", "g_ill"), 0.2, "gregion[0].g_ill"),        # misspelled
      ("nversion.par", ("compute_APD",), "no", "compute_APD"),                    # F1: not a bool
      ("nversion.par", ("bidomain",), 5, "bidomain"),                             # outside its menu
      ("nversion.par", ("num_stim",), -1, "num_stim"),                            # below its literal min
      ("mesh.pts", ("tend",), 1.0, "mesh.pts"),                                   # not a .par document
  ])
  def test_refusals_name_the_key(document, key_path, value, named):
      with pytest.raises(TutorialRecordError, match=named.replace("[", r"\[").replace("]", r"\]")):
          record_key_validator(document, key_path, value)


  def test_whole_array_shorthand_asks_for_elements():
      # +Help lists '-phys_region[Int].ID' as '{ phys_region[PrMelem1].num_IDs x Int }' (B1)
      with pytest.raises(TutorialRecordError, match="element"):
          record_key_validator("x.par", ("phys_region[0]", "ID"), [1, 2, 3])


  def test_index_beyond_count_is_refused_F2():
      with pytest.raises(ParFormatError, match=r"stim\[1\].pulse.strength"):
          check_indices("num_stim = 1\nstim[0].pulse.strength = 250\nstim[1].pulse.strength = 999\n")


  def test_count_default_applies_when_absent_F7():
      check_indices("stim[1].pulse.strength = 1\n")          # num_stim defaults to 2
      with pytest.raises(ParFormatError, match="num_stim"):
          check_indices("stim[2].pulse.strength = 1\n")
  ```
  Confirm the shorthand is in the committed catalog: `grep -c '"name": "phys_region\[Int\].ID"' packages/omnidriver-opencarp/src/omnidriver/opencarp/opencarp_parameters.json` should print `1`.

- [ ] **Step 2: Run them to verify they fail.** `/tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_validation.py -v`. Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `validation.py`**

  ```python
  """Record-key validation against the generated catalog.

  Refusals name the key and cite the evidence (docs/solver-learning/opencarp.md).
  Bounds are checked only when +Help gives a literal number; expressions such
  as ``dt/1000.`` (G1) are left to openCARP itself."""
  from __future__ import annotations

  import re
  from typing import Any

  from omnidriver.core.contracts.dictionary import validate_value_shape
  from omnidriver.core.tutorial_records import TutorialRecordError

  from .catalog import load_catalog, template_name
  from .par_format import ParFormatError, parse_par, unquote

  _LITERAL_NUMBER = re.compile(r"^-?\d+(\.\d*)?([eE][+-]?\d+)?$")
  _TOP_INDEX = re.compile(r"^(?P<array>[A-Za-z_]\w*)\[(?P<index>\d+)\]")


  def record_key_validator(document: str, key_path: tuple[str, ...], value: Any) -> tuple[str, bool]:
      key = ".".join(key_path)
      if not document.endswith(".par"):
          raise TutorialRecordError(f"{document}:{key}: openCARP study keys address a .par document")
      catalog = load_catalog()
      spec = catalog.parameters.get(template_name(key))
      if spec is None:
          raise TutorialRecordError(f"{document}:{key} is not an openCARP {catalog.identity['tag']} parameter")
      if spec.value_kind is None:
          raise TutorialRecordError(
              f"{document}:{key} is openCARP's whole-array form ({spec.opencarp_type}); set each element, e.g. {key}[0]"
          )
      problems = validate_value_shape(spec.value_kind, value)
      if problems:
          hint = " (openCARP reads 'no' and 'off' as on: F1)" if spec.value_kind == "boolean" else ""
          raise TutorialRecordError(f"{document}:{key}: {'; '.join(problems)}{hint}")
      if spec.menu:
          spelled = str(int(value)) if isinstance(value, bool) else str(value)
          if spelled not in spec.menu:
              raise TutorialRecordError(f"{document}:{key} = {value!r} is not one of {list(spec.menu)}")
      for bound, label, outside in ((spec.minimum, "minimum", lambda v, b: v < b), (spec.maximum, "maximum", lambda v, b: v > b)):
          if bound is not None and _LITERAL_NUMBER.match(bound) and spec.value_kind in ("integer", "scalar"):
              if outside(float(value), float(bound)):
                  raise TutorialRecordError(f"{document}:{key} = {value!r} is beyond its {label} {bound}")
      return spec.value_kind, True


  def check_indices(text: str) -> None:
      """Refuse an indexed key at or beyond its count (F2; openCARP exits 5 at startup).

      A count absent from the text takes its catalog default (F7:
      ``num_stim`` defaults to 2). Only top-level arrays are checked;
      nested counts (``phys_region[0].num_IDs``) are left to openCARP."""
      catalog = load_catalog()
      count_key_for = {array: spec.name for spec in catalog.parameters.values() for array in spec.allocates}
      values = {a.key: a.value for a in parse_par(text)}
      for key in values:
          match = _TOP_INDEX.match(key)
          if match is None or match["array"] not in count_key_for:
              continue
          count_key = count_key_for[match["array"]]
          raw = values.get(count_key)
          count_text = unquote(raw) if raw is not None else catalog.parameters[count_key].default
          if count_text is None or not count_text.lstrip("-").isdigit():
              continue
          if int(match["index"]) >= int(count_text):
              source = "" if raw is not None else " (its default; F7)"
              raise ParFormatError(f"{key}: index {match['index']} is outside {count_key} = {count_text}{source} (F2)")
  ```

- [ ] **Step 4: Run the tests to verify they pass.** `/tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_validation.py -v`. Expected: all pass.

- [ ] **Step 5: Commit**

  ```bash
  git add packages/omnidriver-opencarp && git commit -m "feat(opencarp): record-key validation and the index-bound check (F1, F2, F7)"
  ```

---

### Task 10a: C10, an agent finds any record's axes, keys and guidance the same way

The owner's gaps 1 and 3 (2026-09-25). Without this, `describe` shows cardiacFOAM's keys (through `dict_entries`) and shows nothing for openCARP, so an agent would have to know which solver it faces. C10 makes discovery part of the contract.

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/runtime/record_surface.py`
- Modify: `core/plugin_capabilities.py` (new `RecordSurfaceCapability`, `_RecordSurfaceAdapter`, the `record_surface` field and its construction)
- Modify: `core/plugin_interface.py` (two optional hooks), `core/provider_stack.py` (`_SHAPE`)
- Modify: `core/introspection.py` (`_describe_tutorial_record` adds `record_surface`)
- Modify: `e2e_record_plugin.py`, `checks.py`, `test_conformance_toy.py`
- Modify: `ARCHITECTURE.md` (regenerated seam table)

**Interfaces:**
- Produces:
  - plugin hook `get_record_key_catalog(case_root: Path) -> tuple[Mapping[str, Any], ...]`: one mapping per addressable key, with required fields `document`, `key`, `value_kind` and optional `default`, `description`, `minimum`, `maximum`, `menu`. An indexed key may be listed in template form, with `[Int]` for any index.
  - plugin hook `get_agent_guidance() -> tuple[Mapping[str, str], ...]`, each with `title` and `text`.
  - both composed as `"sequence"`.
  - `record_surface(record, *, native_case_root, driver_context) -> dict`, with keys `axes`, `keys`, `guidance`, `case_documentation`.
  - `describe`'s record payload gains `"record_surface"`.
  - `check_discoverable`, registered as `"C10"`.
- Consumes: `ctx.capabilities.axes.catalog()` and `ctx.capabilities.case_files.all_rules()`, which returns `CaseFileRule(path, kind, role, required)`. The role `case.documentation` already exists; cardiacFOAM's profile gives it to `README.md`.

- [ ] **Step 1: Write the failing test.** Add `"C10"` to the toy parametrize list. Append:
  ```python
  def test_c10_surface_lists_the_toy_axis_key_and_guidance(tmp_path):
      from omnidriver.core.introspection import describe_entry
      from omnidriver.core.plugin_interface import load_plugin_context

      target = toy_conformance_target(tmp_path)
      payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)},
                               driver_context=load_plugin_context(target.plugin))
      surface = payload["record_surface"]
      assert surface["axes"] == [{"name": "number_cells", "value_kind": "integer"}]
      assert {"document": "constant/mesh.json", "key": "cells", "value_kind": "integer"} in [
          {k: e[k] for k in ("document", "key", "value_kind")} for e in surface["keys"]]
      assert surface["guidance"] and surface["guidance"][0]["title"]
  ```

- [ ] **Step 2: Run it to verify it fails.** Expected: `KeyError: 'record_surface'`.

- [ ] **Step 3: The capability**

  In `plugin_capabilities.py`, next to `RuntimeEvidenceCapability`:
  ```python
  class RecordSurfaceCapability(Protocol):
      """What an agent may address in a record, and what it should read first.

      Owner decision 2026-09-25 (spec 2026-09-25 §4, C10): discovering a
      record's keys and guidance must not depend on knowing which solver is
      underneath. ``key_catalog`` lists the keys a study may name for a case;
      ``guidance`` is solver-level advice for agents. Both degrade to empty,
      which C10 then reports as a failure for a real target.

      :adapts: get_agent_guidance, get_record_key_catalog
      :consumed-by: omnidriver/core/runtime/record_surface.py
      :fallback: none
      :status: optional-neutral
      """

      def key_catalog(self, case_root: Path) -> tuple[Mapping[str, Any], ...]: ...
      def guidance(self) -> tuple[Mapping[str, str], ...]: ...
  ```
  and:
  ```python
  @dataclass(frozen=True)
  class _RecordSurfaceAdapter:
      plugin: "SolverPlugin"

      def key_catalog(self, case_root: Path) -> tuple[Mapping[str, Any], ...]:
          hook = getattr(self.plugin, "get_record_key_catalog", None)
          return tuple(hook(case_root)) if callable(hook) else ()

      def guidance(self) -> tuple[Mapping[str, str], ...]:
          hook = getattr(self.plugin, "get_agent_guidance", None)
          return tuple(hook()) if callable(hook) else ()
  ```
  Then add the field and its construction, next to `runtime_evidence`:
  - in the capabilities dataclass: `record_surface: RecordSurfaceCapability`;
  - where it is constructed: `record_surface=_RecordSurfaceAdapter(plugin),`.
  
  In `plugin_interface.py`'s optional hooks:
  ```python
      # -- Record surface (C10) ---------------------------------------------------
      def get_record_key_catalog(self, case_root: "Path") -> tuple[Mapping[str, Any], ...]:
          """Every key a study may name for this case: document, key, value_kind, and optionally
          default/description/minimum/maximum/menu. Indexed keys may use ``[Int]`` for any index."""
          ...

      def get_agent_guidance(self) -> tuple[Mapping[str, str], ...]:
          """Solver-level advice an agent should read before writing a study (title, text)."""
          ...
  ```
  In `provider_stack._SHAPE`, add `"get_record_key_catalog": "sequence", "get_agent_guidance": "sequence",`.
  
  Confirm how `"sequence"` combines hooks that take an argument: `grep -n '"sequence"' packages/omnidriver/src/omnidriver/core/provider_stack.py`. `get_environment_diagnostics` is sequence-shaped and takes arguments, so it works as the model.

- [ ] **Step 4: The surface, and `describe`**

  `core/runtime/record_surface.py`:
  ```python
  """What describe tells an agent about a tutorial record, the same for every solver (C10)."""
  from __future__ import annotations

  from pathlib import Path
  from typing import Any

  DOCUMENTATION_ROLE = "case.documentation"


  def record_surface(record, *, native_case_root: Path, driver_context) -> dict[str, Any]:
      axis_catalog = driver_context.capabilities.axes.catalog() or {}
      axes = [
          {"name": name, "value_kind": axis_catalog[name].value_kind}
          for name in sorted(record.allowed_axes) if name in axis_catalog
      ]
      surface = driver_context.capabilities.record_surface
      documentation = []
      for rule in driver_context.capabilities.case_files.all_rules():
          path = Path(native_case_root) / rule.path
          if rule.role == DOCUMENTATION_ROLE and path.is_file():
              documentation.append({"path": rule.path, "text": path.read_text(errors="replace")})
      return {
          "axes": axes,
          "keys": [dict(entry) for entry in surface.key_catalog(Path(native_case_root))],
          "guidance": [dict(item) for item in surface.guidance()],
          "case_documentation": documentation,
      }
  ```
  In `introspection._describe_tutorial_record`, where the payload gets `record_preview`, add:
  ```python
      payload["record_surface"] = record_surface(
          record, native_case_root=Path(cases_root) / record.native_case_relpath, driver_context=driver_context,
      )
  ```
  Use the function's own local names for the record and `cases_root`. It already resolves both to build the preview.
  
  With this, the native README becomes agent-readable: the audit's "READMEs are human-only" finding. cardiacFOAM's `README.md` already has the `case.documentation` role.

- [ ] **Step 5: The toy declares its surface**

  In `E2ERecordPlugin`:
  ```python
      def get_record_key_catalog(self, case_root):
          del case_root
          return ({"document": "constant/mesh.json", "key": "cells", "value_kind": "integer",
                   "description": "the toy's cell count"},)

      def get_agent_guidance(self):
          return ({"title": "toy record", "text": "toyTutorial writes solved.marker; number_cells patches constant/mesh.json:cells."},)
  ```

- [ ] **Step 6: Write C10**

  ```python
  import re as _re

  _ANY_INDEX = _re.compile(r"\[\d+\]")


  def check_discoverable(target: ConformanceTarget) -> CheckVerdict:
      """C10: describe tells an agent, the same way for every solver, which axes
      and keys the record takes, and what to read first."""
      ctx = _context(target)
      record = _record(ctx, target.record)
      with _scratch_environment(target):
          payload = describe_entry(target.record, overrides={"cases_root": str(target.cases_root)}, driver_context=ctx)
      surface = payload.get("record_surface")
      if surface is None:
          return _verdict("C10", False, "describe has no record_surface")
      problems = []
      axis_names = {a["name"] for a in surface["axes"]}
      if axis_names != set(record.allowed_axes):
          problems.append(f"axes listed {sorted(axis_names)}, record allows {sorted(record.allowed_axes)}")
      if any(not a.get("value_kind") for a in surface["axes"]):
          problems.append("an axis is listed without its value kind")
      if not surface["keys"] or any(not e.get("value_kind") for e in surface["keys"]):
          problems.append("no key catalogue, or an entry without a value kind")
      document, key_path = _split_study_key(target.patch[0])
      key = ".".join(key_path)
      listed = {(e["document"], e["key"]) for e in surface["keys"]}
      if (document, key) not in listed and (document, _ANY_INDEX.sub("[Int]", key)) not in listed:
          problems.append(f"the target's own patch key {document}:{key} is not in the catalogue")
      if not surface["guidance"]:
          problems.append("no agent guidance")
      return _verdict("C10", not problems, "; ".join(problems) or
                      f"{len(surface['axes'])} axes, {len(surface['keys'])} keys, {len(surface['guidance'])} guidance item(s)")
  ```
  Register `"C10": check_discoverable,`.

- [ ] **Step 7: Run every core shape; regenerate the seam table**

  ```bash
  /tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_conformance_toy.py -v
  /tmp/odconfcore/bin/python -m pytest packages/omnidriver/tests -q
  /tmp/odconf/bin/python scripts/export-capability-seams.py && /tmp/odconf/bin/python scripts/export-capability-seams.py --check
  ```
  Expected: C1–C10 pass for the toy; 0 failed.

- [ ] **Step 8: Commit**

  ```bash
  git add -A packages/omnidriver ARCHITECTURE.md
  git commit -m "feat(core): the record surface -- describe lists any record's axes, keys and guidance; conformance C10"
  ```

---

### Task 11: The plugin and the `niedererNVersion` record, passing C1–C10 against the real binary

**Files:**
- Create: `src/omnidriver/opencarp/opencarp.yaml`, `environment.py`, `plugin.py`, `records/__init__.py`, `records/niederer_n_version.py`
- Create: `tests/test_plugin_contract.py`, `tests/test_conformance_native.py`
- Modify: `tests/opencarp_native.py` (target builder)

**Interfaces:**
- Produces:
  - `OpenCARPPlugin` (entry point `opencarp`, id `org.omnidriver.opencarp`);
  - `RECORD`, `DX_AXIS`, `TUTORIAL_RECORDS`, `AXIS_CATALOG`;
  - `opencarp_environment_diagnostics(workflow_dag, env)`;
  - `REDACTION_PATTERNS`;
  - in tests, `niederer_conformance_target(tmp_path) -> ConformanceTarget`.
- Consumes: everything from Tasks 1–10; `AxisContract`, `AxisResult`, `TutorialRecord` and `WorkflowStep(... produces, consumes)`; `RenderedFile`, `ResolvedMutation` and `_digest_bytes` (core `case_write`); `StrictDiagnostic`.

- [ ] **Step 1: Write the failing tests**

  `tests/test_plugin_contract.py` (every shape, no binary):
  ```python
  from __future__ import annotations

  from omnidriver.core.plugin_discovery import load_discovered_plugin


  def test_opencarp_stack_is_one_provider_C1():
      ctx = load_discovered_plugin("opencarp")
      assert [p.plugin_id for p in ctx.providers] == ["org.omnidriver.opencarp"]


  def test_record_is_registered():
      ctx = load_discovered_plugin("opencarp")
      assert "niedererNVersion" in ctx.capabilities.tutorial_records.catalog()
  ```

  Append to `tests/opencarp_native.py`:
  ```python
  from omnidriver.conformance import ConformanceTarget


  def niederer_conformance_target(tmp_path: Path) -> ConformanceTarget:
      """Coarse and short, so the native tier stays seconds long (G4, G7)."""
      require_opencarp_binary()
      return ConformanceTarget(
          plugin="opencarp",
          record="niedererNVersion",
          cases_root=opencarp_tutorials_root(),
          scratch_root=tmp_path / "scratch",
          base_study={"dx": 1000.0, "nversion.par:tend": 10.0, "nversion.par:dt": 50.0},
          patch=("nversion.par:gregion[0].g_il", 0.2),
          untouched=("nversion.par", ("gregion[0]", "g_it")),
          sweep_name="dx",
          sweep_values=(1000.0, 500.0),
          unknown_name="nversion.par:gregion[0].g_ill",
          solver_command="openCARP",
          environment={},
      )
  ```

  `tests/test_conformance_native.py`:
  ```python
  """openCARP passes the conformance suite against the real binary and openCARP's own tutorial."""
  from __future__ import annotations

  import pytest

  from omnidriver.conformance import CHECKS, run_check
  from opencarp_native import niederer_conformance_target

  pytestmark = pytest.mark.native


  @pytest.mark.parametrize("check_id", sorted(CHECKS))
  def test_niederer_passes(check_id, tmp_path):
      verdict = run_check(check_id, niederer_conformance_target(tmp_path))
      assert verdict.passed, verdict.detail
  ```

- [ ] **Step 2: Run them to verify they fail.** `/tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests/test_plugin_contract.py -v`. Expected: `LookupError`/`ModuleNotFoundError` for `omnidriver.opencarp.plugin`.

- [ ] **Step 3: Profile, environment and record**

  `src/omnidriver/opencarp/opencarp.yaml`:
  ```yaml
  # openCARP is its own environment and solver: no requires (spec §7; C1).
  schema_version: 1
  plugin:
    id: org.omnidriver.opencarp
    api_version: "2"
  provides:
    - config_value
    - case_value_comparison
    - environment_preflight
    - command_authorization
    - case_writer
  case_profile:
    dictionaries: []
  ```
  Validate the seam names before continuing:
  ```bash
  /tmp/odconf/bin/python -c "from omnidriver.core.plugin_discovery import load_discovered_plugin as l; l('opencarp')"
  ```
  This runs after Step 4 exists. If it raises naming an unknown or incomplete seam, correct `provides:` to the name the error prints (or add the seam's missing member). Never drop a seam the plugin implements.

  `src/omnidriver/opencarp/environment.py`:
  ```python
  """Preflight and log redaction (evidence A4-A8, G3).

  openCARP's whole environment is its binaries plus one library path, supplied
  ambiently (A6): nothing here sources a shell profile or searches for one."""
  from __future__ import annotations

  import shutil
  import subprocess
  from typing import Any, Mapping

  from omnidriver.core.planning_types import StrictDiagnostic

  SOLVER_COMMANDS = frozenset({"openCARP"})
  AUXILIARY_COMMANDS = frozenset({"mesher", "igbextract", "igbhead"})
  # G3: every openCARP run prints its build header, whose repository line
  # embeds a CI token. The whole credential part of any such URL is replaced.
  REDACTION_PATTERNS = (r"(https?://)[^/\s@]+(?=@)",)


  def opencarp_environment_diagnostics(workflow_dag: Mapping[str, Any], env: Mapping[str, str]) -> tuple[StrictDiagnostic, ...]:
      path = env.get("PATH", "")
      commands = sorted({step.get("command") for step in (workflow_dag or {}).get("steps", ()) if step.get("command")})
      diagnostics = [
          StrictDiagnostic(level="error", code="opencarp_command_not_found",
                           message=f"{command!r} is not on PATH={path!r}")
          for command in commands if shutil.which(command, path=path) is None
      ]
      solver = shutil.which("openCARP", path=path)
      if solver is not None and "openCARP" in commands:
          proc = subprocess.run([solver, "-buildinfo"], capture_output=True, text=True, env=dict(env), timeout=60)
          if "GIT tag" not in proc.stdout:
              diagnostics.append(StrictDiagnostic(
                  level="error", code="opencarp_binary_unloadable",
                  message="'openCARP' is on PATH but cannot start; on macOS set DYLD_LIBRARY_PATH to the "
                          "directory holding libsundials_cvode (A4-A6): " + proc.stderr.strip()[-300:],
              ))
      return tuple(diagnostics)
  ```

  `src/omnidriver/opencarp/records/niederer_n_version.py`:
  ```python
  """The Niederer 2011 N-version benchmark, as openCARP ships it.

  Native case: 02_EP_tissue/03E_study_resolution (nversion.par, singlecell.sv).
  Its run.py builds the rest in Python. What this record takes from run.py,
  each fact verified with the real binary (docs/solver-learning/opencarp.md):
  - the slab: ``mesh.Block(size=(20, 7, 3), resolution=dx/1000,
    centre=(10, 3.5, 1.5))`` is ``mesher -size 2.0 0.7 0.3 -center 1.0 0.35
    0.15`` in cm, with resolution in µm (F3: extents 0-20000 x 0-7000 x
    0-3000 µm, fibres along x);
  - ``-imp_region[0].im_sv_init singlecell.sv``, case-relative, because
    relative paths resolve against the working directory (F5), and every step
    runs in the staged case root;
  - no physics-region options: outputs are byte-identical without them (F4).
  ``tend``, ``dt`` and ``mass_lumping`` are ordinary .par keys, so a study
  names them as ``nversion.par:<key>`` (G5).
  """
  from __future__ import annotations

  import math
  from pathlib import Path
  from typing import Any

  from omnidriver.core.tutorial_records import (
      AxisContract, AxisResult, TutorialRecord, TutorialRecordError, WorkflowStep,
  )


  def _dx_resolution(value: Any, staged_case_root: Path) -> AxisResult:
      del staged_case_root
      dx = float(value)
      if not math.isfinite(dx) or dx <= 0:
          raise TutorialRecordError(f"dx must be a positive length in µm, got {value!r}")
      text = repr(dx)
      return AxisResult(command_arguments={
          "mesh": ("-resolution[0]", text, "-resolution[1]", text, "-resolution[2]", text),
      })


  DX_AXIS = AxisContract(name="dx", value_kind="scalar", resolve=_dx_resolution)

  RECORD = TutorialRecord(
      name="niedererNVersion",
      native_case_relpath="02_EP_tissue/03E_study_resolution",
      allowed_axes=frozenset({"dx"}),
      workflow_steps=(
          WorkflowStep(
              step_id="mesh",
              command=("mesher", "-size[0]", "2.0", "-size[1]", "0.7", "-size[2]", "0.3",
                       "-center[0]", "1.0", "-center[1]", "0.35", "-center[2]", "0.15", "-mesh", "slab"),
              produces=("slab.pts", "slab.elem", "slab.lon"),
          ),
          WorkflowStep(
              step_id="solve",
              command=("openCARP", "+F", "nversion.par", "-meshname", "slab", "-simID", "out",
                       "-imp_region[0].im_sv_init", "singlecell.sv"),
              consumes=("nversion.par", "singlecell.sv"),
              produces=("out/vm.igb", "out/init_acts_vm_act-thresh.dat"),   # F6
          ),
      ),
  )
  ```
  `src/omnidriver/opencarp/guidance.md`, the evidence log distilled for an agent. Every line cites its evidence id:
  ```markdown
  # openCARP through omniD

  Study keys are `<file>.par:<parameter>`, e.g. `nversion.par:gregion[0].g_il`.
  `describe` lists every parameter with its type, default and bounds.

  - Flags: write `true`/`false` in a study; omniD writes `1`/`0`. openCARP reads
    `no`, `off`, `yes`, `2` all as ON (F1).
  - Counts size arrays: `stim[1].*` needs `num_stim >= 2`, or openCARP exits (F2).
    `num_stim` defaults to 2, so a case that omits it gets two stimuli (F7).
  - Units: `dt` is in microseconds, `tend` in milliseconds (G2). `spacedt` must
    be <= `tend` (G1). The mesh axis `dx` is in micrometres (F3).
  - A key assigned twice in a .par takes its last value (F8); omniD refuses to
    patch such a key.
  - Relative paths resolve against the case directory, which is every step's
    working directory (F5).
  - Defaults that make a run slow: mesher resolution 100 µm, tend 100 ms, dt 5 µs
    (G7). Pin `dx`, `nversion.par:tend` and `nversion.par:dt` for quick studies.
  - Outputs: `out/vm.igb` holds every time step; `out/init_acts_vm_act-thresh.dat`
    holds one activation time per mesh point in point order, -1 if never
    activated (F6).
  ```
  Add `"guidance.md"` to `[tool.setuptools.package-data]` in `packages/omnidriver-opencarp/pyproject.toml`, and `record_surface` to `opencarp.yaml`'s `provides:`.

  `src/omnidriver/opencarp/records/__init__.py`:
  ```python
  """openCARP tutorial records. Scanned by scripts/check-case-writes.py: nothing here writes a case."""
  from .niederer_n_version import DX_AXIS, RECORD

  TUTORIAL_RECORDS = {RECORD.name: RECORD}
  AXIS_CATALOG = {DX_AXIS.name: DX_AXIS}
  ```

- [ ] **Step 4: The plugin**

  `src/omnidriver/opencarp/plugin.py`:
  ```python
  """OpenCARPPlugin: openCARP as one self-contained provider (spec §7)."""
  from __future__ import annotations

  import os
  from importlib import resources
  from pathlib import Path

  from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
  from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
  from omnidriver.core.plugin_profile import load_plugin_profile

  from .catalog import load_catalog, template_name
  from .environment import AUXILIARY_COMMANDS, REDACTION_PATTERNS, SOLVER_COMMANDS, opencarp_environment_diagnostics
  from .par_format import ParFormatError, format_value, patch_par, read_raw, unquote, values_agree
  from .records import AXIS_CATALOG, TUTORIAL_RECORDS
  from .validation import check_indices, record_key_validator

  _FORMAT = "opencarp_par"


  class OpenCARPPlugin:
      plugin_name = "openCARP"
      plugin_id = "org.omnidriver.opencarp"
      plugin_version = "0.1.0"
      plugin_api_version = "2"

      # -- required contract; the dictionary-shaped members are empty (spec K5 deferred)
      def get_profile(self):
          with resources.as_file(resources.files(__package__).joinpath("opencarp.yaml")) as path:
              return load_plugin_profile(path)

      def get_dict_entries(self):
          return ()

      def get_dictionary_catalog(self):
          return DictionaryCatalog({})

      def get_dict_groups(self):
          return {}

      def get_capabilities(self):
          return {}

      def get_tutorial_catalog(self):
          return {"registered_tutorials": (), "spec_factories": {}}

      def get_tutorial_displays(self):
          return ()

      def validate_configuration(self, spec):
          return ()

      def validate_run_semantics(self, context):
          return ()

      def predict_data_artifacts(self, case_root, spec):
          return ()          # records declare their artifacts through step `produces` (K4)

      # -- records
      def get_tutorial_records(self):
          return dict(TUTORIAL_RECORDS)

      def get_axis_catalog(self):
          return dict(AXIS_CATALOG)

      def get_record_key_validator(self):
          return record_key_validator

      def get_case_value_comparator(self):
          return values_agree

      def get_config_value_reader(self):
          def _read(document_path: Path, key_path: tuple):
              if not Path(document_path).is_file():
                  return None
              key = ".".join(key_path)
              raw = read_raw(Path(document_path).read_text(), key)
              if raw is None:
                  return None
              spec = load_catalog().parameters.get(template_name(key))
              if spec is not None and spec.value_kind == "boolean" and unquote(raw) not in ("0", "1"):
                  raise ParFormatError(
                      f"{document_path}: {key} = {raw!r}; openCARP reads every Flag spelling except 0/false "
                      "as on (F1). The native file must say 0 or 1."
                  )
              return unquote(raw)

          return _read

      # -- case writer
      def get_supported_mutation_modes(self):
          return frozenset({"clone_and_patch"})

      def get_rendered_formats(self):
          return frozenset({_FORMAT})

      def resolve_case_mutation(self, request, *, driver_context):
          targets = tuple(
              {"qualified_id": p.qualified_id, "document": p.document,
               "key": ".".join(p.expanded_key_path()), "value": p.value,
               "value_kind": p.value_kind, "format": _FORMAT}
              for p in request.parameters
          )
          return ResolvedMutation(
              request=request, targets=targets, preconditions=(),
              expected_effects=tuple(f"set {t['key']} in {t['document']}" for t in targets),
              semantic_owner_id=self.plugin_id,
          )

      def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
          by_document: dict[str, dict[str, str]] = {}
          for target in resolved.targets:
              by_document.setdefault(target["document"], {})[target["key"]] = format_value(target["value"], target["value_kind"])
          rendered = []
          for document, values in by_document.items():
              path = Path(snapshot_root) / document      # seeded from the case by core (P2)
              exists_before = path.is_file()
              before = path.read_bytes() if exists_before else b""
              text = patch_par(before.decode(), values)
              check_indices(text)                        # F2, refused by name before any run
              rendered.append(RenderedFile(
                  path=document, content=text.encode(), mode=None, exists_before=exists_before,
                  before_digest=_digest_bytes(before) if exists_before else None,
                  renderer_id=self.plugin_id, format=_FORMAT,
              ))
          return tuple(rendered)

      # -- commands and environment
      def get_solver_commands(self):
          return SOLVER_COMMANDS

      def get_auxiliary_commands(self):
          return AUXILIARY_COMMANDS

      def get_environment_commands(self):
          return frozenset()

      def is_installed_environment_command(self, command):
          return False

      def get_utility_manifests(self):
          return {}

      def get_utility_roots(self):
          return ()

      def get_environment_diagnostics(self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None):
          del explicit_bashrc, driver_context
          return opencarp_environment_diagnostics(workflow_dag, env if env is not None else os.environ)

      def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None):
          del explicit_bashrc, driver_context
          return dict(os.environ)

      def get_configured_environment(self, env, driver_context):
          del driver_context
          return dict(env)

      def get_log_redaction_patterns(self):
          return REDACTION_PATTERNS     # consumed once Task 12 lands; harmless before

      # -- record surface (C10, Task 10a)
      def get_record_key_catalog(self, case_root):
          entries = []
          for par in sorted(Path(case_root).glob("*.par")):
              for spec in load_catalog().parameters.values():
                  if spec.value_kind is None:
                      continue
                  entries.append({
                      "document": par.name, "key": spec.name, "value_kind": spec.value_kind,
                      "default": spec.default, "description": spec.description,
                      "minimum": spec.minimum, "maximum": spec.maximum, "menu": list(spec.menu),
                  })
          return tuple(entries)

      def get_agent_guidance(self):
          text = resources.files(__package__).joinpath("guidance.md").read_text()
          return ({"title": "openCARP: what the binary does that a reader would not guess", "text": text},)
  ```
  Check the profile loads from the package: `/tmp/odconf/bin/python -c "from omnidriver.opencarp.plugin import OpenCARPPlugin as P; print(P().get_profile().plugin_id)"`, which should print `org.omnidriver.opencarp`.

- [ ] **Step 5: Run every shape and the native suite**

  ```bash
  VIRTUAL_ENV=/tmp/odconf uv pip install -q -e packages/omnidriver-opencarp
  /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests -q -m "not native"
  export OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib
  /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests -v -m native
  python3 scripts/check-import-boundaries.py && python3 scripts/check-case-writes.py && python3 scripts/check-core-shape.py && /tmp/odconf/bin/python scripts/export-capability-seams.py --check
  ```
  Expected: all ten checks pass for `niedererNVersion` (C10 included), and every gate exits 0.

  If C5 reports that the staged case is not runnable without a workflow, add the hook `E2ERecordPlugin` uses:
  ```python
      def is_case_runnable_without_workflow(self, case_root):
          return (Path(case_root) / "nversion.par").is_file()
  ```
  Add it only if C5 asks for it.

  **Every C-check failure here is evidence, not an inconvenience.**
  1. Read its detail.
  2. If it's an openCARP behaviour, settle it with a real run and log a new F-row.
  3. If it's a core assumption, fix core with a test (and record a K-change in the spec).
  
  Never loosen a check.

- [ ] **Step 6: Record the result and commit**

  Add to `docs/solver-learning/opencarp.md` an `H` section, "omniD drives openCARP". For each check, give its verdict detail, plus the wall time of the native suite.
  ```bash
  git add packages/omnidriver-opencarp docs/solver-learning/opencarp.md
  git commit -m "feat(opencarp): OpenCARPPlugin and the niedererNVersion record pass conformance C1-C10 against openCARP v18.1"
  ```

---

### Task 12: Solver logs are redacted before they are kept (K9, G3)

**Files:**
- Modify: `core/plugin_capabilities.py` (`RuntimeEvidenceCapability`, `_RuntimeEvidenceAdapter`)
- Modify: `core/plugin_interface.py` (optional hook declaration, beside `get_solve_step_commands`)
- Modify: `core/provider_stack.py` (`_SHAPE`)
- Modify: `core/runtime/workflow_runner.py` (after the step process finishes)
- Modify: `ARCHITECTURE.md` (regenerated table)
- Test: `packages/omnidriver/tests/core/test_log_redaction.py`, `packages/omnidriver-opencarp/tests/test_conformance_native.py`

**Interfaces:**
- Produces:
  - plugin hook `get_log_redaction_patterns() -> tuple[str, ...]`, composed as `"set"`;
  - `runtime_evidence.log_redaction_patterns() -> frozenset[str]`;
  - `redact_step_logs(paths, patterns) -> None`.

- [ ] **Step 1: Write the failing tests**

  `packages/omnidriver/tests/core/test_log_redaction.py`:
  ```python
  from __future__ import annotations

  from omnidriver.core.runtime.workflow_runner import redact_step_logs


  def test_patterns_replace_the_secret_and_nothing_else(tmp_path):
      log = tmp_path / "s.stdout.log"
      log.write_text("*** GIT repo: https://user:SECRET@host/x.git\nTime = 1\n")
      redact_step_logs((log,), (r"(https?://)[^/\s@]+(?=@)",))
      assert log.read_text() == "*** GIT repo: https://[REDACTED]@host/x.git\nTime = 1\n"


  def test_no_patterns_leave_the_file_untouched(tmp_path):
      log = tmp_path / "s.stdout.log"
      log.write_text("x\n")
      before = log.stat().st_mtime_ns
      redact_step_logs((log,), ())
      assert log.stat().st_mtime_ns == before
  ```
  Append to `test_conformance_native.py`:
  ```python
  def test_no_token_survives_in_workflow_logs(tmp_path):
      target = niederer_conformance_target(tmp_path)
      assert run_check("C6", target).passed
      logs = list(target.scratch_root.rglob("workflow_logs/*.log"))
      assert logs, "C6 wrote no step logs"
      assert not [p for p in logs if "gitlab-ci-token" in p.read_text(errors="ignore")]
  ```

- [ ] **Step 2: Run them to verify they fail.** Expected: `ImportError: cannot import name 'redact_step_logs'`; the native test finds the token.

- [ ] **Step 3: Implement**

  In `workflow_runner.py`, at module level:
  ```python
  def redact_step_logs(paths, patterns) -> None:
      """Replace every match of each pattern with its first capture group (if
      it has one) followed by ``[REDACTED]`` (K9). So ``(https?://)[^/\\s@]+(?=@)``
      keeps the scheme and the ``@``, and drops the credential between them."""
      compiled = [re.compile(p) for p in patterns]
      if not compiled:
          return
      for path in paths:
          if not Path(path).is_file():
              continue
          text = Path(path).read_text(errors="replace")
          redacted = text
          for pattern in compiled:
              redacted = pattern.sub(lambda m: ((m.group(1) or "") if m.re.groups else "") + "[REDACTED]", redacted)
          if redacted != text:
              Path(path).write_text(redacted)
  ```
  (Add `import re` if the module lacks it.) Then, straight after the `with stdout_log.open("w") ... as stderr_handle:` block ends and before the `if stop_reason == "timeout":` chain, add:
  ```python
          if driver_context is not None:
              redact_step_logs((stdout_log, stderr_log), driver_context.capabilities.runtime_evidence.log_redaction_patterns())
  ```
  In `plugin_capabilities.py`:
  - add `get_log_redaction_patterns` to the `:adapts:` line of `RuntimeEvidenceCapability`;
  - add the method `def log_redaction_patterns(self) -> frozenset[str]: ...` to the Protocol;
  - add to `_RuntimeEvidenceAdapter`:
    ```python
        def log_redaction_patterns(self) -> frozenset[str]:
            hook = getattr(self.plugin, "get_log_redaction_patterns", None)
            return frozenset(hook()) if callable(hook) else frozenset()
    ```
  In `plugin_interface.py`, beside `get_solve_step_commands`:
  ```python
      def get_log_redaction_patterns(self) -> tuple[str, ...]:
          """Regular expressions whose matches are replaced in kept step logs
          (for example a credential a solver prints in its build header)."""
          ...
  ```
  In `provider_stack.py`, add `"get_log_redaction_patterns": "set",` beside `"get_solve_step_commands": "set",`.
  
  Regenerate the seam table: `/tmp/odconf/bin/python scripts/export-capability-seams.py`, then `--check`.

- [ ] **Step 4: Run the tests to verify they pass.** Run the core test file, the native openCARP suite, core-alone, and `export-capability-seams.py --check`. Expected: 0 failed.

- [ ] **Step 5: Commit**

  ```bash
  git add -u packages ARCHITECTURE.md && git add packages/omnidriver/tests/core/test_log_redaction.py
  git commit -m "feat(core): step logs are redacted by plugin-declared patterns before they are kept (K9)"
  ```

---

### Task 13: CI, the verification guide, and the spec's status

**Files:**
- Modify: `.github/workflows/ci.yml`, `CLAUDE.md`, `docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md`

- [ ] **Step 1: A CI job that installs openCARP's plugin without OpenFOAM**

  In `.github/workflows/ci.yml`, add a job `test-opencarp`, modelled on `test-cardiaccore`:
  - install `packages/omnidriver` and `packages/omnidriver-opencarp` only (**no** `omnidriver-openfoam`: this is C1 as an install fact);
  - run `python -m pytest packages/omnidriver-opencarp/tests -m "not native" -q`.
  
  Add the new package to `test-all-package-wheels`' install line and to the `cache-dependency-path` lists.

- [ ] **Step 2: CLAUDE.md**

  - Add `omnidriver-opencarp` to the package table: may know "openCARP binary, .par, mesher, IGB/LAT outputs", must not know "OpenFOAM, cardiacFoam".
  - Add `-e packages/omnidriver-opencarp` to the all-packages venv line.
  - Add a native row: `OMNIDRIVER_OPENCARP_TUTORIALS=<path> DYLD_LIBRARY_PATH=<lib> python -m pytest packages/omnidriver-opencarp/tests -m native`.
  - Add an invariant row: `| any solver plugin passes C1-C10 | omnidriver.conformance, parametrized per package (toy in core; openCARP native) |`.

- [ ] **Step 3: The spec's status and its dated corrections**

  Append a `## Status` table to the spec, with one row per task and its commit hash. Then add dated corrections (2026-MM-DD):
  - **K3 and K5 not made.** No check forces them (see this plan's opening section).
  - **K7 reduced** to extending the existing lists.
  - **New K8** (sweep reconciliation) and **K9** (log redaction), with their evidence.
  - **C4 checks the `untouched` key**, not every key: sibling enumeration is format-specific, and the P2 class of defect is caught by one sibling.
  - **C8 is defined over `consumes`.**
  - **P1/P2 landed upstream** in `156b80d`/`56d89d7`.

- [ ] **Step 4: Full verification, then commit**

  ```bash
  /tmp/odconf/bin/python -m pytest packages/ -q -m "not slow and not native"
  /tmp/odconfcore/bin/python -m pytest packages/omnidriver/tests -q
  rm -rf /tmp/wheeltest /tmp/wheelenv && /tmp/odconf/bin/python -m build --outdir /tmp/wheeltest packages/omnidriver
  uv venv --python 3.11 /tmp/wheelenv && VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
  /tmp/wheelenv/bin/python scripts/check-wheel-artifact.py && /tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
  OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib /tmp/odconf/bin/python -m pytest packages/omnidriver-opencarp/tests -q -m native
  python3 scripts/check-import-boundaries.py && python3 scripts/check-case-writes.py && python3 scripts/check-core-shape.py && /tmp/odconf/bin/python scripts/export-capability-seams.py --check
  ```
  Expected: 0 failed in every shape; every gate exits 0. The wheel shape matters here: `omnidriver.conformance` ships in the wheel, and C1–C10 over the toy run from it.
  ```bash
  git add .github/workflows/ci.yml CLAUDE.md docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md
  git commit -m "docs,ci: openCARP in CI without OpenFOAM; the conformance invariant; spec status"
  ```

---

### Task 14 (after tutorials-are-pointers step 5 is finished): cardiacFoam as a conformance target

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records/restitution_curves.py` (step `produces`/`consumes`, read from the real `Allrun` and case)
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` (`get_record_key_catalog`, `get_agent_guidance`)
- Create: `packages/omnidriver-cardiacfoam/tests/test_conformance_native.py`

- [ ] **Step 1: Read the real case's inputs and outputs.** From `OMNIDRIVER_NATIVE_TUTORIALS/electrophysiologyProtocols/restitutionCurves_s1s2Protocol` and its `Allrun`, list:
  - what `blockMesh` reads and writes;
  - what `cardiacFoam` reads, and which trace file it writes.
  
  step 4c's real run recorded the trace name pattern `TWorld_epicardialCells_S1_1000_S2_1500.txt`. Write only paths observed in a real run.

- [ ] **Step 2: Write the target and a failing test**, modelled on `niederer_conformance_target`:
  - `plugin="cardiacfoam"`, `record="restitutionCurves"`;
  - `base_study={"blockMeshResolution": [40, 6, 14]}`, the coarse mesh step 4c used;
  - a real `constant/electroProperties` key to patch, and one to leave untouched;
  - sweep over `blockMeshResolution` with two coarse values;
  - `solver_command="cardiacFoam"`.
  
  Run it with `-m native`. Expected: C6 and C8 fail, because no step declares `produces`/`consumes`.

- [ ] **Step 3: Declare the observed paths on the record's steps.** Re-run: C6 and C8 should now pass, and C10 should fail with "no key catalogue".

- [ ] **Step 4: cardiacFOAM's record surface (C10).** *Corrected 2026-09-25 (Wave 2 review, I5): re-shaping `DictEntry` directly cannot pass C10.* `DictEntry` has no document field, its `driver_path` carries `$ELECTRO_MODEL_COEFFS`, and dynamic entries carry named segments such as `regions.<region_name>.baseline`. Four decisions follow, all made here, before this step starts:
  1. **Concretise tokens from the case.** `CardiacFoamPlugin.get_record_key_catalog(case_root)` replaces `$ELECTRO_MODEL_COEFFS` with the case's own `<solver>Coeffs`, reusing `record_key_validation`'s existing substitution. It reads `myocardiumSolver` from `case_root`, and never keeps a second list. The document comes from the entry's catalogue partition.
  2. **Core's key-template grammar gains one named-segment placeholder** (a core change, with its own commit and generality-log row). In a catalogue key, `[Int]` stands for any index and `<name>` for any single dot-free segment. C10 compiles a listed key to a pattern on that basis, replacing its `_ANY_INDEX` normalisation. Document both forms in the `get_record_key_catalog` docstring and the record-surface docs, with tests for each.
  3. **Honest open documents.** A catalogue may list a document-level entry `{"document": "system/controlDict", "key": "<any>", "validated": False}` for a document whose keys are written but have no catalogue (OpenFOAM keys; memory: OpenFOAM keys uncatalogued). C10 accepts an entry without `value_kind` only when `validated` is `False`. A patch key matches such an entry only through its document.
  4. **One canonical catalogue for records.** For a tutorial record, `describe` carries keys only in `record_surface.keys`, and drops `dict_entries` from that record's payload (a core change in `introspection._describe_tutorial_record`, with a generality-log row). Factory and case-folder entries keep `dict_entries` until the factory path is deleted.
  
  `get_agent_guidance()` returns cardiacFOAM's solver-level notes: the rules its validator and catalogues already enforce, stated for a reader, with no new facts. The case README reaches agents through the `case.documentation` role cardiacFOAM's profile already declares.

  Re-run until C1–C10 pass, then commit:
  ```bash
  git commit -m "test(cardiacfoam): restitutionCurves passes conformance C1-C10"
  ```
  Every other record that migrates in step 5 joins this parametrization as it lands. When all of them pass, the old factory path can be deleted.

---

### Task 15 (after tutorials-are-pointers step 5 is finished): every file declared by the layer that reads it (gap 2, K3)

Owner decision 2026-09-25. It waits for step 5 because it edits cardiacFOAM's `plugin.yaml`. Two guards force the change, so it is made the way every K-change is made: the guard fails first.

**Files:**
- Create: `packages/omnidriver/tests/core/test_layer_ownership.py`
- Create: `packages/omnidriver/src/omnidriver/core/runtime_records.py`
- Modify: `core/plugin_capabilities.py` (`_CaseRuntimeConventionsAdapter.conventions` merges core's names)
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_runtime_conventions.py` (drops core's names)
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam-environment.yaml` (gains the OpenFOAM-read files)
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml` (loses them)

**Interfaces:**
- Produces:
  - `CORE_RUNTIME_RECORDS: CaseRuntimeConventions`;
  - `with_core_runtime_records(conventions) -> CaseRuntimeConventions`;
  - the guard tests `test_a_role_namespace_has_one_owner_per_stack` and `test_no_plugin_declares_cores_own_files`.

- [ ] **Step 1: Write the failing guards**

  ```python
  """Every file is declared by the layer that reads it (owner decision 2026-09-25, gap 2)."""
  from __future__ import annotations

  import pytest

  from omnidriver.core.plugin_discovery import load_discovered_plugin
  from omnidriver.core.runtime_records import CORE_RUNTIME_RECORDS

  STACKS = ("cardiacfoam", "cardiaccore", "opencarp")
  GENERIC_NAMESPACES = {"plugin", "case"}


  @pytest.mark.parametrize("stack", STACKS)
  def test_a_role_namespace_has_one_owner_per_stack(stack):
      """The first provider (in requires order) to use a role namespace owns it.

      So a provider that declares ``openfoam.*`` files in a stack that also
      holds the OpenFOAM layer is declaring files that layer reads."""
      ctx = load_discovered_plugin(stack)
      owner: dict[str, str] = {}
      violations = []
      for provider in reversed(ctx.providers):         # most-required first
          for rule in provider.get_profile().case_files:
              namespace = rule.role.split(".", 1)[0]
              if namespace in GENERIC_NAMESPACES:
                  continue
              owner.setdefault(namespace, provider.plugin_id)
              if owner[namespace] != provider.plugin_id:
                  violations.append(f"{provider.plugin_id} declares {rule.path} as {rule.role}; {owner[namespace]} owns {namespace}.*")
      assert not violations, violations


  @pytest.mark.parametrize("stack", STACKS)
  def test_no_plugin_declares_cores_own_files(stack):
      ctx = load_discovered_plugin(stack)
      core_names = set(CORE_RUNTIME_RECORDS.generated_file_names) | set(CORE_RUNTIME_RECORDS.generated_directory_names)
      for provider in ctx.providers:
          hook = getattr(provider, "get_case_runtime_conventions", None)
          if not callable(hook):
              continue
          conventions = hook()
          declared = set(conventions.generated_file_names) | set(conventions.generated_directory_names)
          assert not (declared & core_names), f"{provider.plugin_id} declares core's {sorted(declared & core_names)}"
      merged = ctx.capabilities.case_runtime_conventions.conventions()
      assert core_names <= set(merged.generated_file_names) | set(merged.generated_directory_names)
  ```
  First confirm the order of `ctx.providers`: `grep -n "providers" packages/omnidriver/src/omnidriver/core/provider_stack.py | head`. If the tuple runs most-required-first, iterate it forward instead of `reversed`. The comment must match whichever is true.

- [ ] **Step 2: Run them to verify they fail.**
  - `ImportError` for `runtime_records`, before Step 3.
  - After Step 3, the ownership guard names `org.cardiacfoam` declaring `system/fvSchemes`, `system/fvSolution`, `system/decomposeParDict`, `system/blockMeshDict` and `Allclean` under `openfoam.*`.
  - The core-files guard names `org.omnidriver.openfoam.environment` declaring `workflow_state.json`, `run_document.json`, `sweep_manifest.json` and `workflow_logs`.

- [ ] **Step 3: Core owns its own names (K3)**

  `core/runtime_records.py`:
  ```python
  """The files omniD itself writes into a case, declared once, by core (K3).

  They used to be declared by the OpenFOAM layer's conventions, so a stack
  without that layer did not know them. The adapter that reads a stack's
  CaseRuntimeConventions merges these in, whatever the plugins declare."""
  from __future__ import annotations

  from dataclasses import replace

  from omnidriver.core.plugin_capabilities import CaseRuntimeConventions

  CORE_RUNTIME_RECORDS = CaseRuntimeConventions(
      generated_directory_names=("workflow_logs",),
      generated_file_names=("workflow_state.json", "run_document.json", "sweep_manifest.json"),
      generated_case_markers=("workflow_state.json", "workflow_logs", "run_document.json"),
  )


  def _union(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
      return first + tuple(name for name in second if name not in first)


  def with_core_runtime_records(conventions: CaseRuntimeConventions) -> CaseRuntimeConventions:
      return replace(
          conventions,
          generated_directory_names=_union(conventions.generated_directory_names, CORE_RUNTIME_RECORDS.generated_directory_names),
          generated_file_names=_union(conventions.generated_file_names, CORE_RUNTIME_RECORDS.generated_file_names),
          generated_case_markers=_union(conventions.generated_case_markers, CORE_RUNTIME_RECORDS.generated_case_markers),
      )
  ```
  If importing `CaseRuntimeConventions` from `plugin_capabilities` creates an import cycle, move `CORE_RUNTIME_RECORDS` into `plugin_capabilities.py` beside the dataclass, and keep `runtime_records.py` as the documented re-export.
  
  In `_CaseRuntimeConventionsAdapter.conventions`, wrap every return value in `with_core_runtime_records(...)`, including the empty-conventions fallback.
  
  Before removing anything from OpenFOAM's `openfoam_case_runtime_conventions()`, check whether `driverPostProcessingArchive` is written by core: `grep -rn "driverPostProcessingArchive" packages/omnidriver/src`.
  - If core writes it, add it to `CORE_RUNTIME_RECORDS.generated_directory_prefixes` (extend `_union` to that field).
  - If core doesn't write it, leave it with OpenFOAM.
  
  Then delete `workflow_logs`, `workflow_state.json`, `run_document.json` and `sweep_manifest.json` from OpenFOAM's lists and markers.

- [ ] **Step 4: The OpenFOAM layer declares what OpenFOAM reads**

  Move the five rules (`system/fvSchemes`, `system/fvSolution`, `system/decomposeParDict`, `system/blockMeshDict`, `Allclean`) verbatim from cardiacFOAM's `plugin.yaml` `case_profile.dictionaries` into `openfoam-environment.yaml`'s, keeping their `kind`, `role` and `required`.
  
  Then find every consumer of those roles, and confirm none reads them from the cardiac provider specifically:
  ```bash
  grep -rn "openfoam.discretisation\|openfoam.solver_settings\|openfoam.decomposition\|openfoam.mesh_generation\|openfoam.cleanup" packages/*/src
  ```

- [ ] **Step 5: Run the guards and every shape**

  ```bash
  /tmp/odconf/bin/python -m pytest packages/omnidriver/tests/core/test_layer_ownership.py -v
  /tmp/odconf/bin/python -m pytest packages/ -q -m "not slow and not native"
  OMNIDRIVER_NATIVE_TUTORIALS=/Users/simaocastro/noFrontendCardiacFoam_minor_errors/tutorials /tmp/odconf/bin/python -m pytest packages/ -q -m native
  python3 scripts/check-core-shape.py
  ```
  Expected: 0 failed.
  
  The shape gate may now report a **shrunk** count, if core's own names had been spelled through OpenFOAM terms. If it does, edit the baseline down; that is the debt being paid.

- [ ] **Step 6: Commit**

  ```bash
  git add -A packages scripts/core-shape-baseline.txt
  git commit -m "refactor: every case file is declared by the layer that reads it; core declares its own records (K3)"
  ```

