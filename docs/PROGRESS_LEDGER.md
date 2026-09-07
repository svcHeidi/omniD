# Generic core and OpenFOAM adapter progress ledger

Updated: 2026-09-07

## Committed baseline

`d9d947e Own case roots and sweep process groups` is the latest committed
baseline for this follow-up, after `cf097b3 Close local lease and process
cleanup races` and `7e6ba4c Harden workflow lifecycle and OpenFOAM resolution`.
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

## Verification evidence

| Check | Result |
| --- | --- |
| Focused transaction/fresh/process/lease/effective-resolution tests | `71 passed` |
| Adversarial process/lease regression probes added after `7e6ba4c` | `11 passed` |
| Focused case/sweep ownership tests | `41 passed` |
| Explicit native v2412 conformance/effective-resolution + directive-inertness + rollback | `17 passed` |
| OpenFOAM adapter suite | `192 passed, 72 skipped` |
| Core checkout, excluding the slow self-building wheel test | `748 passed, 90 skipped, 1 deselected` |
| Fresh core wheel | `uv build --wheel` and `check-wheel-artifact.py` succeeded; fresh Python 3.11 wheel suite: `598 passed, 240 skipped, 1 deselected` |
| Neutral Python-only plugin without adapters | passed in the fresh core-wheel workflow check; it runs a shell-only case and validates resume/input drift without importing an adapter |
| Import boundaries | passed |
| Capability seam export | passed |
| CardiacFOAM workflow-planning test seam | `3 passed`; the tests now inspect the planned workflow commands, rather than assuming all launches use `subprocess.run`. No solver was launched. |
| Current checkout package suites, run separately | `1707 passed, 263 skipped, 1 deselected, 40 subtests passed` |

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
  writers, but it is not yet a crash-recoverable multi-file patch transaction.
  A mutation failure rolls back its target files; a later native-resolution or
  replanning refusal is audited but can leave the already-applied edit in the
  isolated execution case for operator inspection.
- Dictionary effective resolution is native v2412 evidence, not a replacement
  for a versioned full evaluator. Unsupported include search paths, generated
  entries, environment-dependent substitutions, instance/time selection, and
  executable directives remain explicit unresolved/runtime operations. The
  post-mutation evidence records inspected dependencies, but dependencies
  outside the case are not yet promoted into the resumable provenance snapshot.
- The completed cardiacFOAM test-seam adjustment validates the planned
  pre-solve/solver command sequence before generic execution. It is not
  cardiacFOAM runtime evidence: no cardiacFOAM source, build, scientific
  default, equation, unit, or model-compatibility rule was changed.

## Next three priorities

1. Turn the owned apply sequence into a journaled or staged patch commit so a
   native-resolution/replanning refusal and a crash cannot leave a partially
   accepted case; promote inspected external dependencies into resume evidence.
2. Add v2412 fixtures for remaining explicit effective-resolution limits,
   including include search paths, generated entries, and time/instance
   selection, while keeping executable directives opt-in.
3. Begin cardiacFOAM integration only with a separately approved native
   runtime/build plan, then validate its solver-specific contract without
   changing scientific defaults or compatibility rules.
