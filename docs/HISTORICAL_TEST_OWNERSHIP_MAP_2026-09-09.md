# Historical cardiac test ownership map

Source reviewed: historical driver tests at commit
`3c6b5e1640ef0f22e1099bf91bca1fbce2b94c92`.

This is an ownership map, not a parity requirement to keep every assertion in
the old package. A current test may exercise an adapter through a Core-owned
contract, but its assertion belongs to the component that owns the meaning.

| Historical assertions | Owner now | Current executable evidence | Decision |
| --- | --- | --- | --- |
| Plugin identity, capability manifest, generic-case boundary, and tutorial/entry discovery (`test_plugin_architecture`, `test_capability_manifest`, `test_generic_case`, `test_introspection`) | Core contract; cardiac adapter supplies declarations | `packages/omnidriver/tests/test_plugin_capabilities.py`, `test_plugin_dependency_boundary.py`, `packages/omnidriver-cardiacfoam/tests/test_plugin_architecture.py`, `test_capability_manifest.py`, `test_generic_case.py` | Keep split: Core owns contract mechanics; cardiac tests prove its declaration. |
| Dictionary parsing, catalog paths, dynamic fields, overrides, and source-backed enum/catalog checks (`test_detection_and_overrides`, `test_dict_builder`, `test_dynamic_required_fields`, `test_template_contract`, `test_ionic_catalog_*`, `test_audit_contract_repairs`, `test_tissue_scoped_overrides`) | Cardiac meaning + OpenFOAM dictionary operation | Same-named cardiac tests, plus `test_dict_entries_catalog.py`, `test_validation.py`, `test_rtst_enum_contract.py` | Keep in cardiac package when asserting cardiac names/conditions; leave parser/mutator mechanics in OpenFOAM. |
| Runtime dependency declarations and source/live verification (`test_runtime_dependencies`, `test_runtime_dependencies_live_verification`) | OpenFOAM environment evidence; cardiac declares required libraries | Same-named cardiac tests and `packages/omnidriver-openfoam/tests/core/test_environment_preflight.py` | Keep declaration tests; runtime-dependent checks must skip from an explicit environment contract. |
| Coupling, Purkinje geometry, mesh provisioning, and heart-solver compatibility (`test_solver_coupling`, `test_purkinje_graph_geometry`, `test_solver_mesh_provisioning`, `test_heart_solver_comparison`) | Cardiac scientific configuration | Same-named cardiac tests | Keep. The adapter interprets valid solver/coupling combinations; Core only combines diagnostics. |
| Cable restitution, single-cell sweep, and tutorial postprocessing (`test_cable_restitution_postprocessing`, `test_single_cell_entry_sweep`, `test_tutorial_postprocessing_contract`) | Cardiac metrics/catalog; Core artifact lifecycle | Same-named cardiac tests | Keep; no OpenFOAM convention belongs in Core. |
| Manufactured tetrahedron cases (`test_manufactured_bath_bidomain_tet`, `test_manufactured_bidomain_tet`, `test_manufactured_eikonal_ecg_tet`, `test_manufactured_monodomain_pseudo_ecg_tet`) | Native cardiac solver acceptance | Same-named cardiac tests, gated on declared source/build availability | Retain as native evidence; do not make their solver execution a Core unit test. |
| Personalized-template catalog keys, units, required sub-block, and manufactured-ECG exclusion (static portions of `test_eikonal_ecg_personalized_templates_regression`) | Cardiac adapter | `test_dict_entries_catalog.py::TestConductionSystemSchemaContract` and `test_validation.py` personalized-template cases | Kept and expanded in T3. |
| Personalized-template finite ECG output, region-mode parity, sensitivity, compiled-template parity, and derivative execution checks (runtime portions of `test_eikonal_ecg_personalized_templates_regression`) | Native cardiac solver acceptance | No current disposable selected-source fixture | Move to T7. It requires the explicit source/build fixture contract from T6; it must not auto-discover another checkout. |

## Result

Every historical behavior has one current owner. The only deferred evidence is
the runtime half of personalized-template regression, deliberately deferred to
T7 because it is solver acceptance rather than adapter orchestration. No Core
or OpenFOAM implementation change is required by this mapping.
