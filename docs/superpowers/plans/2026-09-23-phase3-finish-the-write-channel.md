# Phase 3: Finish the Write Channel — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five open bypasses Phase 2's close-out found, on a smaller
surface than Phase 2 built, so that "one auditable transaction channel for
framework-authored case inputs" is true rather than aspirational.

**Architecture:** Phase 2 assumed twelve bespoke tutorial migrations. Measurement
says otherwise. Across all twelve `_apply_case` bodies, ~65 of ~73 write calls
funnel through a single chokepoint:

```
apply_electro_property_overrides ┐
apply_physics_property_overrides ┼→ apply_entry_overrides → normalize_entry_overrides → update_foam_entry
set_delta_t                      ┤
set_end_time                     ┘
replace_block_mesh_resolutions   ── separate: a `hex (` line rewrite, not a key/value set
```

`normalize_entry_overrides` already yields `{"key", "value", "scope"}` per
override — most of a `ParameterAssignment`. So the spine of this phase is: turn
**one function** into a resolver, follow it with two two-line wrappers, handle
one genuine special case, and the eleven tutorials that call it come along with a
line each. The bespoke part of each tutorial computes *which values*; the writing
is shared.

**Tech Stack:** Python 3.11+, pytest. No new runtime dependency.

**Source:** [`2026-09-20-phase2-one-write-channel.md`](2026-09-20-phase2-one-write-channel.md)'s
G3 close-out (commit `aa8c7fa`) and review R4 (commit `8fbf59c`), which together
enumerate the five bypasses and size them. Phase 2's gates G0–G2 are closed and
reviewed; G3 is not, and this plan is what closes it.

**Prerequisite:** Phase 2 Tasks 1–13 merged. HEAD at plan time: `8fbf59c`.
Suite `0 failed` in all four shapes; both static gates pass.

## Status

Tasks 1–2 done. Tasks 3–11 not started.

| task | what it closes | state | commit |
|---|---|---|---|
| 1 · cut the surface before migrating onto it | over-modelled contract | done | `f476a13` |
| 2 · `apply_entry_overrides` becomes a resolver | the chokepoint, 28 calls | done | `7830529` |
| 3 · `controlDict` setters become resolvers | 11 calls | pending | — |
| 4 · `replace_block_mesh_resolutions` | 8 calls, the special case | pending | — |
| 5 · `--apply` joins the channel | **bypass 4** | pending | — |
| 6 · the eleven tutorials follow through | **bypass 1** (most of it) | pending | — |
| 7 · source artifacts and sidecars, classified | **bypass 1** (remainder) | pending | — |
| 8 · `generic_case.py` | **bypass 2** | pending | — |
| 9 · the `describe` seam | the unmet second payoff | pending | — |
| 10 · `Allrun`, and delete what is unreachable | **bypass 5** | pending | — |
| 11 · close-out, with a widened inventory | G3 | pending | — |

`write_cell_set` (**bypass 3**) is **deliberately out of scope** — see "What this
plan does not do".

## What this plan does not do, and why

**`cardiaccore/operations/vtu_selection.py::write_cell_set`.** It writes a
`cellSet`, a format no renderer understands. Building one has a single consumer,
and this repository's rule is that a shared abstraction needs two demonstrated
consumers. Migrating it means inventing a `cellSet` renderer for one caller.
Leave it as a recorded bypass with its existing in-code classification comment,
and revisit when a second consumer appears.

**Native solver and meshing output.** Those are declared workflow outputs with
artifact attribution, not framework mutations. The channel never claimed them.

**G4 and G5 work** — the agent evidence surface, the release gate. Separate
phases, and G5 needs owner decisions this plan does not make.

## Global Constraints

- Python floor is **3.11**.
- `omnidriver.core` MUST NOT import from any adapter; the waiver list in
  `scripts/check-import-boundaries.py` stays empty.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- **No OpenFOAM syntax in core.** Core moves bytes and digests.
- **`update_foam_entry` is legitimate only inside a renderer.** Writing into the
  isolated snapshot `render_case_files` is given is correct; writing into a live
  case is the bypass this phase removes. After Task 6, every caller outside
  `openfoam/case_rendering.py` is a defect.
- Do not weaken or skip a guard. Every fix needs a test that fails before it and
  passes after — **verify by reverting, not by assuming**.
- A test may encode a defect as intended behaviour. Two did in Phase 2
  (`test_workflow_command_security.py`, `test_single_cell_solver_gets_a_static_polymesh`).
  Correct with a dated note **and** add a test for the corrected behaviour.
- Do not quote suite totals. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number.
- Record a document correction with a date rather than overwriting it silently.
- Do not add a `LICENSE` file or a `license` field.
- **Do not stage the owner's work.** `docs/OMNIDRIVER_ROADMAP.md` (modified) and
  `docs/audits/` (untracked) are theirs. Never `git add -A`.
- Gate scripts need the venv interpreter, not bare `python3`:
  `/tmp/od311/bin/python scripts/check-import-boundaries.py` and
  `... scripts/export-capability-seams.py --check`.
- End commit messages with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`

## How to execute a task in this plan

**Verify before you apply.** Twenty-three plan claims were wrong across Phase 2 —
including two test cases that could not have passed as written, a `resources/`
package that did not exist, and a search chain that was wrong twice. Read the
current source before applying any snippet here. Reporting a wrong claim is a
finding, not a failure.

**A fixture proves the code does what its author believed, not what the world
does.** Where a claim concerns behaviour outside this repository — a native
binary, a file format — check it against that behaviour. The `#includeEtc` chain
shipped wrong twice with a fully green fixture suite.

**Characterize before you migrate.** Every migration task below requires a test
capturing the *current* bytes, written and passing before the change, and passing
unchanged after. Capture content digests and modes, never file existence — an
existence check passes for five empty files.

**Tasks 6–9 are specified at contract level.** Their implementation depends on
what Tasks 2–4 actually produce. Fill in their steps from the landed code and
commit the filled-in plan as that task's first step, as Phase 2's batch P2-H did.

---

## Task 1: Cut the surface before migrating onto it

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/case_write.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py`
- Modify: the Phase 2 plan's decision record (dated note)

**Rationale.** Review R2 found `clone_and_patch` and `generated_input` "distinct
in name only", and the remedy at the time was to *invent* a prerequisite for each
so they would differ. That is backwards: a distinction that needs a
made-up rule to justify it is not a distinction. Migrating eleven tutorials onto
a three-mode contract multiplies that mistake by eleven.

- [x] **Step 1: Count the real consumers of each mode**

```bash
grep -rn "generated_input\|clone_and_patch\|synthesize" packages/*/src/ | grep -v "/build/"
```

Report, per mode: how many production call sites construct a request in it, and
what each one actually needs from it. If `generated_input` has no consumer that
`clone_and_patch` cannot serve, it goes.

- [x] **Step 2: Reduce to two modes if the count supports it**

`MUTATION_MODES = frozenset({"clone_and_patch", "synthesize"})`. The distinction
that survives is real and was validated in Phase 2: `synthesize` requires
explicit source artifacts, `clone_and_patch` does not. Remove
`generated_input`'s invented single-document prerequisite along with it.

**If the count does not support it, do not force it.** Report what you found and
leave three modes. A mode with a genuine consumer stays.

- [x] **Step 3: Shelve what has no consumer, honestly**

The `environment` precondition kind is implemented end to end and is correct, but
no planning path outside `patch_preconditions` emits one. Do **not** delete it —
Task 5 gives it a second consumer. Record it in the plan as implemented-and-thin
so a later reader does not mistake thin for unused.

Audit `ResolvedMutation`: if every field is passed straight through to the
renderer untouched, say so and consider whether it earns its own type.

- [x] **Step 4: Run and commit**

```bash
/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"
/tmp/od311/bin/python scripts/check-import-boundaries.py
/tmp/od311/bin/python scripts/export-capability-seams.py --check
```

### Findings, 2026-09-23

**Per-mode consumer count** (`grep -rn "generated_input\|clone_and_patch\|synthesize" packages/*/src/ | grep -v "/build/"`,
cross-checked against `grep -rln "CaseMutationRequest(" packages/*/src/` and
`grep -rn "supported_creation_modes\|MUTATION_MODES" packages/*/src/`):

| mode | production call sites | what each needs |
|---|---|---|
| `clone_and_patch` | 1 — `cardiaccore/workflows/overrides.py::apply_input_overrides_planned` (the only production `CaseMutationRequest(mode="clone_and_patch", ...)`; declared supported by `cardiaccore/plugin.py`'s `get_supported_mutation_modes` → `{"clone_and_patch"}`) | edits keys in a case that already exists; no source artifacts |
| `synthesize` | 1 — `cardiacfoam/dict_builder.py`'s `build_and_launch` resolution path (the only production `CaseMutationRequest(mode="synthesize", ...)`; declared supported by `cardiacfoam/cardiacfoam_plugin.py`'s `get_supported_mutation_modes` → `{"synthesize"}`) | explicit, non-empty `source_artifacts` — a case built from nothing is refused |
| `generated_input` | **0** | nothing — no adapter's `get_supported_mutation_modes()` ever names it, `openfoam/case_rendering.py` has no renderer for it, and neither production `CaseMutationRequest` constructor ever builds one |

Every other hit is a test (`test_case_write_request.py`), a docstring, or an
unrelated identifier (`_synthesize_case` in
`cardiacfoam/ionic_catalog_verification.py`, a private helper name that
constructs no `CaseMutationRequest` at all).

**Decision: cut.** `generated_input` removed from `MUTATION_MODES`; its
"exactly one document" prerequisite removed from
`CaseMutationRequest.__post_init__`. See the dated correction in
`docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md` (after its
"Decision, 2026-09-23: a parameter value is typed data" section) and in
`omnidriver.core.case_write`'s module/class docstrings. Test coverage: the
three tests that asserted its invented prerequisite
(`test_generated_input_with_no_parameters_is_refused`,
`test_generated_input_with_more_than_one_document_is_refused`,
`test_generated_input_with_exactly_one_document_is_accepted`) are replaced by
one test asserting the mode is now unknown
(`test_generated_input_is_no_longer_a_supported_mode`), per this plan's own
rule that a removed mode's refusal test is replaced, not deleted. Verified by
reverting `case_write.py` to HEAD and confirming the new test fails there
(`DID NOT RAISE ValueError`) and passes after the change.

**`clone_and_patch`'s "at least one parameter" rule: kept.** Its one
production caller, `apply_input_overrides_planned`, already returns `None`
before constructing a request when `validate_input_overrides(overrides)` is
empty — it does not rely on this constructor guard to catch a real
zero-parameter patch. No caller was found that legitimately wants to submit
one (no sweep-axis-resolves-to-no-change caller exists yet; Tasks 2–6 have not
landed). The rule stays as a construction-time invariant for future callers
(`--apply`, Task 5) rather than being relaxed on no evidence.

**`environment` precondition kind: implemented-and-thin, not unused.** Built
by `openfoam/case_rendering.py::patch_preconditions` and checked by
`case_transaction._check_preconditions`; its only emitter today is that one
call site. Not deleted — Task 5 (`--apply` joining the channel) gives it a
second consumer via the F1b `execution_env` readback it was built for. Noted
both here and as a comment beside `PRECONDITION_KINDS` in `case_write.py`.

**`ResolvedMutation` audit.** Not a pure passthrough container:
- `targets` is genuinely consumed, not merely forwarded —
  `openfoam/case_rendering.py::_document_edits` groups it by document, and
  `.formats()` derives a value from it that neither producer hands over
  directly. `__post_init__` also deep-freezes it, a real invariant a plain
  container would not enforce.
- `preconditions` and `semantic_owner_id` genuinely *are* passed straight
  through untouched by both producers
  (`cardiaccore/workflows/overrides.py::resolve_patch_mutation`,
  `cardiacfoam/dict_builder.py`'s synthesis resolver) into `CaseWritePlan`.
  That is expected of a resolve/render boundary, not a defect.
- `expected_effects` is a genuine finding: both producers build one, but
  `CaseWritePlan` has no field for it and nothing else reads it either —
  confirmed by grep across the repo (only its two producers, this class, and
  tests supplying `()`). It is computed and discarded on every real call
  today.

**Recommendation:** the type earns its keep (real behaviour + a real
invariant on `targets`), so it should not be flattened into a dict. The
`expected_effects` field should either gain a consumer (an evidence/record
field on `CaseWriteRecord`, or a `describe`-style preview) or be dropped once
nothing writes it either — but that is Tasks 2–6's call, not Task 1's:
removing a field mid-plan, while later tasks still build on this type, would
be worse than carrying one thin field for now. Not removed in this task, per
the plan's own instruction.

**Plan-claim correction:** `packages/omnidriver/src/omnidriver/core/plugin_interface.py`
was listed as a file this task modifies. It contains no reference to
`generated_input`, to the three/two-mode count, or to any per-mode
enumeration that the cut invalidates — its `get_supported_mutation_modes`
docstring is generic across however many modes exist. No change was needed
there; left unmodified.

---

## Task 2: `apply_entry_overrides` becomes a resolver — the chokepoint

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/overrides.py`
- Create: `packages/omnidriver-cardiacfoam/tests/test_override_resolution.py`

**Interfaces:**
- Produces: `resolve_entry_overrides(file_path, overrides, *, document, electro_properties_path=None) -> tuple[ParameterAssignment, ...]`
  — pure, no filesystem writes. `apply_entry_overrides` keeps its signature and
  its write behaviour for one transitional release, delegating to the resolver
  plus a commit.

**This is the task that makes the rest cheap.** 28 of the tutorials' calls reach
here through `apply_electro_property_overrides` / `apply_physics_property_overrides`.

- [x] **Step 1: Read what `normalize_entry_overrides` already gives you**

```bash
grep -n "def normalize_entry_overrides" -A 40 packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/overrides.py
```

It yields `{"key", "value", "scope"}` per override. A `ParameterAssignment`
needs `qualified_id`, `owner`, `document`, `key_path`, `binding`, `value`,
`value_kind`, `source`. So the gap is: derive `qualified_id` and `value_kind`
from the catalog, set `document` from the file being written, `key_path` from
`scope + key`, and `source`.

**`source` is not a free choice.** A value the caller supplied is `case`. A value
read from a tutorial's own defaults is `template`. Getting this wrong
re-creates finding F4, where catalog examples were promoted into generated
inputs. If you cannot tell which a value is, that is a finding — report it.

- [x] **Step 2: Write the characterization test first**

Capture the exact bytes `apply_electro_property_overrides` produces today for a
representative override set, including a scoped nested key. That test must pass
before your change and unchanged after.

- [x] **Step 3: Write the failing test for the resolver**

Assert: the returned assignments carry qualified ids that round-trip to the same
document and key the old path wrote; a value whose kind the catalog declares is
validated (a `nan` for a `scalar` must raise, since `ParameterAssignment`
validates at construction); and **no file is touched** — assert on a directory
snapshot, because purity is what makes a dry run free.

- [x] **Step 4: Implement, keeping the old entry point working**

`apply_entry_overrides` becomes `resolve_entry_overrides(...)` followed by a
`commit_case_write`. Its signature and return type do not change — a caller
outside this repository must not break in the commit that changes the mechanism
underneath it. Add a dated deprecation note naming the removal condition: "when
no in-tree caller writes through it."

- [x] **Step 5: Run, including both adapter suites, and commit**

### Findings, 2026-09-23

**Step 1 — what `normalize_entry_overrides` actually produces.** Confirmed
against current source (`overrides.py:32-94`):
- `overrides is None` → `[]`.
- **Mapping form** (`{"a.b.c": value}`): every key is dot-split, each token
  resolved through `_resolve_scope_tokens` (which expands the literal token
  `"$ELECTRO_MODEL_COEFFS"` to the case's real active `<solver>Coeffs` block
  name via `detect_electro_coeffs_scope`, and passes any other token through
  unchanged). One part → `{"key": part, "scope": None}`. More than one part →
  `{"key": parts[-1], "scope": parts[:-1]}`. A nested scoped key, e.g.
  `"$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_period_S1"` against a case
  whose active block is `singleCellSolverCoeffs`, yields
  `{"key": "stim_period_S1", "scope": ("singleCellSolverCoeffs", "singleCellStimulus")}`.
- **`Sequence[Mapping]` form**: each item needs `"key"`/`"value"`. **Found, not
  assumed:** this form only dot-splits `"key"` when the item has **no**
  `"scope"` field at all (it then falls back to the same
  `normalize_from_key_value` the mapping form uses). If the item names
  `"scope"` explicitly — even `None` — `"key"` is taken **literally**, not
  dot-split. This asymmetry is real, not a bug this task fixes; the resolver
  preserves it by building on `normalize_entry_overrides` rather than
  re-deriving key/scope splitting itself.

**Step 1 — `value_kind`/`qualified_id`, and the plan-claim correction that
follows from them.** `value_kind` is looked up against the same catalogues
`cardiacfoam_plugin.py` aggregates (`ELECTRO_PROPERTY_ENTRY_GROUPS`,
`PHYSICS_PROPERTY_ENTRIES`) — never guessed — via `_catalog_entry_for`,
tried literally first (`singleCellSolverCoeffs.tissue`, what every real
tutorial call site writes) and, only for an electroProperties lookup with a
non-empty scope, against the catalog's own templated form (first scope
segment replaced by the literal `$ELECTRO_MODEL_COEFFS` token, since that is
how every scoped entry is actually declared). `qualified_id` is the
**concrete** dotted path (`".".join(key_path)`), matching how
`cardiacCore.workflows.overrides._parameters_for` keeps its caller's own
concrete `driver_path` as `qualified_id` rather than an abstract template —
not a bare unqualified leaf key, which is what S1/S3 fixed.

**An override naming a key the catalog does not declare: found, and
refused, not inferred.** `resolve_entry_overrides` raises `ValueError`
(matching the precedent already set by
`cardiaccore.workflows.overrides.validate_input_overrides`) when neither
lookup matches. A real, in-tree instance: `manufactured_bath_bidomain.py`'s
`_apply_case` unconditionally submits
`<solver>Coeffs.manufacturedBidomain.fdaBathVariant`, a key
`dict_entries_catalog.py`'s own 2026-09-19 correction note says was
**deliberately removed** because no native code reads it under
`<solver>Coeffs`. Covered by `test_an_undeclared_key_is_refused_not_silently_written`.

**`source` — determined, not picked, and found to be constant at this
layer.** Every `ParameterAssignment` `resolve_entry_overrides` builds has
`source="case"`. Verified this is correct, not a default-by-omission, by
finding the actual `case`-vs-`template` precedent in this same package
(`dict_builder.py`'s synthesis resolver: `source="case" if delta_t is not
None else "template"`, i.e. `template` names a value **this module itself**
falls back to when its caller supplied none). `overrides.py` has no fallback
of its own anywhere in this call path — every value it sees already arrived
as a concrete entry in the caller's `overrides` argument, with no signal
distinguishing "a real per-case choice" from "a tutorial's own hardcoded
default that happened to be passed in here." That distinction is real (it is
finding F4), but it is not resolvable at this layer; it belongs to each
tutorial's own `_apply_case`, the same place `dict_builder.py` makes it, and
is therefore Task 6's decision per call site, not this task's.

**Plan-claim correction: Step 4's "followed by a `commit_case_write`" does
not hold, and was not implemented that way.** `commit_case_write`
(`case_transaction.py`) requires a full `CaseWritePlan` — an absolute
`case_root`, a `driver_context`, rendered `RenderedFile` bytes (produced by
`case_rendering.py`, not this module), a write lease, and journal recovery.
`apply_entry_overrides` receives a bare `file_path` with no case root and no
driver context; there is nothing to build a `CaseWritePlan` from, and doing
so would mean this transitional wrapper newly depends on machinery none of
its current callers supply. Implemented instead as `resolve_entry_overrides`
followed by the **same direct `update_foam_entry` calls this function
already made**, driven by the resolved assignments' `key_path`/`value`
rather than by `normalize_entry_overrides`'s raw dicts — i.e. "a commit" in
the sense of "apply what was resolved," not a call to
`case_transaction.commit_case_write`. `update_foam_entry` staying legitimate
only inside a renderer is unchanged in intent: this is the one call site the
plan itself keeps for "one transitional release," not a new one.

**Found during verification, not assumed: a fully strict resolver breaks
real, currently-passing tests today**, before Task 6 touches anything.
Running the full `omnidriver-cardiacfoam` suite against a first
implementation that made `apply_entry_overrides` delegate unconditionally
(no fallback) failed six tests:
`test_dict_entries_catalog.py::test_apply_electro_property_overrides_updates_dimensioned_and_dynamic_entries`,
and five in `test_manufactured_eikonal_ecg_tet.py` /
`test_manufactured_monodomain_pseudo_ecg_tet.py`. Root cause, confirmed by
reading the failures: real, currently-accepted overrides do not fit the
catalog's typed-data contract yet —
1. a dynamic per-case identifier the catalog cannot enumerate, e.g.
   `$ELECTRO_MODEL_COEFFS.ecgDomains.ECG.electrodePositions.V1` (`V1` is a
   caller-chosen electrode name, not a declared suffix), and
2. a `dimensioned_scalar`/`dimensioned_tensor` catalog entry (`conductivity`,
   `stimulusIntensity`) whose real callers always pass an **already-rendered
   OpenFOAM literal string** (e.g. `"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"`),
   never the `{"value": ..., "dimensions": ...}` mapping
   `validate_value_shape` requires for that kind. Confirmed no parser from
   that literal syntax into typed data exists anywhere in this repository
   (`grep -rl dimensioned_tensor packages/*/src/` finds only the declaration
   site and the generic shape validator) — this is the same tension Task 4
   names for `replace_block_mesh_resolutions` ("inventing a value kind for
   it would be the `openfoam_literal` layering mistake again"), showing up
   one task early.

   This also means five real tutorials (`cable_1d_cv_convergence.py`,
   `cable_1d_restitution.py`, `manufactured_bath_bidomain.py`,
   `manufactured_monodomain_pseudo_ecg.py`, `manufactured_eikonal_ecg.py`)
   pass a `conductivity` override as a raw string against a
   `dimensioned_tensor` catalog declaration; that gap is real and unresolved
   by this task, and Task 6 will hit it directly for those five tutorials
   unless a parser (or a reconsidered value contract for `conductivity`)
   lands first.

Neither is a catalog-declaration gap this task's mandate covers (that would
be a `dict_entries_catalog.py` change, or a new parser in
`omnidriver-openfoam`/`omnidriver-cardiacfoam`, either well past "the
chokepoint becomes a resolver"), and "keeps its exact signature and write
behaviour for one transitional release" leaves no room to newly refuse
either while eleven tutorials still call through it. Resolved by having
`apply_entry_overrides` catch `resolve_entry_overrides`'s `ValueError` and
fall back to the **exact pre-Task-2 per-item loop** for the whole batch in
that case (safe because `resolve_entry_overrides` is pure — nothing has
been written yet when it raises). `resolve_entry_overrides` itself stays
strict with no fallback: a direct caller (Task 6) gets the real refusal and
must resolve the gap before migrating a tutorial that hits it. Full suite
re-run after adding the fallback: 872 passed, 103 skipped (`omnidriver-cardiacfoam`
alone); 0 failed in all four required shapes for this task (see the
report for the exact commands and counts).

---

## Task 3: The `controlDict` setters become resolvers

**Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/utils.py`
- Create: `packages/omnidriver-openfoam/tests/test_control_dict_resolution.py`

`set_delta_t` and `set_end_time` are two-line wrappers around
`update_foam_entry`. 11 calls across the tutorials.

- [ ] **Step 1: Add `plan_delta_t` / `plan_end_time` beside them**

Returning a `ParameterAssignment` each, for `system/controlDict`'s `deltaT` and
`endTime`, `value_kind="scalar"`. Keep the writing versions until Task 6
migrates their callers, then retire them in the same commit that removes the last
caller.

- [ ] **Step 2: Note the overlap with slice B and do not duplicate it**

`dict_builder`'s synthesis path already renders `controlDict` with both its
template content and its `deltaT`/`endTime` edits folded into one `RenderedFile`
— that was Phase 2's `repeated_edits_to_one_file` case in its real setting. Reuse
that folding rather than writing a second one. If the two cannot share, say why.

---

## Task 4: `replace_block_mesh_resolutions` — the one genuine special case

**Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/utils.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_rendering.py`

This one is **not** a key/value set. It rewrites lines beginning `hex (` inside
an existing `blockMeshDict`, validating that exactly `expected_blocks` were
replaced. A `ParameterAssignment` cannot express it, and inventing a value kind
for it would be the `openfoam_literal` layering mistake again.

- [ ] **Step 1: Decide its shape, on evidence**

Two candidates, and the choice is yours to argue:

1. **A whole-document render.** The mesh resolution becomes an input to
   `default_block_mesh_dict_text`, and the document is synthesized rather than
   patched. Clean, but only works where the framework authored the
   `blockMeshDict` in the first place — the `manufactured_monodomain_1d3d`
   convention copies `blockMeshDict.3D` and patches it, so check that case.
2. **A format-owned patch target.** `case_rendering` grows a target kind that
   names a structural edit rather than a key, with OpenFOAM owning the `hex (`
   grammar. Honest about where the knowledge lives; more machinery.

Report which you chose and why. Do **not** put `hex (` knowledge in core.

- [ ] **Step 2: Characterize against a real `blockMeshDict`, then migrate**

Include the `expected_blocks` validation — silently replacing the wrong number of
blocks is the failure this function exists to prevent.

---

## Task 5: `--apply` joins the channel — bypass 4

**Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py`
- Modify: `packages/omnidriver/src/omnidriver/cli.py`
- Create: `packages/omnidriver-openfoam/tests/test_apply_through_the_channel.py`

**This is the most-used framework write path**, and it is invisible to a
`write_text` grep because it mutates in place through `foamlib`. Owner decision,
2026-09-23: it joins the channel. "One channel" with an exception at the front
door is not one channel.

**It is currently safe, not broken.** `remediation_transaction` gives it
before-image compare-and-swap and restore. So this is a consolidation, not a
rescue — and that means **the bar is semantic parity, not improvement**. If
migrating loses a property the remediation path has, that is a regression even
though the channel is "better".

- [ ] **Step 1: Inventory what `--apply` does that the channel does not**

Read `apply_overrides.py`, `cli.py`'s `--apply` handling, and
`remediation_transaction.py` side by side. List every property the current path
has: override scopes, regeneration scopes, target-path declaration, before-image
restore, the `execution_env` readback added by finding F1. For each, name where
it lands in the channel. **Anything with no home is a blocker — report it rather
than dropping it.**

- [ ] **Step 2: Characterize the CLI contract**

`--apply`'s observable behaviour — exit codes, stdout, the diagnostics it emits,
what it leaves on disk on failure — must not change. Capture it.

- [ ] **Step 3: Migrate, giving the `environment` precondition its second consumer**

The readback from finding F1b runs under `execution_env`; the `environment`
precondition kind exists and has one consumer. This is the second. That also
discharges Task 1 Step 3's note.

---

## Task 6: The eleven tutorials follow through — bypass 1

**Files:** `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/tutorials/` —
`cable_1d_cv_convergence`, `cable_1d_restitution`, `heart_solver_comparison`,
`manufactured_bath_bidomain`, `manufactured_eikonal_ecg`,
`manufactured_monodomain_1d3d`, `manufactured_monodomain_pseudo_ecg`,
`manufactured_monodomain_total_lagrangian_em`, `niederer_2012`,
`restitution_curves`, `single_cell`.

Eleven of the twelve call the appliers Task 2 migrated. `manufactured_purkinje_graph`
is Task 7's.

**Fill in this task's steps from Tasks 2–4's landed code before writing any
production code, and commit the filled-in plan first.**

- [ ] **Step 1: One tutorial end to end, as the pattern**

Start with `single_cell` — three overrides, no mesh, no sidecar. Its `_apply_case`
becomes a `plan_case` that returns assignments instead of writing. Prove
byte-level parity. **That diff is the template for the other ten; put it in the
plan.**

- [ ] **Step 2: The remaining ten, one commit each**

Each with its own characterization test. Where a tutorial's arithmetic is genuinely
bespoke — `cable_1d_restitution`'s two pacing modes, `manufactured_monodomain_1d3d`'s
`blockMeshDict.3D` convention — that arithmetic **stays**; only the write moves.
If a tutorial resists the pattern, report why before inventing a variant.

- [ ] **Step 3: Retire `apply_case` only when the grep is clean**

```bash
grep -rn "apply_case=" packages/*/src/ | grep -v "/build/"
```

Report the count at the start and at the end. Task 8 owns the last one.

---

## Task 7: Source artifacts and sidecars, classified — bypass 1 remainder

Not every write in a tutorial is a parameter. From the measured surface:
7 `shutil.copy`/`copy2`, 4 `write_text`, 1 `json.dump`, 1 `subprocess.run`.

- [ ] **Step 1: Classify each, and route by class, not by uniformity**

- **A copied mesh or graph file is a source artifact**, not a parameter. It
  belongs in `synthesize`'s `source_artifacts`, declared and digested, not
  expressed as a `ParameterAssignment`. Phase 2 deliberately left
  `source_artifacts` un-path-checked because a mesh may live outside the case;
  that decision stands.
- **`cable_1d_restitution`'s `.cardiacfoam_protocol.json` is a standalone
  export** that postprocessing reads **by name**. It needs its own stated
  artifact contract, not the parameter machinery. Find its reader before
  changing anything about it.
- **`.driverfoam_case_id` is a marker**, not an input. Classify and justify.
- **`manufactured_purkinje_graph::_ensure_mesh` shells out to `blockMesh`** to
  author `constant/polyMesh`. A framework-invoked utility authoring a case
  *input* is not a declared workflow output. Decide: does it become a declared
  workflow step in the DAG, or a channel-committed artifact? Argue it.

---

## Task 8: `generic_case.py` — bypass 2

**Files:** `packages/omnidriver/src/omnidriver/core/runtime/generic_case.py`

The last `apply_case` consumer, and the only one in **core**. R4 flagged it as
needing its own design pass, because a generic case has no adapter vocabulary to
resolve against — which is precisely why core owns it.

- [ ] **Step 1: Establish what it may legitimately assume**

A generic case folder declares no catalog. If it cannot produce
`ParameterAssignment`s with real qualified ids, it must not invent them. The
honest options are a `synthesize` request whose content comes entirely from
`RenderedFile` bytes, or an explicit statement that a generic case is not a
framework-authored mutation at all. **Argue which, with evidence from how a
generic case is actually used.**

---

## Task 9: The `describe` seam — the unmet second payoff

**Files:** `packages/omnidriver/src/omnidriver/core/introspection.py`, plus a new
declared seam on the adapter side.

R4 reproduced this and established it is a **contract gap**, not a bug:
`_write_surface` matches supplied keys against catalog qualified ids, but the CLI
hands it raw factory kwargs (`ionic_model`, `electro_property_overrides`).
Passing a flat qualified id instead raises
`TypeError: make_spec() got an unexpected keyword argument`, so catalog-shaped
overrides are not merely unmatched — every factory rejects them. No path in this
codebase produces catalog-shaped overrides from a real invocation.

**`ResolvedMutation.expected_effects` is the other half of this gap.** Task 1
found it computed by both producers — `cardiaccore/workflows/overrides.py` and
`cardiacfoam/dict_builder.py` — and read by nothing: `CaseWritePlan` has no such
field. It was designed in Phase 2 as "what the semantic owner expects this edit
to change", which is exactly what `proposed_changes` needs and cannot currently
get.

So do not treat these as two problems. The kwarg→qualified-id seam answers
*which parameters the caller named*; `expected_effects` answers *what their
owner says will change*. An agent approving a mutation wants both. Give
`expected_effects` a consumer here rather than dropping it as dead — a field
with no reader and a payoff with no data are the same hole from two sides.

If after building the seam `expected_effects` is still redundant, say so with
evidence and remove it; that is a fine outcome. What is not fine is leaving it
computed and unread.

- [ ] **Step 1: Add the seam, not a mapping in core**

Both vocabularies are cardiac, and core may not hardcode a mapping between them.
The adapter or the tutorial spec must declare its kwarg → qualified-id mapping
for `describe` to consult. Generate it from the same catalog entries validation
uses — a second hand-maintained mapping is a second source of truth.

- [ ] **Step 2: Prove the payoff end to end**

`describe --plugin cardiacfoam --entry singleCell --config <real overrides>`
must return non-empty `proposed_changes` naming the qualified ids that will
change and their values. **Paste the output in your report.** Until this passes,
Phase 2's second claimed payoff is unmet, and this task is what closes it.

---

## Task 10: `Allrun`, and delete what is unreachable

- [ ] **Step 1: Route `sweep.py::materialize_case`'s `Allrun` write — bypass 5**

It calls `build_and_launch(..., dry_run=True)` — already channel-routed — then
writes `Allrun` with a bare `write_text` outside it. Smallest bypass; fold it in.

- [ ] **Step 2: Delete `provision_mesh`'s unreachable branch**

R4 established the `BLOCK_MESH_SOLVERS` branch has **zero production callers** —
its only exerciser is `test_solver_mesh_provisioning.py` calling it directly. I
confirmed the sole caller, `ionic_catalog_verification.py`, hardcodes
`singleCellSolver`. Delete the branch and the test that exercises only it, with a
dated note. Unreachable code beside a live route in one function is how the next
reader mistakes one for the other.

**Before deleting, re-run the caller check** — Task 6 may have added one.

---

## Task 11: Close-out, with a widened inventory

- [ ] **Step 1: Widen the inventory script — this is the point**

Phase 2's Task 14 grep did **not** include `open(`, so `openfoam/utils.py`'s
setters, which write via `path.open("w")` and a line-rewrite loop, were invisible
to it. They happened to be inside already-counted tutorials, so the count
survived — but the method did not. The inventory must cover, at minimum:

```
write_text  write_bytes  open(  shutil.copy  shutil.copytree  os.replace
.rename(  .touch(  os.symlink  os.link  json.dump  yaml.dump  pickle.dump
FoamFile(  subprocess.run  subprocess.Popen
```

`foamlib` `__setitem__` and `subprocess`-invoked utilities authoring inputs are
the two classes a naive grep cannot see. Bypass 4 hid behind the first for the
whole of Phase 2.

- [ ] **Step 2: Classify every hit, and list open bypasses explicitly**

Classes: framework-authored case input (bypass if not through
`commit_case_write`), declared workflow output, standalone export, source
artifact, transaction mechanics, framework bookkeeping, test scaffolding. One
line of justification each.

**A bookkeeping file a later run reads as input is not bookkeeping.** R4
spot-checked five and found none miscategorised; check the ones this phase adds.

- [ ] **Step 3: Four shapes, both gates**

```bash
rm -rf /tmp/od311 /tmp/odcore /tmp/wheeltest /tmp/wheelenv
uv venv --python 3.11 /tmp/od311 && VIRTUAL_ENV=/tmp/od311 uv pip install -q \
  -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam \
  -e packages/omnidriver-cardiacfoam -e packages/omnidriver-cardiaccore pytest build
uv venv --python 3.11 /tmp/odcore && VIRTUAL_ENV=/tmp/odcore uv pip install -q \
  -e "packages/omnidriver[post]" pytest
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
```

Known environmental, not a defect: `test_every_core_module_imports_from_a_wheel`
aborts with `SIGABRT` / `dyld: Library not loaded: @rpath/libpython3.11.dylib`,
because `venv.create(with_pip=True)` copies uv's portable CPython whose `@rpath`
cannot resolve from the copy. `symlinks=True` fixes it; a separate session owns
that.

- [ ] **Step 4: Answer the four G3 exit criteria, one line of evidence each**

"Entry/sweep/remediation semantic parity on supported modes; no framework-authored
input bypasses; unsupported modes refuse explicitly; obsolete routes removed."

**If G3 still cannot close, say so and say what remains.** Phase 2's close-out
did exactly that, and it was the right call — a close-out declaring success over
known bypasses converts a known gap into a believed guarantee.

`write_cell_set` is expected to remain open by design. State it as a declared
exception with its reason, not as an oversight.
