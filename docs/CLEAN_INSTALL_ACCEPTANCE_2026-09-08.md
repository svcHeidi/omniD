# Clean-install acceptance — 2026-09-08

This records the small declared support slice exercised from freshly built
`omnidriver` and `omnidriver-openfoam` wheels in a disposable Python 3.11
environment. It uses the public CLI with `--plugin none`; no cardiacFOAM
package, repository test plugin, or Python API composition participates in
the workflow.

## Public workflow results

- A utility-only `Allrun` planned and ran successfully. Its absent external
  `#includeIfPresent` was recorded as a verified absence. A second unchanged
  `run --strict` resumed successfully; creating that include then produced a
  stale-evidence refusal naming the `effective_config:` witness.
- A malformed `#includeFunc` produced a failed normal plan (exit 1). The same
  case ran only with `--allow-unresolved-configuration`; that plan/result
  records `configuration_evidence_policy: exploratory` and the affected
  dictionary.
- A public `--run-document` utility step with `timeout_s: 1` was terminated
  on its first attempt. Its declared safe retry completed attempt 2 without
  changing any consumed input. The final result was `ok` and retained the
  attempt-2 log paths.
- A utility script wrote 5,000 diagnostic lines (103,893 bytes) and exited
  7. With `--tail-lines 20`, the JSON failure response was 5,869 bytes and
  carried the exit code, log paths, `stdout_truncated: true`, and exactly the
  final 20 lines. This is the bounded diagnostic contract a smaller model can
  consume without loading the full log. No behavioural benchmark against a
  particular smaller model was run in this acceptance environment.

## Storage measurements

All sizes below are byte sums of regular files under the attempt's
`postProcessing/` directory; lock files are zero bytes.

| Scenario | Attempts | Attempt files | Snapshot payload | CLI response |
| --- | ---: | ---: | ---: | ---: |
| utility success / unchanged absence | 1 | 4,003 B | 1,703 B | 5,359 B first; 4,979 B resumed |
| timeout then safe retry | 2 | 3,735 B | 1,436 B | 4,994 B final |
| noisy failed utility | 1 | 107,450 B | not duplicated | 5,869 B |

The timeout/retry attempt has one persisted `workflow_state.json` (2,758 B),
not one copy per retry. Its four attempt log files are empty in this fixture.
The noisy fixture's 103,893-byte stdout log dominates its 107,450-byte
attempt footprint; the persisted state is 2,736 B. This makes the intended
storage split explicit: bounded agent responses and state are small, while
solver/utility logs remain the data-bearing output.

## Large-case inventory

The workspace contains no 23 GB case. The closest matching checkout is
`/Users/simaocastro/cardiacFoamEPsacred/cardiacFoamsacred`, approximately
204 GiB. Nearly all of it is tutorial output:

- `tutorials/HeartPurkinje_MonopECG/HeartPurkinje`: about 127 GiB, including
  six `processor0`–`processor5` trees of roughly 19–20 GiB each.
- `tutorials/HeartPurkinje_MonopECG/HeartPurkinje_images`: about 47.7 GiB,
  dominated by time-indexed images/VTK output and six roughly 2 GiB processor
  trees.
- `HeartPurkinje/postProcessing`: about 6.6 GiB, including a 1.4 GiB
  `purkinjeNetwork.dat` and VTK collections.

These are generated field, image, processor and post-processing artifacts,
not a single required input. CardiacFOAM integration should therefore use a
manifested input subset and a separate output location; it must not copy or
content-hash the whole historical tutorial tree on every attempt.
