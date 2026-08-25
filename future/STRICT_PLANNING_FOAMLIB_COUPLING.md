# `strict_planning.py` Has a Hard, Unconditional `foamlib` Dependency

**Status: open, not fixed.** Found during Task 3 (bulk-copy core) of
`docs/superpowers/plans/2026-08-25-monorepo-package-migration.md`'s Step 4
verification grep, which turned up more core/OpenFOAM coupling than the plan
anticipated. Parked rather than fixed in place because the fix isn't a file
move — it's the same class of design work as Task 5's `ConfigValueCapability`,
but for a richer, harder interface, on the single most load-bearing file in
core.

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
