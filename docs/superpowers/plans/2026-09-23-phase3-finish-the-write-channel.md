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

**Corrected 2026-09-23:** this line was stale -- Tasks 6 and 6b (see the
"After Task 6b" section below) had already landed when Task 7 started. Tasks
1–7 done (7's commit is pending -- see its own Status row and "Findings").
Tasks 8–11 not started.

**Corrected 2026-09-24:** this line was stale again -- Task 8 had already
landed (see its own Status row and "Findings", committed `9d159fa`) before
Task 9 started. Tasks 1–9 done. Tasks 10–11 not started (explicitly not this
task's scope, per its own instruction: "Do NOT do Tasks 10-11").

| task | what it closes | state | commit |
|---|---|---|---|
| 1 · cut the surface before migrating onto it | over-modelled contract | done | `f476a13` |
| 2 · `apply_entry_overrides` becomes a resolver | the chokepoint, 28 calls | done | `7830529` |
| 3 · `controlDict` setters become resolvers | 11 calls | done | `2fb5805` |
| 4 · `replace_block_mesh_resolutions` | 8 calls, the special case | done | `746f9c0` |
| 5 · `--apply` joins the channel | **bypass 4** | done | `b6fe66f`, `7eb919d` |
| 6 · the eleven tutorials follow through | **bypass 1** (most of it) | pending | — |
| 7 · source artifacts and sidecars, classified | **bypass 1** (remainder) | done | `85fc504`, `8594422`, `e85784c`, `2c3939c`, `570abfa`, `0b7d337`, and this doc's own commit |
| 8 · `generic_case.py` | **bypass 2** | done | this doc's own commit |
| 9 · the `describe` seam | the unmet second payoff | done | `76957fd`, `ee34d5b` |
| 10 · `Allrun`, and delete what is unreachable | **bypass 5** | done | `2fd2499`, `d033399` |
| 11 · close-out, with a widened inventory | G3 | done — **G3 does not close** | this doc's own commit |

**Corrected 2026-09-24 (Task 11 close-out):** the two rows above were still
"pending" in this table at the start of Task 11, even though `2fd2499` and
`d033399` were already on `HEAD` (`d033399` is `HEAD` itself). Task 10's own
checkboxes below were also still unchecked. The work was real and complete;
only this table and those boxes had not caught up. Checked and backfilled
here rather than left stale for the next reader.

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

## Decision, 2026-09-23: close the two gaps Task 2 hit, then delete its fallback

Task 2 delivered the resolver but had to add a blanket `except ValueError` in
`apply_entry_overrides` that reverts to the pre-Task-2 unchecked write. Its
reasoning was sound under its mandate — "keeps its exact signature and write
behaviour" left no room to newly refuse a currently-passing override — and it
documented the fallback honestly rather than hiding it.

**But the effect is that all 28 existing call sites gain zero strictness.** Any
refusal falls back, including a genuine typo or a `nan`. That is the
compatibility-fallback pattern this repository guards with
`test_fallback_census.py` and `test_no_fallback_reaches_cardiac_code_at_all`.
It cannot survive into Task 6, where eleven tutorials migrate onto the strict
resolver.

Both root causes are mine, from Phase 2. Neither is Task 2's fault.

### Gap 1 — the parser I asserted exists, does not

Phase 2's "a parameter value is typed data, never rendered text" decision said:
"Where an adapter currently holds a rendered string, the adapter parses it when
building the request." **No such parser was ever written.** `mutators._format_value`
renders typed data *to* OpenFOAM text and performs security checks; nothing
reads text back. So five tutorials passing
`"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"` for a `dimensioned_tensor` hit a
validator that requires `{"value": ..., "dimensions": ...}` and always will.

**Fix: write the inverse of `_format_value`, in `omnidriver-openfoam`.** OpenFOAM
owns dimensioned-literal syntax; core must never learn it. Parse
`[d0 d1 d2 d3 d4 d5 d6] <magnitude>` into
`{"value": <scalar or tuple>, "dimensions": (d0..d6)}`, with the seven-exponent
count enforced. A literal that does not parse is refused, not guessed.

Keep the rendered spelling reachable — F1b established that comparing values as
text is wrong but that **the raw spelling is still evidence**. Round-tripping
parse→render must reproduce the original for every literal in the catalog;
prove it over the real entries, not a fixture.

### Gap 2 — `allowed_bindings` assumed every dynamic segment has a closed domain

`<ventKey>` is `("lv", "rv")` — closed, enumerable, correct. But the catalog also
declares `$ELECTRO_MODEL_COEFFS.ecgDomains.<name>.ecgSolver` and
`...ecgDomains.electrodePositions.<electrode>`, where `<name>` is a user-chosen
domain name and `<electrode>` a user-chosen label. **The case defines them; the
catalog cannot enumerate them.** Phase 2's model has no way to say so, so
`DictEntry.__post_init__` refuses to declare them at all.

**Fix: let a binding domain be declared open, explicitly.** `allowed_bindings`
gains a way to say "any valid OpenFOAM word" — for example `None` as the domain,
distinct from an absent key. The distinction that matters is not
open-versus-closed; it is **declared** versus **silently unconstrained**. Audit
finding S1 was that `banana` passed as a ventricle because nothing was declared.
An explicitly open domain is a stated fact an agent can read; an undeclared one
is a hole. A binding against an open domain is still validated as a word —
non-empty, no whitespace, and `_format_value`'s existing `;`/`#` refusals apply.

### Then delete the fallback

With both gaps closed, `apply_entry_overrides` refuses what
`resolve_entry_overrides` refuses. Remove the `try/except ValueError` and the
duplicated write loop. **If a currently-passing test then fails, that test is the
finding** — it encodes an override the catalog does not declare, and this
repository's rule is to correct it with a dated note and add a test for the
corrected behaviour, not to restore the fallback.

One exception is legitimate and must be stated rather than absorbed: if a real
override genuinely cannot be expressed after both gaps close, report it and stop.
Do not reintroduce a general fallback for a specific unsolved case.

### Findings, 2026-09-23

**Commit 1 — the parser.** `omnidriver.openfoam.literals` (new module)
parses both magnitude shapes the real catalog declares: a bare scalar
(`stimulusIntensity`: `"[0 -3 0 0 0 1 0] 75000"`) and a parenthesised tensor
(`conductivity`: `"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"`). Round-tripped
over every dimensioned literal actually found in this repository (the
catalog's own `typical_value` strings, the tutorials' default
conductivities, and the literals real tests pass as overrides —
`packages/omnidriver-openfoam/tests/test_literals.py`'s
`REAL_DIMENSIONED_LITERALS`), not a fixture invented for this task.

**The round trip is value-identical for all of them, and byte-identical for
all but three, found and named rather than hidden**
(`KNOWN_BYTE_ROUND_TRIP_EXCEPTIONS`): two whole-number magnitudes spelled
with an explicit `.0` (`"2.0"`, `"1.0"`) that a float cannot distinguish
from `"2"`/`"1"`, and one literal
(`test_manufactured_eikonal_ecg_tet.py`'s conductivity override) that also
pads its brackets with spaces. This repository's own real literals use both
the with-decimal and without-decimal convention for a whole-number
magnitude, so no single renderer reproduces both — confirming, on this
task's own evidence, F1b's point (Phase 2's decision) that comparing
*spellings* rather than *values* is the wrong axis. `apply_entry_overrides`
therefore keeps the original spelling as `ParameterAssignment.evidence_refs`
("the raw spelling is still evidence") and writes it back verbatim,
rather than a re-rendering, whenever one was parsed from text — proven by
`test_tet_apply_case_forwards_conductivity_and_advection_approach`, which
asserts the exact original string appears in the written file.

**Three corollary gaps, found while closing Gap 2, not anticipated by
either decision.** Making the ecgDomains dynamic path resolve at all
exposed that its `vector3` entry (`electrodePositions.<electrode>`) has the
same "adapter never parses the rendered string" defect Gap 1 named for the
dimensioned kinds — a real test (`test_dict_entries_catalog.py`) passes
`"(1 2 3)"`, not a tuple. Running the fix further exposed the same for
`integer_list` (`verificationModel.checkQuadratureOrders`: `"(6 12 24 48)"`)
and `boolean` (`eikonalAdvectionDiffusionApproach`: `"false"`, an OpenFOAM
`Switch` spelling, not a Python `bool`). All three handled the same way, in
the same module, with their own round-trip tests
(`test_literals.py`); `word_list`/`scalar_list`/`vector3_list` added
alongside `integer_list` on the same reasoning even though no real caller
happens to exercise them today, since leaving three of four list kinds
unparsed for no principled reason would just relocate this same defect to
whichever one is used next.

**The `boolean` formatter is deliberately NOT used to re-render an
already-typed value.** `mutators._format_value` already renders a plain
Python `bool` correctly (`"yes"`/`"no"`), and several real overrides pass
one directly (`verificationModel.enabled`, `verificationModel.anisotropic`
below) — using `format_boolean_literal` there instead would have written
`"true"`/`"false"` and broken every currently-passing test asserting
`"yes"`/`"no"`. Found by running the suite (`test_tet_mesh_family_works_with_ecg_enabled`
failed first), not assumed; `overrides.py` keeps two separate dispatch
tables (`_TEXT_PARSERS`, used for parsing; `_CONTAINER_FORMATTERS`, used
for re-rendering an already-typed value with no preserved evidence) for
exactly this reason.

**Commit 2 — the open-domain mechanism.** `DictEntry.allowed_bindings`'s
value type widened to `tuple[str, ...] | None`; `None` is an explicitly
open domain, distinct from the placeholder being absent from the mapping
altogether. `__post_init__`'s empty-domain refusal now exempts `None`
(`if domain is not None and not domain`) while every other check (partial
declaration, unknown placeholder, static-path bindings) is unchanged.
`omnidriver-cardiacfoam`'s `overrides.py` gained a real matcher for it: a
concrete override that fails both exact lookups is tried against every
`dynamic_path` catalog entry via `omnidriver.openfoam.dict_builder.match_dynamic_entry`
(added there — reused, not duplicated, alongside that module's existing
`is_known_override_driver_path`, which already had the same wildcard regex
convention for a bare membership check), and each captured placeholder is
validated against `entry.allowed_bindings` by `_validate_dynamic_binding`:
absent → refused; `None` → validated as a word plus
`mutators.check_dictionary_word_is_safe`'s `;`/`#`/newline refusal (new
public function, reusing `_format_value`'s existing checks rather than
duplicating them, because a binding becomes a **key**, and `_format_value`
only ever inspects a written **value**); a closed tuple → membership.

**Every entry declared, not just the two named ones.** All 78
`dynamic_path` declarations in `dict_entries_catalog.py` (not only
`ecgDomains`) now state their placeholder's domain explicitly: `<name>`
(`ecgDomains`, `conductionNetworkDomains`, `domainCouplings`), `<electrode>`,
`<patch>` (`bathPotentialDomain`'s ground/surface-current patch maps),
`<region_name>` (`ionicHeterogeneity`), `<constant_name>` and `<state_name>`
(model-specific constant/state names enumerated by a *different* catalog
this one cannot reach) are all open (`None`) — genuinely case- or
model-author-chosen, with no closed enumeration this catalog itself can
state. One placeholder turned out to have a real closed domain instead:
`<scope>` (`ionicConstantOverrides.<scope>.{scale,set}.<constant_name>`) is
declared `("global", "epicardialCells", "mCells", "endocardialCells",
"myocyte")` — the entries' own pre-existing `constraints` text already
named this exact list (citing `ionicModelIO.C:182-189`), so this is a
correction from silently-open to correctly-closed, not a new open
declaration.

**Found, out of scope for this task, not fixed:** `omnidriver-cardiaccore`'s
`catalogs/inputs.py` declares `$PURKINJE_SCAR.regions.<region_id>.*` (four
entries) as `dynamic_path=True` with no `allowed_bindings` at all — the
same undeclared-placeholder shape Gap 2 closed here, in the sibling
package. Not touched: cardiaccore's own matcher
(`workflows/overrides.py::_template_for`) does not consult
`allowed_bindings` for matching at all (it hardcodes `VENT_KEYS` instead),
so this is a purely declarative gap there, unconnected to the mechanism
this task changed, and cardiaccore is outside Task 2/3's mandate.

**Commit 3 — the fallback is gone.** `apply_entry_overrides`'s
`try/except ValueError` and its duplicated pre-Task-2 write loop are
deleted; it now calls `resolve_entry_overrides` unconditionally and refuses
exactly what that function refuses. Verified by reverting: temporarily
restoring the pre-fix `dict_entries_catalog.py` reproduces the ecgDomains
failure with `_catalog_entry_for` returning no match; temporarily emptying
`_TEXT_PARSERS` reproduces exactly the six tests Task 2 named, no more and
no fewer.

**The six previously-failing cases, all passing strictly:**

| case | fix |
|---|---|
| `ecgDomains.ECG.electrodePositions.V1` (dynamic identifier) | Gap 2 (dynamic match) + vector3 corollary |
| `test_dict_entries_catalog.py`'s conductivity/stimulusIntensity literals | Gap 1 (dimensioned parser) |
| `test_tet_apply_case_forwards_conductivity_and_advection_approach` (eikonal) | Gap 1 + boolean corollary |
| `test_conductivity_shorthand_updates_monodomain_tensor` (pseudo-ecg) | Gap 1 |
| `test_tet_mesh_family_works_with_ecg_enabled` / `test_ecg_disabled_removes_block_from_a_reused_entry_case` | integer_list corollary + one catalog gap (below) |
| `test_tet_apply_case_renders_geo_installs_overlay_and_grad_scheme` | catalog gap (below) |

**One test failure was a genuine catalog gap, corrected with a dated
note, not a test correction** (per this task's own instruction: "if a
currently-passing test then fails, that test is the finding"). Four tests
failed with "override
`...verificationModel.anisotropic` is not declared" —
`dict_entries_catalog.py` had never declared this key, even though
`manufacturedPseudoECGVerifier.C:420`
(`cfg.lookupOrDefault<Switch>("anisotropic", false)`, checked against the
authoritative native tree,
`~/noFrontendCardiacFoam_minor_errors/src/verificationModels/ecgVerification/manufacturedPseudoECGVerifier.C`)
genuinely reads it, and `manufactured_monodomain_pseudo_ecg.py`'s
`_apply_case` has written it unconditionally whenever `ecgDomains.ECG` is
configured since before this task. Added the missing `DictEntry` (dated
correction comment in place), scoped to `manufacturedPseudoECGVerifier`
only via `applicable_when` (confirmed by source: `manufacturedEikonalECGVerifier.C`/
`manufacturedBathBidomainECGVerifier.C` do not read it). No test needed a
behaviour correction — the four tests' own assertions were already correct;
only the catalog was missing the declaration they depended on.

**All four required shapes: 0 failed** (aside from the documented
environmental `ensurepip` abort in `test_every_core_module_imports_from_a_wheel`,
present before this task and unrelated to it). Both static gates pass.

## Task 3: The `controlDict` setters become resolvers

**Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/utils.py`
- Create: `packages/omnidriver-openfoam/tests/test_control_dict_resolution.py`

`set_delta_t` and `set_end_time` are two-line wrappers around
`update_foam_entry`. 11 calls across the tutorials.

- [x] **Step 1: Add `plan_delta_t` / `plan_end_time` beside them**

Returning a `ParameterAssignment` each, for `system/controlDict`'s `deltaT` and
`endTime`, `value_kind="scalar"`. Keep the writing versions until Task 6
migrates their callers, then retire them in the same commit that removes the last
caller.

- [x] **Step 2: Note the overlap with slice B and do not duplicate it**

`dict_builder`'s synthesis path already renders `controlDict` with both its
template content and its `deltaT`/`endTime` edits folded into one `RenderedFile`
— that was Phase 2's `repeated_edits_to_one_file` case in its real setting. Reuse
that folding rather than writing a second one. If the two cannot share, say why.

### Findings, 2026-09-23

**Step 1 — signatures, and the two decisions the plan left open.**
`plan_delta_t(delta_t_seconds: float, *, owner: str) -> ParameterAssignment`
and `plan_end_time(t_s: float, *, owner: str) -> ParameterAssignment`, added
beside the two-line writers in `utils.py`. No `control_dict_path` parameter —
unlike `resolve_entry_overrides` (which takes `document` from its caller
because it has only a bare `file_path` and no case root to derive one from),
these two need no path at all: `system/controlDict` is a fixed, case-relative
location, the same for every case, so it is hardcoded (`_CONTROL_DICT_DOCUMENT`)
rather than threaded through a parameter with nothing genuine to vary.

`owner` is a required keyword, not a default. `utils.py` lives in
`omnidriver-openfoam`, which this repository's own package table says "must
not know about cardiology" — so it cannot hardcode `"org.cardiacfoam"` the
way `dict_builder.py` does for its own `ParameterAssignment`s (that module
lives inside `omnidriver-cardiacfoam` and owns that identity). No
`PLUGIN_ID`-equivalent constant exists anywhere in `omnidriver-openfoam`
today (checked: `grep -rn "PLUGIN_ID\|adapter_id=" packages/omnidriver-openfoam/src/`
finds none) — inventing a generic one with no second consumer would repeat
the mistake Task 1 just cut (`generated_input`). Supplied, not discovered.

**`source` — verified constant, for a different reason than Task 2's
resolver.** Every assignment these two build has `source="case"`. Unlike
`dict_builder.py`'s synthesis resolver, which genuinely branches
(`source="case" if delta_t is not None else "template"`, because IT supplies
a built-in default — `1e-4`/`1.0` — when its own caller passes `None`),
`plan_delta_t`/`plan_end_time` have no optional parameter and no fallback of
their own: `delta_t_seconds`/`t_s` are required, exactly like
`set_delta_t`/`set_end_time`'s existing parameters. Every value they ever see
is one a caller explicitly chose to assign, so there is no branch to make —
matching `resolve_entry_overrides`'s reasoning for the same conclusion
("this function has no fallback of its own").

**Can a `controlDict` value arrive as a rendered string here? Checked, not
assumed: no.** `grep -rn "set_delta_t\|set_end_time"` across all eleven real
tutorial call sites (`restitution_curves.py`, `manufactured_bath_bidomain.py`,
`niederer_2012.py`, `manufactured_monodomain_pseudo_ecg.py`,
`manufactured_eikonal_ecg.py`, `manufactured_monodomain_total_lagrangian_em.py`,
`cable_1d_restitution.py`, `manufactured_monodomain_1d3d.py`,
`cable_1d_cv_convergence.py`) shows every one already computes and passes a
native Python `float` (`float(case.params["dt"])`, `dt_ms * 1.0e-3`, arithmetic
on floats) — never an already-rendered OpenFOAM literal string. This differs
from Task 2's Gap 1 (`dimensioned_scalar`/`dimensioned_tensor`/`vector3`
catalog entries, whose real callers pass literal text like
`"[-1 -3 3 0 0 2 0] (0.2 0 0 0.03 0 0.03)"`) for a structural reason: a bare
`controlDict` scalar has no OpenFOAM-specific literal grammar at all — no
dimension brackets, no parenthesised magnitude — so there is nothing here
for `omnidriver.openfoam.literals` to parse. Accordingly `plan_delta_t`/
`plan_end_time` take `float` only (matching `set_delta_t`/`set_end_time`'s
existing parameter types exactly), populate no `evidence_refs`, and there is
no "original spelling" distinct from the Python float value itself to
preserve — confirmed by a characterization test showing `1e-3` and `0.001`
already collapse to identical output bytes today (`_format_value` renders a
float with `str()`, and `1e-3 == 0.001` is the same float). If a future
caller (Task 6) needs to pass a rendered string, `validate_value_shape`
refuses it outright (not a `Real`) rather than silently accepting or
guessing — the same strict-resolver posture Task 2 established, not a new
gap.

**Does `dict_builder.py`'s `controlDict` folding consume these planners? No
— and it is not supposed to, by this task's own file scope** (the plan lists
only `utils.py` and a new test file for Task 3; `dict_builder.py` is not
listed). Read in full before concluding this
(`resolve_synthesis_mutation` and `build_and_launch`'s parameter-building
loop, `dict_builder.py:943-1057` and `:1227-1275`): the fold answers a
different question than the planners do. `plan_delta_t`/`plan_end_time`
assume `system/controlDict` **already exists** and unconditionally address
its real `deltaT`/`endTime` keys — exactly what the eleven tutorial callers
need, patching a file a template already rendered. `dict_builder.py`'s
synthesis path has **no existing file to patch**; it must decide what
content to author from scratch, using a built-in default (`1e-4`/`1.0`) when
the caller gave none, and *additionally* fold in a second, redundant edit
target only when the caller gave an explicit value — reproducing a real
pre-migration double-write bug byte-for-byte
(`test_synthesis_through_the_channel.py`). That base/patch duality is encoded
in its own private `ParameterAssignment` convention
(`key_path=("deltaT_base",)` / `("deltaT_patch",)`, `qualified_id=
"$CARDIACFOAM.control.deltaT_base"`) that `resolve_synthesis_mutation` alone
unpacks into `control_values` before building `build_control_dict(...)`'s
freshly authored text — a content-authoring decision no planner addressing a
concrete `("deltaT",)` key against an existing document can make. The
**mechanism** that folds multiple edit targets addressing one document into
a single `RenderedFile` (`case_rendering.py`'s `_document_edits` /
`render_synthesis_case_files`) is genuinely shared already, by both
`resolve_patch_mutation` (cardiacCore's `clone_and_patch` producer) and
`resolve_synthesis_mutation` — this task adds no second copy of *that*, which
is the duplication the plan actually warns against. A smaller, optional
reuse **is** available and was deliberately left for a later task rather
than done here: `dict_builder.py` could build its `deltaT_patch`/
`endTime_patch` target dicts by calling `plan_delta_t`/`plan_end_time` and
reading `.document`/`.expanded_key_path()`/`.value` off the result, instead of
writing the literal key `"deltaT"`/`"endTime"` a second time — genuine, but
out of this task's file scope (`dict_builder.py` is not listed as a file
Task 3 modifies), and changing that module's synthesis path is a
Task 6/7-shaped decision, not this one's.

**Characterization (Step 2 of the report, not of this checklist).**
`test_control_dict_resolution.py` pins `set_delta_t`/`set_end_time`'s exact
output by content digest for both spellings of the same float
(`1e-3`/`0.001`), and separately proves those two spellings already collapse
to identical bytes today — a real, verified writer behaviour: `update_foam_entry`
rewrites a whole-line entry as `<indent><key>    <value>;` (four spaces, not
the original column alignment; confirmed by direct execution, not assumed —
`deltaT          1e-06;` becomes `deltaT    0.001;`, `endTime         1;`
becomes `endTime    250.0;`, `str(250.0)`'s `.0` carried through). Both pass
before and unchanged after this task's change. Verified by reverting
`utils.py` alone: exactly the twelve planner tests fail (`NoneType` not
callable, since the test module's planner import falls back to `None` when
`plan_delta_t`/`plan_end_time` do not exist yet), the four characterization
tests still pass — no more and no fewer failures either way.

**All four shapes, 0 failed** (core-only shape's
`test_every_core_module_imports_from_a_wheel` aborts in `ensurepip`,
documented pre-existing and environmental, unrelated to this task — this
task touches no core module). Both static gates pass.

---

## Task 4: `replace_block_mesh_resolutions` — the one genuine special case

**Files:**
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/utils.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_rendering.py`

This one is **not** a key/value set. It rewrites lines beginning `hex (` inside
an existing `blockMeshDict`, validating that exactly `expected_blocks` were
replaced. A `ParameterAssignment` cannot express it, and inventing a value kind
for it would be the `openfoam_literal` layering mistake again.

- [x] **Step 1: Decide its shape, on evidence**

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

- [x] **Step 2: Characterize against a real `blockMeshDict`, then migrate**

Include the `expected_blocks` validation — silently replacing the wrong number of
blocks is the failure this function exists to prevent.

### Findings, 2026-09-23

**Chose candidate 2, and the plan's own framing of candidate 1 undersells
how badly it fails.** The plan asked to check
`manufactured_monodomain_1d3d` for whether it patches a document the
framework did not author, as a possible exception to candidate 1. Checked
against the authoritative native tree (`~/noFrontendCardiacFoam_minor_errors`,
per this repo's "authoritative native trees" convention) for all eight real
`replace_block_mesh_resolutions` call sites, not just that one: every single
one patches a tutorial-authored `blockMeshDict` with its own vertices and
boundary patches (`bathBidomain/system/blockMeshDict.3D`: three ``hex (``
blocks, vertices `(-1 0 0) (0 0 0) (1 0 0) (2 0 0)...`, boundary
`xMin`/`xMax`/`sides`; `monodomain1D3D/system/blockMeshDict.3D`: one ``hex (``
block, boundary `inlet`/`outlet`/`sides`) -- nothing like
`default_block_mesh_dict_text`'s generic one-block slab with a single
`walls` patch, which its own docstring already calls "not tuned to any
specific tutorial's science". **There is no split between the eight call
sites**: the plan's "two cases may genuinely need different answers"
possibility does not apply here, because all eight need the same answer.
`manufactured_monodomain_1d3d` differs only in copying `blockMeshDict.3D` to
`blockMeshDict.3D.active` before patching that copy -- a detail of *which*
document the eventual Task 6 resolver names, not a reason for a different
target shape. Candidate 1 is not viable for any of the eight; candidate 2 is
viable for all of them.

**The shape.** `utils.plan_block_mesh_resolution(document, cell_counts_str,
*, expected_blocks=1)` is a pure function returning a plain
`Mapping[str, Any]` -- `{"document", "format", "hex_cell_counts",
"expected_blocks"}` -- not a `ParameterAssignment`. This needed no change to
`core.case_write` at all: `ResolvedMutation.targets` is already a
loosely-typed mapping per target (`dict_builder.resolve_synthesis_mutation`'s
own raw `{"document", "content", "format"}` targets are the existing
precedent), consumed only by `case_rendering._document_edits`, which never
assumed every target is a `ParameterAssignment`. `case_rendering.
render_patch_case_files` now recognizes a target carrying
`"hex_cell_counts"` and applies `utils._rewrite_hex_block_lines` (the
algorithm factored out of `replace_block_mesh_resolutions`, reused rather
than re-implemented) instead of `update_foam_entry`, validating
`expected_blocks` against what it actually found in the real document --
the same check the function always made, now made by the renderer because
that is where the real file is read. At most one hex target per document is
accepted; a second is refused (`render_patch_case_files` raises), for the
same "which one survives depends on ordering" reason
`CaseMutationRequest` already refuses two `ParameterAssignment`s at one
slot.

**No `source` field.** A raw `ResolvedMutation` target carries no
`VALUE_SOURCES` vocabulary at all -- neither this target nor
`dict_builder.py`'s own synthesis targets have one. `source` classifies
where a *value* a caller assigned came from; this target assigns no value,
it names a structural rewrite and the count it must satisfy. There was
nothing to determine here, and forcing a `source` field onto it would be
inventing a distinction the shape does not have, the same mistake Phase 2's
`generated_input` mode made (Task 1's finding).

**`replace_block_mesh_resolutions` (the writer) kept, not retired.** Same
pattern Task 3 established for `set_delta_t`/`set_end_time`: the writer
keeps writing directly for its eight tutorial callers until Task 6 migrates
them onto the render/commit channel; both the writer and the new resolver
are retired together, in the same commit that removes the last caller.

**Corrected 2026-09-23, in passing.** The pre-Task-4 writer wrote each
rewritten line to disk as it iterated, so a mismatched `expected_blocks`
still raised, but only after the file had already been overwritten with the
(wrong-count) rewrite -- an undocumented side effect no test pinned
(`test_missing_hex_line_raises` never read the file back). Refactoring onto
`_rewrite_hex_block_lines` (which computes the full rewritten text in memory
before anything is written) means a raised `KeyError` now leaves the file
untouched. This is a behaviour change on the error path, verified against no
currently-passing test, so it is recorded as a correction rather than
silently carried forward.

**Characterization: real content, not an invented fixture.** Per this
repo's "no invented-geometry tests" rule,
`packages/omnidriver-openfoam/tests/core/test_block_mesh_resolution_channel.py`
embeds `bathBidomain/system/blockMeshDict.3D`'s real bytes (transcribed from
the native tree, digest-checked against a cited sha256 by its own first
test) rather than a single-block fixture -- deliberately chosen because it
has three `hex (` blocks, so `expected_blocks=1` vs `expected_blocks=3` is a
real distinction, not one a single-block fixture could exercise. Tests
against this fixture: the direct writer's byte-exact output (characterization,
passed before this task's change and passes unchanged after -- verified,
not assumed: `test_common_blockmesh_resize.py`'s four pre-existing tests
also pass unchanged), `expected_blocks` mismatch still refuses (both via the
writer and via the renderer), and the renderer's output is byte-identical to
the direct writer's for the same real content and request -- the actual
migration proof.

**Verified by reverting**, not by assuming: `git stash` on both modified
files reproduced an `ImportError: cannot import name 'plan_block_mesh_
resolution'` at collection for all ten new tests, with every pre-existing
test in the package (including `test_common_blockmesh_resize.py`'s four)
unaffected. Restoring the change returns all ten to green.

**All four required shapes: 0 failed** (the documented environmental
`ensurepip` abort in `test_every_core_module_imports_from_a_wheel` aside,
present before this task and unrelated to it). Both static gates pass.

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

- [x] **Step 1: Inventory what `--apply` does that the channel does not**

Read `apply_overrides.py`, `cli.py`'s `--apply` handling, and
`remediation_transaction.py` side by side. List every property the current path
has: override scopes, regeneration scopes, target-path declaration, before-image
restore, the `execution_env` readback added by finding F1. For each, name where
it lands in the channel. **Anything with no home is a blocker — report it rather
than dropping it.**

- [x] **Step 2: Characterize the CLI contract**

`--apply`'s observable behaviour — exit codes, stdout, the diagnostics it emits,
what it leaves on disk on failure — must not change. Capture it.

- [x] **Step 3: Migrate, giving the `environment` precondition its second consumer**

The readback from finding F1b runs under `execution_env`; the `environment`
precondition kind exists and has one consumer. This is the second. That also
discharges Task 1 Step 3's note.

### Findings, 2026-09-23

**Step 1 inventory — where each property lands.** Read `apply_overrides.py`,
`cli.py`'s `--apply` handling, `step_candidate.py` (the real call site —
see the corrected plan claim below) and `remediation_transaction.py` side
by side.

| property | today | lands in the channel as |
|---|---|---|
| Override scopes (`$TOKEN.` key-patch, `OverrideScope.resolve_entry`) | reads/writes `case_root` directly | Unchanged mechanism, now given a private snapshot copy instead of `case_root` (see progressive-visibility note below) |
| Regeneration scopes (bare-selector full-file rebuild) | `regenerate()` rewrites `case_root/file_relpath` directly | Same callable, called on the snapshot copy; its own selector value is *also* represented as a `ParameterAssignment` for the audit trail |
| `get_override_target_paths` (the crash-safety pair `_check_cross_member_pairs` enforces) | computes the finite write set before any write | Unchanged — still the same function, still paired with `apply_overrides` on one provider; reused to pick which documents to snapshot |
| Before-image restore | `apply_overrides.py`'s own `_restore_on_failure`, in-process only, no crash recovery | `commit_case_write`'s journal. Strictly stronger: `case_root` is never touched at all until the final atomic replace (today it's touched then restored), and a mid-commit crash is now recoverable, which `_restore_on_failure` never provided. `_restore_on_failure`/`_apply_validated_overrides` are removed (confirmed gone by `test_the_pre_channel_direct_write_helpers_are_removed`) |
| F1 `execution_env` readback | loop after the direct write succeeds | Unchanged loop, repositioned to run after `commit_case_write` succeeds |
| F1b typed comparison (`effective_values_agree`) | same loop | Unchanged |
| `environment` precondition's second consumer | no precondition machinery on this path | New: `apply_overrides.py` calls `case_rendering.patch_preconditions` before building the plan — the same function cardiacCore's Task 8 consumer already calls |
| `;`/`#`/newline security refusal (SECURITY.md) | `_format_value` inside `update_foam_entry` | Unchanged — still applied automatically; nothing bypasses it |
| Case lease / serialization | `cli.py`'s `_dispatch_context` holds the case lease for the whole `step`; `apply_overrides.py` never acquired one itself | **The one property with no home without a core change.** `commit_case_write`'s own lease is not reentrant from the same thread (`acquire_case_lease` finds its own lock file and refuses it), so calling it unmodified from inside `--apply`'s already-held lease would refuse itself on every call — a guaranteed regression, not a hypothetical (confirmed by reproducing the refusal directly). Closed by giving `commit_case_write` an explicit, opt-in, **verified** `case_lease_held: bool = False` parameter (`core/case_transaction.py`, commit `b6fe66f`, its own commit because it changes shared machinery every future consumer inherits) — a caller claiming to already hold the lease without holding it is refused loudly (`case_lease_is_held` checked, never trusted), and every existing caller omitting the parameter is byte-identical to before. Three alternatives were considered and rejected: making `acquire_case_lease` itself silently reentrant (weakens `test_a_second_attempt_under_a_held_lease_is_refused`, an existing guard); releasing `cli.py`'s lease around override-application (opens a real race window `remediation_transaction.py`'s own lease-held assertions already rely on not existing); duplicating `commit_case_write`'s write/journal logic lease-free inside `apply_overrides.py` (DRY-violating, strictly riskier, no less "shared surface" than an opt-in parameter). |

Everything else found a home; nothing was dropped as a blocker.

**Step 2 — the CLI contract.** `cli.py` and `step_candidate.py` were read
and neither needed to change. `cli.py::_execute_step` only parses the
`--apply` JSON payload and wraps any exception from
`execute_step_candidate_owned` as `{"status": "failed", ..., "error":
f"--apply rejected: {exc}"}` with exit code 1 (0 on success) —
`step_candidate.py::execute_step_candidate_owned` (not `cli.py` — see
below) is what actually calls `override_scopes.apply()`. Since
`apply_overrides()` kept its exact external signature and return shape
(same evidence-tuple keys, same `OverrideError` type for every failure
category), this wrapping is unaffected. The one behaviour that is
observably different: the wrapped `FileNotFoundError` text for a missing
document now names the private snapshot path instead of the real
`case_root` path (no test pins the exact text either way). What's left on
disk on any failure changed for the *better*, not differently, and is
tested directly (`test_a_failure_partway_through_a_batch_leaves_case_root_
completely_untouched`, `test_regeneration_failure_leaves_case_root_
untouched`, `test_a_change_between_precondition_capture_and_commit_
refuses_the_apply`): `case_root` is left exactly as it was before the
call, in every failure mode exercised, including one (precondition drift)
that did not exist as a concept before this task.

**Corrected plan claim, 2026-09-23.** This task's own brief said to read
"`cli.py`'s `--apply` handling" for the call site. That is incomplete:
`cli.py` only parses the JSON payload; the actual call chain
(`execute_step_candidate_owned` → `override_scopes.apply()` →
`apply_overrides.apply_overrides()`) lives in
`core/runtime/step_candidate.py`, which the plan's file list never named.
Neither file needed to change in the end, but the read target was wrong.

**F1/F1b, verified against the real install, not a fixture.**
`test_apply_readback_matches_the_real_foamdictionary`
(`test_apply_through_the_channel.py`) sources the real OpenFOAM v2412
install at `/Volumes/OpenFOAM-v2412` via `discover_openfoam_bashrc()` +
`load_openfoam_environment()`, applies `deltaT="1e-3"`, and asserts the
real `foamDictionary` reports back `"0.001"` while `matches_requested` is
still `True` (F1b: values compared, not spellings) — and that the file on
disk keeps `"1e-3"` verbatim (Gap 1). This test is not skipped in this
environment; it ran against the real binary.

**The `environment` precondition's second consumer, confirmed
functionally.** `test_environment_precondition_is_a_genuine_second_
consumer` gives `--apply` a dict carrying a real `#includeEtc` directive
and asserts an `environment`-kind `Precondition` actually appears in what
`case_rendering.patch_preconditions` returns — not merely that the
function was invoked.

**Verified by reverting.** Stashing `apply_overrides.py` alone reproduces
exactly 4 of the 17 new tests failing —
`test_a_change_between_precondition_capture_and_commit_refuses_the_apply`,
`test_environment_precondition_is_a_genuine_second_consumer`,
`test_apply_file_path_route_refuses_a_value_with_no_closed_shape`,
`test_the_pre_channel_direct_write_helpers_are_removed` — exactly the
genuinely-new properties this task adds, nothing else; every parity test
(byte-identical writes, empty-overrides no-op, missing-target error,
mid-batch-failure isolation, regeneration structural rewrite, lease reuse)
passes against both the old and the new code, which is what "parity, not
improvement" being satisfied actually looks like as evidence rather than
assertion.

**All four shapes: 0 failed** (aside from the documented environmental
`ensurepip` abort in `test_every_core_module_imports_from_a_wheel`,
present before this task and unrelated to it — confirmed unchanged: same
single `SIGABRT` failure, same test). Both static gates pass. Commits:
`b6fe66f` (the `case_lease_held` core change, reviewable on its own) and
`7eb919d` (the `apply_overrides.py` migration itself).

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

- [x] **Step 1: One tutorial end to end, as the pattern**

Start with `single_cell` — three overrides, no mesh, no sidecar. Its `_apply_case`
becomes a `plan_case` that returns assignments instead of writing. Prove
byte-level parity. **That diff is the template for the other ten; put it in the
plan.**

- [x] **Step 2: The remaining ten, one commit each**

Each with its own characterization test. Where a tutorial's arithmetic is genuinely
bespoke — `cable_1d_restitution`'s two pacing modes, `manufactured_monodomain_1d3d`'s
`blockMeshDict.3D` convention — that arithmetic **stays**; only the write moves.
If a tutorial resists the pattern, report why before inventing a variant.

- [x] **Step 3: Retire `apply_case` only when the grep is clean**

```bash
grep -rn "apply_case=" packages/*/src/ | grep -v "/build/"
```

Report the count at the start and at the end. Task 8 owns the last one.

### Findings, 2026-09-23

**The shape, derived from Tasks 2–5's landed code, not assumed.**
`resolve_entry_overrides` (Task 2) already returns typed `ParameterAssignment`s;
`plan_delta_t`/`plan_end_time` (Task 3) and `plan_block_mesh_resolution` (Task 4)
do the same for `controlDict` and the hex-block rewrite. What Task 6 needed
was the missing middle: a `clone_and_patch` **resolver** for cardiacFoam
(cardiacCore already has one, `workflows/overrides.py::resolve_patch_mutation`,
from Phase 2) and a shared **commit** helper every tutorial's `plan_case`
calls once. Both landed in `cardiacfoam/overrides.py`:

- `_write_value_for_assignment(assignment)` — extracted, not duplicated, from
  `apply_entry_overrides`'s own write loop. Returns `assignment.evidence_refs[0]`
  when present (the preserved original spelling, Task 2 Gap 1), else a
  `_CONTAINER_FORMATTERS`-rendered value, else the raw value. **This is the
  one fact that makes byte parity possible for a dimensioned/vector3/list
  override**: `case_rendering.render_patch_case_files`'s generic
  `update_foam_entry(..., edit["value"], ...)` would otherwise be handed
  `ParameterAssignment.value` (the *typed* value — a tuple, a
  `{"value":..., "dimensions":...}` mapping) and render it differently from
  what `apply_entry_overrides` always wrote. cardiacCore's own
  `resolve_patch_mutation` can pass `parameter.value` straight through
  because none of its parameters carry `evidence_refs` or need container
  formatting; cardiacFoam's can, so its resolver cannot copy that shortcut.
- `resolve_patch_mutation(request) -> ResolvedMutation` — cardiacFoam's own
  `clone_and_patch` resolver, mirroring cardiacCore's in shape, differing
  in exactly that one line (`"value": _write_value_for_assignment(parameter)`
  instead of `parameter.value`).
- `merge_assignments(*groups)` — collapses several `ParameterAssignment`
  sequences addressing the same document to their final per-slot value,
  later group wins. Needed because `CaseMutationRequest` refuses two
  parameters at one slot outright, but several tutorials (`single_cell`
  included) apply two override sets to the same document in sequence today,
  the second legitimately overwriting the first at a shared key — the same
  "later write wins" behaviour two sequential `apply_electro_property_overrides`
  calls already have.
- `commit_case_overrides(case_root, *, parameters, extra_targets=(), extra_effects=(), workflow, requested_by, driver_context=None, execution_env=None)`
  — one channel-routed commit per tutorial case. Reaches
  `resolve_patch_mutation`/`case_rendering.render_patch_case_files` the same
  way `dict_builder.build_and_launch` already reaches its own synthesis
  resolver: `driver_context.capabilities.case_writer.resolve`/`.render`, not
  a direct function call — which required declaring the capability, below.
  `extra_targets`/`extra_effects` fold in a target `resolve_patch_mutation`
  cannot build (no `ParameterAssignment` to build it from) — today, only
  `plan_block_mesh_resolution`'s raw mapping — by constructing a new
  `ResolvedMutation` whose `targets` is `resolved.targets + extra_targets`;
  `render_case_files` only ever iterates `resolved.targets` and never assumed
  every one came from a `ParameterAssignment` (Task 4's own finding). Returns
  `None` when there is nothing to write — `CaseMutationRequest` refuses an
  empty `parameters` tuple for `clone_and_patch` outright, so this check runs
  before one is constructed, the same no-op contract
  `cardiaccore.apply_input_overrides_planned` already gives.

**`cardiacfoam_plugin.CardiacFoamPlugin` now declares `clone_and_patch`
support.** `get_supported_mutation_modes()` → `frozenset({"synthesize",
"clone_and_patch"})`; `resolve_case_mutation` dispatches on `request.mode`
to `dict_builder.resolve_synthesis_mutation` or `overrides.resolve_patch_mutation`.
Chosen over building each tutorial's `ResolvedMutation` directly (the way
`openfoam/apply_overrides.py` does, since that module resolves overrides
against *whichever* plugin's declared scopes the composed stack carries and
cannot claim one identity) because cardiacFoam tutorials genuinely are one
plugin's own semantic-owner resolution, the same shape cardiacCore's
`resolve_patch_mutation` already has — declaring the mode is the honest
statement of what is now true, not an invented distinction (Task 1's own
lesson).

**Per-tutorial outcome (9 of 11 got a `plan_case`; 2 report as resisting):**

| tutorial | coverage | characterization test |
|---|---|---|
| `single_cell` | full (the template) | `test_single_cell_write_channel.py` |
| `cable_1d_cv_convergence` | full (entry + `deltaT`/`endTime` + block mesh) | `test_cable_1d_cv_convergence_write_channel.py` |
| `restitution_curves` | full (entry + `endTime`, no mesh) | `test_restitution_curves_write_channel.py` |
| `manufactured_monodomain_total_lagrangian_em` | full (entry on two documents + `deltaT` + block mesh) | `test_manufactured_monodomain_total_lagrangian_em_write_channel.py` |
| `niederer_2012` | hex-family only (`mesh_family == "tet"` keeps `apply_case` as its only route) | `test_niederer_2012_write_channel.py` |
| `manufactured_monodomain_1d3d` | full (the `.active` copy convention stays a direct write; only the rewrite that follows it moves) | `test_manufactured_monodomain_1d3d_write_channel.py` |
| `cable_1d_restitution` | full (both pacing modes' arithmetic unchanged; `.driverfoam_case_id`/`.cardiacfoam_protocol.json` stay direct — Task 7's classification) | `test_cable_1d_restitution_write_channel.py` |
| `manufactured_eikonal_ecg` | hex-family only; `grad_scheme`/`fv_scheme_overrides`/`fv_solution_overrides` (uncataloged `fvSchemes`/`fvSolution`) stay direct | `test_manufactured_eikonal_ecg_write_channel.py` |
| `manufactured_monodomain_pseudo_ecg` | **partial**: only `deltaT`/`endTime` + hex-family block mesh migrate; electroProperties edits stay direct (see below) | `test_manufactured_monodomain_pseudo_ecg_write_channel.py` |
| `manufactured_bath_bidomain` | **resists — not migrated** (see below) | — |
| `heart_solver_comparison` | **resists — not migrated** (see below) | — |

**Corrected 2026-09-24 (Task 11 close-out).** The `manufactured_bath_bidomain`
and `manufactured_monodomain_pseudo_ecg` rows above are stale: commit
`ca11a25` (after this task, implementing the "a parameter asserts a final
state" decision below) gave both tutorials a real `_plan_case` that migrates
their electroProperties edits (`resolve_electro_property_ensure`/`_removal`,
`plan_dict_block`), and `e3f5d08` then collapsed `_apply_case` to a thin
wrapper for both. Measured directly against `HEAD` (`d033399`) for Task 11:
both now have a working `_plan_case` covering **both** mesh families
(unlike `manufactured_eikonal_ecg`/`niederer_2012`, which still branch tet to
an independent `_apply_case`). But in both tutorials' own `_plan_case`, the
uncataloged `fvSchemes`/`fvSolution`/`controlDict` passthrough
(`grad_scheme`, `phi_tolerance`, `n_outer_correctors`,
`n_nonorthogonal_correctors`, `fv_scheme_overrides`, `fv_solution_overrides`,
`control_dict_overrides`) still calls `update_foam_entry` directly against
the real `case_root`, and — for `manufactured_bath_bidomain` only — an
`uncataloged_case_overrides` dict carrying the dead
`manufacturedBidomain.fdaBathVariant` key (kept only because nothing reads
it, not because it is needed) is still written via the pre-channel
`apply_electro_property_overrides`. Both tutorials' tet branches
(`render_tet_geo` plus the numerics overlay `shutil.copy`) are also still
direct, inside the now-migrated `_plan_case`. See Task 11's own inventory
below for the full, current accounting; this note exists so a reader of
this table does not mistake "resists — not migrated" for today's state.

**Two tutorials report as resisting the pattern, per this task's own
escape hatch, rather than inventing a variant:**

- **`heart_solver_comparison`** has no `ParameterAssignment`-shaped mutation
  at all: `_apply_case` is four `shutil.copy` calls swapping whole files
  (`electroProperties`, `fvSchemes`, `fvSolution`, `controlDict`) in from a
  fixed template directory — its own module docstring already says so
  ("apply_case swaps into constant/ and system/ verbatim"). This is
  structurally a source-artifact copy (Task 7's classification: "a copied
  mesh or graph file is a source artifact, not a parameter"), not a
  key/value patch; `render_patch_case_files` has no target shape for "whole
  document copied in" (only `render_synthesis_case_files` has a `"content"`
  target, for `synthesize` mode, which this is not — the case already
  exists). Forcing this through `clone_and_patch` would mean inventing a
  third target shape mid-task, which this task's own instruction says to
  report instead of doing.
- **`manufactured_bath_bidomain`**'s electroProperties edits are not a
  single set of independent key assignments: `_ensure_patch_entry` (upsert
  via `ensure_electro_property_entry`, `add_if_missing=True`) and
  `remove_electro_property_entry`/`remove_electro_property_dict` run
  *interleaved* with the two `apply_electro_property_overrides` calls in a
  load-bearing order — a stale `groundPatches.xMin`/`surfaceCurrentPatches.xMin`
  or `ecgDomains` block left behind by a *previous* case sharing the same
  reused `case_root` is explicitly removed before the new values are set
  (the code's own comment: "The committed electroProperties records
  whichever variant ran last -- the shared case_root entry-based sweeps
  mutate in place"). `ParameterAssignment` describes a SET at an existing
  key; it has no vocabulary for an upsert or a conditional removal, and
  collapsing the two `apply_electro_property_overrides` calls into one
  merged channel commit (the way `single_cell` merges its two calls) would
  silently drop this cleanup for a reused case_root — a real regression, not
  a cosmetic one. `_apply_case` is left unmodified; no `_plan_case` is
  supplied.

**One tutorial (`manufactured_monodomain_pseudo_ecg`) partially resists for
the identical reason** `manufactured_bath_bidomain` fully does — an
add-if-missing electrode upsert and a conditional `ecgDomains` removal,
interleaved with its own two `apply_electro_property_overrides` calls — but
its `deltaT`/`endTime`/block-mesh edits touch entirely different files
(`controlDict`, `blockMeshDict.<dimension>`) with no ordering dependency on
the resisting electroProperties edits, so that subset migrates cleanly while
the electroProperties edits stay direct, run in their original relative
position, after the channel commit.

**Every migrated document's real values, not an invented fixture, and
verified against the real catalog validation path — several genuinely
exercise Task 2's Gap 1 parser** (`cable_1d_cv_convergence`'s and
`cable_1d_restitution`'s `conductivity` overrides are real dimensioned
tensor literals, e.g. `"[-1 -3 3 0 0 2 0] (0.1334 0 0 0.1334 0 0.1334)"`,
round-tripped through `_write_value_for_assignment`'s `evidence_refs`
path). No characterization needed hardcoded byte spellings invented for
this task — each test's fixture text is a plausible, minimal document the
real catalog's declared entries accept, and every digest in every test was
captured by running the unmodified `_apply_case` once and recording its
actual output, not composed by hand.

**A real, previously undiscovered production bug found while writing
`manufactured_monodomain_total_lagrangian_em`'s characterization test, out
of this task's mandate to fix.** Its `_apply_case` hardcodes the key
`sequentialElectroMechanicalCoeffs.electromechanicalVerificationModel.type`,
but the native reader
(`~/noFrontendCardiacFoam_minor_errors/src/verificationModels/electromechanicsVerification/electromechanicalVerificationModel.C`'s
`configured`/`New`, via
`~/noFrontendCardiacFoam_minor_errors/src/electroMechanicalModels/electroMechanicalModel/electroMechanicalModel.C`'s
`electroMechanicalProperties_(subDict(type + "Coeffs"))`) actually reads
`verificationModel.type` off that same subDict — not
`electromechanicalVerificationModel.type`. Before Task 2's 2026-09-23
catalog-strictness decision this wrong key was written silently as a dead
entry no native code ever read; Task 2's fallback removal now refuses it
outright, since the catalog never declared the misspelled path (correctly —
nothing reads it). This means **the tutorial's own default call already
raises `ValueError` on unmodified HEAD**, independent of anything Task 6
touches — confirmed by running `_apply_case(root, case())` with no overrides
against HEAD before this task's changes. `test_manufactured_monodomain_total_lagrangian_em_write_channel.py`
characterizes this honestly: it asserts `_apply_case` and `_plan_case` raise
the *identical* `ValueError` for the default call (true behavioural parity
for a call that itself fails), rather than working around the bug inside
Task 6. Flagged as a separate follow-up (`task_7eca39be`), not fixed here —
fixing the tutorial's own hardcoded key is a correctness change to that
tutorial's arithmetic, not a write-channel migration.

**`set_delta_t`/`set_end_time`/`replace_block_mesh_resolutions` are NOT
retired in this task**, and the `apply_case=` grep count is unchanged
(16 before, 16 after — see Step 3 below). Two things block retirement,
independently:

1. **`_apply_case` is deliberately kept as an independent, unmodified
   writer beside `_plan_case` for every migrated tutorial**, the same "one
   transitional release" reasoning Task 2 gave for keeping
   `apply_entry_overrides`'s own direct-write body: `TutorialSpec.apply_case`
   has no default (`core/runtime/models.py`), so every spec must supply
   one regardless, and every characterization test in this task proves
   `_plan_case` byte-identical *against* `_apply_case`'s independent output
   — collapsing `_apply_case` into a thin wrapper over `_plan_case` before
   proving that would make the proof circular. Collapsing it now, having
   proven parity, is a safe, mechanical follow-up this task did not spend
   its remaining budget on.
2. **Two tutorials were not migrated for `deltaT`/block-mesh at all**
   (`manufactured_bath_bidomain`'s `set_delta_t`/`replace_block_mesh_resolutions`
   calls, `heart_solver_comparison` calls neither) — these are real,
   unremoved callers regardless of point 1.

**Step 3, reported as instructed:**

```
grep -rn "apply_case=" packages/*/src/ | grep -v "/build/"
```

**Count at the start of this task: 16. Count at the end: 16** (unchanged —
see above). Breakdown: 3 in `cardiaccore/workflows/preprocessing.py`
(already migrated in Phase 2, outside this task), 11 in
`cardiacfoam/tutorials/` (all eleven Task 6 tutorials, `manufactured_purkinje_graph`
included — Task 7's), 1 in `core/runtime/generic_case.py` (Task 8's, and
expected to remain — this task's own brief said so: "expect the count to
reach one, not zero").

**All four required shapes: 0 failed** (aside from the documented
environmental `ensurepip` abort in `test_every_core_module_imports_from_a_wheel`,
present before this task and unrelated to it). Both static gates pass.

---

## Decision, 2026-09-23: a parameter asserts a final state, not only a value

Task 6 migrated nine of eleven tutorials and found the third gap in Phase 2's
contract. The first two — a dimensioned-literal parser that was asserted but
never written, and bindings that assumed every dynamic domain is closed — are
closed. This one is more fundamental.

**`ParameterAssignment` can only say "set X to V".** It has no vocabulary for
an upsert or a removal. So `manufactured_bath_bidomain` cannot migrate at all,
and `manufactured_monodomain_pseudo_ecg` migrated only its disjoint
`deltaT`/`endTime`/block-mesh edits: both interleave
`ensure_electro_property_entry`, `remove_electro_property_entry` and
`remove_electro_property_dict` between their override calls, and those removals
are load-bearing for a reused `case_root`. Forcing them into the current
vocabulary would silently drop real cleanup.

**A removal is a mutation, and arguably the one most worth reviewing.** Deleting
`bathPotentialDomain` changes which solver path runs, by absence. A channel that
claims to be the one auditable record of framework-authored inputs, and cannot
describe a deletion, is not that record.

**Decision: `ParameterAssignment` gains an `operation`, and every operation is an
assertion about the document's final state.**

| operation | asserts |
|---|---|
| `set` (default) | the key exists with this value |
| `ensure` | the key exists with this value, created if absent |
| `remove` | the key does not exist |

`value` is required for `set` and `ensure`, and **forbidden** for `remove` —
enforced in `__post_init__`. There is precedent for exactly this shape:
`Precondition` already refuses a `digest` together with `must_be_absent`,
because "must be absent" and "must have this digest" are different claims.

Three things this must not become:

- **Not a new type.** One addressing vocabulary. A `ParameterRemoval` beside
  `ParameterAssignment` would mean two things to keep in step, and this
  repository's rule is that one fact has one declarer.
- **Not a rendering concern.** `update_foam_entry` already carries
  `add_if_missing`; `ensure` maps onto it. Removal belongs to the format owner
  in `case_rendering`, the same way the `hex (` rewrite does. Core describes the
  assertion; OpenFOAM performs it.
- **Not an excuse to keep both paths.** Task 6 left `_apply_case` in place
  beside `_plan_case`, so the `apply_case=` count is unchanged at 16 and bypass
  1 is still open. Adding `operation` is what unblocks the last two tutorials;
  retiring `_apply_case` is what actually closes the bypass. Both are needed.

### What Task 6 left open, to be finished alongside

- `manufactured_bath_bidomain` and `heart_solver_comparison` unmigrated.
  `heart_solver_comparison` is four `shutil.copy` calls of whole template files
  — that is a source-artifact classification and belongs to **Task 7**, not to
  the `operation` work.
- `_apply_case` retained on all thirteen tutorials. Once byte parity is proven,
  collapse it to a thin wrapper over `_plan_case` and retire it, which retires
  `set_delta_t`/`set_end_time`/`replace_block_mesh_resolutions` with it.
- A real production bug Task 6 found and correctly did not fix in place:
  `manufactured_monodomain_total_lagrangian_em`'s `_apply_case` writes
  `electromechanicalVerificationModel.type` where the native C++ reads
  `verificationModel.type`, so its own default call already raised on unmodified
  `HEAD`. Tracked separately.

## After Task 6b, 2026-09-23: three corrections to how bypass 1 is measured and read

**The `apply_case=` count cannot reach 1, and the plan was wrong to expect it.**
Task 6b collapsed `_apply_case` to a thin wrapper over `_plan_case` on ten of
sixteen sites, yet the count is unchanged at 16 — because `TutorialSpec.apply_case`
has **no default**, so every `make_spec` must still pass one whether or not it
supplies `plan_case`. Collapsing a body does not remove the wiring. The grep
therefore measures a field's presence, not whether anything writes outside the
channel, and it cannot fall until `apply_case` becomes optional when `plan_case`
is supplied. That is a small core change to `core/runtime/models.py`, and it is
what lets Task 11 read bypass 1 honestly. Until then, the meaningful measure is:
**does any tutorial write outside `commit_case_write`?** Ten do not. The remaining
six are `heart_solver_comparison` and `manufactured_purkinje_graph` (Task 7),
`core/runtime/generic_case.py` (Task 8), and three cardiacCore sites already
migrated in Phase 2 that still wire the field.

**Two tutorials write a key where the native solver does not read it.** Both
were already broken before Phase 3; strictness made them fail loudly rather than
introducing the fault, which was checked by running both sides of the fallback
deletion and against the native source:

| tutorial | writes | native reads |
|---|---|---|
| `manufactured_monodomain_total_lagrangian_em` | `electromechanicalVerificationModel.type` | `verificationModel.type` |
| `manufactured_bath_bidomain` | `manufacturedBidomain.fdaBathVariant` | `verificationModel.fdaBathVariant` (`manufacturedFDABathBidomainVerifier.C`, `getOrDefault(..., electrodePair)`) |

The bath template carries `verificationModel { fdaBathVariant electrodePair; }`
and no `manufacturedBidomain` block, so the old unchecked write raised `KeyError`
and the new strict path raises `ValueError` before touching a file. A caller
asking this tutorial for the `groundElectrode` variant has therefore never been
able to get it. **The strict resolver is now the drift gate for this class**:
any key a tutorial writes must be one the catalog declares at that scope, so the
next wrong-scope key fails at plan time rather than silently. Both fixes are
one-line scope corrections and are tracked separately.

**Retiring a function must not retire its coverage.** Task 6b deleted
`test_common_blockmesh_resize.py` with `replace_block_mesh_resolutions`. Three of
its four behaviours had successors; the fourth — a missing `blockMeshDict` must
fail loudly — had moved to the renderer but its test had not. Restored in
`a0f9954` and revert-confirmed. The rule for Tasks 7–10: before deleting a test
alongside a retired function, map each behaviour it pinned to a surviving test
by name.

Task 6b also tightened `set` to `add_if_missing=False` — previously
unconditionally `True`, so a `set` against a missing key silently created it.
Verified that no migrated tutorial relied on the old permissiveness. `ensure`
is now the explicit way to create.

## Task 7: Source artifacts and sidecars, classified — bypass 1 remainder

Not every write in a tutorial is a parameter. From the measured surface:
7 `shutil.copy`/`copy2`, 4 `write_text`, 1 `json.dump`, 1 `subprocess.run`.

- [x] **Step 1: Classify each, and route by class, not by uniformity**

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

### Findings, 2026-09-23

**Full inventory, all 13 measured writes plus 2 more found by widening the
grep to `open(` (per this task's own instruction: "the previous close-out
established that the grep this programme used could not see `open(...)`
writes").** One line of justification each; classes match Task 11's own
taxonomy (declared workflow output, standalone export, source artifact,
framework bookkeeping, framework-authored case input).

| site | class | justification |
|---|---|---|
| `heart_solver_comparison.py` `_apply_case`'s two `shutil.copy` calls (4 files: `electroProperties`, `fvSchemes`, `fvSolution`, `controlDict`) | **framework-authored case input → `RenderedFile`, migrated** | Small, hand-editable OpenFOAM documents cardiacFoam reads exactly as any other tutorial's version of the same document -- not opaque, not large. `plan_verbatim_content` + a new `"content"` target on `render_patch_case_files` (Phase 3 Task 7) route them through `commit_case_write`; `source_artifacts` names which solver-variant template supplied the bytes, since the request assigns zero `ParameterAssignment`s. |
| `manufactured_purkinje_graph.py` `_apply_case`'s `shutil.copy2` (`purkinjeGraph.<id>` → `purkinjeGraph`) | **source artifact, blocked on missing artifact staging (corrected 2026-09-24, see below)** | Large geometric data (the class `RenderedFile`'s own docstring calls out as "referenced by digest, never embedded"), not a small dictionary key -- same class `manufactured_monodomain_1d3d`'s identical copy already has. Stays a direct write: this tutorial's *only* write is this copy, and a channel commit whose sole content is a source-artifact declaration would build a `CaseWritePlan` with zero `RenderedFile`s, which `CaseWritePlan.__post_init__` itself refuses ("a plan must render at least one file") -- a guard this task may not weaken. |
| `manufactured_monodomain_1d3d.py`'s `shutil.copy2` (identical `purkinjeGraph.<id>` → `purkinjeGraph`) | **source artifact, blocked on missing artifact staging (corrected 2026-09-24, see below)** | Same reasoning as above. Not a declared exception in the same sense -- this tutorial's *other* edits (hex rewrite, electro overrides, controlDict) already reach `commit_case_write` via its own `_plan_case`, so the copy sits beside a real channel commit rather than replacing the tutorial's only one. |
| `manufactured_monodomain_1d3d.py`'s `block_mesh_active.write_text(block_mesh_dict.read_text())` (`blockMeshDict.3D` → `.active`) | **case input, blocked on missing artifact staging (corrected 2026-09-24, see below)** | Decides *which* document the channel will subsequently patch; carries no value of its own. Predates Task 7 and is outside its mandate to revisit. |
| `manufactured_bath_bidomain.py` / `manufactured_eikonal_ecg.py` / `manufactured_monodomain_pseudo_ecg.py`'s tet-branch numerics-profile overlay `shutil.copy` (`overlay_name` resolves to `"fvSolution"`, replacing `system/fvSolution` wholesale) | **framework-authored case input, same class as `heart_solver_comparison` -- classification corrected, migration deferred** | Task 6 labelled these "source artifacts, Task 7's domain"; checked against `defaults.TET_NUMERICS_PROFILES`/`_NUMERICS_PROFILES` (found, not assumed) and they are small hand-authored numerics documents, not mesh/graph data -- the identical class `plan_verbatim_content` now serves. Corrected with a dated note in all three tutorials' own `_plan_case` docstrings. **Not migrated**: these three tutorials are outside Task 7's two assigned ones, and migrating a third party's tet branch is real, additional scope, not a corollary of fixing a misclassification comment. Tracked as a follow-up. |
| `cable_1d_restitution.py`'s `(case_root / ".driverfoam_case_id").write_text(case.case_id)` | **marker / framework bookkeeping, not migrated (by design)** | Intra-run sentinel so `Allrun.post` (`postProcessing_cableRestitution.py`'s `__main__`) can recover the sweep's semantic case id without a `--case-id` argument threading through the `workflow_dag`. Not read by cardiacFoam; not a result a scientist inspects. Named `CASE_ID_SENTINEL_FILENAME`, documented at its definition, with the exact reader cited. |
| `cable_1d_restitution.py`'s `(case_root / ".cardiacfoam_protocol.json").write_text(json.dumps(...))` (also the task's one `json.dump`-class write) | **standalone export, not migrated (by design)** | Not a `ParameterAssignment` (no key in an existing document) and not a source artifact (nothing was consumed to produce it). Read **by name** by `postProcessing_cableRestitution.py`'s own `PROTOCOL_METADATA`/`load_protocol_metadata` -- found by reading that reader before changing anything, per this task's own instruction. Named `PROTOCOL_SIDECAR_FILENAME`, with its full schema and reader stated in a module-level docstring. |
| `niederer_2012.py`'s `target_file.write_text(rendered)` (`.geo` template, `__LC__` substituted) | **framework-authored case input, same RenderedFile-eligible class -- classification corrected, migration deferred** | Small hand-authored gmsh geometry text with one substitution, downstream-used exactly like `heart_solver_comparison`'s templates. Already named "Task 7's domain, not Task 6's" in its own docstring. **Not migrated**: outside Task 7's two assigned tutorials, and it additionally duplicates `omnidriver.openfoam.tet_mesh_provisioning.render_tet_geo` (the shared helper three *other* tutorials already call for the identical operation) instead of reusing it -- a second, larger reuse fix a follow-up should do together with the migration, not two separate patches. |
| `manufactured_purkinje_graph.py::_ensure_mesh` (the task's one `subprocess.run`, plus its own `log.blockMesh` `open("w")` -- found by widening the grep) | **dead code, deleted** | Zero callers anywhere in this repository (confirmed by `grep -rn "_ensure_mesh"` before deletion, matching only its own definition) and duplicates the "mesh" `workflow_dag` step *already declared* in this same module's `make_spec` -- the real, executed mesh-authoring mechanism (`workflow_orchestrator.py`/`workflow_runner.py`). There was nothing live to migrate, so it is deleted rather than turned into a declared step or a channel-committed artifact -- both already exist or are inapplicable. |
| `niederer_2012.py`'s `_update_end_time`'s hand-rolled `control_dict_path.open("w")` (found by widening the grep) | **framework-authored case input, already parameter machinery -- not Task 7's domain** | This is `endTime`, exactly what `plan_end_time`/`ParameterAssignment` already cover; `_plan_case`'s hex-family path uses `plan_end_time`, and this hand-rolled writer survives only inside `_apply_case`, kept for byte-parity proof per Task 2/3/6's own "keep both until parity is proven, then collapse" convention. Not "outside the parameter machinery" in the sense this task addresses -- it is that machinery's own pre-Task-6-collapse leftover. |

**`_ensure_mesh`'s `blockMesh` subprocess -- the question answered, not
assumed.** It becomes **neither** a new declared workflow step nor a
channel-committed artifact: `manufactured_purkinje_graph.py`'s own
`make_spec` **already** declares a `"mesh"` step
(`{"id": "mesh", "command": "blockMesh", "args": [...], "depends_on": []}`,
with `"solve"` depending on it), executed by the real, live
`workflow_dag` dispatch mechanism (confirmed executed, not merely present,
by finding `workflow_orchestrator.py`/`workflow_runner.py` consuming
`workflow_dag` steps, and by the identical, already-live pattern in
`manufactured_eikonal_ecg.py`'s own comment: "this lives on the
workflow_dag path, which is the mechanism sweep-run actually executes").
`_ensure_mesh` predates that convention, was never wired to any caller
(`grep -rn "_ensure_mesh"` found only its own definition, in this module,
before this task's deletion), and would have been the same authoring
twice over two different mechanisms had it ever been called. The plan's own
framing ("a native utility producing its own files is ordinarily a declared
workflow output -- the question is whether this one ... is different")
resolves cleanly here: it is not different in kind, it is simply
**redundant** with a step that already exists -- so the honest action is
deletion with a dated correction note, not migration.

**`heart_solver_comparison`'s whole-file copies -- argued from downstream
usage, per this task's own instruction.** `RenderedFile`, not a source
artifact. `plan_verbatim_content`'s docstring (`openfoam/utils.py`) carries
the full argument; in short: a source artifact is a *reference* to
something external a mutation consumed (a mesh, an opaque asset,
un-path-checked because it may live outside the case) that this channel
never itself commits. These four documents are the opposite -- small,
hand-editable OpenFOAM dictionaries that *become* `case_root`'s actual
`electroProperties`/`fvSchemes`/`fvSolution`/`controlDict`, read downstream
by cardiacFoam exactly the way every other tutorial's version of the same
document is read. Routing them as source artifacts would carry them out of
the channel's own audit trail (no `content_digest`, no journal-recorded
before/after bytes) for no reason but their own authoring granularity
(whole-document swap vs. key-level edit). `CaseMutationRequest`'s
"clone_and_patch assigns at least one parameter" invariant (Task 1, kept on
"no caller needs this relaxed") is widened, not dropped, to "a parameter or
a source artifact" -- `heart_solver_comparison` is the real caller Task 1
did not yet have; see the dated correction on that type's own docstring and
`test_a_clone_and_patch_request_with_no_parameters_but_a_source_artifact_is_accepted`.

**The protocol sidecar's reader, found before anything was changed, per this
task's own instruction.** `.cardiacfoam_protocol.json` and
`.driverfoam_case_id` are both read by the *native* tutorial tree's own
postprocessor -- not by anything in this repository --
`~/noFrontendCardiacFoam_minor_errors/tutorials/electrophysiologyProtocols/
cableProtocol/monodomain1DCableCV/setup/postProcessing_cableRestitution.py`,
invoked as `Allrun.post`'s own command (`python3
setup/postProcessing_cableRestitution.py`, the `workflow_dag`'s `extract_cv`
step). That script declares `PROTOCOL_METADATA = ".cardiacfoam_protocol.json"`
and reads it with `load_protocol_metadata(case_dir) = json.loads((case_dir /
PROTOCOL_METADATA).read_text())`; its `__main__` falls back to
`case_dir / ".driverfoam_case_id"` for the case id when `--case-id` is not
supplied. Both filenames are now named constants
(`PROTOCOL_SIDECAR_FILENAME`, `CASE_ID_SENTINEL_FILENAME`) in
`cable_1d_restitution.py`, each with a module-level docstring stating its
contract (schema, reader, and the "changing this silently breaks
postprocessing" warning) -- the "own stated artifact contract" this task
asked for. Not modelled as a `DataArtifact`: that vocabulary is for a raw
data *output* a run or utility produces (`expected_artifacts`'
`cable_probes`/`restitution_event_summary`/etc., each claimed by a
`workflow_dag` step's `produces`), and both files are written directly by
`_plan_case`/`_apply_case` at case-materialization time, before any step
runs -- forcing them into `expected_artifacts` would trip
`test_every_required_artifact_is_claimed_by_the_step_that_writes_it`'s own
guard for a file no step actually produces.

**Whether any tutorial still writes outside `commit_case_write` after this
task.** `heart_solver_comparison` now does not (it commits through the
channel with zero parameters and a declared source artifact).
`manufactured_purkinje_graph` still makes zero `commit_case_write` calls --
see the corrected framing immediately below; this is not the same shape as
`write_cell_set`. Every other tutorial's status is unchanged by this task.

### Corrections from review, 2026-09-24

**The three graph/mesh-adjacent copies (rows above: `manufactured_purkinje_graph`'s
`purkinjeGraph` copy, `manufactured_monodomain_1d3d`'s identical copy, and
its `blockMeshDict.3D` → `.active` copy) are not "declared exceptions" and
are not two unrelated shapes ("source artifact" vs. "routing convention").
Corrected: all three are blocked on one missing channel capability,
**artifact staging**, not on three separate settled decisions.**

`CaseMutationRequest.source_artifacts` (and the `source_artifact`
`Precondition` kind) let the channel *reference* an artifact -- name it,
digest it, refuse to commit if it drifted. Neither gives the channel a way
to *place* that artifact's bytes at a case-relative destination.
`RenderedFile` places bytes, but only the small, hand-editable-document
class this phase's own rule excludes large assets from (`RenderedFile`'s
docstring: "the global 'large assets are referenced by digest, never
embedded' rule is about meshes and VTU output"). So a mesh or graph copy has
a reference mechanism and an embedding mechanism, and needs neither -- it
needs a third one, **staging**, that this phase never built. Phase 2's own
plan named both halves ("large assets referenced by digest **and staged**");
only the referencing half was ever implemented.

This reframes all three sites:

- `manufactured_purkinje_graph`'s `purkinjeGraph` copy and
  `manufactured_monodomain_1d3d`'s identical copy are the same missing
  capability, not "a declared exception" (`manufactured_purkinje_graph`) and
  "not migrated, Task 6's classification" (`manufactured_monodomain_1d3d`)
  as two different resting states. Neither was ever *decided* to stay
  outside the channel; both are *blocked* until artifact staging exists.
- `manufactured_monodomain_1d3d`'s `blockMeshDict.3D` → `.active` copy is a
  **case input**, not bookkeeping: `system/blockMeshDict.3D.active` is what
  the `mesh` workflow step actually reads. Calling it "a routing convention,
  not a parameter or source artifact" was accurate about what it is not, but
  did not say what it is: the same staging operation as the graph copies
  (an existing file's bytes, placed at a new case-relative destination, with
  no key/value edit), just with an in-case rather than external source.

**Why this distinction matters for Task 11.** `write_cell_set` is a genuine
declared exception: a real format decision (invent a `cellSet` renderer, or
don't) deferred until a second consumer justifies building one. These three
are not a decision at all -- they are work no one has done yet, on a
capability whose need was anticipated in Phase 2's own plan and never
closed. Task 11's inventory should list "artifact staging: missing" as its
own line, separate from `write_cell_set`'s "declared, single-consumer,
revisit on a second one" -- conflating the two would make a buildable gap
look like a considered, stable design choice.

**Not fixed here.** Designing and building an artifact-staging primitive
(what it references, what precondition it checks, how `commit_case_write`
places bytes it never rendered) is out of this review correction's scope --
it is exactly the kind of capability work this plan's own Task 11 close-out
should surface explicitly, which is why it is named here rather than
attempted. The three call sites' own docstrings
(`manufactured_purkinje_graph.py::_apply_case`,
`manufactured_monodomain_1d3d.py::_plan_case`) carry a dated correction with
this same reframing.

**Also from the same review: the `"content"` target's own test coverage,
and a misleading helper name.** `plan_verbatim_content`/`render_patch_case_files`'s
`"content"` branch had exactly one exerciser --
`test_heart_solver_comparison_write_channel.py`, in cardiacFoam's own suite
-- for format behaviour OpenFOAM owns, the same way Task 4's `hex (` rewrite
is pinned in `omnidriver-openfoam/tests/core/test_block_mesh_resolution_channel.py`.
Added `omnidriver-openfoam/tests/core/test_content_target_channel.py`:
a content target renders exactly the given bytes; two content targets on
one document are refused; a content target authors a document that does not
exist yet, while an ordinary value edit against a missing document is still
refused (`test_block_mesh_resolution_channel.py`'s own
`test_the_renderer_refuses_a_missing_block_mesh_dict` stayed green,
confirmed, not assumed); a content target plus a value edit on the same
document lands the edit atop the content; before-digest and mode are
preserved when the document already existed. Verified by reverting
`case_rendering.py`/`utils.py`: the new file fails to collect at all
(`ImportError: cannot import name 'plan_verbatim_content'`), while
`test_block_mesh_resolution_channel.py`'s existing 12 tests are unaffected
either way.

`plan_verbatim_content`, `plan_block_mesh_resolution`, and `plan_dict_block`
all called a helper named `_hex_patch_format()` merely to look up
`case_rendering.FORMAT` (deferred to call time to avoid a module cycle) --
a name that named only its first caller and would have misled a reader of
`plan_dict_block` or `plan_verbatim_content` into thinking they reused a
hex-specific helper for no reason. Renamed to `_patch_format()`; it has no
other callers, so this is a pure rename with a dated note at its definition,
not a behaviour change.

**Characterization tests, and the revert-to-confirm result.**
`test_heart_solver_comparison_write_channel.py` pins `_apply_case`'s exact
output by content digest per solver variant (four documents × four
variants) and proves `_plan_case` reproduces it byte-for-byte; also asserts
the committed request carries zero parameters and the expected
`source_artifacts` entry. Verified by reverting
`heart_solver_comparison.py` alone (`git stash`): the characterization test
(`test_characterization_apply_case_current_bytes`) still passes unchanged
(the pre-Task-7 direct-copy `_apply_case` wrote the identical bytes), while
every `test_plan_case_*` test fails with `AttributeError: module ... has no
attribute '_plan_case'` -- restoring the change returns all to green.
`test_manufactured_purkinje_graph_write_channel.py` is new coverage (this
tutorial's `_apply_case` had none before this task) plus a lock-in that
`_ensure_mesh` no longer exists and the `"mesh"` step it duplicated is still
declared.

**No test deleted.** This task added tests; it retired no function that had
existing test coverage (`_ensure_mesh` had zero callers and zero tests), so
there is no "map each behaviour to a surviving test" bookkeeping to do here.

**All four shapes: 0 failed** (the documented environmental `ensurepip`
abort in `test_every_core_module_imports_from_a_wheel` aside, present before
this task and unrelated to it -- confirmed absent from the wheel-install
shape's own run). Both static gates pass.

**What this task got wrong in its own brief, corrected here.** "It belongs
in `synthesize`'s `source_artifacts`" (Step 1's first bullet) does not hold
literally: every real source-artifact copy this task found
(`manufactured_purkinje_graph`, `manufactured_monodomain_1d3d`) is a
`clone_and_patch` mutation, not `synthesize` -- `dict_builder.py`'s
synthesis path is still `source_artifacts`'s only production populator, and
neither tutorial's mesh/graph copy is routed through it or through any
other channel mechanism (both stay direct writes, as argued above).
`CaseMutationRequest.source_artifacts` itself is mode-agnostic already (only
`synthesize` requires it non-empty), and this task's own
`heart_solver_comparison` change is the first real `clone_and_patch` caller
to populate it -- but that is a provenance declaration alongside a real
`RenderedFile` commit, not a case of the graph/mesh classification "landing
in" that field the way the brief implied.

---

## Task 8: `generic_case.py` — bypass 2

**Files:** `packages/omnidriver/src/omnidriver/core/runtime/generic_case.py`

The last `apply_case` consumer, and the only one in **core**. R4 flagged it as
needing its own design pass, because a generic case has no adapter vocabulary to
resolve against — which is precisely why core owns it.

- [x] **Step 1: Establish what it may legitimately assume**

A generic case folder declares no catalog. If it cannot produce
`ParameterAssignment`s with real qualified ids, it must not invent them. The
honest options are a `synthesize` request whose content comes entirely from
`RenderedFile` bytes, or an explicit statement that a generic case is not a
framework-authored mutation at all. **Argue which, with evidence from how a
generic case is actually used.**

### Findings, 2026-09-24

**What `_apply_case` writes.** `generic_case.py::_apply_case` calls exactly
one thing: `mutation_callback(case_root, case, dict_file_relpaths=...,
dict_file_overrides=...)`. `make_spec`'s own `_apply_case_mutation`
parameter defaults to `_no_solver_mutation`, whose entire body is `return
None` (its docstring already says so: "what a case mutation is when no
plugin supplies one: nothing"). So `apply_case` is a genuine no-op
placeholder in the common case, not a stub that used to do something — it
exists purely because `TutorialSpec.apply_case` had no default.

**Who authors a generic case's inputs, and the production path that proves
it.** `packages/omnidriver/src/omnidriver/core/runtime/registry.py`'s entry
resolution (`_match_entry`/case-path branch) picks core's own
`make_generic_case_spec` — the no-op-default factory — precisely when
`driver_context.capabilities.case_compatibility.has_case_marker(...)` is
false, i.e. exactly the "no catalog" case this task's brief describes. When
an adapter *does* recognise a case marker, a different factory (the
adapter's own, e.g. `cardiacfoam.tutorials.generic_case.make_generic_case_spec`)
is used instead, wired to a real, adapter-owned mutation callback — a
different code path this task does not touch. The only test exercising the
true bypass-2 path end to end,
`packages/omnidriver-cardiaccore/tests/test_generic_contract.py::test_controlled_allrun_executes_without_domain_claims`,
proves this concretely: it hands `omnidriver run --entry controlled-case` a
case folder containing nothing but a user-written `Allrun` script, and the
observable output (`generic-proof.txt`) comes entirely from that script
running as the declared workflow step, not from any dictionary mutation.
Materialization (`sweep_runner._materialize_entry_case`, the only caller of
`invoke_case_mutation`/`apply_case` in core — confirmed by
`grep -rn "\.apply_case(\|invoke_case_mutation("` returning exactly those two
sites) stages this pre-existing, user-authored folder via `shutil.copytree`
before the mutation hook runs at all. So a generic case's inputs are
authored by the user, before handing the folder to the framework; the
framework's role is staging + declared-workflow execution, never content
authorship.

**Decision: candidates 2 and 3, combined; candidate 1 does not apply.**
Candidate 1 (a `synthesize` request from `RenderedFile` bytes) requires core
to have bytes of its own to embed — it has none: this module renders
nothing, it only stages a copy and dispatches to an optional callback.
Candidate 2 holds for exactly the no-catalog, no-adapter-callback case:
`apply_case` there is not a framework-authored mutation at all, the same
reasoning the plan already applies to native solver/meshing output — the
channel never claimed it. Candidate 3 (`apply_case` optional when
`plan_case` is supplied) is needed regardless, and for a concrete, verified
reason beyond the brief's own: every real invocation of this no-op path
through `invoke_case_mutation` was, before this change, emitting a
`DeprecationWarning` on **every** marker-less generic-case run (confirmed by
running the previous code — see revert-to-confirm below) — a warning that
was not describing anything actually deprecated, only an unavoidable
required field. `TutorialSpec.apply_case` is now `ApplyCaseFn | None = None`
in `core/runtime/models.py`.

**A third case the brief's two-way split did not name, resolved by not
conflating them.** An adapter *can* supply a real, non-sentinel mutation
callback to this same factory (cardiacfoam's own generic-case wrapper always
does). Core cannot see what that callback writes or whether it already
routes through the case-write channel — wiring it to `plan_case` returning
`None` would misreport a possibly-real, possibly-uncommitted write as
channel-compliant, which is exactly the kind of false negative Task 11's
close-out needs to avoid. `make_spec` therefore branches on
`mutation_callback is _no_solver_mutation` (an identity check against the
module's own private sentinel, set only when the caller passed no callback):
the genuine no-op case gets `apply_case=None, plan_case=<dispatch>`; a
real-callback case keeps `apply_case=<dispatch>, plan_case=None`, unchanged
from before and still routed through the deprecated, non-reporting fallback
(honest: this call site's write status remains genuinely unknown to core,
tracked separately, not fixed here).

**`invoke_case_mutation`'s "neither present" refusal.** Added an explicit
branch: `plan_case` preferred, then `apply_case` with the existing
deprecation warning, and only if both are `None` a `TypeError` naming the
spec by `spec.name!r` and both missing hooks — verified this replaces a bare
`TypeError: 'NoneType' object is not callable` (see revert-to-confirm).

**The `apply_case=` count.** `grep -rn "apply_case=" packages/*/src | grep -v
/build/` is **16 before and 16 after** — unchanged, because it is a static
text-occurrence count and `generic_case.py`'s own construction still
contains the keyword (now as a conditional expression, `apply_case=None if
... else ...`). This matches the "After Task 6b" section's own warning that
this grep "measures a field's presence, not whether anything writes outside
the channel." What changed is not the text count but the runtime value: in
the true bypass-2 scenario (no case marker, `_no_solver_mutation` in
effect), the field this factory hands `TutorialSpec` is now genuinely
`None`, and the honest `plan_case` reports the `None` mutation instead —
removing `generic_case.py` from the "remaining six" bypass-1/2 sites named
in "After Task 6b", for that scenario specifically. The real-adapter-callback
branch is unchanged and intentionally left as a named, tracked gap (see
above), not silently absorbed into this count.

**Existing tests updated, and why each was still the right test to change
rather than replace.**
`packages/omnidriver/tests/core/test_core_generic_case.py::test_make_generic_case_spec_applies_no_solver_mutation`
called `spec.apply_case(...)` directly on a no-callback spec; updated to
assert `spec.apply_case is None` and call `spec.plan_case(...)` instead,
asserting it returns `None`. Same file's
`test_generic_dict_file_overrides_reach_the_mutation_callback` (a real
callback, `_MutationSpy`) gained one assertion, `spec.plan_case is None`,
locking in that the real-callback branch is unaffected. Two new tests in
that file exercise `invoke_case_mutation` itself against `generic_case.py`
specs: `test_a_generic_case_with_no_mutation_reports_through_invoke_case_mutation_without_warning`
(no `DeprecationWarning`, `warnings.simplefilter("error", ...)` would fail
the test if one fired) and
`test_a_generic_case_with_a_real_callback_still_falls_back_through_apply_case`
(the real-callback branch still warns and still runs the callback).
`packages/omnidriver/tests/core/test_entry_case_parity.py` gained
`test_invoke_case_mutation_refuses_by_name_when_neither_hook_is_supplied`,
which is core-level plumbing coverage independent of `generic_case.py`
(matching that file's own stated scope in its module docstring).

**No test deleted; nothing to map to a survivor.** This task only changed
behaviour that these tests directly exercise; none had coverage retired out
from under them.

**Revert-to-confirm.** `git stash push -- .../generic_case.py
.../models.py`, then ran the four touched/new tests against unmodified HEAD:
`test_make_generic_case_spec_applies_no_solver_mutation` and
`test_a_generic_case_with_no_mutation_reports_through_invoke_case_mutation_without_warning`
failed (`AttributeError`-shaped: `spec.plan_case` was `None` so calling it
raised, and the "no warning" assertion caught the real
`DeprecationWarning` that fired every time under the old code — direct
confirmation of the warning-on-every-run finding above);
`test_invoke_case_mutation_refuses_by_name_when_neither_hook_is_supplied`
failed with `AssertionError: Regex pattern did not match ... Actual message:
"'NoneType' object is not callable"` — exactly the bare, untraceable error
the named refusal replaces. `git stash pop` restored the change; all four
passed again.

**All four shapes: 0 failed.** `packages/ -q -m "not slow"`: 2546 passed,
259 skipped, 2 deselected. Core-only (`/tmp/odcore`,
`packages/omnidriver/tests`): 1117 passed, 94 skipped, plus the documented
environmental `ensurepip`/`SIGABRT` abort in
`test_every_core_module_imports_from_a_wheel` (present before this task,
unrelated — it aborts building its own disposable venv, not from anything
this task touched). Wheel shape (`python -m build` +
`scripts/check-wheel-artifact.py` + `pytest packages/omnidriver/tests`
against `/tmp/wheelenv`): artifact gate OK, 950 passed, 262 skipped, 0
failed. Both static gates (`check-import-boundaries.py`,
`export-capability-seams.py --check`) pass.

**What this task's brief got right, and one thing worth flagging for
Task 11.** The brief's framing (a generic case has no catalog, so it must
not invent qualified ids) held up exactly as stated once checked against the
real registry dispatch and the real test. The one addition beyond the brief:
it posed the decision as a binary (synthesize vs. "not a mutation"), but the
actual call site is not uniform — the same factory serves both a genuine
no-op and an opaque real-callback case, and treating them identically would
have either invented content (candidate 1, ruled out) or silently
misreported a real write as channel-compliant. Recorded here rather than
silently resolved so Task 11's inventory does not read the real-callback
branch as fixed.

---

## Merge note, 2026-09-24: two unmerged branches conflict semantically, not just textually

Two follow-up branches, both unmerged, edit `manufactured_bath_bidomain.py` and
`tests/test_manufactured_bath_bidomain_write_channel.py`:

| branch | work | state |
|---|---|---|
| `claude/compassionate-gates-967e8d` | tet-branch overlay copies join the channel; `niederer_2012` reuses the `.geo` renderer | committed as `df0a059` on `9d159fa`, green in all four shapes |
| `claude/sharp-cannon-7e5e7c` | corrects `manufacturedBidomain.fdaBathVariant` to `verificationModel.fdaBathVariant`, and the same class of bug in `manufactured_monodomain_total_lagrangian_em` | uncommitted as of this note; **no venv built from its worktree was found**, so any green it reports may be main's |

**Corrected 2026-09-24 (Task 11 close-out).** `claude/sharp-cannon-7e5e7c`'s
branch *ref* (`c3d12a3`) is not unmerged — `git merge-base main
claude/sharp-cannon-7e5e7c` returns `c3d12a3` itself, i.e. it is an ancestor
of `main` with zero commits unique to it. But its **worktree**
(`.claude/worktrees/sharp-cannon-7e5e7c`) still carries real uncommitted
changes to exactly the two files this note describes
(`manufactured_bath_bidomain.py`, `manufactured_monodomain_total_lagrangian_em.py`,
plus three test files) — so the note's substance holds: that work never
reached any commit, on this branch or on `main`. Measured directly:
`manufactured_bath_bidomain`'s `fdaBathVariant` defect is **not** in the
state this note describes any more — `main` (as of `ca11a25`) already writes
the catalog-declared `verificationModel.fdaBathVariant` as a real
`ParameterAssignment` through the channel, and keeps the dead
`manufacturedBidomain.fdaBathVariant` key as a separate, explicitly-named
`uncataloged_case_overrides` direct write (see Task 11's inventory: this is
now its own small, deliberate open bypass, not the "every call raises"
defect `ca11a25` first found). `manufactured_monodomain_total_lagrangian_em`'s
sibling bug (`electromechanicalVerificationModel.type`, should be
`verificationModel.type`) is **still open on `main`**, confirmed by reading
its current source — the uncommitted worktree fix for that file never
landed. Do not read "uncommitted" as "therefore irrelevant": the
total_lagrangian_em fix genuinely has not happened anywhere in git history.

**A clean text merge will still fail.** `df0a059`'s
`TestManufacturedBathBidomainTetWriteChannel` characterizes the tutorial *as it
is today*, so two of its tests assert that `_plan_case` raises the dead-key
`ValueError` (`assertRaisesRegex(..., _DEAD_KEY_MESSAGE_FRAGMENT)`), and they pin
`_TET_DIGESTS_BEFORE`, whose `constant/electroProperties` digest is captured at
the moment of that raise. The wrong-scope fix removes the raise. So those tests
break once both branches are merged, whichever lands second.

**Resolution, for whichever branch lands second**, per the tet-overlay session's
own analysis:

1. Drop the `assertRaisesRegex(ValueError, _DEAD_KEY_MESSAGE_FRAGMENT)` in those
   two tests.
2. Read the committed record from `_plan_case`'s return value, not through the
   `commit_case_overrides` wrapper.
3. Re-capture **only** the `constant/electroProperties` digest in
   `_TET_DIGESTS_BEFORE`.
4. **Leave the `fvSchemes`, `controlDict` and `.geo` digests untouched.** They
   are the overlay migration's evidence, and the dead-key fix does not change
   them. If re-capturing moves any of them, one of the two changes is wrong.
   Stop and investigate rather than accepting the new digest.

This supersedes the coordinating session's earlier advice to "keep both sets of
assertions". That advice was wrong, because one set asserts exactly the failure
the other set fixes.

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

- [x] **Step 1: Add the seam, not a mapping in core**

Both vocabularies are cardiac, and core may not hardcode a mapping between them.
The adapter or the tutorial spec must declare its kwarg → qualified-id mapping
for `describe` to consult. Generate it from the same catalog entries validation
uses — a second hand-maintained mapping is a second source of truth.

- [x] **Step 2: Prove the payoff end to end**

`describe --plugin cardiacfoam --entry singleCell --config <real overrides>`
must return non-empty `proposed_changes` naming the qualified ids that will
change and their values. **Paste the output in your report.** Until this passes,
Phase 2's second claimed payoff is unmet, and this task is what closes it.

### Findings, 2026-09-24

**Evaluated before building anything, per this task's own instruction: reusing
`spec.plan_case` beats a declared kwarg→qualified-id seam, and needs no mapping
at all.** `describe_entry` already builds `spec` via
`_materialize_resolved_entry(resolution, ...)`, which calls the real factory
(`make_spec(**factory_overrides)`) with the caller's raw overrides -- so
`spec.plan_case` is already the tutorial's own bound resolution closure,
carrying every kwarg the caller named (`ionic_model`, `electro_property_overrides`,
...). Calling it needs no second, hand-maintained mapping, and no per-tutorial
edit at all: every migrated tutorial's `plan_case` already has the same
two-argument shape (`PlanCaseFn`). A declared kwarg-mapping seam (Step 1's own
literal wording) would have been strictly worse on both counts this repository's
rules care about most -- a second source of truth (the mapping could drift from
the catalog `resolve_entry_overrides` actually validates against), and thirteen
per-tutorial edits at exactly the moment two other sessions are editing five of
those same files.

**What calling it actually touches -- established, not assumed, before writing
`_resolve_proposed_changes`.** `plan_case` is not a pure resolver: every
migrated tutorial's `plan_case` calls `commit_case_overrides`/
`apply_input_overrides_planned`, which really commits through
`commit_case_write` (journal, atomic replace into `case_root`). Calling it
against the real `spec.case_root` from a read-only `describe` would be an
unaudited write. So `_resolve_proposed_changes`
(`core/introspection.py`) never passes `spec.case_root` itself: when it
exists, it stages a disposable clone into a fresh `tempfile.TemporaryDirectory`
using `sweep_runner._stage_entry_case` -- the exact mechanism a real sweep run
already uses to isolate one case before mutating it, reused rather than
duplicated -- and calls `plan_case` against the clone; when it does not exist
(a case not yet materialized), it hands `plan_case` an empty scratch directory.
Either way the real `case_root` is only ever *read* (by the staging copy, when
it runs) and never written. This is proven, not merely argued:
`packages/omnidriver-cardiacfoam/tests/test_describe_proposed_changes.py`
hashes every file under the real fixture `case_root` before and after calling
`_write_surface`/`describe_entry` and asserts the digests are identical, and
that no stray staging/journal file was left beside it either.

**The other half: `expected_effects` given its first real consumer.** Task 1
found it computed by every producer (`cardiaccore/workflows/overrides.py`,
`cardiacfoam/overrides.py`, `cardiacfoam/dict_builder.py`) and read by nothing
-- `CaseWritePlan` had no field for it. Closed, not removed: `CaseWritePlan`
gained an `expected_effects: tuple[str, ...] = ()` field, threaded from
`ResolvedMutation.expected_effects` at all **four** `CaseWritePlan(...)`
construction sites (the three above, plus `openfoam/apply_overrides.py`, found
by `grep -n "CaseWritePlan(" packages/*/src/omnidriver/*/*.py
packages/*/src/omnidriver/*/*/*.py` -- one site the module docstring's own
enumeration had not named). `commit_case_write` copies it, and the plan's own
validated `request.parameters` (`ParameterAssignment.to_json()` each), onto the
returned `CaseWriteRecord` (two new fields, `expected_effects` and
`parameters`, both defaulted to `()` so every existing constructor call and
every persisted-completed replay payload written before this change reads back
unchanged). `describe`'s `_resolve_proposed_changes` reads exactly this pair:
`record.parameters` for the structured, qualified-id-bearing `proposed_changes`
entries; `record.expected_effects` for the human-readable superset that also
covers a raw (non-`ParameterAssignment`) target -- a whole-dict removal, a
hex-line rewrite -- that has no single qualified id to carry, by construction
(the 2026-09-23 decision, "a parameter asserts a final state, not only a
value", left exactly this shape outside `ParameterAssignment`'s vocabulary).
**Not found to be redundant**: it is the only field that survives for a target
with no addressable qualified id, so it keeps its consumer rather than being
dropped.

**A serialization corollary of freezing `parameters`, found by running the new
tests, not assumed.** `CaseWriteRecord.__post_init__` deep-freezes each
`parameters` entry the same way `committed`/`evidence` already are (R2 finding
3's convention) -- but unlike those two, a `ParameterAssignment.to_json()`
dict nests further mappings (`binding`, `allowed_bindings`), so the existing
`[dict(entry) for entry in self.evidence]` shallow-unfreeze pattern left an
inner `MappingProxyType` un-thawed, and `json.dumps` on the result raised
`TypeError: Object of type mappingproxy is not JSON serializable`. Fixed by
reusing `_json_value` (already defined in this module for exactly this shape,
`ParameterAssignment.to_json()`'s own `value` field) instead of a second,
shallower unfreeze helper.

**The pasted `describe` output for `singleCell`** (`/tmp/od311/bin/python -m
omnidriver describe --plugin cardiacfoam --entry singleCell --config
<config>`, `config` = `{"ionic_model": "BuenoOrovio", "tissue":
"epicardialCells", "electro_property_overrides":
{"singleCellSolverCoeffs.singleCellStimulus.stim_period_S1": 900},
"physics_property_overrides": {"type": "electroMechanicalModel"}}`, against a
real fixture `case_root` with `constant/electroProperties`/
`physicsProperties`, per this task's own "paste it" instruction — see the
report for the exact commands and the real fixture bytes). `write_surface`:

```
proposed_changes_source: plan_case_preview
proposed_changes_reason: (empty)
expected_effects: [
  "set 'singleCellSolverCoeffs.tissue' in constant/electroProperties",
  "set 'singleCellSolverCoeffs.ionicModel' in constant/electroProperties",
  "set 'singleCellSolverCoeffs.singleCellStimulus.stim_amplitude' in constant/electroProperties",
  "set 'singleCellSolverCoeffs.singleCellStimulus.stim_period_S1' in constant/electroProperties",
  "set 'type' in constant/physicsProperties"
]
proposed_changes (5):
  {qualified_id: singleCellSolverCoeffs.tissue, document: constant/electroProperties, value: epicardialCells, source: case, operation: set}
  {qualified_id: singleCellSolverCoeffs.ionicModel, document: constant/electroProperties, value: BuenoOrovio, source: case, operation: set}
  {qualified_id: singleCellSolverCoeffs.singleCellStimulus.stim_amplitude, document: constant/electroProperties, value: 0.4, source: case, operation: set}
  {qualified_id: singleCellSolverCoeffs.singleCellStimulus.stim_period_S1, document: constant/electroProperties, value: 900, source: case, operation: set}
  {qualified_id: type, document: constant/physicsProperties, value: electroMechanicalModel, source: case, operation: set}
```

Non-empty, real qualified ids, real values, real sources -- Phase 2's second
claimed payoff, closed.

**A removal, as a proposed change -- with an honest limit stated, not
papered over.** `manufactured_monodomain_pseudo_ecg`'s conditional `ecgDomains`
removal (this task's own suggested example) is a `plan_dict_block` **raw
target**, not a `ParameterAssignment` -- Task 6/7's own finding: "not a
`ParameterAssignment` at all... a whole sub-dictionary has no single
`key_path`". Run against a real fixture (`ecg_enabled=False`, its default),
`describe`'s `expected_effects` names it verbatim: `"remove ecgDomains block
from constant/electroProperties"`. It does **not** appear in the structured
`proposed_changes` list, and cannot: there genuinely is no single qualified id
for a whole-dict removal to carry, the same reason `ParameterAssignment`
could not express it in the first place. This is the honest, stated
distinction `_resolve_proposed_changes`'s own docstring draws between the two
return values, not a gap this task papered over.

The one real tutorial that calls `resolve_electro_property_removal`
(`manufactured_bath_bidomain`, the qualified-id-bearing kind) cannot
demonstrate the structured case end to end today: an unrelated,
pre-existing, separately-tracked bug (`bidomainSolverCoeffs.
manufacturedBidomain.fdaBathVariant`, an undeclared key written
unconditionally) makes **every** real invocation of its `plan_case` raise
before returning, confirmed by running it against a real fixture -- and per
this task's own escape hatch ("if its in-flight state blocks you, say so and
pick another"), this file is also one of the two "wrong-scope key" tutorials
a parallel session owns right now (see the "Merge note, 2026-09-24" section
above), so it is not fixed here. Picked another: a minimal, self-contained
`plan_case` built only for
`test_describe_proposed_changes.py::TestAParameterShapedRemovalIsAStructuredProposedChange`,
calling the same real, unmodified production functions
(`resolve_electro_property_removal` -> `commit_case_overrides`) against a
synthetic fixture, isolating the *mechanism* from that tutorial's own,
unrelated bug:

```
_resolve_proposed_changes(...) ->
  proposed_changes = [{
    "qualified_id": "bidomainSolverCoeffs.bathPotentialDomain.groundPatches.xMin",
    "document": "constant/electroProperties",
    "value": None,
    "source": "case",
    "operation": "remove",
  }]
  expected_effects = (
    "remove 'bidomainSolverCoeffs.bathPotentialDomain.groundPatches.xMin' "
    "in constant/electroProperties",
  )
```

A qualified-id-bearing removal, with a null value and `operation: "remove"`,
as a structured proposed change -- proven against real, unmodified production
code, with the real fixture's directory snapshot unchanged before and after.

**Purity evidence.** Every test in `test_describe_proposed_changes.py` hashes
the real fixture `case_root`'s full file tree before and after calling
`_write_surface`/`_resolve_proposed_changes`, and asserts the digests match
and no stray file was left beside it. The manual CLI proof above was checked
the same way directly (`sha256sum` on the fixture files before and after the
`omnidriver describe` invocation): unchanged.

**Revert-to-confirm.** `git stash push` on the seven touched source files
(`core/case_write.py`, `core/case_transaction.py`, `core/introspection.py`,
and the four `CaseWritePlan(...)` producer sites) reproduces two collection
failures (`ImportError: cannot import name '_resolve_proposed_changes'`) for
both new test modules, and four direct failures in
`test_case_write_plan.py` (`TypeError: ... got an unexpected keyword argument
'expected_effects'` / `'parameters'`) -- exactly the new behaviour this task
adds, nothing else. `git stash pop` restored the change; all now pass.

**All four required shapes: 0 failed** (aside from the documented
environmental `ensurepip` abort in `test_every_core_module_imports_from_a_wheel`,
present before this task and unrelated to it). Both static gates pass.

**Correction, 2026-09-24 (coordinator review).** This section's own report
overstated `test_describe_proposed_changes.py`'s proof: calling it "real
fixture, real CLI invocation" is wrong on both halves.
`TestSingleCellProposedChangesEndToEnd` writes a small, hand-authored
`electroProperties`/`physicsProperties` into a fresh temp directory --
plausible, catalog-valid text, not bytes sourced from the native tutorial
tree -- and calls `_write_surface` directly, never through
`packages/omnidriver/src/omnidriver/cli.py`. "Real" there meant only "a
real directory on disk, not a mock/patch", which is not what "real fixture,
real CLI invocation" claims to a reader. The coordinator's own run --
`describe` through the actual `omnidriver` CLI entry point, against a copy
of the actual native `singleCell` tutorial case (not this session's
invented text) -- is the genuine end-to-end proof of this task's Step 2 and
is what actually found Defect 1 below; this module's own unit tests could
not have found it, because none of them drives the CLI. This programme's
rule is that a report must not claim more than was executed; recorded here
with a date rather than silently edited, per house style.

## Corrections from coordinator review, 2026-09-24: two real defects found by running the real CLI against a real case

Both were found by the coordinator running `describe` through the actual
CLI against a copy of the real native `singleCell` tutorial case -- neither
was visible from this task's own unit tests, which is itself the finding
above.

### Defect 1: a failed preview reported as "no changes", not as "unknown"

With `cases_root` supplied inside `--config` rather than as `--cases-root`
(a pre-existing `cli.py:1180` behaviour, `99f3168`, 2026-09-04 -- **not this
task's to fix**; `resolve_cases_root` deliberately has no config-file tier,
`ENVIRONMENT_CONTRACT.md` §12; the coordinator is tracking it separately),
the CLI resolves a different root than the caller intended. The staged
preview then genuinely cannot find `constant/electroProperties` and raises.
Before this correction, `_write_surface` caught that failure inside
`_resolve_proposed_changes`, then fell through to the **naive key-match
fallback regardless of why the resolver-based path failed** -- which
computes `[]` for a raw factory-kwargs `overrides` dict (its own condition,
"the qualified id is already a key in `overrides`", is essentially never
true for one), reporting **the same shape as a legitimate no-op**. `describe`
still exited 0 and an agent reading `proposed_changes: []` would conclude
nothing would change, when the true state is "could not be determined".

**Fixed in `core/introspection.py::_write_surface`**, not by adding a new
exception path but by narrowing which failure gets the naive fallback at
all: the fallback now applies **only** when `spec.plan_case is None` (no
resolver exists for this spec, ever -- the original, stated Phase 2 Task 13
scope limit). Every other reason `_resolve_proposed_changes` returns `None`
-- an ambiguous sweep, or the staged preview itself raising -- now yields
`proposed_changes: null` (`None`) and `proposed_changes_source: "unknown"`,
a third answer a consumer cannot mistake for an empty list of changes.
`proposed_changes_reason` still names the underlying error either way.

**Exit code: left at 0, argued, not left implicit.** `describe` is used
before a case is materialized as often as after -- an ordinary situation,
not a caller error -- and the rest of its payload (the catalog, `modes`,
the config schema, the tutorial contract) stays valid and useful when the
write-channel preview specifically cannot run. Failing the whole command
over one sub-feature would make `describe` markedly less useful as a
discovery tool for exactly the situation it is most needed in. The
distinction an agent needs -- "this preview is unknown, not empty" -- is
carried in the payload's own `proposed_changes`/`proposed_changes_source`
fields, the same way `modes` already reports "not supported: `<reason>`"
without failing the call.

**Verified against the real regression, not only a synthetic test.**
Reproduced the coordinator's exact scenario (`case_root` existing but
missing `constant/electroProperties`) both as a new unit test
(`test_a_staged_preview_that_raises_reports_unknown_not_an_empty_list`,
`test_describe_proposed_changes.py`) and by running the real CLI: before
the fix, `proposed_changes: []`; after, `proposed_changes: null`,
`proposed_changes_source: "unknown"`, `proposed_changes_reason: "the
staged plan_case preview raised: patch target 'constant/electroProperties'
does not exist under ..."`, exit code still `0`, and the (deliberately
empty) case directory left with no file created by the failed attempt.
Verified by reverting `introspection.py` alone: the new test fails
(`AssertionError: '[]' is not None`-shaped), confirming it would have
caught this before the fix; restoring returns it to green.

### Defect 2: a tutorial default reported as `source="case"`

`single_cell._plan_case` folded `stim_amplitude` -- looked up from this
tutorial's own default `stimulus_map` table, keyed by the caller's
`ionic_model` choice, not itself supplied by the immediate caller -- into
the same `case_overrides` dict as `tissue`/`ionicModel` (values the caller
genuinely did choose via `case.params`), and `resolve_entry_overrides`
marks every entry it resolves `source="case"` unconditionally. `describe`
is what made this externally visible for the first time; it is not new
behaviour `describe` introduced. Audit finding F4 again: a tutorial default
presented as though the case had asked for it.

**Fixed, in `single_cell` only**, per the coordinator's explicit scope
limit (`manufactured_bath_bidomain`, `manufactured_eikonal_ecg`,
`manufactured_monodomain_pseudo_ecg`, `niederer_2012`,
`manufactured_monodomain_total_lagrangian_em` are being edited by parallel
sessions right now and are not touched). `stim_amplitude` is now resolved
separately from `case_overrides`, via a new small public function,
`cardiacfoam/overrides.py::resolve_electro_property_set` (the ordinary-`set`
counterpart to `resolve_electro_property_ensure`/`_removal`, added because
neither existing single-key resolver lets a caller declare a `source` other
than the `"case"` `resolve_entry_overrides` always assigns), with
`source="case"` only when `stimulus_map` is not `defaults.STIMULUS_MAP`
itself (the `make_spec` caller replaced the whole table -- a deliberate
choice, even if the replacement's values happen to equal the default's) and
`"template"` otherwise -- the same rule `dict_builder.py`'s synthesis
resolver already applies (`source="case" if delta_t is not None else
"template"`). An explicit `electro_property_overrides` entry for
`stim_amplitude` still wins (`merge_assignments`'s unchanged "second write
wins" order) and is still `"case"` -- a genuine caller-supplied value.
Three new tests in `test_single_cell_write_channel.py` cover all three
cases; verified against the real CLI: `stim_amplitude` now reports
`source: "template"` for the default table and `"case"` for either an
explicit `stimulus_map` replacement or an explicit `electro_property_overrides`
entry. Byte-for-byte output is unchanged (`source` is metadata, never
rendered) -- confirmed by the unmodified pre-existing characterization
tests staying green.

**Owed, not done here: the same provenance audit across every other
tutorial's `_plan_case`.** `single_cell` is very unlikely to be the only
one folding a tutorial-computed default into a `resolve_entry_overrides`
call and reporting it `source="case"` -- `stim_amplitude` is the worked
example, not a special case. Per the coordinator's explicit instruction,
this is **not** audited or fixed for any other tutorial in this task,
because five of the eleven migrated tutorials are mid-edit in two parallel
branches right now. Tracked here as owed work, to be done once those
branches merge: re-check every `_plan_case` for a value it computed from
its own defaults (not the immediate caller's argument) folded into a
`resolve_entry_overrides`/`case_overrides` dict, and give it an explicit
`source` the same way, using this same rule and `resolve_electro_property_set`.

**All four required shapes, on the tree with both defects fixed: 0 failed**
(aside from the documented environmental `ensurepip` abort). Both static
gates pass.

**What this task's own brief got wrong.** Step 1's literal instruction ("The
adapter or the tutorial spec must declare its kwarg → qualified-id mapping")
described the seam the plan expected to need; the evaluation this same
section asked for first found a cheaper, more honest alternative (reuse
`plan_case` itself) that needs no such mapping at all -- recorded here as the
task's own "Evaluate this before building anything" section anticipated, not
silently substituted.

---

## Task 10: `Allrun`, and delete what is unreachable

- [x] **Step 1: Route `sweep.py::materialize_case`'s `Allrun` write — bypass 5**

It calls `build_and_launch(..., dry_run=True)` — already channel-routed — then
writes `Allrun` with a bare `write_text` outside it. Smallest bypass; fold it in.

- [x] **Step 2: Delete `provision_mesh`'s unreachable branch**

R4 established the `BLOCK_MESH_SOLVERS` branch has **zero production callers** —
its only exerciser is `test_solver_mesh_provisioning.py` calling it directly. I
confirmed the sole caller, `ionic_catalog_verification.py`, hardcodes
`singleCellSolver`. Delete the branch and the test that exercises only it, with a
dated note. Unreachable code beside a live route in one function is how the next
reader mistakes one for the other.

**Before deleting, re-run the caller check** — Task 6 may have added one.

### Findings, 2026-09-24 (backfilled by Task 11 — this task's own checkboxes and
the Status table above were still unchecked/"pending" when Task 11 started,
even though both commits below were already on `HEAD`)

**Step 1 (`2fd2499`).** `build_case`/`build_and_launch` gained
`include_allrun` (default `False`, so every other caller is unaffected); when
`True`, `resolve_synthesis_mutation` folds `Allrun` in as one more content
target (a new `plan_verbatim_content` `executable=True` flag) in the same
`CaseWritePlan`, committed by the same one `commit_case_write` call.
`materialize_case` now passes `include_allrun=True` and does no direct
filesystem write of its own. The trap named in the commit: a content
target's mode previously hardcoded `mode=None` (non-executable); an
"executable" content target now writes `(existing mode | 0o111)` when the
document already existed, or `0o755` fresh, reproducing the pre-migration
`write_text` + `chmod` behaviour exactly, characterized on both a fresh case
and one with a pre-existing `Allrun`.

**Step 2 (`d033399`).** Re-verified R4's caller-count claim after Tasks 6–9:
`provision_mesh(` still has exactly one production call site
(`ionic_catalog_verification.py`, hardcoding `singleCellSolver` — always the
`MESHLESS_SOLVERS` branch). Deleted the `BLOCK_MESH_SOLVERS` branch and its
two tests that exercised only it, mapping each pinned behaviour to a
survivor: "`dx` controls cell count" survives in
`omnidriver-openfoam/tests/test_mesh_provisioning.py` and
`test_dict_builder.py::test_dx_kwarg_controls_generated_block_mesh_resolution`
(the live channel path); "`dry_run` does not write `blockMeshDict` for a
spatial solver" does not survive anywhere and is correctly gone — it was a
property of the dead branch specifically, and the live path's `blockMeshDict`
content target has never been `dry_run`-gated.

Both commits' full rationale, including their own revert-to-confirm
evidence, is in their commit messages (`git show 2fd2499`, `git show
d033399`) rather than restated here.

---

## Task 11: Close-out, with a widened inventory

- [x] **Step 1: Widen the inventory script — this is the point**

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

- [x] **Step 2: Classify every hit, and list open bypasses explicitly**

Classes: framework-authored case input (bypass if not through
`commit_case_write`), declared workflow output, standalone export, source
artifact, transaction mechanics, framework bookkeeping, test scaffolding. One
line of justification each.

**A bookkeeping file a later run reads as input is not bookkeeping.** R4
spot-checked five and found none miscategorised; check the ones this phase adds.

- [x] **Step 3: Four shapes, both gates**

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

- [x] **Step 4: Answer the four G3 exit criteria, one line of evidence each**

"Entry/sweep/remediation semantic parity on supported modes; no framework-authored
input bypasses; unsupported modes refuse explicitly; obsolete routes removed."

**If G3 still cannot close, say so and say what remains.** Phase 2's close-out
did exactly that, and it was the right call — a close-out declaring success over
known bypasses converts a known gap into a believed guarantee.

`write_cell_set` is expected to remain open by design. State it as a declared
exception with its reason, not as an oversight.

### Findings, 2026-09-24: G3 close-out

**Everything below was executed, not assumed.** Grep output, git history
(`git log`, `git show`, `git merge-base`), and direct file reads are cited by
command or path throughout. No test run is claimed that was not actually
run; no CLI output is pasted that was not actually produced.

#### Step 1 — the widened inventory script

```bash
grep -rnE 'write_text|write_bytes|open\(|shutil\.copy|shutil\.copytree|os\.replace|\.rename\(|\.touch\(|\.chmod\(|os\.symlink|os\.link|json\.dump|yaml\.dump|pickle\.dump|FoamFile\(|subprocess\.run|subprocess\.Popen' \
  packages/*/src/ --include='*.py' | grep -v '/build/' | grep -v '__pycache__'
```

(`.chmod(` was added to the plan's own list — Task 10's `Allrun` executable-bit
handling reads/writes mode via `os.chmod` in `transaction_mechanics.py`, so
leaving it out would have re-created exactly the class of blind spot this
step exists to close.) 180 hits, `packages/*/src/`, `.py` only,
`/build/`/`__pycache__` excluded. Two classes the grep cannot see, per the
plan's own instruction, were closed by direct reading rather than by
grep: every `FoamFile(` construction site outside
`openfoam/foam_backend.py`/`openfoam/mutators.py` (11 sites — all read-only,
`[...]`/`.get(...)`, no `__setitem__`/`del`, confirmed by reading each one),
and every `subprocess.run`/`Popen` call (13 sites — none author a case
input; see the table below).

#### Step 2 — classification

One line of justification each. Sites sharing one file and one class are
grouped into one row; individual line numbers are given where more than one
class applies within a file.

| site(s) | class | justification |
|---|---|---|
| `core/case_transaction.py` (`_atomic_write_bytes` calls, `_write_one`/`_restore_one`) | transaction mechanics | this **is** `commit_case_write`'s own atomic-replace/journal-recovery primitive — the channel itself, not a caller of it |
| `core/runtime/transaction_mechanics.py`, `sweep_manifest.py`, `postprocess_phase.py`, `attempt_lease.py`, `provenance.py`, `remediation_audit.py`, `repair_loop.py`, `workflow_state.py`, `reconciler.py`, `resume.py`, `failure_context.py`, `remediation_transaction.py` (all, incl. its rollback `_atomic_write_bytes` at line 269 — restores exactly the prior bytes, authors nothing new) | transaction mechanics / framework bookkeeping | leases, journals, manifests, provenance snapshots, remediation before-images and audit logs — all in the framework's own bookkeeping locations, none read by a native OpenFOAM solver as case configuration |
| `core/runtime/sweep_runner.py` (staging `shutil.copytree`/`os.replace`, `_write_staging_journal`) | transaction mechanics | verbatim relocation of an already-existing, user/tutorial-authored case to a private sibling then an atomic rename — copies content, authors none |
| `core/runtime/sweep_runner.py` (`run_document_path.write_text(...)`) | framework bookkeeping | `run_document.json` lives in the sweep's own `output_dir`, not `case_root` — its own comment: "unrelated to the tutorial's real `case_root`"; drives the orchestrator's next `omnidriver run` invocation, never read by a solver |
| `core/runtime/workflow_runner.py` (log file `open("w")`, `subprocess.Popen`) | declared workflow output / transaction mechanics | executes a workflow step's own declared command (`blockMesh`, `Allrun`, …) and logs its stdout/stderr — the live, legitimate execution mechanism Task 7 already established for `_ensure_mesh`'s redundant duplicate, not a bypass of it |
| `core/runtime/output_collection.py` (`shutil.copy2`) | declared workflow output | archives solver-produced results after a run (`OutputCollisionError` on a content mismatch) — collects outputs, authors no input |
| `postprocessing/table_writer.py` | declared workflow output | writes CSV/HTML result tables from run data |
| `cli.py` (all ~20 hits) | not a write at all | every hit is `print(json.dumps(...))` to stdout, or `json.dumps(...).encode()` for a digest — no file write in this module |
| `core/provider_identity.py`, `core/plugin_profile.py`, `core/case_write.py`, `core/provider_stack.py`, `core/plugin_interface.py` | not a write at all | `json.dumps(...)` used to build a canonical byte string for hashing/comparison, never passed to a file write |
| `core/utility_catalog.py` (`toml_path.open("rb")`) | not a write | reads a catalog TOML, read-only |
| `openfoam/case_rendering.py` (`_snapshot_copy`'s `shutil.copy2`; `snapshot_path.write_bytes`/`write_text`) | transaction mechanics | the renderer's own private-snapshot mechanism — reads the real case once, writes only inside `snapshot_root`, per its own docstring: "the one read of the real case a patch renderer performs" |
| `openfoam/mutators.py` (`update_foam_entry`/`remove_foam_dict`/etc.'s `write_text` calls) + `openfoam/foam_backend.py` (`FoamFile.__setitem__`, `del foam_file[path]`, `write_text`) | transaction mechanics (the format owner) | `foam_backend.py`'s `__setitem__`/`del` — the two operations the plan specifically warned a grep cannot see — are called **only** from `mutators.py` (confirmed: `grep -rn "foam_backend\." packages/*/src/` outside `mutators.py` returns nothing); `mutators.py`'s own public functions are called from `case_rendering.py` (legitimate), `apply_overrides.py` (legitimate, see below), and a bounded, named set of direct tutorial callers (see the open-bypass list) |
| `openfoam/apply_overrides.py` (`update_foam_entry` × 3) | transaction mechanics | confirmed by direct read: every call targets `snapshot_root / ...`, never `case_root` — Task 5's migration holds; `case_root` is provably never touched until `commit_case_write`'s own atomic replace |
| `openfoam/openfoam_environment.py` (`subprocess.run`, `open(err_file)`) | not a case input | environment discovery (sourcing `bashrc`, probing `PATH`) — ambient truth per this repo's supplied-vs-discovered rule, not case authorship |
| `openfoam/effective_dictionary.py` (`subprocess.run` of real `foamDictionary`) | not a case input | F1b's readback comparison — reads a value back through the native binary, writes nothing |
| `openfoam/mesh_geometry.py`, `function_object_fields.py`, `case_dict_keys.py`, `cardiacfoam/detection.py`, `runtime_evidence.py`, `run_document_config.py`, `validation.py`, `dict_builder.py:452` | not a write | every `FoamFile(...)` here is a getitem/`.get`/`.keys()` read chain, confirmed by direct reading (no `[...] =`, no `del`) |
| `openfoam/tet_mesh_provisioning.py::render_tet_geo` | **framework-authored case input — open bypass** | writes `box.geo` (a gmsh mesh template with `__LC__` substituted) directly into `case_root`; called from three tutorials' tet paths, none through the channel (see list below) |
| `cardiacfoam/dict_builder.py` (`regenerate_electro_properties`, lines 800/821/823) | transaction mechanics | confirmed by tracing its one caller, `overrides.electro_properties_regeneration_scope`, into `apply_overrides.py`'s `regen_scope.regenerate(snapshot_root / ...)` — this is Task 5's own "regeneration scope," already migrated, running on the snapshot |
| `cardiaccore/operations/electrodes.py` (`write_reference_offset_bundle`, `write_electrode_positions`) | standalone export (Phase 2 classification, unchanged) | both functions carry their own 2026-09-23 Phase 2 Task 12 classification comment in source: a coordinate bundle for cross-tool consumption, no dictionary key |
| `cardiaccore/operations/vtu_selection.py::write_cell_set` | **declared exception** | unchanged from Phase 2 — writes a `cellSet` format no renderer understands; single consumer, revisit when a second appears |
| `cardiacfoam/mesh_provisioning.py::provision_mesh` (`shutil.copyfile`) + `cardiacfoam/ionic_catalog_verification.py` (all hits: 3× `write_text`, `provision_mesh`, `subprocess.run`) | test scaffolding / drift-gate tooling | `provision_mesh`'s **only** production caller is `ionic_catalog_verification.py` (confirmed: `grep -rn "provision_mesh(" packages/*/src/` outside its own definition), which authors a throwaway scratch case per ionic model solely to run the real `listCellModelsVariables` utility and diff its output against the static catalog — a maintainer drift-gate, invoked only from `tests/test_ionic_catalog_live_verification.py`/`test_ionic_catalog_verification.py`, no CLI entry point, no tutorial or workflow reachability; the case it authors is never a real user's case |
| `cardiacfoam/runtime_profile.py` (`subprocess.run` × 3, `manifest_path.write_text`, `artifact_path.open("rb")`) | framework bookkeeping | a build/runtime evidence manifest (library digests, `WM_PROJECT_VERSION`, …), not case configuration |
| `cardiacfoam/tutorials/cable_1d_restitution.py` (`.driverfoam_case_id`, `.cardiacfoam_protocol.json`) | framework bookkeeping / standalone export (Task 7 classification, unchanged) | reader traced in Task 7 to the native tree's own `postProcessing_cableRestitution.py`; unchanged, re-confirmed present in current source |
| `cardiacfoam/tutorials/manufactured_purkinje_graph.py` (`shutil.copy2`), `manufactured_monodomain_1d3d.py` (`shutil.copy2`, `block_mesh_active.write_text`) | **blocked on artifact staging** (Task 7 correction, unchanged) | re-confirmed present, unfixed, in current source — see the dedicated list below |
| `cardiacfoam/tutorials/{manufactured_bath_bidomain,manufactured_eikonal_ecg,manufactured_monodomain_pseudo_ecg}.py` (tet overlay `shutil.copy`, `render_tet_geo` calls) | **framework-authored case input — open bypass on `main`** | fixed on unmerged `claude/compassionate-gates-967e8d` (`df0a059`); open on `main` as measured — see the list below |
| `cardiacfoam/tutorials/{manufactured_bath_bidomain,manufactured_eikonal_ecg,manufactured_monodomain_pseudo_ecg}.py` (uncataloged `fvSchemes`/`fvSolution`/`controlDict` passthrough: `grad_scheme`, `phi_tolerance`, `n_outer_correctors`, `n_nonorthogonal_correctors`, `fv_scheme_overrides`, `fv_solution_overrides`, `control_dict_overrides`) | **framework-authored case input — open bypass, newly surfaced by this audit** | direct `update_foam_entry` calls against the real `case_root`, inside the now-"migrated" `_plan_case` for all three tutorials — not fixed by either unmerged branch; see below |
| `cardiacfoam/tutorials/manufactured_bath_bidomain.py::_plan_case` (`uncataloged_case_overrides` → `apply_electro_property_overrides`, line 562) | **framework-authored case input — open bypass** | writes the dead `manufacturedBidomain.fdaBathVariant` key via the pre-channel direct applier, deliberately, unconditionally; see below |
| `cardiacfoam/tutorials/niederer_2012.py` (`control_dict_path.open("w")`, `target_file.write_text` for `.geo`, plus its own `apply_electro_property_overrides`/`apply_physics_property_overrides` calls) | **framework-authored case input — open bypass on `main`** | entire `mesh_family=="tet"` branch (`_apply_case`); `.geo` write fixed on `claude/compassionate-gates-967e8d`, open on `main` |
| `cardiacfoam/generic_case_mutation.py::apply_case_mutation` | **framework-authored case input — open bypass, resolved from "unknown" by this audit** | Task 8 flagged cardiacFoam's own generic-case adapter callback as a write whose channel status core "cannot see" and left "tracked separately, not fixed here." Read directly: it calls `apply_electro_property_overrides`/`apply_physics_property_overrides` on the real `case_root`, no channel. Confirmed live and reachable via `cardiacfoam_plugin.py`'s import of `tutorials.generic_case`, not dead code. |

**Bookkeeping-file-read-as-input check, per the plan's own warning.** The
Phase-3-era additions this warning targets are `cable_1d_restitution`'s two
sidecars (already traced to a real, named native reader in Task 7 — not
re-litigated here) and Task 10's `run_document.json`. Checked
`run_document.json`'s only consumer: `sweep_runner.py`'s own
`_run_case_process` passes it right back to `omnidriver run
--run-document <path>` as the next process's *orchestration* input (which
step to run, in what order) — never unpacked into a case's `constant/`/
`system/` directory. Not a case input.

#### The three explicit categories

**Open bypasses (framework-authored case input, not through
`commit_case_write`), measured on `main` (`d033399`):**

1. `manufactured_eikonal_ecg.py::_apply_case` (lines 185–324, the entire
   `mesh_family=="tet"` route): `render_tet_geo` (294), the numerics-overlay
   `shutil.copy` (301), three direct `update_foam_entry` calls for
   `grad_scheme`/`fv_scheme_overrides`/`fv_solution_overrides` (304–316),
   and `apply_electro_property_overrides` × 2 +
   `apply_physics_property_overrides` (320–322). Fixed on
   `claude/compassionate-gates-967e8d` for the `render_tet_geo`/overlay part
   only.
2. `manufactured_eikonal_ecg.py::_plan_case` (lines 417–429): the same three
   `update_foam_entry` calls (`grad_scheme`/`fv_scheme_overrides`/
   `fv_solution_overrides`), direct, **inside the already-"migrated" hex
   path**. Not fixed on either unmerged branch.
3. `manufactured_bath_bidomain.py::_plan_case` (lines 424–432): tet branch
   (`render_tet_geo`, overlay `shutil.copy`), direct. Fixed on
   `claude/compassionate-gates-967e8d`.
4. `manufactured_bath_bidomain.py::_plan_case` (lines 538–557): the
   `grad_scheme`/`phi_tolerance`/`fv_scheme_overrides`/`fv_solution_overrides`
   passthrough, direct, unconditional. Not fixed on either unmerged branch.
5. `manufactured_bath_bidomain.py::_plan_case` (line 562):
   `apply_electro_property_overrides(electro_properties,
   uncataloged_case_overrides)` — writes the dead
   `manufacturedBidomain.fdaBathVariant` key, unconditionally, via the
   pre-channel direct applier. Low-stakes (nothing native reads this key)
   but a real write outside the channel. Not addressed by either unmerged
   branch (a different fix — dropping the dead key rather than keeping it —
   is what the uncommitted `sharp-cannon-7e5e7c` worktree apparently
   intended, per the Merge note correction above, but it never landed).
6. `manufactured_monodomain_pseudo_ecg.py::_plan_case` (lines ~398–404): tet
   branch (`render_tet_geo`, overlay `shutil.copy`), direct. Fixed on
   `claude/compassionate-gates-967e8d`.
7. `manufactured_monodomain_pseudo_ecg.py::_plan_case` (lines 452–489): the
   `grad_scheme`/`phi_tolerance`/`n_outer_correctors`/
   `n_nonorthogonal_correctors`/`fv_scheme_overrides`/`fv_solution_overrides`/
   `control_dict_overrides` passthrough, direct, unconditional. Not fixed on
   either unmerged branch.
8. `niederer_2012.py::_apply_case` (the entire `mesh_family=="tet"` route):
   hand-rolled `endTime` writer (`control_dict_path.open("w")`, line 74),
   `.geo` `write_text` (line 232, duplicating rather than reusing
   `render_tet_geo`), and `apply_electro_property_overrides` × 2 +
   `apply_physics_property_overrides` (237–239). The `.geo`
   duplication is fixed (by reuse) on `claude/compassionate-gates-967e8d`;
   the rest is not.
9. `cardiacfoam/generic_case_mutation.py::apply_case_mutation` — cardiacFoam's
   real generic-case adapter callback, live and reachable via
   `cardiacfoam_plugin.py`, writes `electroProperties`/`physicsProperties`
   directly via the pre-channel appliers whenever a cardiacFoam-recognized
   generic case (with a case marker) is materialized. Task 8 named this
   branch's channel status as unknown to core; this audit confirms it is, in
   fact, unmigrated. Not addressed by either unmerged branch.

Items 1, 3, 6, 8's `render_tet_geo`/overlay portions are fixed on
`claude/compassionate-gates-967e8d` (unmerged — see Step 3/the
main-vs-unmerged accounting). Items 2, 4, 5, 7, 9 are not addressed by
**either** unmerged branch and were not previously named as a discrete open
bypass anywhere in this plan; they are this audit's own finding, surfaced
precisely because migrating a tutorial's *addressable* overrides
(Task 6/`ca11a25`) left its *unaddressable* ones — the ones the catalog
never declared — exactly where they were.

**Blocked on artifact staging** (the missing capability Task 7's review
correction named; the channel can reference a source artifact by digest but
cannot place one in a case):

- `manufactured_purkinje_graph.py::_apply_case`'s `purkinjeGraph.<id>` →
  `purkinjeGraph` copy.
- `manufactured_monodomain_1d3d.py`'s identical `purkinjeGraph` copy.
- `manufactured_monodomain_1d3d.py`'s `blockMeshDict.3D` → `.active` copy
  (a case input — decides which document the channel's own patch
  subsequently addresses — not bookkeeping).

**Declared exceptions:**

- `cardiaccore/operations/vtu_selection.py::write_cell_set` — a `cellSet`
  format no renderer understands; single consumer; revisit when a second
  appears. Unchanged from earlier tasks.

#### Step 3 — main-vs-unmerged accounting

`claude/compassionate-gates-967e8d` (`df0a059`, on `9d159fa`): confirmed
**not** an ancestor of `main` (`git merge-base --is-ancestor df0a059 main` →
false; `git log main..claude/compassionate-gates-967e8d` shows exactly
`df0a059`). Its tet-overlay-copy and `.geo`-reuse fixes are real but not on
`main`; open bypasses 1/3/6/8 above are reported as open **on `main`**, per
this task's own instruction to measure main as it is.

`claude/sharp-cannon-7e5e7c` (`c3d12a3`): confirmed its branch *ref* **is**
an ancestor of `main` (`git merge-base main claude/sharp-cannon-7e5e7c` →
`c3d12a3` itself, zero unique commits) — so it is not "unmerged" in the
sense of carrying commits `main` lacks. Its **worktree**
(`.claude/worktrees/sharp-cannon-7e5e7c`) still has real uncommitted changes
to `manufactured_bath_bidomain.py`, `manufactured_monodomain_total_lagrangian_em.py`,
and three test files (`git status --short` confirmed), so the plan's
original characterization ("uncommitted... any green it reports may be
main's") holds for its substance even though the branch pointer itself is
stale. See the dated correction on the Merge note section above for the
full accounting, including which half of its intended fix (bath_bidomain)
is already independently resolved on `main` via `ca11a25`, and which half
(`manufactured_monodomain_total_lagrangian_em`) is not.

#### Step 4 — four shapes and both gates

Ran fresh: `ps aux | grep -c "od311/bin/python"` showed no other process
actually using `/tmp/od311` (the count of 2 was `grep` matching its own
command-line argument, confirmed by a second, more specific check returning
empty) — so `/tmp/od311`/`/tmp/odcore`/`/tmp/wheeltest`/`/tmp/wheelenv`
were rebuilt at their standard paths, not `-closeout` variants.

| shape | command | result |
|---|---|---|
| all four, not slow | `/tmp/od311/bin/python -m pytest packages/ -q -m "not slow"` | 2565 passed, 259 skipped, 2 deselected, 0 failed |
| core alone | `/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q` | 1126 passed, 94 skipped, **1 failed**: `test_every_core_module_imports_from_a_wheel`, `SIGABRT` in its own disposable venv's `ensurepip` — the documented, pre-existing environmental failure named in this plan's own Step 3, not a defect from this task |
| wheel artifact gate | `/tmp/od311/bin/python -m build --outdir /tmp/wheeltest packages/omnidriver` then `/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py` (installed via `uv pip install -q "/tmp/wheeltest/omnidriver-0.1.0-py3-none-any.whl[post]" pytest` — the plan's own glob form, `omnidriver-*.whl[post]`, is not shell-expanded inside quotes and fails with `uv`; substituted the literal built filename) | `modules imported: 81/81`; `Wheel artifact OK: core installs and runs standalone.` exit 0 |
| wheel suite | `/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q` | 959 passed, 262 skipped, 0 failed |
| gate: import boundaries | `/tmp/od311/bin/python scripts/check-import-boundaries.py` | exit 0 |
| gate: capability seams | `/tmp/od311/bin/python scripts/export-capability-seams.py --check` | exit 0 |

**Plan-command correction, 2026-09-24.** The plan's own Step 3 command block
quotes the wheel glob (`"/tmp/wheeltest/omnidriver-*.whl[post]"`), which
`uv pip install` does not shell-expand — it fails with `error: The wheel
filename "omnidriver-*.whl" is invalid: Must have a Python tag`. Worked
around by installing the literal built filename instead; recorded here since
the plan's command as written does not run.

The durable claim, per this plan's own rule: **0 failed** in every shape
except the one documented, pre-existing environmental failure. No suite
total is otherwise quoted as a permanent fact.

#### Step 5 — the four G3 exit criteria

> "Entry/sweep/remediation semantic parity on supported modes; no
> framework-authored input bypasses; unsupported modes refuse explicitly;
> obsolete routes removed."

- **Entry/sweep/remediation semantic parity on supported modes: met, on
  what has actually migrated.** Task 5's `--apply` migration and Task 6/6b's
  ten fully-collapsed tutorials each carry their own byte-for-byte
  characterization tests proving parity against pre-migration output,
  verified by reverting (per-task findings, unchanged by this audit).
  `remediation_transaction.py`, read directly for this close-out, performs
  only backup/restore/archive around whatever wrote the values — it is not
  itself a second writer, so it inherits whatever the underlying write path
  (now largely channel-routed) already proved. **Not met for the three
  tutorials in the open-bypass list**: `manufactured_bath_bidomain`,
  `manufactured_eikonal_ecg`, `manufactured_monodomain_pseudo_ecg`, and
  `niederer_2012`'s tet route still have a real second writer
  (`update_foam_entry`/`apply_electro_property_overrides` direct calls)
  whose parity with the channel path is not a settled question — it *is*
  the channel path, running unaudited, beside a channel commit in the same
  function.
- **No framework-authored input bypasses: not met.** Nine open-bypass sites
  measured above, on `main`, right now — four newly surfaced by this
  audit (bypasses 2, 4, 7, 9) that were not previously named anywhere in
  this plan as a discrete bypass.
- **Unsupported modes refuse explicitly: met.** `generated_input` is gone
  (Task 1); `resolve_entry_overrides`/`CaseMutationRequest` refuse an
  undeclared key or an unresolvable dynamic binding by raising, not by
  silently writing (Task 2's Gap 1/Gap 2 closure, re-confirmed unchanged in
  current source); `describe`'s `_write_surface` now reports `unknown`
  rather than a misleading empty `proposed_changes` list when a preview
  cannot run (Task 9, Defect 1, unchanged).
- **Obsolete routes removed: met, for what Task 6b/10 actually retired.**
  `set_end_time`/`replace_block_mesh_resolutions` retired with their last
  callers (`e3f5d08`); `provision_mesh`'s unreachable `BLOCK_MESH_SOLVERS`
  branch deleted (`d033399`). **Not fully met**: `apply_electro_property_
  overrides`/`apply_physics_property_overrides`/`update_foam_entry`-as-a-
  direct-caller are all still live, real, non-obsolete routes for the nine
  open-bypass sites above — "obsolete" does not yet describe them, because
  they are still load-bearing for real tutorial behaviour today.

#### Can G3 close?

**No.** Three of the four criteria are only partially met, and "no
framework-authored input bypasses" is the one this gate exists to guarantee
— it is not met, on `main`, as measured directly against current source and
confirmed by two independent checks (the widened grep, and direct reading of
every `FoamFile`/`subprocess` site the grep cannot classify by itself). This
matches Phase 2's own precedent for this situation: report the gap plainly
rather than let a close-out convert a known bypass into a believed
guarantee.

**What remains, and roughly what each item involves:**

1. **The uncataloged `fvSchemes`/`fvSolution`/`controlDict` passthrough**
   (bypasses 2, 4, 7) in `manufactured_eikonal_ecg`, `manufactured_bath_bidomain`,
   `manufactured_monodomain_pseudo_ecg`. Each is a handful of direct
   `update_foam_entry` calls for keys the catalog does not declare (arbitrary
   caller-supplied key/value pairs, not fixed catalog entries). Closing this
   needs either a catalog extension (declaring these as real entries, if
   they have a genuine closed shape) or a new `ParameterAssignment`-shaped
   "uncataloged/raw entry" address that the channel can carry without
   requiring catalog membership — a real design decision, not a mechanical
   migration.
2. **The three tet-branch open bypasses** (1, 3, 6, 8's `render_tet_geo`/
   overlay portions) are **already fixed** on `claude/compassionate-gates-967e8d`
   (`df0a059`) — this is a merge decision, not new work, but the merge
   itself has a real semantic conflict (see the Merge note) that needs
   resolving, not a fast-forward.
3. **The dead-key write** (bypass 5, `manufactured_bath_bidomain`'s
   `uncataloged_case_overrides`) — smallest item here: either drop the dead
   key outright (nothing reads it) or, if some external consumer is
   genuinely unknown and the key must be kept for safety, give it a real,
   channel-routed home.
4. **`generic_case_mutation.py::apply_case_mutation`** (bypass 9) — needs
   its own design pass, the same kind Task 8 gave core's `generic_case.py`:
   cardiacFoam's adapter callback has real catalog vocabulary available (it
   is cardiacFoam-specific, not core), so this is more tractable than
   Task 8's core-side branch, but it is unstarted.
5. **Artifact staging** (the missing capability) — see the handoff item
   below; blocks three more sites even once the above five are closed.
6. **`manufactured_monodomain_total_lagrangian_em`'s wrong-scope key**
   (`electromechanicalVerificationModel.type`) — a correctness bug, not a
   channel bypass per se (the tutorial's own default call already raises
   before any write), but it blocks that tutorial from ever exercising its
   real write path until fixed. Already tracked (`task_7eca39be`).

#### Handoff — every known follow-up, recorded so the next phase inherits it

- **Artifact staging.** The channel can reference a source artifact by
  digest (`source_artifacts`) but cannot place one at a case-relative
  destination. Blocks: `manufactured_purkinje_graph`'s `purkinjeGraph`
  copy, `manufactured_monodomain_1d3d`'s identical copy, and
  `manufactured_monodomain_1d3d`'s `blockMeshDict.3D` → `.active` copy.
  Design surface: what it references, what precondition it checks, how
  `commit_case_write` places bytes it never rendered. Named, not designed,
  by Task 7's 2026-09-24 review correction; still unbuilt.
- **The provenance audit across every tutorial's `_plan_case`.** A value
  computed from a tutorial's own defaults (not the immediate caller's
  argument) must be `source="template"`, not `source="case"`, when folded
  into `resolve_entry_overrides`. Worked example: `single_cell`'s
  `stim_amplitude`, fixed in `136112a`. The other ten migrated tutorials
  are unaudited for this — Task 9's own "owed, not done here" note,
  unchanged by this audit (this task did not re-run that audit; it is
  orthogonal to the bypass inventory above, which tracks *where* a write
  lands, not what `source` label it carries once it does).
- **`generic_case.py`'s adapter-callback branch** (core, Task 8) — left on
  the deprecated `apply_case` fallback because core cannot see whether the
  callback writes through the channel. This audit resolves the cardiacFoam
  instance of that question (see bypass 9: it does not), but the core-level
  branch itself — the general mechanism for *any* adapter's callback, not
  just cardiacFoam's — is still unaudited for other adapters and still
  structurally unable to see into an opaque callback.
- **The two unmerged branches, and their semantic merge conflict.**
  `claude/compassionate-gates-967e8d` (`df0a059`, real unmerged commits)
  fixes bypasses 1/3/6/8's tet-overlay portions; merging it into
  `main` will hit the semantic conflict the Merge note describes
  (`_TET_DIGESTS_BEFORE`'s two `assertRaisesRegex` tests, now stale because
  `main` already fixed the dead-key raise via `ca11a25`) — the note's own
  four-step resolution still applies, adjusted for `main`'s current state.
  `claude/sharp-cannon-7e5e7c`'s branch ref is already an ancestor of
  `main`, but its **worktree**'s uncommitted fix for
  `manufactured_monodomain_total_lagrangian_em` never landed anywhere;
  that fix (not a branch merge) is what is still needed. The merge order
  and disposition are the owner's decision.
- **The `cases_root` CLI footgun.** A config-supplied `cases_root` is
  silently overwritten (`cli.py`, from `99f3168`, 2026-09-04). Named by
  Task 9's coordinator review (Defect 1's root cause) as tracked
  separately, not this plan's to fix. Unchanged by this audit.
- **The duplicated placeholder grammar** (Phase 2's G4 handoff). Not
  re-investigated by this task — out of the write-channel scope this plan
  covers (G3, not G4) — and not re-confirmed present or absent here; carry
  it forward as an open question for whoever owns G4.
- **The nine open bypasses this close-out found**, items 1–9 above, are
  themselves the primary handoff: none were fixed by this task per its own
  "measure and record only, do not migrate" rule.
