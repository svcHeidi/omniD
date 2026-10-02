# Historical cardiacFoam operational notes

> **Not a current agent contract.** This file contains useful historical
> cardiacFoam operational detail, including retired pre-omnidriver names and
> host assumptions. Do not use it as a routing or implementation authority.
> Start at [`AGENTS.md`](AGENTS.md), then verify any command here against the
> current CLI, package, and selected adapter before use.

## What the agent can do

| Action | Function | Module |
|---|---|---|
| Discover records, dict keys, ionic models, utilities | `describe_entry(...)` | `omnidriver.core.introspection` |
| Plan one record case (stages a copy, never writes the native case) | `strict_plan(...)` | `omnidriver.core.strict_planning` |
| Execute an agent-authored RunDocument | `omnidriver run/step --run-document <file>`; `build_execution_inputs(...)` | `omnidriver.core.runtime.run_document_exec` |
| Execute one strict workflow step | `run_workflow_step(...)` | `omnidriver.core.runtime.workflow_runner` |
| Read/write strict workflow state | `workflow_state_from_json(...)`, `WorkflowRunState.to_json()` | `omnidriver.core.runtime.workflow_state` |
| Validate RunDocument v3 (any other version is refused) | `RunDocument.from_json(...)` | `omnidriver.core.runtime.run_model` |
| Check a flat `{slot_key: value}` context against the catalogue's rules, its menus and, given the plugin's `cxx_mapping`, the keys its C++ requires | `rule_diagnostics(entries, context, document=, mapping=)` | `omnidriver.openfoam.case_rules` |
| Synthesize a fresh `electroProperties` / `physicsProperties` | `build_electro_properties(...)`, `build_physics_properties(...)` | `omnidriver.cardiacfoam.dict_builder` |
| Parse an existing `electroProperties` back to selectors + overrides | `parse_electro_properties(path)` | `omnidriver.cardiacfoam.dict_builder` |
| Write a from-scratch case's dicts as one committed plan (nothing is launched) | `build_and_launch(...)` | `omnidriver.cardiacfoam.dict_builder` |
| Locate predicted outputs | `strict_plan(...)`'s `expected_artifacts` field (also in `omnidriver plan --strict` JSON) | `omnidriver.core.strict_planning` |
| Verify outputs vs predictions | `artifact_reconciliation` in `run --strict`/`step --strict` JSON output | `omnidriver.core.runtime.reconciler` |
| List past runs | `list_runs(root)` | `omnidriver.core.runtime.run_discovery` |
| Plan/run a study over a record | `omnidriver sweep-plan/sweep-run --spec sweep.json --output-dir <dir>` | `omnidriver.core.runtime.sweep_runner` |

## Selecting the stack

A solver repository names itself in an `omnidriver.toml` at its root, with
exactly four keys, each a path relative to the repository and inside it:

```toml
plugin = "cardiacfoam"
tutorials = "tutorials"
source = "src"
scripts = "applications/scripts"
```

omnidriver reads it only from a place you supply, never by searching upward
from the working directory:

- `--repo <dir>`: the repository. Its `plugin` selects the stack and its
  `tutorials` is the cases root (`--cases-root` is refused with it). Its
  `source` must be where the plugin's `cxx_mapping` finds the C++ relative to
  the tutorials folder. omnidriver exports the profile's declared source
  variable (`OMNIDRIVER_NATIVE_TUTORIALS` for cardiacFOAM,
  `OMNIDRIVER_CARDIACCORE_TREE` for cardiacCore) from the repository, and
  refuses a variable already set to something else. `scripts` is read, not
  yet used.
- `--cases-root <dir>` or `$OMNIDRIVER_CASES_ROOT`, when it is a repository's
  tutorials folder: the cases root itself or its parent holds an
  `omnidriver.toml` whose `tutorials` is that folder. The working-directory
  default for the cases root infers nothing.
- `--plugin <id>`, for a solver with no repository (openCARP, the test toys):
  an installed id from the `omnidriver.plugins` entry-point group, or
  `module.path:PluginClass` (a colon always selects this trusted
  local-development import; neither form is sandboxed). Given with a
  repository, it must select the same stack or the run is refused by name.

With neither a repository nor `--plugin` the run is refused: there is no
default plugin and no choice among installed plugins. `capability_manifest`'s
accept-surface is the selected stack's own, so `allowed_commands.core` changes
with the stack.

## Preferred strict agent loop

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
silently select another checkout. This runtime file is separate from study
values and applies to all cardiacFoam records.

```bash
omnidriver plan --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry singleCell
omnidriver run  --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry singleCell
```

`--entry` is the name of a tutorial record the selected stack registers;
`describe` lists them in its `records` key. A record is the only entry kind.
`plan`, `step` and `run` stage the record's case under
`<scratch>/records/<name>`; the scratch directory is supplied (`--scratch-dir`
or `OMNIDRIVER_SCRATCH_DIR`, outside the cases root) or the command is refused
by name (`ScratchRootNotSupplied`). The native case is never written. A single
plan, step or run takes the native case as it is, plus `--parallel` and
`--input`; any study (`document:key` patches, axes, `parallel`) goes in a
sweep spec (see "Running a study: sweeps").

`describe --entry <record>` takes no study values; it returns `entry`,
`records`, `plugin_catalogs`, `record_preview`, `record_surface` and
`capability_manifest`. A preview of a study is `sweep-plan`.

The `plan --strict` command stages the case and persists the plan's
`run_document.json` under `launch.output_dir`. It prints JSON with:

- `status`: `ok` or `failed`
- `entry`: the record name as requested
- `resolved_entry`: `{entry_name, entry_path}`
- `readiness_score`: weighted 0-100 score over the three stages in
  `simulation_audit`
- `simulation_audit`: the scored stages `workflow_preparation` (workflow DAG
  normalization), `artifact_prediction` and `environment_preflight`
- `workflow_diagnostics`: normalized workflow-DAG validation results (command
  allowlist, DAG structure)
- `artifact_diagnostics`: the stack's configuration validation and the
  command allowlist
- `environment_diagnostics`: missing executables, unsourced OpenFOAM env, missing MPI launcher
- `plugin_diagnostics`: the stack's own checks (`get_plan_diagnostics`);
  errors fail the plan, warnings and notes never do. The OpenFOAM layer
  answers it for cardiacFOAM and cardiacCore with the catalogue compared with
  the scanned C++ (see "The C++ scan"), `unknown_sampled_field` warnings (see
  "Function objects") and `uncatalogued_case_dict_key` warnings for case keys
  nothing catalogues; a key the scan reads is reported once, as the
  `uncatalogued` note, never again as a case-key warning
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
omnidriver step --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry singleCell --step solve
```

**Resuming can silently replay stale results.** If `workflow_state.json`
already says `completed` — e.g. a leftover case directory from a previous
session, code change, or experiment — `run --strict`/`step --strict` report
success and exit 0 without invoking the solver at all; there is no warning.
Any re-run intended as a genuine before/after comparison after a code or
config change MUST pass `--fresh`, which deletes the resolved output directory
before running so the workflow executes exactly as it would on a first run:

```bash
omnidriver run --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry singleCell --fresh
```

`--fresh` refuses to delete anything that doesn't look like omnidriver's own
output (no `workflow_state.json`/`sweep_manifest.json`/`run_document.json`
found), the filesystem root, your home directory, or a path outside
`OMNIDRIVER_ALLOWED_RUNS_ROOT` when that's set — but it does not prompt for
confirmation, so treat any `--output-dir`/case directory you point it at as
fully disposable and copy out anything you want to keep first.

`--max-total-attempts <N>` caps the total number of step executions across the
whole run (a retry-storm guard on top of each step's per-step `max_attempts`).
It defaults to unbounded.

Programmatic planning uses the same contract:

```python
from omnidriver.core.plugin_interface import load_plugin_context
from omnidriver.core.strict_planning import strict_plan

# `driver_context` is keyword-only and has NO default: which adapter's
# semantics a plan is built under is supplied, never guessed. `cases_root` and
# the scratch root are supplied too. Any other key in `overrides` is a study
# value for this one case.
report = strict_plan(
    "singleCell",
    overrides={"cases_root": "<tutorials>"},
    scratch_root="<scratch>",
    driver_context=load_plugin_context("cardiacfoam"),
)
payload = report.to_json()
if payload["status"] != "ok":
    raise RuntimeError(payload)
print(payload["workflow_state"]["current_step_id"])
```

### Running a case folder that is not a record

`--case <dir>` stands in for `--entry` when you hold a case folder that is no
record: one you wrote, or one `build_and_launch(..., include_allrun=True)`
produced.

```bash
omnidriver run --strict --plugin cardiacfoam --case <dir> --scratch-dir <scratch>
```

It builds an ad hoc record of one step, `run`, that runs the stack's declared
case entrypoint (`Allrun` for the OpenFOAM stacks), staged from `<dir>` into
`<scratch>/records/<dir name>`; `<dir>` is never written. The folder must hold
that entrypoint. `--case` is valid with `describe`, `catalog`, `plan`, `step`
and `run`, excludes `--entry` and `--cases-root`, and is refused by name where
the stack declares no entrypoint (openCARP).

### Executing an agent-authored RunDocument

`plan --strict` emits a complete `run_document` (RunDocument v3) in its JSON
output. An agent can persist that document, edit it (e.g. add or reorder
`workflowDag` steps, set per-step `retry_policy`), and execute the edited
document directly — the driver runs *your* document instead of regenerating
one from `--entry`:

```bash
# 1. Plan and capture the run document the planner produced.
omnidriver plan --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry singleCell > plan.json
python3 -c "import json; json.dump(json.load(open('plan.json'))['run_document'], open('run.json','w'))"

# 2. (optional) edit run.json — workflowDag, retry_policy, expectedArtifacts.

# 3. Execute the document. No --entry; --strict is implied by the document.
omnidriver run  --repo <cardiacFOAM> --run-document run.json
omnidriver step --repo <cardiacFOAM> --run-document run.json --step solve   # single step
```

`--run-document` is mutually exclusive with `--entry`, `--case` and
`--cases-root`. Before executing, the driver:

1. Loads and schema-validates the document. Any version but 3 is refused.
2. Checks the document's plugin identity against the selected stack.
3. Re-normalizes the supplied `workflowDag` and enforces the **command
   allowlist**: each step's command must be a known OpenFOAM/driver core
   command, a recognized case script (`Allrun`-family), an entry in the
   active plugin's utility manifests (`get_utility_manifests()`, declaring
   `produces`), or an executable installed under
   `$FOAM_APPBIN`/`$FOAM_USER_APPBIN` (any core OpenFOAM app or your own
   compiled utility). Arbitrary non-OpenFOAM commands are rejected before
   anything runs. Note: when OpenFOAM is not sourced, only the core set +
   case scripts + declared utility manifests are accepted.
4. Requires `launch.caseRoot` (an existing directory) and `launch.outputDir`;
   when `OMNIDRIVER_ALLOWED_RUNS_ROOT` is set, both must resolve under it.

If any of these produce an error-level diagnostic, the command prints
`{"status": "failed", "diagnostics": [...]}` and exits non-zero **without
executing anything**. Otherwise execution, `workflow_state.json` resume,
retry/backoff, and `failure_context` behave exactly as for an `--entry` run.

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

## Running a study: sweeps

A study — values to change in a record's native case — goes in a sweep spec.
`sweep-plan` previews every case without running anything; `sweep-run`
additionally runs each. A one-case study is a one-value axis. A `sweep.json`
has two top-level objects:

- `"base"`: `entry` (the record) and `cases_root` (where its native case
  lives, relative to the directory the sweep runs from), both required: a
  record has no ambient cases root, and the sweep commands refuse
  `--cases-root`. Every other key is a study value fixed across every case.
- `"sweep"`: `"mode"` (`"cross_product"` or `"zip"`), `"independent"` (axis
  name to list of values), and `"dependent"` (a list of
  `{"name", "derive", "of"}` entries for derived *labels only*; the registered
  derivations are `case_id_template`, which joins the named `of` values into a
  `caseId`, and `output_dir_name_template`).

Each `independent`/`dependent` name, and each `base` key other than
`entry`/`cases_root`, is a `document:dotted.path` key, one of the record's own
axes, its route selector (`mesh`), `parallel`, or a naming key (`caseId`,
`output_dir_name`). Anything else is refused up front, for the whole sweep.
`describe --entry <record> --cases-root <tutorials>` lists the record's axes
and keys.

`niederer2011` is a **tutorial record** (`records/niederer_2011.py`), a thin,
declarative pointer at the native case (`NiedererEtAl2011verification`). Its
study names real `document:dotted.path` keys and its own `dx`/`tetDx` axes
directly, in the case's own units (metres, seconds):

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
`omnidriver sweep-plan --repo . --scratch-dir <scratch> --spec tutorials/NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json`.

One case with study values is the same spec with one-value axes:

```json
{
  "base": {"entry": "niederer2011", "cases_root": "tutorials", "mesh": "hex"},
  "sweep": {"mode": "zip", "independent": {"dx": [0.0005], "system/controlDict:endTime": [0.2]}}
}
```

Each case is staged from the native case into `<output_dir>/cases/<case_id>/`
and committed there; the native tree is never written. A `caseId` dependent
entry becomes the case's directory name (validated for uniqueness and
path-safety); otherwise cases are named `case_0001`, `case_0002`, ... in
expansion order. A case that cannot be staged or planned fails alone
(`materialization_error`, or `plan_error` in `sweep-run`), not the whole
sweep. `sweep-plan` reports each
case's `status`, `record_commit_status`, `unchanged_patches` (a patch that
already matched the case) and its full `plan`.

`sweep-run` plans and runs the cases serially, each as a child
`omnidriver run --run-document <output_dir>/<case_id>/run_document.json`, and
records them in `sweep_manifest.json`. A sweep does not resume across
invocations: an `--output-dir` that already holds a manifest is refused by
name, and `--fresh` deletes the whole `--output-dir` and starts over.
`--case-timeout-s <seconds>` marks a case that exceeds it failed (a
`timeout_error` in its summary) and the sweep continues; `--max-cases`
(default 200) caps the expanded case count, checked before any case is
staged. Keep a failed output directory when diagnosing; cleanup is an
explicit, disposable-output action.

`--output-dir` defaults to `<scratch>/sweeps/<spec-name>`, which needs
`--scratch-dir` (or `OMNIDRIVER_SCRATCH_DIR`); with neither the command is
refused by name (`ScratchRootNotSupplied`) rather than writing into the
checkout (see `CLAUDE.md`'s scratch-root rule).

See `omnidriver/core/runtime/sweep_runner.py` for the full implementation.

## Running a record in parallel

A tutorial record declares its solve step
once, and serial is the default, as the native `Allrun` is. To run the solve
in parallel, ask for it; the solver's own layer knows how, and the code checks
the facts.

**The request.** One reserved study name, `parallel`, in a sweep's `base` or
as a sweep axis, or `--parallel` on the CLI (`describe`,
`plan`/`step`/`run --strict --entry <record>`, `sweep-plan`, `sweep-run`). The
flag is the same request from its own source: a job script adds it without
editing the study, and a flag that disagrees with the study's value is refused
by name, never merged. Absent or `false` is serial. A sweep
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
`record_preview.workflow_commands` shows each step's command line, with N as
the request alone would make it, and `record_preview.parallel` the request. A
run's document carries `resolvedEntry.parallel` (`{"requested": ...,
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
  `--parallel N` equal to what the case says.
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
a count that disagrees with one; a malformed `SLURM_NTASKS`; `--parallel` with
`--run-document`.

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

1. **The brain (`build_sweep_context`)**: Reads the sweep's own record (`sweep_manifest.json`), verifies it against what is actually on disk, and returns a single grounded `SweepContext`.
2. **The postprocessing module (`run_postprocessing_module`)**: A separate function that receives the `SweepContext` and a task. It always refuses (`not_configured`) rather than guessing an undeclared generic analysis task -- there is no automatic per-case script discovery.

If an agent needs deeper reasoning than the flat summary, it reads one case's
durable execution state with `read_case_workflow_state(context, case_id)`,
which raises clearly on an unknown case ID.

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
reconciles claimed artifact ids against on-disk files after each step. If an
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

To apply a chosen fix mechanically, write the same `document:key` patches a
study takes, as one JSON object, and run it against the staged case the plan
wrote (`--apply` needs `--run-document`, because `--entry` re-stages the case):

```
omnidriver plan --strict --repo <cardiacFOAM> --scratch-dir <scratch> --entry <record>
echo '{"constant/electroProperties:singleCellSolverCoeffs.tissue": "epicardialCells"}' > patches.json
omnidriver step --run-document <scratch>/records/<record>/run_document.json --step <id> --apply patches.json
```

Each patch goes through the record's own key validator and typed comparison,
so a key the catalogue lacks is accepted exactly when the C++ reads it, a
patch that changes nothing is reported `unchanged` and writes nothing, and the
whole set commits in one journaled `commit_case_write` that rolls back its own
failure. A name that is not a `document:key` (an axis or reserved name)
changes the plan, so it is refused: plan again with it. The step then reruns
(`attempt++`), the JSON carries `applied_patches`, and one record per attempt is
appended to `remediation_history.jsonl` under the output directory. If the
process dies mid-edit, the next `step`/`run` refuses until
`omnidriver recover --case-root <case>` restores the before-images.

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
stack's scanner runs. Every entry whose values a C++ runtime-selection table
registers (every `ionicModel`, say) then carries them as `cxx_values`.
Without the root a plan notes `plugin_cxx_source_not_supplied` and scans
nothing. openCARP has no C++ mapping (`cxx_source: null`): its catalogue is
generated from the binary.

## The C++ scan: `omnidriver scan` and `catalog --uncatalogued`

The scan (`omnidriver.openfoam.dict_keys_scanner`) reads every dictionary
read in the C++: the key, the method (`get<T>`, `lookupOrDefault`, `found`,
`subDict`, ...), the type, the default, the sub-dictionary scope below the
dictionary it starts from (a parameter, a member, `this` or a literal
`IOdictionary` document), and the selection-table names of the class that
reads it. It also records which dictionary each call passes to which
parameter. A read whose receiver it cannot show to be a dictionary is listed
as unresolved, never guessed. The scan is cached under the scratch root,
keyed by a digest of the `*.C`/`*.H` files and of the scanner itself: every
plan recomputes the digest and rescans only when either changed, and an
unreadable or altered cache file is rescanned.

Preflight links the binary to this source: a user-compiled solver under
`$FOAM_USER_APPBIN`, or a library under `$FOAM_USER_LIBBIN` that a
`Make/files` below the source root builds, that is older than the sources it
is built from gets a `stale_build` warning naming it, the number of newer
source files and the newest of them. The plan and the scan read that source,
so they describe a state the binary was not built from.

The catalogues stay the source of truth, and a key that appears in or
disappears from the C++ never fails a plan. A plan compares them with the scan:
- a key, sub-dictionary, menu value or selection table the C++ reads and the
  catalogue lacks is a `plugin_catalog_uncatalogued` note carrying what was
  scanned (type, default, whether it is required, where, and the `entry`
  arguments to write the catalogue entry from);
- a catalogued key the C++ no longer reads is a `plugin_catalog_unread` note
  ("catalogued; the supplied C++ no longer reads it"), and a case or study that
  sets it gets an `unread_case_dict_key` warning saying it has no effect;
- a catalogue claim the C++ refutes is a `plugin_catalog_disagreement` warning
  stating both sides: a type the C++ reads differently, a menu value no table
  registers, a required key the C++ gives a default, or an optional key the C++
  requires. A read counts against an entry only when it agrees with the entry
  beyond the final name, or is in a file the entry cites, so a same-named key
  elsewhere disagrees with nothing.

The C++ wins when a value is judged: a study's value is checked against the
type the C++ reads the key as, and an enum value outside the names the C++'s
selection table registers refuses the case. Only an invalid value refuses.

A study may set an uncatalogued key at exactly the path where the C++ reads
it, even when the case does not hold it yet: a validated key is written with
an upsert. The scan places a dictionary from the catalogued keys read on it
and from the calls that pass it along; a key at another path, or read only
through a dictionary the scan cannot place, is refused, and the refusal says
where the C++ does read it. The value is checked against the scanned type.
A model a scanned selection table registers but the catalogue's menu lacks
(a new `ionicModel`, say) is accepted the same way.

```bash
omnidriver scan --plugin cardiacfoam --scratch-dir <dir>        # rescan, print a summary
omnidriver catalog --plugin cardiacfoam --uncatalogued         # every uncatalogued read, with its entry arguments
omnidriver catalog --plugin cardiacfoam --unread               # every catalogued key the C++ no longer reads
```

`catalog --uncatalogued` lists each uncatalogued read with its type,
`value_kind`, default, scope and source location: what an agent needs to
describe it and add it to the catalogue. Each plugin's
`dict_key_allowlist.json` records what the scan cannot establish:
`unseen_reads` (catalogued keys read outside the source, such as by
OpenFOAM's `Foam::Time`, or through a non-literal key) and, for
cardiacFOAM, `runtime_selection` (which table each enum's menu comes from).

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

## Checking a solver you are working on: `omnidriver check`

```bash
omnidriver check --repo <cardiacFOAM> --scratch-dir <dir> --record singleCell --checks C1,C4,C6 \
  --benchmarks <omnidriver>/benchmarks
```

`check` runs the conformance checks C1 to C14, and with `--regression` the
record's native regression script (the one its case-file rules name) in a copy
under the scratch root, against the solver your shell holds, and prints the
verdicts as JSON. It **reports and gates nothing**: the exit code is 0 whenever
the checks ran, and a failing check is the report doing its job. Each record
declares how it is exercised briefly (`TutorialRecord.conformance`: a short
study, a patch, a sweep and, for a record that compares against a benchmark, the
quantity C13 and C14 compare); a record that declares none is reported
`no_study`. A record whose commands are not on `PATH` is `not_run`, naming them:
run from the solver's shell (`omnidriver env`). A record that needs a supplied
input takes `--input NAME=PATH`, as in a plan. The native tree is never written:
a check fails if anything under the cases root changed while it ran.

## Discovering what's valid

Three layers of discovery:

1. **What records exist?** The `records` key of `describe --entry <record>`'s output (`describe_entry(...)` programmatically) lists every tutorial record the selected stack registers.
2. **What dict keys can I set?** Iterate `omnidriver.cardiacfoam.dict_entries_catalog.ELECTRO_PROPERTY_ENTRY_GROUPS` and `omnidriver.cardiacfoam.common_dict_entries.PHYSICS_PROPERTY_ENTRIES` for case-physics entries. For time-control use `omnidriver.cardiacfoam.common_dict_entries.CONTROL_DICT_ENTRIES` (`deltaT`, `endTime`). Each entry carries `driver_path`, `value_kind`, `enum_values`, `unit`, `typical_value`, and structured constraints (`applicable_when`, `forbidden_when`, `required_when`, `mutually_exclusive_with`). These live in the `omnidriver-cardiacfoam` package, not `omnidriver.dict_entries` in core — core's `dict_entries.py` only exposes context-aware helpers such as `get_electro_property_entry_groups(driver_context)`.
3. **What ionic models can I pick?** `from omnidriver.cardiacfoam.ionic_model_catalog import IONIC_MODEL_CATALOG`. Each entry carries `states`, `algebraic`, `compatible_solvers`, `compatible_tissues`, `species`, `cardiac_region`, `recommended_exports`.
4. **What utilities are known?** `from omnidriver.core.utility_catalog import load_utility_manifests`; call it with a plugin's utility root(s) (`plugin.get_utility_roots()`) to get a `dict[str, UtilityManifest]`. Strict planning fails when a workflow command has missing required `produces` metadata. There is no `UTILITY_CATALOG` module-level constant — core names no solver's utilities by design; see `future/UTILITY_CATALOG_STANDALONE_GAP.md`.
5. **What does the C++ read that the catalogue lacks?** `omnidriver catalog --plugin P --uncatalogued` (see "The C++ scan" above). (`omnidriver.plugins` is the entry-point group name, not a package path.)
6. **What commands may a workflow step run, and what fields may a function object sample?** Read the `capability_manifest` block emitted by both `describe --entry <name>` and `plan --strict --entry <name>` (and `describe_entry(...)` / `strict_plan(...).to_json()` programmatically). It is the authoritative, machine-readable accept-surface: `allowed_commands` (`core`, `case_scripts`, `utilities`, plus the `$FOAM_APPBIN` note) mirrors the command allowlist exactly, and `samplable_fields` lists the field names the *resolved* model exposes,
keyed by region. **Both blocks are plugin-dependent.** For cardiacFoam the
regions are `electro` / `solid`; read the keys that are there rather than
assuming a fixed set. Author `workflowDag` commands and `functions{}` field lists against this instead of guessing — a command outside `allowed_commands` is rejected before execution, and a field outside `samplable_fields` is dropped silently by the solver (see below).

## What the rules catch

Every record case passes the stack's rules once its study is written and
before anything runs: `plan --strict`, `run` and each case of a sweep. A rule
that finds an error refuses the case by name (`tutorial record 'X': the
resolved case breaks N rule(s): <field>: <message>`), with the rule's own
message. The rules read the resolved case's files, so a direct key, an axis
and the native case all count.

- **Catalogue relations** (cardiacFOAM's `electroProperties`, each cardiacCore
  utility dictionary) — `applicable_when` / `required_when` / `forbidden_when` /
  `mutually_exclusive_with` / `co_required_with`, once per instance of a
  `<name>` block. An enum value outside its menu is refused: the names the
  supplied C++'s selection table registers when the source is supplied, the
  catalogue's menu otherwise. Value types are the C++'s: a study's value is
  checked against them when it is written.
- **Keys the C++ requires** — a key the supplied C++ reads with `get<T>` or
  `lookup` and no default, in a class the case selects (a selection table
  registers it under a name the case holds, or the plugin's reviewed
  `built_when` says the case builds it), that the catalogue lacks and the case
  does not set. The refusal names the key, its dictionary, its type, the C++ file
  and class, and says the catalogue does not list it. A key the same function
  tests with `found` first is optional.
- **Solver coupling** — pairings like (`singleCellSolver`, any Purkinje) reject with the table's stated reason.
- **Block references** — `domainCouplings.<name>.conductionNetworkDomain` must point at a declared block.
- **Tissue heterogeneity** — `ionicHeterogeneity` requires a supported `ionicModel` and well-formed regions and gradient axes.
- **Tissue compatibility** — `tissue` must be in the `ionicModel`'s `compatible_tissues`.
- **ECG consistency** — `personalizedTemplates` and the pseudo-ECG `anisotropic` switch must agree with the verifier and solver they sit beside.
- **Purkinje resistance** — `reactionDiffusionPvjCoupler` needs `rPvj` unless its materialized graph carries `pvjResistances`.

A rule refuses a combination it knows is wrong, never a name the C++ accepts:
an ionic model, tissue or verifier the catalogue lacks but the scan finds
registered (reported `uncatalogued`) passes every rule. `step --apply` runs the
same rules after its edit commits; a refusal leaves the edit in the case, so
patch it again.

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

**Strict planning checks sampled field names.** `plan --strict` parses each
`controlDict` `functions{}` sub-dict's `fields (...)` list and emits a
**warning-level** `unknown_sampled_field` diagnostic (in the report's
`plugin_diagnostics`) for any field the resolved model does not expose —
`region solid;` blocks are checked against the mechanics fields, everything else
against the electro fields (`capability_manifest.samplable_fields`). This is
**non-blocking**: it never fails a plan, because the catalog can lag the C++
solver and a false positive must not block a run — but it turns the solver's
otherwise-silent field drop into a visible signal. `#includeFunc` shorthands are
not parsed (their field lists live in `$FOAM_ETC/caseDicts`).

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
consistent enough to run. Run the written case, with `include_allrun=True`
so it holds an entrypoint, as `omnidriver run --strict --case <case_dir>` (see
"Running a case folder that is not a record").

A case with no mesh gets a generic `system/blockMeshDict`, and the generated
`Allrun` runs `blockMesh` before `cardiacFoam`. `singleCellSolver` gets one
hex cell. `monodomainSolver`/`bidomainSolver`/`eikonalSolver` get a small cubic
slab sized by `dx` (metres, isotropic cell size; not tuned to any tutorial).
`dx` must divide the slab evenly (`cell_counts_from_dx` in
`omnidriver.openfoam.mesh_provisioning` refuses silent rounding) and raises
`ValueError` for `singleCellSolver`. A mesh already under `constant/polyMesh/`
or `system/blockMeshDict` is never clobbered, whatever `overwrite` says, and
`dx` never touches an anatomical mesh imported with `vtkUnstructuredToFoam`.

### Parsing Complex OpenFOAM Dictionaries

`mutators.py` mutates dictionaries in two tiers.

**Tier 1** is a line-based reader/writer. It is the primary path because it
returns and writes values *verbatim* -- `5e-6` stays `5e-6`. It handles block
comments, `#include`, and `#calc` correctly.

**Tier 2** is `foam_backend.py`, backed by foamlib. It is consulted only when
tier 1 cannot locate the target -- most commonly a brace inside a quoted value,
which defeats brace counting. foamlib parses in process and never evaluates
`#calc` or `#codeStream`.

Reads never reach tier 2: `read_foam_entry` returns verbatim source text, and foamlib returns typed values.

omnidriver does not shell out to the `foamDictionary` binary, and its
behaviour does not depend on whether OpenFOAM is sourced. If you are writing
tools that query these dictionaries, use the `mutators.py` API -- not `grep`
or `sed`.

### Find past runs

```python
from omnidriver.core.runtime.run_discovery import list_runs
for state in list_runs("/path/to/runs/dir"):
    print(state["status"], state["_state_path"])
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
  disk space or output-directory writability. The OpenFOAM bashrc is supplied, never
  searched for: `--environment-source`, else `OPENFOAM_BASHRC`, else `openfoam.bashrc`
  in the file `OMNIDRIVER_RUNTIME_CONFIG` names, else the `etc/bashrc` of the install
  a sourced shell names through `WM_PROJECT_DIR`; a plan that needs OpenFOAM and has
  none refuses with `missing_openfoam_env`.

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

## Adding a New cardiacFoam Tutorial

Every cardiacFoam tutorial is a **tutorial record**
(`docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`), a
thin declarative pointer at a native case plus its studies, not Python that
builds cases. Electromechanics has no tutorial yet (see above).

To add a new tutorial, add a `TutorialRecord` under
`omnidriver/cardiacfoam/records/` and wire it into
`records/__init__.py`'s `TUTORIAL_RECORDS`. `records/single_cell.py` is
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
| `SolverPlugin` | the contract's declared members | Only those `validate_plugin` names (below) |
| `SolverPluginOptionalHooks` | probe-based hooks | Never required; enable capabilities |

### Mandatory files

| File | Purpose |
|---|---|
| `my_solver_plugin.py` | Python class implementing the contract |
| `plugin.yaml` | Manifest: identity, case file rules, optional C++ roots |
| `pyproject.toml` entry-point | `[project.entry-points."omnidriver.plugins"]` |
| `omnidriver.toml` | In a solver's own repository, if it has one: `plugin`, `tutorials`, `source`, `scripts` (see "Selecting the stack") |

### Required Members (all plugins)

The list below is `_REQUIRED_PLUGIN_MEMBERS`'s own nine: the 4 identity strings
plus the 5 capability members `capability_seams.members_by_tier()["required"]`
names -- the two places that decide enforcement, kept in sync by
construction (`plugin_interface._required_plugin_members`).

```python
plugin_name             # str — human display name
plugin_id               # str — reverse-DNS id, must match plugin.yaml
plugin_version          # str — plugin semantics version
plugin_api_version      # str — "2", the only supported contract version
get_profile()           # PluginProfile from load_plugin_profile("plugin.yaml")
get_capabilities()      # CapabilityManifest via build_capability_manifest()
validate_configuration(spec)   # tuple[StrictDiagnostic, ...]
validate_run_semantics(case_root) # tuple[StrictDiagnostic, ...]: the resolved case's rules
predict_data_artifacts(case_root, spec) # tuple[DataArtifact, ...]
```

### Optional Members (probed; answer a documented fallback when absent)

Everything else `plugin_capabilities.py` declares is optional: most answer a
neutral value (`False`, `{}`, `()`) when the plugin omits them
(`capability_seams.members_by_tier()["optional-neutral"]`); a small set
instead raises, naming the missing hook
(`...["optional-refusing"]`, e.g. `render_case_files`,
`resolve_case_mutation`). A representative sample a solver plugin commonly
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
get_tutorial_records()          # dict[str, TutorialRecord] — what `--entry` names
get_plan_diagnostics(case_root, *, workflow_dag, env, scratch_root, driver_context)
                                # tuple[StrictDiagnostic, ...] — added to a strict plan
get_case_runtime_conventions()  # CaseRuntimeConventions; `case_entrypoints` is the file `--case` runs
get_dict_entry_catalog()        # dict — entries by document name (unserialized)
get_solve_step_commands()       # frozenset[str]
get_telemetry_source_globs(command) # tuple[str, ...]
get_extra_provenance_paths(case_root) # tuple[RuntimeDependency, ...]
get_artifact_value_reader(format)    # Any | None
```

`get_dict_entries`, `get_dictionary_catalog` and
`get_dict_groups` are optional; absent, each answers empty. A plugin without dictionaries (openCARP) omits them.

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

| Hook | If absent |
|---|---|
| `get_tutorial_records()` | no records: `--entry` refuses every name |
| `get_plan_diagnostics(...)` | `()`: the plan adds nothing of the stack's own. An error fails the plan; a warning or note never does |
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
omnidriver plan --strict --plugin mysolver --cases-root <tutorials> --scratch-dir <scratch> --entry <record>
```

### `validate_plugin()` cross-validation rules

- `profile.plugin_id` **must equal** `plugin.plugin_id`
- `profile.api_version` **must equal** `plugin.plugin_api_version`
- All `DictEntry.driver_path` values must be **globally unique**

### Common errors

| Error | Cause |
|---|---|
| `KeyError: 'mysolver'` | Wrong entry-point group or not installed |
| `TypeError: SolverPlugin is missing required members: X` | A required member (above) is absent |
| `TypeError: profile id does not match plugin_id` | YAML id ≠ class property |
| `TypeError: duplicate paths: X` | Two `DictEntry` share same `driver_path` |

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
