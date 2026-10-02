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
3. Propose a finite set of `document:key` patches, the same a study takes, and
   run `omnidriver step --run-document ... --apply patches.json`.
4. The executor acquires case/output leases, commits the patches through the
   case writer (one journaled `commit_case_write`), replans, and only then
   dispatches the utility step. Each attempt is appended to
   `remediation_history.jsonl`.
5. The result lists `applied_patches`. A commit that fails rolls back to the
   original bytes; one interrupted by a crash blocks the case until
   `omnidriver recover` restores it.

The plugin's record validator accepts or refuses each key by name, and its
renderer may reject an invalid value by raising `ValueError`: a refusal at
that stage never writes and never dispatches. A later replan rejection leaves
the committed edit in the case, says so, and never dispatches.

## Executable proof

The patch slice is exercised end to end over the conformance toy in
`packages/omnidriver/tests/core/test_cli_step.py` and, on each solver's real
case, by the `test_step_apply_native.py` of its package.
