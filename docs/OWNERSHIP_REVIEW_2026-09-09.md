# Ownership review: core, OpenFOAM, and cardiacFOAM

Date: 2026-09-09
Scope: capability hooks and runtime modules used by planning, mutation, execution, provenance, result collection, and entry-case staging. This is a read-only boundary review before catalog reconciliation. It does not alter scientific defaults, accepted solver combinations, or native execution.

## Decision

The boundary describes *who owns a decision*, not which legacy module happened to implement it. Core owns the lifecycle around a declared operation: plan identity, leases, snapshots, validation aggregation, dispatch, cancellation, retry policy, rollback, and evidence records. An adapter owns the declaration and interpretation that require its knowledge.

The target contract is deliberately small:

1. **Describe** capabilities and a stable identity.
2. **Inspect** configuration and dependencies without mutation.
3. **Validate** domain or environment requirements with evidence.
4. **Propose operations**, including inputs, outputs, and finite mutation targets.
5. **Interpret results** into bounded diagnostics and metrics.
6. **Supply fixtures** that prove the above contracts.

These are operation families, not six mandatory methods or six oversized entry points. The target contract lets a plugin implement only the families it supports; existing mandatory hooks need a compatibility migration before that becomes true everywhere. An adapter proposal never owns a transaction: core snapshots its declared targets, invokes the declared operation, validates the candidate, controls dispatch, and records the outcome. Configuration validation is not execution success. A rejected or interrupted candidate may remain quarantined for inspection and explicit recovery; automatic restoration is not always the desired policy.

**Clarification, 2026-09-09:** Core owns the generic capability interfaces, request/result types, and lifecycle enforcement. Adapters own implementations and content that require environment or domain knowledge. A row assigning a capability to OpenFOAM or cardiacFOAM refers to that implementation/content, not relocation of its generic protocol. A different environment must remain able to implement the same contract.

The dependency direction remains:

```text
agent -> core application API -> adapter contracts
                                /                \
                         OpenFOAM adapter <- cardiacFOAM adapter
```

`omnidriver.openfoam` must not import `omnidriver.cardiacfoam`; the cardiac adapter may use OpenFOAM dictionary and runtime facilities.

## Review record

“Evidence” names the current implementation rather than an intended future consumer. The acceptance test is existing executable evidence that should stay green while a row is reconciled. `Move` means move responsibility, not blindly copy the current implementation. `Simplify` means fold several narrow hooks into one of the six operation families only after its callers have migrated.

| Current hook or module | Owner after review | Real consumer and evidence returned | Acceptance test | Classification |
| --- | --- | --- | --- | --- |
| `DriverContext`, attempt leases, transactions, workflow DAG and process runner | Core | `core/runtime/*`; identities, before-images, state transitions, logs, exit/timeout evidence | `test_execution_transaction.py`, `test_remediation_transaction.py`, `test_process_execution_contract.py` | Keep |
| `TutorialCatalogCapability` | Core owns registration/query contract; environment or domain adapters supply tutorials | Registry and `describe`; tutorial identity, defaults, and fixtures | `test_plugin_capabilities.py`, cardiac `test_registered_tutorials_need_no_repository.py` | Keep |
| `DictionaryCatalogCapability` | Core owns catalog contract; OpenFOAM owns syntax/read-write and common configuration semantics; cardiacFOAM owns cardiac paths, meanings, conditions and required dimensions | `openfoam/apply_overrides.py`, strict planner; current mixed catalog returns cardiac documents plus OpenFOAM-editable entries | `test_dict_entries.py`, cardiac `test_dict_entries_catalog.py`, OpenFOAM mutation tests | Simplify |
| `ConfigurationValidatorCapability` and `RunSemanticValidatorCapability` | Core owns contracts and policy aggregation; adapters implement their applicable environment/domain checks | Strict planning and run-document validation; structured scientific diagnostics | `test_validation.py`, `test_run_document_config_schema.py` | Keep, later group under **Validate** |
| `CxxMappingCapability.get_profile` and `CaseFileContractCapability` | Split: OpenFOAM owns environment file/runtime bindings; cardiacFOAM owns solver source/model provenance | Strict planning, provenance, tutorial audit; profile rules and source references | `test_plugin_profile.py`, `test_case_file_contract.py`, `test_provenance_inputs.py` | Move |
| `MeshDiagnosticPolicyCapability` | Split: OpenFOAM owns `polyMesh` inspection; cardiacFOAM owns Purkinje/non-dimensional scientific exceptions | Strict planner; mesh diagnostics | OpenFOAM `test_strict_planning_mesh_geometry_adapter.py`, cardiac `test_check_mesh_geometry_manifest.py` | Move |
| `CaseCompatibilityCapability` | Split: OpenFOAM owns entrypoint/case-layout recognition; cardiacFOAM owns `electroProperties` solver marker | Runtime registry; case ownership/runnability decision | `test_case_compatibility_matrix.py`, cardiac `test_case_introspection_capability.py` | Move |
| `SweepMaterializerCapability` | CardiacFOAM proposes semantic changes; Core materializes transaction; OpenFOAM performs dictionary writes | Sweep routing/materialization; currently writes a case directly with no uniform declared-target operation | `test_sweep_plan_contract.py`, `test_sweep_materialize.py` | Simplify |
| `CommandAuthorizationCapability` and `runtime/workflow.py` command checks | Core owns authorization policy; OpenFOAM declares installed-application/runtime conventions; cardiacFOAM declares solver commands | Workflow planning/dispatch; authorization evidence and artifact attribution | `test_command_authorization.py`, `test_workflow_command_security.py` | Move |
| `CaseIntrospectionCapability.selected_start_time` | OpenFOAM | Provenance input selection; OpenFOAM time-selection evidence | `test_provenance_inputs.py`, OpenFOAM config-value tests | Move |
| `CaseIntrospectionCapability.resolve_case_models` / `samplable_fields` | CardiacFOAM | Provenance and configuration diagnostics; resolved solver/model/field evidence | cardiac `test_case_introspection_capability.py`, `test_dynamic_required_fields.py` | Keep |
| `ConfigValueCapability`, `DictDiagnosticsCapability`, `effective_dictionary.py`, `mutators.py` | Core retains generic reader/diagnostic protocols; OpenFOAM owns its format-specific implementations | Inspection and dictionary operation implementation; parse/include/dimension/runtime evidence | OpenFOAM `tests/core/test_effective_dictionary.py`, `tests/core/test_mutators.py` | Move |
| `OverrideSchemaCapability`, `OverrideScopeCapability`, `DictRegenerationCapability` | Core owns generic contracts and transaction; OpenFOAM declares common numerical/runtime settings and writes dictionaries; cardiacFOAM declares cardiac paths, conditions and operations | Agent-facing `step --apply`; proposed target paths and effective-value evidence | `test_override_schema_capability.py`, cardiac `test_override_round_trip.py`, `test_bath_bidomain_variant_apply.py` | Simplify |
| `EnvironmentPreflightCapability`, `parallel_execution.py`, runtime discovery | Core retains generic preflight contract; OpenFOAM supplies its runtime and parallel conventions; cardiacFOAM adds solver/build requirements | Strict plan and sweep runner; source/runtime/executable/MPI evidence | `test_launch_readiness.py`, OpenFOAM `tests/core/test_environment_preflight.py` | Move |
| `RuntimeEvidenceCapability` | Core captures raw stdout/stderr, timestamps, exit status and artifact identity; OpenFOAM interprets its logs, time directories, fields and utility diagnostics; cardiacFOAM supplies solver dependencies and cardiac readers | Provenance and telemetry; dependency and metric-reader evidence | `test_runtime_evidence.py`, cardiac `test_runtime_dependencies.py` | Move |
| `CaseProvenanceCapability` | Split on the same boundary | Provenance classifier; declared generated outputs and resolved required inputs | `test_case_provenance_capability.py`, cardiac `test_provenance_inputs.py` | Move |
| `ArtifactPredictorCapability`, report catalog, named catalogs | Core owns generic prediction/report contracts; OpenFOAM supplies utility artifacts; cardiacFOAM supplies cardiac artifacts, reports and model catalogs | Artifact tracking and `describe`; cardiac outputs, report applicability, model catalogs | `test_artifacts_predictor.py`, cardiac `test_report_catalog_export.py`, `test_ionic_catalog_contract.py` | Keep |
| `runtime/output_collection.py`, `runtime/reconciler.py` | Core tracks generic artifacts; OpenFOAM interprets time directories, fields, and utility diagnostics | Completion/result reconciliation; current numeric-time and `postProcessing` assumptions | `test_output_collection.py`, `test_postprocessing_generic.py` | Move |
| `runtime/sweep_runner.py:_stage_entry_case` and `_clean_stale_time_directories` | Core keeps atomic staging, recovery journal, promotion and lease; OpenFOAM owns generated-output classification and stale-time policy | Entry-case sweep staging; current filter names `postProcessing`, `processor*`, `.foam`, `.msh`, `.geo`, `log.*`, numeric time directories, and `polyMesh` | cardiac `tests/regression_equivalence/test_staging.py`, core `test_sweep_runner.py`, OpenFOAM `tests/core/test_sweep_materialize.py` | Move |
| `GenericOpenFOAMPlugin` | Move OpenFOAM implementation out of Core once its environment adapter supplies the profile and runtime declaration; retain an explicit neutral core execution option | Core-only fallback/scaffold; currently encodes OpenFOAM identity and case layout in core | `test_generic_plugin_execution.py`, `test_core_generic_case.py`, `test_plugin_dependency_boundary.py` | Remove (blocked by command-boundary migration) |

## Explicit consequences

### Staging is a core mechanism, not an OpenFOAM mechanism

Do not move copying, leases, atomic promotion, recovery journals, or rollback out of core. Move only the classification currently embedded in `_stage_entry_case` and `_clean_stale_time_directories`: the OpenFOAM adapter should inspect a source case and declare which files/directories are generated and which stale outputs must be removed before reuse. Core applies that bounded declaration during its existing staging transaction.

The declaration needs to be explainable: resolve classification rules against the inspected source tree into a finite manifest of affected paths, reasons and supporting evidence. Do not hide mutation scope behind a general-purpose ignore callback. Core checks confinement and source identity before applying that manifest under ownership.

Moving a heuristic does not make it correct. Names such as `.msh`, `.geo`, `data/`, `0/` or `postProcessing/` can identify authored inputs in a legitimate case. Declared inputs and provenance must constrain exclusions; conflicting classifications must be reported rather than silently deleting input. Preserve authored meshes and similarly named input directories in the acceptance fixtures.

### Dictionary changes are a three-party operation

OpenFOAM owns the common meanings and dimensional representation of `controlDict`, `fvSchemes`, `fvSolution`, decomposition and utility settings. CardiacFOAM owns solver-specific parameters, their required dimensions and applicable restrictions. Neither layer infers scientific defaults from examples alone.

For a request such as “change the ionic model”:

1. CardiacFOAM validates the requested semantic path, activation conditions, dimensions, and finite dictionary targets.
2. OpenFOAM reads/writes those targets and supplies syntax, include, dimension, and effective-resolution evidence.
3. Core snapshots the targets, persists the proposal/evidence, validates before dispatch, and records execution separately. A refusal or interruption blocks reuse and retains the candidate for inspection or restoration through the explicit recovery contract.

No layer named `adapted` is needed. “Adapted” describes this translation from cardiac meaning to OpenFOAM operations under a core-owned lifecycle.

### Result interpretation must stop assuming OpenFOAM in Core

Core retains raw process-evidence capture and generic artifact matching, freshness, collection and reconciliation mechanisms. The existing modules need behavioral tests when those mechanisms are separated from format-specific assumptions; moving code alone does not strengthen their guarantees. Recognition of numeric time directories, `postProcessing`, field layouts, and OpenFOAM utility output belongs in an OpenFOAM result interpreter. CardiacFOAM then adds activation time, ECG, convergence, and other domain metrics through the same **Interpret results** operation family.

## Migration order and gates

1. **Adopt these ownership principles.** For each catalog delta or extraction, identify its owner, consumer and behavioral acceptance test. Existing test references are regression guards, not proof that the proposed boundary is already enforced.
2. **Extract OpenFOAM declarations, not core mechanisms.** First extract staging/output classification and stale-time policy behind bounded adapter declarations. Preserve the current staging and transaction mechanisms. Add a non-OpenFOAM fixture with authored `data/`, `0/`, `postProcessing/`, `.msh` and `.geo` inputs, proving that core does not discard them by name.
3. **Split mixed hooks by decision owner.** Start with dictionary mutation, case profile/introspection, and mesh/result diagnostics. Do not add a forwarding hook for each legacy function; compose them under the six operation families.
4. **Move the generic OpenFOAM default out of core only after command authorization/trust-boundary work has a declared environment contract.** Until then, `GenericOpenFOAMPlugin` remains an explicitly recorded legacy default, not evidence that Core owns OpenFOAM. Preserve an explicit neutral execution option without either adapter installed, and document how default selection changes for existing callers.
5. **Reconcile catalogs in parallel where ownership is clear.** Do not block confirmed cardiac catalog fixes on completing every mixed-hook extraction. Every incoming record must retain source evidence, verification/support status, activation conditions and owning adapter; distinguish compiled defaults, examples and recommendations. Defer only changes that depend on an unresolved contract boundary.

The standing structural gates are `test_plugin_dependency_boundary.py` (no cardiac import from Core and no direct plugin bypass), `test_capability_seam_documentation.py` (declared hooks and actual consumers), and `scripts/check-import-boundaries.py`. The next extraction must add a fixture-level gate for the OpenFOAM staging declaration and retain the existing transaction and staging regressions above.
