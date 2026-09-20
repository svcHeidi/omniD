# Phase 2: One Case-Write Channel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two materialization mechanisms and three override shapes into one inspectable, transactional channel, so that every case write is planned before it happens and rolled back if it fails.

**Architecture:** `TutorialSpec.apply_case` and `SweepMaterializerCapability.materialize` are the same operation at different arities. A `CaseWriter` capability replaces both with `plan_case(request) -> CaseWritePlan` (pure) and `write_case(plan) -> CaseWriteRecord` (impure, core-owned, transactional). The plan is a declarative list of operations — `patch` or `synthesize` — each naming its target and its owning provider, so it can be shown to an agent before anything is written.

**Tech Stack:** Python 3.11+, pytest. No new runtime dependency.

**Source spec:** `docs/superpowers/specs/2026-09-20-provider-composition-design.md` §5.

**Prerequisite:** Phase 1 complete. The composition rule decides who owns the writer when two providers could.

## Global Constraints

- Python floor is **3.11**. Keep lazy annotations in `plugin_interface.py`.
- `omnidriver.core` MUST NOT import from any adapter package; waiver list stays empty.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- No production module in core or an adapter may touch `driver_context.providers` directly.
- Do not weaken or skip a guard to make a change pass.
- **The `Files:` block is authoritative for what to commit, not the per-step `git add` list.** Those lists were written before the tasks ran and have been stale three times (Phase 0 Tasks 1, 4 and 6). Commit every file the task actually changed; if that differs from the `Files:` block, say so in the report.
- Do not quote suite totals. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number.
- Record document corrections with a date.
- Do not add a `LICENSE` file or a `license` field.
- Rebuild the wheel after every source change before running the wheel shape.
- **Every write must be rollback-safe.** A task that adds a write path without a before-image is incomplete.

---

## File Structure

**Core — created:**
- `core/case_write.py` — `CaseWriteOperation`, `CaseWritePlan`, `CaseWriteRecord`. Types only; no I/O.
- `core/case_writer.py` — the core-owned `write_case` executor and its transaction wrapper. One responsibility: turn a plan into bytes, atomically.
- `tests/core/test_case_write_plan.py`
- `tests/core/test_case_writer_transaction.py`

**Core — modified:**
- `core/plugin_capabilities.py` — `CaseWriterCapability`; `SweepMaterializerCapability` retired into it.
- `core/contracts/dictionary.py` — `value_kind` vocabulary closed; `dynamic_path` placeholder grammar.
- `core/runtime/models.py` — `TutorialSpec.apply_case` retired in favour of `plan_case`.
- `sweep_materialize.py`, `sweep_routing.py` — route through `CaseWriterCapability`.
- `core/introspection.py` — `describe` emits the plan and the override scopes.
- `core/utility_catalog.py` — gains an in-process operation type.
- `schemas/sweep-spec.json` — created; the sweep spec finally has one.

**Adapters — modified:**
- `omnidriver-cardiacfoam/.../dict_builder.py` — split; synthesis becomes `plan_case`.
- `omnidriver-cardiacfoam/.../sweep.py` — `route`/`materialize` become `plan_case`.
- `omnidriver-cardiaccore/.../workflows/overrides.py` — becomes `plan_case`.
- `omnidriver-cardiaccore/.../operations/vtu_selection.py`, `operations/electrodes.py` — route through the shared writer.

---

## Task 1: The plan types

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/case_write.py`
- Create: `packages/omnidriver/tests/core/test_case_write_plan.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `CaseWriteOperation(kind, target, key, value, provider_id, before)`, `CaseWritePlan(case_root, operations, provider_id)`, `CaseWriteRecord(plan, applied, skipped, rolled_back)`. Every later task uses these names.

- [ ] **Step 1: Write the failing test**

```python
"""A case write is planned before it happens.

Two materialization mechanisms existed and never met: `TutorialSpec.apply_case`
for tutorials and entry sweeps, `SweepMaterializerCapability.materialize` for
cross-product sweeps, which bypassed `TutorialSpec` entirely. They are the same
operation at different arities.
"""

import pytest

from omnidriver.core import case_write


def test_a_plan_is_immutable():
    op = case_write.CaseWriteOperation(
        kind="patch", target="constant/electroProperties",
        key="ionicModel", value="TT06", provider_id="org.cardiacfoam",
    )
    plan = case_write.CaseWritePlan(
        case_root="/tmp/case", operations=(op,), provider_id="org.cardiacfoam",
    )
    with pytest.raises(Exception):
        plan.operations = ()


def test_an_unknown_operation_kind_is_refused():
    with pytest.raises(ValueError, match="rewrite"):
        case_write.CaseWriteOperation(
            kind="rewrite", target="x", key=None, value=None, provider_id="org.a",
        )


def test_a_plan_describes_itself_for_an_agent():
    """`--dry-run` becomes a property of the type, not a threaded flag."""
    op = case_write.CaseWriteOperation(
        kind="synthesize", target="constant/electroProperties",
        key=None, value={"ionicModel": "TT06"}, provider_id="org.cardiacfoam",
    )
    plan = case_write.CaseWritePlan(
        case_root="/tmp/case", operations=(op,), provider_id="org.cardiacfoam",
    )
    payload = plan.to_json()
    assert payload["operations"][0]["kind"] == "synthesize"
    assert payload["operations"][0]["target"] == "constant/electroProperties"
    assert payload["operations"][0]["provider_id"] == "org.cardiacfoam"


def test_targets_must_be_case_relative():
    """A plan must not be able to write outside the case."""
    with pytest.raises(ValueError, match="absolute"):
        case_write.CaseWriteOperation(
            kind="patch", target="/etc/passwd", key="x", value="y",
            provider_id="org.a",
        )
    with pytest.raises(ValueError, match="escape"):
        case_write.CaseWriteOperation(
            kind="patch", target="../outside", key="x", value="y",
            provider_id="org.a",
        )
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_write_plan.py -v
```

Expected: FAIL — no module `case_write`.

- [ ] **Step 3: Implement the types**

```python
"""Declarative description of what a case write will do, before it does it.

Core owns this vocabulary; a provider fills it. Two kinds only:

``patch``      -- set one key in an existing file. Today `mutators.update_foam_entry`.
``synthesize`` -- write a whole file from the catalogue. Today
                  `build_electro_properties` / `regenerate_electro_properties`.

Only ``synthesize`` needs provider vocabulary, which is why only it is
provider-supplied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

OPERATION_KINDS = frozenset({"patch", "synthesize"})


@dataclass(frozen=True)
class CaseWriteOperation:
    kind: str
    target: str
    key: str | None
    value: Any
    provider_id: str
    #: Bytes as they were before this operation, filled by the writer so a
    #: failed plan can be rolled back exactly. None until the writer reads it.
    before: bytes | None = None

    def __post_init__(self) -> None:
        if self.kind not in OPERATION_KINDS:
            raise ValueError(
                f"unknown case-write operation kind {self.kind!r}; "
                f"known kinds are {sorted(OPERATION_KINDS)}"
            )
        path = PurePosixPath(self.target)
        if path.is_absolute():
            raise ValueError(f"case-write target must be case-relative, not absolute: {self.target!r}")
        if ".." in path.parts:
            raise ValueError(f"case-write target must not escape the case: {self.target!r}")
        if self.kind == "patch" and not self.key:
            raise ValueError("a patch operation must name a key")

    def to_json(self) -> dict:
        return {
            "kind": self.kind,
            "target": self.target,
            "key": self.key,
            "provider_id": self.provider_id,
        }


@dataclass(frozen=True)
class CaseWritePlan:
    case_root: Any
    operations: tuple[CaseWriteOperation, ...]
    provider_id: str

    def to_json(self) -> dict:
        return {
            "case_root": str(self.case_root),
            "provider_id": self.provider_id,
            "operations": [op.to_json() for op in self.operations],
        }

    @property
    def targets(self) -> tuple[str, ...]:
        """Every file this plan may touch, for before-image capture."""
        return tuple(dict.fromkeys(op.target for op in self.operations))


@dataclass(frozen=True)
class CaseWriteRecord:
    plan: CaseWritePlan
    applied: tuple[CaseWriteOperation, ...] = ()
    skipped: tuple[CaseWriteOperation, ...] = ()
    rolled_back: bool = False

    def to_json(self) -> dict:
        return {
            "plan": self.plan.to_json(),
            "applied": [op.to_json() for op in self.applied],
            "skipped": [op.to_json() for op in self.skipped],
            "rolled_back": self.rolled_back,
        }
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_write_plan.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/case_write.py \
        packages/omnidriver/tests/core/test_case_write_plan.py
git commit -m "feat(core): a case write is described before it happens"
```

---

## Task 2: The transactional writer

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/case_writer.py`
- Create: `packages/omnidriver/tests/core/test_case_writer_transaction.py`

**Interfaces:**
- Consumes: `case_write.CaseWritePlan` (Task 1); `core/runtime/remediation_transaction.py`'s journal.
- Produces: `case_writer.write_case(plan, *, driver_context) -> CaseWriteRecord`.

- [ ] **Step 1: Write the failing test**

```python
"""Every write is rollback-safe, including the ones that were not.

cardiacCore's override writer had no rollback wrapper and was not wired to the
transaction ledger, because it was reached only through `apply_case` at
materialization time -- before any `step --strict --apply` transaction existed.
"""

import pytest

from omnidriver.core import case_write, case_writer


def test_a_failing_operation_rolls_the_whole_plan_back(tmp_path, neutral_context):
    target = tmp_path / "constant" / "props"
    target.parent.mkdir(parents=True)
    target.write_text("original\n")

    plan = case_write.CaseWritePlan(
        case_root=tmp_path,
        provider_id="org.test",
        operations=(
            case_write.CaseWriteOperation(
                kind="patch", target="constant/props", key="a", value="1",
                provider_id="org.test",
            ),
            case_write.CaseWriteOperation(
                kind="patch", target="constant/missing", key="b", value="2",
                provider_id="org.test",
            ),
        ),
    )
    with pytest.raises(Exception):
        case_writer.write_case(plan, driver_context=neutral_context)
    assert target.read_text() == "original\n", "the first write was not rolled back"


def test_a_successful_plan_records_what_it_applied(tmp_path, neutral_context):
    target = tmp_path / "constant" / "props"
    target.parent.mkdir(parents=True)
    target.write_text("a 0;\n")

    plan = case_write.CaseWritePlan(
        case_root=tmp_path, provider_id="org.test",
        operations=(case_write.CaseWriteOperation(
            kind="patch", target="constant/props", key="a", value="1",
            provider_id="org.test",
        ),),
    )
    record = case_writer.write_case(plan, driver_context=neutral_context)
    assert len(record.applied) == 1
    assert record.rolled_back is False


def test_before_images_are_captured_for_every_target(tmp_path, neutral_context):
    """Capture happens before the first write, not per operation.

    Two operations on one file must not leave the second's before-image
    holding the first's output.
    """
    target = tmp_path / "constant" / "props"
    target.parent.mkdir(parents=True)
    target.write_text("a 0;\nb 0;\n")

    plan = case_write.CaseWritePlan(
        case_root=tmp_path, provider_id="org.test",
        operations=(
            case_write.CaseWriteOperation(
                kind="patch", target="constant/props", key="a", value="1",
                provider_id="org.test",
            ),
            case_write.CaseWriteOperation(
                kind="patch", target="constant/props", key="b", value="bad",
                provider_id="org.test",
            ),
        ),
    )
    with pytest.raises(Exception):
        case_writer.write_case(plan, driver_context=neutral_context)
    assert target.read_text() == "a 0;\nb 0;\n"
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_writer_transaction.py -v
```

Expected: FAIL — no module `case_writer`.

- [ ] **Step 3: Implement**

`write_case` must, in this order: resolve every target under `case_root` and refuse anything escaping it; capture a before-image per **distinct target** once, before any write; apply operations in plan order, dispatching `patch` and `synthesize` through the composed `CaseWriterCapability` (Task 3); restore every captured before-image and re-raise on any failure; return a `CaseWriteRecord`.

Write files atomically — temp file plus `os.replace` — the way `runtime/workflow_runner._atomic_write_json` and `runtime/sweep_manifest.write_manifest` already do. Reuse that helper rather than adding a third.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_writer_transaction.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/case_writer.py \
        packages/omnidriver/tests/core/test_case_writer_transaction.py
git commit -m "feat(core): one transactional writer for every case write"
```

---

## Task 3: `CaseWriterCapability`

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Test: `packages/omnidriver/tests/core/test_capability_seam_documentation.py`

**Interfaces:**
- Consumes: `case_write` types (Task 1).
- Produces: `CaseWriterCapability` with `plan(request) -> CaseWritePlan` and `synthesize(operation, case_root) -> bytes`, adapting `plan_case` and `synthesize_case_file`. `:status: optional-refusing` — a neutral plan would silently produce the wrong case.

- [ ] **Step 1: Write the failing test**

```python
def test_case_writer_is_a_seam_and_refuses_by_name():
    from omnidriver.core import plugin_capabilities

    assert hasattr(plugin_capabilities, "CaseWriterCapability")
    assert "case_writer" in plugin_capabilities.PluginCapabilities.__annotations__

    seam = next(
        s for s in __import__(
            "omnidriver.core.capability_seams", fromlist=["x"]
        ).collect_seams() if s.field == "case_writer"
    )
    assert seam.status == "optional-refusing", (
        "a neutral plan would silently write the wrong case, which is worse "
        "than refusing"
    )
```

- [ ] **Step 2: Run to verify it fails, then implement**

Add the Protocol with its four docstring fields, the adapter, and the `PluginCapabilities` field, following `ConfigValueCapability`'s established shape. The fallback — `legacy_plan_case` — raises naming the hook, exactly as `legacy_materialize_sweep_case` does.

- [ ] **Step 3: Regenerate, run, commit**

```bash
python3 scripts/export-capability-seams.py && python3 scripts/export-capability-seams.py --check
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/tests/core/test_capability_seam_documentation.py ARCHITECTURE.md
git commit -m "feat(core): CaseWriterCapability, refusing rather than neutral"
```

---

## Task 4: Promote the value-kind vocabulary

cardiacCore invented integer/scalar/word/enum/vector3 inside `workflows/overrides._check_value`. `DictEntry.value_kind` already exists.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py`
- Test: `packages/omnidriver/tests/core/test_dict_entries.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `contracts.dictionary.VALUE_KINDS: frozenset[str]` and `contracts.dictionary.check_value(entry, value) -> str | None` returning a problem or `None`.

- [ ] **Step 1: Write the failing test**

```python
def test_value_kinds_are_a_core_vocabulary():
    """One source of reality: a plugin must not invent a parallel type system."""
    from omnidriver.core.contracts import dictionary

    assert {"integer", "scalar", "word", "enum", "vector3"} <= dictionary.VALUE_KINDS


def test_check_value_rejects_a_bad_vector():
    from omnidriver.core.contracts import dictionary

    entry = dictionary.DictEntry(driver_path="$X.v", value_kind="vector3")
    assert dictionary.check_value(entry, "(1 2)") is not None
    assert dictionary.check_value(entry, "(1 2 3)") is None


def test_cardiaccore_no_longer_declares_its_own_kinds():
    import inspect
    import pytest
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore.workflows import overrides

    source = inspect.getsource(overrides)
    assert "vector3" not in source or "from omnidriver.core.contracts" in source
```

- [ ] **Step 2: Run to verify it fails, then implement**

Move the five checks from `_check_value` into `contracts/dictionary.check_value`, keyed on `DictEntry.value_kind`. Have cardiacCore call it. Do **not** change any `DictEntry`'s declared `value_kind` in this task — only where the checking lives.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/contracts/dictionary.py \
        packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py \
        packages/omnidriver/tests/core/test_dict_entries.py
git commit -m "refactor(core): value kinds are core's vocabulary, not a plugin's"
```

---

## Task 5: Promote the dynamic-path placeholder

cardiacCore spells `<ventKey>` twice — in `workflows/overrides.VENT_KEY_PLACEHOLDER` and inside the catalogue's own `driver_path` strings. `DictEntry.dynamic_path` already exists.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/inputs.py`

**Interfaces:**
- Produces: `contracts.dictionary.PLACEHOLDER_RE` and `contracts.dictionary.expand_dynamic_path(entry, **bindings) -> tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_dynamic_path_expands_from_core():
    from omnidriver.core.contracts import dictionary

    entry = dictionary.DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.seed", dynamic_path=True,
    )
    assert dictionary.expand_dynamic_path(entry, ventKey=("lv", "rv")) == (
        "$PURKINJE_TREE.lv.seed", "$PURKINJE_TREE.rv.seed",
    )


def test_the_placeholder_is_spelled_once():
    """The catalogue's spelling and the resolver's were two literals."""
    import inspect
    import pytest
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore.workflows import overrides

    assert not hasattr(overrides, "VENT_KEY_PLACEHOLDER"), (
        "the placeholder grammar belongs to DictEntry, not to one plugin"
    )
```

- [ ] **Step 2: Run to verify it fails, then implement**

Add `PLACEHOLDER_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")` and `expand_dynamic_path` to `contracts/dictionary.py`. Delete `VENT_KEY_PLACEHOLDER` from cardiacCore and have `resolve_override_target` use the core expander. `catalogs/inputs.VENT_KEYS` stays — it is the binding, which is cardiacCore's, not the grammar, which is core's.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/contracts/dictionary.py \
        packages/omnidriver-cardiaccore/
git commit -m "refactor(core): the dynamic-path placeholder grammar is core's"
```

---

## Task 6: cardiacCore's override writer becomes `plan_case`

The parallel mechanism stops being parallel, and gains rollback and the ledger.

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml`
- Test: `packages/omnidriver-cardiaccore/tests/test_case_write_plan.py`

**Interfaces:**
- Consumes: `CaseWriterCapability` (Task 3), `case_write` types (Task 1).
- Produces: `CardiacCorePlugin.plan_case(request) -> CaseWritePlan`; `apply_input_overrides` retired.

- [ ] **Step 1: Write the failing test**

```python
def test_cardiaccore_plans_before_it_writes(cardiaccore_stack_context, tmp_case):
    plan = cardiaccore_stack_context.capabilities.case_writer.plan(
        case_root=tmp_case,
        values={"$PURKINJE_TREE.lv.seed": "(0 0 1)"},
    )
    assert plan.operations
    assert all(op.kind == "patch" for op in plan.operations)
    assert plan.operations[0].target.startswith("system/")


def test_a_failed_cardiaccore_write_rolls_back(cardiaccore_stack_context, tmp_case):
    """It had no rollback wrapper and was not wired to the ledger."""
    import pytest
    from omnidriver.core import case_writer

    before = (tmp_case / "system" / "generatePurkinjeTreeDict").read_bytes()
    plan = cardiaccore_stack_context.capabilities.case_writer.plan(
        case_root=tmp_case,
        values={"$PURKINJE_TREE.lv.seed": "not-a-vector"},
    )
    with pytest.raises(Exception):
        case_writer.write_case(plan, driver_context=cardiaccore_stack_context)
    assert (tmp_case / "system" / "generatePurkinjeTreeDict").read_bytes() == before
```

- [ ] **Step 2: Run to verify it fails, then implement**

Rewrite `apply_input_overrides` as a pure `plan_case` returning `CaseWriteOperation`s — one `patch` per resolved target — and delete the direct `mutators.update_foam_entry` calls. `resolve_override_target` and `_DOCUMENT_FOR_SCOPE` survive: they are how the plan is built. Declare `case_writer` in `provides:`.

Have `workflows/preprocessing.py`'s four `apply_case` closures call `plan_case` + `case_writer.write_case` instead of writing directly.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/ -v
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver-cardiaccore/
git commit -m "refactor(cardiaccore): overrides become a plan, and gain rollback"
```

---

## Task 7: cardiacCore's bespoke writers

`operations/vtu_selection.write_cell_set` and `operations/electrodes.write_*` bypass `mutators` entirely and perform no atomic rename.

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/operations/vtu_selection.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/operations/electrodes.py`

**Interfaces:**
- Consumes: the shared atomic write helper used by `case_writer` (Task 2).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
def test_operation_writers_are_atomic(tmp_path, monkeypatch):
    """A crash mid-write must not leave a truncated cellSet behind."""
    from omnidriver.cardiaccore.operations import vtu_selection

    target = tmp_path / "system" / "theSet"
    target.parent.mkdir(parents=True)
    target.write_text("previous\n")

    def _boom(*args, **kwargs):
        raise RuntimeError("interrupted")

    monkeypatch.setattr(vtu_selection, "_render_cell_set", _boom)
    try:
        vtu_selection.write_cell_set(target, cells=[1, 2, 3])
    except RuntimeError:
        pass
    assert target.read_text() == "previous\n"
```

- [ ] **Step 2: Run to verify it fails, then implement**

Route both writers through the same atomic helper `case_writer` uses. Neither needs the full plan machinery — they are agent-invoked operations, not case materialization — but both must be atomic. Create their parent directory explicitly; `electrodes.write_*`'s own docstring records that it does not.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/ -v
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/operations/
git commit -m "fix(cardiaccore): operation writers are atomic and create their parents"
```

---

## Task 8: Split `build_and_launch`

**The largest refactor in this specification.** 1007 lines mixing dictionary synthesis with orchestration — mesh provisioning, environment loading, running the solver — inside a module named `dict_builder`.

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_builder.py`
- Create: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/case_orchestration.py`
- Test: `packages/omnidriver-cardiacfoam/tests/test_dict_builder.py`

**Interfaces:**
- Consumes: `case_write` types (Task 1).
- Produces: `dict_builder.plan_case(request) -> CaseWritePlan` (pure, synthesis only); `case_orchestration.build_and_launch(...)` (everything else, unchanged behaviour).

- [ ] **Step 1: Write the characterization test first**

Before moving anything, pin current behaviour:

```python
def test_build_and_launch_writes_the_same_five_files(tmp_path, cardiacfoam_context):
    """Characterization, not specification: this records what it does today so
    the split cannot change it silently."""
    from omnidriver.cardiacfoam import dict_builder

    dict_builder.build_and_launch(
        case_root=tmp_path, spec=_minimal_spec(), dry_run=True, overwrite=True,
    )
    for relpath in (
        "constant/electroProperties", "constant/physicsProperties",
        "system/fvSchemes", "system/fvSolution", "system/controlDict",
    ):
        assert (tmp_path / relpath).exists(), relpath
```

- [ ] **Step 2: Run it to confirm it passes today**

```bash
python -m pytest packages/omnidriver-cardiacfoam/tests/test_dict_builder.py -k same_five -v
```

Expected: PASS. If it fails, the split cannot begin — fix the test until it records reality.

- [ ] **Step 3: Extract synthesis into `plan_case`**

Move `build_electro_properties`, `build_physics_properties`, and the `system_templates` calls behind a pure `plan_case` returning `synthesize` operations. It must not write.

- [ ] **Step 4: Move orchestration out**

Move `build_and_launch`'s remaining body — mesh provisioning, environment loading, `normalize_workflow_dag`, `validate_workflow_commands`, `run_workflow` — into `case_orchestration.py`. Have it call `plan_case` + `case_writer.write_case` for the file writes. Keep `dict_builder`'s public names re-exported from `case_orchestration` so no caller breaks in this task.

- [ ] **Step 5: Run the characterization test unchanged**

```bash
python -m pytest packages/omnidriver-cardiacfoam/tests/ -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`, with the characterization test **unedited**. If it needed editing, the split changed behaviour.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-cardiacfoam/
git commit -m "refactor(cardiacfoam): split synthesis from orchestration"
```

---

## Task 9: Retire the second materialization mechanism

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/sweep.py`
- Modify: `packages/omnidriver/src/omnidriver/sweep_materialize.py`, `sweep_routing.py`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/models.py`

**Interfaces:**
- Consumes: `CaseWriterCapability` (Task 3).
- Produces: `SweepMaterializerCapability` deleted; `TutorialSpec.apply_case` replaced by `plan_case`.

- [ ] **Step 1: Write the failing test**

```python
def test_both_sweep_shapes_use_one_channel(stack_context):
    """A cross-product sweep and an entry sweep must plan the same way.

    cardiacFoam had two materialization paths of its own, and which ran
    depended on how the sweep was invoked.
    """
    from omnidriver.core import plugin_capabilities

    assert not hasattr(plugin_capabilities, "SweepMaterializerCapability")
    assert "case_writer" in plugin_capabilities.PluginCapabilities.__annotations__


def test_cardiaccore_can_be_cross_product_swept(cardiaccore_stack_context, tmp_path):
    """It could be entry-swept but not cross-product swept -- not by design,
    but because one hook pair was absent."""
    from omnidriver import sweep_materialize

    plan = sweep_materialize.plan_case(
        case_dir=tmp_path, routed={"$PURKINJE_TREE.lv.seed": "(0 0 1)"},
        driver_context=cardiaccore_stack_context,
    )
    assert plan.operations
```

- [ ] **Step 2: Run to verify it fails, then implement**

Rewrite `sweep_materialize.materialize_case` to call `case_writer.plan` then `write_case`. Rewrite `cardiacfoam/sweep.route_case_values` as its `plan_case` input mapping — the routing classification survives; only its output type changes. Delete `SweepMaterializerCapability`, `legacy_route_sweep_case` and `legacy_materialize_sweep_case`.

Replace `TutorialSpec.apply_case` with `plan_case`, and have `sweep_runner._materialize_entry_case` call `write_case`.

- [ ] **Step 3: Run, regenerate the table, commit**

```bash
python -m pytest packages/ -q -m "not slow"
python3 scripts/export-capability-seams.py && python3 scripts/export-capability-seams.py --check
git add packages/ ARCHITECTURE.md
git commit -m "refactor(core,cardiacfoam): one materialization channel, not two"
```

---

## Task 10: The sweep spec gets a schema

No file, no hook. An agent learns it from `spec_error` failures.

**Files:**
- Create: `schemas/sweep-spec.json`
- Modify: `packages/omnidriver/src/omnidriver/core/sweep/sweep_expansion.py`
- Modify: `packages/omnidriver/src/omnidriver/core/introspection.py`

**Interfaces:**
- Produces: `schemas/sweep-spec.json`, validated in `expand_sweep`, surfaced in `describe` under `sweep_schema`.

- [ ] **Step 1: Write the failing test**

```python
def test_a_sweep_spec_has_a_published_schema(stack_context):
    from omnidriver.core import introspection

    payload = introspection.describe_entry(entry=None, driver_context=stack_context)
    assert "sweep_schema" in payload
    assert payload["sweep_schema"]["type"] == "object"


def test_an_invalid_sweep_spec_fails_with_a_diagnostic_not_a_string():
    from omnidriver.core.sweep import sweep_expansion

    problems = sweep_expansion.validate_spec({"sweep": {"mode": "nonsense"}})
    assert problems
    assert all(
        set(p) == {"level", "code", "message", "source", "field"} for p in problems
    )
```

- [ ] **Step 2: Run to verify it fails, then implement**

Author `schemas/sweep-spec.json` from what `expand_sweep` actually accepts — `mode`, `independent`, `dependent`, `caseId` — reading the code, not guessing. Validate in `expand_sweep` and emit `StrictDiagnostic`s. Surface the schema in `describe` beside `config_schema`.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add schemas/sweep-spec.json packages/omnidriver/src/omnidriver/core/
git commit -m "feat(core): the sweep spec has a schema an agent can read"
```

---

## Task 11: `describe` shows the write surface

Two gaps: `$TOKEN.` scopes never appear in `describe`, and five catalogues are reachable only through dev-time export scripts.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/introspection.py`

**Interfaces:**
- Produces: `describe` gains `override_scopes`, `report_catalog`, `tutorial_displays`, `utility_manifests`.

- [ ] **Step 1: Write the failing test**

```python
def test_describe_shows_what_an_agent_may_write(stack_context):
    """An agent could not learn the $TOKEN. syntax from any runtime call."""
    from omnidriver.core import introspection

    payload = introspection.describe_entry(entry=None, driver_context=stack_context)
    for key in ("override_scopes", "report_catalog", "utility_manifests"):
        assert key in payload, key
```

- [ ] **Step 2: Run to verify it fails, then implement**

Add each from its existing capability — `override_scopes.scopes()`, `report_catalog.reports()`, `command_authorization.utility_manifests()`, `tutorials.displays()`. Reuse `introspection._serialize`; do not add a second serializer.

Leave `capability_seams` out: it describes the contract, not an entry, and belongs in the generated document.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/introspection.py
git commit -m "feat(core): describe shows the write surface, not only the read one"
```

---

## Task 12: A core type for in-process operations

cardiacCore's seven Python callables travel as an opaque blob through `get_named_catalogs`. `utility_catalog` models only binaries.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/utility_catalog.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/operations.py`

**Interfaces:**
- Produces: `utility_catalog.OperationDefinition(id, callable_ref, summary, entrypoints, produces)`.

- [ ] **Step 1: Write the failing test**

```python
def test_an_in_process_operation_has_a_core_type():
    from omnidriver.core import utility_catalog

    assert hasattr(utility_catalog, "OperationDefinition")


def test_cardiaccore_operations_are_typed():
    import pytest
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.core import utility_catalog
    from omnidriver.cardiaccore.catalogs.operations import OPERATIONS

    assert all(
        isinstance(op, utility_catalog.OperationDefinition)
        for op in OPERATIONS.values()
    )
```

- [ ] **Step 2: Run to verify it fails, then implement**

Add a frozen `OperationDefinition` beside `UtilityManifest`, and convert cardiacCore's seven `_add()` records to it. `OPERATIONS` becomes a frozen mapping rather than a mutable module dict populated by import-time side effects, which removes the need for `plugin.py`'s defensive `deepcopy`.

The three `status` axes cardiacCore invented (`array_api`, `native_file_reader`, `workflow_integration`) stay plugin data — core does not model maturity.

- [ ] **Step 3: Run, commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/utility_catalog.py \
        packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/operations.py
git commit -m "feat(core): in-process operations have a type, not a blob"
```

---

## Task 13: All four shapes, and the close-out

- [ ] **Step 1: Rebuild the wheel and run every shape**

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q
python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
```

Expected: `0 failed` everywhere, waiver list empty.

- [ ] **Step 2: Confirm the two payoffs**

```bash
python -m omnidriver sweep-plan --plugin cardiaccore --spec <a cross-product sweep>
```

Expected: succeeds. Before Phase 2 it raised `SweepValidationError` naming `materialize_sweep_case`.

- [ ] **Step 3: Count the write paths**

```bash
grep -rn 'write_text\|os.replace\|shutil.copy' packages/*/src --include=*.py | grep -v test | wc -l
```

Record the number in the commit message beside the pre-Phase-2 count. The claim is not "one writer" — core's manifest and state writers legitimately remain — but that no *case content* is authored outside `case_writer`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: Phase 2 passes in all four verification shapes"
```
