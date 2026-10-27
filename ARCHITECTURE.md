# OmniDriver architecture

This repository is **OmniDriver**: a solver-agnostic workflow engine in six packages, one per concern; a seventh, `omnidriver-agents`, that measures agents driving it through the CLI and imports none of them; and an eighth, `omnidriver-verifier`, that holds manufactured problems as data and checks them, depending on core only.

## Monorepo and namespace packages
The engine gives an agent deterministic access to simulation solvers (OpenFOAM-based, openCARP and TorchCor today), their environments and the machines they run on. What the agent does with that access (benchmarking, comparing solvers, improving one) is the agent's reasoning, not omniD's.

The project is a **Monorepo** paired with Python **Namespace Packages** (PEP 420). All the code lives in one GitHub repository, published as eight decoupled `pip` packages.

### Directory Structure & Import Semantics
No package's `src/omnidriver/` holds an `__init__.py`, so Python treats it as a namespace: each package installs on its own and imports as `omnidriver.<package>`.

```text
omnidriver/ (GitHub Root)
├── packages/
│   ├── omnidriver/                  (import omnidriver.core)
│   │   └── src/omnidriver/
│   │       ├── cli.py               <-- The `omnidriver` command; every refusal in one JSON
│   │       │                            shape (core/refusal.py lists its codes)
│   │       ├── conformance/         <-- C1-C14, the executable definition of "a solver can
│   │       │                            plug in" (`omnidriver check`), and what a target supplies
│   │       ├── schemas/             <-- run document, point reference, comparison report
│   │       └── core/                <-- Plugin contract, provider stack, records, planning
│   │           ├── runtime/         <-- Execution: run documents, steps, sweeps, provenance,
│   │           │                        resume, MPI, the record surface `describe` shows
│   │           ├── quantities/      <-- Solver-neutral results-as-quantities: Quantity,
│   │           │                        units, sentinels, the reader contract, comparison
│   │           └── runtime_records.py <-- Core's own run-record filenames, declared once
│   │                                    (workflow_state.json, run_document.json, ...)
│   │
│   ├── omnidriver-openfoam/         (import omnidriver.openfoam)
│   │   └── src/omnidriver/openfoam/ <-- Translates core requests into OpenFOAM
│   │
│   ├── omnidriver-cardiacfoam/          (import omnidriver.cardiacfoam)
│   │   └── src/omnidriver/cardiacfoam/  <-- Cardiac physics and logic
│   │       └── physics_layout.py/.json  <-- Which region(s) a case's physics type
│   │                                        declares, one row per type
│   │
│   ├── omnidriver-cardiacsubstrate/          (import omnidriver.cardiacsubstrate)
│   │   └── src/omnidriver/cardiacsubstrate/  <-- Cardiac preprocessing adapter; sibling to
│   │                                         cardiacfoam, not a dependent of it (Rule 4)
│   │
│   ├── omnidriver-opencarp/             (import omnidriver.opencarp)
│   │   └── src/omnidriver/opencarp/     <-- openCARP adapter; depends on core only (Rule 5)
│   │
│   ├── omnidriver-torchcor/             (import omnidriver.torchcor)
│   │   └── src/omnidriver/torchcor/     <-- TorchCor adapter; depends on core only (Rule 5)
│   │
│   ├── omnidriver-verifier/             (import omnidriver.verifier)
│   │   └── src/omnidriver/verifier/     <-- Manufactured problems as data and their checks
│   │                                        (`omnidriver-verify`); depends on core only (Rule 6)
│   │
│   └── omnidriver-agents/               (import omnidriver_agents; not in the namespace)
│       └── src/omnidriver_agents/       <-- Agent harness: runs a task under agent CLIs, with
│                                             and without omniD, through the CLI only (Rule 7)
│
├── benchmarks/                      <-- Published, solver-neutral reference definitions
│                                        (e.g. niederer2011.json); scripts/check-benchmark-
│                                        references.py gates them
```

### Architectural Rules
1. **Core Independence:** `omnidriver.core` MUST NOT import anything from `openfoam` or `cardiac`. It must contain **zero** physics rules and **zero** OpenFOAM vocabulary.
2. **Environment Boundary:** `omnidriver.openfoam` depends on `omnidriver.core`, but knows nothing about specific physics.
3. **Domain Implementation:** `omnidriver.cardiacfoam` depends on both.
4. **Sibling adapters:** `omnidriver.cardiacsubstrate` also depends on core and
   openfoam, and MUST NOT import `omnidriver.cardiacfoam` (nor the reverse).
   The two cardiac adapters are siblings; what passes between them is declared
   and mediated, not imported.
5. **Independent adapters:** `omnidriver.opencarp` and `omnidriver.torchcor`
   depend on core only and MUST NOT import `omnidriver.openfoam`, either
   cardiac adapter or each other, nor may any of them import either.
6. **The verifier:** `omnidriver.verifier` imports only core's refusal shape.
   It reaches no solver: it judges the results an agent hands it as JSON
   against a problem's exact solution. No other package imports it, so no
   plugin depends on the checks that judge it.
7. **The harness stays outside:** `omnidriver_agents` imports nothing from
   `omnidriver`, and nothing under `omnidriver` imports it; it measures omniD
   through the `omnidriver` command and its JSON.
   `scripts/check-import-boundaries.py` enforces all seven rules.

## Verification

`CLAUDE.md` holds the commands and what each shape catches (all packages, core
alone, core from a built wheel, the static gates). The durable claim is
`0 failed`; a test count is a fact about the moment it was taken.

## Rule 1 in practice

Rule 1's second sentence is not "core names no OpenFOAM word". `Allrun`,
`system/controlDict` and `$FOAM_APPBIN` are one environment's bindings of
concepts core legitimately owns, and core owns the concept, not its spelling.
The checkable rule: core may name a binding only where it is reached through a
declared role, a provider member or a documented, overridable default; a
hardcoded string with no declaration path is a defect. `scripts/check-core-shape.py`
fails on any OpenFOAM layout token in core (its baseline,
`scripts/core-shape-baseline.txt`, is empty and may only shrink), and
`scripts/check-openfoam-shape.py` does the same for cardiac vocabulary in the
OpenFOAM layer; `scripts/check-import-boundaries.py` enforces the import
directions above.

## Provider composition

A plugin is a stack of providers: a solver plugin layered on the environment
it `requires:` (cardiacFOAM and cardiacSubstrateFOAM on the OpenFOAM layer), or one
provider on its own (openCARP). `provider_stack.order_providers` orders them
least specific first from their profiles' `requires:`, refusing an unmet
requirement or a cycle, stably, since the stack digest hashes the order.

The contract is `SolverPlugin` in `core/plugin_interface.py`. Only a
provider's four identity properties are required; every other member is
optional. `provider_stack.MEMBERS` is the one table of the contract: for each
member, how a stack composes the providers that implement it, and what the
stack answers when none does. Core reaches every member through
`driver_context.stack.call(member, ...)`, and hands every member that may
need what the context carries (the solver repository, the stack itself)
that context as the keyword `driver_context`: the plan and environment
diagnostics, step-failure explanation, the loaded environment, the case
writer, the record-key validator, the key catalogue and the case rules.

| shape | semantics | example member(s) |
|---|---|---|
| `set` | union of every implementer's set | `get_solver_commands`, `get_environment_commands` |
| `map` | merge in stack order; a duplicate key is an error unless the more specific entry carries `overrides: <provider id>` naming whose entry it replaces | `get_named_catalogs`, `get_tutorial_records`, `resolve_supplied_variables` |
| `catalog` | the `map` rule over a `DictionaryCatalog`'s documents, rebuilt into a catalog | `get_dictionary_catalog` |
| `sequence` | concatenate every implementer's result, in stack order | `validate_run_semantics`, `get_record_key_catalog` |
| `single` | the most specific non-`None` answer | `get_config_value_reader`, `get_parallel_steps` |
| `chain` | thread the first argument through every implementer | `select_applicable_record_keys` |
| `profile` | every provider's profile: case files concatenated, the rest from the most specific | `get_profile` |

A member nobody implements answers its shape's empty value (`frozenset()`,
`{}`, `()`, `None`, an empty catalogue; `chain` returns its argument), or its
own entry where empty would be wrong (no `get_environment_diagnostics` is an
`environment_capability_unavailable` error in the plan). A member marked
`Needed` refuses by name instead, naming the operation that needs it: the
record-key validator, case-value comparator and config-value reader for
running a record case, `get_parallel_steps` for a parallel run, and the
resolver and renderer for writing a case.

When a provider joins a stack, `validate_plugin` refuses a public callable
that names no member (a misspelling would otherwise be ignored), and half of
a pair that one provider answers together: `resolve_case_mutation` with
`get_supported_mutation_modes`, `render_case_files` with
`get_rendered_formats`. Building the stack refuses a case-file path or a
rendered format with two declarers.

The stack identity records, per member, the most specific implementing
provider (`<unclaimed>` when none), and digests the content of the profile
and the dictionary entries. A content change in another member,
in an editable install with no version bump, is invisible to it.

## What the agent knows, and how

A fact an agent acts on should be a field of some command's JSON; prose is for
the why. **Data** is a CLI field, **prose** is a document, **unknown** is
nowhere. Where the solvers differ, the row says so.

| fact | cardiacFOAM, cardiacSubstrateFOAM | openCARP | TorchCor |
|---|---|---|---|
| keys | data: `describe --entry` (`record_surface.keys`), `catalog`; drift: `catalog --uncatalogued`, `--unread` | data: `catalog`, generated from `+Help` | data with `--repo` (the runner's `--describe`); with `--plugin` alone keys are written unvalidated |
| menus | data: `menu`, `cxx_values` from the scan | data: `menu`, with `menu_labels` for integer codes | data: `device` |
| defaults | mostly unknown: `default` is stated for a few selectors; a catalogued default the C++ contradicts is a `disagreement` warning, but the C++'s default reaches the agent only for an uncatalogued read | data: `default`, or `default_expression` | unknown: every key is required |
| relations, bounds | data: the relation fields, `minimum`/`exclusive_minimum`/`maximum`; some positivity rules are still only `constraints` prose | data: bounds; a bound that is an expression is a refusal's `maximum_expression` | data: the runner's `--check` verdict |
| units | partly data: `unit`, empty on most numeric entries | data: `unit`, in core's spelling | data: in the key names (`_S_per_m`, `_mV`) |
| axes, readers | data: `record_surface.axes`, `record_surface.readers` (a format with no reader is `reader: null`) | same | same |
| numerics, orders | data: `menu_attributes` (`formal_order`, `stated_by`, `settled_by`) on the fvSchemes tables and cardiacFOAM's `solutionAlgorithm`, `batchedIntegrator` and `timeCouplingScheme` | unknown | unknown |
| ionic models | data: `catalog --named ionic_model_catalog` (cardiacFOAM) | unknown: a free string | one model |
| utilities | data: `describe`'s `utility_manifests` (flags, arguments, `produces`); drift under `catalog --uncatalogued`/`--unread` | n/a | n/a |
| native studies | prose: the solver guidance points at `setup/studies/`; no command lists them | prose: `benchmarks/niederer2011/oblique/` | same as openCARP |
| current case values | unknown | unknown | unknown |
| shell | data: `env` (`variables`, `shell_prefix`, `commands`, `preflight`) | same | same |
| MPI | data: `env` (`launcher`, the 2-rank `parallel` probe); preflight refuses the other MPI's launcher | same | n/a: `serial_only` |
| builds and source | data: `build-record`, the run document's `solverProvenance`, `stale_build` / `build_source_unknown` | data: `-buildinfo` | data: the editable install |
| machine | data: `env`'s `host`, each step's `host` in `workflow_state.json`; a run document's process count is rechecked against the allocation at dispatch (`allocation_mismatch`) | same | same |
| job submission | prose: `AGENT_GUIDE.md`'s Slurm script; `sweep-plan` writes each case's run document, so a sweep can be one job per case | same | n/a |
| cross-solver mappings | prose: `docs/solver-learning/cross-solver-variables.md` | same | not covered |
| benchmarks | data once named: `describe --benchmarks DIR`; no command lists them | same | same |
| verification problems | data: `omnidriver-verify` (`problems`, `show`, `residual`, `cell-model`, `norms`, `compare`) | same, through the problems' finite-element norms | not mapped |
| verification status | `check` prints `verified` per record and persists nothing; the results are prose in the ROADMAP and `docs/solver-learning` | same | same |
