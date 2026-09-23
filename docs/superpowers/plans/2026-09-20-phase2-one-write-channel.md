# Phase 2: One Case-Write Channel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One auditable transaction channel for **framework-authored case
inputs**: every such write is resolved by its semantic owner, rendered by its
format owner, reviewed as a complete immutable plan, committed by core under a
lease and a journal, and verified against the selected runtime afterwards.

**Architecture:** Three owners, one channel. The **solver adapter** answers what
a parameter means, whether it applies, and which concrete address it has. The
**format owner** — OpenFOAM for OpenFOAM syntax — renders candidate file bytes
against an isolated snapshot. **Core** owns the reviewed plan, the lease, the
journal, the commit, the rollback and the record. Core never learns dictionary
syntax; the adapter never learns transaction mechanics.

Three creation modes stay distinct, because their prerequisites differ:
`clone_and_patch` (an existing case, edited), `synthesize` (a case built from a
catalog, needing source artifacts), and `generated_input` (an operation
authoring one input file). Collapsing them is how the previous draft came to
describe asset-free synthesis as a patch.

**Tech Stack:** Python 3.11+, pytest. No new runtime dependency.

**Source spec:** `docs/superpowers/specs/2026-09-20-provider-composition-design.md` §5,
as **superseded** by [`docs/audits/2026-09-22-implementation-roadmap.md`](../../audits/2026-09-22-implementation-roadmap.md)
§4 where the two disagree. §4's disposition table is the authority on every task
below; the audit's proposal defects **W1** and **W2** are the specific mistakes
this rewrite exists to avoid.

**Prerequisite:** gate **G0** —
[`2026-09-22-phase2-prerequisites.md`](2026-09-22-phase2-prerequisites.md) —
closed. Task 1 below must not start before it is.

## Status

**Rewritten 2026-09-22.** The [pre-implementation audit and revised
roadmap](../../audits/2026-09-22-implementation-roadmap.md) retained the
one-transaction-channel goal and rejected the previous plan's contract and
examples. This document replaces them. The former task snippets are gone
rather than annotated: leaving a refuted contract next to its replacement is how
an implementer picks the wrong one. The historical proposal is recoverable from
git at `db93cc4`; §4's disposition table records what each of its thirteen tasks
became.

**Review checkpoint, 2026-09-22 (kept):** reproduced provider-ordering,
effective-readback and adapter-addressing defects are prerequisites to this
work, not part of it. They are gate G0 and now have their own plan. No Phase 2
implementation has been performed.

**Prerequisite met 2026-09-22:** Phase 1
(`docs/superpowers/plans/2026-09-20-phase1-provider-stack.md`) merged to `main`
at `02fde13`.

**G0 closed 2026-09-22.** See the Status table and close-out in
`2026-09-22-phase2-prerequisites.md`: all eight findings reproduce no longer,
four installation shapes and both static gates pass. Phase 2 may begin at G1.

| gate | task | state | commit |
|---|---|---|---|
| G1 | 1 · the mutation request and the parameter envelope | done | `bbc989b` +R2 fixes |
| G1 | 2 · the reviewed plan, complete and immutable | done | `c29c46d` +R2 fixes |
| G1 | 3 · `CaseWriterCapability` and format ownership | done | `c43a7ca` +R2 fixes |
| G1 | 4 · value kinds and dynamic-path bindings | done | `f427ae6` +R2 fixes |
| G2 | 5 · the core transaction executor | done | `9986c1d` +R3 fixes |
| G2 | 6 · recovery, replay and staleness | done | `33fb553` +R3 fixes |
| G2 | 7 · the conformance suite | done | `e13f085` +R3 fixes |
| G2 | 8 · vertical slice A — one patch path | done | `dc7fbef` |
| G2 | 9 · vertical slice B — one synthesis path | done | `8721f21` +R3 fixes |
| G3 | 10 · entry cases migrate | done (partial -- cardiacfoam specs not migrated, see report) | `255a34a` |
| G3 | 11 · sweeps migrate, and the sweep spec gets a versioned schema | done | `2480f3f` |
| G3 | 12 · cardiacCore operations and remediation migrate | done (partial -- `write_cell_set` classified, not migrated, see report) | `5e350eb` |
| G3 | 13 · `describe` shows the write surface | done | `b0ac9dd` |
| G3 | 14 · four shapes, the mutation inventory, and the close-out | pending -- not this batch | — |

**G1 closed 2026-09-23.** Review R2 returned *not closed* on twelve findings —
including proposal defect W1 fixed on one field and left open on every other,
and `renderer_for` naming the wrong provider on the two-provider stack this plan
calls the real path. All twelve fixed (`3571ecb`..`0f024c8`).

**G2 closed 2026-09-23.** Review R3 returned *not closed* on two blockers: an
unwrapped `PermissionError` escaping `commit_case_write`, and a relative
`case_root` silently committing into a different directory that happened to
share its name. Both fixed, with seven tracked findings, in `3f7dcac`..`4633aac`.
What survived R3 unscathed is worth recording too: cross-process lease
serialisation, mid-commit interruption, and a rollback whose own restore
partially fails — that last one names the failed paths, keeps the journal, and
never claims a false rollback.

## What "one write channel" does and does not mean

It means: **one auditable transaction channel for framework-authored case
inputs.** Every file this framework writes into a case as an *input* is planned,
reviewed, committed and recorded through it.

It does **not** mean:

- **Every write in the repository.** Native solvers and meshing utilities
  produce their own files. Those are declared workflow outputs with artifact
  attribution, not framework mutations. A grep count of `write_text` calls
  cannot tell the two apart, and Task 14 replaces that acceptance criterion with
  a reviewed inventory of mutation paths.
- **Simultaneous atomic visibility of several files to arbitrary outside
  processes.** Per-file atomic replacement plus a journal gives recovery, and it
  keeps framework readers from observing a half-applied transaction. An outside
  process reading the case mid-commit can see a mixed state. Task 5 documents
  the supported filesystem and reader model, and Task 7 tests interruption
  recovery. Do not write a docstring claiming more than this.
- **Control over writers outside the framework.** A lease coordinates this
  framework's attempts. A user editing a dictionary in an editor is not
  prevented; they are detected, at recheck time, as drift. State that limit
  where the lease is documented.
- **One provider answering everything.** The semantic owner and the format owner
  are different providers on the real path, and two formats may have two
  renderers. Task 3 makes ownership explicit rather than assuming an exclusive
  writer.

## The five value sources, kept apart

A plan's values come from somewhere, and the somewhere is part of the evidence.
None of these automatically becomes another:

| source | what it is |
|---|---|
| `case` | an explicit value in the case, with its file and key |
| `effective` | the value after supported native evaluation, with its dependency closure and runtime identity |
| `call_site_default` | a C++ caller-supplied default for one path and build; may appear in no dictionary |
| `template` | a tutorial example or framework-authored template value |
| `recommendation` | a domain recommendation, with applicability and supporting evidence |

A tutorial tolerance is not a universal solver default. A plausible value is not
a validated recommendation. Any code path that promotes one of these into
another without saying so is the defect this table exists to prevent — see
finding F4, where `populate_values(..., typical_value_fallback=True)` promoted
catalog examples into generated inputs.

## Execution batches and review points

Five batches, **run in sequence**, for the reason the prerequisites plan gives:
one working tree, shared absolute-path verification virtualenvs, one `git`
index. Three reviews, placed at gate boundaries rather than after each task.

| batch | tasks | gate | review after |
|---|---|---|---|
| P2-E · contracts | 1, 2, 3, 4 | G1 | **yes — R2** |
| P2-F · transaction machinery | 5, 6, 7 | G2 | no |
| P2-G · the two vertical slices | 8, 9 | G2 | **yes — R3** |
| P2-H · migration | 10, 11, 12, 13 | G3 | no |
| P2-I · close-out | 14 | G3 | **yes — R4** |

**R2 — the contract review, and the most valuable one in the programme.**
Everything downstream is built on Tasks 1–4, and W1/W2 were contract defects
that only a review caught. It must check: the serialized plan contains every
value that will be written; no frozen record has a mutable interior, including
nested ones; no before-image is a plan field; the digest is stable across
processes; `resolve` is pure and `render` is the only hook that reads; one
declarer per format; the value-kind vocabulary is closed with no escape hatch
and the migration of every existing `DictEntry` is to its real shape rather
than to a default.

**R3 — adversarial, at the G2 exit.** The conformance suite is the artefact
most likely to be quietly incomplete, so the reviewer writes at least two
failing cases the suite does not have and reports whether the channel survives
them. It must also check that both characterization tests (Tasks 8 and 9)
passed **unchanged** through the migration, and that the honesty limits in
`case_transaction.py`'s docstring are still accurate after the implementation
landed.

**R4 — the G3 exit.** Reviews the mutation-path inventory line by line against
a fresh grep, not against the implementer's table, and confirms every remaining
framework-authored input either routes through `commit_case_write` or is
declared as one of the other three classifications with a justification that
holds.

P2-F carries no review because P2-G is what proves it: a transaction executor
with no consumer is untested design, and R3 reviews both together.

## Decision, 2026-09-23: a parameter value is typed data, never rendered text

Review R2 found this contract question unmade, and every task from 5 onward
depends on it. Deciding it here.

**`ParameterAssignment.value` carries native Python data.** A `vector3` is
`(1.0, 0.0, 0.0)`, not `"(1 0 0)"`. A `dimensioned_scalar` is
`{"value": 50000, "dimensions": (0, -3, 0, 0, 0, 1, 0)}`, not
`"[0 -3 0 0 0 1 0] 50000"`. Rendering that into dictionary syntax is the format
owner's job, in `render_case_files`, and nowhere else.

Four reasons, in order of weight:

1. **The alternative puts OpenFOAM syntax in core.** `case_write.py` is a core
   module and this plan's hardest constraint is that core moves bytes and
   digests. A `value` field holding `"[0 -3 0 0 0 1 0] 50000"` is dictionary
   syntax sitting in core, and every consumer that reads it has to parse it —
   which is the layering failure that deleting `openfoam_literal` fixed.
2. **It is the only way `validate_value_shape` can mean anything.** Against
   rendered text every kind collapses to "is a string", which is the
   unqualified scalar/string vocabulary the roadmap §2 names as unsafe, and it
   reopens the `nan`-for-a-scalar hole that audit finding S1 closed.
3. **Text comparison is already known to be wrong here.** Finding F1b: a
   requested `1e-3` resolves natively to `0.001`, and comparing spellings
   rejected a correct edit. Storing spellings would rebuild that defect inside
   the plan.
4. **The write channel is new code and inherits nothing.** The rendered strings
   R2 found — `test_override_round_trip.py`'s `_VALUES` — belong to the
   existing `--apply` override surface, not to this channel. An adapter that
   holds a rendered string parses it when it builds the request. That is the
   adapter's job: it owns what the parameter means.

**On the objection that deleting `openfoam_literal` removed the way to say
"pre-rendered text", and nothing replaced it.** Nothing needed to. A value core
cannot type is not a parameter — it is content, and content already has a
carrier: `RenderedFile`, which holds complete bytes the format owner produced.
A `#codeStream` block or an arbitrary sub-dictionary reaches disk as part of a
rendered file, not as a `ParameterAssignment`. Do **not** add a `literal` kind,
a `text` kind, or an untyped escape to `VALUE_KINDS`. If a case arises that
this genuinely cannot express, that is a finding worth reporting — not a reason
to reintroduce the default that let `nan` through.

**Consequence to implement:** `ParameterAssignment.__post_init__` calls
`validate_value_shape(self.value_kind, self.value)` and raises on any returned
reason. That is what closes R2's finding 4.

## Global Constraints

- Python floor is **3.11**. Keep lazy annotations in `plugin_interface.py`.
- `omnidriver.core` MUST NOT import from any adapter package; the waiver list in
  `scripts/check-import-boundaries.py` stays empty.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- **No OpenFOAM syntax in core.** Core moves bytes and digests. If a core module
  needs to know what a `;` means, the design is wrong.
- No production module in core or an adapter may touch `driver_context.providers` directly.
- Do not weaken or skip a guard to make a change pass.
- **Every write must be rollback-safe.** A task that adds a write path without a
  before-image in the journal is incomplete.
- **A new shared abstraction needs two demonstrated consumers**, an explicit
  contract, and a deletion or migration target for what it replaces. Tasks 8 and
  9 are the two consumers; do not extract shared byte-writing mechanics before
  both exist.
- Do not quote suite totals. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number.
- Record a document correction with a date rather than overwriting it silently.
- Do not add a `LICENSE` file or a `license` field to any `pyproject.toml`.
- Rebuild the wheel after every source change before running the wheel shape.
- Large assets (meshes, VTU) are referenced by digest and staged, never embedded
  in plan JSON.
- **Do not stage pre-existing work.** Run `git status` before every commit and
  treat every pre-existing modification as someone else's WIP. Never `git add -A`.

## How to execute a task in this plan

**Verify every factual claim before acting on it.** These tasks were written
against `db93cc4` on 2026-09-22 and the codebase moves. The contract's own
docstrings have been wrong six times.

**"Expected: PASS" has been wrong twice.** A correct fix can expose a real gap
downstream. Investigate the gap, decide the remedy on evidence, and report. Do
not narrow the fix and do not weaken a test.

**Reuse before you build.** This plan names the existing machinery each task
should reuse — `remediation_transaction`'s `_atomic_write_bytes`,
`_fsync_directory` and `_snapshot_targets`; `attempt_lease`'s `acquire_case_lease`
and `acquire_case_staging_lease`; `planning_types`' `StrictDiagnostic`;
`provider_identity`'s `StackIdentity`. A task that reimplements one of these has
gone wrong. If the existing one does not fit, say why in your report before
replacing it.

**Fixture and helper names in these snippets are illustrative.** Check what
already exists in the target test file and its conftest first. Known trap:
`plugin_discovery.discover_plugins()` returns `EntryPoint` objects — use
`load_discovered_plugin(name)`.

**`from conftest import X` is unreliable.** Both packages' `tests` directories
are reachable when the whole repo is collected, and core's conftest wins. Use a
uniquely named module inside an importable package.

**A test may encode a defect as intended behaviour.** One did, in
`test_workflow_command_security.py`, with a comment explaining the hole as a
design choice. Correct it with a dated note **and** add a test for the corrected
behaviour.

**Do not write a test that asserts only that a symbol exists**, and do not write
one that expects arbitrary text such as `"bad"` to fail without a declared type
constraint that makes it fail. Both appeared in the refuted draft.

**Report being wrong as a finding.** A plan that mis-describes the codebase is
information, not a failure.

---

## File Structure

**Core — created:**
- `core/case_write.py` — the request, the parameter envelope, the rendered file,
  the precondition, the reviewed plan, the committed record. **Types and
  canonical serialization only; no I/O, no filesystem access.**
- `core/case_transaction.py` — the commit executor: lease, journal, atomic
  replacement, rollback, recovery. The only module in the repository that writes
  a framework-authored case input.
- `tests/core/test_case_write_plan.py` (Task 2)
- `tests/core/test_case_write_request.py` (Task 1)
- `tests/core/test_case_writer_capability.py` (Task 3)
- `tests/core/test_case_transaction.py` (Task 5)
- `tests/core/test_case_transaction_recovery.py` (Task 6)
- `tests/core/test_write_channel_conformance.py` (Task 7)

**Core — modified:**
- `core/plugin_capabilities.py` — `CaseWriterCapability` and its adapter;
  `SweepMaterializerCapability` retires into it in Task 11.
- `core/plugin_interface.py` — the three new protocol members.
- `core/provider_stack.py` — composition classification for those members, and a
  one-declarer-per-format check.
- `core/contracts/dictionary.py` — the closed `value_kind` vocabulary and the
  dynamic-path binding grammar.
- `core/runtime/models.py` — `TutorialSpec.apply_case` retires in Task 10.
- `core/runtime/remediation_transaction.py` — shared mechanics extracted in
  Task 5, **after** Tasks 8 and 9 prove two consumers.
- `sweep_materialize.py`, `sweep_routing.py` — route through the channel (Task 11).
- `core/introspection.py` — `describe` emits the write surface (Task 13).
- `core/utility_catalog.py` — an in-process operation type, **only if** Task 12
  demonstrates two consumers needing common validation.

**Core — created as an installed resource:**
- `src/omnidriver/resources/sweep-spec.schema.json` — inside the package, not a
  repository-only `schemas/` directory, because a repository-only file is absent
  from every wheel (Task 11).

**OpenFOAM — modified:**
- `openfoam/case_rendering.py` (created) — renders `patch` and `synthesize`
  edits for the `openfoam_dictionary` format against a snapshot. The only place
  dictionary syntax appears in this channel.
- `openfoam/environment.py` — declares the format and the two render members.

**Adapters — modified:**
- `omnidriver-cardiacfoam/.../dict_builder.py` — `build_and_launch` splits;
  synthesis becomes a resolve/render pair (Task 9).
- `omnidriver-cardiacfoam/.../sweep.py` — `route`/`materialize` become resolve
  plus a plan (Task 11).
- `omnidriver-cardiaccore/.../workflows/overrides.py` — resolve only; the write
  moves to the channel (Task 8).
- `omnidriver-cardiaccore/.../operations/vtu_selection.py`,
  `operations/electrodes.py` — case inputs join the channel; standalone exports
  get their own stated artifact contract (Task 12).

---

## Gate G1 — approve executable contracts

Exit evidence: a small neutral provider plus both adapters can describe their
supported mutation modes; a reviewed plan is complete and stable across
processes; no OpenFOAM syntax appears in core.

---

## Task 1: The mutation request and the parameter envelope

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/case_write.py`
- Create: `packages/omnidriver/tests/core/test_case_write_request.py`

**Interfaces:**
- Consumes: `qualified_slot_key`-style qualified addressing from G0 Task 5 — core
  does not import it, but the addresses it validates have that shape.
- Produces:
  `CaseMutationRequest(mode, case_root, adapter_id, workflow, source_artifacts, parameters, requested_by)`;
  `MUTATION_MODES = frozenset({"clone_and_patch", "synthesize", "generated_input"})`;
  `ParameterAssignment(qualified_id, owner, document, key_path, binding, value, value_kind, source)`;
  `VALUE_SOURCES = frozenset({"case", "effective", "call_site_default", "template", "recommendation"})`.
  Every later task uses these names.

- [ ] **Step 1: Confirm G0 is closed**

```bash
grep -n "G0 closed" docs/superpowers/plans/2026-09-22-phase2-prerequisites.md
```

Expected: one match with a date. If there is none, stop. The reviewed plan
records a stack identity and a resolution provenance; both were
non-deterministic or untruthful before G0, and a plan bound to either is not
reproducible.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_write_request.py`:

```python
"""A mutation request names its mode, its owner, and its sources.

Three creation modes with different prerequisites, deliberately not collapsed:

``clone_and_patch``  an existing case is edited. Source: that case.
``synthesize``       a case is built from a catalog. Needs explicit source
                     artifacts -- a mesh, a template tree -- which a patch does
                     not.
``generated_input``  an operation authors one input file.

The refuted draft had two kinds, ``patch`` and ``synthesize``, and described
them as "the same operation at different arities". They are not: a synthesis
with no source artifact declared is a case built from nothing, and that is how
asset-free synthesis came to look like a supported mode.
"""

from pathlib import Path

import pytest

from omnidriver.core import case_write


def _assignment(**overrides):
    fields = dict(
        qualified_id="$CARDIAC_CONDUCTIVITY.df",
        owner="org.cardiaccore",
        document="system/setCardiacConductivityDict",
        key_path=("df",),
        binding={},
        value=0.1,
        value_kind="scalar",
        source="case",
    )
    fields.update(overrides)
    return case_write.ParameterAssignment(**fields)


def test_an_unsupported_mode_is_refused_by_name():
    with pytest.raises(ValueError, match="rewrite"):
        case_write.CaseMutationRequest(
            mode="rewrite", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(), requested_by="test",
        )


def test_synthesis_without_a_source_artifact_is_refused():
    """A case built from nothing is not a supported creation mode."""
    with pytest.raises(ValueError, match="source artifact"):
        case_write.CaseMutationRequest(
            mode="synthesize", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(_assignment(),), requested_by="test",
        )


def test_a_patch_needs_no_source_artifact():
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.a", workflow="w", source_artifacts=(),
        parameters=(_assignment(),), requested_by="test",
    )
    assert request.mode == "clone_and_patch"


def test_a_parameter_keeps_its_document_scope():
    """Two documents declaring one leaf name are two parameters.

    The unqualified form is what let an absent scar dictionary overwrite a
    present conductivity dictionary's field name (audit finding S3).
    """
    conductivity = _assignment(qualified_id="$CARDIAC_CONDUCTIVITY.fiberField",
                               document="system/setCardiacConductivityDict")
    scar = _assignment(qualified_id="$CARDIAC_SCAR.fiberField",
                       document="system/setCardiacScarDict")
    assert conductivity.slot() != scar.slot()


def test_two_assignments_to_one_slot_are_refused():
    duplicate = (_assignment(), _assignment(value=0.2))
    with pytest.raises(ValueError, match="assigned twice"):
        case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=duplicate, requested_by="test",
        )


def test_an_unknown_value_source_is_refused():
    """A value's origin is evidence. "I do not know where this came from" is
    not one of the five sources."""
    with pytest.raises(ValueError, match="plausible"):
        _assignment(source="plausible")


@pytest.mark.parametrize("source", sorted(case_write.VALUE_SOURCES))
def test_every_declared_source_is_accepted(source):
    assert _assignment(source=source).source == source


def test_an_absolute_document_path_is_refused():
    with pytest.raises(ValueError, match="case-relative"):
        _assignment(document="/etc/passwd")


def test_a_document_path_escaping_the_case_is_refused():
    with pytest.raises(ValueError, match="escape"):
        _assignment(document="../outside/dict")


def test_a_dynamic_binding_must_be_declared_not_inferred():
    """`<ventKey>` accepted `banana` because the segment was substituted
    without being checked (audit finding S1). A binding carries its allowed
    values with it."""
    with pytest.raises(ValueError, match="banana"):
        _assignment(
            qualified_id="$PURKINJE_TREE.<ventKey>.seed",
            key_path=("<ventKey>", "seed"),
            binding={"<ventKey>": "banana"},
            value=[1.0, 2.0, 3.0],
            value_kind="vector3",
            allowed_bindings={"<ventKey>": ("lv", "rv")},
        )


def test_a_declared_binding_is_accepted_and_expanded():
    assignment = _assignment(
        qualified_id="$PURKINJE_TREE.<ventKey>.seed",
        key_path=("<ventKey>", "seed"),
        binding={"<ventKey>": "lv"},
        value=[1.0, 2.0, 3.0],
        value_kind="vector3",
        allowed_bindings={"<ventKey>": ("lv", "rv")},
    )
    assert assignment.expanded_key_path() == ("lv", "seed")
```

- [ ] **Step 3: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_write_request.py -v
```

Expected: FAIL — no module `case_write`.

- [ ] **Step 4: Implement**

Create `packages/omnidriver/src/omnidriver/core/case_write.py`:

```python
"""What a framework-authored case mutation is, before anything is written.

Core owns this vocabulary. A solver adapter fills it with meaning; a format
owner turns it into bytes; core commits those bytes. Nothing in this module
touches a filesystem or knows any dictionary syntax -- it is types and
canonical serialization, and that is what lets it sit in core at all.

Three creation modes, kept distinct because their prerequisites differ:

``clone_and_patch``   an existing case is edited in place or into a clone.
``synthesize``        a case is built from a catalog. Requires explicit source
                      artifacts; a case built from nothing is not a supported
                      mode.
``generated_input``   one input file is authored by an operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

MUTATION_MODES = frozenset({"clone_and_patch", "synthesize", "generated_input"})

#: Where a value came from. These never convert into one another: a tutorial
#: example is not a solver default, and a plausible number is not a validated
#: recommendation. See the plan's "five value sources" table.
VALUE_SOURCES = frozenset({
    "case", "effective", "call_site_default", "template", "recommendation",
})


def _check_case_relative(label: str, value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError(f"{label} must be case-relative, not absolute: {value!r}")
    if ".." in path.parts:
        raise ValueError(f"{label} must not escape the case: {value!r}")
    return path


def _freeze(value: Any) -> Any:
    """Deep-freeze a payload so a "frozen" record has no mutable interior.

    ``@dataclass(frozen=True)`` prevents rebinding a field, not mutating the
    object a field points at. A plan holding a ``dict`` is a reviewed plan whose
    reviewed contents can change after review -- proposal defect W1.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in sorted(value.items())})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (bytearray, set)):
        raise TypeError(
            f"a plan payload must be JSON-shaped and immutable; got {type(value).__name__}"
        )
    return value


@dataclass(frozen=True)
class ParameterAssignment:
    """One parameter, addressed unambiguously, with its value and its origin."""

    qualified_id: str
    owner: str
    document: str
    key_path: tuple[str, ...]
    binding: Mapping[str, str]
    value: Any
    value_kind: str
    source: str
    allowed_bindings: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    unit: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_case_relative("a parameter's document", self.document)
        if not self.key_path:
            raise ValueError(f"parameter {self.qualified_id!r} names no key")
        if self.source not in VALUE_SOURCES:
            raise ValueError(
                f"parameter {self.qualified_id!r} declares value source "
                f"{self.source!r}; known sources are {sorted(VALUE_SOURCES)}"
            )
        for placeholder, bound in self.binding.items():
            allowed = self.allowed_bindings.get(placeholder)
            if allowed is None:
                raise ValueError(
                    f"parameter {self.qualified_id!r} binds {placeholder!r} but "
                    f"declares no allowed values for it; an undeclared binding "
                    f"writes a key no utility reads"
                )
            if bound not in allowed:
                raise ValueError(
                    f"parameter {self.qualified_id!r} binds {placeholder!r} to "
                    f"{bound!r}, which is not one of {list(allowed)}"
                )
        object.__setattr__(self, "value", _freeze(self.value))
        object.__setattr__(self, "binding", _freeze(self.binding))
        object.__setattr__(
            self, "allowed_bindings",
            MappingProxyType({
                key: tuple(values) for key, values in sorted(self.allowed_bindings.items())
            }),
        )

    def slot(self) -> str:
        """The address this assignment occupies, document scope included."""
        return f"{self.document}::{'.'.join(self.expanded_key_path())}"

    def expanded_key_path(self) -> tuple[str, ...]:
        return tuple(self.binding.get(segment, segment) for segment in self.key_path)

    def to_json(self) -> dict[str, Any]:
        return {
            "qualified_id": self.qualified_id,
            "owner": self.owner,
            "document": self.document,
            "key_path": list(self.key_path),
            "binding": dict(self.binding),
            "expanded_key_path": list(self.expanded_key_path()),
            "value": _json_value(self.value),
            "value_kind": self.value_kind,
            "source": self.source,
            "unit": self.unit,
            "evidence_refs": list(self.evidence_refs),
        }


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class CaseMutationRequest:
    """An explicit request to author case inputs, in a declared mode."""

    mode: str
    case_root: Path
    adapter_id: str
    workflow: str
    source_artifacts: tuple[str, ...]
    parameters: tuple[ParameterAssignment, ...]
    requested_by: str

    def __post_init__(self) -> None:
        if self.mode not in MUTATION_MODES:
            raise ValueError(
                f"unsupported creation mode {self.mode!r}; supported modes are "
                f"{sorted(MUTATION_MODES)}"
            )
        if self.mode == "synthesize" and not self.source_artifacts:
            raise ValueError(
                "a synthesize request must name at least one source artifact; a "
                "case built from no declared source is not a supported creation "
                "mode"
            )
        seen: dict[str, str] = {}
        for parameter in self.parameters:
            slot = parameter.slot()
            if slot in seen:
                raise ValueError(
                    f"slot {slot!r} is assigned twice, by {seen[slot]!r} and "
                    f"{parameter.qualified_id!r}; which one survives would "
                    f"depend on iteration order"
                )
            seen[slot] = parameter.qualified_id

    def to_json(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "case_root": str(self.case_root),
            "adapter_id": self.adapter_id,
            "workflow": self.workflow,
            "source_artifacts": list(self.source_artifacts),
            "parameters": [parameter.to_json() for parameter in self.parameters],
            "requested_by": self.requested_by,
        }
```

- [ ] **Step 5: Run the tests**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_write_request.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
python3 scripts/check-import-boundaries.py
```

Expected: the new file PASSES, core reports `0 failed`, the import gate exits 0.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/case_write.py packages/omnidriver/tests/core/test_case_write_request.py
git commit -m "feat(core): the case-mutation request and parameter envelope

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 2: The reviewed plan, complete and immutable

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/case_write.py`
- Create: `packages/omnidriver/tests/core/test_case_write_plan.py`

**Interfaces:**
- Consumes: `CaseMutationRequest`, `ParameterAssignment` (Task 1).
- Produces:
  `RenderedFile(path, content, content_digest, mode, exists_before, before_digest, renderer_id, format)`;
  `Precondition(kind, target, digest, must_be_absent)` with
  `PRECONDITION_KINDS = frozenset({"file", "include", "source_artifact", "environment", "absence"})`;
  `CaseWritePlan(schema_version, request, files, preconditions, semantic_owner_id, stack_identity, created_at)`
  with `plan_id`, `plan_digest`, `to_json()` and `from_json()`;
  `CaseWriteRecord(transaction_id, plan_id, plan_digest, committed, evidence, status)`.
  Tasks 5–14 all use these.

This task is where proposal defect **W1** is closed. Three specific mistakes in
the refuted draft, each with a test below:

1. `to_json` omitted the operation's `value` and `key`, so the payload an agent
   reviewed did not contain what would be written.
2. `@dataclass(frozen=True)` held a `value: Any` that could be a `dict`, so the
   reviewed contents were mutable after review.
3. `before: bytes | None` lived inside the plan. A before-image is execution
   state that the journal owns; a plan carrying one is a plan that changes when
   it is executed.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_write_plan.py`:

```python
"""A reviewed plan contains everything that will happen, and nothing that has.

Closes proposal defect W1. The previous draft's plan omitted values from its
JSON, held mutable payloads inside frozen records, and carried execution-time
before-images as plan fields.

A plan is reviewable only if what an agent reads is what will be written, and
stable only if the bytes it hashes cannot change afterwards.
"""

from pathlib import Path

import pytest

from omnidriver.core import case_write


def _request():
    return case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"),
        adapter_id="org.cardiacfoam", workflow="entry",
        source_artifacts=(),
        parameters=(
            case_write.ParameterAssignment(
                qualified_id="$ELECTRO.ionicModel", owner="org.cardiacfoam",
                document="constant/electroProperties", key_path=("ionicModel",),
                binding={}, value="TT06", value_kind="word", source="case",
            ),
        ),
        requested_by="test",
    )


def _file(**overrides):
    fields = dict(
        path="constant/electroProperties",
        content=b"ionicModel TT06;\n",
        mode=None,
        exists_before=True,
        before_digest="a" * 64,
        renderer_id="org.openfoam",
        format="openfoam_dictionary",
    )
    fields.update(overrides)
    return case_write.RenderedFile(**fields)


def _plan(**overrides):
    fields = dict(
        request=_request(),
        files=(_file(),),
        preconditions=(
            case_write.Precondition(
                kind="file", target="constant/electroProperties",
                digest="a" * 64, must_be_absent=False,
            ),
        ),
        semantic_owner_id="org.cardiacfoam",
        stack_identity="deadbeef" * 8,
        created_at="2026-09-22T00:00:00Z",
    )
    fields.update(overrides)
    return case_write.CaseWritePlan(**fields)


def test_the_serialized_plan_contains_every_value_that_will_be_written():
    payload = _plan().to_json()
    parameter = payload["request"]["parameters"][0]
    assert parameter["value"] == "TT06"
    assert parameter["expanded_key_path"] == ["ionicModel"]
    rendered = payload["files"][0]
    assert rendered["content_digest"]
    assert rendered["path"] == "constant/electroProperties"
    assert rendered["format"] == "openfoam_dictionary"


def test_a_plan_round_trips_through_json_unchanged():
    plan = _plan()
    assert case_write.CaseWritePlan.from_json(plan.to_json()).plan_digest == plan.plan_digest


def test_a_frozen_plan_has_no_mutable_interior():
    """W1: `frozen=True` stops rebinding a field, not mutating what it points
    at. A reviewed plan whose reviewed contents can change is not reviewed."""
    plan = _plan()
    with pytest.raises(Exception):
        plan.files = ()
    parameter = plan.request.parameters[0]
    with pytest.raises(TypeError):
        parameter.binding["injected"] = "value"


def test_a_dict_valued_parameter_is_frozen_too():
    assignment = case_write.ParameterAssignment(
        qualified_id="$ELECTRO.coeffs", owner="org.a",
        document="constant/electroProperties", key_path=("coeffs",),
        binding={}, value={"gNa": 1.0}, value_kind="dictionary", source="template",
    )
    with pytest.raises(TypeError):
        assignment.value["gNa"] = 2.0


def test_a_plan_carries_no_before_image():
    """W1: a before-image is execution state. The journal owns it; a plan that
    gains one during execution is not the plan that was reviewed."""
    fields = {field.name for field in case_write.CaseWritePlan.__dataclass_fields__.values()}
    assert "before" not in fields
    rendered_fields = {
        field.name for field in case_write.RenderedFile.__dataclass_fields__.values()
    }
    assert "before" not in rendered_fields
    # A digest of the prior content is evidence and belongs here; the bytes
    # themselves are recovery state and do not.
    assert "before_digest" in rendered_fields


def test_the_digest_is_stable_across_processes():
    """The digest is what a stale-plan check compares. Dict iteration order,
    float repr and key order must not enter it."""
    import json
    import subprocess
    import sys
    import textwrap

    probe = textwrap.dedent(
        """
        from pathlib import Path
        from omnidriver.core import case_write
        request = case_write.CaseMutationRequest(
            mode="clone_and_patch", case_root=Path("/tmp/case"),
            adapter_id="org.a", workflow="w", source_artifacts=(),
            parameters=(
                case_write.ParameterAssignment(
                    qualified_id="$E.coeffs", owner="org.a",
                    document="constant/electroProperties", key_path=("coeffs",),
                    binding={}, value={"z": 1.0, "a": 2.0, "m": 3.0},
                    value_kind="dictionary", source="template",
                ),
            ),
            requested_by="probe",
        )
        plan = case_write.CaseWritePlan(
            request=request,
            files=(case_write.RenderedFile(
                path="constant/electroProperties", content=b"x",
                mode=None, exists_before=False, before_digest=None,
                renderer_id="org.openfoam", format="openfoam_dictionary",
            ),),
            preconditions=(),
            semantic_owner_id="org.a",
            stack_identity="0" * 64,
            created_at="2026-09-22T00:00:00Z",
        )
        print(plan.plan_digest)
        """
    )
    digests = set()
    for seed in ("0", "1", "2", "3"):
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        digests.add(result.stdout.strip())
    assert len(digests) == 1, digests


def test_a_rendered_file_outside_the_case_is_refused():
    with pytest.raises(ValueError, match="case-relative"):
        _file(path="/etc/passwd")
    with pytest.raises(ValueError, match="escape"):
        _file(path="../outside")


def test_two_rendered_files_at_one_path_are_refused():
    with pytest.raises(ValueError, match="written twice"):
        _plan(files=(_file(), _file(content=b"other\n")))


def test_a_schema_version_mismatch_is_refused_with_the_versions_named():
    payload = _plan().to_json()
    payload["schema_version"] = 999
    with pytest.raises(ValueError, match="999"):
        case_write.CaseWritePlan.from_json(payload)


def test_an_unknown_precondition_kind_is_refused():
    with pytest.raises(ValueError, match="guess"):
        case_write.Precondition(
            kind="guess", target="x", digest=None, must_be_absent=False,
        )


def test_an_absence_precondition_carries_no_digest():
    """"This file must not exist" and "this file must have digest X" are
    different claims. A precondition asserting both is incoherent."""
    with pytest.raises(ValueError, match="absent"):
        case_write.Precondition(
            kind="absence", target="constant/x", digest="a" * 64, must_be_absent=True,
        )


def test_a_record_is_separate_from_its_plan():
    """The committed result is not a field of the plan. Recording it there is
    how a reviewed artifact comes to differ from what was reviewed."""
    plan = _plan()
    record = case_write.CaseWriteRecord(
        transaction_id="t1", plan_id=plan.plan_id, plan_digest=plan.plan_digest,
        committed=({"path": "constant/electroProperties", "digest": "b" * 64},),
        evidence=(), status="committed",
    )
    assert record.plan_digest == plan.plan_digest
    assert "committed" not in {
        field.name for field in case_write.CaseWritePlan.__dataclass_fields__.values()
    }
```

- [ ] **Step 2: Run to verify it fails**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_write_plan.py -v
```

Expected: FAIL — `RenderedFile`, `Precondition`, `CaseWritePlan` and
`CaseWriteRecord` do not exist.

- [ ] **Step 3: Implement**

Append to `packages/omnidriver/src/omnidriver/core/case_write.py`:

```python
import hashlib
import json

#: Bumped whenever a field is added, removed or reinterpreted. A plan
#: serialized under one version is not readable under another: a reader that
#: silently accepts an older payload is a reader that fills a missing field
#: with a default nobody reviewed.
PLAN_SCHEMA_VERSION = 1

PRECONDITION_KINDS = frozenset({
    "file",              # a case file that must have this digest
    "include",           # a file the renderer read through an include directive
    "source_artifact",   # a mesh or template the synthesis consumed
    "environment",       # an environment value the resolution depended on
    "absence",           # a location that must stay empty, because a file
                         # appearing there changes which file is selected
})


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json(payload: Any) -> str:
    """The one serialization a digest is taken over.

    ``sort_keys`` and fixed separators, so dict iteration order cannot enter a
    digest. ``allow_nan=False``, because ``NaN`` is not JSON and a payload
    carrying one round-trips into something a reader cannot parse.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False,
    )


@dataclass(frozen=True)
class RenderedFile:
    """One file's complete proposed content, as its format owner rendered it."""

    path: str
    content: bytes
    mode: int | None
    exists_before: bool
    before_digest: str | None
    renderer_id: str
    format: str

    def __post_init__(self) -> None:
        _check_case_relative("a rendered file's path", self.path)
        if not isinstance(self.content, bytes):
            raise TypeError(
                f"rendered content for {self.path!r} must be bytes, not "
                f"{type(self.content).__name__}; core does not encode text it "
                f"cannot read"
            )
        if self.exists_before and not self.before_digest:
            raise ValueError(
                f"{self.path!r} is declared to exist before the write but "
                f"carries no before-digest; a conflict check needs one"
            )
        if not self.exists_before and self.before_digest:
            raise ValueError(
                f"{self.path!r} is declared absent before the write but carries "
                f"a before-digest"
            )

    @property
    def content_digest(self) -> str:
        return _digest_bytes(self.content)

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_digest": self.content_digest,
            "content_bytes": len(self.content),
            "mode": self.mode,
            "exists_before": self.exists_before,
            "before_digest": self.before_digest,
            "renderer_id": self.renderer_id,
            "format": self.format,
        }


@dataclass(frozen=True)
class Precondition:
    """One fact that must still hold when the plan is committed."""

    kind: str
    target: str
    digest: str | None
    must_be_absent: bool

    def __post_init__(self) -> None:
        if self.kind not in PRECONDITION_KINDS:
            raise ValueError(
                f"a precondition may not guess its kind: {self.kind!r} is not "
                f"one of {sorted(PRECONDITION_KINDS)}"
            )
        if self.must_be_absent and self.digest:
            raise ValueError(
                f"precondition on {self.target!r} requires the target to be "
                f"absent and also to have a digest; those are different claims"
            )

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "target": self.target,
            "digest": self.digest, "must_be_absent": self.must_be_absent,
        }


@dataclass(frozen=True)
class CaseWritePlan:
    """Everything that will happen, reviewable before any of it does.

    The plan holds no execution state. Before-*images* live in the journal
    (:mod:`omnidriver.core.case_transaction`); before-*digests* live here,
    because a conflict check is part of what a reviewer approves.
    """

    request: CaseMutationRequest
    files: tuple[RenderedFile, ...]
    preconditions: tuple[Precondition, ...]
    semantic_owner_id: str
    stack_identity: str
    created_at: str
    schema_version: int = PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for rendered in self.files:
            if rendered.path in seen:
                raise ValueError(
                    f"{rendered.path!r} is written twice by one plan; the "
                    f"surviving content would depend on ordering"
                )
            seen.add(rendered.path)

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.to_json(),
            "files": [rendered.to_json() for rendered in self.files],
            "preconditions": [p.to_json() for p in self.preconditions],
            "semantic_owner_id": self.semantic_owner_id,
            "stack_identity": self.stack_identity,
            "created_at": self.created_at,
        }

    @property
    def plan_digest(self) -> str:
        return hashlib.sha256(canonical_json(self.to_json()).encode()).hexdigest()

    @property
    def plan_id(self) -> str:
        return self.plan_digest[:16]

    @classmethod
    def from_json(cls, payload: Mapping[str, Any]) -> "CaseWritePlan":
        version = payload.get("schema_version")
        if version != PLAN_SCHEMA_VERSION:
            raise ValueError(
                f"plan schema version {version!r} is not {PLAN_SCHEMA_VERSION}; "
                f"reading it would mean filling fields nobody reviewed"
            )
        raise NotImplementedError(
            "implement alongside the first consumer that reads a persisted plan"
        )


@dataclass(frozen=True)
class CaseWriteRecord:
    """What a committed transaction actually did. Not part of the plan."""

    transaction_id: str
    plan_id: str
    plan_digest: str
    committed: tuple[Mapping[str, Any], ...]
    evidence: tuple[Mapping[str, Any], ...]
    status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "plan_id": self.plan_id,
            "plan_digest": self.plan_digest,
            "committed": [dict(entry) for entry in self.committed],
            "evidence": [dict(entry) for entry in self.evidence],
            "status": self.status,
        }
```

**Superseded 2026-09-23.** `from_json` was implemented in full during Task 2,
not deferred to Task 6, and it takes `payload` alone — no `contents=`
side-channel. `RenderedFile` embeds its bytes as base64, so a persisted plan
already round-trips without one. The Task 6 snippet below that calls
`from_json(payload, contents={...})` is stale; ignore its signature.

- [ ] **Step 4: Run and commit**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_write_plan.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
git add packages/omnidriver/src/omnidriver/core/case_write.py packages/omnidriver/tests/core/test_case_write_plan.py
git commit -m "feat(core): a complete, immutable, digest-stable reviewed plan

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 3: `CaseWriterCapability` and format ownership

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py`
- Create: `packages/omnidriver/tests/core/test_case_writer_capability.py`

**Interfaces:**
- Consumes: `CaseMutationRequest`, `RenderedFile`, `Precondition` (Tasks 1–2).
- Produces three protocol members:
  `resolve_case_mutation(request, *, driver_context) -> ResolvedMutation` (semantic owner, **pure**);
  `get_rendered_formats() -> frozenset[str]` (format ownership declaration);
  `render_case_files(resolved, *, snapshot_root, driver_context, execution_env) -> tuple[RenderedFile, ...]`
  (format owner, **reads the filesystem**, writes nothing outside `snapshot_root`).
  Plus `ResolvedMutation(request, targets, preconditions, expected_effects, semantic_owner_id)`
  in `case_write.py`, and `CaseWriterCapability` in `plugin_capabilities.py`.

The refuted draft assumed one exclusive writer answering everything. Two owners
are on the real path — the adapter knows what a parameter means, OpenFOAM knows
how to spell it — so ownership is split by *what is being answered*, and
rendering is dispatched by *declared format*, with one declarer per format.

The pure/impure split matters and is easy to get wrong: `resolve_case_mutation`
must not touch the filesystem, which is what makes a dry run non-destructive.
`render_case_files` reads — it must, to patch an existing file — and writes only
inside the snapshot core hands it.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_writer_capability.py`:

```python
"""Who answers what, and what happens when nobody does.

Resolution is the semantic owner's: what a parameter means, whether it applies,
where it lives. Rendering is the format owner's: how that address and value are
spelled in that file format. Committing is core's.

One declarer per format, for the same reason there is one declarer per case
file: two providers claiming to render `openfoam_dictionary` makes the bytes
that reach disk depend on composition order.
"""

from pathlib import Path

import pytest

from omnidriver.core import case_write, plugin_capabilities, provider_stack


class _Profile:
    def __init__(self, requires=()):
        self.requires = tuple(requires)
        self.case_files = ()


class _Renderer:
    plugin_id = "org.format"

    def get_profile(self):
        return _Profile()

    def get_rendered_formats(self):
        return frozenset({"openfoam_dictionary"})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env):
        return (
            case_write.RenderedFile(
                path="constant/electroProperties", content=b"ionicModel TT06;\n",
                mode=None, exists_before=False, before_digest=None,
                renderer_id=self.plugin_id, format="openfoam_dictionary",
            ),
        )


class _SecondRenderer(_Renderer):
    plugin_id = "org.other_format"


def test_two_providers_claiming_one_format_are_refused():
    with pytest.raises(ValueError, match="openfoam_dictionary"):
        provider_stack.compose(
            provider_stack.order_providers([_Renderer(), _SecondRenderer()])
        )


def test_a_format_nobody_declares_is_refused_by_name_not_silently_skipped():
    """An unrenderable file must stop the plan. Dropping it would commit a
    partial case that looks complete."""
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Renderer())
    with pytest.raises(ValueError, match="vtk_unstructured"):
        capabilities.case_writer.renderer_for("vtk_unstructured")


def test_the_declared_renderer_is_the_one_asked():
    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Renderer())
    assert capabilities.case_writer.renderer_for("openfoam_dictionary") == "org.format"


def test_resolution_must_not_touch_the_filesystem(tmp_path, monkeypatch):
    """A dry run is non-destructive only if resolution is pure. The adapter
    that resolves is the one with a case in front of it, so this is enforced,
    not trusted."""
    opened = []
    real_open = Path.open

    def _tracking_open(self, *args, **kwargs):
        opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _tracking_open)

    class _ImpureAdapter:
        plugin_id = "org.impure"

        def get_profile(self):
            return _Profile()

        def resolve_case_mutation(self, request, *, driver_context):
            (Path(request.case_root) / "probe").open("w").close()
            return None

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_ImpureAdapter())
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=tmp_path, adapter_id="org.impure",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    with pytest.raises(ValueError, match="pure"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_adapter_with_no_writer_hooks_refuses_by_name():
    """Not neutral. An empty resolution silently produces a case that is not
    the one that was asked for -- the same reason
    `SweepMaterializerCapability` refuses rather than defaulting."""

    class _Bare:
        plugin_id = "org.bare"

        def get_profile(self):
            return _Profile()

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_Bare())
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=Path("/tmp/case"), adapter_id="org.bare",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    with pytest.raises(ValueError, match="org.bare"):
        capabilities.case_writer.resolve(request, driver_context=object())


def test_an_unsupported_mode_is_refused_by_the_adapter_not_the_type():
    """`CaseMutationRequest` refuses an unknown mode. An adapter refusing a
    known mode it does not support is a different, equally explicit answer --
    and it names the modes it does support."""

    class _PatchOnly(_Renderer):
        plugin_id = "org.patch_only"

        def get_supported_mutation_modes(self):
            return frozenset({"clone_and_patch"})

        def resolve_case_mutation(self, request, *, driver_context):
            raise AssertionError("must be refused before reaching the adapter")

    capabilities = plugin_capabilities.adapt_plugin_capabilities(_PatchOnly())
    request = case_write.CaseMutationRequest(
        mode="synthesize", case_root=Path("/tmp/case"), adapter_id="org.patch_only",
        workflow="w", source_artifacts=("mesh.vtu",), parameters=(),
        requested_by="test",
    )
    with pytest.raises(ValueError, match="clone_and_patch"):
        capabilities.case_writer.resolve(request, driver_context=object())
```

- [ ] **Step 2: Run to verify it fails, then implement**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_writer_capability.py -v
```

Expected: FAIL throughout — no `case_writer` capability.

Implement in three places.

**`core/case_write.py`** — the resolution result:

```python
@dataclass(frozen=True)
class ResolvedMutation:
    """The semantic owner's answer: concrete addresses and expected effects.

    Pure. Produced without reading the case, so a dry run costs nothing and
    changes nothing. The renderer reads; this does not.
    """

    request: CaseMutationRequest
    targets: tuple[Mapping[str, Any], ...]
    preconditions: tuple[Precondition, ...]
    expected_effects: tuple[str, ...]
    semantic_owner_id: str

    def formats(self) -> tuple[str, ...]:
        return tuple(sorted({str(target["format"]) for target in self.targets}))
```

**`core/plugin_interface.py`** — the three protocol members, with docstrings
that say what is pure and what is not, since the capability-seam table is
generated from them:

```python
    # -- CaseWriterCapability -------------------------------------------------
    def resolve_case_mutation(
        self, request: Any, *, driver_context: Any,
    ) -> Any:
        """Resolve a mutation request into concrete addresses and effects.

        The semantic owner's hook: which parameters apply, what they mean,
        which document and key each lands in, and what the edit is expected to
        change. Returns a ``ResolvedMutation``.

        **Pure.** Must not read or write the filesystem. A dry run's promise of
        costing nothing rests on this, and core enforces it rather than
        trusting it. Raise a ``ValueError`` naming the supported modes to
        refuse a mode this adapter does not support. Absent -> this adapter
        authors no case inputs."""
        ...

    def get_supported_mutation_modes(self) -> "frozenset[str]":
        """Which creation modes this adapter supports.

        Adapters differ and are meant to: cardiacCore preprocessing patches
        declared dictionaries, cardiacFoam synthesizes a case from a catalog.
        Absent -> every mode the adapter's ``resolve_case_mutation`` accepts."""
        ...

    def get_rendered_formats(self) -> "frozenset[str]":
        """File formats this provider renders. Exactly one declarer per format.

        Composition refuses a stack where two providers claim one format: the
        bytes reaching disk would otherwise depend on composition order.
        Absent -> this provider renders nothing."""
        ...

    def render_case_files(
        self, resolved: Any, *, snapshot_root: "Path", driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        """Render complete proposed file contents, in this provider's formats.

        The format owner's hook. **Reads** the case -- it must, to patch an
        existing file -- and writes nothing outside ``snapshot_root``, an
        isolated copy core provides. Returns ``RenderedFile`` objects with
        complete bytes; core commits them and this hook does not.

        ``execution_env`` is the selected runtime, for a renderer that must
        resolve includes or evaluate a directive to know what it is editing.
        Declare every file read through it as a precondition on the
        ``ResolvedMutation``, including files that were *absent* where their
        presence would change which file is selected. Absent -> this provider
        renders nothing."""
        ...
```

**`core/plugin_capabilities.py`** — the capability and its adapter:

```python
class CaseWriterCapability(Protocol):
    """How a framework-authored case mutation becomes reviewable bytes.

    Three answers from up to three owners. ``resolve`` is the selected
    adapter's and is pure. ``render`` belongs to whichever provider declares
    the file's format, one declarer per format. Committing is core's and is not
    here at all -- see :mod:`omnidriver.core.case_transaction`.

    The fallback cannot be neutral. An empty resolution silently yields a case
    that is not the one requested, so an adapter without these hooks is refused
    by name.

    :adapts: resolve_case_mutation, get_supported_mutation_modes, get_rendered_formats, render_case_files
    :consumed-by: omnidriver/core/case_transaction.py
    :fallback: none
    :status: optional-refusing
    """

    def resolve(self, request: Any, *, driver_context: Any) -> Any: ...
    def supported_modes(self) -> frozenset[str]: ...
    def renderer_for(self, file_format: str) -> str: ...
    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]: ...


@dataclass(frozen=True)
class _CaseWriterAdapter:
    plugin: "SolverPlugin"

    def supported_modes(self) -> frozenset[str]:
        hook = getattr(self.plugin, "get_supported_mutation_modes", None)
        if callable(hook):
            return frozenset(hook())
        from .case_write import MUTATION_MODES

        return MUTATION_MODES

    def resolve(self, request: Any, *, driver_context: Any) -> Any:
        hook = getattr(self.plugin, "resolve_case_mutation", None)
        if not callable(hook):
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} declares no "
                f"resolve_case_mutation(); it authors no case inputs, and an "
                f"empty resolution would silently produce a case that is not "
                f"the one requested"
            )
        supported = self.supported_modes()
        if request.mode not in supported:
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} does not support creation "
                f"mode {request.mode!r}; it supports {sorted(supported)}"
            )
        resolved = _resolved_purely(hook, request, driver_context=driver_context)
        return resolved

    def renderer_for(self, file_format: str) -> str:
        hook = getattr(self.plugin, "get_rendered_formats", None)
        declared = frozenset(hook()) if callable(hook) else frozenset()
        if file_format not in declared:
            raise ValueError(
                f"no provider in this stack renders {file_format!r}; declared "
                f"formats are {sorted(declared)}. A file whose format nobody "
                f"renders stops the plan rather than being dropped from it"
            )
        return self.plugin.plugin_id

    def render(
        self, resolved: Any, *, snapshot_root: Any, driver_context: Any,
        execution_env: Any | None = None,
    ) -> tuple[Any, ...]:
        hook = getattr(self.plugin, "render_case_files", None)
        if not callable(hook):
            raise ValueError(
                f"provider {self.plugin.plugin_id!r} declares no render_case_files()"
            )
        return tuple(hook(
            resolved, snapshot_root=snapshot_root,
            driver_context=driver_context, execution_env=execution_env,
        ))
```

`_resolved_purely` is the enforcement the test demands. Write it as a small
helper in the same module that patches nothing globally — the least invasive
form is to run the hook with `case_root` replaced by a path guard object, but a
simpler and sufficient check is to compare a directory listing of `case_root`
before and after:

```python
def _resolved_purely(hook, request, *, driver_context):
    """Run a resolution hook and refuse one that touched the case.

    Resolution is declared pure, and a dry run's promise rests on that. This
    detects creation and deletion, not in-place modification of an existing
    file -- state that limit rather than implying a stronger guarantee. A
    renderer is where filesystem reads belong.
    """
    from pathlib import Path as _Path

    root = _Path(request.case_root)
    before = {p for p in root.rglob("*")} if root.is_dir() else set()
    resolved = hook(request, driver_context=driver_context)
    after = {p for p in root.rglob("*")} if root.is_dir() else set()
    if before != after:
        changed = sorted(str(p) for p in before ^ after)
        raise ValueError(
            f"resolve_case_mutation() must be pure; "
            f"{request.adapter_id!r} changed {changed}"
        )
    return resolved
```

Then add `case_writer: CaseWriterCapability` to `PluginCapabilities` and
`case_writer=_CaseWriterAdapter(plugin)` to its constructor, beside the existing
`override_scopes=` line.

**`core/provider_stack.py`** — classify the four new members and add the
one-declarer check. Read the existing `_SHAPE` table and the classification
comment block before adding entries; an unclassified member is an import-time
error by design:

```python
    "resolve_case_mutation": "single",
    "get_supported_mutation_modes": "set",
    "get_rendered_formats": "set",
    "render_case_files": "sequence",
```

`render_case_files` is `sequence` because a plan can span two formats and each
renderer answers for its own; core selects by `renderer_for` and never merges
two renderings of one path — `CaseWritePlan` refuses that in Task 2. Add a
check modelled on `_check_case_file_declarers`:

```python
def _check_format_declarers(ordered) -> None:
    """One declarer per rendered format, always.

    Two providers claiming `openfoam_dictionary` makes the bytes that reach
    disk depend on composition order, which is the same defect
    `_check_case_file_declarers` refuses for case files.
    """
    declared_by: dict[str, str] = {}
    for provider in ordered:
        hook = getattr(provider, "get_rendered_formats", None)
        for file_format in (hook() if callable(hook) else ()):
            if file_format in declared_by:
                raise ValueError(
                    f"format {file_format!r} is rendered by both "
                    f"{declared_by[file_format]!r} and {provider.plugin_id!r}; "
                    f"one format has one renderer, and tolerating two makes the "
                    f"bytes on disk depend on composition order"
                )
            declared_by[file_format] = provider.plugin_id
```

and call it from `compose` alongside the three existing eager checks.

- [ ] **Step 3: Regenerate the seam table, run, commit**

```bash
python3 scripts/export-capability-seams.py
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_writer_capability.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
git add packages/omnidriver/src/omnidriver/core/case_write.py packages/omnidriver/src/omnidriver/core/plugin_interface.py packages/omnidriver/src/omnidriver/core/plugin_capabilities.py packages/omnidriver/src/omnidriver/core/provider_stack.py packages/omnidriver/tests/core/test_case_writer_capability.py ARCHITECTURE.md
git commit -m "feat(core): CaseWriterCapability with explicit format ownership

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

`ARCHITECTURE.md` carries the generated capability-seam table; confirm with
`git status` that regeneration changed it before staging it.

---

## Task 4: Value kinds and dynamic-path bindings

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py`
- Create: `packages/omnidriver/tests/core/test_value_kinds_and_bindings.py`

**Interfaces:**
- Consumes: `ParameterAssignment.value_kind` and `.allowed_bindings` (Task 1).
- Produces: `VALUE_KINDS` — a closed vocabulary of generic value *shapes*;
  `DictEntry.allowed_bindings: Mapping[str, tuple[str, ...]]`;
  `validate_value_shape(kind, value) -> tuple[str, ...]` returning reason
  strings, empty when the value fits. Adapters call it; the renderer formats.

**Generic shapes only.** A vector, tensor, dimensioned quantity, enum,
dictionary and list cannot be squeezed into scalar-or-string, and that is what
this vocabulary fixes. It does **not** carry units, ranges or physical meaning:
those are the adapter's, supplied only where domain evidence justifies them.
`DictEntry.unit` already exists for the adapter to fill; core does not check it
against anything.

- [ ] **Step 1: Read what already exists**

```bash
sed -n '1,60p' packages/omnidriver/src/omnidriver/core/contracts/dictionary.py
grep -rn "value_kind=" packages/ | sed 's/.*value_kind=//' | cut -d, -f1 | sort | uniq -c | sort -rn
```

`DictEntry` already has `value_kind`, `dynamic_path`, `unit`, `typical_value`,
`enum_values` and applicability maps. Extend it. Do not create a second
registry — the roadmap is explicit that existing dictionary/catalog types come
first.

The second command lists every kind currently in use. Your closed vocabulary
must cover all of them or the task's first step is a migration, not a
tightening. Record the list in your report.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver/tests/core/test_value_kinds_and_bindings.py`:

```python
"""Generic value shapes, closed; physical meaning, elsewhere.

`value_kind` defaulted to the string "literal" and was validated only by an
adapter's own `_check_value`, which accepted any non-empty string for a vector
and `nan` for a scalar (audit finding S1). Closing the vocabulary in core gives
every adapter one shape check; it does not give core an opinion about
conductivity.

`dynamic_path` was a bare boolean: a path had placeholders or it did not, and
nothing said which values a placeholder may take. That is why `banana` passed
as a ventricle.
"""

import pytest

from omnidriver.core.contracts import dictionary


def test_the_vocabulary_is_closed():
    with pytest.raises(ValueError, match="literal"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="literal",
        )


@pytest.mark.parametrize("kind", sorted(dictionary.VALUE_KINDS))
def test_every_declared_kind_is_accepted(kind):
    assert dictionary.DictEntry(
        driver_path="$A.x", description="", value_kind=kind,
    ).value_kind == kind


@pytest.mark.parametrize("kind,value", [
    ("scalar", 0.1),
    ("integer", 3),
    ("boolean", True),
    ("word", "TT06"),
    ("vector3", (1.0, 2.0, 3.0)),
    ("tensor9", tuple(float(i) for i in range(9))),
    ("dimensioned", {"value": 1.0, "dimensions": (0, 2, -1, 0, 0, 0, 0)}),
    ("list", (1.0, 2.0)),
    ("dictionary", {"gNa": 1.0}),
])
def test_a_well_shaped_value_passes(kind, value):
    assert dictionary.validate_value_shape(kind, value) == ()


@pytest.mark.parametrize("kind,value,reason", [
    ("scalar", float("nan"), "finite"),
    ("scalar", float("inf"), "finite"),
    ("scalar", "0.1", "number"),
    ("integer", 1.5, "integer"),
    ("integer", True, "integer"),
    ("boolean", 1, "boolean"),
    ("word", "", "empty"),
    ("word", "two words", "whitespace"),
    ("vector3", (1.0, 2.0), "three"),
    ("vector3", (1.0, 2.0, float("nan")), "finite"),
    ("vector3", "not a vector", "three"),
    ("tensor9", tuple(range(6)), "nine"),
    ("dimensioned", {"value": 1.0}, "dimensions"),
    ("dimensioned", {"value": 1.0, "dimensions": (0, 2)}, "seven"),
    ("list", 1.0, "sequence"),
    ("dictionary", [("a", 1)], "mapping"),
])
def test_a_badly_shaped_value_is_reported_with_a_reason(kind, value, reason):
    reasons = dictionary.validate_value_shape(kind, value)
    assert reasons, f"{kind} accepted {value!r}"
    assert any(reason in r for r in reasons), reasons


def test_a_dynamic_path_declares_its_allowed_bindings():
    entry = dictionary.DictEntry(
        driver_path="$PURKINJE_TREE.<ventKey>.seed", description="",
        value_kind="vector3", dynamic_path=True,
        allowed_bindings={"<ventKey>": ("lv", "rv")},
    )
    assert entry.allowed_bindings["<ventKey>"] == ("lv", "rv")


def test_a_dynamic_path_without_declared_bindings_is_refused():
    """A placeholder whose values nobody declared is a placeholder anything
    matches -- which is how `banana` became a ventricle."""
    with pytest.raises(ValueError, match="<ventKey>"):
        dictionary.DictEntry(
            driver_path="$PURKINJE_TREE.<ventKey>.seed", description="",
            value_kind="vector3", dynamic_path=True,
        )


def test_declared_bindings_on_a_static_path_are_refused():
    with pytest.raises(ValueError, match="dynamic_path"):
        dictionary.DictEntry(
            driver_path="$A.x", description="", value_kind="scalar",
            allowed_bindings={"<ventKey>": ("lv",)},
        )


def test_a_placeholder_in_the_path_but_not_in_the_bindings_is_refused():
    with pytest.raises(ValueError, match="<layer>"):
        dictionary.DictEntry(
            driver_path="$A.<ventKey>.<layer>.x", description="",
            value_kind="scalar", dynamic_path=True,
            allowed_bindings={"<ventKey>": ("lv", "rv")},
        )


def test_core_asserts_nothing_about_units():
    """`unit` is the adapter's, supplied where domain evidence justifies it.
    Core carries it and checks nothing against it."""
    entry = dictionary.DictEntry(
        driver_path="$A.x", description="", value_kind="scalar", unit="furlong",
    )
    assert entry.unit == "furlong"
    assert dictionary.validate_value_shape("scalar", 0.1) == ()
```

- [ ] **Step 3: Run to verify it fails, then implement**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_value_kinds_and_bindings.py -v
```

Expected: FAIL — `VALUE_KINDS`, `validate_value_shape` and `allowed_bindings` do
not exist, and `"literal"` is still the default.

In `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py`:

```python
import math
from collections.abc import Mapping as _Mapping, Sequence as _Sequence
from numbers import Integral, Real

#: Generic value SHAPES, closed. A shape says how a value is built, never what
#: it means: no units, no ranges, no physical interpretation. Those are the
#: adapter's and are supplied only where domain evidence justifies them.
#:
#: Closed 2026-09-22. The previous default was the string ``"literal"``, which
#: said nothing and was checked by nothing, so an adapter's own value check was
#: the only barrier -- and it accepted `nan` for a scalar and any non-empty
#: string for a vector (audit finding S1).
VALUE_KINDS = frozenset({
    "scalar", "integer", "boolean", "word", "enum",
    "vector3", "tensor9", "dimensioned", "list", "dictionary",
})

_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_]*>")


def _finite(value) -> bool:
    return isinstance(value, Real) and math.isfinite(float(value))


def validate_value_shape(kind: str, value) -> tuple[str, ...]:
    """Reasons a value does not fit a declared shape; empty when it fits.

    Returns reasons rather than raising, so a caller can report every bad
    parameter in one pass instead of the first one.
    """
    if kind not in VALUE_KINDS:
        return (f"unknown value kind {kind!r}; known kinds are {sorted(VALUE_KINDS)}",)
    if kind == "scalar":
        if isinstance(value, bool) or not isinstance(value, Real):
            return ("must be a number",)
        return () if _finite(value) else ("must be a finite number",)
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, Integral):
            return ("must be an integer",)
        return ()
    if kind == "boolean":
        return () if isinstance(value, bool) else ("must be a boolean",)
    if kind in {"word", "enum"}:
        if not isinstance(value, str) or not value:
            return ("must be a non-empty word",)
        return () if value.split() == [value] else ("must contain no whitespace",)
    if kind in {"vector3", "tensor9"}:
        width = 3 if kind == "vector3" else 9
        spelled = "three" if width == 3 else "nine"
        if isinstance(value, str) or not isinstance(value, _Sequence):
            return (f"must be {spelled} numbers",)
        if len(value) != width:
            return (f"must be {spelled} numbers, not {len(value)}",)
        bad = [i for i, item in enumerate(value) if isinstance(item, bool) or not _finite(item)]
        return (f"components {bad} must be finite numbers",) if bad else ()
    if kind == "dimensioned":
        if not isinstance(value, _Mapping):
            return ("must be a mapping with value and dimensions",)
        reasons = []
        if "value" not in value:
            reasons.append("missing 'value'")
        dimensions = value.get("dimensions")
        if dimensions is None:
            reasons.append("missing 'dimensions'")
        elif not isinstance(dimensions, _Sequence) or len(dimensions) != 7:
            reasons.append("'dimensions' must be seven exponents")
        return tuple(reasons)
    if kind == "list":
        if isinstance(value, (str, bytes)) or not isinstance(value, _Sequence):
            return ("must be a sequence",)
        return ()
    if kind == "dictionary":
        return () if isinstance(value, _Mapping) else ("must be a mapping",)
    raise AssertionError(f"unhandled value kind {kind!r}")
```

Then change `DictEntry`: replace `value_kind: str = "literal"` with
`value_kind: str = "word"`, add
`allowed_bindings: dict[str, tuple[str, ...]] = field(default_factory=dict)`,
and add a `__post_init__` that refuses an unknown kind, a `dynamic_path` entry
whose placeholders are not all declared, and declared bindings on a static path.

Changing the default from `"literal"` to `"word"` will break every entry that
relied on it. That is the point of closing the vocabulary — but it is a real
migration:

```bash
grep -rn "DictEntry(" packages/ | wc -l
grep -rln "value_kind" packages/*/src/
```

Run the full suite and fix each declaration to its actual shape. Do not add
`"literal"` back. If an entry's real shape is genuinely unclear, say so in your
report and leave it as `"word"` with a `# TODO` naming the document — one
honest unknown is better than a vocabulary with an escape hatch in it.

- [ ] **Step 4: Run, regenerate, commit**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_value_kinds_and_bindings.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
python3 scripts/export-capability-seams.py --check
git add packages/omnidriver/src/omnidriver/core/contracts/dictionary.py packages/omnidriver/tests/core/test_value_kinds_and_bindings.py
git commit -m "feat(core): close the value-kind vocabulary and declare dynamic bindings

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

Include every catalog file you migrated in the stage, and list them in your
report — the count will be large and the reviewer needs to see it.

- [ ] **Step 5: G1 exit check**

Before moving to G2, prove the contract is describable by three different
providers:

```bash
/tmp/od311/bin/python - <<'PY'
# `discover_plugins()` returns dict[str, EntryPoint] -- iterating it yields
# name strings -- and `load_discovered_plugin(name)` returns a DriverContext
# whose `.providers` holds the actual provider objects. Corrected 2026-09-22
# after batch G0-A hit the earlier, wrong form.
from omnidriver.core.plugin_discovery import discover_plugins, load_discovered_plugin
providers = {}
for name in discover_plugins():
    for provider in load_discovered_plugin(name).providers:
        providers[provider.plugin_id] = provider
for plugin_id, plugin in sorted(providers.items()):
    modes = getattr(plugin, "get_supported_mutation_modes", lambda: None)()
    formats = getattr(plugin, "get_rendered_formats", lambda: frozenset())()
    print(f"{plugin_id}: modes={sorted(modes) if modes else 'all'} formats={sorted(formats)}")
PY
grep -rn "openfoam\|foamlib\|dictionary syntax" packages/omnidriver/src/omnidriver/core/case_write.py packages/omnidriver/src/omnidriver/core/case_transaction.py 2>/dev/null
```

Expected: each installed provider prints its declared modes and formats; the
grep finds nothing in core. Record both outputs in the Status table as G1's exit
evidence.

---

### Stale snippets in Tasks 5–7, corrected 2026-09-23

Batch P2-F found four places where these tasks' illustrative code predates the
R2 contract fixes. The prose is still right; the snippets are not. Fix them as
you go rather than working around them:

* `CaseMutationRequest(..., parameters=())` for a `clone_and_patch` request is
  now refused — R2 finding 7 made that mode require at least one parameter, on
  the grounds that a patch patching nothing is not a mutation. Test helpers
  need a real parameter.
* `value_kind="dictionary"` appears in Task 2's and Task 7's snippets. Task 4
  deleted that kind; nothing used it. `dimensioned_scalar` is the mapping-shaped
  kind. Do **not** re-add `dictionary` to `VALUE_KINDS`.
* `CaseWritePlan.from_json(payload, contents={...})` — see the superseding note
  in Task 2. The signature takes `payload` only.
* Task 7's `stale_build` snippet calls a helper `_installed_providers()` that
  does not exist. Build one locally, and make the limit assertion name a
  specific capability whose winner is real while its digest is a placeholder —
  asserting merely that *some* capability is placeheld is trivially true for
  any incomplete provider and proves nothing.

## Gate G2 — prove one write channel

Exit evidence: the public plan → diff → commit → validate path passes
adversarial transaction checks, and post-write unknown evidence blocks the
appropriate execution.

---

## Task 5: The core transaction executor

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/case_transaction.py`
- Create: `packages/omnidriver/tests/core/test_case_transaction.py`

**Interfaces:**
- Consumes: `CaseWritePlan`, `RenderedFile`, `Precondition`, `CaseWriteRecord`
  (Tasks 1–2); the capability from Task 3.
- Reuses, without reimplementing: `remediation_transaction._atomic_write_bytes`,
  `._fsync_directory`, `._snapshot_targets`; `attempt_lease.acquire_case_lease`,
  `.acquire_case_staging_lease`.
- Produces: `commit_case_write(plan, *, driver_context, execution_env) -> CaseWriteRecord`;
  `TRANSACTION_STATES`; `CaseTransactionError`. This is **the only function in
  the repository that writes a framework-authored case input** once G3 closes.

- [ ] **Step 1: Read the machinery you are reusing**

```bash
grep -n "^def \|^class " packages/omnidriver/src/omnidriver/core/runtime/remediation_transaction.py
grep -n "^def \|^class " packages/omnidriver/src/omnidriver/core/runtime/attempt_lease.py
sed -n '/def _atomic_write_bytes/,/^def /p' packages/omnidriver/src/omnidriver/core/runtime/remediation_transaction.py
sed -n '/def acquire_case_lease/,/^def /p' packages/omnidriver/src/omnidriver/core/runtime/attempt_lease.py
```

`_atomic_write_bytes` already handles mode preservation and `_fsync_directory`
already handles durability. If either does not do what this task needs, say why
in your report before writing a second one.

Note the constraint the roadmap places on extraction: **a shared abstraction
needs two demonstrated consumers.** Remediation is one; this channel becomes the
second. Do not move code out of `remediation_transaction.py` in this task —
import from it, and extract in Task 12 once both consumers exist and their needs
are known.

- [ ] **Step 2: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_transaction.py`:

```python
"""Commit is core's, and it is recoverable.

Per-file atomic replacement plus a journal. That gives: recovery from an
interruption, rollback of a partially applied plan, and a framework reader
never seeing a half-written file. It does NOT give simultaneous atomic
visibility of several files to an arbitrary outside process -- proposal defect
W2 described it as an atomic case write, and it is not one. The tests below
assert what is true.
"""

from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write


def _plan(case_root: Path, files, preconditions=()):
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.a",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    return case_write.CaseWritePlan(
        request=request, files=tuple(files), preconditions=tuple(preconditions),
        semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )


def _rendered(path, content, *, exists_before=False, before_digest=None, mode=None):
    return case_write.RenderedFile(
        path=path, content=content, mode=mode, exists_before=exists_before,
        before_digest=before_digest, renderer_id="org.r", format="f",
    )


def test_a_plan_writes_every_file_and_records_their_digests(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"one\n"),
        _rendered("system/b", b"two\n"),
    ])
    record = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None,
    )
    assert (tmp_path / "constant" / "a").read_bytes() == b"one\n"
    assert (tmp_path / "system" / "b").read_bytes() == b"two\n"
    assert record.status == "committed"
    assert {entry["path"] for entry in record.committed} == {"constant/a", "system/b"}


def test_an_overwritten_file_is_restored_when_a_later_write_fails(tmp_path):
    (tmp_path / "constant").mkdir()
    existing = tmp_path / "constant" / "a"
    existing.write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    plan = _plan(tmp_path, [
        _rendered("constant/a", b"replaced\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert existing.read_bytes() == b"original\n"
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_newly_created_file_is_removed_on_rollback(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("constant/new", b"one\n"),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert not (tmp_path / "constant" / "new").exists()
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_directory_created_only_for_the_transaction_is_removed_on_rollback(tmp_path):
    plan = _plan(tmp_path, [
        _rendered("brand/new/dir/file", b"one\n"),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert not (tmp_path / "brand").exists()
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_file_mode_is_preserved_across_replacement(tmp_path):
    (tmp_path / "constant").mkdir()
    script = tmp_path / "constant" / "Allrun"
    script.write_bytes(b"#!/bin/sh\n")
    script.chmod(0o755)
    before = case_write._digest_bytes(b"#!/bin/sh\n")
    plan = _plan(tmp_path, [
        _rendered("constant/Allrun", b"#!/bin/sh\necho hi\n",
                  exists_before=True, before_digest=before, mode=0o755),
    ])
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert script.stat().st_mode & 0o777 == 0o755


def test_a_failed_precondition_refuses_before_any_write(tmp_path):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"changed since planning\n")
    plan = _plan(
        tmp_path,
        [_rendered("constant/a", b"new\n", exists_before=True, before_digest="a" * 64)],
        preconditions=[case_write.Precondition(
            kind="file", target="constant/a", digest="a" * 64, must_be_absent=False,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="constant/a"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert (tmp_path / "constant" / "a").read_bytes() == b"changed since planning\n"


def test_an_absence_precondition_that_no_longer_holds_refuses(tmp_path):
    """A file appearing at a higher-priority include location changes which
    file the run reads (audit finding F2). Its absence was a precondition."""
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "shadow").write_bytes(b"appeared\n")
    plan = _plan(
        tmp_path, [_rendered("constant/a", b"new\n")],
        preconditions=[case_write.Precondition(
            kind="absence", target="site/shadow", digest=None, must_be_absent=True,
        )],
    )
    with pytest.raises(case_transaction.CaseTransactionError, match="site/shadow"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_a_path_escaping_the_case_is_refused_at_commit_too(tmp_path):
    """`RenderedFile` refuses it at construction. Commit checks again against
    the resolved real path, because a symlink can move a legal path outside."""
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "escape").symlink_to(outside / "target")
    plan = _plan(tmp_path, [_rendered("constant/escape", b"x\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="symlink"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_a_second_attempt_under_a_held_lease_is_refused(tmp_path):
    from omnidriver.core.runtime.attempt_lease import acquire_case_lease

    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with acquire_case_lease(tmp_path):
        with pytest.raises(case_transaction.CaseTransactionError, match="lease"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )


def test_the_journal_is_removed_after_a_clean_commit(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)
    assert not case_transaction.pending_transaction(tmp_path)
```

- [ ] **Step 3: Run to verify it fails, then implement**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_transaction.py -v
```

Expected: FAIL — no module `case_transaction`.

Create `packages/omnidriver/src/omnidriver/core/case_transaction.py`. Its
module docstring must state the guarantee honestly:

```python
"""Commit a reviewed plan's bytes, recoverably.

What this guarantees:

* Each file is replaced atomically, so a framework reader never observes a
  partially written file.
* A journal records every before-image before any write, so an interrupted
  transaction is recoverable and a failed one is rolled back: overwritten files
  are restored, created files are removed, and directories created only for the
  transaction are removed.
* A case lease serializes this framework's attempts against one case.

What this does NOT guarantee, and must not be documented as guaranteeing
(proposal defect W2):

* Simultaneous atomic visibility of several files to an arbitrary outside
  process. A process reading the case during a multi-file commit can observe a
  mixed state. The supported reader model is: this framework's own readers, and
  outside readers that read after the transaction completes.
* Control over writers outside the framework. A lease coordinates framework
  attempts. A user editing a dictionary in an editor is not prevented -- they
  are detected at precondition recheck as drift, which refuses the commit.
* Durability beyond what ``fsync`` on the file and its directory provides on
  the host filesystem. Network filesystems that reorder or defer are out of the
  supported profile; say so rather than assuming POSIX semantics hold.
"""
```

Name the three private helpers Task 6 builds on, so they exist before their
tests patch them:

```python
def _write_journal(case_root: Path, transaction: Mapping[str, Any]) -> None:
    """Persist the transaction head atomically, before the first file write."""


def _write_one(target: Path, rendered: "RenderedFile") -> dict[str, Any]:
    """Replace one file atomically and return its committed entry."""


def _restore_one(target: Path, before_image: Mapping[str, Any]) -> None:
    """Put one file back the way the journal recorded it."""
```

Then implement `commit_case_write` in this order, which is the order the
roadmap's lifecycle step 5 and 6 require:

1. Acquire `acquire_case_lease(plan.request.case_root)`; a held lease refuses.
2. Refuse if `pending_transaction(case_root)` returns an unrecovered journal.
3. Recheck every `Precondition` against the filesystem. Any failure refuses
   before a single byte is written, naming the target.
4. Resolve each `RenderedFile.path` against the case root and refuse a symlink
   or a resolved path outside it — again, even though `RenderedFile` checked the
   spelling, because a symlink moves a legal spelling outside.
5. Write the journal — transaction id, plan digest, and every before-image —
   through `_atomic_write_bytes` and `_fsync_directory`, before the first write.
6. Write each file through `_atomic_write_bytes`, preserving mode.
7. On any failure, roll back from the journal and raise `CaseTransactionError`
   with the original as `__cause__`.
8. On success, remove the journal and return a `CaseWriteRecord`.

Declare the legal states explicitly rather than leaving them implicit:

```python
#: The transaction's authoritative head is the journal file. Legal states and
#: who may advance them:
#:
#: ``planning``   no journal. Nothing has been written.
#: ``preparing``  journal written, no file replaced yet. Recovery: delete the
#:                journal; nothing was changed.
#: ``applying``   at least one file replaced. Recovery: restore every
#:                before-image in the journal, then delete it.
#: ``committed``  every file replaced, journal removed. Terminal.
#: ``rolled_back`` recovery completed. Terminal.
#:
#: There is one head and one recovery owner: whoever holds the case lease.
#: A journal in ``applying`` blocks dispatch until recovery runs -- an
#: unrecovered case is not a case whose inputs are known.
TRANSACTION_STATES = ("planning", "preparing", "applying", "committed", "rolled_back")
```

- [ ] **Step 4: Run, then commit**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_transaction.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
python3 scripts/check-import-boundaries.py
git add packages/omnidriver/src/omnidriver/core/case_transaction.py packages/omnidriver/tests/core/test_case_transaction.py
git commit -m "feat(core): the case-write transaction executor

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

The chmod-based failure-injection tests will not behave as written when run as
root. Guard them with `pytest.mark.skipif(os.geteuid() == 0, ...)` and say so —
a test that silently passes because it could not fail is worse than a skip that
says why.

---

## Task 6: Recovery, replay and staleness

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/case_transaction.py`
- Modify: `packages/omnidriver/src/omnidriver/core/case_write.py` — implement `CaseWritePlan.from_json`
- Create: `packages/omnidriver/tests/core/test_case_transaction_recovery.py`

**Interfaces:**
- Consumes: Task 5's journal and states.
- Produces: `recover_case_transaction(case_root) -> CaseWriteRecord | None`;
  `pending_transaction(case_root) -> Mapping | None`;
  `commit_case_write(..., transaction_id=None)` — passing an id that matches a
  completed transaction returns its record rather than reapplying.

This task answers the question the roadmap raises as a hard requirement:
"retrying after an uncertain response must recover the existing transaction or
refuse drift, not blindly reapply."

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_transaction_recovery.py`:

```python
"""An interrupted or retried transaction has one correct outcome.

Three situations, three answers:

* Interrupted mid-apply -> recovery restores the before-images and the case is
  back where it started. Until recovery runs, dispatch is blocked: a case whose
  inputs are half-written is not a case whose inputs are known.
* Retried after an uncertain response, same transaction id -> the existing
  record is returned. Reapplying would write over a case that may have moved on.
* Retried with a plan whose preconditions no longer hold -> refused as stale,
  naming what changed.
"""

import json
from pathlib import Path

import pytest

from omnidriver.core import case_transaction, case_write


def _plan(case_root: Path, files, preconditions=()):
    request = case_write.CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id="org.a",
        workflow="w", source_artifacts=(), parameters=(), requested_by="test",
    )
    return case_write.CaseWritePlan(
        request=request, files=tuple(files), preconditions=tuple(preconditions),
        semantic_owner_id="org.a", stack_identity="0" * 64,
        created_at="2026-09-22T00:00:00Z",
    )


def _rendered(path, content, **kwargs):
    return case_write.RenderedFile(
        path=path, content=content, mode=kwargs.get("mode"),
        exists_before=kwargs.get("exists_before", False),
        before_digest=kwargs.get("before_digest"),
        renderer_id="org.r", format="f",
    )


def test_an_interrupted_transaction_is_recoverable(tmp_path, monkeypatch):
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    calls = {"n": 0}
    real = case_transaction._write_one

    def _die_after_first(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise KeyboardInterrupt("simulated interruption")
        return real(*args, **kwargs)

    monkeypatch.setattr(case_transaction, "_write_one", _die_after_first)
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/b", b"two\n"),
    ])
    with pytest.raises(KeyboardInterrupt):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)

    # The journal survived; the case has not been restored yet.
    assert case_transaction.pending_transaction(tmp_path)

    record = case_transaction.recover_case_transaction(tmp_path)
    assert record.status == "rolled_back"
    assert (tmp_path / "constant" / "a").read_bytes() == b"original\n"
    assert not (tmp_path / "constant" / "b").exists()
    assert not case_transaction.pending_transaction(tmp_path)


def test_an_unrecovered_journal_blocks_a_new_commit(tmp_path):
    (tmp_path / ".omnidriver").mkdir(parents=True, exist_ok=True)
    case_transaction._write_journal(tmp_path, {
        "transaction_id": "t-stuck", "state": "applying",
        "plan_digest": "0" * 64, "before_images": [],
    })
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="t-stuck"):
        case_transaction.commit_case_write(plan, driver_context=object(), execution_env=None)


def test_replaying_a_completed_transaction_returns_its_record(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    first = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    (tmp_path / "constant" / "a").write_bytes(b"someone else edited this\n")
    second = case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-1",
    )
    assert second.transaction_id == first.transaction_id
    assert second.status == "committed"
    # Not reapplied: a retry after an uncertain response must not overwrite a
    # case that moved on.
    assert (tmp_path / "constant" / "a").read_bytes() == b"someone else edited this\n"


def test_a_replay_with_a_different_plan_under_one_id_is_refused(tmp_path):
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    case_transaction.commit_case_write(
        plan, driver_context=object(), execution_env=None, transaction_id="t-2",
    )
    other = _plan(tmp_path, [_rendered("constant/a", b"different\n")])
    with pytest.raises(case_transaction.CaseTransactionError, match="t-2"):
        case_transaction.commit_case_write(
            other, driver_context=object(), execution_env=None, transaction_id="t-2",
        )


def test_a_rollback_that_itself_fails_leaves_the_journal_and_says_so(tmp_path, monkeypatch):
    """The worst case must be loud. A failed rollback leaves a case in an
    unknown state, and the journal is the only record of what it was."""
    (tmp_path / "constant").mkdir()
    (tmp_path / "constant" / "a").write_bytes(b"original\n")
    before = case_write._digest_bytes(b"original\n")

    monkeypatch.setattr(
        case_transaction, "_restore_one",
        lambda *a, **k: (_ for _ in ()).throw(OSError("restore failed")),
    )
    plan = _plan(tmp_path, [
        _rendered("constant/a", b"new\n", exists_before=True, before_digest=before),
        _rendered("constant/unwritable/b", b"two\n"),
    ])
    (tmp_path / "constant" / "unwritable").mkdir()
    (tmp_path / "constant" / "unwritable").chmod(0o500)
    try:
        with pytest.raises(case_transaction.CaseTransactionError, match="rollback"):
            case_transaction.commit_case_write(
                plan, driver_context=object(), execution_env=None,
            )
        assert case_transaction.pending_transaction(tmp_path)
    finally:
        (tmp_path / "constant" / "unwritable").chmod(0o700)


def test_a_persisted_plan_round_trips(tmp_path):
    """`CaseWritePlan.from_json` is implemented here, its first real consumer."""
    plan = _plan(tmp_path, [_rendered("constant/a", b"one\n")])
    payload = json.loads(case_write.canonical_json(plan.to_json()))
    restored = case_write.CaseWritePlan.from_json(payload, contents={
        "constant/a": b"one\n",
    })
    assert restored.plan_digest == plan.plan_digest
```

`from_json` takes a `contents` mapping because `to_json` records content
*digests*, not bytes — a plan carrying a mesh inline is the giant-JSON-payload
failure the roadmap names. The journal stages the bytes; the reader is handed
them. If you find a cleaner split, take it and say why in your report.

- [ ] **Step 2: Run to verify it fails, then implement**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_case_transaction_recovery.py -v
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
```

Implement `recover_case_transaction`, `pending_transaction`, `_write_journal`,
`_write_one`, `_restore_one`, the `transaction_id` replay path, and
`CaseWritePlan.from_json`. Delete the `NotImplementedError` and the paragraph in
Task 2 that promised this.

Wire the unrecovered-journal block into dispatch, reusing G0 Task 8's coverage
gate rather than adding a second one: an unrecovered journal is a required check
reporting `unavailable` for the `case_inputs` stage.

- [ ] **Step 3: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/case_transaction.py packages/omnidriver/src/omnidriver/core/case_write.py packages/omnidriver/tests/core/test_case_transaction_recovery.py docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md
git commit -m "feat(core): transaction recovery, idempotent replay, staleness refusal

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 7: The conformance suite

**Files:**
- Create: `packages/omnidriver/tests/core/test_write_channel_conformance.py`

**Interfaces:**
- Consumes: everything from Tasks 1–6.
- Produces: `CHANNEL_CONFORMANCE_CASES` — a named, enumerated list the suite
  iterates, so a gap is visible as a missing name rather than as absence.

The roadmap enumerates what must be covered before migration. Each line below is
one required case; the suite must have a test per line, named after it.

| # | case |
|---|---|
| 1 | complete plan serialization and identity |
| 2 | no hidden mutable payloads |
| 3 | format-specific patching |
| 4 | repeated edits to one file |
| 5 | missing files |
| 6 | new files |
| 7 | file modes |
| 8 | rollback after injected failure |
| 9 | interrupted recovery |
| 10 | rollback failure |
| 11 | stale input |
| 12 | stale build |
| 13 | changed indirect dependency |
| 14 | replay after an uncertain result |
| 15 | competing attempts |
| 16 | path escape and symlinks |
| 17 | duplicate ownership |
| 18 | post-write evidence unavailable |

- [ ] **Step 1: Enumerate the cases in code, before writing any of them**

```python
#: Every case the write channel must handle before any route migrates onto it.
#: A name here with no test is a visible gap; a case not listed is one nobody
#: decided to leave out. Derived from the 2026-09-22 roadmap §4.
CHANNEL_CONFORMANCE_CASES = (
    "complete_plan_serialization_and_identity",
    "no_hidden_mutable_payloads",
    "format_specific_patching",
    "repeated_edits_to_one_file",
    "missing_files",
    "new_files",
    "file_modes",
    "rollback_after_injected_failure",
    "interrupted_recovery",
    "rollback_failure",
    "stale_input",
    "stale_build",
    "changed_indirect_dependency",
    "replay_after_an_uncertain_result",
    "competing_attempts",
    "path_escape_and_symlinks",
    "duplicate_ownership",
    "post_write_evidence_unavailable",
)


def test_every_conformance_case_has_a_test():
    """The suite's own completeness check."""
    import inspect
    import sys

    module = sys.modules[__name__]
    names = {name for name, _ in inspect.getmembers(module, inspect.isfunction)}
    missing = [
        case for case in CHANNEL_CONFORMANCE_CASES
        if f"test_{case}" not in names
    ]
    assert not missing, f"conformance cases with no test: {missing}"
```

Write this first and watch it fail with all eighteen names. That list is the
task's to-do.

- [ ] **Step 2: Write each case**

Several are already covered by Tasks 5 and 6 — import and reuse rather than
duplicating. The ones that are genuinely new:

- **`format_specific_patching`** — a plan spanning two formats, each rendered by
  its own declarer, committed in one transaction.
- **`repeated_edits_to_one_file`** — two parameters landing in one document.
  `CaseWritePlan` refuses two `RenderedFile`s at one path, so the renderer must
  fold them into one rendering. Assert both values are present in the committed
  bytes, and assert the plan refuses a renderer that returns two.
- **`stale_build`** — the plan's `stack_identity` no longer matches the composed
  stack. Refuse, naming both digests. This is what G0 Task 1 made meaningful:
  before it, the digest varied between processes and this check would have
  refused every valid plan.

  **State its limit in the test's docstring rather than implying a stronger
  one.** Audit finding C4: `build_stack_identity` records a placeholder digest
  for every capability outside the three the single-plugin digest already
  covered, so an editable install whose *implementation* changed with no version
  bump produces the same `stack_identity`. This check therefore catches a
  changed provider set, a changed version, and a changed profile, dictionary
  vocabulary or manifest — and does **not** catch an edited renderer. Write
  that into the test:

  ```python
  def test_stale_build(tmp_path):
      """A plan bound to one stack is refused against another.

      Known limit (audit finding C4, recorded not discovered): most
      capabilities contribute a placeholder digest, so an edited
      implementation in an editable install is invisible here. Binding a plan
      to the implementations actually used needs real content digests, which
      is G4 work. Do not document this as catching an edited renderer.
      """
  ```

  Add a second test asserting the limit itself, so it is measured rather than
  remembered:

  ```python
  def test_the_stack_digest_does_not_yet_bind_renderer_content(tmp_path):
      """Fails when C4 is fixed. That failure is the signal to delete the
      limit note above -- not to relax this assertion."""
      from omnidriver.core.provider_identity import RESOLUTION_PLACEHOLDER
      from omnidriver.core.provider_stack import resolutions, order_providers

      recorded = resolutions(order_providers(_installed_providers()))
      placeheld = [
          capability for capability, (_winner, digest) in recorded.items()
          if digest == RESOLUTION_PLACEHOLDER
      ]
      assert placeheld, (
          "every capability now carries a real content digest; C4 is closed, "
          "so delete this test and the limit note on test_stale_build"
      )
  ```
- **`changed_indirect_dependency`** — an `include` precondition's digest changed
  even though every case file is untouched.
- **`competing_attempts`** — two commits against one case; the second blocks on
  the lease rather than interleaving.
- **`duplicate_ownership`** — two providers declaring one format; composition
  refuses. Reuse Task 3's test rather than rewriting it.
- **`post_write_evidence_unavailable`** — the runtime is absent, so the readback
  returns `unresolved`. The commit succeeds and the **execution** is blocked,
  through G0 Task 8's coverage gate. Assert both halves: the case was written,
  and `is_launchable(...).coverage_ok` is false.

```python
def test_post_write_evidence_unavailable(tmp_path):
    """An unverifiable write is committed and does not dispatch.

    Not the same as refusing the write: offline editing is supported, and a
    case whose values could not be read back is a case nobody has verified.
    The write happens; the run does not.
    """
    ...
    assert (tmp_path / "constant" / "a").exists()
    readiness = is_launchable(
        plan_status="ok",
        simulation_audit=(SimulationAuditItem(
            stage="effective_configuration", status="unavailable",
        ),),
    )
    assert not readiness.launchable
```

- [ ] **Step 3: Run, and run the whole suite**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_write_channel_conformance.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/tests/core/test_write_channel_conformance.py
git commit -m "test(core): the write-channel conformance suite

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 8: Vertical slice A — one patch path

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py`
- Create: `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_rendering.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py`
- Create: `packages/omnidriver-cardiaccore/tests/test_patch_through_the_channel.py`

**Interfaces:**
- Consumes: Tasks 1–7.
- Produces: `CardiacCorePlugin.resolve_case_mutation` for `clone_and_patch`;
  `OpenFOAMEnvironment.get_rendered_formats() -> {"openfoam_dictionary"}` and
  `.render_case_files`. `apply_input_overrides` keeps its public signature and
  routes through `commit_case_write`.

The existing path is `apply_input_overrides` → `update_foam_entry` — a direct
write, no plan, no journal. Migrate it as the first real consumer. **Keep its
public signature.** A caller outside this repository must not break in the same
commit that changes the mechanism underneath it.

- [ ] **Step 1: Characterize the current behaviour first**

Before changing anything, write a test that passes today and must keep passing:

```python
def test_applying_overrides_still_writes_the_same_bytes(tmp_path):
    """Characterization. Captured before the migration, asserted after.

    Not a test of the new channel -- a test that the new channel produces the
    same case the old path did. Semantic parity is what makes a migration a
    migration rather than a rewrite.
    """
    case = _case_with_conductivity_dict(tmp_path)
    apply_input_overrides(case, {"$CARDIAC_CONDUCTIVITY.df": 0.42})
    assert "df" in (case / "system" / "setCardiacConductivityDict").read_text()
    assert "0.42" in (case / "system" / "setCardiacConductivityDict").read_text()
```

Run it now. It must PASS before you start. Record the exact bytes it produces —
the migrated path must produce them too.

- [ ] **Step 2: Write the failing test for the new path**

Create `packages/omnidriver-cardiaccore/tests/test_patch_through_the_channel.py`
with the characterization test above plus:

```python
def test_a_patch_is_planned_before_it_is_written(tmp_path):
    case = _case_with_conductivity_dict(tmp_path)
    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case, adapter_id="org.cardiaccore",
        workflow="preprocessing", source_artifacts=(),
        parameters=(ParameterAssignment(
            qualified_id="$CARDIAC_CONDUCTIVITY.df", owner="org.cardiaccore",
            document="system/setCardiacConductivityDict", key_path=("df",),
            binding={}, value=0.42, value_kind="scalar", source="case",
        ),),
        requested_by="test",
    )
    capabilities = _composed_capabilities()
    resolved = capabilities.case_writer.resolve(request, driver_context=_context())
    assert resolved.formats() == ("openfoam_dictionary",)
    # Nothing written yet.
    assert "0.42" not in (case / "system" / "setCardiacConductivityDict").read_text()


def test_the_plan_names_every_file_it_read(tmp_path):
    """Preconditions cover the complete read dependency set, including
    includes and the absence of a file whose appearance changes selection."""
    ...
    kinds = {p.kind for p in plan.preconditions}
    assert "file" in kinds


def test_a_rolled_back_patch_leaves_the_dictionary_byte_identical(tmp_path):
    case = _case_with_conductivity_dict(tmp_path)
    original = (case / "system" / "setCardiacConductivityDict").read_bytes()
    ...
    assert (case / "system" / "setCardiacConductivityDict").read_bytes() == original


def test_the_public_entry_point_keeps_its_signature(tmp_path):
    import inspect
    from omnidriver.cardiaccore.workflows.overrides import apply_input_overrides

    signature = inspect.signature(apply_input_overrides)
    assert list(signature.parameters) == ["case_root", "overrides"]
```

- [ ] **Step 3: Implement the renderer, then the resolver**

`openfoam/case_rendering.py` is the **only** new place dictionary syntax appears
in this channel. It renders against `snapshot_root`, reading the existing file
and applying each target through the existing `update_foam_entry`, then returns
complete bytes. Reuse `mutators`; do not write a second dictionary writer.

Its preconditions must include every file it read. Reuse
`effective_dictionary._inspect_source_closure` for the include set — after G0
Task 4 that follows the native etc chain, and the *absent* higher-priority
candidates it reports become `absence` preconditions. That is the whole point of
sequencing F2 before this task.

- [ ] **Step 4: Route `apply_input_overrides` through the channel**

Keep the signature; change the body to build a request, resolve, render, and
`commit_case_write`. The function returns `None` today — keep that, and add a
new `apply_input_overrides_planned(...) -> CaseWriteRecord` for callers that
want the record. Do not change a return type in a migration commit.

- [ ] **Step 5: Run everything, including the characterization test**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiaccore/tests/test_patch_through_the_channel.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
```

Expected: `0 failed`, and the characterization test passes **unchanged** from
Step 1. If it needs changing, the migration changed behaviour — investigate
before adjusting it, and report what changed and why it is acceptable.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-openfoam/src/omnidriver/openfoam/case_rendering.py packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/overrides.py packages/omnidriver-cardiaccore/tests/test_patch_through_the_channel.py
git commit -m "feat: route cardiacCore overrides through the write channel

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Task 9: Vertical slice B — one synthesis path

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_builder.py` — `build_and_launch`
- Create: `packages/omnidriver-cardiacfoam/tests/test_synthesis_through_the_channel.py`

**Interfaces:**
- Consumes: Tasks 1–8.
- Produces: `CardiacFoamPlugin.resolve_case_mutation` for `synthesize`;
  `build_case(...) -> CaseWritePlan` split out of `build_and_launch`, which
  keeps its signature and becomes plan + commit + launch.

This is the second consumer. Only after this task exists may shared mechanics be
extracted from `remediation_transaction.py` — that is Task 12.

`build_and_launch` today writes five files with bare `write_text`: `constant/electroProperties`,
`constant/physicsProperties`, `system/fvSchemes`, `system/fvSolution`,
`system/controlDict`, then provisions a mesh and mutates `controlDict` again
through `update_control_dict`. Every one of those is a framework-authored input.
The double write of `controlDict` — synthesized, then mutated — becomes one
rendering with both effects, which is the `repeated_edits_to_one_file`
conformance case in its real setting.

- [ ] **Step 1: Characterize the current behaviour**

Write a test that captures **complete content and modes**, not five files'
existence. The refuted draft's characterization test checked existence, which
would have passed for five empty files:

```python
def test_build_and_launch_produces_this_exact_case(tmp_path):
    """Characterization, captured before the migration.

    Content digests and modes, not existence. A migration that produced five
    empty files would pass an existence check.
    """
    result = build_and_launch(
        {"myocardiumSolver": "monodomainSolver", "ionicModel": "TT06"},
        physics_selectors={...}, case_dir=tmp_path, dry_run=True,
        delta_t=1e-4, end_time=1.0,
    )
    digests = {
        str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(tmp_path.rglob("*")) if p.is_file()
    }
    modes = {
        str(p.relative_to(tmp_path)): oct(p.stat().st_mode & 0o777)
        for p in sorted(tmp_path.rglob("*")) if p.is_file()
    }
    assert digests == EXPECTED_DIGESTS
    assert modes == EXPECTED_MODES
    assert result["status"] == "dry_run_complete"
```

Generate `EXPECTED_DIGESTS` and `EXPECTED_MODES` by running the current code and
pasting the result. Say in a comment that they were captured, from which commit,
and on which date.

Also capture the **declared workflow effects** — what the run document says this
case will do — not just the bytes. A synthesis that writes identical files but
declares different steps is not parity.

- [ ] **Step 2: Write the failing test**

```python
def test_synthesis_refuses_without_a_source_artifact(tmp_path):
    """`synthesize` with no declared source is not a supported mode. The
    refuted draft treated synthesis and patching as one operation at different
    arities, which is how asset-free synthesis looked supported."""
    with pytest.raises(ValueError, match="source artifact"):
        CaseMutationRequest(
            mode="synthesize", case_root=tmp_path, adapter_id="org.cardiacfoam",
            workflow="entry", source_artifacts=(), parameters=(),
            requested_by="test",
        )


def test_controldict_is_rendered_once_with_both_effects(tmp_path):
    """Today `controlDict` is written from a template and then mutated. One
    rendering carries both, so the plan shows the final content."""
    plan = build_case(..., delta_t=2e-4, end_time=0.5)
    rendered = {f.path: f.content.decode() for f in plan.files}
    assert "system/controlDict" in rendered
    assert "2e-04" in rendered["system/controlDict"] or "0.0002" in rendered["system/controlDict"]
    assert len([f for f in plan.files if f.path == "system/controlDict"]) == 1


def test_an_existing_case_is_not_silently_overwritten(tmp_path):
    """`overwrite=False` raised FileExistsError. Through the channel it becomes
    a precondition, and the message must still name the file."""
    ...


def test_a_failed_synthesis_leaves_no_partial_case(tmp_path):
    """The old path wrote electroProperties, then physicsProperties, then three
    system files. A failure at file four left a case that looks built."""
    ...
    assert not (tmp_path / "constant" / "electroProperties").exists()
```

- [ ] **Step 3: Split, implement, and run the characterization test unchanged**

Split `build_and_launch` into `build_case(...) -> CaseWritePlan` (pure
resolution plus rendering) and the orchestration that commits it and launches.
`build_and_launch` keeps its signature and its return shape.

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_synthesis_through_the_channel.py -v
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`, with the characterization test's digests and modes
unchanged. Mesh provisioning writes a `blockMeshDict` — that is a framework
input and joins the plan. If `provision_mesh` runs a native utility instead,
that is a workflow step, not a mutation; say which it is in your report.

- [ ] **Step 4: G2 exit check, then commit**

```bash
/tmp/od311/bin/python -m pytest packages/omnidriver/tests/core/test_write_channel_conformance.py -q
git add packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_builder.py packages/omnidriver-cardiacfoam/tests/test_synthesis_through_the_channel.py
git commit -m "feat(cardiacfoam): route case synthesis through the write channel

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

Record in the Status table that G2's exit evidence is met: one patch path and
one synthesis path share the transaction contract while keeping their different
prerequisites.

---

## Gate G3 — migrate and simplify

Exit evidence: entry, sweep and remediation parity on supported modes; no
framework-authored input bypasses the channel; unsupported modes refuse
explicitly; obsolete routes removed.

**Tasks 10–13 are specified at contract level, and that is deliberate.** Tasks
1–9 carry complete code because their shape is decidable now. These four are
migrations whose shape depends on what G2 actually produces — which fallback
survives, what the renderer's precondition set really contains, how many
`apply_case` consumers remain. Writing invented code for them now would be the
plan asserting a fact it does not have, which is the failure mode the roadmap
named: "Historical plans are evidence of intent, not proof of present
behavior."

What each task below **does** carry is non-negotiable and complete: the exact
files, the acceptance criterion, the parity evidence required, and the tests
that must exist. Before starting any of them, fill in the implementation steps
from the G2 code as it landed, and commit that filled-in version of this plan
as the task's first step. A reviewer must be able to see what was decided at
G2 close-out rather than during the migration.

---

## Task 10: Entry cases migrate

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/models.py` — `TutorialSpec.apply_case`
- Modify: every `apply_case` implementation the grep below finds
- Create: `packages/omnidriver/tests/core/test_entry_case_parity.py`

**Filled in 2026-09-23 (batch P2-H, before implementation), from the landed
G2 code:**

`grep -rn "\.apply_case(" packages/ --include="*.py" | grep -v /tests/` finds
exactly **one** production call site:
`core/runtime/sweep_runner.py::_materialize_entry_case`
(`spec.apply_case(spec.case_root, cases[0])`). Every other hit is a
`TutorialSpec` construction site (`apply_case=partial(_apply_case, ...)`,
~19 of them across `cardiaccore/workflows/preprocessing.py` and 13
`cardiacfoam/tutorials/*.py` files) or a test. So "prefer `plan_case`" only
has to change in one place.

Two of the four `cardiaccore/workflows/preprocessing.py` specs' `_apply_case`
already delegate to `overrides.apply_input_overrides`, which (Slice A,
`dc7fbef`) already calls `apply_input_overrides_planned` internally — the
write channel is already underneath them; what is missing is only that
`apply_case`'s `-> None` signature throws the `CaseWriteRecord` away. The 13
`cardiacfoam/tutorials/*.py` specs' `_apply_case` implementations call
`omnidriver.cardiacfoam.overrides.apply_electro_property_overrides`/
`apply_physics_property_overrides` (dict_builder.py's Slice B
`resolve_synthesis_mutation` is a *different*, synthesis-only path — it does
not cover this patch path at all), plus several call `gmsh`/template-swap
logic with no channel equivalent yet. Migrating those is real, adapter-shaped
design work (a new `resolve_patch_mutation` for cardiacfoam's own catalog),
not a signature rename, and is out of scope for one batch.

Concrete steps:
1. Add `PlanCaseFn = Callable[[Path, CaseConfig], "CaseWriteRecord | None"]`
   and `TutorialSpec.plan_case: PlanCaseFn | None = None` (after `apply_case`,
   before `metadata`) to `runtime/models.py`. Add
   `invoke_case_mutation(spec, case_root, case) -> CaseWriteRecord | None`
   next to it: calls `spec.plan_case(...)` when set; otherwise emits
   `warnings.warn(..., DeprecationWarning)` naming the removal condition
   ("removed when no in-tree spec supplies `apply_case`") and falls back to
   `spec.apply_case(...)`.
2. Change `sweep_runner.py`'s one call site to
   `invoke_case_mutation(spec, spec.case_root, cases[0])`.
3. Migrate the two `preprocessing.py` specs whose `_apply_case` already
   routes through the channel (`make_human_purkinje_slab_spec`,
   `make_human_purkinje_endocardial_spec` — and, by the same shape,
   `make_pig_morphometric_purkinje_spec`/`make_pig_transmural_purkinje_spec`
   via `_make_pig_purkinje_spec`) to also supply `plan_case=partial(_plan_case,
   ...)`, a thin wrapper calling `apply_input_overrides_planned` directly and
   returning its `CaseWriteRecord | None`. Keep `apply_case=` too — a
   pre-existing test (`test_biv_preprocessing_contract.py`) calls
   `spec.apply_case(...)` directly and stays a legitimate consumer.
4. Do **not** touch the 13 `cardiacfoam/tutorials/*.py` specs this batch —
   their underlying mutation is not yet channel-routed at all, so adding
   `plan_case=` to them would either (a) alias `apply_case` (no real
   migration, just theater) or (b) require inventing a new
   `resolve_patch_mutation` for cardiacfoam under this task's time budget,
   risking a physics-relevant regression with no adapter-specific review.
   Reported as the remaining count, not silently dropped.
5. `apply_case` is **not** retired this batch: the grep in step (1) still
   returns 13 non-test cardiacfoam construction sites after step 3. Report
   the count before (this section) and after (post-migration, still 13 + the
   2 cardiaccore-authored functions kept for the direct-`apply_case` test).

- [ ] **Step 1: Find every consumer before changing anything**

```bash
grep -rn "apply_case" packages/ --include="*.py" | grep -v "/build/"
grep -rn "ApplyCaseFn" packages/
```

`TutorialSpec.apply_case: ApplyCaseFn = Callable[[Path, CaseConfig], None]`.
List every construction site and every call site in your report before editing.
The roadmap is explicit: "Do not begin by replacing `TutorialSpec.apply_case`
across every consumer" — which is why this is Task 10 and not Task 1.

- [ ] **Step 2: Characterize, migrate one spec at a time, keep parity**

Add `TutorialSpec.plan_case: PlanCaseFn | None = None` beside `apply_case`
rather than replacing it. Core prefers `plan_case` when present and falls back to
`apply_case` with a deprecation note naming the removal condition ("removed when
no in-tree spec supplies `apply_case`"). Migrate specs one at a time, each with
a byte-level characterization test.

Retire `apply_case` only when the grep from Step 1 returns nothing outside
tests. Report the count at the start and at the end.

- [ ] **Step 3: Run and commit**

```bash
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
python3 scripts/export-capability-seams.py --check
```

---

## Task 11: Sweeps migrate, and the sweep spec gets a versioned schema

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/sweep_materialize.py`, `sweep_routing.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` — retire `SweepMaterializerCapability`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/sweep.py`
- Create: `packages/omnidriver/src/omnidriver/resources/sweep-spec.schema.json`
- Create: `packages/omnidriver/tests/core/test_sweep_spec_schema.py`

**The schema goes inside the installed package, not a repository-only
`schemas/` directory.** A repository-only file is absent from every wheel, which
is exactly the defect class the wheel shape exists to find.

**Filled in 2026-09-23 (batch P2-H, before implementation), from the landed
G2 code and one correction to this task's own file list:**

**Correction:** `packages/omnidriver/src/omnidriver/resources/` does not
exist and there is no precedent for it. `packages/omnidriver/src/omnidriver/
schemas/` already does — it ships `run-document.json` today via
`[tool.setuptools.package-data]` (`"omnidriver.schemas" = ["run-document.json"]`)
and is read back with `importlib.resources.files("omnidriver.schemas")`
(`core/runtime/run_model.py`). Creating a second resource-package convention
for one more schema would restate a fact the existing convention already
owns. `sweep-spec.schema.json` goes in `omnidriver/schemas/` beside it, and
the package-data line gains a second file, not a second package.

There are **no in-tree `*.json` sweep-spec files** — `sweep-plan`/`sweep-run`
load a spec from a path the caller supplies (`sweep_runner._load_spec`);
nothing under `packages/` is one. The "in-tree sweep specs" that exist are
the two worked JSON examples in `AGENT_GUIDE.md` (generic mode, ~line 274;
`base.entry` mode, ~line 378) — those are what
`test_every_in_tree_sweep_spec_validates` validates, as embedded dict
literals (not `SWEEP_SPEC_PATHS` reading real files, since there are none).

The schema, enumerated from what `core/sweep/sweep_expansion.py` actually
reads (not from `AGENT_GUIDE.md`): top level requires `"sweep"` (object);
`"base"`, if present, is an object with no core-imposed shape (adapter
vocabulary — `sweep_runner._entry_name`/`base = sweep_spec.get("base", {})`
only ever `.get()` into it). `sweep.mode` must be `"cross_product"` or
`"zip"`. `sweep.independent` is a required non-empty object of
non-empty-array values. `sweep.dependent` is an optional array of
`{"name", "derive", "of"}` objects (`"of"` a string or array of strings).
Cross-field rules `expand_sweep` enforces (no forward references, no name
collisions, path-safe `caseId`) are semantic, not structural, and are left
to `expand_sweep` itself rather than encoded in JSON Schema.

Concrete steps:
1. Write `packages/omnidriver/src/omnidriver/schemas/sweep-spec.schema.json`,
   `"$id"` ending `/v1`, matching the enumeration above.
2. Add a loader next to `run_model.py`'s (`core/sweep/sweep_expansion.py` or
   a new small module) using the identical
   `importlib.resources.files("omnidriver.schemas").joinpath(...)` pattern.
3. Extend `pyproject.toml`'s existing
   `"omnidriver.schemas" = ["run-document.json"]` line to list both files.
4. Extend `scripts/check-wheel-artifact.py` with a numbered check that the
   resource loads, parses, and its `$id` ends in a version, from the wheel
   env only.
5. `test_sweep_spec_schema.py`: the two `AGENT_GUIDE.md`-derived examples
   validate; a structurally-rejected spec (e.g. `mode="banana"`, which
   `_mode()` already raises `SweepValidationError` for) fails schema
   validation too; the wheel-resource test.
6. Route `SweepMaterializerCapability.route`/`materialize` through
   `resolve_case_mutation`/`commit_case_write` **only if** a concrete
   adapter implementation exists to migrate onto (`_SweepMaterializerAdapter`
   is a refusing compatibility bridge over `route_sweep_case_values`/
   `materialize_sweep_case` plugin hooks, not itself a case-input author);
   verify against G2's landed `CaseWriterCapability` before assuming this
   step is still shaped the way the original task text describes it.

- [ ] **Step 1: Derive the schema from executable behaviour**

Do not write the schema by reading the docs. Enumerate what the expansion code
actually accepts, then write the schema to match, then test that every in-tree
sweep spec validates against it and that a spec the code rejects fails the
schema too:

```python
def test_every_in_tree_sweep_spec_validates():
    for path in SWEEP_SPEC_PATHS:
        validate(json.loads(path.read_text()), schema=load_sweep_schema())


def test_the_schema_is_readable_from_an_installed_wheel():
    """A repository-only schema file is absent from every wheel."""
    from importlib.resources import files
    payload = files("omnidriver.resources").joinpath("sweep-spec.schema.json").read_text()
    assert json.loads(payload)["$schema"]


def test_the_schema_carries_a_version():
    assert load_sweep_schema()["$id"].endswith("/v1")
```

Add the resource to the wheel: check `pyproject.toml`'s package-data
configuration and extend `scripts/check-wheel-artifact.py` to assert the schema
is present. Run the wheel shape before committing.

- [ ] **Step 2: Route materialization through the channel**

`SweepMaterializerCapability.route` is pure and `materialize` writes — the same
split as `resolve` and `render`/`commit`. `route` becomes
`resolve_case_mutation` for the `clone_and_patch` mode; `materialize` disappears
into `commit_case_write`. Keep the refusing fallback: an adapter without the
hooks is refused by name, never defaulted.

- [ ] **Step 3: Run, including the wheel shape, and commit**

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```

---

## Task 12: cardiacCore operations and remediation migrate, and shared mechanics are extracted

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/operations/vtu_selection.py`, `operations/electrodes.py`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/remediation_transaction.py`
- Create: `packages/omnidriver-cardiaccore/tests/test_operations_write_contract.py`

Two different things live in these operations, and the refuted draft's Task 7
treated them as one:

- **Case inputs** an operation authors. These join the channel.
- **Standalone exports** an operation produces for a human or another tool.
  These are artifacts, not case inputs. They need their own stated contract —
  where they go, who owns them, what happens on failure — not a transaction
  channel built for inputs.

**Filled in 2026-09-23 (batch P2-H, before implementation), from the landed
G2 code and one correction to this task's own file list:**

**Correction:** `mesh_provisioning.provision_mesh` (Step 3's explicit target)
is not in `cardiaccore` at all — it lives in
`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/mesh_provisioning.py`.
This task's "Files" header omits it; adding it here rather than silently
touching an unlisted file.

`grep -rn "write_text\|write_bytes\|open(.*[\"']w" .../operations/` finds
exactly three hits, classified:

| hit | classification | why |
|---|---|---|
| `vtu_selection.py:86` `write_cell_set` | case input, **not migrated this batch** | renders a real OpenFOAM `cellSet` FoamFile meant for a case's `constant/polyMesh/sets/`; the value shape fits today's channel (`value_kind="integer_list"` exists), but there is no registered renderer for the `cellSet` format — `case_rendering.py` owns `openfoam_dictionary` only. Inventing that renderer is design work beyond this task's stated files; left as an open bypass for Task 14's inventory. |
| `electrodes.py:251` `write_reference_offset_bundle` | standalone export | writes a portable, unit-labelled coordinate bundle to an arbitrary destination for cross-tool/human consumption; no case dictionary, no case-relative addressing, nothing an OpenFOAM utility reads. |
| `electrodes.py:307` `write_electrode_positions` | standalone export | same reasoning — explicit unit-labelled target positions, a data product for a downstream step, not a case input. |

Extraction target (shared mechanics, two real consumers): `case_transaction.py`
already imports `_atomic_write_bytes`/`_fsync_directory` **from**
`remediation_transaction.py` — a real, if backwards, existing coupling. The
genuinely dual-consumed primitives are exactly those two functions plus the
"write JSON atomically" pattern (`case_transaction._write_journal`/
`_persist_completed` do it inline; `remediation_transaction._atomic_write`
does the same thing under a different name). Before-image capture
(`case_transaction._before_image`/`_restore_one`) and remediation's
manifest/backup-file scheme (`_snapshot_paths`/`_validated_manifest`) are
**not** unified — remediation's is more elaborate because of attempt
ownership (compare-and-swap, backup archive keyed by transaction id); forcing
either shape onto the other is exactly the "invent a fake attempt" trap this
task warns against.

Concrete steps:
1. New module `core/runtime/transaction_mechanics.py`:
   `atomic_write_bytes`, `fsync_directory`, `atomic_write_json` (the
   dedup of `_atomic_write`/the inline journal-write pattern).
2. `remediation_transaction.py`: delete its own `_atomic_write_bytes`/
   `_fsync_directory` bodies, import from `transaction_mechanics`; `_atomic_write`
   becomes a one-line delegation to `atomic_write_json`. What goes away:
   the duplicate fsync/replace implementation (two independent copies today).
3. `case_transaction.py`: import from `transaction_mechanics` instead of
   `remediation_transaction` (removing the backwards dependency); use
   `atomic_write_json` in `_write_journal`/`_persist_completed`.
4. `mesh_provisioning.py`: fix the clobber unconditionally (all callers,
   including `ionic_catalog_verification.py`'s direct use) — a *partial*
   five-file state now raises instead of being silently completed either
   direction. Add `meshless_polymesh_fixture() -> dict[str, bytes]`.
5. `dict_builder.py`: `resolve_synthesis_mutation` folds the fixture's five
   files in as `skip_if_present` synthesis targets when a new
   `_SYNTHESIS_META_DOCUMENT` meta-parameter
   (`include_meshless_polymesh`, mirroring the existing `overwrite` one)
   is true. `build_case` gains `dry_run: bool = False`, sets that meta
   parameter to `myocardium_solver in _meshless_solvers() and not dry_run`
   (dry_run must keep writing nothing — R3 finding 8), keeps the `dx`
   rejection for meshless solvers unconditional (regardless of dry_run,
   matching the pre-existing test), and runs the partial-mesh precheck
   before adding those targets. `build_and_launch` drops its direct
   `provision_mesh(...)` call for `_meshless_solvers()` and passes
   `dry_run=dry_run` into `build_case`. `provision_mesh` itself is untouched
   as a standalone function (still the right tool for
   `ionic_catalog_verification.py`, which does not go through
   `build_and_launch`).
6. Parity/characterization tests: partial mesh now raises (revert-confirmed);
   `build_case`/`commit_case_write` for a meshless solver produces the same
   five fixture bytes the old `provision_mesh` copy produced, atomically and
   journaled; `dry_run=True` still writes nothing (pre-existing test must
   keep passing unchanged).

- [ ] **Step 1: Classify every write in these modules, in writing**

```bash
grep -rn "write_text\|write_bytes\|open(.*[\"']w" packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/operations/
```

For each hit, record in your report: case input or standalone export, and why.
"Atomic rename alone is not the promised planned transaction" — a write that
renames atomically and is not planned is still a bypass.

- [ ] **Step 2: Extract shared mechanics, now that two consumers exist**

Remediation and the write channel both need: a journal, before-images, atomic
replacement, mode preservation, directory cleanup, and recovery. Remediation
additionally needs **attempt ownership**, which the channel does not. Extract
the shared core; do **not** invent a fake attempt during initial materialization
so that the channel can reuse remediation's path unchanged. That was the
refuted draft's Task 2 recipe and it would put a fabricated attempt id into
provenance.

Name the extracted module and its two consumers in your report, along with the
deletion target: what in `remediation_transaction.py` goes away.

- [ ] **Step 3: Retire duplicate materialization, on parity evidence only**

The refuted draft's Task 9 deleted the second materialization mechanism. Delete
it only when the migrated public routes prove semantic parity, per route, with
a test. Supporting patch-based sweeps does not imply asset-free cardiacCore
synthesis works; those are different modes with different prerequisites.

Report, per retired route: the parity test that justifies it.

---

## Task 13: `describe` shows the write surface

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/introspection.py`
- Create: `packages/omnidriver/tests/core/test_describe_write_surface.py`

`describe` must expose qualified mutable, consumed and supported scopes, their
evidence, and complete proposed changes — **generated from the same contracts
validation uses**, not from a second hand-maintained description. A second
description is a second source of truth, and this repository's rule is that one
fact has one declarer.

**Filled in 2026-09-23 (batch P2-H, before implementation), from the landed
G2 code and one correction to this task's own test snippet:**

**Correction:** the sketched test imports `CATALOG.entries` directly — but
this test file lives under `packages/omnidriver/tests/core/`, and core must
not import cardiac vocabulary (`CATALOG` is cardiac). The core-level test
uses a fake `DictionaryCatalogCapability`-shaped double composed into a test
`driver_context`, the same way every other core capability test in this
package already does, not a real adapter's catalog.

The one core-owned, flat, adapter-agnostic anchor for "the same catalog
entries validation uses" is `driver_context.capabilities.dictionary_catalog.
entries()` → a tuple of `DictEntry` (core's own dataclass,
`contracts/dictionary.py`) with `.driver_path`/`.value_kind`/`.typical_value`
etc. — every adapter's `get_dict_entries()` backs it, and it is exactly what
`validate_value_shape(entry.value_kind, value)` is checked against
elsewhere. `override_schema.dict_entry_catalog()` is **not** this anchor —
its own docstring says its shape is adapter-declared and nested differently
per adapter (physicsProperties flat, electroProperties grouped), so core
cannot walk it generically to recover qualified ids.

Concrete steps:
1. `_write_surface(driver_context, spec, overrides)` in `introspection.py`:
   - `mutable`: one entry per `dictionary_catalog.entries()` item —
     `qualified_id`, `value_kind`, `unit`, and `source` (`"case"` when
     `overrides` supplies it, `"template"` when the entry's `typical_value`
     is non-empty and no override does, else `"call_site_default"` — every
     value drawn from `VALUE_SOURCES`, `core/case_write.py`).
   - `consumed`: paths named in `spec.metadata["workflow_dag"]["steps"][*]
     ["consumes"]` (already-declared data every `TutorialSpec` with a
     workflow DAG carries; not a new concept).
   - `modes`: one entry per `case_write.MUTATION_MODES`, each
     `{"supported": bool, "reason": str}` from
     `driver_context.capabilities.case_writer.supported_modes()` —
     `reason` non-empty exactly when `supported` is `False` (an absent
     resolver, an exception resolving `supported_modes()`, or the mode
     simply not reported).
   - `proposed_changes`: the `mutable` entries whose `qualified_id` the
     caller's `overrides` actually set, each showing the value and
     `source="case"`. **Scope limit, stated in the report, not hidden:**
     this lists what the caller asked to change, validated against the
     catalog — it does not invoke a real adapter's `resolve()`, because
     core cannot construct an adapter-specific `CaseMutationRequest`
     (document/key_path addressing) generically. A literal resolve/render
     preview is future work, named as such.
2. Wire `"write_surface": _write_surface(...)` into `describe_entry`'s
   return dict.
3. `test_describe_write_surface.py`: the three tests named above, adapted to
   the fake-capability-double correction.



```python
def test_the_described_surface_comes_from_the_validation_contracts():
    """Not a parallel description. The same catalog entries that validate a
    value are the ones described, so the two cannot drift."""
    described = describe(...)["write_surface"]
    from_catalog = {entry.driver_path for entry in CATALOG.entries}
    assert {item["qualified_id"] for item in described["mutable"]} <= from_catalog


def test_an_unsupported_mode_is_described_as_unsupported_not_omitted():
    """Omission reads as "no opinion". An agent needs to know the difference
    between a mode that is unsupported and one nobody mentioned."""
    described = describe(...)["write_surface"]
    assert described["modes"]["synthesize"]["supported"] is False
    assert described["modes"]["synthesize"]["reason"]


def test_every_described_value_carries_its_source():
    for item in describe(...)["write_surface"]["mutable"]:
        assert item["source"] in VALUE_SOURCES
```

---

## Task 14: Four shapes, the mutation inventory, and the close-out

- [ ] **Step 1: Rebuild and run all four shapes**

```bash
rm -rf /tmp/od311 /tmp/odcore /tmp/wheeltest /tmp/wheelenv
uv venv --python 3.11 /tmp/od311 && VIRTUAL_ENV=/tmp/od311 uv pip install -q \
  -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam \
  -e packages/omnidriver-cardiacfoam -e packages/omnidriver-cardiaccore pytest
uv venv --python 3.11 /tmp/odcore && VIRTUAL_ENV=/tmp/odcore uv pip install -q \
  -e "packages/omnidriver[post]" pytest
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest

/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python -m pytest packages/omnidriver/tests -q
/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q -m "not slow"
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
```

Expected: `0 failed` everywhere; both gates exit 0.

- [ ] **Step 2: Produce the mutation-path inventory**

**This replaces the refuted draft's write-count acceptance criterion.** A count
of `write_text` calls cannot distinguish a framework-authored input from a
solver's own output, so it can neither pass nor fail honestly.

```bash
grep -rn "write_text\|write_bytes\|shutil.copy\|os.replace\|Path.rename" \
  packages/*/src/ | grep -v "/build/" > /tmp/all-writes.txt
wc -l /tmp/all-writes.txt
```

Classify **every** line into a table in your report:

| path | classification | justification |
|---|---|---|
| … | framework-authored case input | must go through `commit_case_write` |
| … | declared workflow output | native utility's own file; artifact attribution |
| … | standalone export | Task 12's artifact contract |
| … | transaction mechanics | inside `case_transaction.py` itself |
| … | test fixture | not production |

Every line in the first class that does not route through `commit_case_write` is
an open bypass. List them; do not close the gate with any remaining.

- [ ] **Step 3: Confirm the two payoffs, and state the limits**

The payoffs this phase claims:

1. Every framework-authored case input is planned before it is written and
   rolled back if it fails. Evidence: the inventory above plus the conformance
   suite.
2. An agent can see the complete proposed change before approving it. Evidence:
   Task 13's `describe` output for a real request.

The limits it does **not** claim, restated here so the close-out records them:

- No simultaneous atomic visibility to outside readers.
- No control over writers outside the framework.
- No native solver acceptance. G5 owns that; this phase probes dictionaries.

- [ ] **Step 4: Update the Status table and hand off to G4**

Set every task's state to its commit hash. Record which of the roadmap's G3 exit
criteria are met and which are not, with evidence per line.

Then record, explicitly, the four audit findings this phase deliberately does
**not** close, so the next plan inherits them rather than rediscovering them:

| finding | why it is not here | owner |
|---|---|---|
| C4 — placeholder capability digests; explicit selection expands one dependency level | the reviewed plan is bound to `stack_identity`, and Task 7 measures exactly how far that binding reaches. Real content digests need a contract for what "capability content" is, which is G4's | G4 |
| F3 — no reusable numerical-parameter/default knowledge surface; builders author numerical choices | Task 4's value kinds give shapes, not defaults. An inventory separating authored templates from native defaults is G4's | G4 |
| F4 — `typical_value_fallback=True` promotes catalog examples into generated inputs; the C++ scanner misses reads after `//` inside a string and duplicates nested matches | this phase makes value *origin* recordable (`VALUE_SOURCES`) and does not repair the scanner or change the fallback policy | G4 |
| placeholder grammar is declared three times | `_PLACEHOLDER` in `core/contracts/dictionary.py`, plus its own copies in `core/specs/validation.py` and `cardiacfoam/dict_builder.py`. The regex cannot see `<_x>` or `<x-y>`, so the all-declared-bindings guard is defeatable; widening one copy without the others diverges them silently. Zero production declarations are affected today, so it is latent. Found by R2 2026-09-23; the fix batch reported it rather than widening one copy, which was the right call. One fact, three declarers — model the relation instead of restating it. | G4 |
| R1 — release tags omit cardiacCore; eligibility is not bound to all gates at the exact revision | release work follows contract convergence, and the supported profile and distribution terms are the owner's decisions | G5 |

`VALUE_SOURCES` exists from Task 1 and F4 is the first place it earns its keep:
a catalog example promoted into a generated input is a `template` value
presented as a `case` value. Do not fix F4 here, but note in the handoff that
the vocabulary it needs is already in place.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md
git commit -m "docs: close G3 -- one write channel, migrated

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Disposition of the refuted draft's thirteen tasks

Recorded so a reader arriving from the roadmap's §4 table can find where each
one went. The draft itself is at `db93cc4`.

| refuted task | became |
|---|---|
| 1 — plan types | Tasks 1 and 2, rewritten: complete immutable payload, concrete addresses, preconditions, schema and identity, semantic owner and renderer named. Journal data separated out. |
| 2 — transactional writer | Tasks 5 and 6: a case-level lease/journal/recovery contract. Shared mechanics extracted in Task 12, once two consumers exist. |
| 3 — writer capability | Task 3: planning and rendering specified before the executor; patch rendering explicit; ownership per format, not one exclusive writer. |
| 4 — value kinds | Task 4: generic shapes in core; OpenFOAM text parsing stays in OpenFOAM; scientific constraints stay in the adapter. G0 Task 5 fixed the weak validation first. |
| 5 — dynamic paths | Task 4: allowed bindings validated, not just placeholders expanded; full document scope preserved. |
| 6 — cardiacCore migration | Task 8, after G0's addressing and validation fixes; source artifacts and effective configuration explicit. |
| 7 — Python operation writers | Task 12, split: case inputs join the channel, standalone exports get their own stated artifact contract. Atomic rename alone is not a planned transaction. |
| 8 — split `build_and_launch` | Task 9, after the contract is executable. Characterizes complete content, modes and declared effects — not five files' existence. Public compatibility preserved. |
| 9 — retire duplicate materialization | Task 12, deferred until migrated public routes prove per-route semantic parity. |
| 10 — sweep schema | Task 11: derived from executable behaviour, versioned, and bundled inside installed package resources. |
| 11 — introspection | Task 13: qualified scopes, evidence, complete proposed changes, generated from the validation contracts. |
| 12 — in-process operation type | Task 12, and only if two consumers need common validation. Domain algorithms and maturity metadata stay in the adapter. |
| 13 — verification and close-out | Task 14: four shapes plus native and public-route conformance; raw write-count acceptance replaced by a reviewed mutation-path inventory. |

Two more corrections the rewrite carries, from the roadmap's §4 closing
paragraph:

- The draft's internal API disagreed with itself — `plan(request)` in one place,
  `plan(case_root=..., values=...)` in its examples. One signature now:
  `resolve(request)` → `render(resolved)` → `commit_case_write(plan)`.
- Tests that asserted only that a symbol exists, and tests that expected
  arbitrary text such as `"bad"` to fail with no declared type constraint making
  it fail, are gone. Task 4 declares the constraint that makes a shape check
  meaningful.
