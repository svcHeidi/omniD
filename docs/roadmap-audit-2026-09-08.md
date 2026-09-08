# Roadmap reassessment — 2026-09-08

Audited core/OpenFOAM HEAD `bea21d4`. CardiacFOAM working-tree changes were excluded and left untouched. This is a focused source/test audit, not full release certification. The September 5 roadmap remains the product design; its implementation findings are historical.

## What is now implemented

- Local case/output ownership, process-group cleanup, retry safety policy, and stale checkpoint/output checks.
- Journaled finite-target edits, durable before-images, explicit recovery, canonical lease identities, and transaction ID/revision/status checks.
- Separate applying, validated, dispatching, and terminal transaction states.
- Structured step-candidate executor shared with CLI mutation execution; repair reservations bind proposals, observations, transactions and outcomes. Durable witnesses support restart reconciliation.
- Native v2412 dictionary fixtures and effective resolution for the supported subset. External inspected files from accepted repairs feed resume provenance.

These close the previously reproduced transaction defects. They do not establish complete effective-configuration identity for an untouched case or scientific solver validity.

## Remaining priorities and acceptance gates

1. **Protect disposable case replacement.** `core/runtime/sweep_runner.py::_stage_entry_case` still removes an existing directory with `shutil.rmtree` before copying. Introduce stable ownership outside the replaceable directory and a supported staging/promotion protocol. Test concurrent staging versus execution, interruption during copy/promotion, and source preservation. A live case must never be removed; an incomplete copy must never become executable. Define host-local filesystem limits instead of promising arbitrary multi-file atomicity.

2. **Unify configuration evidence across ordinary planning and repairs.** `apply_overrides.py` is the native resolver's current production caller. `provenance_inputs.py` imports external effective dependencies through accepted remediation history. Add an adapter-owned inspect/resolve contract for untouched cases, consumed generically by core. Test that an external include affects plan/dispatch/resume identity without any prior repair, while inspection leaves case bytes unchanged.

   Record absent optional includes as absence evidence: `_inspect_source_closure` currently skips them, so appearance of an external optional include is not covered by inspected-file provenance. Bind the actual configuration evaluator executable/runtime identity, not only a parser label and installation path. Preserve explicit unresolved states for unsupported syntax.

3. **Complete semantic identity proportionately.** `DriverContext` still assigns `capability_digest=profile.digest`; large files above 256 MiB still use metadata evidence and cannot establish complete content identity. Bind resolved contracts and required executable/configuration dependencies to the plan. Add streaming hashing for required large inputs with measured cost. Do not imply loader-complete library attestation without implementing it.

4. **Prove the user-facing vertical slice.** The structured executor and repair coordinator now exist; do not rebuild them. Supply a thin documented adapter/example that composes observation, proposal, reservation, execution and recovery. Use a neutral plugin and an OpenFOAM utility-only case. Include success, stale proposal, rejected configuration, changed external input, interrupted dispatch and successful recovery. Acceptance is one reproducible clean-install walkthrough with structured results, without cardiacFOAM or undocumented internal glue.

5. **Refresh package/release evidence at the final revision.** Run required all-package, isolated-core, fresh-wheel and static gates, plus explicit native v2412 conformance. Add adapter artifact coverage and required-native-test reporting. Keep scientific/native cardiac tests deferred and distinguish skipped coverage from passing evidence.

## Scope decisions

Retain the two logical layers and three package ownership boundaries. No wholesale rewrite, general C++ semantic engine, distributed lease service, or resident agent platform is justified by this audit. Broader OpenFOAM syntax support can follow the first declared conformance profile; unsupported forms must be explicit. CardiacFOAM scientific integration remains a separate gate.

The progress ledger's baseline and next-priority list lag HEAD: the executor has already been extracted, although a public end-to-end integration example is still needed. `GITHUB_MIGRATION.md`'s September 4 statement that cardiac integration is the only remaining unknown is historical and does not describe current core acceptance work.

## Verification performed in this audit

- Repair-loop, remediation transaction and execution-transaction suites: **55 passed**.
- Structured step-candidate executor suite: **11 passed**.
- Native/effective dictionary, apply-resolution and dictionary conformance suites: **21 passed**, no skips, using the local v2412 volume.
- Import boundaries, generated capability seams and initial whitespace checks passed.
- An independent low-reasoning agent reviewed ordinary planning/effective-dependency gaps; root reviewed lifecycle, staging and roadmap status.
- No cardiacFOAM run or implementation change. Full-suite and wheel numbers in the progress ledger were not independently rerun here.
