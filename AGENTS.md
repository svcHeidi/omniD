# OmniD agent router

This is the provider-neutral entry point for an agent working in OmniD. Read
it before planning a change or run. It does not assume that a provider reads
files automatically: an agent launcher must inject this file and the selected
documents from `agent-handbook/guidance-manifest.yaml`.
When implementing such a launcher, also read
[`agent-handbook/provider-integration.md`](agent-handbook/provider-integration.md).

## Choose one role

- **Builder:** onboard or extend a solver adapter, its catalogs, workflows, or
  result interpretation.
- **Runner:** plan or execute an already-supported experiment.
- **Evaluator:** compare agents or guidance revisions on a held-out task.
- **Maintainer:** change OmniD implementation without expanding a solver's
  scientific support boundary.

Load the required reading for that role from
[`agent-handbook/guidance-manifest.yaml`](agent-handbook/guidance-manifest.yaml).
Do not load every document by default.

## Non-negotiable boundary

Native cases, dictionaries, command help, runtime observations, and available
source establish mechanical facts. Model choice, physical meaning and units,
accepted workflow combinations, scientific acceptance criteria, and an
algorithm implemented outside the native solver require domain evidence or a
user decision. Record an unresolved boundary; do not fill it with a plausible
guess.

Solver-specific behavior belongs in that solver's adapter and tests. Core
changes require a reproduced orchestration defect, not a desire for a more
general abstraction.
