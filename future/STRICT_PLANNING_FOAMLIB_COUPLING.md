# `strict_planning.py` Had a Hard, Unconditional `foamlib` Dependency

**Status: resolved.** See §6 for what actually shipped. §1-5 are the
original finding and are kept as the record of how the problem was
discovered and why it wasn't a trivial fix — read them for context, but the
code they describe (`omnidriver.core` importing `omnidriver.openfoam`
directly) no longer exists.

## 1. What's coupled

`core/strict_planning.py` (the strict planner — `driverFoam plan --strict`,
per `KEY_FILES.md`: "the strict planner... produces machine-readable JSON
with readiness score, diagnostics, and launch command") has two **top-level,
unconditional** imports:

```python
from openfoam_driver.core.specs.function_object_fields import function_object_field_diagnostics
from openfoam_driver.core.specs.case_dict_keys import case_dict_key_diagnostics as _case_dict_key_diagnostics
```

Both target modules import `foamlib` directly and unconditionally:

- `core/specs/function_object_fields.py:38` — `from foamlib import FoamFile`,
  used in `function_object_field_diagnostics()` to validate declared function
  objects against real field values in a case's dict files.
- `core/specs/case_dict_keys.py:144` — `from foamlib import FoamFile` (inside
  `case_dict_key_diagnostics()`), used to scan a case's actual dict keys
  against the catalog.

This is unlike `mesh_provisioning.py` (Task 4), which had **no confirmed
production caller** and could just move. These two modules are *load-bearing*
for the strict planner — moving them to `omnidriver-openfoam` would make
`strict_planning.py` import from `omnidriver.openfoam` at module scope,
violating the "core MUST NOT import openfoam" constraint the instant anyone
imports the planner. I left them in place in
`packages/omnidriver/src/omnidriver/core/specs/` (copied as part of Task 3's
bulk `core/` copy — not removed from the exclusion list) rather than break
the copy immediately.

## 2. Why this isn't a Task 5 copy-paste

Task 5 solves the same *shape* of problem for `provenance_inputs.py`, by
adding `ConfigValueCapability.read(path, key) -> str | None` — a single
plugin-routed value read. `function_object_field_diagnostics()` and
`case_dict_key_diagnostics()` are not single-value reads: they return
structured diagnostic collections (readiness findings, mismatched-key
reports) built from walking and interpreting a case's *entire* dict tree
against a catalog. Turning that into a capability means designing a richer
protocol — something like:

```python
class DictDiagnosticsCapability(Protocol):
    def function_object_field_diagnostics(self, case_root, resolved, ...): ...
    def case_dict_key_diagnostics(self, case_root, catalog, ...): ...
```

implemented by `omnidriver.openfoam` the same way `ConfigValueCapability`
is — but the exact signatures need to be derived from how `strict_planning.py`
actually calls them today (arguments, return shape, how the JSON diagnostic
output serializes them), not guessed. That's real interface-design work
against the strict planner specifically, not a mechanical extraction.

## 3. Related, smaller finding in the same grep pass: `tutorial_contracts.py`

`core/tutorial_contracts.py` is mostly fine — it already does the
role-based lookup pattern correctly at lines 120-127 (`rule.role.startswith("openfoam.")`,
the pattern `MIGRATION_AUDIT_v2.md` §2 pointed at as the model to follow).
But the *same file* also has three untouched hardcoded literals that don't
go through that mechanism:

- line 109: `_glob_relpaths(case_root / "system", "blockMeshDict*")`
- line 143: `_glob_relpaths(case_root / "constant", "*")`
- line 144: `_glob_relpaths(case_root / "system", "*")`

Unlike the `strict_planning.py` issue, this one doesn't need a new
capability — it needs the exact same `case_files` role-filter this file
already uses two lines away, just applied to these three spots too. This is
small enough to fold into Task 6 (the provenance-role-lookup task) when that
task is reached, rather than needing its own design pass.

## 4. Suggested next steps

- Before Task 6 (or as part of it), read `strict_planning.py`'s actual call
  sites for both diagnostic functions end-to-end to derive the real
  parameter/return shape needed for a `DictDiagnosticsCapability`.
- Decide whether `function_object_field_diagnostics` and
  `case_dict_key_diagnostics` should become one capability or two — they're
  both "scan the case's dict files against a catalog," but check whether
  callers ever need one without the other before merging them into a single
  protocol.
- Fold `tutorial_contracts.py`'s three hardcoded literals into Task 6 as a
  small addendum — reuse `required_rules()`/`case_files` filtering already
  present in the same file.
- Until this is resolved, `omnidriver.core` still contains two files that
  import `foamlib` — the "zero OpenFOAM vocabulary in core" rule in
  `ARCHITECTURE.md`'s Global Constraints is **not yet satisfied**. Don't
  claim Task 3/7 "core is clean" without re-running the `foamlib` grep from
  Task 3 Step 4 and getting zero hits.

## 5. What Task 4 actually did to unblock this (not to fix it)

Task 4's own verification (installing all three packages and importing
`omnidriver.cli`) turned up a second, more fundamental bug caused by the
`strict_planning.py` coupling: `omnidriver.core.__init__.py` had been copied
from the monorepo's `openfoam_driver/__init__.py` verbatim, including its
eager re-exports (`from .introspection import describe_entry,
describe_tutorial`). `core.introspection` imports `core.strict_planning`,
which — once `environment_preflight.py` moved to `omnidriver.openfoam` in
this same task — needed `omnidriver.openfoam`, which itself needs
`omnidriver.core.planning_types`. That's a real circular import:
`omnidriver.core.__init__` → `strict_planning` → `omnidriver.openfoam` →
`omnidriver.core.planning_types`, which re-enters `omnidriver.core.__init__`
mid-execution.

Separately — and this is the more consequential bug — `packages/omnidriver/src/omnidriver/__init__.py`
also existed at all (also copied verbatim from the monorepo). A real
`__init__.py` at that exact path makes `omnidriver` a **regular** package
rather than a PEP 420 namespace package, which means its `__path__` is fixed
to `packages/omnidriver/src/omnidriver/` only — Python never looks in
`packages/omnidriver-openfoam/src/omnidriver/` or
`packages/omnidriver-cardiacfoam/src/omnidriver/` for `omnidriver.openfoam` /
`omnidriver.cardiacfoam` at all. This silently broke the entire point of the
three-package split from the moment Task 3 copied that file, not just the
`strict_planning.py` coupling — every cross-package import would have failed
`ModuleNotFoundError: No module named 'omnidriver.openfoam'` regardless of
whether `strict_planning.py` was involved. Fixed by deleting
`packages/omnidriver/src/omnidriver/__init__.py` entirely (confirmed no
package ships one at that path now) and moving its re-exports into
`core/__init__.py` — then dropping those re-exports too, once they turned
out to be the thing causing the circular import, since nothing outside the
package actually consumed them (checked: one caller did `import omnidriver`
with zero attribute access).

With both of those fixed, the three `core → openfoam` imports the original
finding (§1) described became merely explicit instead of broken:
`strict_planning.py:42` (`environment_preflight`), `strict_planning.py:73`
(`mesh_geometry`), and `provenance_inputs.py:82-83`
(`environment_preflight`, `mutators`) all now import
`omnidriver.openfoam.*` directly and absolutely. `omnidriver-openfoam`'s own
test suite passes cleanly against this (100 passed, 59 skipped, 0 failed).
**This makes the boundary violation in §1 real and observable rather than a
buried transitive dependency** — which is arguably useful (it's now one
`grep` away from being found and counted) but is still a violation, not a
fix. Anyone picking up §2's capability-design work should start by re-running:

```bash
grep -rn "^from omnidriver\.openfoam\|^import omnidriver\.openfoam" packages/omnidriver/src --include="*.py"
```

and treating every hit as an open item.

## 6. What actually shipped

The full capability-design work §2 called for was done. `omnidriver.core`
now has **zero** runtime imports of `omnidriver.openfoam` and **zero**
runtime imports of `foamlib`, confirmed by:

```bash
grep -rn "^from omnidriver\.openfoam\|^import omnidriver\.openfoam" packages/omnidriver/src/omnidriver/core --include="*.py"   # no hits
grep -rln "foamlib" packages/omnidriver/src --include="*.py"   # only docstring mentions, no import foamlib
```

Three new capabilities closed the six real call sites found (more than the
three originally documented in §1 — `provenance_inputs.py` and
`sweep_runner.py` also had direct openfoam imports the original grep missed):

- **`EnvironmentPreflightCapability`** (`diagnostics`, `configure`) —
  replaces `strict_planning.py`'s and `cli.py`'s direct
  `environment_preflight._environment_diagnostics` calls, and
  `sweep_runner.py`'s direct `openfoam_environment.configure_plugin_environment`
  call. Fallback: `legacy_environment_diagnostics` /
  `legacy_configured_environment` in `compatibility.py`, same "preserve
  historical behavior, unconditionally OpenFOAM until a plugin opts in"
  pattern as every other legacy fallback in that file.
- **`MeshDiagnosticPolicyCapability.base_geometry_diagnostics`** (new method
  on the existing capability) — replaces `strict_planning.py`'s direct
  `mesh_geometry.mesh_geometry_diagnostics` call. Worth noting: the
  capability's own docstring had claimed "core classifies the physical scale
  of every polyMesh region" — that was never true; polyMesh parsing is
  OpenFOAM-specific by definition. The docstring was wrong from the start,
  just invisible while core and the OpenFOAM environment were one package.
- **`DictDiagnosticsCapability`** (`function_object_fields`, `case_dict_keys`)
  — new capability, exactly as sketched in §2. `function_object_fields.py`
  and `case_dict_keys.py` moved from `core/specs/` to
  `omnidriver-openfoam/src/omnidriver/openfoam/` (with their two test files),
  closing the `foamlib` import that lived in core's own source, not just an
  import of the openfoam package.

**Bonus fix, not a capability:** `provenance_inputs.py`'s and
`strict_planning.py`'s `_MPI_LAUNCHERS`/`_unwrap_mpi_program` imports turned
out to be a plain miscategorization, not a real boundary crossing — the MPI
launcher-recognition logic has zero OpenFOAM-specific content (no `FOAM_*`,
no bashrc). Moved to `core/runtime/workflow.py` (core, correctly) instead of
capability-wrapping something that was never openfoam-specific in the first
place; `environment_preflight.py` now imports it back from core.

**Deliberately left as-is, not part of this fix:**

- ~~`omnidriver/cli.py` still has two direct `omnidriver.openfoam` imports~~
  **Corrected 2026-09-03: fixed, not deliberate any more.** `cli.py` now reaches
  both through capabilities (`environment_preflight.load`,
  `override_scopes.apply`); it has zero module-scope `omnidriver.openfoam`
  imports, and `scripts/check-import-boundaries.py` records the same fix. The
  flag was also renamed `--environment-bashrc`. The original reasoning, which
  this section recorded as a scope decision, is kept below for the record:
- `omnidriver/cli.py` had two direct `omnidriver.openfoam` imports
  (`load_openfoam_environment` for bashrc sourcing, `apply_overrides`/
  `validate_overrides`/`OverrideError` for the `--apply` flag). Scope
  decision: `cli.py` is the leaf CLI entry point, not part of `omnidriver.core`
  the library — and it already isn't solver-agnostic at the UX level (its own
  `--openfoam-bashrc` flag name is OpenFOAM-specific), so fixing its imports
  alone would be cosmetic without also redesigning the CLI's flag surface to
  be plugin-driven, which is out of scope here.
- `core/runtime/workflow.py::_is_installed_openfoam_app` hardcodes
  `FOAM_APPBIN`/`FOAM_USER_APPBIN` env var names inline — no import, so it
  didn't show up in any `grep openfoam` sweep, but it's the same "core
  assumes OpenFOAM" category of issue. Not fixed: `validate_workflow_commands`
  currently treats this check as unconditional regardless of which plugin
  (or no plugin) is active — see `test_an_installed_openfoam_app_is_authorized_whatever_the_plugin` —
  and turning it into a capability would change that "even with no context"
  behavior, which is a real product decision, not a mechanical extraction.
  Flagging for whoever picks this up next.

Full three-package suite after this work: 1432 passed, 293 skipped, 1 failed
(the same pre-existing `test_a_factory_failure_fails_one_case_not_the_command`
failure noted throughout this migration — confirmed unrelated, reproduces
identically against the untouched source monorepo).
