# Core architecture and deterministic execution audit — 2026-09-05

This is a planning report, not an implementation or release certification. The core team comprised an architecture lead and an independent contract/failure expert. Repository instructions and architecture documents were read as historical claims; production call paths and tests were inspected for evidence. No simulation or solver execution was performed by this team. The only live probes were two small, in-memory Python checks described below. All evidence paths are relative to the repository root and line numbers refer to this audit snapshot.

Path abbreviations: `cli.py` means `packages/omnidriver/src/omnidriver/cli.py`; `core/...` means `packages/omnidriver/src/omnidriver/core/...`; bare runtime/profile filenames refer to the full path established in their paragraph.

## Decision

Retain the three-package direction and the explicit operation context, but make a resolved, content-addressed execution contract the center of the system. Today the repository contains useful pieces of deterministic orchestration; it does not yet compose them into a dependable end-to-end guarantee. In particular, provenance models are tested but are not connected to production resume. A large refactor which only rearranges packages would miss the highest-risk defect.

The agent is the reasoning client. Core should provide deterministic inspect, resolve, validate, stage, execute, observe, and resume operations. The OpenFOAM adapter owns actual file interpretation, runtime identity and launcher behavior. The cardiac adapter owns equations, model combinations, units, valid parameter domains, artifact meaning and scientific checks. These are three implementation responsibilities inside the user's two conceptual layers: reasoning and simulation tools. A separate general-purpose C++ intelligence layer is not a prerequisite; expose bounded, versioned source/runtime evidence through these adapters first.

## Evidence and prioritized findings

### C1 — P0 release blocker: resume is not bound to the current inputs or workflow

`packages/omnidriver/src/omnidriver/cli.py:149` and `:270` load an existing `workflow_state.json` and replace the newly planned state. The full-run path rejects only a saved failed state (`:283`). `core/runtime/workflow_orchestrator.py:62` executes only while the supplied state is pending and has a current step. A completed prior state therefore suppresses a changed workflow without checking what produced that state.

`core/runtime/provenance.py:221` provides snapshot construction and `:286` provides comparison; `core/runtime/provenance_inputs.py:234` provides input enumeration. Repository-wide production searches found no callers of the first two public snapshot operations or the enumeration function outside their own implementation modules; callers are tests. `core/runtime/workflow_state.py:54` stores no plan digest, input digest, runtime identity or execution ownership. This is an integration defect, not evidence that the provenance component itself is useless.

**Decision:** retain the provenance primitives; integrate them before further feature expansion. Bind every state and attempt to plan/input/runtime identities. Resume must reject changed DAG, dictionaries, includes, selected initial state, solver binary, libraries, plugin semantics and artifacts, or explicitly create a new run/invalidate dependent steps. Preserve a readable diff.

**Acceptance:** run a fake two-step workflow through the public CLI, then change each identity input independently and prove no completed step is silently reused. Unchanged inputs must resume without duplicate execution. Prove this against an installed wheel.

### C2 — P1: full workflow execution drops plugin context

`cli.py:544` passes `driver_context` to the single-step route (`:556`), but the full-run route (`:558`) omits it and `_execute_run` has no context parameter (`:252`). `core/runtime/workflow_orchestrator.py:32` also has no context, and its runner call (`:65`) cannot forward one. The low-level runner uses that context to resolve plugin entrypoints (`core/runtime/workflow_runner.py:218`) and decomposition directories (`:295`). Missing context defaults to OpenFOAM conventions in `core/plugin_profile.py:230`.

A plugin declaring a custom bare entrypoint or nonstandard decomposition prefix may work in `step` and fail or use different semantics in `run`. This directly contradicts the intended per-operation dependency discipline even though import-boundary gates pass.

**Decision:** refactor run/step around one execution service with a required resolved context. No optional context in internal execution paths.

**Acceptance:** a neutral plugin with a custom entrypoint and custom partition prefix must behave identically under single-step, full-run, retry and resume. Assert context identity at the actual process-launch and artifact-check boundaries.

### C3 — P1: the capability digest does not identify capability semantics

`core/plugin_profile.py:43` hashes only the declarative profile payload. `core/plugin_interface.py:619` assigns that digest as `capability_digest`. The profile explicitly covers files and C++ mapping, not execution or solver semantics (`plugin_profile.py:1`). The context is frozen, but it stores the live plugin object (`plugin_interface.py:250`), and adapters call that object repeatedly (`plugin_capabilities.py:1081`, for example).

Verified in memory: create a context around `GenericOpenFOAMPlugin`, replace its `get_solver_commands` method, then read commands through the existing context. The new command is immediately visible while `capability_digest` remains unchanged. No file or process execution was involved. Independently, a package code change retaining the profile YAML/version does not alter this digest.

**Decision:** rename the current digest to `profile_digest` during migration. Construct an immutable resolved capability snapshot including normalized catalogs, schemas, command/artifact contracts and build/package identity. Record validator implementation/build identity, not only their advertised version. Trusted plugins remain trusted code; freezing does not turn them into a sandbox.

**Acceptance:** changed dictionary constraint, schema, allowed command, artifact contract or plugin implementation invalidates identity. Repeated reads during an operation return the same captured semantics. Unsupported capability returns a typed unavailable result rather than an implicit environment default.

### C4 — P1: large-file fingerprints silently ignore their only change signal

`core/runtime/provenance.py:15` promises metadata fingerprints using size plus mtime above 256 MiB; `:188` switches to metadata with no content digest. `_component_digest_payload` excludes mtime unconditionally (`:199`), and comparison uses that payload (`:216`, `:311`). Two same-sized large files with different contents/mtimes compare equal. `snapshot_from_components` still marks metadata-only snapshots complete (`:238`).

An in-memory component probe changed only mtime on a 300,000,000-byte metadata component: comparison returned no differences, aggregate digests matched, and `is_complete` was true. This probe allocated no large file.

**Decision:** retain explicit fingerprint strength, remove the unconditional exclusion for metadata comparisons. Prefer streaming content hashes for strict reproducibility; cached hashes require a declared invalidation policy. Metadata-only identity must never certify exact content equivalence.

**Acceptance:** same-size metadata changes are visible; same-byte mtime changes for content-hashed files do not invalidate content identity. Required weak/unavailable dependencies yield a named assurance limitation or prevent strict resume.

### C5 — P1: success is weaker than fresh artifact production

The runner marks exit-code zero successful (`core/runtime/workflow_runner.py:275`) and checks declared required outputs with glob existence only (`:278`–`:300`). It accepts any existing matching artifact, including stale outputs; time-indexed artifacts accept serial or any partition match. It does not establish that this attempt produced the file, that every expected partition exists, or that the bytes are valid. This is especially consequential when combined with stale resume and retries.

**Decision:** retain artifact declarations; refactor into typed output contracts with attempt ownership, completeness and adapter validators. Old outputs must be separately classified as preexisting/reused. Preserve raw exit status separately from execution completion and scientific validity.

**Acceptance:** an exit-zero command that produces nothing cannot pass because old matching files remain. Empty/malformed artifacts fail validation when a format is declared. A partitioned result missing one required partition cannot pass an all-partitions contract. Known reusable immutable inputs remain explicitly reusable.

### C6 — P1: concurrency and interrupted execution have no ownership contract

`core/runtime/workflow_runner.py:40` uses a fixed `.tmp` filename and replace; it has no run lease or compare-and-swap state transition. Attempts use deterministic log filenames (`:210`) and open them for writing (`:248`). The runner checks an in-memory pending/failed state (`:191`) before persisting running (`:242`) and launching. Two clients can load the same pending state and launch the same mutable case concurrently. Atomic rename prevents a partially visible JSON write; it does not provide mutual exclusion. A process killed after persisting running has no ownership/recovery record in `workflow_state.py:54`.

**Decision:** add a per-run lease, unique attempt identity, compare-and-swap state transitions, crash reconciliation and process-tree cancellation. Declare whether execution is at-most-once, retryable or idempotent per step. Default timeout retryability is currently unconditional (`failure_classification.py:7`), even though partial effects may exist.

**Acceptance:** two simultaneous clients launch one attempt; the other receives a stable busy/conflict response. Killing the controller before/after launch yields a recoverable interrupted state with evidence. Timed-out child/MPI processes cannot continue into a retry. Crash tests must not require a real solver.

### C7 — P2: readiness scores convert missing evidence into apparent certainty

`core/runtime/strict_audit.py:20` assigns arbitrary weights; `:59` awards full points for an empty diagnostic list. Mesh checks return no diagnostics when skipped (`core/strict_planning.py:283`), while the audit records `skipped` separately (`strict_audit.py:263`) and still computes `ready` from blocked/warning stages (`:268`). `StrictPlanReport.status` intentionally excludes environment errors (`strict_planning.py:422`, `:458`); launch separately gates them (`runtime/launch_readiness.py:48`). Offline planning is legitimate, but a single `ok` or percentage is insufficient for an agent to infer what was checked. C++ source unavailability is only a warning (`strict_planning.py:231`).

**Decision:** replace percentage readiness as authority with explicit check outcomes: pass, fail, unknown, not applicable, skipped. Retain a human summary if useful, but no score may authorize execution. Report the checked scope, evidence source/version and blind spots. Keep offline planning possible and report launch readiness separately.

**Acceptance:** skipped/source-unavailable checks never claim verified; offline structural planning can pass while launch is blocked. Unknown parser/model coverage is visible and handled by an explicit assurance policy.

### C8 — P2: extension overhead preserves historical defaults rather than a minimal contract

The public interface has 27 required members (`core/plugin_interface.py:507`), many optional probes (`:262`), 24 internal capability seams, and a 568-line compatibility module. The optional phases fallback alphabetically sorts phases (`core/compatibility.py:474`) even though the primary phase order is semantic (`plugin_interface.py:487`). Other absent hooks return unconstrained config (`compatibility.py:106`) or import OpenFOAM readers (`:516`). Only API v2 is supported (`plugin_interface.py:504`), while several adapters still describe v1 fallback behavior. Some comments are stale: optional-hook documentation says fallbacks return cardiac data (`:277`), whereas the compatibility functions inspected no longer do so.

**Decision:** keep narrow capability interfaces where they serve different consumers, but consolidate duplicated authoring requirements into explicit bundles: environment, solver semantics, case materialization and runtime evidence. Capability support must be declared, schema-validated and available for introspection. Remove unreachable v1 compatibility branches after call-site/test census. Move OpenFOAM default composition into the OpenFOAM adapter. Do not add a plugin registry framework merely to replace a small explicit constructor.

**Acceptance:** a neutral environment plugin can implement a minimal useful inspect/plan/execute vertical slice without OpenFOAM fallback imports or dozens of no-op methods. Multi-phase ownership requires explicit order. Existing cardiac behavior remains preserved through a documented adapter/migration.

## Target operation contracts

### Additional independent expert findings retained for implementation

- **C9 — P1, mutations invalidate prior planning:** `cli.py:164` applies overrides after planning and then immediately dispatches the prior step (`:186`). `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py:238` explicitly acknowledges partial mutation if a later override fails. Its raw `system/file:entry` path (`:169`) checks routing syntax without catalog semantic validation. Gate: validate the effective staged case and re-resolve affected plan contracts before atomic commit; failed batches leave the original case unchanged. Preserve numerical exploration through an explicitly uncatalogued/unknown-assurance path, not hidden rejection or implicit validation.
- **C10 — P2, attempt ceiling is not enforced across all dispatches:** `core/runtime/workflow_orchestrator.py:53` documents a total-attempt ceiling, increments attempts at `:64`, but checks the budget only in retry handling (`:92`). Successful steps can exceed the ceiling and zero still permits a first dispatch. Gate: zero budget dispatches nothing; successful and failed attempts both consume budget; document whether it persists across resumes.
- **C11 — P2, common solver failures still require heuristic interpretation:** the runner emits typed diagnostics for timeout/launch failure (`core/runtime/workflow_runner.py:245`), but ordinary nonzero exit leaves diagnostics empty. `runtime/failure_context.py:47` carries text tails, and `runtime/remediation.py:72` eventually returns no hint for unsupported failure. This is an honest fallback, but does not achieve deterministic C++/solver diagnosis. Gate: versioned OpenFOAM events or diagnostic adapter handles known missing-key, runtime-selection, dimension, numerical and convergence errors with stable codes/evidence; unsupported failures remain unknown. Prefer solver-emitted structured events when the solver is under project control.

The independent expert corroborated C1, C2, C4, C5 and C6's timeout/idempotency concern, and contributed C9–C11. The lead independently verified the cited mutation/failure code and retained these items without running a solver. The expert classified C1 P1; the lead elevates it to a P0 release gate specifically because public release as a deterministic resumable framework would otherwise allow stale success. This is a release-priority judgment, not a claim of catastrophic impact on every use.

| Operation | Required deterministic result |
|---|---|
| Inspect | Captured runtime/build identity; supported and unsupported capabilities; raw/effective configuration with source and default origin; evidence coverage |
| Resolve/validate | Immutable resolved case and DAG; explicit check outcomes and scope; machine-readable diagnostics with stable codes and field paths |
| Prepare mutation | Typed patch with precondition input digest, affected files, regeneration consequences, proposed effective configuration and validation result |
| Commit/stage | Atomic application to an owned workspace; materialized input manifest; rollback/recovery record; no execution of a stale patch |
| Execute | Exact resolved plan id, argv, cwd, environment projection, resource limits, trusted executable identity, lease and attempt id |
| Observe | Raw process result; structured adapter events; artifact freshness/completeness; parser confidence; no guessed scientific pass |
| Resume | Identity comparison and reuse/invalidation decision, with explicit reasons; unchanged completed work reused only when its evidence is intact |

Separate a user intent document, a resolved plan and an execution record. The present mutable RunDocument combines desired config, workflow, launch paths, state and results (`core/runtime/run_model.py:31`). Keep an import/export compatibility representation while authoritative internal types become smaller and immutable. A plan should be executable by identity; re-resolving a tutorial name is a different operation and must reveal changed inputs.

Structural validity means the document/DAG is well formed. Semantic validity means declared configuration rules hold under the identified solver/environment. Runtime readiness means the identified executables, files and resources exist and pass the checked preflight. Execution success means the workflow and output contracts completed. Scientific validity requires model-specific verification, validation and convergence evidence. No static planner can prove arbitrary C++ termination, numerical convergence or scientific correctness for every admissible input; support bounded, explicit guarantees and named unknowns.

## Phased roadmap and release gates

1. **Contract baseline and critical integration (core lead; failure/provenance expert).** Land public-entry regression reproductions for C1/C2/C4/C5, then fix context propagation and wire identity checks into execution/resume. Publish an assurance vocabulary and known-gaps ledger. Gate: fake solver lifecycle exercises plan→run→change→refuse/resume through installed distributions, with no stale success.
2. **Resolved plan and mutation transactions (core lead with environment lead).** Introduce immutable plan/input/runtime identities, capability snapshot, patch preconditions, staging ownership, state leases and attempt records. Gate: deterministic normalized plan for identical captured inputs; changed inputs invalidate plan; concurrent/crashed operations cannot corrupt case/state or duplicate a step silently.
3. **Adapter contract simplification (architecture lead with both adapter owners).** Explicit environment/solver bundles; remove unreachable compatibility; unify run/step/RunDocument adapters; preserve an escape path with declared assurance reduction for unsupported inputs. Gate: one neutral toy environment and cardiac plugin both pass the same external conformance suite without ambient package/root dependencies.
4. **Observed execution and scientific evidence (runtime expert with solver experts).** Versioned diagnostic events, conservative fallbacks for legacy logs, fresh artifact validation, safe retry/cancellation, numerical verification criteria. Gate: controlled OpenFOAM/cardiac vertical slices on declared supported installations; failures are typed and attributable; numerical tolerances and reproducibility class are explicit.
5. **Publishability (release lead).** Wheel-only core/OpenFOAM/full-stack matrix on supported Python/runtime versions, runnable examples, migration guide, license decision by owner, version policy and an honest supported-features matrix. Gate: reproducible fresh install and documented end-to-end example using only shipped resources, plus explicit exclusion of unsupported configurations.

Do not make a generalized agent host, generic C++ compiler service, UI, vector database, broad HPC scheduler integration or automatic scientific optimization a prerequisite for the first dependable vertical slice. Those may become separate roadmaps after the contracts prove useful.

## Verification and uncertainties

The parent team ran the non-slow/non-integration suite and both static gates successfully on the existing Python 3.14.3 environment; those results are recorded in the master audit. This team's two in-memory probes confirmed C3 and C4. C1/C2/C5/C6 are production-path inspections and inference from the shown branches, not live solver reproductions. Concurrency, process-tree timeout behavior and public-CLI stale-resume repros remain explicit first-phase verification work. The installed-wheel/support-version matrix was not repeated by this team. No claim here certifies the numerical implementation or parser coverage; those belong to the environment and cardiac teams.
