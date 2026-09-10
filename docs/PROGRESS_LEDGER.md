# Generic core and OpenFOAM adapter progress ledger

Updated: 2026-09-08

**Roadmap review:** [September 8 reassessment](roadmap-audit-2026-09-08.md) audits HEAD `bea21d4` and supersedes the priority order below. The baseline paragraph below identifies the start of the latest implementation batch, not current HEAD.

## Current cardiac reconciliation scope — 2026-09-09

The historical implementation log below is not the current cardiac task list. See [the reconciliation plan](CARDIACFOAM_RECONCILIATION_PLAN.md): T0–T7, T1b, and H1 are complete with recorded source-only, installed-package, reference-run, and exploratory-sweep evidence. The first public experiment interface is complete: it reuses the established sweep runner and exposes inspectable execution, output, and optional checker-report evidence. Generated-output/staging path conventions are now adapter declarations. Remaining work is incremental extraction of other OpenFOAM interpretation, including reconciliation time directories; this does not claim that every package boundary is finished.

Driver tests establish configuration/execution/reporting correctness. Solver regressions retain scientific assertions and are reused by integration tests; broad tutorial-content snapshots do not belong in ordinary Core tests. Preserve manual solver evidence separately from driver-native acceptance.

## Committed baseline

`39c4873 Enforce remediation transaction transitions` is the latest committed
baseline for this follow-up, after `751a117 Harden repair loop evidence and
restart`, `c3298d7 Add bounded agent repair loop`, `16757c5 Recover interrupted
remediation transactions`, `0f50720 Journal agent repairs and bind external
inputs`, and the earlier local ownership and effective-resolution batches.
The pre-existing uncommitted changes under `packages/omnidriver-cardiacfoam/`
were intentionally left untouched.

## Changes made in this batch

- Completed single-run, step, embedded-document, and sweep checkpoints now
  require both matching input provenance and the presence of every required
  predicted artifact before they can be reused. A sweep manifest is only an
  index; a `completed` record with stale input evidence, missing output, a
  missing document/state, or changed routed overrides is invalidated and
  replanned rather than skipped.
- A workflow step now owns a new POSIX process group. Timeout and caller
  cancellation terminate that group; a zero-exit parent with surviving owned
  descendants is failed rather than accepted. Retry attempts remain separate
  log/state attempts, and automatic retry requires the affected step to state
  `retry_policy.safe_to_retry: true` as well as its attempt budget.
- A workflow attempt now holds a host-local output-directory lease for its
  whole orchestration lifetime. A live owner blocks a second attempt; a dead
  same-host PID is recovered, while a remote-host or malformed lease fails
  closed. The process runner recognizes that lease when it is invoked from
  the orchestrator, without weakening direct-step ownership.
- Added solver-free tests for changed inputs, deleted required output, sweep
  reuse validation, timeout/cancellation cleanup, completed-step replay,
  retry-attempt log ownership, and workflow-digest recovery rejection.
- Native dictionary fixtures now distinguish lexical inspection from effective
  OpenFOAM evaluation. They cover comments, quoted strings, nested values,
  multiline lists, dimensions, lists, duplicate keys, includes, and `$`
  substitution. The adapter README records that directive evaluation is an
  explicit execution capability; lexical reads/mutations never execute
  `#calc` or `#codeStream`. Existing rollback tests confirm a failed override
  batch restores all original target bytes.
- `resolve_effective_foam_entry(...)` is an explicit native adapter operation:
  it records the parser/runtime and local dependency closure, resolves safe
  quoted local includes (including declared environment-variable paths), and
  preserves optional-include and declaration-order semantics. It reports
  runtime-dependent include forms or executable directives instead of treating
  them as ordinary parsing.
- The post-commit adversarial audit exposed and closed two local races missed
  by the earlier process/lease tests. Process-group escalation now observes
  the owned group after the direct parent exits, so a child that ignores
  `SIGTERM` is still sent `SIGKILL`. Stale-record inspection and replacement
  are serialized by a stable host-local advisory guard, so a recovering
  contender cannot unlink a newer live owner's record.
- Workflow dispatch now leases the mutable case root as well as its output
  directory, so choosing a different output path cannot bypass local case
  ownership. Sweep case timeouts launch a fresh POSIX session and reuse the
  workflow runner's group-aware `SIGTERM`/`SIGKILL` cleanup rather than
  terminating only the CLI parent.
- CLI resume validation, `step --apply` mutation, native effective-value
  resolution, strict replanning, and dispatch now execute while the same case
  and output leases are held. A changed workflow identity or a native value
  that is unresolved or differs from the requested value blocks dispatch, and
  the resolution evidence is retained in the remediation history.
- `--fresh` now obtains output ownership before clearing an existing output
  directory and preserves its live lease records while clearing contents. A
  different case cannot erase a live owner's output by selecting the same
  output path. Direct step execution also verifies claimed pre-held leases and
  safely acquires whichever of the case/output pair is not already held.
- Effective resolution now follows quoted `#includeEtc` through the selected
  runtime's explicit `FOAM_ETC`, records that external dependency and
  environment key, and has a native v2412 fixture proving the resolved value.
  A separate native `#calc` fixture proves executable evaluation remains gated
  unless the caller explicitly opts in; `#includeFunc` still reports unresolved.
- Agent-proposed edits now create a case-local atomic remediation journal before
  mutation. Its states distinguish `applying`, `accepted`, `rejected`, and
  `rolled_back`; an interrupted transaction always blocks reuse, and a rejected
  candidate requires a new explicit repair. Rejected candidates copy their
  inspected case files into a transaction-specific output archive, while every
  transaction retains a durable record under the output directory. Journal
  transitions flush and `fsync` their file before atomic replacement and also
  `fsync` the containing directory on POSIX.
- The apply document may now carry a hypothesis alongside its override list.
  Transaction records bind that hypothesis and proposal digest to the new plan,
  parent transaction, execution attempt, and outcome, and flag an unchanged
  proposal repeated after failure. This records an agent repair loop without
  changing automatic retry policy or imposing a new experiment limit.
- External files observed by accepted effective-resolution evidence are now
  required provenance inputs. Modifying or removing a selected runtime include
  therefore invalidates resume evidence just like changing an in-case input.
- Before publishing an `applying` transaction, core now requires the plugin to
  declare the complete finite mutation target set and stores byte-for-byte,
  mode-preserving before-images in the transaction output. A plugin with a
  custom mutator but no target-declaration hook fails closed.
- `recover --case-root ... --output-dir ...` restores those exact before-images
  while owning both case and output leases, removes targets that were originally
  absent, and archives the interrupted/rejected candidate first. Backup paths,
  hashes, target confinement, symlinks, transaction identity, and output
  identity are validated before any restoration write occurs.
- The journal reuse gate now covers full workflow runs as well as individual
  steps. A mutator that writes and then raises is recorded as `rejected` unless
  every target still exactly matches its durable baseline; it can no longer be
  mislabeled `rolled_back`. Sequential accepted repairs conservatively retain
  all prior external effective-resolution dependencies.
- A separate repair-loop coordinator now models agent experimentation above the
  workflow retry layer. Each candidate binds a hypothesis and override proposal
  to the exact observation digest that motivated it, reserves its execution slot
  durably before dispatch, and records the resulting observation and remediation
  transaction identity in a loop-specific journal.
- Repair execution count and elapsed-time budgets are explicit and independent
  of `max_total_attempts`. Repeated unchanged failures stop the loop early,
  changed evidence resets that counter, stale proposals fail before execution,
  and agent reasoning is not itself assigned an arbitrary idea limit.
- Repair observations and nested proposals are now strict, canonical JSON
  snapshots rather than mutable caller-owned objects. Journals retain the full
  motivating and resulting evidence alongside each digest, while the
  failure-context adapter excludes volatile attempt numbers and log paths from
  unchanged-failure comparisons.
- Callers may supply a stable repair-loop UUID. Reopening a completed loop is
  idempotent; reopening a loop whose last candidate was durably reserved when
  the process disappeared marks that slot interrupted and requires recovery,
  rather than silently resetting the loop's execution budget.
- Every remediation mutation now requires the current thread to own both the
  canonical case and output leases. Transaction updates use exact
  transaction-ID, revision, and prior-status compare-and-swap checks, so stale
  or duplicate callbacks cannot replace a newer case head. Recovery applies
  the same expected-state check before touching candidate files.
- Configuration lifecycle is now `applying -> validated -> dispatching ->
  accepted/rejected`. Validation alone never makes a candidate reusable;
  `applying`, `validated`, and `dispatching` all block ordinary execution and
  can restore their before-images. Only a recorded successful execution becomes
  accepted, while a failed execution retains and rejects the candidate.
- Lease identity is canonical across relative, absolute, symlink, and macOS
  `/var`/`/private/var` aliases. Repair-loop journals and their nonblocking
  advisory locks live in a stable sibling control directory outside `--fresh`
  cleanup; journals from the earlier output-local location migrate without
  resetting their budgets.
- The CLI-private single-step mutation path is now a structured core executor.
  It acquires case then output ownership, re-observes failure evidence under
  both leases, rejects a stale proposal before snapshot or mutation, applies
  the candidate, resolves its effective configuration, replans, dispatches,
  and records the outcome as one operation. CLI `step --apply` is a JSON/file
  adapter over that executor rather than a second implementation.
- Each repair-loop execution now has a durable UUID reservation. Loop ID,
  execution ordinal, reservation ID, motivating observation digest, proposal
  digest, and remediation transaction ID are checked across the loop journal,
  executor result, case marker, and durable transaction record. Duplicate or
  older callbacks from the same loop fail before replacing the current case
  transaction.
- Candidate result states now have explicit semantics: `succeeded` requires an
  accepted dispatched transaction, `failed` requires a dispatched rejected
  transaction, and `rejected` denotes a pre-dispatch refusal. An unexpected
  executor crash after dispatch admission deliberately leaves the transaction
  in `dispatching`, so restart recovery can identify the interrupted candidate
  instead of treating it as solver evidence.
- One-shot reservation claims live beside the repair-loop journal, outside
  disposable output cleanup. A bound terminal transaction first commits its
  full result and observation to that stable witness, then publishes the case
  head and output mirror. Restart reconciliation reacquires case then output
  ownership and can repair either torn journal copy without overwriting a newer
  transaction, including when another repair loop replaced the case head.

## Verification evidence

| Check | Result |
| --- | --- |
| Focused transaction/fresh/process/lease/effective-resolution tests | `71 passed` |
| Focused remediation-journal, agent-loop, and external-provenance tests | `54 passed` |
| Durable before-image/recovery, dispatch-gate, provenance, and OpenFOAM target tests | `46 passed` |
| Agent repair-loop budget, evidence-lineage, restart, unchanged-failure, and durability tests | `17 passed` |
| Focused lifecycle/CAS/lease-alias/repair-loop/workflow adversarial matrix | `71 passed`; independent re-review `79 passed` |
| Structured executor/reservation/transaction/CLI adversarial matrix | `97 passed`; independent blocker-only re-review found no remaining blocker |
| Adversarial process/lease regression probes added after `7e6ba4c` | `11 passed` |
| Focused case/sweep ownership tests | `41 passed` |
| Explicit native v2412 conformance/effective-resolution + directive-inertness + rollback | `17 passed` |
| OpenFOAM adapter suite | `197 passed, 72 skipped` |
| Core checkout, excluding the slow self-building wheel test | `814 passed, 90 skipped` |
| Isolated core wheel install/import test for this batch | `1 passed` |
| Fresh core wheel | `uv build --wheel` and `check-wheel-artifact.py` succeeded; all `75/75` core modules imported; fresh Python 3.11 wheel suite: `640 passed, 240 skipped` |
| Neutral Python-only plugin without adapters | passed in the fresh core-wheel workflow check; it runs a shell-only case and validates resume/input drift without importing an adapter |
| Import boundaries | passed |
| Capability seam export | passed |
| CardiacFOAM workflow-planning test seam | `3 passed`; the tests now inspect the planned workflow commands, rather than assuming all launches use `subprocess.run`. No solver was launched. |
| Current checkout package suites, run separately | `1778 passed, 263 skipped, 40 subtests passed` |

The native evidence above is specifically from `/Volumes/OpenFOAM-v2412`
using its `foamDictionary` after sourcing `etc/bashrc`. It is not a claim for
other OpenFOAM releases, forks, platforms, or parser versions.

## Remaining limitations and decisions

- The process-group guarantee applies to ordinary POSIX descendants in the
  step's session. A program that intentionally starts a different session is
  outside that ownership boundary.
- The lease is deliberately host-local. Remote-host and malformed lock files
  fail closed rather than guessing that another owner is stale; coordinated
  multi-host recovery needs a durable shared-lock service or an explicit
  operator-mediated recovery protocol. That protocol is deferred while local
  ownership and planning transactions remain incomplete.
- The case/output lease transaction is host-local and prevents concurrent
  writers. Ordinary mutation exceptions roll back target files; a crash or a
  later native-resolution/replanning refusal leaves the candidate clearly
  marked and blocked from reuse until the explicit recovery command restores
  its durable before-images. Recovery covers declared target files, not arbitrary
  undeclared plugin side effects; custom mutators therefore fail closed unless
  they declare their full finite target set.
- Dictionary effective resolution is native v2412 evidence, not a replacement
  for a versioned full evaluator. Function-object include search, generated
  entries, instance/time selection, and executable directives remain explicit
  unresolved/runtime operations. External dependencies are promoted to resume
  evidence after an accepted apply transaction; ordinary non-mutating planning
  does not yet produce the same effective-configuration dependency set.
- The completed cardiacFOAM test-seam adjustment validates the planned
  pre-solve/solver command sequence before generic execution. It is not
  cardiacFOAM runtime evidence: no cardiacFOAM source, build, scientific
  default, equation, unit, or model-compatibility rule was changed.

## Next three priorities

1. Add a stable sibling staging lock and transactional replace protocol for
   managed disposable cases, so crash recovery can safely restage a candidate
   without deleting a live or newly acquired case owner.
2. Add v2412 fixtures for remaining explicit effective-resolution limits,
   including function-object includes, generated entries, and time/instance
   selection, while keeping executable directives opt-in.
3. Connect the repair-loop coordinator to an agent-facing command/API whose
   candidate executor reacquires case/output leases and invokes the existing
   mutation -> effective resolution -> replan -> dispatch transaction. Then
   begin cardiacFOAM integration only with a separately approved native
   runtime/build plan, validating its solver-specific contract without changing
   scientific defaults or compatibility rules.
