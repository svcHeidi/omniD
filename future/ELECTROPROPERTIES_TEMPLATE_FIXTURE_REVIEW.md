# `electroProperties` Template Fixture — Placement and Staleness

**Status: resolved.**

## 1. Placement

The bundled fallback template lives at
`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/fixtures/template/constant/electroProperties`,
declared as `omnidriver-cardiacfoam` package data. `test_template_contract.py::_template_path()`
resolves it in two tiers: Tier 1, a live `tutorials/template/constant/electroProperties`
found by walking up from the test file (only exists inside the full
cardiacFoam monorepo checkout); Tier 2, this bundled fixture.

This standalone repo has no `tutorials/` sibling, so Tier 1 never fires here
— Tier 2 is not dead weight, it is the *only* path this repo's test suite
ever exercises. Confirmed: `test_template_uses_code_backed_selector_keys`
runs unconditionally (no skip guard) and passes against the bundled fixture
on every run.

A byte-identical, **unreferenced** duplicate of this fixture also existed at
`packages/omnidriver/src/omnidriver/core/specs/fixtures/template/constant/electroProperties`
— left behind by the Task 3 bulk-copy commit, never declared in
`packages/omnidriver/pyproject.toml`'s package-data, never imported by any
code. Cardiac-domain content sitting in core's source tree, unreferenced or
not, is exactly the kind of leak this migration has been closing elsewhere
(see `future/UTILITY_CATALOG_STANDALONE_GAP.md`). Deleted.

## 2. The other consumers

- `heart_solver_comparison.py` — a false alarm. Its `"electroProperties"`
  references are unrelated: a *different* electroProperties file, copied at
  runtime from `case_root/setup/solverVariants/<variant>/` into a live
  tutorial case. No `Path(__file__).parents[N]` fragility, no connection to
  the bundled fixture.
- `test_tutorial_keys_are_catalog_addressable.py` (now in
  `packages/omnidriver/tests/core/`) — also doesn't touch the bundled
  fixture. It walks the *monorepo's live* `tutorials/` tree via
  `git ls-files`, and correctly self-skips here via `skip_without_monorepo`.
  Not the cross-package test dependency the original note worried it might
  be — it needs the monorepo checkout, not any package data.

## 3. Staleness check

Ran the same scoped-key-extraction + catalog-addressability check
`test_tutorial_keys_are_catalog_addressable.py` uses against the monorepo's
live tutorials, directly against the bundled fixture instead: originally 39
scoped keys, 2 not addressable through `validate_overrides` — both named
`initialODEStep`, one at the myocardium-level scope
(`$ELECTRO_MODEL_COEFFS.initialODEStep`), one at the Purkinje-network scope
(`$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.initialODEStep`).

Both removed. The myocardium-level key was already confirmed dead by
pre-existing comments in the repo (`test_apply_overrides.py:66-68`): "zero
reads in this repo or in OpenFOAM ... deleted from the tutorial dicts". The
Purkinje-scoped sibling was judged the same — dead, same key, same
treatment — and removed too rather than kept as a partially-resolved
special case. The fixture, the now-deleted core duplicate, and two worked
examples in `override_schema.py`'s `--config` schema help text (lines ~90,
~153) all referenced the myocardium-level key after its removal from the
catalog — all fixed to match. Re-running the same check now finds 37 scoped
keys, all addressable.
