# OmniDriver Architecture and Migration Goals

This repository is the staging ground for the transition from a monolithic `driverFOAM` tool into the modular, universal **OmniDriver** ecosystem.

## The Grand Vision: Monorepo + Namespace Packages
The engine is shifting from being an OpenFOAM-specific orchestrator to a universal scientific workflow engine capable of orchestrating deterministic continuous simulations (e.g., FEniCS, deal.II, OpenFOAM) and steering dynamic optimization loops via autonomous agents.

To achieve this, the project is adopting a **Monorepo** structure paired with Python **Namespace Packages** (PEP 420). All the code lives in one GitHub repository, but it is published as four strictly decoupled `pip` packages. (**Corrected 2026-09-19**: this said "three" — `omnidriver-cardiaccore` joined 2026-09-18, and the Architectural Rules below already documented it as a fourth, sibling adapter; only this intro sentence and the diagram below it had not caught up.)

### Directory Structure & Import Semantics
Because `src/omnidriver/` will not contain an `__init__.py` file in any of the packages, Python treats it as a namespace. Users can install them independently but import them beautifully:

```text
omnidriver/ (GitHub Root)
├── packages/
│   ├── omnidriver/                  (import omnidriver.core)
│   │   └── src/omnidriver/core/     <-- Universal DAG, provenance, schemas
│   │
│   ├── omnidriver-openfoam/         (import omnidriver.openfoam)
│   │   └── src/omnidriver/openfoam/ <-- Translates core requests into OpenFOAM
│   │
│   ├── omnidriver-cardiacfoam/          (import omnidriver.cardiacfoam)
│   │   └── src/omnidriver/cardiacfoam/  <-- Cardiac physics and logic
│   │
│   └── omnidriver-cardiaccore/          (import omnidriver.cardiaccore)
│       └── src/omnidriver/cardiaccore/  <-- Cardiac preprocessing adapter; sibling to
│                                             cardiacfoam, not a dependent of it (Rule 4)
```

### Architectural Rules
1. **Core Independence:** `omnidriver.core` MUST NOT import anything from `openfoam` or `cardiac`. It must contain **zero** physics rules and **zero** OpenFOAM vocabulary.
2. **Environment Boundary:** `omnidriver.openfoam` depends on `omnidriver.core`, but knows nothing about specific physics.
3. **Domain Implementation:** `omnidriver.cardiacfoam` depends on both.
4. **Sibling adapters:** `omnidriver.cardiaccore` also depends on core and
   openfoam, and MUST NOT import `omnidriver.cardiacfoam` (nor the reverse).
   The two cardiac adapters are siblings; what passes between them is declared
   and mediated, not imported. Added 2026-09-18 with that package's
   integration; `scripts/check-import-boundaries.py` enforces all four.

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
| core's whole suite against a built wheel | ✅ **0 failed** since 2026-09-04 — `scripts/check-wheel-artifact.py` plus the suite; see `CLAUDE.md`. Before that day it could not even be *collected*: eight modules called `repo_root_default()` at import time and thirteen tests failed. |
| core imported from a built wheel | ✅ guarded by `test_wheel_install_imports.py` |
| plugin resolves by entry-point name | ✅ guarded by `test_entry_point_group_matches_packaging.py` |
| core's CLI usable alone | ✅ `omnidriver --help` exits 0 in a core-only install |
| `"org.cardiacfoam"` in core | 1 occurrence, in a docstring recording that the twenty gated fallbacks were deleted (`plugin_capabilities.py:1362`) — zero in executable logic. **Corrected 2026-09-03**: this said 2 occurrences and named `capability_seams.py:160`, whose copy went in `6a212dd`. |

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
or transition. The measurement history is preserved in `GITHUB_MIGRATION.md` §2
and in the Phase 2 plan's "Task 5, remeasured".)

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
  `omnidriver-cardiacfoam` package data and read through the
  `command_authorization` capability seam; core no longer hardcodes any
  plugin's utilities root.
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


## Plugin capability seams

<!-- BEGIN GENERATED: capability-seams -->

<!-- Generated by scripts/export-capability-seams.py -- do not edit by
     hand. The source of truth is the structured field block in each
     capability Protocol's docstring in core/plugin_capabilities.py. -->

`SolverPlugin` (plus the optional
`SolverPluginOptionalHooks`) in `core/plugin_interface.py` is the **public**
contract a plugin author implements. `PluginCapabilities` in
`core/plugin_capabilities.py` is core's **internal** view *over* a loaded
plugin — it points the opposite way and is not an authoring surface.

A capability marked `optional-neutral` or `optional-refusing` degrades when
the plugin does not implement its hook: the named `compatibility.py`
fallback runs instead. No fallback branches on plugin identity, so a given
fallback answers the same for every plugin. An `optional-refusing` member's
fallback cannot be neutral and refuses by hook name instead.

| capability | protocol | adapts | consumed by | fallback | status |
|---|---|---|---|---|---|
| `tutorials` | `TutorialCatalogCapability` | `get_tutorial_catalog`, `get_tutorial_displays` | `omnidriver/core/runtime/registry.py`, `omnidriver/cardiacfoam/dict_builder.py` | none | required |
| `dictionaries` | `DictionaryCatalogCapability` | `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog`, `get_phases` | `omnidriver/dict_entries.py`, `omnidriver/cardiacfoam/sweep.py`, `omnidriver/openfoam/apply_overrides.py`, `omnidriver/openfoam/dict_builder.py`, `omnidriver/core/specs/validation.py`, `omnidriver/core/strict_planning.py` | `legacy_phases` | get_dict_entries=required, get_dict_groups=required, get_dictionary_catalog=required, get_phases=optional-neutral |
| `manifest` | `CapabilityManifestCapability` | `get_capabilities` | `omnidriver/dict_entries.py`, `omnidriver/core/introspection.py`, `omnidriver/core/strict_planning.py` | none | required |
| `configuration_validator` | `ConfigurationValidatorCapability` | `validate_configuration` | `omnidriver/core/strict_planning.py` | none | required |
| `run_semantic_validator` | `RunSemanticValidatorCapability` | `validate_run_semantics` | `omnidriver/core/specs/validation.py` | none | required |
| `artifacts` | `ArtifactPredictorCapability` | `predict_data_artifacts` | `omnidriver/core/runtime/artifacts.py` | none | required |
| `run_document_configuration` | `RunDocumentConfigurationCapability` | `build_run_document_config`, `get_run_document_config_schema` | `omnidriver/core/runtime/run_document_adapter.py`, `omnidriver/core/runtime/run_document_exec.py` | `legacy_run_document_config`, `legacy_run_document_config_schema` | optional-neutral |
| `cxx_mapping` | `CxxMappingCapability` | `get_profile` | `omnidriver/core/strict_planning.py` | none | required |
| `mesh_diagnostic_policy` | `MeshDiagnosticPolicyCapability` | `get_mesh_geometry_diagnostics`, `get_base_mesh_geometry_diagnostics`, `is_nondimensional_case` | `omnidriver/core/strict_planning.py` | `legacy_nondimensional_case`, `legacy_base_mesh_geometry_diagnostics` | optional-neutral |
| `case_compatibility` | `CaseCompatibilityCapability` | `has_case_marker`, `is_case_runnable_without_workflow` | `omnidriver/core/runtime/registry.py` | `legacy_case_marker`, `legacy_case_runnable_without_workflow` | optional-neutral |
| `sweep_materializer` | `SweepMaterializerCapability` | `materialize_sweep_case`, `route_sweep_case_values` | `omnidriver/sweep_materialize.py`, `omnidriver/sweep_routing.py` | `legacy_materialize_sweep_case`, `legacy_route_sweep_case` | optional-refusing |
| `command_authorization` | `CommandAuthorizationCapability` | `get_auxiliary_commands`, `get_environment_commands`, `get_solver_commands`, `get_utility_manifests`, `get_utility_roots`, `is_installed_environment_command` | `omnidriver/core/runtime/artifacts.py`, `omnidriver/core/runtime/workflow.py`, `omnidriver/core/strict_planning.py` | `legacy_auxiliary_commands`, `legacy_environment_commands`, `legacy_is_installed_environment_command`, `legacy_solver_commands`, `legacy_utility_manifests`, `legacy_utility_roots` | optional-neutral |
| `case_introspection` | `CaseIntrospectionCapability` | `get_samplable_fields`, `get_selected_start_time`, `resolve_case_models` | `omnidriver/core/runtime/provenance_inputs.py` | `legacy_resolve_case_models`, `legacy_samplable_fields` | optional-neutral |
| `case_files` | `CaseFileContractCapability` | `get_profile`, `get_config_resolution_description` | `omnidriver/core/runtime/strict_audit.py`, `omnidriver/core/tutorial_contracts.py`, `omnidriver/core/runtime/provenance_inputs.py` | `legacy_describe_config_resolution` | get_profile=required, get_config_resolution_description=optional-neutral |
| `case_runtime_conventions` | `CaseRuntimeConventionsCapability` | `get_case_runtime_conventions` | `omnidriver/core/runtime/registry.py`, `omnidriver/core/runtime/sweep_runner.py` | `legacy_case_runtime_conventions` | optional-neutral |
| `environment_preflight` | `EnvironmentPreflightCapability` | `get_environment_diagnostics`, `get_configured_environment`, `get_loaded_environment` | `omnidriver/core/strict_planning.py`, `omnidriver/core/runtime/sweep_runner.py`, `omnidriver/cli.py` | `legacy_environment_diagnostics`, `legacy_configured_environment`, `legacy_load_environment` | optional-neutral |
| `dict_diagnostics` | `DictDiagnosticsCapability` | `get_function_object_field_diagnostics`, `get_case_dict_key_diagnostics` | `omnidriver/core/strict_planning.py` | `legacy_function_object_field_diagnostics`, `legacy_case_dict_key_diagnostics` | optional-neutral |
| `override_schema` | `OverrideSchemaCapability` | `get_dict_entry_catalog`, `get_override_schema` | `omnidriver/core/introspection.py` | `legacy_dict_entry_catalog`, `legacy_override_schema` | optional-neutral |
| `runtime_evidence` | `RuntimeEvidenceCapability` | `get_artifact_value_reader`, `get_extra_provenance_paths`, `get_solve_step_commands`, `get_telemetry_source_globs` | `omnidriver/core/runtime/provenance_inputs.py` | none | optional-neutral |
| `case_provenance` | `CaseProvenanceCapability` | `get_generated_output_globs`, `get_required_inputs` | `omnidriver/core/runtime/provenance_inputs.py` | none | optional-neutral |
| `report_catalog` | `ReportCatalogCapability` | `get_report_catalog` | `scripts/export-report-catalog.py` | `legacy_report_catalog` | optional-neutral |
| `named_catalogs` | `NamedCatalogsCapability` | `get_named_catalogs` | `omnidriver/core/introspection.py` | `legacy_named_catalogs` | optional-neutral |
| `override_scopes` | `OverrideScopeCapability` | `get_override_scopes`, `get_override_target_paths`, `apply_overrides`, `inspect_effective_configuration` | `omnidriver/openfoam/apply_overrides.py`, `omnidriver/core/runtime/provenance_inputs.py`, `omnidriver/core/runtime/step_candidate.py`, `omnidriver/core/strict_planning.py` | `legacy_override_scopes`, `legacy_override_target_paths`, `legacy_apply_overrides`, `legacy_inspect_effective_configuration` | get_override_scopes=optional-neutral, get_override_target_paths=optional-refusing, apply_overrides=optional-refusing, inspect_effective_configuration=optional-neutral |
| `dict_regeneration` | `DictRegenerationCapability` | `get_regeneration_scopes` | `omnidriver/openfoam/apply_overrides.py` | `legacy_dict_regeneration_scopes` | optional-neutral |
| `config_value` | `ConfigValueCapability` | `get_config_value_reader` | `omnidriver/cardiacfoam/run_document_config.py` | none | optional-neutral |
| `dict_key_scanner` | `DictKeyScannerCapability` | `get_dict_key_scanner` | `omnidriver/core/strict_planning.py` | `legacy_dict_key_scanner` | optional-neutral |

26 capability seams.

<!-- END GENERATED: capability-seams -->
