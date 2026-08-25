# Migration Audit v2: Solver-Agnostic Core Engine (evidence-checked)

**Status:** the v1 audit's *direction* is correct but its *problem statement is
incomplete and its Task 2 targets code that doesn't have the bug it
describes*. This version replaces claims with file:line evidence gathered by
reading the actual call graph and running `pytest` in this repo.

## 0. The fact the original audit missed: core is already broken, right now

```
$ git log --oneline
2d84f00 Remove cardiacfoam specific entries
7116745 Initial commit of generic standalone orchestrator

$ git status --short
 M ARCHITECTURE.md
 D openfoam_driver/plugins/cardiacfoam_plugin.py

$ python3 -m pytest openfoam_driver/tests -q
...
ERROR openfoam_driver/tests/core/test_dict_entries.py
ERROR openfoam_driver/tests/core/test_override_round_trip.py
ERROR openfoam_driver/tests/core/test_plugin_profile.py
ERROR openfoam_driver/tests/core/test_remediation.py
ERROR openfoam_driver/tests/core/test_run_document_config_schema.py
ERROR openfoam_driver/tests/core/test_strict_planning.py
ERROR openfoam_driver/tests/drift_guards/test_rtst_enum_contract.py
ERROR openfoam_driver/tests/drift_guards/test_source_refs_exist.py
8 errors during collection
ModuleNotFoundError: No module named 'openfoam_driver.plugins.cardiacfoam'
```

`openfoam_driver/plugins/` in this staging repo contains **only
`__init__.py`** — the cardiacFOAM plugin itself has already been removed as
part of the extraction. But `core/` still imports it in ~22 places, and the
single most load-bearing one is the **default context**:

```python
# core/compatibility.py:58-64
def legacy_default_driver_context() -> "DriverContext":
    from .plugin_interface import driver_context
    from ..plugins.cardiacfoam_plugin import CardiacFoamPlugin   # <- deleted module
    ...

def resolve_public_driver_context(driver_context):
    return driver_context if driver_context is not None else legacy_default_driver_context()
```

`resolve_public_driver_context(None)` is the fallback used *everywhere* a
caller doesn't pass an explicit plugin (`registry.py`, `run_document_exec.py`,
and the rest). Calling it today raises `ModuleNotFoundError`. This is not a
hypothetical future risk the plan should guard against — it's the actual
current state of the repo the OmniDriver task list is being built on top of.
**This has to be fixed before any of Tasks 1-4 in the original plan, or
you'll be refactoring code you can't run tests against.**

Verified directly:

```
$ python3 -c "
from openfoam_driver.core.compatibility import legacy_default_driver_context
legacy_default_driver_context()
"
ModuleNotFoundError: No module named 'openfoam_driver.plugins.cardiacfoam_plugin'
```

## 1. The real surface area (not 3 files — closer to 10)

The v1 audit named three modules. Grepping actual imports (not docstring
mentions) turns up a longer, uneven list:

| File | Cardiac/OpenFOAM coupling | Confirmed via |
|---|---|---|
| `core/compatibility.py` | **~19 lazy imports** of `..plugins.cardiacfoam.*` across every optional-hook fallback (`case_compatibility`, `sweep`, `command_authorization`, `case_introspection`, `override_schema`, `reports`, `overrides`, `run_document_config`, `config_schema`, `planning_policy`, `generic_case_mutation`, `named_catalogs`) plus the default-context import above | `grep -n "plugins\.cardiacfoam" core/compatibility.py` |
| `dict_entries.py` (top-level) | 1 lazy import, `plugins.cardiacfoam.common_dict_entries`, inside `__getattr__` | line 80 |
| `sweep_materialize.py` (top-level) | 1 lazy import, `plugins.cardiacfoam.sweep.materialize_case`, inside dead function `_materialize_case_legacy` (never called — see §3) | line 43 |
| `sweep_routing.py` (top-level) | 1 lazy import, `plugins.cardiacfoam.sweep.route_case_values` | line 39 |
| `core/runtime/provenance_inputs.py` | hardcodes `system/controlDict`, walks `system/`, `constant/` literally | lines 104, 327 |
| `core/specs/mesh_provisioning.py` | emits a raw `blockMeshDict` string (OpenFOAM syntax) | lines 59-176 |
| `core/runtime/mutators.py` | `foamlib`-based dict read/write | 4 real callers, see §4 |
| `core/specs/mesh_geometry.py` | hardcodes `case_root / "constant"` | line 132 |
| `core/specs/apply_overrides.py` | hardcodes `case_root / "system" / "controlDict"` | line 331 |

`tutorials_display.py`, `specs/dict_builder.py`, `runtime/artifacts.py`
mention `plugins.cardiacfoam.*` only in **docstrings/comments**, not imports
— real but lower priority (update the text when the plugin moves, no runtime
risk).

**Correction to the v1 problem statement:** `compatibility.py` is the
dominant OpenFOAM/cardiac dependency in `core`, not an omitted footnote. It's
larger than the three named modules combined and it's the one currently
causing collection failures.

## 2. What the plan proposes to invent already exists — don't rebuild it

The v1 plan's Task 1 proposes a new `environment_rules` YAML block with
`time_control_role: "openfoam.control_dict"` and
`mesh_provisioner: "openfoam.blockMesh"`. That's not new — it's a
re-description of a mechanism already shipped:

```yaml
# core/generic-plugin.yaml (already in the repo)
case_profile:
  dictionaries: []
  #   role  - semantic role tag; common values:
  #             openfoam.control_dict    : system/controlDict
  #             openfoam.mesh_generation : system/blockMeshDict
  #             ...
```

```python
# core/plugin_capabilities.py:412-445 — CaseFileContractCapability
# "Roles are namespaced and the prefix is load-bearing." openfoam.* vs plugin.*
def required_rules(self) -> tuple["CaseFileRule", ...]: ...
```

And it's already *consumed* by role prefix in a working file:

```python
# core/tutorial_contracts.py:120-127
required_rules = driver_context.capabilities.case_files.required_rules()
generic_files = [r.path for r in required_rules if not r.role.startswith("openfoam.")]
openfoam_files = [r.path for r in required_rules if r.role.startswith("openfoam.")]
```

**Corrected instruction:** don't add `environment_rules`. Extend the existing
`role` vocabulary (it's a free-text string today, not validated against the
documented enum — `plugin_profile.py:109-113` only checks
`required ∈ {always, never, conditional}`, never checks `role`) and reuse
`required_rules()`. One caveat the v1 plan didn't note: `required_rules()`
filters to `required == "always"` — a role declared `conditional` won't be
found by it, so a role-lookup helper needs to search `_rules()` (all rules),
not just the required subset.

## 3. Task 2 in the v1 plan is checking a function that doesn't have the bug

> *"Modify `core/runtime/run_document_exec.py`. Replace the hardcoded
> `constant/` and `system/` checks in `_case_is_runnable()`."*

Checked directly:

```python
# core/runtime/registry.py:83-97 — this is where _case_is_runnable actually lives;
# run_document_exec.py only imports it, with a comment already marking it settled:
#   "_case_is_runnable is a private helper reused as-is: the plan treats this as
#    an accepted pragmatic tradeoff... (out of scope here)."
def _case_is_runnable(case_root, *, driver_context=None) -> bool:
    if (case_root / "Allrun").is_file():
        return True
    driver_context = resolve_public_driver_context(driver_context)
    return driver_context.capabilities.case_compatibility.is_runnable_without_workflow(...)
```

There is no hardcoded `constant/`/`system/` check here — it already delegates
to a plugin capability. Editing this function per the v1 plan would touch the
wrong file and re-litigate a decision a prior pass already closed. **Drop
this task entirely.** (It resurfaces indirectly through §0 —
`resolve_public_driver_context` is broken, but the fix there is
restoring/replacing the default, not touching `_case_is_runnable`.)

Also worth flagging while we're in this file:
`sweep_materialize.py::_materialize_case_legacy` (the function with the dead
`plugins.cardiacfoam.sweep` import) is called from **nowhere** in the repo —
not production code, not tests. It's dead. Delete it rather than migrate it;
don't spend Task 4 effort moving code nothing calls.

## 4. Revised task list, in dependency order, each with real callers and the tests that pin them

### Task 0 (new, blocking): Un-break the default context
- `core/compatibility.py::legacy_default_driver_context` currently imports a
  module that no longer exists in this repo (§0).
- Decide one of two things before anything else: (a) this staging repo
  installs the cardiacfoam plugin as a **dev/test dependency** (entry-point
  package, matching the OmniDriver multi-repo plan), and
  `legacy_default_driver_context` stays as-is; or (b) the default becomes
  `GenericOpenFOAMPlugin` (already exists, `core/generic_plugin.py:27`) and
  cardiac-default behavior becomes explicitly opt-in.
- Either way: `python3 -m pytest openfoam_driver/tests -q` must go from 8
  collection errors to 0 before Tasks 1-4 are safe to attempt — you cannot
  verify "zero behavioral change" against a suite that doesn't run.

### Task 1 (was "expand plugin.yaml schema"): Extend the existing role vocabulary, don't add a parallel one
- Files: `core/generic-plugin.yaml` (docs), `core/plugin_profile.py` (add
  role validation against the documented enum — currently unchecked).
- No new top-level YAML section.

### Task 2 — dropped (see §3). If anything, rename to "confirm
`_case_is_runnable`/`_is_case_directory` stay capability-routed" and leave
the code alone.

### Task 3 (was "abstract provenance parsing"): Make `provenance_inputs.py` use the role lookup it's already documented as consuming
- Target: `core/runtime/provenance_inputs.py::_select_start_time` (line 104)
  and `walk_roots` (line 327) — replace the literal
  `case_root / "system" / "controlDict"` and `"system"`/`"constant"` strings
  with a lookup against `case_files` filtered by
  `role == "openfoam.control_dict"` (mirror the pattern already in
  `tutorial_contracts.py:120-127`).
- Real callers to re-check after the change: `provenance_inputs.py` imports
  `read_foam_entry` from `mutators.py` (line 83) — that stays, since parsing
  the *contents* of controlDict is still legitimately `foamlib`'s job; only
  the *path* becomes role-resolved.
- Tests that pin current behavior and must be updated in lockstep:
  **`test_provenance_inputs.py`** (347 lines, 12 literal `system/`/`constant/`
  references) and **`test_trust_boundary_end_to_end.py`** (757 lines, 7
  literal references, security-sensitive — treat as the regression gate, not
  an afterthought).

### Task 3b (new, was buried in Task 3 in v1 but is really a separate module): `mutators.py`
- The v1 plan's Problem section calls this out as its own item (#3) but the
  Task list gives it one sentence folded into Task 3. It needs its own task
  because it has **4 real call sites**, none named in v1:
  `core/specs/apply_overrides.py:54`, `core/specs/utils.py:5`,
  `core/runtime/provenance_inputs.py:83`, `core/runtime/parallel_execution.py:38`.
- Tests: `test_mutators.py` (754 lines) is the main coverage;
  `test_mutators_differential.py` (24 lines) looks like a golden/parity check
  against real `foamlib` semantics — confirm what it's actually diffing
  against before moving anything, given this project's prior incident
  (see root `CLAUDE.md`) of an ad-hoc script silently flipping a tracked
  `fvSchemes` default undetected until manual audit. A thin differential test
  is exactly the kind of check that goes stale silently.

### Task 4 (mesh provisioning): trace the real caller before moving the file
- `core/specs/mesh_provisioning.py::default_block_mesh_dict_text` /
  `cell_counts_from_dx` have **no confirmed production caller** — only
  `test_mesh_provisioning.py` and `test_sweep_materialize.py` call them
  directly. The one plausible production path
  (`sweep_materialize.py::_materialize_case_legacy`) is dead code per §3.
- Actual materialization goes through
  `driver_context.capabilities.sweep_materializer.materialize(...)`, a
  capability resolved dynamically — confirm which concrete class implements
  it (this repo's stripped `plugins/` doesn't currently have one, consistent
  with §0) before writing "move this to the OpenFOAM plugin," since there may
  currently be nothing on the other end to move it to.
- `core/specs/mesh_geometry.py:132` (`case_root / "constant"`) and
  `core/specs/apply_overrides.py:331` (`system/controlDict`) are two more
  hardcoded-path sites in the same family the v1 plan never named — fold into
  this task or split out explicitly, but don't leave them unlisted a second
  time.

## 5. Net changes from v1

- **Added:** Task 0 (compatibility.py default-context breakage — currently
  blocking, not proposed).
- **Removed:** Task 2 as written (wrong file, wrong function, already-closed
  decision).
- **Corrected:** Task 1 reuses `case_profile.dictionaries[].role` instead of
  inventing `environment_rules`.
- **Split:** `mutators.py` gets its own task (3b) instead of one sentence
  inside Task 3.
- **Grounded:** every remaining task now names its real callers and the
  specific test files whose literal path assertions will need to change.
