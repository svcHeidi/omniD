# OmniD solver-onboarding study protocol

## Status

Prospective methods study.  The protocol was created before semantic
implementation of the cardiacCoreStandalone OmniD adapter and is now being
used to record its first native vertical slice.

## Working question

Can an OpenFOAM solver or utility workflow be exposed as a reproducible,
inspectable experiment interface from its available native evidence (cases,
dictionaries, documentation, APIs, controlled runs, and source when
available)--without importing a pre-existing machine-readable catalog or study
configuration?

## Working contribution

OmniD separates a native case's execution from a plugin's supported scientific
interface.  A plugin declares only evidence-backed commands, configuration
entries, tutorial materialization rules, artifacts, metrics, and sweep axes.
The resulting plan binds those declarations to staged inputs and execution
evidence.  [The builder evidence contract](BUILDER_AGENT_EVIDENCE_CONTRACT.md)
defines how source access strengthens, but never gates, those declarations.

The paper must not claim that arbitrary OpenFOAM solvers are automatically
understood, that every dictionary key is safely mutable, or that workflow
completion establishes scientific validity.

## Research questions

1. Can a new adapter progress from a generic case to one real native vertical
   slice with explicit, testable declarations?
2. Does evidence-led onboarding expose configuration and workflow errors
   before a solver launch, with source inspection used only when available?
3. Do staged execution, provenance, and artifact contracts preserve the
   evidence needed to reproduce a reported experiment?
4. What manual curation is required to expose a useful user-facing set of
   parameters (x axes) and result metrics (y values)?

## Study cases

| ID | Role | Evidence source | Status |
| --- | --- | --- | --- |
| CF-1 | Mature adapter reference: cardiacFOAM tutorial experiments | Native tutorials, OmniD plans/runs, solver-owned checkers | Completed baseline |
| CC-1 | Source-only onboarding case: cardiacCoreStandalone `bivCase` | Native `Allrun`, dictionaries, source utilities, README, named local asset case | Native vertical slice completed with a separately staged local asset bundle; clean-clone asset-distribution closure pending |
| S-3 | Non-cardiac OpenFOAM solver/workflow | To be selected before a generality claim | Required for broad claim |

`CC-1` is a clean committed snapshot at
`/private/tmp/omnidriver-experiments/cardiaccore-omnidriver-onboarding-source`.
Its previous agent catalog, schema, intent, and pipeline JSON files are
excluded from implementation input.  Native case data such as
`electrodePositions.json` remains available.

## Unit of evidence

One record per plan or execution attempt, with:

- source commit and a dirty-tree statement;
- plugin package version and capability identity;
- OpenFOAM/runtime identity;
- source case, staged case, declared inputs, and workflow digest;
- command outcome, required artifact outcome, and any native checker result;
- reason for a failure, repair, retry, or refusal.

The OmniD `run_document.json`, `workflow_state.json`, staged inputs, logs, and
produced artifacts are primary evidence.  This ledger indexes them; it does
not replace them.

## Acceptance levels

1. **Generic contract:** clean installation, plugin discovery, generic strict
   plan, controlled marker `Allrun`, and explicit refusal of unsupported
   semantic operations.
2. **Native vertical slice:** one tutorial/case has source-backed commands,
   required dictionaries, predicted artifacts, strict plan, staged execution,
   and native result check where one exists.
3. **Experiment interface:** each advertised x axis has a valid mutation and
   each advertised y metric has an explicit artifact/reader contract.
4. **Generality:** repeat level 2 on an independent non-cardiac OpenFOAM
   workflow.  Two cardiac codebases alone support a case-study claim, not a
   general OpenFOAM claim.

## Reporting measures

- Number of source-backed exposed commands, configuration entries, artifacts,
  x axes, and y metrics.
- Catalog coverage against the selected native vertical slice, not against all
  source files.
- Plan/refusal/runtime/checker outcomes and time-to-diagnosis for each defect.
- Provenance completeness: source, runtime, configuration, workflow, input,
  and output evidence available for each completed result.
- If external users participate: task completion, time, errors, and ability to
  explain the selected configuration and output.  Without participants, do
  not claim measured usability.

## Initial evidence ledger

| ID | Date | Case | Intervention | Outcome | Evidence |
| --- | --- | --- | --- | --- | --- |
| CF-1.1 | 2026-09-14 | cardiacFOAM coupled 1D-3D | Scoped stale `rPvj` / `couplingMode` overrides | Three authored four-point sweeps completed | `/private/tmp/omnidriver-experiments/paper-repro-coupled-*-run/` |
| CC-1.0 | 2026-09-14 | cardiacCoreStandalone | Created committed, JSON-stripped source-only fixture | Ready for generic onboarding gate | Fixture path above |
| CC-1.1 | 2026-09-14 | cardiacCore standalone adapter | Implemented neutral OmniD API-v2 scaffold; tested a controlled marker `Allrun` | Contract and controlled execution passed (2 tests); wheel-build gate blocked because the prepared interpreter has no importable setuptools backend and network installation is unavailable | `/private/tmp/omnidriver-experiments/omnidriver-cardiaccore-plugin/` |
| CC-1.2 | 2026-09-14 | cardiacCore `bivCase` | Built tracked utilities; declared the native four-stage wrapper, its inputs, and its generated fields in the out-of-tree adapter | Strict plan was 100% ready; a clean staged run completed each utility once; 8 required fields reconciled, while two paired conductivity fields were correctly optional and absent | `cardiacCoreStandalone@7ebf126`, `cases/bivCase/Allrun`, `/private/tmp/omnidriver-experiments/cardiaccore-biv-preprocessing-provenance-run/bivCase/` |
| CC-1.3 | 2026-09-14 | cardiacCore `bivCase` provenance | Reclassified generated utility fields from the adapter's utility manifests, preserving the explicitly consumed intermediate `0/Conductivity` | Fresh staged rerun completed; final resume provenance excludes generated anatomy/Purkinje fields and retains only the declared intermediate dependency | Adapter tests (4 passed) and `workflow_state.json` in the CC-1.2 staged case |
| CC-1.4 | 2026-09-14 | cardiacCore `bivCase` input catalog | Reused OmniD's existing OpenFOAM dictionary catalog/read infrastructure; published 12 reviewed x values from the four authored dictionaries and separated unexercised conditional branches | Adapter tests (5 passed); public `describe` exposes the four document groups and the separate conditional-input catalog. No mutation interface was enabled yet | `/private/tmp/omnidriver-experiments/omnidriver-cardiaccore-plugin/`, `/private/tmp/omnidriver-experiments/cardiaccore-describe.json` |
| CC-1.5 | 2026-09-14 | cardiacCore cross-solver conditions | Owner clarified the semantic roles of conditional branches: manual AHA segmentation, pig Purkinje morphometry, and bidomain tensors | Conditions remain unvalidated against a consuming cardiacFoam solver until that solver/workflow is supplied; the builder contract now requires an explicit producer-to-consumer closure pass | [BUILDER_AGENT_EVIDENCE_CONTRACT.md](BUILDER_AGENT_EVIDENCE_CONTRACT.md) |
| CC-1.6 | 2026-09-14 | cardiacCore `bivCase` JSON interface | Implemented `input_overrides`: a validated run/sweep JSON maps the 12 reviewed x values to the four native dictionaries in a disposable case; added the adapter-owned `preprocessing` configuration phase and RunDocument reader | Normal JSON run with `thickness=0.05` completed all four utilities. A two-value sweep strictly planned both staged cases. Sweep execution is pending installed-plugin discovery: an uninstalled `PYTHONPATH` adapter cannot be rediscovered by the sweep's child process. | `/private/tmp/omnidriver-experiments/cardiaccore-json-runtime-run/bivCase/`, `/private/tmp/omnidriver-experiments/cardiaccore-json-sweep-plan/` |
| CC-1.7 | 2026-09-14 | cardiacCore clean-user asset closure | Staged only mesh and raw input fields from the separately named `cardiacCore-local-cases/bivCase_Pig_Morphometric_Tree` into the clean `bivCase` source fixture; retained the source dictionaries and workflow | The adapter completed all four preprocessing utilities with the JSON slab-thickness override (`0.05`); the eight expected generated fields were present. This validates the external asset interface. A distributed canonical asset bundle or declared native generator remains required for a clone-and-run claim. | `/private/tmp/omnidriver-experiments/cardiaccore-local-asset-run.idJ6BG/bivCase/workflow_state.json`, [BUILDER_AGENT_EVIDENCE_CONTRACT.md](BUILDER_AGENT_EVIDENCE_CONTRACT.md) |
| CC-1.8 | 2026-09-15 | cardiacCore capability comparison | Compared the original user-authored agent contracts, catalogs, variant intents, and checks to the tested four-utility OmniD adapter | The current adapter covers fibre/sheet conductivity, AHA outputs, slab, and morphometry. The next required vertical slice is explicit Purkinje-tree generation with anatomy-portable seeds, density/coverage checks, and later graph hand-off. Scar and VTK import are separate workflows. | [CARDIACCORE_CAPABILITY_COMPARISON.md](CARDIACCORE_CAPABILITY_COMPARISON.md) |
| CC-1.9 | 2026-09-15 | cardiacCore package integration | Moved the tested adapter from the temporary experiment package to `packages/omnidriver-cardiaccore/` using the repository's `omnidriver.cardiaccore` namespace | Package and Core regression tests passed (10 tests). Editable install and entry-point discovery remain blocked in the prepared virtual environment because it lacks `setuptools` and cannot access PyPI; this is recorded without bypassing package installation. | `packages/omnidriver-cardiaccore/`, local package test output |
| CC-1.10 | 2026-09-15 | cardiacCore explicit Purkinje trees | Declared and executed named human endocardial and pig morphometric/transmural workflows. The pig path declares its morphometry weight fields as generator dependencies; both run the generator from the staged case CWD. | Both fresh staged OmniD runs completed: human 3 stages and pig 4 stages. All declared face sets, VTKs, parameter file, per-step logs, and resume evidence were recorded. Tree seed/growth configuration remains fixed pending validation/coverage criteria. | `/private/tmp/omnidriver-experiments/cardiaccore-human-tree-omnid.OSzvX3/bivCase/workflow_state.json`, `/private/tmp/omnidriver-experiments/cardiaccore-pig-morphometric-omnid.d5S2HV/bivCase/workflow_state.json` |

## Positioning references to develop

- FAIR workflow recommendations: Wilkinson et al., *Scientific Data* (2025),
  https://doi.org/10.1038/s41597-025-04451-9.
- Reproducibility tenets for computational workflows: de Paula Kinoshita et
  al., *Future Generation Computer Systems* (2025),
  https://doi.org/10.1016/j.future.2024.107684.
- OpenFOAM testing practice: Jørgensen et al., *OpenFOAM Journal* (2025),
  https://journal.openfoam.com/index.php/ofj/article/view/134.
