# OmniDriver Architecture and Migration Goals

This repository is the staging ground for the transition from a monolithic `driverFOAM` tool into the modular, universal **OmniDriver** ecosystem.

## The Grand Vision: Monorepo + Namespace Packages
The engine is shifting from being an OpenFOAM-specific orchestrator to a universal scientific workflow engine capable of orchestrating deterministic continuous simulations (e.g., FEniCS, deal.II, OpenFOAM) and steering dynamic optimization loops via autonomous agents.

To achieve this, the project is adopting a **Monorepo** structure paired with Python **Namespace Packages** (PEP 420). All the code lives in one GitHub repository, but it is published as three strictly decoupled `pip` packages.

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
│   └── omnidriver-cardiac/          (import omnidriver.cardiac)
│       └── src/omnidriver/cardiac/  <-- Cardiac physics and logic
```

### Architectural Rules
1. **Core Independence:** `omnidriver.core` MUST NOT import anything from `openfoam` or `cardiac`. It must contain **zero** physics rules and **zero** OpenFOAM vocabulary.
2. **Environment Boundary:** `omnidriver.openfoam` depends on `omnidriver.core`, but knows nothing about specific physics.
3. **Domain Implementation:** `omnidriver.cardiac` depends on both.

## Immediate Migration Goals (To-Do)

Complete these in order — each task assumes the ones above it are done. File
paths and line numbers are given so each item can be verified directly; see
[`MIGRATION_AUDIT_v2.md`](MIGRATION_AUDIT_v2.md) for supporting detail.

- [ ] **Task 0 — Fix the default plugin context.**
  `core/compatibility.py::legacy_default_driver_context` imports
  `..plugins.cardiacfoam_plugin.CardiacFoamPlugin`, which is not present in
  `openfoam_driver/plugins/` (only `__init__.py` exists there today). Every
  caller of `resolve_public_driver_context(None)` — the default path used
  throughout `registry.py` and `run_document_exec.py` — raises
  `ModuleNotFoundError`, and `pytest` fails to collect 8 test modules for the
  same reason. Choose one: (a) install the cardiacfoam plugin as a dev/test
  dependency and keep the cardiac default, or (b) make
  `GenericOpenFOAMPlugin` (`core/generic_plugin.py:27`) the default and make
  cardiac behavior opt-in. Exit criterion: `python3 -m pytest
  openfoam_driver/tests -q` collects with 0 errors.

- [ ] **Task 1 — Formalize the role vocabulary.**
  `core/generic-plugin.yaml`'s `case_profile.dictionaries[].role` field
  documents values including `openfoam.control_dict` and
  `openfoam.mesh_generation`; `CaseFileContractCapability.required_rules()`
  (`core/plugin_capabilities.py:412-445`) exposes them to core, already
  consumed by role prefix in `core/tutorial_contracts.py:120-127`. Add
  validation for `role` in `core/plugin_profile.py` against the documented
  enum (currently an unchecked free string).

- [ ] **Task 2 — Keep case-runnability checks capability-routed.**
  `core/runtime/registry.py::_case_is_runnable` already delegates to
  `driver_context.capabilities.case_compatibility.is_runnable_without_workflow(...)`
  rather than checking `constant`/`system` directly — no change needed. Use
  it as the reference pattern for Task 3.

- [ ] **Task 3 — Resolve provenance paths by role, not by literal string.**
  `core/runtime/provenance_inputs.py::_select_start_time` (line 104) and
  `walk_roots` (line 327) hardcode `system/controlDict`, `system/`,
  `constant/`. Resolve the controlDict path by filtering `case_files` for
  `role == "openfoam.control_dict"` (mirror
  `tutorial_contracts.py:120-127`); use the full `case_files` list rather
  than `required_rules()`, since a role can be declared `conditional`.
  Update `test_provenance_inputs.py` (12 literal path references) and
  `test_trust_boundary_end_to_end.py` (7 references) alongside the change.

- [ ] **Task 3b — Quarantine `mutators.py`'s `foamlib` coupling.**
  Call sites: `core/specs/apply_overrides.py:54`, `core/specs/utils.py:5`,
  `core/runtime/provenance_inputs.py:83`,
  `core/runtime/parallel_execution.py:38`. Confirm what
  `test_mutators_differential.py` (24 lines) pins against `test_mutators.py`
  (754 lines) before moving code, so the parity check carries over
  explicitly rather than by accident.

- [ ] **Task 4 — Extract `mesh_provisioning.py`.**
  Trace `default_block_mesh_dict_text` / `cell_counts_from_dx` to their real
  caller before moving them: production materialization goes through
  `driver_context.capabilities.sweep_materializer.materialize(...)`, a
  dynamically-resolved capability with no concrete implementation currently
  present in this repo's `plugins/` tree. Delete
  `sweep_materialize.py::_materialize_case_legacy` (imports a module that
  does not exist, and is never called). Also quarantine the hardcoded paths
  at `core/specs/mesh_geometry.py:132` (`case_root / "constant"`) and
  `core/specs/apply_overrides.py:331` (`system/controlDict`).

- [ ] **Rename the Package:** Change all internal python modules from
  `openfoam_driver` to `omnidriver`, after Tasks 0-4 — this multiplies every
  import-path fix above.
- [ ] **Update Entry Points:** Update `pyproject.toml` to reflect the new
  `omnidriver.plugins` entry point group.
  `[project.entry-points."driverfoam.plugins"]` is currently empty — no
  plugin is registered in this repo yet.
