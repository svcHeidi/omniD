# Core generality: replace core's OpenFOAM-shaped concepts with general ones

**Date:** 2026-09-26 · **Status:** the scope split was approved by the owner in
conversation (2026-09-26). The written form is written from those decisions.
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
