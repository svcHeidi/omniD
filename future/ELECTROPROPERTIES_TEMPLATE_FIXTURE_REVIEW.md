# `electroProperties` Template Fixture — Placement and Staleness

**Status: investigated and largely resolved.** One deliberate gap remains,
left open on purpose (see §4).

## 1. Placement

The bundled fallback template lives at
`packages/omnidriver-cardiac/src/omnidriver/cardiac/fixtures/template/constant/electroProperties`,
declared as `omnidriver-cardiac` package data. `test_template_contract.py::_template_path()`
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
live tutorials, directly against the bundled fixture instead: 38 scoped
keys (after §4's fix; was 39), all but one addressable through
`validate_overrides`.

`$ELECTRO_MODEL_COEFFS.initialODEStep` (the myocardium-level key) was
**removed** — confirmed dead by pre-existing comments already in the repo
(`test_apply_overrides.py:66-68`): "zero reads in this repo or in OpenFOAM
... deleted from the tutorial dicts". The fixture, the now-deleted core
duplicate, and two worked examples in `override_schema.py`'s `--config`
schema help text (lines ~90, ~153) still referenced it after that removal —
all four fixed to match.

## 4. Remaining open gap

`$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.initialODEStep`
— the **Purkinje-network-scoped** sibling of the removed key — is still
live in the fixture and still not catalog-addressable. Left in place
deliberately, not removed: unlike the myocardium-level key, this one has
not been checked against the Purkinje network's own ODE integrator (a
different C++ code path from the myocardium `ODESolver.C:70` reader the
removed key was confirmed dead against). It may be genuinely read there, or
equally dead — undetermined. Marked with an inline comment at the fixture
site pointing back to this file. Resolving it means checking the Purkinje
solver's own ODE-step reader before deciding remove-or-catalog, same as was
done for the myocardium-level key.
