# Generic core and OpenFOAM adapter progress ledger

Updated: 2026-09-06

## Committed baseline

`080cc88 Harden core workflow and OpenFOAM evidence` was the starting commit.
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

## Verification evidence

| Check | Result |
| --- | --- |
| Focused lifecycle/process/retry/sweep/lease tests | `72 passed` |
| Explicit native v2412 conformance/effective-resolution + directive-inertness + rollback | `17 passed` |
| OpenFOAM adapter suite | `189 passed, 72 skipped` |
| Core alone, excluding the slow self-building wheel test | `711 passed, 86 skipped, 1 deselected` |
| Fresh core wheel | `uv build --wheel` succeeded; `check-wheel-artifact.py` and the core suite in a fresh temporary venv succeeded |
| Neutral Python-only plugin without adapters | passed in the fresh core-wheel workflow check; it runs a shell-only case and validates resume/input drift without importing an adapter |
| Import boundaries | passed |
| Capability seam export | passed |
| CardiacFOAM workflow-planning test seam | `3 passed`; the tests now inspect the planned workflow commands, rather than assuming all launches use `subprocess.run`. No solver was launched. |
| All packages in an installed temporary environment | `1692 passed, 263 skipped, 1 deselected, 40 subtests passed` |

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
  operator-mediated recovery protocol.
- Dictionary effective resolution is native v2412 evidence, not a replacement
  for a versioned full evaluator. Unsupported include search paths, generated
  entries, environment-dependent substitutions, instance/time selection, and
  executable directives remain explicit unresolved/runtime operations.
- The completed cardiacFOAM test-seam adjustment validates the planned
  pre-solve/solver command sequence before generic execution. It is not
  cardiacFOAM runtime evidence: no cardiacFOAM source, build, scientific
  default, equation, unit, or model-compatibility rule was changed.

## Next three priorities

1. Add v2412 fixtures for the remaining explicit effective-resolution limits
   (include search paths, generated entries, and time/instance selection),
   keeping executable directives opt-in.
2. Design a deliberate multi-host lease/recovery protocol; retain the current
   fail-closed behavior until that ownership authority exists.
3. Begin cardiacFOAM integration only with a separately approved native
   runtime/build plan, then validate its solver-specific contract without
   changing scientific defaults or compatibility rules.
