# OmniDriver architecture

This repository is **OmniDriver**: a solver-agnostic workflow engine in five packages, one per concern.

## The Grand Vision: Monorepo + Namespace Packages
The engine orchestrates deterministic continuous simulations (OpenFOAM and openCARP today) and can steer optimization loops through autonomous agents.

The project is a **Monorepo** paired with Python **Namespace Packages** (PEP 420). All the code lives in one GitHub repository, but it is published as five strictly decoupled `pip` packages.

### Directory Structure & Import Semantics
Because `src/omnidriver/` will not contain an `__init__.py` file in any of the packages, Python treats it as a namespace. Users can install them independently but import them beautifully:

```text
omnidriver/ (GitHub Root)
├── packages/
│   ├── omnidriver/                  (import omnidriver.core)
│   │   └── src/omnidriver/core/     <-- Universal DAG, provenance, schemas
│   │       ├── quantities/          <-- Solver-neutral results-as-quantities: Quantity,
│   │       │                            units, sentinels, the reader contract, comparison
│   │       └── runtime_records.py   <-- Core's own run-record filenames, declared once
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
│   ├── omnidriver-cardiaccore/          (import omnidriver.cardiaccore)
│   │   └── src/omnidriver/cardiaccore/  <-- Cardiac preprocessing adapter; sibling to
│   │                                         cardiacfoam, not a dependent of it (Rule 4)
│   │
│   └── omnidriver-opencarp/             (import omnidriver.opencarp)
│       └── src/omnidriver/opencarp/     <-- openCARP adapter; depends on core only (Rule 5)
│
├── benchmarks/                      <-- Published, solver-neutral reference definitions
│                                        (e.g. niederer2011.json); scripts/check-benchmark-
│                                        references.py gates them
```

### Architectural Rules
1. **Core Independence:** `omnidriver.core` MUST NOT import anything from `openfoam` or `cardiac`. It must contain **zero** physics rules and **zero** OpenFOAM vocabulary.
2. **Environment Boundary:** `omnidriver.openfoam` depends on `omnidriver.core`, but knows nothing about specific physics.
3. **Domain Implementation:** `omnidriver.cardiacfoam` depends on both.
4. **Sibling adapters:** `omnidriver.cardiaccore` also depends on core and
   openfoam, and MUST NOT import `omnidriver.cardiacfoam` (nor the reverse).
   The two cardiac adapters are siblings; what passes between them is declared
   and mediated, not imported.
5. **Independent adapter:** `omnidriver.opencarp` depends on core only and
   MUST NOT import `omnidriver.openfoam` or either cardiac adapter, nor may
   any of them import it. `scripts/check-import-boundaries.py` enforces all
   five.

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
hardcoded string with no declaration path is a defect. `scripts/check-core-shape.py` holds what is left to a recorded
baseline (`scripts/core-shape-baseline.txt`) that can only shrink, and
`scripts/check-import-boundaries.py` enforces the import directions above.
What is still open is tracked in `docs/superpowers/ROADMAP.md`.

## Provider composition

A plugin is a stack of providers: a solver plugin layered on the environment
it `requires:` (cardiacFOAM and cardiacCore on the OpenFOAM layer), or one
provider on its own (openCARP). `provider_stack.order_providers` orders them
least specific first from their profiles' `requires:`, refusing an unmet
requirement or a cycle, stably, since the stack digest hashes the order.

The contract is `SolverPlugin` in `core/plugin_interface.py`. Only a
provider's four identity properties are required; every other member is
optional. `provider_stack.MEMBERS` is the one table of the contract: for each
member, how a stack composes the providers that implement it, and what the
stack answers when none does. Core reaches every member through
`driver_context.stack.call(member, ...)`.

| shape | semantics | example member(s) |
|---|---|---|
| `set` | union of every implementer's set | `get_solver_commands`, `get_environment_commands` |
| `map` | merge in stack order; a duplicate key is an error unless the more specific entry carries `overrides: <provider id>` naming whose entry it replaces | `get_named_catalogs`, `get_tutorial_records` |
| `catalog` | the `map` rule over a `DictionaryCatalog`'s documents, rebuilt into a catalog | `get_dictionary_catalog` |
| `sequence` | concatenate every implementer's result, in stack order | `validate_run_semantics`, `get_record_key_catalog` |
| `single` | the most specific non-`None` answer | `get_config_value_reader`, `get_parallel_steps` |
| `chain` | thread the first argument through every implementer | `get_configured_environment` |
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
