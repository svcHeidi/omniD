# CF-1 evidence record: the cardiacFOAM restitution measurement chain

## Status

Execution record for study case **CF-1** (mature adapter reference) of
[the onboarding study protocol](ONBOARDING_STUDY_PROTOCOL.md), acceptance
level 2 (native vertical slice) and level 3 (experiment interface).

The chain under test is the one that feeds cardiacFOAM's
`restitutionEikonalSolver1D`: single-cell pacing, single-cell S1--S2
restitution, and the 1D cable S1--S2 restitution that measures CV and APD90.

## Provenance

| Item | Value |
| --- | --- |
| cardiacFOAM | `6515739bd1b1c6cf7ef21fe1d4e25830352ed4d2` (`main`) |
| OmniD | `87febff4b3cabfa5ffbad571822c2f7feb3db58f`, dirty (`cli.py`, two untracked docs, one untracked test) |
| OpenFOAM | `/Volumes/OpenFOAM-v2412`, v2412, `darwin64ClangDPInt32Opt` |
| Plugin | `org.cardiacfoam` 0.1.0, API v2, `sha256:de4650f505af15ac4a2d1b0bd6e56651152bcbed7cca9f88a5762e83e2ad3c3e` |
| Backend | full (`solids4foam` present) |
| Evidence root | `/private/tmp/omnidriver-experiments/restitution-chain-2026-09-14/` |

Cases were staged as a **committed closure** — `git archive HEAD` of the three
tutorial directories into a temporary cases root — so no run touched the
cardiacFOAM working tree. The closure is 83 files / 1.2 MB; the live
`singleCell` directory by contrast carries 5.1 GB of accumulated, ignored run
output, which is exactly the state that hides the defect in record CF-1.6.

## Records

| ID | Case | Intervention | Outcome | Evidence |
| --- | --- | --- | --- | --- |
| CF-1.5 | All three entries | `plan --strict --cases-root <staged>` | All three planned `ok` at readiness 100%, one warning each (CF-1.7) | `plan-singleCell.json`, `plan-restitutionCurves.json`, `plan-cable1DRestitution.json` |
| CF-1.6 | `restitutionCurves` | Clean staged `run --strict` | **Failed**: `cardiacFoam` aborted on a missing `constant/polyMesh`. Native defect, faithfully reproduced — see below | `run-restitutionCurves.json`, `solve.attempt1.stderr.log` |
| CF-1.7 | All three entries | Strict planning C++/catalog scan | **Scanner inert**: `plugin_cxx_source_unavailable: /Users/simaocastro/src`. Degraded to a warning, so nothing fails | `catalog_coverage_errors` in every plan |
| CF-1.8 | `restitutionCurves` | Re-run after repairing the mesh out of band | **Refused**, with a message that names no remedy (see below); `--fresh` then succeeded | `run-restitutionCurves2.json`, `run-restitutionCurves3.json` |
| CF-1.9 | `singleCell` | Clean staged `run --strict` | **Passed**. TWorld, two paced beats at 0.021 s and 1.021 s, Vm -87.1 to +51.9 mV | `run-singleCell.json`, `TWorld_endocardialCells_S1_1000.txt` |
| CF-1.10 | `restitutionCurves` | `run --strict --fresh` with mesh present | **Passed**. S1--S2 protocol verified in the trace (below) | `run-restitutionCurves3.json`, `BuenoOrovio_epicardialCells_S1_2000_S2_250.txt` |

## CF-1.9 / CF-1.10: what the adapter actually delivered

`singleCell` produced a two-beat TWorld trace with physiological amplitude,
via a `mesh` → `solve` DAG, from a clean closure, with no manual step.

`restitutionCurves` produced the S1--S2 protocol it advertises. Measured from
the written trace (`writeAfterTime 18.0` clips the earlier drive-train beats):

```text
upstrokes        18.0211  20.0211  20.2706  20.5211  s
intervals          2000.0    249.5    250.5         ms
```

That is the last two of ten S1 beats at the declared 2000 ms BCL, followed by
both S2 beats at the declared 250 ms coupling interval, both **captured**. The
`nstim2` train fires every pulse including the last — the historical
end-of-train boundary loss is not present.

Note what this axis is: `S2_INTERVALS_MS` is a **stimulus coupling interval**,
not a measured DI90. That is the known limitation recorded below, not a defect
in this run.

## Findings

### F1 — `restitutionCurves_s1s2Protocol` cannot run from a clean checkout

Severity: **blocking, in cardiacFOAM, not in OmniD.**

The tutorial ships `system/blockMeshDict`, commits no `constant/polyMesh`, and
its own committed `Allrun` is:

```bash
runApplication cardiacFoam
```

with no `blockMesh`. The sibling `singleCell/Allrun` does run `blockMesh`. The
live cardiacFOAM working tree has no `constant/polyMesh` for this case either,
so `./Allrun` fails there today with the same
`Cannot find file "points" in directory "polyMesh"`.

Nothing catches it: the case has no `regression/` directory, so
`tutorials/Alltest-regression` never sweeps it.

OmniD behaved correctly. Its `restitution_curves` spec declares a `solve`-only
DAG, which mirrors the native `Allrun` exactly — the adapter reproduced the
tutorial's own contract, including its error. Fixing the tutorial's `Allrun`
should be paired with adding a `mesh` step to the spec, so the two stay
faithful to each other.

### F2 — the plugin's C++ source root can never resolve

Severity: **silent loss of coverage.**

`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml`:

```yaml
cxx_mapping:
  source_roots:
    - ../../../../../../src
```

`plugin_profile.py` resolves this against `plugin.yaml`'s **own** directory.
Six levels up from `.../omnidriver/cardiacfoam/` is `/Users/simaocastro`, so
the root becomes `/Users/simaocastro/src`, which does not exist.

This is a relic of the pre-migration flat layout: when the plugin lived at
`applications/scripts/driverFoam/openfoam_driver/plugins/cardiacfoam/` inside
cardiacFOAM, six levels up landed on that repo's root and `../src` was
cardiacFOAM's `src/`. After the spin-out, the same relative path climbs out of
the OmniD repository entirely. It is not satisfiable from a wheel either.

The consequence is that `_catalog_diagnostics` in `strict_planning.py` takes
the `continue` branch for every strict plan, so the entire C++↔catalog
dict-key scanner — `unmatched_cxx_reads`, `stale_paths`, `unmatched_subdicts`,
`unused_allowlist`, all of which are `error` level — never runs. It degrades
to one `warning`, so no plan has ever failed on it.

This is the *supplied-versus-discovered* rule in `CLAUDE.md` §"Two rules that
were learned the hard way": the selected solver's source root has no ambient
truth relative to the plugin package, and is already supplied at runtime as
`--cases-root`. Resolving it from the package's own location invents an answer.

### F3 — a failed run cannot be re-run, and the message names no remedy

Severity: **usability, relevant to the study's RQ4.**

After CF-1.6 failed, the identical command returned:

```text
Could not read existing workflow state: Saved workflow cannot resume with
incomplete or metadata-only input evidence
```

The message states a condition, not an action. Three mechanisms exist for this
situation — `--fresh`, `--retry-failed`, and `action=recover` — and the message
names none of them. `--fresh` resolved it, but `--fresh` first prints
`deleting <case>/postProcessing` and does exactly that: against a live case
directory rather than a staged closure, it would destroy prior results.

### F4 — both restitution entries are on the coupling-interval axis

Severity: **known limitation, recorded so it is not rediscovered.**

Neither entry measures DI90. `restitution_curves` defaults declare
`S2_INTERVALS_MS = (1500 … 250)` at a 2000 ms BCL; `cable_1d_restitution`
declares `S2_INTERVALS_MS = (700.0, 500.0)` at 1000 ms. Both are S1--S2
stimulus coupling intervals.

The DI90-aware protocol — `requested_di90_values_ms`,
`reference_repolarization90_s`, S2 scheduled from a *measured*
repolarization90 — was developed in cardiacFOAM at `dea96c21` and removed from
that repository at `aa47e7d2` when driverFOAM was spun out. It exists today
only in cardiacFOAM's git history at `aa47e7d2^`
(`applications/scripts/driverFoam/openfoam_driver/plugins/cardiacfoam/tutorials/cable_1d_restitution.py`,
350 lines, 16 DI90 references). OmniD's copy is the earlier 244-line
pre-DI90 version; `git log -S requested_di90 --all` in OmniD returns nothing,
so the migration never carried it across.

Its test, `test_cable_restitution_postprocessing.py`, was removed with it and
was never added to OmniD, so cardiacFOAM's 30 KB
`setup/postProcessing_cableRestitution.py` is currently untested in either
repository.

The three sweep specs still committed in the cardiacFOAM tutorial
(`sweep_stewart_true_di90_dt1e-6.json`, `..._automaticity_...`,
`..._di90_boundaries_...`) are written against the removed spec and cannot run
against OmniD as it stands.

## What this says about publishing OmniD

Two of the four findings are in the *adapter's own migration*, not in its
design: F2 is a path that stopped meaning what it meant when the package
moved, and F4 is a capability that did not cross with it. Both are invisible
from the test suite, and both were found by *running the thing end to end from
a clean closure* — which is the study's own claim about evidence-led
onboarding, demonstrated against its most mature adapter.

F1 is the strongest positive result: OmniD reproduced a native tutorial's
defect rather than papering over it. An orchestrator that had silently run
`blockMesh` because it looked necessary would have hidden a bug that has been
latent in cardiacFOAM's tutorial tree. That is worth stating explicitly in the
paper — fidelity to the native contract is a feature, and here it has a
concrete instance.

F3 is a direct RQ4 observation: the recovery interface exists and works, but is
not discoverable from the failure it addresses.

## CF-1.11: the cable, end to end

| ID | Case | Intervention | Outcome | Evidence |
| --- | --- | --- | --- | --- |
| CF-1.11 | `cable1DRestitution` | Clean staged `run --strict` | **Passed.** `clean` → `run` → `extract_cv` all exit 0; six postprocessing artifacts produced | `run-cable1DRestitution.json`, `*_cv_summary.json`, `*_event_summary.json`, `*_restitution.csv` |

The DAG ran `blockMesh`, `decomposePar`, `cardiacFoam` on six ranks and
`reconstructPar` through the tutorial's own `Allrun parallel`, then invoked
`setup/postProcessing_cableRestitution.py`. Every artifact the `dea96c21`
hardening added was produced: long-form `_restitution.csv`, `_events.csv`,
`_segments.csv`, and a `_event_summary.json` carrying per-beat APD50/70/90
with a `repolarization*_status` field.

Applied schedule, as planned by the adapter:

```text
externalStimulus.stimulusStartTimeList: (0 1 2 3 4 4.5)
```

Five S1 at 1000 ms plus one S2 at a 500 ms **coupling interval** — explicit
absolute times, so the inclusive-pulse-index trap does not apply.

### F5 — the postprocessor ran in its legacy degraded mode

Severity: **the concrete cost of F4.**

```json
"protocol_outcome": null,
"selection_mode": "legacy_last_activation_no_protocol_metadata"
```

`dea96c21` added a `.cardiacfoam_protocol.json` sidecar carrying the applied
schedule and stimulus geometry, precisely so postprocessing would never infer
the protocol from case names. OmniD's pre-DI90 spec does not emit it, so the
postprocessor fell back to *selecting the last activation* — the same code path
whose beat-association defect produced a fabricated capture from an
automaticity beat. None of the six `protocol_outcome` statuses is available;
the field is `null`.

The hardened postprocessor is present, runs, and produces its artifacts. It is
simply not being given the metadata it was hardened to consume.

### F6 — the cable README misstates the committed mesh

Severity: **documentation, but it silently changes a scientific result.**

`README.md` line 54 claims "Resolution: 0.1 mm along the cable (`200 x 1 x 1`)"
and line 142 describes the calibration at "0.1 mm cable resolution,
`deltaT = 1e-6 s`". The committed `system/blockMeshDict` is `(100 1 1)` — a
**0.2 mm** cable — and `git log -p --all` shows it has never been anything
else. The 0.1 mm reference measurements were produced by sweep specs that
override `dx` (`"dx_values": [[0.1]]`); the committed default case is twice as
coarse. Anyone re-running "the reference" from the committed case silently gets
a different discretisation.

Relatedly, OmniD's `cable_1d_restitution` defaults declare `DX_VALUES = (0.1,)`,
but `run` does not apply it — sweep-axis defaults take effect only under
`sweep-run`, and `run` uses the committed mesh. The adapter is honest about
what it did (the case id reads `DX0.2`), but a reader of the defaults file
would reasonably expect 0.1.

### An unplanned scientific cross-check

This run was a **coarser** replication of the reference conditions — dx 0.2 mm
versus 0.1 mm, `deltaT` 1e-5 s versus 1e-6 s — and it independently reproduces
the reference's repolarization measurements at sub-millisecond agreement:

| Quantity (probe 0) | This run (dx 0.2, dt 1e-5) | Reference (dx 0.1, dt 1e-6) | Δ |
| --- | ---: | ---: | ---: |
| Conditioned APD90, final S1 | 302.70 ms | 303.037 ms | 0.34 ms |
| Reference repolarization90 | 4.303753 s | 4.304086 s | 0.33 ms |
| Measured DI90 of the S2 beat | 197.41 ms | 197.054 ms | 0.36 ms |

Per-beat APD90 at probe 0 across the drive train:

```text
beat 0 (from rest)  315.74 ms
beat 1              301.17 ms
beat 2              301.77 ms
beat 3              302.27 ms
beat 4 (final S1)   302.70 ms
S2 (coupling 500)   291.72 ms
```

Pacing at 1 Hz **shortens** APD90 from the rest beat and then re-lengthens it
slightly. It does not prolong it to approximately 450 ms. The retained
`Purkinje_S1_S2_Calibration.md` claim is refuted a second time, now at a
resolution where the result is demonstrably insensitive to discretisation.

Central-segment CV was **3.136 m/s at a measured DI90 of 197.4 ms**. Under the
reconciliation plan's shifted-axis interpretation the retained `0.500` table
point sits at DI90 ≈ 0.197 s with CV 3.29 m/s, so the two are 4.7% apart —
close enough to be consistent with the axis reinterpretation, and not close
enough to call it a reproduction. CV is the quantity most sensitive to axial
resolution, and this run is at half the reference's, so **this number must not
be used as a calibration point**. It is a consistency check, not evidence.

## Repair: reinstating the DI90 protocol

| ID | Case | Intervention | Outcome | Evidence |
| --- | --- | --- | --- | --- |
| CF-1.12 | `spatial_pacing` | Added the explicit-times emitter; made the S1--S2 emitter delegate to it | `.6g` truncation fixed on both paths; 5 new tests | `tests/test_spatial_pacing.py` |
| CF-1.13 | `cable_1d_restitution` | Ported the DI90 pacing mode, the protocol sidecar and three artifact declarations from `aa47e7d2^` | Committed boundary sweep plans 7/7 `ok`; sidecar verified in a staged run | `tests/test_cable_restitution_di90.py`, `sweepplan-di90-boundaries.json` |

### F7 — stimulus times were being truncated to six significant figures

Severity: **silent numerical regression in the path already in use.**

`generate_spatial_s1_s2_stimulus_lists` formatted its own times with `{t:.6g}`
rather than delegating. The `.12g` fix that `dea96c21` introduced — together
with the explicit-times emitter it lived on — never crossed into OmniD.

A reference S2 time of `4.634086260869566 s` renders as `4.63409` under `.6g`:
a 3.74 us error, **nearly four steps at the protocol's `deltaT = 1e-6 s`**.

The defect was latent because every schedule anyone had run was round. Today's
`cable1DRestitution` run used `(0 1 2 3 4 4.5)`, all exact in six figures, so
it looked clean. It only bites once a stimulus time is *derived* — which is
precisely what the DI90 protocol does. Nothing tested this module at all, on
either side of the migration.

After the repair, a staged DI90 case writes:

```text
stimulusStartTimeList    (0.0 1.0 2.0 3.0 4.0 4.32875368308);
```

against a scheduled `4.303753683083511 + 0.025`, an error below 5e-12 s.

### F8 — `sweep-plan` resolves the case directory from the working directory

Severity: **third instance of the F2 pattern.**

`sweep-plan` and `sweep-run` reject `--cases-root` outright
(`--config/--entry-kind/--cases-root are not valid with action=sweep-plan`) and
resolve the case directory relative to the **process working directory**.
Invoked from the OmniD checkout, the boundary sweep failed all seven cases with

```text
Missing mesh dictionary: /Users/simaocastro/omnidriver/electrophysiologyProtocols/...
```

The workaround is to `cd` into the staged cases root first, after which all
seven plan `ok`. This is the same invented-root class as F2: `plan`/`run` take
a supplied root, the sweep actions discover one instead, and the two disagree.

### Verification

`packages/omnidriver-cardiacfoam/tests`: **845 passed, 1 failed, 104 skipped,
40 subtests passed**. The single failure is
`test_installed_cli_rejects_missing_case_without_solver`, which strips
`PYTHONPATH` on purpose to exercise an *installed* CLI; nothing here is
installed, only reachable through `bin/driverFoam`'s `PYTHONPATH`. Confirmed
pre-existing by running that module on a pristine `HEAD` worktree, where it
fails identically. It is the "installed wheel shape" that `CLAUDE.md` says
people skip — and it is currently the only shape in which this suite is not
green.

Note that this repair is **not** the acceptance gate. It restores the ability
to *run* the gate. Nothing in the C++ model has changed, and no scientific
constant has been touched.

## F9 — the orchestrator stopped a run that had exited successfully

Severity: **not a defect. The strongest positive result in this record.**

While reinstating the DI90 protocol the three postprocessing artifacts were
declared in `expected_artifacts` without being claimed in any step's
`produces`. Core's workflow builder auto-credits an unclaimed artifact to the
last *solver* step -- auxiliary post-processing commands are deliberately
excluded from artifact credit, so that a silently failing solver fails its own
step rather than a later one. `Allrun` was therefore made answerable for files
only `Allrun.post` writes, and the first case stopped with:

```text
Step 'run' exited successfully but has missing expected artifacts:
restitution_event_summary, restitution_metrics_csv, restitution_events_csv
```

### Why this matters more than the bug did

**The step exited 0.** Every command inside it succeeded: `blockMesh`,
`decomposePar`, `cardiacFoam` across six ranks to completion, `reconstructPar`.
A shell `Allrun` -- which is how this case is meant to be run, and how the
committed tutorial does run it -- would have returned 0 and reported nothing
wrong, because `runApplication` chains propagate binary exit codes and nothing
else. An exit code cannot tell you whether an experiment produced its
measurements. It only tells you that no process crashed.

OmniD refused the step anyway, named the three files, and stopped the sweep.

The cost avoided is concrete. The acceptance gate for this workstream is a
seven-case sweep at `deltaT = 1e-6 s`, roughly 3--3.5 h per case: about a day
of compute. Had the artifact contract not been enforced, that sweep would have
run to completion, reported seven successes, and produced no restitution data
at all -- discovered only at aggregation time, or not at all if someone read
the exit status and moved on. The check converted a silent day-long failure
into a loud nine-minute one, on the first real case, against an authoring error
made in this same session.

### The second half of the contract is stronger still

The same check distinguishes two failures, not one:

| diagnostic | condition |
| --- | --- |
| `missing_artifacts` | the declared file never appeared |
| `stale_artifacts` | the file exists, but nothing about it changed |

The runner snapshots every claimed artifact *before* the step and compares
after. `stale_artifacts` catches the classic way a re-run appears to succeed:
the command fails or no-ops, a previous run's output is still sitting in the
case directory, and the file check passes because the file is *there*. For a
tutorial tree that accumulates ignored output -- the live `singleCell`
directory in this study carries 5.1 GB of it -- that is not a hypothetical.

### For the paper

This belongs beside F1. Both are instances of the same property: the
orchestrator declines to call something successful because it looked
successful. F1 is fidelity to a native contract that was itself broken; F9 is
refusal to accept a zero exit code as evidence of a result. Together they
support a claim the study can actually make -- that an evidence-led interface
catches failures the native workflow reports as clean -- and they were both
found by running the mature adapter end to end from a clean closure, not by
reasoning about it.

The honest framing is that F9 caught an error introduced *by this session's own
port*. That is the point. The check is worth having precisely because the
people declaring artifacts are the people who get them wrong.

## F10 — two identifiers named "case id" meet at the artifact seam

Severity: **an adapter cannot correctly declare a postprocessor's outputs.**

The three reinstated artifacts were declared as

```python
path_pattern=f"{output_dir.name}/{{case_id}}_event_summary.json"
```

and that declaration cannot match in either invocation mode. Two independent
reasons, and it is worth separating them because they have different owners.

### The identifier half

Core documents the placeholder in `DataArtifact`:

> `{case_id}` (substituted with the sweep case identifier)

and `_artifact_snapshot` substitutes `case_root.name`. Core is entirely
self-consistent: in a sweep the case directory *is* `case_0001`.

But the cardiac adapter has a **different** case id. `_build_cases` mints
`implicit_Stewart_myocyte_DT0.01_DX0.2_COND01_RDI9025`, `_apply_case` writes it
to `.driverfoam_case_id`, and the postprocessor reads that sentinel
(`postProcessing_cableRestitution.py`, `sentinel = case_dir /
".driverfoam_case_id"`) to name every file it writes. So the files are named
after one identifier and the contract is expanded with another.

**Core already provides the mechanism to make these the same.**
`sweep_expansion.py`:

```python
label = str(values["caseId"]) if "caseId" in values else f"case_{index:04d}"
```

`case_0001` is only the *fallback*. A sweep spec can derive `caseId` from its
axis values through the registered `case_id_template` derivation, and core
validates uniqueness with an error that tells the author which axes to add.
The catalog is a fixed registry -- no `getattr`, no `eval` on spec input.

So there are not two identifiers because core lacks a mechanism. There are two
because **the adapter does not use core's**: it mints its own id in parallel and
core falls back to the generic label. That is the duplicated source of truth.

### The location half

`sweep_runner.py` deliberately forces `effective_routed["output_dir_name"] = "."`
for a staged sweep case, and its comment describes this exact failure mode:

> Leaving it in place double-nests output_dir ... which then makes the
> workflow's artifact check report real, present output as missing.

Core therefore already fixed this bug class *for the directory it materialises*.
What it does not do is tell the spec, which built `path_pattern` from
`output_dir.name` before the rewrite. Any pattern derived that way is stale by
construction. That half is core's: it rewrites a value the adapter used to
build a contract and provides no way to recompute the contract.

### Recommended resolution

One identifier and one location:

1. **Identifier.** Let core's sweep label be *the* case id -- derive `caseId` in
   the sweep spec and have the adapter stop minting a second one, writing
   `case_root.name` into the sentinel (or retiring the sentinel and reading the
   directory name). Then `case_root.name`, the sentinel, the filename prefix
   and the `{case_id}` expansion are the same string by construction.
2. **Location.** Stop passing `--output-dir` from the workflow DAG and let the
   postprocessor use its own default (`output_dir or case_dir /
   "postProcessing"`). The location becomes invariant across `run` and
   `sweep-run`, and `postProcessing/*_event_summary.json` matches in both.

Until one of these lands, the three artifacts cannot be declared truthfully,
and declaring them untruthfully fails the step (see F9).

## F11 — the retired name is still core's own vocabulary

Severity: **naming, but it reaches the provenance record.**

`driverFOAM` survives throughout `omnidriver`, and not only in history docs:

| Reference | Location | Kind |
| --- | --- | --- |
| `produced_by="driverFOAM"` | `core/runtime/artifacts.py` | compared as a literal in `core/runtime/workflow.py` |
| `_has_driverfoam_marker()` | `core/runtime/fresh.py` | gates `--fresh` |
| "driverFOAM cannot route sweep axes / materialize sweep cases" | `core/compatibility.py` | user-facing error text |
| `.tmp/driverfoam/sweeps/<spec-name>` | core | default path |
| `driverfoam-runtime.yaml` | repo root | the runtime config file in active use |
| `bin/driverFoam` | repo root | deliberate back-compat wrapper, documented in the file |
| `.driverfoam_case_id` | adapter, and cardiacFOAM's postprocessor | cross-repo contract |

For a tool named `omnidriver`, whose CLI module is `omnidriver`, recording
`produced_by: driverFOAM` in the artifact provenance and telling users
"driverFOAM cannot ..." is the retired name leaking into the evidence the study
relies on. Core is meant to carry no solver vocabulary; it should not carry its
own former name either.

Three of these are not simple renames:

- `produced_by="driverFOAM"` is compared against a literal, so declaration and
  comparison must change together -- and the string appears in already-written
  `run_document.json` files, which would stop being recognised.
- `driverfoam-runtime.yaml` is in active use; renaming needs a fallback or a
  deprecation window, or existing runtimes break.
- `.driverfoam_case_id` **cannot be renamed unilaterally**: cardiacFOAM's
  committed postprocessor reads it by that exact name. It needs a coordinated
  change in both repositories, or a reader that accepts either name. Note that
  F10's recommended resolution may retire this sentinel entirely, which would
  settle it.

The error strings and the `.tmp/driverfoam/` path are the only ones that are
purely cosmetic. `bin/driverFoam` is a deliberate compatibility shim and should
stay.

## Resolution of F10 and F11

| ID | Intervention | Outcome |
| --- | --- | --- |
| CF-1.14 | F10: case-relative `--output-dir`; artifact patterns glob the suffix instead of using `{case_id}` | Staged sweep case completed with `extract_cv` producing all three declared artifacts |
| CF-1.15 | F11: retired the `driverFOAM` name throughout core, with back-compatible readers | Suite returns to its single pre-existing failure |

### F10 as applied

Two changes, both in the adapter:

```python
# location: a case-relative literal, not the spec-time output_dir
"args": ["--output-dir", defaults.OUTPUT_DIR_NAME],
# identifier: glob the suffix; core's {case_id} names a different thing
path_pattern=f"{defaults.OUTPUT_DIR_NAME}/*_event_summary.json",
```

Verified end to end on a staged sweep case:

```text
workflow status: completed | failed_step: None
  run         completed  produced ['monodomain_vm_series', 'cable_probes']
  extract_cv  completed  produced ['restitution_event_summary',
                                   'restitution_metrics_csv', 'restitution_events_csv']
```

Output now lands in `postProcessing/` in both `run` and `sweep-run`.

### F11 as applied

`produced_by` became `DRIVER_PRODUCED_BY = "omnidriver"`, and the comparison in
`workflow.py` now tests membership of `DRIVER_PRODUCED_BY_VALUES`, which retains
the retired value: a `run_document.json` written before the rename must keep its
bookkeeping excluded from step responsibility, or `workflow_state` and
`workflow_logs` would be charged to the solver step and fail it.

`DRIVERFOAM_ALLOWED_RUNS_ROOT` became `OMNIDRIVER_ALLOWED_RUNS_ROOT`, and the
retired name is still read. That one is not politeness: the variable confines
where `--fresh` may delete, so ignoring an operator's existing setting would
switch a configured safety boundary off with no diagnostic.

Marker helpers, refusal messages, plugin-contract and discovery docstrings, and
the run-document schema description all moved to `omnidriver`. Four references
remain deliberately: `LEGACY_DRIVER_PRODUCED_BY`, and three comments that
describe history correctly.

### Two further defects found while renaming

- The `--output-dir` help text documented `<repo>/.tmp/driverfoam/sweeps/`,
  a path that no longer exists. `default_sweep_output_dir` resolves through
  `scratch_root`, so the real default is `.omnidriver/sweeps/<spec-name>` or
  `$OMNIDRIVER_SCRATCH_DIR/sweeps/<spec-name>`. The help was wrong, not merely
  stale in its branding.
- `plugin_interface.py` directed adapter authors to
  `.agents/skills/driverfoam-plugin-builder/SKILL.md`. There is no `.agents/`
  in this repository; that path belonged to the pre-migration cardiacFOAM tree
  and was deleted there by `aa47e7d2`. It pointed at nothing in any repository.
  Repointed at `AGENT_GUIDE.md`'s plugin section.

### What the suite caught

Four tests failed on the first post-rename run, and one of them earned its
keep: the packaged `run-document.json` is **generated** from `schemas/` by
`schemas/generate_run_document_schema.py`, and the schema had been hand-edited
in its generated copy. Fixed at the source and regenerated. The remaining three
were assertions on the retired strings; they were updated rather than relaxed,
and two new guards were added for the back-compatible readers above.

Final: **1895 passed, 1 failed, 258 skipped, 40 subtests passed**. The single
failure is the pre-existing installed-CLI test described earlier.

## F12 — case identity has no owner

Severity: **design, and the one that matters for a generality claim.**

Core touches case identity in three places that disagree:

| Place | Value | Set by |
| --- | --- | --- |
| `CaseConfig.case_id` (`models.py`) | `implicit_Stewart_..._RDI9025` | the adapter's `build_cases` |
| sweep `caseId`, and the staged directory name | `case_0001` unless derived | the sweep spec, else core's fallback |
| `{case_id}` expansion in `_artifact_snapshot` | `case_root.name` | hardcoded |

Core's own public helper `expand_path_pattern(pattern, case_id=None, time=None)`
is parameterised, and `reconciler.py` documents the sane rule -- substitute a
supplied value, else the glob wildcard `*`. `_artifact_snapshot` bypasses both
and substitutes the directory name unconditionally. So **core already holds two
different behaviours for one placeholder**, and the correct one is already in
the repository.

### Proposed ownership

**Core owns case identity; the adapter owns the naming recipe.**

"Which case is this" is orchestration: every solver has cases, and core already
declares the type, validates uniqueness and names the directory. "What it should
be called" requires knowing that `ionicModel`, `dt`, `dx` and `requestedDI90`
exist, which core cannot know and should not. Core already provides the seam --
`case_id_template` in the fixed derivation registry -- and the cardiac adapter
simply does not use it, minting a parallel identifier instead.

The `.driverfoam_case_id` sentinel is misplaced by the same logic. It is a
driver-to-case channel ("you are running as case X"), which every plugin's
post-processing wants, not cardiac knowledge. Its blast radius is **one writer
and one reader**: `cable_1d_restitution.py` and cardiacFOAM's
`postProcessing_cableRestitution.py`. It is a private handshake between one
spec and one script that happens to span two repositories.

Shape:

1. Core stamps the case identity into every case, under a neutral name.
2. `_artifact_snapshot` expands `{case_id}` from that identity through
   `expand_path_pattern`, matching `reconciler.py` rather than contradicting it.
3. The adapter stops writing a sentinel and stops minting a second identifier;
   `_build_cases` keeps producing the label, which becomes *the* case id.
4. cardiacFOAM's postprocessor reads the neutral name, with a fallback for one
   release.

Cost is roughly 30 lines here and 3 in cardiacFOAM. There are currently **zero**
`{case_id}` path patterns in either adapter, so the semantics change has no
consumer to regress, and F9's enforcement is untouched -- what the placeholder
resolves to is independent of whether matching happens.

The open choice is where the recipe is declared: in the sweep JSON through the
existing `case_id_template` derivation (recipe as data, uniform across plugins),
or routed from adapter code (existing sweep specs unchanged). The first is the
better fit for a generality claim.
