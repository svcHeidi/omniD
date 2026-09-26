# Core generality: replace core's OpenFOAM-shaped concepts with general ones

**Date:** 2026-09-26 · **Status:** implemented 2026-09-26 (plan
`docs/superpowers/plans/2026-09-26-core-generality.md`). The scope split was
approved by the owner in conversation (2026-09-26); the written form is
written from those decisions.
**Follows:** `2026-09-25-solver-conformance-and-opencarp-design.md`. openCARP
now passes C1–C10, so a second solver exists to prove each change against.
**Evidence:** a read-only map of every OpenFOAM-shaped concept in core
(2026-09-26, summarised in §2), the core shape gate's baseline
(`scripts/core-shape-baseline.txt`), and the audit
`docs/audits/2026-09-25-generality-and-landscape.md` §2.

## 1. Why

Core names no cardiac vocabulary, and it now has a gate against OpenFOAM
layout terms. But its data model still thinks in OpenFOAM:
- environments are sourced shell profiles;
- outputs live in time directories under `processor*` replicas;
- every plugin must stub dictionary-shaped members;
- core's own files are declared by the OpenFOAM layer.

The map found most of this is threading or dead code. Real logic exists in only
three places. This spec replaces each concept with the smallest general form
that serves both an OpenFOAM stack and openCARP.

## 2. What the map found

| concept | reality | general form |
|---|---|---|
| environment as a sourced `bashrc` (69 gate hits) | 100% parameter threading through `cli`, `strict_planning`, `plugin_capabilities`, `compatibility`, `plugin_interface`; dead data in `generic_case` params. Real logic lives only in openfoam/cardiacfoam plugins | one opaque `environment_source: str \| None` (CLI `--environment-source`) that core passes through and never reads; each plugin interprets it (OpenFOAM: a script to source; openCARP: ignored) |
| time directories (`{time}`, `time_indexed`, `time_directory_name_pattern`, `preserved_time_directory_names`, `decomposition_directory_prefix`, `selected_start_time`, the `processor*` walk in `provenance_inputs`) | real logic in `reconciler`, `workflow_runner` snapshots, `sweep_runner` cleaning/staging, `provenance_inputs`, `registry` | plugin-declared **instance directories** (`instance_directory_pattern`, `preserved_instance_names`, placeholder `{instance}`); plugin-declared **replica directories** (`replica_directory_globs`); one provenance hook `input_roots(case_root, resolved_case) -> tuple[relpath]` that composes start time and replicas in the plugin. Core stops knowing "start time" and "processor" |
| dictionary-shaped **required** members | `get_dict_groups`, `get_dictionary_catalog`, `get_tutorial_displays` have no core runtime need on the record path; `get_dict_entries` feeds identity digest, validation and describe | `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog`, `get_tutorial_displays` become **optional-neutral**, with empty fallbacks in adapters, merges and the identity digest (a stable digest for "none"); the openfoam and opencarp stubs are deleted. `get_tutorial_catalog` stays required until the last factory tutorial retires |
| core's own files declared by OpenFOAM (K3) | `openfoam_case_runtime_conventions()` declares `workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `workflow_logs`. **Bug:** openCARP declares no conventions, so record staging copies an earlier run's state files and `out/` into the new stage | the core half now: `CORE_RUNTIME_RECORDS` plus `with_core_runtime_records()`, merged in `_CaseRuntimeConventionsAdapter.conventions`; record staging also excludes every record step's `produces`. The OpenFOAM half (removing the names there) stays in the openCARP plan's Task 15 |
| cardiac names in core | `dict_entries.get_heterogeneity_models`, `get_electro_property_entry_groups`; `cardiacfoam_monorepo_root`; CLI help naming cardiac tutorials; "without running OpenFOAM" | move the two functions to cardiacfoam; point `scripts/check-wheel-artifact.py` at a neutral function; delete or move `cardiacfoam_monorepo_root`; scrub CLI help |
| name heuristic `strict_planning._is_nondimensional_entry` ("manufactured"/"verification") | exempts records by *name*; cardiacfoam already has a real hook (`planning_policy.is_nondimensional_case`) | delete the heuristic; rely on the plugin hook only. First prove every currently exempted case is still exempted by the hook. Rename `SKIP_MESH_DIAGNOSTICS` to a neutral name (dated note) |

## 3. Decisions (owner, 2026-09-26)

| item | decision |
|---|---|
| now | A1 environment source, A2 instance/replica directories, A3 optional dictionary members, A5 the core half of K3 plus record-staging exclusions, A6 cardiac names out of core, A7 the name heuristic |
| later | A4, deleting the never-executed `scripts/run_case.sh`, `RUN_CASE_SCRIPT_RELPATH`, `resolve_run_script_path` and the dead `generic_case` params: after the tutorial stream's step C, because the deletion edits cardiacFOAM defaults that stream is changing. Task 15's OpenFOAM half: after step 5 |
| rule | every change is a rename or relocation with no compatibility shim. Old names are deleted in the same commit across every package, and tests change with them |
| rule | each change lands on `main` as its own small commit with a generality-log row, and the tutorial stream rebases (the shared-core rules in the openCARP plan still hold) |

## 4. Proof

Each change keeps every existing guard green and adds these:
- **The shape gate's baseline shrinks, and is edited down in the same commit.**
  A1 removes all 69 `bashrc` hits; A2 removes the `processor` hits. The
  `case.foam` hits go with A4, later. Target after this spec: only the A4 debt
  remains.
- **C1–C10 still pass for both the toy and openCARP, and cardiacFOAM native is
  still 0 failed.**
- **A5 gets a new conformance check, or a C7 extension:** staging a record a
  second time carries no state from the first run. openCARP fails it today,
  which is the bug.
- **A3 gets a test:** a plugin that implements none of the four
  now-optional members loads, composes, describes and runs.
- **A2 gets tests for instance and replica directories using only the
  plugin-declared vocabulary:** an OpenFOAM stack's time and `processor*`
  behaviour is unchanged (existing tests), and a stack that declares none of
  them behaves as openCARP does.

**Corrected 2026-09-26 (implementation, topic A):**
- "only the A4 debt remains" was not reachable as written: `run_document_exec.py`'s
  `FOAM_` hit was the legacy `DRIVERFOAM_ALLOWED_RUNS_ROOT` variable (the
  project's former name), no OpenFOAM coupling, and outside A1/A2/A4. It has
  since been removed outright (Task 9 close-out, owner decision, 2026-09-26),
  so only the A4 debt now remains, as originally targeted.
- The A5 check is C11, not a C7 extension (plan Task 3). It is strict: a
  restaged case holds only native paths -- concretely, **C11 checks path-set
  equality** (`restaged == native`, both directions, corrected further by R1
  fix finding M1: the check used to accept `restaged <= native`, a subset,
  which could not see a staging rule that wrongly *drops* an authored native
  file). Meeting it needed `CORE_RUNTIME_RECORDS` to list every file core
  writes (seven files and four directories -- corrected 2026-09-26, final
  review M13: this said "two directories, not four"; the directories are
  `workflow_logs`, the case-transaction journal directory,
  `remediation_transactions` and `remediation_candidates`) and openCARP's
  record to declare its full outputs (F15).
- A3's stable digest: every provider digest and the cardiac stacks'
  identities are unchanged; `opencarp` and standalone `openfoam-environment`
  record `dictionaries` as `<unclaimed>` once, because their stub had been
  its false winner.
- A7: the hook did not cover `manufacturedMonodomainTotalLagrangianEM`; it
  now reads the electro region that case declares **through
  `physics_layout.json`** (one row per physics type; a case without
  `physicsProperties` is single-region, per cardiacFoam's
  `physicsModel::New` `MUST_READ`).
- A2 landed as three commits (A2a instances, A2b replicas, A2c input roots);
  the run-document schema key `time_indexed` became `instance_indexed`.
- The R1 and R2 checkpoint-review fixes, one line each:
  - R1-I1 (corrected 2026-09-26, final review M13: this bullet described
    A7's own original motivation, the EM tutorial gap, which is a
    different finding, not recorded here before now): `planning_policy
    .is_nondimensional_case`'s `except Exception` swallowed
    `PhysicsLayoutError`, so a case with no `constant/physicsProperties`
    (e.g. `ionicHeterogeneity`) silently lost the exemption the pre-A7
    direct read gave it, becoming a bare `FileNotFoundError` the hook
    caught and answered `False` (not exempt) for. `PhysicsLayoutError` now
    subclasses `TutorialRecordError` so it reaches `plan --strict`'s
    existing refusal handling instead of a traceback, and a case with no
    `physicsProperties` is now an explicit single-region `_IMPLICIT_LAYOUT`
    (role `electro` only), documented against cardiacFoam's
    `physicsModel::New` and `ionicHeterogeneity`'s own probe application.
    (`manufacturedMonodomainTotalLagrangianEM`'s region-split gap is A7's
    own fix, above, not R1-I1.)
  - R1-I2: `record_generated_relpaths` keeps an intermediate a later step
    `consumes` excluded from a record's generated set (first-touch-in-step
    -order rule), rather than re-including it as an authored input.
  - R1-I3: `CORE_RUNTIME_RECORDS` gains the remediation-transaction marker
    and its two directories -- three files core writes that its own "every
    file" claim had missed.
  - R2-I1: `load_run_document` re-raises a schema `jsonschema.ValidationError`
    as `ValueError`, so a pre-A2 completed sweep case is reported
    not-reusable by name instead of crashing the sweep.
  - R2-I2: `CaseProvenanceCapability.input_roots` takes the stack's merged
    `CaseRuntimeConventions` as a required `conventions` keyword, so a
    stacked provider's replica globs are what provenance walks, not always
    OpenFOAM's own default.
  - R2-I3: `CaseRuntimeConventions.__post_init__` refuses a malformed
    `replica_directory_globs`/`preserved_instance_names`/
    `instance_directory_pattern` by name at construction, closing the
    bare-`str` migration mistake the old `decomposition_directory_prefix`
    field invited.

## 5. Order and parallelism

- **Parallel tracks, disjoint files:**
  - **A6 + A7:** strict_planning heuristic, `dict_entries`, CLI help.
  - **A5:** conventions adapter, record staging.
  - **A3:** plugin interface tiers, adapters, merges, identity digest.
- **Then A1**, a mechanical rename that touches every package, so it runs
  alone.
- **Then A2**, the deepest change: reconciler, provenance, sweep and workflow
  runner. It runs alone and is reviewed by Opus.
- Opus reviews after the parallel tracks, after A2, and a final whole-topic
  review.

## 6. Out of scope

- The step-is-a-subprocess and run-is-a-directory paradigm (in-process
  solvers): a later topic.
- `VALUE_KINDS`' `dimensioned_*` kinds stay. They are a generic value shape
  that cardiacfoam and openfoam use.
- Function-object diagnostics and `samplable_fields` stay named as they are.
  They are declared by plugins and neutral in effect; renaming them is later
  debt.
