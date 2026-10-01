# Neutral utility repair workflow

This is the smallest supported agent workflow. It uses no cardiacFOAM model
or solver: the case's `Allrun` only checks a repaired input and writes a
utility report. The same ownership, planning, transaction, provenance and
recovery boundaries apply to a solver workflow.

## Case contract

The agent first calls `strict_plan(...)` with its selected `DriverContext`.
The report is non-mutating and includes `configuration_evidence`; external
dictionary includes and their optional-absence witnesses are part of the
subsequent checkpoint identity. A utility-only `Allrun` can be as small as:

```sh
#!/bin/sh
set -eu
test "$(tr -d '\n' < config)" = 2
mkdir -p postProcessing
printf repaired > postProcessing/utility-report.txt
```

Normal planning requires every declared configuration record to be
`inspected`. `unresolved`, `execution_required`, and `runtime_unavailable`
records fail the plan and therefore block dispatch. An operator can request
`--allow-unresolved-configuration` (or
`allow_unresolved_configuration=True`) only for an explicitly exploratory
run; the report and its RunDocument intent then carry the `exploratory`
policy and the affected dictionary paths. Unknown evidence statuses always
block. A verified absent `#includeIfPresent` is complete resume evidence:
unchanged absence can resume, while the file appearing invalidates the
checkpoint.

For a native OpenFOAM utility case, replace the check with the declared
utility invocation (for example `foamDictionary system/controlDict -entry
endTime -value`). Keep it in the normal workflow DAG; do not shell out from
an agent callback.

## Agent sequence

1. Inspect and plan the case. Do not edit it while planning.
2. Execute the planned step. A failure report carries `failure_context`.
3. Propose a finite, catalog-addressable override list and run
   `omnidriver step ... --apply overrides.json`; the file may carry a
   `hypothesis` beside the `overrides`.
4. The executor acquires case/output leases, persists before-images, applies
   the override, checks effective configuration when the plugin supplies it,
   replans, and only then dispatches the utility step.
5. The result names the remediation transaction. An accepted transaction is
   the case head; a rejected or interrupted one blocks reuse of the case
   until it is restored or restaged.

The adapter must declare every target through
`get_override_target_paths(...)`; its `apply_overrides(...)` may reject an
invalid proposal by raising `ValueError`. A mutation-time rejection restores
declared before-images and never dispatches. A later replan rejection leaves
a clearly marked candidate that must go through the durable recovery path;
it is never silently reused.

## Executable proof

`packages/omnidriver/tests/core/test_core_generic_case.py` proves neutral
read-only planning and configuration closure inspection. The utility patch
slice is exercised with a real `Allrun` subprocess in
`packages/omnidriver/tests/core/test_step_candidate.py`:

- `test_neutral_utility_workflow_patches_and_dispatches_a_declared_case_script` —
  successful patch/replan/dispatch and durable acceptance.
- `test_changed_plan_rejects_written_candidate_before_dispatch` — a
  post-write replan rejection leaves a marked candidate and never dispatches.
- `test_unowned_execution_never_starts_a_transaction` — without both leases
  nothing is written.

Run the focused proof with:

```sh
.venv/bin/python -m pytest \
  packages/omnidriver/tests/core/test_core_generic_case.py \
  packages/omnidriver/tests/core/test_step_candidate.py -q
```

This is a local, host-owned workflow. It does not claim distributed locking,
loader-complete library attestation, or cardiacFOAM scientific validity.
