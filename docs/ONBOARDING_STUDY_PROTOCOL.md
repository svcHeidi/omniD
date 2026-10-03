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

## Unit of evidence

One record per plan or execution attempt, with:

- source commit and a dirty-tree statement;
- plugin package version and capability identity;
- OpenFOAM/runtime identity;
- source case, staged case, declared inputs, and workflow digest;
- command outcome, required artifact outcome, and any native checker result;
- reason for a failure, repair, retry, or refusal.

The OmniD `run_document.json`, `workflow_state.json`, staged inputs, logs, and
produced artifacts are primary evidence.  A study ledger indexes them; it does
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

## Positioning references to develop

- FAIR workflow recommendations: Wilkinson et al., *Scientific Data* (2025),
  https://doi.org/10.1038/s41597-025-04451-9.
- Reproducibility tenets for computational workflows: de Paula Kinoshita et
  al., *Future Generation Computer Systems* (2025),
  https://doi.org/10.1016/j.future.2024.107684.
- OpenFOAM testing practice: Jørgensen et al., *OpenFOAM Journal* (2025),
  https://journal.openfoam.com/index.php/ofj/article/view/134.
