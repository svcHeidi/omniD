# CardiacFOAM reconciliation plan

2026-09-09. Scope: preserve solver knowledge and meaningful test coverage while retaining omniD's solver-neutral architecture. No solver execution or scientific change is authorized by this planning document.

## Reference identities

- Reconciliation baseline: `01a1e24018b0e054656c395d3b261b1f1f87ee15`. Test-scope reassessment inspected HEAD `178f42a` (2026-09-09).
- User-selected solver reference: `/Users/simaocastro/noFrontendCardiacFoam_minor_errors`, current gold `HEAD` at `c3a852e957d23077ce1b2712331dfe45489c4386`.
- Historical driver reference: commit `3c6b5e1640ef0f22e1099bf91bca1fbce2b94c92`, path `applications/scripts/driverFoam/` in that repository. Its child `aa47e7d2` removed driverFOAM as an external add-on. Current solver HEAD therefore cannot supply that directory directly.
- The solver checkout has a modified solids4foam submodule and untracked files. Record these separately; a parent commit does not identify that entire working tree. The older sibling `cardiacFoam` is not the selected migration reference.

## Authority and comparison rules

Use historical driverFOAM to recover intended catalogs and driver behavior, current selected C++/tutorials to check whether those contracts still apply, and omniD to own execution, recovery, evidence and package boundaries. Do not blindly merge a monolithic package into the split architecture.

Basename/hash counts are inventory hints, not a semantic audit. `export-capability-seams.py` and `regenerate-ionic-catalog.py` already exist in omniD's scripts. The dictionary scanner, runtime-selection scanner and names parser exist under their split-package names. Plugin phase tests also have a renamed counterpart. Each supposedly missing behavior needs a mapped consumer and assertion, not just a missing filename.

## Task breakdown

The ownership review and initial delta audit are the input contracts for every
task below. A task may not broaden its scope without a new row in the delta
audit. Core mechanics (transactions, evidence, execution policy) are not in
scope for catalog tasks.

**Progress (2026-09-10):** T0 and T2–T5 are complete. T1 has an initial map but needs T1b below; it is not complete. T6 is implemented with explicit source/runtime selection, committed-input staging and disposable outputs. T7 has passed one complete single-cell reference experiment through OmniD and the solver-owned check-only comparison; the Niederer tissue fixture and a small sweep remain.

**Test scope:** driverFOAM owns orchestration and adapter-contract tests. It integrates and reports solver-owned scientific regressions; it does not independently define scientific correctness or freeze evolving tutorial content. Studies own their experimental protocols and paper baselines. Exact effective inputs and commands must be verified separately from numerical regression outcomes: passing a metric tolerance does not prove every requested override was applied.

| ID | Owner | Work and bounded output | Depends on | Acceptance gate |
| --- | --- | --- | --- | --- |
| T0 | Lead / architecture | Freeze source identities, dirty-tree record, ownership map, and initial delta classification. | None | [ownership review](OWNERSHIP_REVIEW_2026-09-09.md) and [delta audit](CARDIACFOAM_INITIAL_DELTA_AUDIT_2026-09-09.md) agree; no unexplained path delta. |
| T1 | Cardiac adapter | Map each historical test assertion to Core, OpenFOAM, cardiac adapter, or native solver regression. Create only the missing/relocated test records. | T0 | Every retained behavior has one consumer and one executable assertion; no test depends on checkout auto-discovery. |
| T2 | Cardiac adapter | Add the one source-backed `rootStimulus.startTimeList` catalog record, fixture, and focused validation test. | T0 | Selected-source tutorial fixture parses; catalog exposes the path and its list value semantics. |
| T3 | Cardiac adapter | Add the `personalizedTemplates` subcatalog, fixture, and tests for valid configuration and manufactured-ECG incompatibility. | T0 | All nested keys map to selected source reads; invalid manufactured combination is rejected before execution. |
| T4 | Cardiac adapter | Audit `batchedIntegrator` per active-tension model, including Rush--Larsen support; update applicability only for verified models. | T0 | Runtime-selection/build evidence and a model-specific applicability test justify every allowed combination. |
| T5 | Cardiac adapter | Decide and document whether legacy ECG `verificationModel.*` is supported as an alias or intentionally rejected; test that decision. Preserve the existing bath/bidomain path correction. | T0 | One explicit compatibility policy; no restoration of broad `verificationModel.alpha/k` predicates without source evidence. |
| T1b | Test owners across packages | Classify assertions by owner and required resources. Replace broad tutorial-characterization hashes in Core with neutral structural tests and small adapter configuration fixtures; reclassify manufactured-tet tests by actual behavior. | T1, T2–T5 | Each removed snapshot assertion has a behavioral replacement or an explicit retirement rationale; legitimate tutorial edits do not fail unrelated Core tests. |
| H1 | Packaging / test harness | Choose explicit installation of the three distributions or a declared uv workspace; reconcile the stale lock deliberately. | None; parallel with T1b | A fresh environment imports and invokes the intended installed packages without accidental checkout imports; retain separate core-only and wheel gates. |
| T6 | Cardiac integration harness using Core/OpenFOAM contracts | Implement separate selected-source and selected-runtime fixtures with explicit revision, inputs, build identity and disposable output. | T1b, H1, T2–T5 | Source-only checks require no solver. Explicitly requested native checks fail on missing/invalid prerequisites; no host checkout discovery or source mutation. |
| T7 | Driver integration; solver owns numerical oracle | Run a disposable short single-cell and small tissue case through the driver using the selected solver scripts and regression checker. Compare direct/reference and driven execution where applicable. | T6 | Prove intended effective inputs/commands and truthful result reporting separately from the solver regression result. Record applicability, storage and bounded diagnostics. Do not duplicate numerical tolerances in driver tests. |

T1 evidence: [historical test ownership map](HISTORICAL_TEST_OWNERSHIP_MAP_2026-09-09.md).

T6 contract: [selected-source/build fixture contract](SELECTED_SOURCE_BUILD_FIXTURE_CONTRACT.md).
The source/build document records a previously inspected solver selection, not a moving HEAD guarantee. T6 revalidates it at use time. Native acceptance also depends on T1b and H1; one passed single-cell experiment does not complete the remaining tissue/sweep part of T7.

T4 decision (revised 2026-09-09): `batchedIntegrator` is an ionic-model key
and places no constraint on `activeTensionModel`. Batched active tension
always integrates with explicit Euler.

The original T4 conclusion -- that only `NashPanfilovBatched` supplies
Rush--Larsen parameters, so the two Land variants must use `euler` -- read a
constructor flag correctly but mistook it for a property of the models. All
seven Land-2017 states are linear in their own state and therefore
Rush--Larsen-able; the flag recorded that nobody had written the parameters,
not that they could not exist. The deciding evidence is stiffness: Land's
fastest time constant is ~0.7 ms against the 1e-5 s (0.01 ms) timestep both
electromechanics tutorials use, i.e. dt/tau ~ 0.014, where explicit Euler is
comfortably stable. Ionic fast gates run ~50x stiffer, which is why they need
Rush--Larsen and active tension does not.

The solver therefore dropped the Rush--Larsen machinery from
`batchedActiveTensionModel` entirely rather than completing it, and no longer
reads `batchedIntegrator` at all. It must be *ignored* rather than rejected
there: `electroModel::ionicProperties()` returns the same dictionary object as
`electroProperties()`, so a tension model that errored on `rushLarsen` would
abort runs that set the key for their *ionic* model.

The adapter's `_evaluate_batched_active_tension_integrator` rule is removed
accordingly; the catalog entry is scoped to ionic models.

T4 follow-up: `src/activeTensionModels/Make/files` is the selected source's
compiled-model declaration. The adapter now removes its stale
`GoktepeKuhl`/`GoktepeKuhlBatched` claims, adds scientific catalog records for
both compiled T-World variants, and asserts that the selector and the
scientific catalog have the same model identity set. This is a catalog
truthfulness correction; no solver behavior changes.

T5 decision: nested `ecgDomains.<name>.verificationModel` is a supported
source-compatible ECG verifier surface. Its `type` takes precedence over
`ecgVerificationModel`; the adapter records only the shared type, enable,
dimension, and quadrature settings. `alpha` and `k` remain on their
model-specific paths, preserving the bath/bidomain correction.

Next sequence: T1b and H1 in parallel, then implement T6, then T7. Catalog decisions T2–T5 remain closed unless new source evidence contradicts them. No broader architectural rewrite or second scientific regression suite is part of this sequence.

## Scope rules

- T2–T5 may change only `packages/omnidriver-cardiacfoam/` and their tests,
  unless T1 shows a missing OpenFOAM dictionary operation or Core mechanism.
- Core owns transaction, provenance, dispatch, retries, cancellation, and
  generic result tracking. OpenFOAM owns dictionary/runtime conventions.
  CardiacFOAM owns parameter paths, conditions, dimensions, and metrics.
- Defaults, dimensions, admissibility ranges, numerical tolerances, and source
  references are scientific decisions: a task must present source evidence and
  a focused test before changing them.
- The selected binary's compile-time capability is the runtime fact: an
  electro-only build is valid without solids4foam, while an
  electromechanics-enabled build records solids4foam only as optional build
  provenance. Do not infer either capability from source checkout layout or
  operating-system-specific library inspection.
- `named_catalogs.py` is byte-identical to the historical driver and is out of
  scope unless new source evidence changes that conclusion.

## Exit criterion

No unexplained catalog loss; every relevant historical assertion mapped, retained or explicitly superseded; installed core and adapters retain their gates; required native tests use the recorded source/build rather than hidden discovery. A passed driver test is not scientific solver verification.
