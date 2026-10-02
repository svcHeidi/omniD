# OmniDriver Architecture and Migration Goals

This repository is the staging ground for the transition from a monolithic single-solver tool into the modular, universal **OmniDriver** ecosystem.

## The Grand Vision: Monorepo + Namespace Packages
The engine is shifting from being an OpenFOAM-specific orchestrator to a universal scientific workflow engine capable of orchestrating deterministic continuous simulations (e.g., FEniCS, deal.II, OpenFOAM) and steering dynamic optimization loops via autonomous agents.

To achieve this, the project is adopting a **Monorepo** structure paired with Python **Namespace Packages** (PEP 420). All the code lives in one GitHub repository, but it is published as five strictly decoupled `pip` packages.

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

## Migration Status

**Phase 1 of core completion has landed** (branch `phase1-core-completion`,
`a57eac4`..`8418365`). The monorepo→packages migration is structurally
complete; Rule 1 as originally written is superseded — see
`future/ENVIRONMENT_CONTRACT.md` and the Open Items below.

**Re-measured 2026-09-02**, after `future/ENVIRONMENT_CONTRACT.md`'s Tier 3
(closed) and Tier 4's entrypoint slice (done), against a **freshly built**
core-only venv (per the recipe in `CLAUDE.md` — not this repo's own `.venv`,
which has all three packages installed).

**Pass/fail, not totals.** This table used to quote exact test counts; they
went stale twice in two days (1543 → 1546 → 1551 → 1566) and were corrected
each time by someone who happened to notice. A count is a fact about the
moment it was taken, and nothing regenerates it. `0 failed` is the durable
claim; run the command for the number:

| | state |
|---|---|
| all packages installed | ✅ **0 failed** — `pytest packages/ -q -m "not slow"`. **Corrected 2026-09-18**: this row claimed ✅ **0 failed** before that date too, and that had never been measured. Three cardiacFoam modules resolved a `DriverContext` at import time, so with more than one adapter installed the run died during *collection*: pytest printed errors, not failures, and the absence of a failure count was read as zero failures. Behind the abort were 235 real failures, nearly all one cause — cardiacFoam's own source asking the `omnidriver.plugins` registry which adapter it was, which has no answer once a second adapter is installed. CI's `test-cardiac` job had been red on it continuously. The ✅ is now measured, and `test_adapter_never_asks_who_it_is` guards the cause. |
| core installed alone | ✅ **0 failed** — `pytest packages/omnidriver/tests -q` in a core-only venv |
| core's whole suite against a built wheel | ✅ **0 failed** since 2026-09-04 — `scripts/check-wheel-artifact.py` plus the suite; see `CLAUDE.md`. Before that day it could not even be *collected*: eight modules looked the repository root up at import time and thirteen tests failed. |
| core imported from a built wheel | ✅ guarded by `test_wheel_install_imports.py` |
| plugin resolves by entry-point name | ✅ guarded by `test_entry_point_group_matches_packaging.py` |
| core's CLI usable alone | ✅ `omnidriver --help` exits 0 in a core-only install |
| `"org.cardiacfoam"` in core | 0 occurrences |

The core-only failure count that this table used to track as the honest
measure of how far core is from standing alone is now **zero**. It began at
160 across four distinct causes (2026-08-27); Tier 1–4 of
`future/ENVIRONMENT_CONTRACT.md` closed the rest. Core genuinely stands alone
today, not just in test-collection terms — the CLI, `describe`, and the full
core-only suite all run clean from a wheel-equivalent install with nothing
else on the path.

(**Corrected 2026-09-03.** Two paragraphs stood here describing 140 remaining
failures — 129 from the implicit cardiac `DriverContext`, 11 from
export-script subprocesses — and analysing how many were a threading problem.
They were left un-deleted when the count reached zero, so this section stated
its own headline metric two ways, in adjacent paragraphs, with no strikethrough
or transition. The measurement history was preserved in `GITHUB_MIGRATION.md` §2
and in the Phase 2 plan's "Task 5, remeasured" — the former deleted
2026-09-22 once the plans directory's own per-phase Status tables superseded
it; the latter still stands at `docs/superpowers/plans/2026-08-27-core-completion-phase-2.md`.)

**Two claims this section used to make, both withdrawn 2026-08-27:**

- *"the `omnidriver.plugins` entry-point group works (`cardiacfoam`
  discoverable via `importlib.metadata`)"* — the metadata was discoverable; the
  code read a different group name (`driverfoam.plugins`), so selecting a plugin
  by name resolved nothing in any install. Fixed in `d760b88`, and the fix is
  guarded by a test that reads real installed metadata rather than the
  `_entry_points()` mock every other discovery test uses.
- *"core's own suite produces 20 collection errors"* — collection errors are
  zero and have been since the test-core decoupling pass. Collecting cleanly is
  a much weaker property than it reads as: function-scoped imports are invisible
  to `--collect-only`, which is why 8 failures hid behind a clean collection
  report. Count failures, not collection errors.

An earlier correction, retained because the lesson generalises: this section
once claimed core had zero runtime imports of `omnidriver.openfoam`. That was
true of the `core/` *subdirectory* and false of the *package* — `cli.py`, one
level up, imported it at module scope, so `import omnidriver.cli` raised
`ModuleNotFoundError` in a core-only install and the whole CLI surface was
unreachable. The `check-import-boundaries.py` gate printed "boundaries OK"
throughout, because it scanned only `core/`. Scope widened in `2f6ce63`;
`cli.py` fixed in `f51387b`.

Full history: `docs/superpowers/plans/2026-08-25-monorepo-package-migration.md`
(the executed migration), `docs/superpowers/plans/2026-08-27-core-completion.md`
(Phase 1, complete), and `MIGRATION_AUDIT_v2.md` (the pre-migration audit —
note its file paths name the retired flat `openfoam_driver/` tree).

## Open Items

Tracked as standalone notes in `future/`, each with its own status:

- [`future/UTILITY_CATALOG_STANDALONE_GAP.md`](future/UTILITY_CATALOG_STANDALONE_GAP.md) —
  resolved. The 12 `utility.manifest.toml` sidecars are now bundled as
  `omnidriver-cardiacfoam` package data and read through the stack's
  `get_utility_manifests`; core no longer hardcodes any plugin's utilities
  root.
- [`future/ELECTROPROPERTIES_TEMPLATE_FIXTURE_REVIEW.md`](future/ELECTROPROPERTIES_TEMPLATE_FIXTURE_REVIEW.md) —
  resolved. The bundled fixture is verified accurate against the dict-key
  catalog (every scoped key catalog-addressable, both dead `initialODEStep`
  keys removed, a duplicate unreferenced copy in core deleted).
- [`future/STRICT_PLANNING_FOAMLIB_COUPLING.md`](future/STRICT_PLANNING_FOAMLIB_COUPLING.md) —
  resolved; kept for the record of what the coupling was and why it wasn't a
  trivial fix.
- [`future/ENVIRONMENT_CONTRACT.md`](future/ENVIRONMENT_CONTRACT.md) —
  **Tiers 1–3 closed, Tier 4 partly done, and it supersedes Rule 1 above.**
  Rule 1's second sentence ("zero OpenFOAM vocabulary") is not satisfied and,
  as stated, is not the goal: `Allrun`, `system/controlDict` and
  `$FOAM_APPBIN` are one environment's *bindings* of concepts core legitimately
  owns. That document restates the rule as something checkable — core may name
  a binding only where it is reached through a declared role, a capability
  hook, or a documented, overridable default — and measures which of core's
  bindings currently qualify. **Read it before acting on Rule 1 as written.**

  §5a landed in Phase 1: the role vocabulary is validated at profile load
  (`plugin_profile.KNOWN_ROLES`), and a case's entrypoint is resolved from the
  plugin's declared `openfoam.entrypoint` rule instead of a hardcoded `Allrun`.
  Tier 3 (six items: `control_dict` start-time lookup, `processor*`
  decomposition seam, `apply_overrides`'s crash, `ArtifactFormat` +
  `utility_catalog` vocabulary, the `--openfoam-bashrc` rename) closed
  2026-09-02. Tier 4 — the trust boundary, §5b — is the
  `CASE_SCRIPT_COMMANDS` entrypoint slice only so far
  (`future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md`); `Allclean`/
  `Allrun.pre`/`Allrun.post`, `CORE_NEUTRAL_COMMANDS`, and
  `_is_installed_openfoam_app` remain open, and §6's
  `GenericEnvironmentPlugin` rename stays blocked until Tier 4 is fully closed.

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
provider (`<unclaimed>` when none), and digests the content of the profile,
the dictionary entries and the manifest. A content change in another member,
in an editable install with no version bump, is invisible to it.
