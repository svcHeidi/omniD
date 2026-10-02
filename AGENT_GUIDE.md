# Historical cardiacFoam operational notes

> **Not a current agent contract.** This file contains useful historical
> cardiacFoam operational detail, including retired pre-omnidriver names and
> host assumptions. Do not use it as a routing or implementation authority.
> Start at [`AGENTS.md`](AGENTS.md), then verify any command here against the
> current CLI, package, and selected adapter before use.

## What the agent can do

| Action | Function | Module |
|---|---|---|
| Discover tutorials, dict keys, ionic models, utilities | `describe_tutorial(...)` | `omnidriver.core.introspection` |
| Build a non-mutating strict launch contract | `strict_plan(...)` | `omnidriver.core.strict_planning` |
| Execute an agent-authored RunDocument | `omnidriver run/step --run-document <file>`; `build_execution_inputs(...)` | `omnidriver.core.runtime.run_document_exec` |
| Execute one strict workflow step | `run_workflow_step(...)` | `omnidriver.core.runtime.workflow_runner` |
| Read/write strict workflow state | `workflow_state_from_json(...)`, `WorkflowRunState.to_json()` | `omnidriver.core.runtime.workflow_state` |
| Validate RunDocument v3 (any other version is refused) | `RunDocument.from_json(...)` | `omnidriver.core.runtime.run_model` |
| Validate a configuration before launching | `validate_run(run, *, entries=None)` | `omnidriver.core.specs.validation` |
| Synthesize a fresh `electroProperties` / `physicsProperties` | `build_electro_properties(...)`, `build_physics_properties(...)` | `omnidriver.cardiacfoam.dict_builder` |
| Parse an existing `electroProperties` back to selectors + overrides | `parse_electro_properties(path)` | `omnidriver.cardiacfoam.dict_builder` |
| Write a from-scratch case's dicts as one committed plan (the sweep's case writer; nothing is launched) | `build_and_launch(...)` | `omnidriver.cardiacfoam.dict_builder` |
| Locate predicted outputs | `strict_plan(...)`'s `expected_artifacts` field (also in `omnidriver plan --strict` JSON) | `omnidriver.core.strict_planning` |
| Verify outputs vs predictions | `artifact_reconciliation` in `run --strict`/`step --strict` JSON output | `omnidriver.core.runtime.reconciler` |
| List past runs | `list_runs(root)` | `omnidriver.core.runtime.run_discovery` |
| Plan/run a parameter sweep | `omnidriver sweep-plan/sweep-run --spec sweep.json --output-dir <dir>` | `omnidriver.core.runtime.sweep_runner` |

## Preferred strict agent loop

A single per-operation driver context supplies focused solver capabilities
internally; omitted contexts, RunDocument v3, optional-hook fallbacks,
commands, diagnostics, and artifacts behave as documented below.

Use strict planning before launching. It is the only path that tells an agent
whether the run is machine-readable, validated, catalog-covered, artifact
predictable, and workflow-addressable before execution starts.

For the cardiacFoam plugin, configure
`omnidriver-runtime.example.yaml` once per
host and expose it through `OMNIDRIVER_RUNTIME_CONFIG`. The plugin declares
the `lightweight` and `full` physics backends in its `plugin.yaml`; the local
file selects one backend, its OpenFOAM bashrc, the full-mode solids4foam root,
and the generated `cardiacFoam.build.json` manifest. The manifest is not a
build step you run yourself: `runtime_profile.py` generates or refreshes it
automatically, on the fly, whenever it is missing or older than the compiled
`cardiacFoam` solver — by inspecting the solver's actual linked libraries
(`otool -L`/`ldd`) to infer which backend was compiled, never by trusting an
asserted flag. omnidriver rejects an unset, invalid, unbuilt, or
compiled-metadata-mismatched selection instead of letting a shell resolver
silently select another checkout. This runtime file is separate from
case/sweep overrides and applies to all cardiacFoam entries.

```bash
omnidriver plan --strict --entry singleCell
omnidriver run --strict --entry singleCell
```

The `plan --strict` command is non-mutating. It prints JSON with:

- `status`: `ok` or `failed`
- `entry`: the raw entry identifier as requested (pre-resolution)
- `resolved_entry`: case/spec identity and paths
- `readiness_score`: weighted 0-100 score summarising whether the driver has
  enough concrete case-generation and run-preparation evidence to execute
- `simulation_audit`: scored stages showing exactly how simulations are created
  and prepared: `build_cases()`, required OpenFOAM files, dictionary
  resolution, workflow DAG normalization, artifact prediction, environment
  preflight, and mesh geometry
- `validation_diagnostics`: RunDocument and configuration validation results
- `workflow_diagnostics`: normalized workflow-DAG validation results (command
  allowlist, DAG structure)
- `catalog_coverage_errors`: strict dict-key coverage failures
- `artifact_diagnostics`: solver/utility/artifact prediction coverage failures
- `environment_diagnostics`: missing executables, unsourced OpenFOAM env, missing MPI launcher
- `mesh_geometry_diagnostics`: mesh-scale / geometry sanity checks
- `workflow_dag`: normalized executable steps
- `workflow_state`: initial pending step state
- `expected_artifacts`: predicted machine-readable artifacts
- `launch`: exact launch command and output paths

The `run --strict` command executes normalized steps until completion or
failure. It writes:

- `workflow_state.json` under the strict-plan output directory
- `workflow_logs/<step>.attempt<N>.stdout.log`
- `workflow_logs/<step>.attempt<N>.stderr.log`

If `workflow_state.json` already exists, `run --strict` resumes from that
state. If the saved state is `failed`, it exits non-zero and does not retry the
failed step automatically. Use `step --strict` for an explicit manual rerun:

```bash
omnidriver step --strict --entry singleCell --step solve
```

**Resuming can silently replay stale results.** If `workflow_state.json`
already says `completed` — e.g. a leftover case directory from a previous
session, code change, or experiment — `run --strict`/`step --strict` report
success and exit 0 without invoking the solver at all; there is no warning.
This was hit in practice: a sweep re-run after a solver code change reported
the previous day's numbers as fresh, caught only because the "new" errors
matched the old ones to six significant figures — two different code
versions cannot agree that precisely, so identical numbers meant identical
(non-)execution, not agreement. Any re-run intended as a genuine before/after
comparison after a code or config change MUST pass `--fresh`, which deletes
the resolved output directory before running so the workflow executes
exactly as it would on a first run:

```bash
omnidriver run --strict --entry singleCell --fresh
```

`--fresh` refuses to delete anything that doesn't look like omnidriver's own
output (no `workflow_state.json`/`sweep_manifest.json`/`run_document.json`
found), the filesystem root, your home directory, or a path outside
`OMNIDRIVER_ALLOWED_RUNS_ROOT` when that's set — but it does not prompt for
confirmation, so treat any `--output-dir`/case directory you point it at as
fully disposable and copy out anything you want to keep first.

`--max-total-attempts <N>` caps the total number of step executions across the
whole run (a retry-storm guard on top of each step's per-step `max_attempts`).
It defaults to unbounded, preserving prior behavior.

For `sweep-run`, `--case-timeout-s <seconds>` sets a wall-clock timeout per case
subprocess; a case that exceeds it is recorded as failed (with a `timeout_error`
in its summary) and the sweep continues to the next case rather than hanging.
Defaults to no timeout.

Programmatic planning uses the same contract:

```python
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan

# `driver_context` is keyword-only and has NO default: which adapter's
# semantics a plan is built under is supplied, never guessed. Resolve it once,
# the way the CLI does for `--plugin`, and thread it down.
report = strict_plan("singleCell", driver_context=load_plugin_context("cardiacfoam"))
payload = report.to_json()
if payload["status"] != "ok":
    raise RuntimeError(payload)
print(payload["workflow_state"]["current_step_id"])
```

### Executing an agent-authored RunDocument

`plan --strict` emits a complete `run_document` (RunDocument v3) in its JSON
output. An agent can persist that document, edit it (e.g. tune `config`, add or
reorder `workflowDag` steps, set per-step `retry_policy`), and execute the
edited document directly — the driver runs *your* document instead of
regenerating one from `--entry`:

```bash
# 1. Plan and capture the run document the planner produced.
omnidriver plan --strict --entry singleCell > plan.json
python3 -c "import json; json.dump(json.load(open('plan.json'))['run_document'], open('run.json','w'))"

# 2. (optional) edit run.json — config, workflowDag, retry_policy, expectedArtifacts.

# 3. Execute the document. No --entry; --strict is implied by the document.
omnidriver run  --run-document run.json
omnidriver step --run-document run.json --step solve   # single step
```

`--run-document` is mutually exclusive with `--entry` (and with
`--config`/`--entry-kind`/`--cases-root`). Before executing, the driver:

1. Loads and schema-validates the document (a `version: "1"` document is
   migrated to v2 automatically).
2. Runs `validate_run` on its `config`.
3. Re-normalizes the supplied `workflowDag` and enforces the **command
   allowlist**: each step's command must be a known OpenFOAM/driver core
   command, a recognized case script (`Allrun`-family), an entry in the
   active plugin's utility manifests (`get_utility_manifests()`, declaring
   `produces`), or an executable installed under
   `$FOAM_APPBIN`/`$FOAM_USER_APPBIN` (any core OpenFOAM app or your own
   compiled utility). Arbitrary non-OpenFOAM commands are rejected before
   anything runs. Note: when OpenFOAM is not sourced, only the core set +
   case scripts + declared utility manifests are accepted.
4. Requires `launch.caseRoot` and `launch.outputDir`.

If any of these produce an error-level diagnostic, the command prints
`{"status": "failed", "diagnostics": [...]}` and exits non-zero **without
executing anything**. Otherwise execution, `workflow_state.json` resume,
retry/backoff, and `failure_context` behave exactly as for the `--entry` path.

**Command-boundary guarantees.** Steps run argv-style (no shell). A step's
working directory cannot escape `caseRoot`. Bare command names resolve via
`PATH` only — a case directory **cannot shadow** a trusted binary such as
`cardiacFoam`. Only recognized case scripts (`Allrun`-family), named bare
(`Allrun`) or as `./Allrun`, resolve to case-local files; arbitrary
`./script` and absolute-path commands are rejected by the allowlist. Note
this does **not** sandbox the code *inside* an invoked `Allrun` — running a
case means running its scripts, which is arbitrary case-authored code by
design. The trust model is local/single-tenant: it assumes `PATH` and the
`$FOAM_*BIN` variables are not attacker-controlled.

See [`SECURITY.md`](SECURITY.md) for the full trust model, output-location
contract, and the explicit list of what is and is not mitigated. For the
plugin-boundary compatibility fallbacks (optional-hook defaults), see
`omnidriver/core/compatibility.py`.

## Sweeping a parameter grid

For running many cases off one parameter grid, use `sweep-plan`/`sweep-run`
instead of hand-looping `build_and_launch`. A `sweep.json` has two top-level
objects:

- `"base"`: fixed values applied to every case — `electro_selectors`,
  `physics_selectors`, `electro_overrides`, `physics_overrides`, `delta_t`,
  `end_time` (same shapes as `build_and_launch`'s kwargs).
- `"sweep"`: `"mode"` (`"cross_product"` or `"zip"`), `"independent"` (axis
  name to list of values, routed into `build_and_launch`'s parameters per
  below), and `"dependent"` (a list of `{"name", "derive", "of"}` entries for
  derived *labels only* — not routed through the selector rules below —
  currently the only registered `derive` function is `case_id_template`,
  which joins the named `of` values into a `caseId` label).

```json
{
  "base": {
    "electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
    "physics_selectors": {"type": "electroModel"}
  },
  "sweep": {
    "mode": "cross_product",
    "independent": {"ionicModel": ["TNNP", "BuenoOrovio"], "deltaT": [1e-6, 2e-6]},
    "dependent": [{"name": "caseId", "derive": "case_id_template", "of": ["ionicModel", "deltaT"]}]
  }
}
```

Each resolved case's axis values route automatically into `build_and_launch`'s
parameters: `myocardiumSolver`/`ionicModel`/`tissue` go to `electro_selectors`,
`type` goes to `physics_selectors`, `deltaT`/`endTime` go to the dedicated
`delta_t`/`end_time` kwargs, `dx` goes to the dedicated `dx` kwarg (mesh
resolution in mm, see below), any other `system/controlDict` key is rejected
outright, and any key that isn't a recognized electroProperties/
physicsProperties driver_path is rejected outright too (it would otherwise
have no effect on the generated case). Everything recognized falls through
to `electro_overrides`.

Every case is *materialized* fresh: `build_and_launch(..., dry_run=True)`
writes its dict files, and the sweep runner additionally writes a generated
`Allrun` script and a `workflow_contract.json`, into `<output_dir>/<case_id>/`.
This is not a registered-tutorial lookup; each case is its own on-disk
`case_folder` entry.

### Mesh provisioning for from-scratch cases

A freshly materialized `case_folder` has no author-supplied mesh, so
`build_and_launch` provisions one based on `myocardiumSolver`. Every solver
meshes the same way: a `system/blockMeshDict` is
written and the generated `Allrun` runs `blockMesh` before `cardiacFoam`.

- `singleCellSolver` (no real geometry): the `blockMeshDict` is fixed at one
  hex cell, matching the native `singleCell` tutorial's own one-cell block —
  there is no resolution to choose.
- `monodomainSolver`/`bidomainSolver`/`eikonalSolver` (need real geometry): a
  generic default `system/blockMeshDict` is written (a small cubic slab,
  "walls" patch — **not** tuned to any specific tutorial's science). Sweep
  this mesh's resolution with the `dx` axis (**metres**, isotropic cell size — this is a
  from-scratch `case_folder` mechanism, unrelated to the tutorial-record
  `dx` axis `records/niederer_2011.py` declares for the Niederer benchmark,
  which happens to share the same name but resolves against that case's own
  `system/blockMeshDict` instead). `dx` derives the cell count for the fixed
  default slab size via `specs/mesh_provisioning.py::cell_counts_from_dx`,
  which raises `ValueError` if `dx` does not evenly divide the slab size —
  deliberately no silent rounding, the same rigor
  `records/niederer_2011.py`'s own `dx` axis applies to its (different,
  non-cubic) slab; both share the `cell_counts_from_dx` calculation,
  differing only in how the result gets written (`mesh_provisioning.py`
  generates a fresh file from its own template; the Niederer record's axis
  patches an existing author-provided file through the normal case-write
  channel).
  `dx` is meaningless for `singleCellSolver` (no geometry to resolve) and
  raises `ValueError` rather than silently having no effect. `dx` also has
  nothing to do with real anatomical meshes imported via
  `vtkUnstructuredToFoam` (most real tutorials) — those are unstructured
  meshes with no cell-size concept, and this mechanism never touches them.
- A mesh already present under `constant/polyMesh/` or `system/blockMeshDict`
  is never clobbered by a repeat `build_and_launch` call, regardless of that
  call's own `overwrite` flag — this protects a hand-authored custom mesh
  from being silently replaced by the generic default.
If the sweep declares a `caseId` dependent entry, it becomes the case's
directory name (validated for uniqueness and path-safety); otherwise cases
are named `case_0001`, `case_0002`, ... in expansion order.

Both actions enforce a safety cap of 200 expanded cases by default (override
with `--max-cases`), checked before any case is expanded or materialized:

```bash
omnidriver sweep-plan --spec sweep.json --output-dir .tmp/omnidriver/sweeps/my_sweep/
omnidriver sweep-run --spec sweep.json --output-dir .tmp/omnidriver/sweeps/my_sweep/
```

`sweep-plan` materializes and strict-plans every case without launching
anything. `sweep-run` additionally launches each case and is resumable:
re-invoking it against the same `--output-dir` skips cases already recorded
as `completed` in `sweep_manifest.json`, leaves `failed` cases alone unless
`--retry-failed` is passed, and refuses to proceed at all if `sweep.json` has
changed since that output directory's manifest was created (a spec-hash
mismatch) — use a fresh `--output-dir` or resolve the mismatch first.

`--fresh` applies here too, and matters more: a solver/code change
invalidates every case in the sweep equally, so `sweep-run --fresh` deletes
the *entire* `--output-dir` (not just individual cases) before re-running
everything from scratch — this also sidesteps the spec-hash-mismatch refusal
above, since there's no old manifest left to compare against. Mutually
exclusive with `--retry-failed` (resume-only-failures vs. wipe-everything are
contradictory intents).

See `omnidriver/core/runtime/sweep_runner.py` for the full implementation.

### Sweeping an existing registered tutorial (`base.entry`)

The generic mode above always materializes a fresh, from-scratch `case_folder`
via `build_and_launch`. Some tutorials (`manufacturedMonodomainPseudoECG` and
others under `omnidriver/specs/tutorials/`) instead expose their own
`make_spec(**kwargs)` with tutorial-specific parameters (e.g.
`manufacturedMonodomainPseudoECG`'s `dimensions`/`number_cells`/`dt_values`).
To sweep one of these instead of a from-scratch case, set `base.entry` to the
tutorial's registered name.

`niederer2011` is a **tutorial record** (`records/niederer_2011.py`) — a
thin, declarative pointer at the native case
(`NiedererEtAl2011verification`), not a factory tutorial. Its study names real
`document:dotted.path` keys and its own `dx`/`tetDx` axes directly, in the
case's own units (metres, seconds):

```json
{
  "base": {
    "entry": "niederer2011",
    "cases_root": "tutorials",
    "mesh": "hex"
  },
  "sweep": {
    "mode": "zip",
    "independent": {
      "dx": [0.0005, 0.0005, 0.0005, 0.0002, 0.0002, 0.0002, 0.0001, 0.0001, 0.0001],
      "system/controlDict:deltaT": [5e-05, 1e-05, 5e-06, 5e-05, 1e-05, 5e-06, 5e-05, 1e-05, 5e-06],
      "system/controlDict:endTime": [0.2, 0.2, 0.2, 0.08, 0.08, 0.08, 0.055, 0.055, 0.055]
    }
  }
}
```

This is the native study
`NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json`:
Niederer et al. (2011)'s grid, Δx 0.5/0.2/0.1 mm × Δt 0.05/0.01/0.005 ms,
with `endTime` per Δx chosen so every probe has activated. Run it from
the native repository root:
`omnidriver --plugin cardiacfoam sweep-plan --spec tutorials/NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json --output-dir <dir>`.

**A record sweep names its own cases root.** `base.cases_root` says where
the record's native case lives: here `tutorials`, relative to the directory
the sweep runs from. A record has no ambient cases root, and `sweep-plan`/
`sweep-run` refuse `--cases-root`, so a record sweep without
`base.cases_root` is refused before any case exists, as the CLI's JSON
failure. Each `independent`/`dependent` name, and each `base` key other than
`entry`/`cases_root`, is a `document:dotted.path` key, one of the record's
own axes, its route selector (`mesh`), or a sweep naming key (`caseId`,
`output_dir_name`). Anything else is refused up front,
for the whole sweep. Each case is staged from the native case into
`<output_dir>/cases/<case_id>/` and committed there; the native tree is never
written. `describe --entry niederer2011 --cases-root tutorials` lists the
record's axes and keys.

The paragraph below describes only the remaining **factory** tutorials.

For a factory tutorial (not a record), every axis value is forwarded
verbatim as a keyword argument to that
tutorial's own `make_spec(**overrides)` — there is no fixed vocabulary the way
generic mode has (`electro_selectors`/`dx`/etc.); `make_spec` validates its
own keyword arguments and an unrecognized one is a normal `TypeError`,
reported as that case's `materialization_error`, same as any other per-case
failure. Values fixed across every case in the sweep (like a factory's
`solvers`/`end_time_by_dx`) go in `base`; per-case values come from
`independent`/`dependent` and win on conflict.

**One case per resolved combination, and why.** Several of these tutorials'
own `apply_case()` methods patch `system/controlDict`/`system/blockMeshDict*`
directly instead of writing an isolated per-case directory. omnidriver stages
a fresh copy under the disposable workspace before applying those mutations,
but each resolved axis combination must still collapse to exactly one case —
if it doesn't (e.g. a config that still fans out internally because a
constraining kwarg like `solvers` is missing),
`sweep-plan`/`sweep-run` reports that case as `failed` with a clear
`materialization_error` rather than silently applying only the first of
several. In practice this means giving `dt`/`dx`-style axes their own
dedicated sweep row (`"zip"` mode with per-case single-element lists)
instead of relying on the tutorial's own internal multi-value fan-out.
Entry-mode sweeps remain serial because each case owns its staged case tree
and post-processing boundary.

**Entry-mode execution is staged and disposable.** `sweep-plan` and
`sweep-run` copy the registered tutorial into
`<output_dir>/cases/<case_id>/` before calling `apply_case()`; the source under
`tutorials/` is never the mutable execution root. All generated
meshes, processor/time directories, logs, workflow state, manifests,
post-processing output, and archives must stay below the disposable
workspace. Keep a failed workspace when diagnosing a run;
cleanup is an explicit, disposable-output action.

A sweep with no `--output-dir` needs `--scratch-dir <dir>` (or
`OMNIDRIVER_SCRATCH_DIR`); without one it is refused by name
(`ScratchRootNotSupplied`) rather than silently writing into the checkout
(see `CLAUDE.md`'s scratch-root rule).

Everything else — the manifest, `--retry-failed`, `--case-timeout-s`,
`--max-cases`, resumability — is identical to generic mode.

## Running a record in parallel

A tutorial record declares its solve step
once, and serial is the default, as the native `Allrun` is. To run the solve
in parallel, ask for it; the solver's own layer knows how, and the code checks
the facts.

**The request.** One reserved study name, `parallel`, in any study source
(`--config`'s entry, a sweep's `base`, or a sweep axis), or `--parallel` on the
CLI (`describe`, `plan`/`step`/`run --strict --entry <record>`, `sweep-plan`,
`sweep-run`). The flag is the same request from its own source: a job script
adds it without editing the study, and a flag that disagrees with the study's
value is refused by name, never merged. Absent or `false` is serial. A sweep
axis `"parallel": [false, true]` runs one case of each.

- `parallel: true` / `--parallel`: the solver layer finds N itself.
- `parallel: N` / `--parallel N`: states N. A layer whose case states a count
  refuses an N that differs from it; a layer whose case states none uses it.

What each layer does with it:

| stack | parallel form | where N comes from |
|---|---|---|
| OpenFOAM (cardiacFOAM) | `<solve>.decompose` (`decomposePar -force`) → `<solve>` as `mpirun -np N cardiacFoam -parallel` → `<solve>.reconstruct` (`reconstructPar`); the steps after the solve (`postProcess -latestTime`) run on the reconstructed case | the staged case's `system/decomposeParDict:numberOfSubdomains`, read as the run will see it. Set N with that study key; `parallel: N` must equal it, or the plan is refused naming both. The decompose step consumes the dictionary, so provenance fingerprints it |
| openCARP | `<solve>` as `mpirun -np N openCARP ...`; outputs keep their names, node order and location (`docs/solver-learning/opencarp.md` I7) | the scheduler's allocation for `parallel: true`, or the `N` you supply. `true` outside a scheduler is refused. The `mpirun` first on PATH must be the launcher of the MPI openCARP was built against; preflight refuses another MPI's (`opencarp_mpi_launcher_mismatch`, I2, I5) |

`describe --entry <record> --parallel` previews the form before anything runs:
`record_preview.workflow_commands` shows each step's command line, with N as the
study's uncommitted values would make it, and `record_preview.parallel` the
request. A run's document carries `resolvedEntry.parallel` (`{"requested": ...,
"allocation": ...}`), and its DAG differs, so a serial and a parallel run of one
case are told apart in provenance. A serial run's document has no
`resolvedEntry.parallel`.

**On a scheduler.** omniD reads the allocation from one declared place,
`SLURM_NTASKS`, only when a run asks for parallel (a scheduler's allocation is
an ambient fact: CLAUDE.md, "supplied versus discovered"). It never overrides
the case, and the case never overrides it: when they disagree the plan is
refused by name, and you change one of them.

- OpenFOAM: make `numberOfSubdomains` equal the allocation. Put it in the study
  (`"system/decomposeParDict:numberOfSubdomains": 64`), or request
  `--ntasks` equal to what the case says.
- openCARP: `--parallel` with no count uses the allocation.

A Slurm job script for the Niederer campaign:

```bash
#!/bin/bash
#SBATCH --ntasks=64
#SBATCH --time=12:00:00
source /path/to/OpenFOAM/etc/bashrc            # the solver's environment, as for a serial run
export OMNIDRIVER_SCRATCH_DIR=$SCRATCH/omnid    # staging is supplied, never invented
# The study sets system/decomposeParDict:numberOfSubdomains to 64 (or the
# agent writes it into base); the job adds only the request:
python -m omnidriver sweep-run --plugin cardiacfoam --spec niederer_dx0.1.json \
    --output-dir $SCRATCH/niederer_dx0.1 --parallel
```

`mpirun` inherits the allocation from Slurm. For openCARP the same script
drops `source` and puts openCARP's own MPI launcher first on `PATH`. A case
whose count disagrees with `$SLURM_NTASKS` fails at plan time, before any
solver starts, naming both numbers.

**Refused by name:** a stack with no parallel form (`get_parallel_steps`); a
record whose selected steps run no declared solve command
(`get_solve_step_commands`); `parallel: null`; OpenFOAM given a count that differs from
`numberOfSubdomains`, or a case with no `numberOfSubdomains`; openCARP given `true` with no allocation, or
a count that disagrees with one; a malformed `SLURM_NTASKS`; `--parallel` for
an entry that is not a tutorial record, or with `--run-document`.

## Polling a long-running run

For a run that takes minutes, prefer the async-friendly polling pattern,
against the real run-state file:

```python
import json
import time
from pathlib import Path

state_path = Path("<output_dir>/workflow_state.json")
while True:
    state = json.loads(state_path.read_text())
    if state["status"] in {"completed", "failed", "skipped"}:
        break
    time.sleep(15)
```

`workflow_state.json` is written by the strict workflow orchestrator and
updated after every step, so the read above is safe at any instant.

## Post-processing phase (brain + module)

The execution engine hands off to the postprocessing phase once a workflow or sweep reaches a terminal state. This is split into two independent pieces:

1. **The brain (`build_sweep_context`)**: Reads the sweep's own record (`sweep_manifest.json`), verifies it against what is actually on disk (resolving entry-mode vs generic-mode output directory differences), and returns a single grounded `SweepContext`.
2. **The postprocessing module (`run_postprocessing_module`)**: A separate function that receives the `SweepContext` and a task. It always refuses (`not_configured`) rather than guessing an undeclared generic analysis task -- there is no automatic per-case script discovery any more.

If an agent needs deeper reasoning than the flat summary, it must use the brain's query functions:

- `read_case_workflow_state(context, case_id)`
- `read_case_output_file(context, case_id, relative_path)`

These query functions raise clearly on an unknown case ID and safely restrict reads to files the brain has already verified.

### Post-processing utilities

`omnidriver.postprocessing` is the plotting and table utilities the native
cardiacFOAM post-processing scripts import directly (`PlotSpec`, `TraceSpec`,
`build_line_traces`, `load_csv_folder`, `apply_plotly_layout`,
`write_plotly_html`, `TableWriter`, `DEFAULT_PALETTE`) -- core's own
plan/run/sweep-run path never imports it, and nothing discovers or invokes a
script automatically; a caller runs its own post-processing script by hand
and may use these utilities from it.

## Verifying outputs

Strict planning predicts artifacts before launch and assigns artifact ids to
workflow steps when catalog coverage is available. The strict step/run path
now reconciles claimed artifact ids against on-disk files after each step. If an
expected artifact is missing, the step automatically fails with a `missing_artifacts` code.

### Reading a failed strict step

When `run --strict` fails or a `step --strict` ends `failed`, the printed JSON
carries a top-level `failure_context` object for the failed step:

- `step_id`, `attempt`, `exit_code` — identity of the failed attempt. Note
  `exit_code` may be `0` even on failure (e.g. `missing_artifacts`): the
  contract is **status-driven**, never exit-code-driven.
- `diagnostics` — the diagnostic codes the runner emitted.
- `stdout_log` / `stderr_log` — paths, for a full read.
- `stdout_tail` / `stderr_tail` — the last `--tail-lines` lines (default 200) of
  each log, bounded to 64 KiB.
- `stdout_truncated` / `stderr_truncated` — whether content was dropped.

The driver surfaces raw tails and status only. It does **not** judge convergence
or pick a fix — interpretation and remediation are the agent's job. The loop is:
read `failure_context` → edit the case dict (e.g. via `build_electro_properties`
or `mutators.py`) → `step --strict --step <id>` reruns the failed step (the
`attempt` counter increments).

To shorten that loop, `failure_context` also carries a
`candidate_remediations` array — **suggestions only**, the agent applies them.
Each entry has `diagnostic_code`, `driver_path`, `change` (a human-readable
transform, descriptive), `rationale`, `source` (`"static"`), and `confidence`. A
hint with an empty `driver_path` is advisory. The ladder emits static,
diagnostic-code-keyed hints; when one matches, it points the agent straight at
the failure. When none matches, the array is empty and the agent reasons from
`failure_context` and the catalog. For numerical control such as `deltaT`, the
per-ODE stability limit is the anchor: around `1e-6` s for biophysical
(Hodgkin-Huxley-style) ionic models and around `2e-5` s for phenomenological
models.

To apply a chosen fix mechanically, write an overrides file
(`[{"driver_path": "...", "value": "..."}]`) and run:

```
omnidriver step --strict --step <id> --apply overrides.json
```

This validates each override for *applyability*, applies it via the dict mutators
(resolving `$ELECTRO_MODEL_COEFFS.*` to the case's solver-specific coeffs block),
reruns the step (`attempt++`), and appends one record to `remediation_history.jsonl`
under the output directory. The driver accepts three forms of overrides:

1. `$ELECTRO_MODEL_COEFFS.*`: Catalog-addressable entries. For a `dynamic_path`,
   replace each template placeholder with the concrete instance name in the
   `driver_path` (for example,
   `$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.global.scale.myChannel`). The
   concrete key must already exist in the generated dictionary.
2. `system/path/to/dict:entry_path`: Explicit overrides for any OpenFOAM dictionary (e.g., `system/fvSolution:solvers/V/tolerance`). The file path must be strictly inside `system/`. If the case uses multiple regions (e.g., electromechanics), check `constant/physicsProperties` to determine if you need to target `system/electro/fvSolution` or the top-level `system/fvSolution`.
   - **Note on entry paths**: `/` traverses nested blocks. OpenFOAM lets a sub-dictionary be keyed by a quoted regex instead of a literal name (e.g. a solver block declared as `"Vm|VmFinal|u|uFinal"`); mutators.py resolves an ordinary member name (`solvers/Vm/tolerance`) against such a pattern automatically, so you do **not** need to know the pattern or spell it out in quotes — just use the field name you actually mean (e.g. `system/electro/fvSolution:solvers/Vm/tolerance`). An exact literal key always wins over a pattern match if both exist.
3. Flat string paths (e.g., `deltaT`): Routed to `system/controlDict` for backward compatibility.

Invalid overrides are rejected **before** any mutation or rerun.

**Derived constants are not overridable.** Some models expose constants that are
*computed* from other (user-facing) constants at `initConsts` — e.g. the
Land-Niederer active-tension transition rates (`AC_k_uw`, `AC_k_ws`, `AC_k_wu`,
`AC_k_su`, `AC_cds`, `AC_cdw`, `AC_ktm_block`, `AC_A`, `AC_XSSS`, `AC_XWSS`,
`AC_fPKA_TnI`, `AC_PKAForceMultiplier`). The active-tension catalog deliberately
omits these from its `constants` list, and overriding one has no effect (the
solver recomputes it from its inputs). To *change* such a quantity, override the
user-facing constants it derives from. An agent may still **reason about** derived
values (e.g. predict how halving `AC_dr` shifts `AC_k_su`) — just don't try to set
them directly. (Note: the ionic catalog, which is auto-generated from the full C++
constant enum, *does* list derived constants; the same rule applies there — listed
≠ overridable.)

`run --strict` and `step --strict` already compare predicted artifacts to
on-disk reality after every step/run -- no separate file to read. The
printed JSON payload carries an `artifact_reconciliation` object, built by
`reconcile_artifacts()` (`core/runtime/reconciler.py`):

```python
payload = json.loads(run_strict_stdout)  # the JSON run --strict prints
reconciliation = payload["artifact_reconciliation"]
print(reconciliation["matched_count"], "/", reconciliation["predicted_count"])
for artifact in reconciliation["artifacts"]:
    if artifact["status"] == "missing" and not artifact["optional"]:
        print("  warning missing required:", artifact["artifact_id"])
```

Missing-but-optional artifacts are not errors. They only appear under specific
configurations, for example probes that were not enabled.

## Comparing results as quantities

Once two runs' declared artifacts hold quantities a plugin's reader
understands (`RuntimeEvidenceCapability.artifact_value_reader`), an agent
compares them with `omnidriver compare` rather than parsing solver output
itself. Core reads no result file on its own: everything — which runs, which
artifact of each, where to sample, which reference, which pairs and the
tolerance — comes from the agent's comparison request
(`omnidriver/schemas/quantity-comparison.schema.json`), validated against
that schema before anything is read.

**Orientation, pairing and tolerance are the agent's step, and they are
stated in the request.** Core does no frame conversion and infers no
pairing. **A request's
`points` are written in the *reader's* (the solver's) own frame and unit —
not the reference's.** The two frames only coincide for openCARP, whose
reader "orients nothing: openCARP's frame is whatever the mesh says"
(`opencarp/lat_reader.py`); for a points-taking reader in a different
frame, points written in the reference's frame instead sample the wrong
location with zero reported offset. Orienting a reference's coordinates into a
reader's frame (e.g. cardiacFOAM's probe-versus-slab rotation) is the
agent's own step, done before writing the request. A request's `pairs` say
explicitly which `(run, quantity)` on the left compares against which on
the right, under which reference label. A tolerance (`kind`: `absolute` or
`relative`, a `value`, and a `rationale`) is declared once, before either
run is read.

**`points` means one of two things, by the artifact's reader
(`takes_points`).** For a reader that samples at supplied locations
(openCARP's), `points` says where to sample, and the reader receives them.
For a reader that samples where it chooses, `points` instead states the
agent's *expected* location of each named quantity — the reader never
receives them; the comparison checks each sample's own reported
`sampled_at` against that expected point, exactly as for a points-taking
reader, so a mispaired probe still shows up as `sampled_off_point`. Either
meaning requires `max_sampling_offset`: it is **pre-registered, with no
default** — a request that gives `points` without it is refused by name,
before anything is read.

**`both_not_reached` is also pre-registered, with no default.** Every
request states `"both_not_reached": "agree"` or `"fail"`: with `agree`, a
pair whose sentinel (e.g. `-1`) is resolved on both sides does not fail the
report; with `fail`, it does, exactly like `outside_tolerance`. Either way,
the report's `status` is never `passed` unless at least one pair is
`within_tolerance` — a report full of `both_not_reached` pairs is
`unavailable`, with `status_reason` saying why, never a vacuous `passed`.

**What pre-registration actually enforces, and what stays the agent's own
discipline.** Nothing stops rerunning `compare` with a
loosened tolerance at a new report path, and a written report's request
digest ties it to the request bytes that produced it, not to a time before
any value was read. What core actually enforces is narrower: the report is
written once (below), the request's digest is recorded in it, and
(`omnidriver.quantities` reports specifically) `experiments.inspect_sweep_experiment`
recomputes the overall status from the report's own `metrics` rather than
trusting a stated `status`. Writing the request *before* looking at
results, and not writing a second one once the first result is
unwelcome, is the agent's own discipline — the tool does not, and cannot,
verify it.

**The report is written once, and read-only.** `run_quantity_comparison(request_path,
report_path)` (`omnidriver compare --comparison-request ... --report ...`)
refuses to run at all if `report_path` already exists, and refuses to
overwrite it if two processes race to write it (it hard-links a temporary
file into place, then `chmod`s it `0o444`). A changed request is a new
report, at a new path; the request's own digest is recorded in the report
so the two stay traceable to each other. **`omnidriver compare` exits 0
once a report is written, whatever its `status`** — `failed` and
`unavailable` are still a successful run of the tool; check the report's
own `status` field, not the process exit code, for the comparison's
result. Exit 1 means the comparison itself was refused (a malformed
request, a report path that already exists, …), reported as JSON on
stdout with an `error` field, and no report file is written at all.

Each pair in the report's `metrics` carries a `status`:

- `within_tolerance` / `outside_tolerance` — both sides evaluated, compared
  against the pair's bound;
- `both_not_reached` — the sentinel (e.g. `-1`) on both sides, resolved
  before any unit conversion, never converted itself (`-1 s` is never
  `-1000 ms`); counts as agreement or as a failure per the request's
  `both_not_reached` choice above;
- `reached_on_one_side` — the sentinel on exactly one side;
- `sampled_off_point` — a side's reader sampled further from its requested
  or expected point than the run's stated `max_sampling_offset`;
- `not_evaluated` — a side could not be read at all (a `reason` says why:
  the case did not complete, the stack declares no reader for the
  artifact's format, the artifact is missing, the reader itself raised, or
  an expected location was given but the reader reported none to check it
  against).

Each side of a pair also reports its `value`, `unit` (post-conversion) and
`declared_unit` (the reader's own), its `sampling_rule` (e.g. `node`,
`point`) and its
`sampled_at`/`sampled_at_unit` next to the
`requested_at`/`requested_at_unit` point that was asked for and the
`sampling_offset`/`sampling_offset_unit` between them — so a wrong pairing
or a misoriented frame is visible in the report itself, not hidden behind
an aggregate number, and every one of those location numbers carries its
own unit (`max_sampling_offset_unit` likewise, on each `runs` entry). The
report's own `status` (`passed`/`failed`/`unavailable`) is `failed` if any
pair is outside tolerance, reached on one side only, sampled off point, or
(with `both_not_reached: "fail"`) both not reached; `unavailable` if any
pair could not be evaluated, or if no pair reached `within_tolerance` at
all; `passed` otherwise.

**Relative paths in the request resolve against the request file's own
directory**, not the current working directory: `"reference": "../reference.json"`
in `requests/request.json` reads `reference.json` next to `requests/`, and
likewise for each run's `sweep_output`.

**Attaching the report to an experiment.** `quantities.experiment_comparisons(report_path,
sweep_output=...)` builds the `ComparisonRequest` tuple for every case in one
sweep that the report actually names, for `experiments.inspect_sweep_experiment(...,
comparisons=...)` to associate. Core verifies the association itself
(`ExperimentCase.comparison.association_status`) from the run's own recorded
digests — it never trusts the report's say-so about which case it covers.

**Example: openCARP vs openCARP, two resolutions, at the paper's points**
(`packages/omnidriver-opencarp/tests/test_quantity_comparison_native.py`,
proof for `benchmarks/niederer2011.json`). An agent runs the sweep, reads
each case's own artifact id off its run document, writes points from the
reference (already in the reader's frame — F3, `docs/solver-learning/opencarp.md`),
and states the pairing and tolerance itself:

```bash
OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials DYLD_LIBRARY_PATH=/opt/homebrew/lib \
  python -m omnidriver sweep-run --plugin opencarp --spec sweep.json \
  --output-dir sweep --scratch-dir scratch
```

```json
{
  "schema_version": 1, "reference": "benchmarks/niederer2011.json",
  "tolerance": {"kind": "absolute", "value": 5.0, "unit": "ms",
                "rationale": "declared before either run was read; exploratory, not a benchmark acceptance claim"},
  "both_not_reached": "agree",
  "runs": {
    "dx500": {"plugin": "opencarp", "sweep_output": "sweep", "case_id": "case_0001",
              "artifact_id": "record.solve.2", "points": {"unit": "mm", "at": {"P1": [0, 0, 0], "...": "..."}},
              "max_sampling_offset": 0.001},
    "dx250": {"plugin": "opencarp", "sweep_output": "sweep", "case_id": "case_0002",
              "artifact_id": "record.solve.2", "points": {"unit": "mm", "at": {"P1": [0, 0, 0], "...": "..."}},
              "max_sampling_offset": 0.001}
  },
  "pairs": [{"reference_label": "P1", "left": {"run": "dx500", "quantity": "P1"},
             "right": {"run": "dx250", "quantity": "P1"}}]
}
```

```bash
python -m omnidriver compare --comparison-request request.json --report report.json
```

At dx 500 vs dx 250 (dt 50 µs, tend 150 ms), the report's own numbers are the
proof, not agreement between resolutions: P1 (nearest the stimulus) is
`within_tolerance` (both around 1.355 ms), while most other points are
`outside_tolerance` by tens of ms — the coarser mesh's diagonal conduction
disagrees with the finer one, which is exactly what a spatial-refinement
comparison is for. The pipeline reporting that correctly, with every value,
unit and sampled location shown, is the proof; a passing overall `status` is
not the goal.

### Comparing two solvers on the Niederer benchmark

The worked example is
`packages/omnidriver-cardiacfoam/tests/test_niederer_cross_solver_native.py`.
It needs both native environments, and its evidence is
`docs/solver-learning/cardiacfoam.md` section X. These are the agent's
steps. Core does none of them for you.

1. **Orient each solver from its own native files, never from a secondary
   map.**
   - **cardiacFOAM** (`NiedererEtAl2011verification`). Three files:
     - `constant/electroProperties`, `monodomainSolverCoeffs.externalStimulus`:
       the stimulus box `stimulusLocationMin`/`stimulusLocationMax` is at
       the corner (0, 0, 7) mm;
     - `system/blockMeshDict`: the slab spans x 20, y 3, z 7 mm;
     - the conductivity tensor: fibres run along x.

     Against `benchmarks/niederer2011.json`'s `frame` (origin at the
     stimulus corner; axes a, b and c along the 20, 7 and 3 mm edges), that
     gives x = a, y = c, z = 7 mm - b. So probe k of
     `system/Niedererpoints` is P(k+1).
   - **openCARP** (`02_EP_tissue/03E_study_resolution`). `nversion.par`'s
     `stim[0].elec` box sits at the origin, and the record's `mesher` slab
     is 0-20000 x 0-7000 x 0-3000 µm with fibres along x
     (`docs/solver-learning/opencarp.md` F3). Its frame *is* the reference
     frame.
2. **Run both at a setting that reaches every point.**
   - Use the same dx and time step on both: the `dx` axis is in metres for
     cardiacFOAM and in µm for openCARP, and `nversion.par:dt` is in µs
     (G2).
   - Run long enough for the slowest point to activate on both. At dx
     0.5 mm that is past about 143 ms (`cardiacfoam.md` Q7, openCARP G4),
     and the example uses 200 ms. The native cardiacFOAM `endTime` (0.015 s)
     reaches only P1.
   - Each solver runs as its own `sweep-run`, with its own `--output-dir`
     and `--scratch-dir`.
3. **Write each side's points in its own solver's frame and unit.**
   - openCARP's reader samples at the points you give it. Give the
     reference's own coordinates, in mm.
   - cardiacFOAM's reader chooses its own sampling (`takes_points` false),
     so its `points` are your *expected* locations. Give them in metres,
     straight from `system/Niedererpoints`, including the 0.019999 x
     coordinate.
   - Each side needs its own `max_sampling_offset`. For openCARP it is a
     rounding bound, because every P1-P9 is a node at dx 500 µm. For
     cardiacFOAM it is 0: its reader now requires `interpolationScheme
     cellPoint` on the case's `system/Niedererpoints` and reports each
     probe's own location. The worked example below ran before
     that, with `cell` sampling.
   - No code converts a frame. The orientation is in your points and in
     each pair's `note`.
4. **Pair explicitly.** Each `pairs[]` entry names the openCARP quantity
   `P<k+1>` and the cardiacFOAM quantity `"<k>"` under that reference label.
   Its `note` says how you oriented it. Take each side's `artifact_id` from
   its run document's `expectedArtifacts`, by format:
   - openCARP: `opencarp_lat_per_node`, `record.solve.2`;
   - cardiacFOAM: `cardiacfoam_activation_probes`, `record.samplePoints.0`.
5. **Pre-register, then run `compare`.**
   - Declare the tolerance, with its rationale, and `both_not_reached`
     before either run is read. The example chooses `fail`, so a point the
     duration was too short for fails the report instead of agreeing.
   - Keep the request. Its digest is in the report.
6. **Read the report, not the exit code.**
   - `omnidriver compare` exits 0 whenever it writes a report.
   - Check the report's `status`, and each pair's two `sampled_at` against
     its `requested_at`, with their units: µm for openCARP, m for
     cardiacFOAM.
   - Attach the report to each sweep with
     `experiment_comparisons(report_path, sweep_output=<that sweep>)` and
     check `association_status` is `run_verified` for both.
   - A `failed` status between two discretisations is a finding to report,
     not a request to retune. In section X it is `failed`: P1, P3 and P7
     agree within 5 ms, and the points across the 7 mm edge differ by
     15-19 ms.

### The Niederer campaign: the whole grid, for a cluster

`benchmarks/niederer2011/campaign/` runs the steps above
over the paper's full grid, Δx 0.5/0.2/0.1 mm × Δt 0.05/0.01/0.005 ms. Its
`README.md` is the runbook, and covers:
- each solver's environment;
- one `sweep-run` per solver and Δx, serial or on N ranks, with a Slurm
  example;
- 21 pre-registered requests, one cross-solver per level and one temporal
  per solver, Δx and pair of successive Δt, with their digests;
- `campaign.sh compare`, and a performance protocol.

What it adds to the steps above:
- **Relative request paths.** Every path in a request is relative, and
  `runs/` is a link to scratch. So a request's digest is the same on
  every machine, and nothing is filled in per run.
- **openCARP runs `nversion.par:mass_lumping 0`.** That is the full mass
  matrix, which openCARP's own `run.py` uses. The binary's default is
  lumped, and the `niedererNVersion` record passes nothing, so the runs
  above were lumped. At Δx 0.5 mm, P8 is 58 ms with the full
  mass matrix against 126 ms lumped (`docs/solver-learning/opencarp.md`
  G10).
- **Per-level studies.** cardiacFOAM uses its native study, not a copy.
  `level_study.py` keeps one Δx's rows and adds the rank count, and
  changes nothing the study states.

## The entries of one dictionary: `omnidriver catalog`

```bash
omnidriver catalog --plugin cardiacfoam --entry niederer2011 --cases-root <tutorials> \
    --document constant/electroProperties --key monodomainSolverCoeffs.ionicModel
```

It prints the record's key catalogue as JSON, the same entries `describe`
shows as `record_surface.keys` and the record-key validator refuses by.
`--document` and `--key` filter it, and both are optional. A concrete key
such as `stim[0].start` finds its `stim[Int].start` template. Each entry
names its `document`, `key`, `value_kind` and `description`. cardiacFOAM and
cardiacCore entries add `driver_path`, `unit`, `menu`, `typical_value`,
`applicable_when` and `source_refs` (C++ files). openCARP entries add
`default`, `minimum`, `maximum`, `menu` and `source_refs` (the binary's
`+Help`). No catalogue here records a default for an OpenFOAM key.

`cxx_source` says whether the C++ was read. The source root is supplied,
never discovered. For cardiacFOAM it is `$OMNIDRIVER_NATIVE_TUTORIALS/../src`,
and for cardiacCore `$OMNIDRIVER_CARDIACCORE_TREE/src`; the plugin profile's
`cxx_mapping.source_root` declares both. When the root is supplied, the
stack's scanner runs and reports any drift. Every entry whose values a C++
runtime-selection table registers (every `ionicModel`, say) then carries
them as `cxx_values`. `plan --strict` runs the same scan and fails on drift.
Without the root it notes `plugin_cxx_source_not_supplied` and scans
nothing. openCARP has no C++ mapping (`cxx_source: null`): its catalogue is
generated from the binary.

## A solver's shell: `omnidriver env`

```bash
OPENCARP_MPI_BIN=/usr/local/lib/opencarp/lib/petsc/bin DYLD_LIBRARY_PATH=/opt/homebrew/lib \
HYDRA_IFACE=lo0 omnidriver env --plugin opencarp
```

Each plugin's manifest declares its environment: the variables you supply
(each with why it is needed and whether it is required), the file to source,
the directories to put first on `PATH`, and its MPI launcher. The OpenFOAM
layer declares one shell for cardiacFOAM and cardiacCore. `env` reads only
what is set; it never searches the disk. It prints JSON with:
- each variable, set or unset, with its value;
- `shell_prefix`, the bash commands in the one safe order: source first, then
  every export (macOS strips `DYLD_*` when bash starts), then `PATH`;
- the launcher `mpirun` resolves to after that prefix: path, real path and
  version;
- every authorized command's path, or `null`;
- `preflight`: the stack's own preflight on that environment, over its solver
  command and a 2-rank solve.

Run commands behind the prefix: `bash -c '<shell_prefix> omnidriver run ...'`.
It exits 1, with the refusal named, when a required variable is unset or the
check fails. Each solver's shell puts only its own MPI first, and a launcher
from the other MPI is refused (`openfoam_mpi_launcher_mismatch`,
`opencarp_mpi_launcher_mismatch`). Every step a run executes records where
it ran in `workflow_state.json`, under `steps[].host`: host name, OS, CPU,
core count, the scheduler and threading variables, the declared variables
and, under a launcher, its path, version and rank count.

## Discovering what's valid

Three layers of discovery:

1. **What tutorials exist?** `omnidriver.core.introspection` does not export a `describe_launch_matrix` function. Read `registered_tutorials`/`available_tutorials` off `describe_entry(...)`'s output (see item 6 below), or call `list_entries(cases_root, driver_context=driver_context)` / `list_case_directories(cases_root, driver_context=driver_context)` from `omnidriver.core.runtime.registry` directly.
2. **What dict keys can I set?** Iterate `omnidriver.cardiacfoam.dict_entries_catalog.ELECTRO_PROPERTY_ENTRY_GROUPS` and `omnidriver.cardiacfoam.common_dict_entries.PHYSICS_PROPERTY_ENTRIES` for case-physics entries. For time-control use `omnidriver.cardiacfoam.common_dict_entries.CONTROL_DICT_ENTRIES` (`deltaT`, `endTime`). Each entry carries `driver_path`, `value_kind`, `enum_values`, `unit`, `typical_value`, and structured constraints (`applicable_when`, `forbidden_when`, `required_when`, `mutually_exclusive_with`). These live in the `omnidriver-cardiacfoam` package, not `omnidriver.dict_entries` in core — core's `dict_entries.py` only exposes context-aware helpers such as `get_electro_property_entry_groups(driver_context)`.
3. **What ionic models can I pick?** `from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG`. Each entry carries `states`, `algebraic`, `compatible_solvers`, `compatible_tissues`, `species`, `cardiac_region`, `recommended_exports`.
4. **What utilities are known?** `from omnidriver.core.utility_catalog import load_utility_manifests`; call it with a plugin's utility root(s) (`plugin.get_utility_roots()`) to get a `dict[str, UtilityManifest]`. Strict planning fails when a workflow command has missing required `produces` metadata. There is no `UTILITY_CATALOG` module-level constant — core names no solver's utilities by design; see `future/UTILITY_CATALOG_STANDALONE_GAP.md`.
5. **What dict keys have parser limitations?** Read `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_key_allowlist.json` (cardiacCore has its own beside its `plugin.yaml`). Strict dict-key scanning fails when new uncatalogued keys appear, stale catalog paths remain, or allowlist entries become unused, and, through its `runtime_selection` section, when an enum's values stop matching the C++ runtime-selection table they come from. (`omnidriver.plugins` is the entry-point group name, not a package path.)
6. **What commands may a workflow step run, and what fields may a function object sample?** Read the `capability_manifest` block emitted by both `describe --entry <name>` and `plan --strict --entry <name>` (and `describe_entry(...)` / `strict_plan(...).to_json()` programmatically). It is the authoritative, machine-readable accept-surface: `allowed_commands` (`core`, `case_scripts`, `utilities`, plus the `$FOAM_APPBIN` note) mirrors the command allowlist exactly, and `samplable_fields` lists the field names the *resolved* model exposes,
keyed by region. **Both blocks are plugin-dependent.** For cardiacFoam the
regions are `electro` / `solid`; under `--plugin none` neither key is
present (only `note`), so read the keys that are there rather than
assuming a fixed set. Author `workflowDag` commands and `functions{}` field lists against this instead of guessing — a command outside `allowed_commands` is rejected before execution, and a field outside `samplable_fields` is dropped silently by the solver (see below).

**Hand-built case directories need both an `Allrun` and a `workflow_contract.json`.**
A directory resolved as `entry_kind="case_folder"` (any case directory under
`cases_root` that isn't a registered tutorial) needs an executable
`Allrun` script *and* a `workflow_contract.json` whose `"steps"` array is
non-empty. Without a populated `"steps"` array, the registry silently sets
the resolved entry's workflow DAG to `None` — there is no diagnostic that
names `workflow_contract.json` or `Allrun` specifically, so `strict_plan`
just blocks at the `workflow_preparation` stage with a generic "workflow DAG
is missing or invalid" error and no pointer to the actual cause
(`sweep_materialize.py` writes both files for exactly this reason).

## What the validator catches

`validate_run(run)` runs seven families of checks:

- **Required fields** — every `required` entry has a value.
- **Enum membership** — values for enum-typed entries are in `enum_values`.
- **Structured constraints** — `applicable_when` / `forbidden_when` / `required_when` / `mutually_exclusive_with`.
- **Solver coupling** — pairings like (`singleCellSolver`, any Purkinje) reject with the table's stated reason.
- **Block references** — `domainCouplings.<name>.conductionNetworkDomain` must point at a declared block.
- **Tissue heterogeneity** — `ionicHeterogeneity` requires a supported `ionicModel` and `endoMInterface < mEpiInterface`.
- **Tissue compatibility** — `tissue` must be in the `ionicModel`'s `compatible_tissues`.

If the dict builder rejects your input with `ValueError`, the message lists every violation. Fix the selectors or overrides and call again.

## Function objects (probes, sampling, sets, …)

Function objects are **OpenFOAM's, not omnidriver's.** Anything you put in a
case's `controlDict` `functions { … }` block is defined by the OpenFOAM
documentation, not by this driver — so there is no driver catalog, builder, or
helper for them, and there shouldn't be. Author them the normal OpenFOAM way:

- **Reuse OpenFOAM's shipped library.** `functions { #includeFunc probes(...) }`
  pulls a ready-made, documented object from `$FOAM_ETC/caseDicts/postProcessing/`.
  `ls "$FOAM_ETC/caseDicts/postProcessing"` lists what is available — that
  directory *is* the reference; do not re-derive these from tutorials.
- **Or write a full typed block** (`type probes; libs (...); fields (...);
  probeLocations (...);`) exactly as the OpenFOAM docs specify. To attach it to
  an existing case, write the fragment into `system/<Name>` and `#include` it
  from a `functions{}` entry, or set it through the `system/<dict>:<entry>`
  override form (the `system/path/to/dict:entry_path` form documented above).

**The only parts you can't get from OpenFOAM docs — because they are
cardiacFoam-specific:**

- **Sample-able field names.** The *object* is OpenFOAM's; the *fields* it can
  sample are this solver's: membrane voltage `Vm`, `activationTime`, total
  ionic current `Iion`; active tension `Ta` and fibre stretch `lambda`;
  bidomain potentials `phiE` / `phiI`; per-ionic-model species (e.g. `Ca_i`).
  The authoritative, model-specific list is the catalogs already noted under
  "Discovering what's valid" (`IONIC_MODEL_CATALOG` states / algebraic /
  `recommended_exports`, `ACTIVE_TENSION_MODEL_CATALOG`). Sample only names that
  exist for your chosen model, or the solver drops them.
- **Regions (multi-region cases only).** Electromechanical cases split fields
  across two regions: `electro` (`Vm`, `Ca_i`, ionic state) and `solid` (`Ta`,
  `lambda`, mechanics). A function object on such a case must carry
  `region electro;` or `region solid;` accordingly. Single-region electro cases
  take no `region` entry. But see the electromechanics note below before
  driving such a case at all.

> ### Electromechanics has no tutorial
>
> **Do not invent one, and do not try to resurrect the old one.**
> `manufacturedMonodomainTotalLagrangianEM`, the factory tutorial for this,
> is deleted rather than migrated: it never worked
> (these cases lay their dicts out per region --
> `constant/electro/electroProperties`, `constant/solid/solidProperties` --
> while the planner looks for `constant/electroProperties`). Electromechanics
> has not been rebuilt as a tutorial record yet. The native case is
> untouched, and the electromechanics/active-tension catalog content
> described above still stands -- only the tutorial entry is gone.
>
> This is a deliberately deferred gap, not a defect to discover. The entry
> name is refused like any other unknown entry; if you are here because you
> want electromechanics to work, the correct response is to report that it
> has no tutorial yet and stop -- not to add one as a side quest.

Outputs land where OpenFOAM puts them:
`postProcessing/<functionObjectName>/<time>/<field>`.

**Strict planning now checks sampled field names.** `plan --strict` parses each
`controlDict` `functions{}` sub-dict's `fields (...)` list and emits a
**warning-level** `unknown_sampled_field` diagnostic (in the report's
`function_object_diagnostics`) for any field the resolved model does not expose —
`region solid;` blocks are checked against the mechanics fields, everything else
against the electro fields (`capability_manifest.samplable_fields`). This is
**non-blocking**: it never fails a plan, because the catalog can lag the C++
solver and a false positive must not block a run — but it turns the solver's
otherwise-silent field drop into a visible signal. `#includeFunc` shorthands are
not parsed (their field lists live in `$FOAM_ETC/caseDicts`). Set
`SKIP_FUNCTION_OBJECT_DIAGNOSTICS=1` to bypass the check entirely.

## Common patterns

### Override a single dict key

```python
build_electro_properties(
    selectors={"myocardiumSolver": "monodomainSolver",
               "ionicModel": "TNNP",
               "tissue": "epicardialCells"},
    overrides={
        "$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude": "60",
        "$ELECTRO_MODEL_COEFFS.solutionAlgorithm": "implicit",
    },
)
```

Override paths use the full `$ELECTRO_MODEL_COEFFS.<key>` form. Top-level keys (like `myocardiumSolver`) live in `selectors`, not `overrides`.

**Block-gated families.** Some groups only appear once you configure them.
`singleCellStimulus.*` is one: override any key under it — as above — and the
rest of the family fills from its typical values, so the four keys the solver
requires together (`stim_start`, `stim_period_S1`, `stim_duration`,
`stim_amplitude`) are never written half-complete. Override none of them and
**no stimulus block is generated at all**, which is deliberate: a run without a
stimulus is legal, and inventing one from defaults would silently pace a case
that asked for nothing. `bathPotentialDomain.*`, `ecgDomains.*` and
`conductionNetworkDomains.*` behave the same way.

### Configure a bath bidomain run

```python
build_electro_properties(
    selectors={"myocardiumSolver": "bidomainSolver",
               "ionicModel": "bathBidomainFDAManufactured"},
    overrides={
        "$ELECTRO_MODEL_COEFFS.bathPotentialDomain.bathCellZones": "(bath organ)",
    },
)
```

Declaring any `bathPotentialDomain.*` override auto-enables the bath block — the bath leaves typical-value default unless overridden.

### Read back an existing dict

```python
from omnidriver.cardiacfoam.dict_builder import parse_electro_properties

parsed = parse_electro_properties("/path/to/case/constant/electroProperties")
# {"selectors": {"myocardiumSolver": "monodomainSolver", "ionicModel": "TNNP", ...},
#  "overrides": {"$ELECTRO_MODEL_COEFFS.solutionAlgorithm": "explicit", ...}}
```

Pass the result directly to `build_electro_properties` to round-trip:

```python
from omnidriver.cardiacfoam.dict_builder import build_electro_properties, parse_electro_properties

parsed = parse_electro_properties(existing_path)
text = build_electro_properties(parsed["selectors"], overrides=parsed["overrides"] or None)
```

Only non-default values appear in `overrides`. Entries matching the catalog's
`typical_value` are omitted. `dynamic_path` entries and keys outside the
catalog are silently ignored by the parser, but strict planning and the strict
dict-key scanner are the contract gates for new generated plans.

### Write a case, then run it separately

```python
build_and_launch(
    electro_selectors={
        "myocardiumSolver": "monodomainSolver",
        "ionicModel": "TNNP",
        "tissue": "epicardialCells",
    },
    physics_selectors={"type": "electroModel"},
    case_dir="/path/to/case",
    end_time=0.001,   # 1 ms — a quick check before widening for production
    delta_t=0.0001,
)
```

`build_and_launch` only writes the case's dicts (plus `system/blockMeshDict`,
and `Allrun` when `include_allrun=True`) through one committed case-write
plan; it never launches anything itself. If the call returns without
raising, the case structure, boundary conditions, and property files are
consistent enough to run. Run the written case with
`omnidriver run --strict --entry-kind case_folder --entry <case_dir>`.

### Parsing Complex OpenFOAM Dictionaries

`mutators.py` mutates dictionaries in two tiers.

**Tier 1** is a line-based reader/writer. It is the primary path because it
returns and writes values *verbatim* -- `5e-6` stays `5e-6`. It handles block
comments, `#include`, and `#calc` correctly.

**Tier 2** is `foam_backend.py`, backed by foamlib. It is consulted only when
tier 1 cannot locate the target -- most commonly a brace inside a quoted value,
which defeats brace counting. foamlib parses in process and never evaluates
`#calc` or `#codeStream`.

Reads never reach tier 2: `read_foam_entry` and `read_foam_dict_block` return
verbatim source text, and foamlib returns typed values.

omnidriver does not shell out to the `foamDictionary` binary, and its
behaviour does not depend on whether OpenFOAM is sourced. If you are writing
tools that query these dictionaries, use the `mutators.py` API -- not `grep`
or `sed`.

### Find past runs

```python
from omnidriver.core.runtime.run_discovery import list_runs
for manifest in list_runs("/path/to/runs/dir"):
    print(manifest["run_id"], manifest["status"], manifest["_manifest_path"])
```

## Known gaps

These are real limitations; the agent must not assume them:

- **Automatic retry** is mechanical and bounded. `run --strict` retries a step
  whose failure is classified *retryable* (currently `workflow_step_timeout`) up
  to its `retry_policy.max_attempts` (or the run's `default_max_attempts`), with
  exponential backoff (`retry_policy.backoff_seconds`). Fatal failures
  (`missing_artifacts`, exec errors, generic nonzero exit / FOAM FATAL ERROR) are
  never retried. Between retryable attempts the persisted `workflow_state.json` is
  kept resumable, so a crash during backoff resumes into another retry. It does
  **not** read logs to reclassify failures or mutate configuration between
  attempts (that is deferred). A *terminal*-failed saved state is still refused by
  `run --strict`; use `step --strict` to rerun it manually.

- **Environment preflight** is command-aware but not exhaustive. Strict planning
  derives the executables your plan will run from its `workflow_dag` steps and
  errors (`environment_diagnostics`, a first-class report field) if any are missing
  from `PATH`, if `WM_PROJECT_DIR` is unset, or if the plan is parallel but no
  `mpirun`/`mpiexec` is found. It warns on a partially-sourced environment
  (`WM_PROJECT_VERSION` / `FOAM_USER_LIBBIN` unset). It does **not** yet check free
  disk space or output-directory writability. Set `SKIP_ENV_DIAGNOSTICS=1` to bypass
  the gate (used by the test suite).

- **Active-tension models beyond NashPanfilov and GoktepeKuhl** are not in `active_tension_catalog.py`. Future C++ models must be registered there before artifact prediction will cover their state variables.

If your agent depends on any of these, expect failure and consider a workaround (e.g. starting from an existing tutorial template and overriding deltas rather than constructing from scratch).

## Where to read further

- `omnidriver/dict_entries.py` — context-aware dict-key helpers (core)
- `omnidriver/cardiacfoam/dict_entries_catalog.py`, `omnidriver/cardiacfoam/common_dict_entries.py` — every dict key with its constraints (`omnidriver.plugins` is the entry-point group name, not a package)
- `omnidriver/cardiacfoam/ionic_model_catalog.py` — every ionic model
- `omnidriver/core/utility_catalog.py` — utility manifest schema and `load_utility_manifests()`; roots come from the active plugin, not an ambient catalog
- `omnidriver/cardiacfoam/solver_coupling.py` — cross-domain coupler rules
- `omnidriver/core/strict_planning.py` — strict preflight report and RunDocument v3 assembly
- `omnidriver/core/runtime/run_model.py` — RunDocument v3 model (any other version is refused)
- `omnidriver/core/runtime/workflow.py` — workflow DAG normalization and validation
- `omnidriver/core/runtime/workflow_state.py` — persisted step state model
- `omnidriver/core/runtime/workflow_runner.py` — low-level strict step executor
- `omnidriver/schemas/run-document.json` (packaged resource) — canonical RunDocument v3 JSON Schema

## Plugin selection (Phase 1)

`--plugin` accepts an installed plugin id from the `omnidriver.plugins`
entry-point group, a trusted `module.path:PluginClass` local-development
import (a colon always selects this form), or `none` for generic OpenFOAM.
The `capability_manifest` accept-surface is plugin-dependent:
`allowed_commands.core` lists solver-neutral OpenFOAM commands plus the
active plugin's own, so it changes with `--plugin`.

---

## Adding a New cardiacFoam Tutorial

cardiacFoam has no factory-tutorial path. Every tutorial registers a
**tutorial record**
(`docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`), a
thin declarative pointer at a native case plus its studies, not Python that
builds cases. Electromechanics has no tutorial yet (see above). There is
nothing left to register a factory into, and a deleted tutorial name is
refused like any other unknown entry.

To add a new tutorial, add a `TutorialRecord` under
`omnidriver/cardiacfoam/records/` and wire it into
`records/__init__.py`'s `TUTORIAL_RECORDS`, plus a `TutorialDisplay` entry in
`omnidriver/cardiacfoam/tutorial_displays.py`. `records/single_cell.py` is
the smallest complete worked example; `records/manufactured_bidomain.py`
shows a record with several studies and a shared axis. See the design doc
above for the record/axis/workflow-step shape, and
`docs/solver-learning/cardiacfoam.md` for what each tutorial's native case
actually reads and writes.

Once registered, drive it exclusively through `omnidriver`
(plan/run/sweep) per `CLAUDE.md` — never a bespoke shell script.

---

## Plugin Guide — Adding a New Solver to omnidriver

This section is for **plugin authors** — developers or AI agents who need to
add support for a new OpenFOAM solver to omnidriver. End-users running existing
solvers do not need to read this section.

> **Quickest path:** Follow the dedicated skill at
> `.agents/skills/omnidriver-plugin-builder/SKILL.md` (**not present in this
> repository** — it lives in the cardiacFoam monorepo, per `KEY_FILES.md`),
> which contains a complete step-by-step workflow, a worked
> `ShallowWaterPlugin` example, and a troubleshooting table.

### What a plugin is

An omnidriver plugin is a Python class that implements the `SolverPlugin`
contract defined in `omnidriver/core/plugin_interface.py`. It creates a
clean boundary between the generic execution engine and all solver-specific
knowledge.

Two Protocol classes define the contract:

| Class | Members | Required when |
|---|---|---|
| `SolverPlugin` | 29 | Always |
| `SolverPluginOptionalHooks` | 27 (probe-based) | Never required; enable capabilities |

### Mandatory files

| File | Purpose |
|---|---|
| `my_solver_plugin.py` | Python class implementing the contract |
| `plugin.yaml` | Manifest: identity, case file rules, optional C++ roots |
| `pyproject.toml` entry-point | `[project.entry-points."omnidriver.plugins"]` |

### Required Members (all plugins)

The list below is `_REQUIRED_PLUGIN_MEMBERS`'s own 10: the 4 identity strings
plus the 6 capability members `capability_seams.members_by_tier()["required"]`
names -- the two places that decide enforcement, kept in sync by
construction (`plugin_interface._required_plugin_members`).

```python
plugin_name             # str — human display name
plugin_id               # str — reverse-DNS id, must match plugin.yaml
plugin_version          # str — plugin semantics version
plugin_api_version      # str — "2", the only supported contract version
get_profile()           # PluginProfile from load_plugin_profile("plugin.yaml")
get_capabilities()      # CapabilityManifest via build_capability_manifest()
get_tutorial_catalog()  # dict with spec_factories, registered_tutorials
validate_configuration(spec)   # tuple[StrictDiagnostic, ...]
validate_run_semantics(context) # tuple[...]
predict_data_artifacts(case_root, spec) # tuple[DataArtifact, ...]
```

### Optional Members (probed; answer a documented fallback when absent)

Everything else `plugin_capabilities.py` declares is optional: most answer a
neutral value (`False`, `{}`, `()`) when the plugin omits them
(`capability_seams.members_by_tier()["optional-neutral"]`); a small set
instead raises, naming the missing hook
(`...["optional-refusing"]`, e.g. `render_case_files`,
`apply_overrides`). A representative sample a solver plugin commonly
implements:

```python
get_solver_commands()           # frozenset[str] — artifact-producing binaries
get_auxiliary_commands()        # frozenset[str] — meshers, decomposers
get_environment_commands()      # frozenset[str] — environment-supplied static commands
is_installed_environment_command(command) # bool — runtime lookup for an environment app
get_utility_manifests()         # dict[str, Any]
get_utility_roots()             # tuple[Path, ...]
resolve_case_models(case_root)  # dict — best-effort, never raise
get_samplable_fields(resolved)  # dict[str, tuple[str, ...]] — by region
get_override_schema(tutorial, info) -> dict
get_run_document_config_schema() -> dict  # JSON Schema
get_dict_entry_catalog()        # dict — entries by document name (unserialized)
get_solve_step_commands()       # frozenset[str]
get_telemetry_source_globs(command) # tuple[str, ...]
get_extra_provenance_paths(case_root) # tuple[RuntimeDependency, ...]
get_artifact_value_reader(format)    # Any | None
```

`get_dict_entries`, `get_dictionary_catalog`,
`get_dict_groups` and `get_tutorial_displays` are optional; absent, each
answers empty. A plugin without dictionaries (openCARP) omits them.

There is no shipped scaffold to copy in this repository. The closest in-repo
example of a plugin with no domain-specific semantics is
`OpenFOAMEnvironmentPlugin`
(`packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py`,
paired with `openfoam-environment.yaml` in the same directory) — read it
alongside this contract and the plugin-builder skill referenced above.

`OpenFOAMEnvironmentPlugin` proves
"no domain-specific semantics"; it does not prove "no OpenFOAM". For the
complete example of a plugin outside OpenFOAM entirely, read
`packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py`
(`OpenCARPPlugin`) — it implements the full contract with none of the four
optional dictionary members and passes conformance C1–C14 against the real
openCARP v18.1 binary.

### Key Optional Hooks (`SolverPluginOptionalHooks`, probed with `getattr`)

Two have no neutral fallback — sweeps fail if they are absent:

| Hook | If absent |
|---|---|
| `route_sweep_case_values(...)` | **Sweeps refused by name** |
| `materialize_sweep_case(...)` | **Sweeps refused by name** |
| `has_case_marker(case_root)` | `False` |
| `is_nondimensional_case(spec)` | `False` (SI mesh checks on) |
| `build_run_document_config(spec)` | `({}, ())` |
| `get_override_scopes()` | `()` |
| `get_regeneration_scopes()` | `()` |
| `get_report_catalog()` | `()` |
| `get_named_catalogs()` | `{}` |
| `get_parallel_steps(step, *, request, read_value, allocation)` | a run asking for `parallel` is refused by name; serial runs never call it |

### Entry-point registration

```toml
[project.entry-points."omnidriver.plugins"]
mysolver = "my_package.my_solver_plugin:MySolverPlugin"

[tool.setuptools.package-data]
"my_package" = ["plugin.yaml"]
```

### Validation commands

```bash
# Verify entry-point is discoverable
python -c "from importlib.metadata import entry_points; \
           print(list(entry_points(group='omnidriver.plugins')))"

# Load and validate
python -c "
from omnidriver.core.plugin_interface import load_plugin_context
ctx = load_plugin_context('mysolver')
print('OK:', ctx.identity)
"

# Strict plan
omnidriver --plugin mysolver plan --strict --entry <tutorial_or_case_path>
```

### `validate_plugin()` cross-validation rules

- `profile.plugin_id` **must equal** `plugin.plugin_id`
- `profile.api_version` **must equal** `plugin.plugin_api_version`
- All `DictEntry.driver_path` values must be **globally unique**

### Common errors

| Error | Cause |
|---|---|
| `KeyError: 'mysolver'` | Wrong entry-point group or not installed |
| `TypeError: missing required members: X` | Missing v1 methods |
| `TypeError: missing v2 contract; missing: X` | Missing v2 callables |
| `TypeError: profile id does not match plugin_id` | YAML id ≠ class property |
| `TypeError: duplicate paths: X` | Two `DictEntry` share same `driver_path` |
| Sweep refused: `does not implement route_sweep_case_values` | Implement sweep hooks |

### See also

- `omnidriver/core/plugin_interface.py` — full Protocol definitions
- `omnidriver/openfoam/environment.py` (`OpenFOAMEnvironmentPlugin`) — closest
  in-repo example of a plugin with no domain-specific semantics
- `omnidriver/opencarp/plugin.py` (`OpenCARPPlugin`) — the complete
  non-OpenFOAM plugin example, passing C1–C14 against the real binary
- `omnidriver/cardiacfoam/cardiacfoam_plugin.py` — full v2 reference
  (`omnidriver.plugins` is the entry-point group name, not a package; the
  real path is `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`)
- `KEY_FILES.md` — navigational map for all reader types
