# Historical cardiac test ownership map

Source reviewed: historical driver tests at commit
`3c6b5e1640ef0f22e1099bf91bca1fbce2b94c92`.

This is an ownership map, not a parity requirement to keep every assertion in
the old package. A current test may exercise an adapter through a Core-owned
contract, but its assertion belongs to the component that owns the meaning.

| Historical assertions | Owner now | Current executable evidence | Decision |
| --- | --- | --- | --- |
| Plugin identity, capability manifest, generic-case boundary, and tutorial/entry discovery (`test_plugin_architecture`, `test_capability_manifest`, `test_generic_case`, `test_introspection`) | Core contract; cardiac adapter supplies declarations | `packages/omnidriver/tests/core/test_plugin_capabilities.py`, `test_plugin_dependency_boundary.py`, `packages/omnidriver-cardiacfoam/tests/test_plugin_architecture.py`, `test_capability_manifest.py`, `test_generic_case.py` | Keep split: Core owns contract mechanics; cardiac tests prove its declaration. |
| Dictionary parsing, catalog paths, dynamic fields, overrides, and source-backed enum/catalog checks (`test_detection_and_overrides`, `test_dict_builder`, `test_dynamic_required_fields`, `test_template_contract`, `test_ionic_catalog_*`, `test_audit_contract_repairs`, `test_tissue_scoped_overrides`) | Cardiac meaning + OpenFOAM dictionary operation | Same-named cardiac tests, plus `test_dict_entries_catalog.py`, `test_validation.py`, `test_rtst_enum_contract.py` | Keep in cardiac package when asserting cardiac names/conditions; leave parser/mutator mechanics in OpenFOAM. |
| Runtime dependency declarations and source/live verification (`test_runtime_dependencies`, `test_runtime_dependencies_live_verification`) | OpenFOAM environment evidence; cardiac declares required libraries | Same-named cardiac tests and `packages/omnidriver-openfoam/tests/core/test_environment_preflight.py` | Keep declaration tests; source/runtime checks use explicit fixtures. Only unrequested native checks may skip; requested acceptance fails if prerequisites are missing. |
| Coupling, Purkinje geometry, mesh provisioning, and heart-solver compatibility (`test_solver_coupling`, `test_purkinje_graph_geometry`, `test_solver_mesh_provisioning`, `test_heart_solver_comparison`) | Cardiac scientific configuration | Same-named cardiac tests | Keep. The adapter interprets valid solver/coupling combinations; Core only combines diagnostics. |
| Cable restitution, single-cell sweep, and tutorial postprocessing (`test_cable_restitution_postprocessing`, `test_single_cell_entry_sweep`, `test_tutorial_postprocessing_contract`) | Cardiac metrics/catalog; Core artifact lifecycle | Same-named cardiac tests | Keep; no OpenFOAM convention belongs in Core. |
| Manufactured tetrahedron cases (`test_manufactured_bath_bidomain_tet`, `test_manufactured_bidomain_tet`, `test_manufactured_eikonal_ecg_tet`, `test_manufactured_monodomain_pseudo_ecg_tet`) | Cardiac adapter configuration | Same-named tests construct synthetic files and assert make_spec/apply_case/workflow behavior | Keep as configuration tests; their names do not establish solver execution or numerical acceptance. Classify any actual native portions separately. |
| Personalized-template catalog keys, units, required sub-block, and manufactured-ECG exclusion (static portions of `test_eikonal_ecg_personalized_templates_regression`) | Cardiac adapter | `test_dict_entries_catalog.py::TestConductionSystemSchemaContract` and `test_validation.py` personalized-template cases | Kept and expanded in T3. |
| Personalized-template finite ECG output, region-mode parity, sensitivity, compiled-template parity, and derivative execution checks (runtime portions of `test_eikonal_ecg_personalized_templates_regression`) | Solver-owned scientific regression; driver owns invocation and reporting | No current disposable selected-source fixture | Map to the selected solver checker before invoking it. T7 covers only the declared acceptance slice; broader personalized-template science remains separately tracked. Do not copy its numerical oracle into Core or auto-discover a checkout. |

## T1b follow-up: assertion owner and execution resources

Correction, 2026-09-09: this is an initial map, not proof that every historical assertion is covered. Classify each retained test on two independent axes:

| Assertion owner | Resource category |
| --- | --- |
| Core lifecycle/API; OpenFOAM format/runtime; cardiac configuration; solver science; study protocol | Synthetic fixture; selected source checkout; native OpenFOAM utility; compiled solver/reference data |

Python may implement or invoke checks in any category. Language, filename and the word "manufactured" do not determine ownership or native applicability.

`packages/omnidriver/tests/core/test_cardiac_tutorial_characterization.py` hashes full real-tutorial dictionaries, plans, diagnostics and capability reports. Replace that broad Core snapshot with neutral registration/plan/dependency assertions and small cardiac fixtures testing declared configuration semantics. Retain narrowly scoped exact snapshots only when their content is an intentional contract with readable diffs. Exact scientific-case inputs belong in an identified case manifest; numerical acceptance remains with the solver's regression checker or the study's protocol. Do not regenerate hashes merely to silence an unexplained change.

For each retired assertion record: intended behavior, current replacement test and owner, or why it is obsolete. Preserve checks that requested values reach their effective dictionary paths and unrelated inputs remain unchanged. A numerical regression alone cannot detect every ignored parameter.

Ordinary tests read committed minimal fixtures and write only temporary directories. Selected-source tests read an explicit checkout. Native integration stages explicit inputs outside source trees and reuses solver-owned Allrun/regression scripts. No test silently discovers a sibling checkout, edits authored tutorials, updates its expected results, or changes scientific tolerances.

## Result

### T1b completion record (2026-09-10)

The follow-up classification is complete. The remaining potentially ambiguous
historical assertions have the following explicit disposition:

| Historical assertion family | Executable replacement or disposition | Owner and resources |
| --- | --- | --- |
| Broad Core tutorial-characterization hashes | Retired. Core retains neutral plugin registration, plan and dependency assertions in `packages/omnidriver/tests/core/test_plugin_capabilities.py` and `test_plugin_dependency_boundary.py`; cardiac declarations use `test_capability_manifest.py`, `test_generic_case.py`, and `test_registered_tutorials_need_no_repository.py`. | Core lifecycle / cardiac declaration; synthetic fixtures only. No authored tutorial bytes are a Core contract. |
| Four manufactured tetrahedron tests | Retained as the four `test_manufactured_*_tet.py` files. They write synthetic dictionaries, exercise `make_spec` / `apply_case` / DAG configuration, and do not launch a solver or assert numerical output. | Cardiac configuration; synthetic fixtures only. |
| Personalized-template runtime comparisons | Deferred to solver-owner review until an identified solver checker/reference exists. The adapter keeps catalog and incompatibility validation; OmniD must not recreate its finite-output or derivative thresholds. | Solver science / study protocol; selected source, compiled solver and reference data when the solver exposes the checker. |
| Package split/import behavior | `test_all_packages_wheel_install.py` builds the three distributions in a temporary copy, installs their wheels into a new virtual environment, and invokes plugin discovery and `describe`. Passed on 2026-09-10. | Packaging; temporary build and virtual environment only. |
| Selected-source/native references | `test_selected_cardiacfoam_fixture.py` and the selected native integration fixture declare their exact source/runtime inputs, stage only named committed files, and report driver evidence separately from the solver check-only report. | Core/OpenFOAM execution mechanics plus solver-owned numerical oracle; explicit source/runtime only. |

T1 and T1b are complete. T6 supplies explicit source/runtime fixtures; T7
invokes existing solver regressions and verifies driver execution separately.
The driver must not grow a duplicate scientific test suite. Existing scientific
assertions without a selected solver checker remain deferred for solver-owner
review, not invented as driver-owned thresholds.
