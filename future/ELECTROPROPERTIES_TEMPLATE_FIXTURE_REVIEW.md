# `electroProperties` Template Fixture — Placement and Staleness Unverified

**Status: open, not investigated beyond locating the consumers.** Parked here
during the monorepo→packages migration (see
`docs/superpowers/plans/2026-08-25-monorepo-package-migration.md`, Task 2)
rather than chased down, so this doesn't get silently decided in passing.

## 1. What moved and why

The monorepo ships a bundled fallback template at
`applications/scripts/driverFoam/openfoam_driver/core/specs/fixtures/template/constant/electroProperties`,
used when the live `tutorials/template/constant/electroProperties` tree isn't
available (standalone / CI installs without the full monorepo checkout).

It was declared as **core** package data in the old root `pyproject.toml`:

```toml
"openfoam_driver.core.specs" = ["fixtures/template/constant/*"]
```

but its content — an `electroProperties` dict — is cardiac-domain data, not
solver-agnostic. During the package split I moved it to
`packages/omnidriver-cardiac/src/omnidriver/cardiac/fixtures/template/constant/electroProperties`
and updated `packages/omnidriver-cardiac/pyproject.toml`'s package-data to
match. I only fixed the one caller I was actively touching,
`packages/omnidriver-cardiac/tests/test_template_contract.py`'s
`_template_path()`, which previously found it via a hardcoded
`Path(__file__).parents[3]` — a depth that assumed the old
`tests/plugins/cardiacfoam/` nesting and silently breaks once that directory
was flattened to `tests/` directly. Rewrote it to resolve via the installed
`omnidriver.cardiac` package's own `__file__` instead of a directory-depth
count.

## 2. What's unverified

**I have not confirmed this fixture is still accurate or still needed.**
Specifically:

- Whether the `electroProperties` keys/values in the fixture still match the
  current dict-key catalog (`omnidriver.cardiac.dict_entries_catalog` /
  `common_dict_entries.py`) — it may predate recent catalog changes and be
  silently stale, since nothing appears to regenerate it automatically.
- Whether Tier 1 (the live `tutorials/template/` monorepo path) is what
  actually gets exercised in every real test run, making Tier 2 (this bundled
  fixture) effectively dead weight that only fires in a standalone/CI context
  nobody currently runs.

## 3. Other consumers found but not yet checked

A grep for `fixtures/template` / `template...electroProperties` while
writing this note turned up two more references I have **not** yet
inspected, beyond the one test I fixed:

- `packages/omnidriver-cardiac/src/omnidriver/cardiac/tutorials/heart_solver_comparison.py`
  (copied wholesale in Task 2 — may contain its own hardcoded path assuming
  the old directory depth, same class of bug as the test had; not checked).
- `tests/core/test_tutorial_keys_are_catalog_addressable.py` in the monorepo
  — this one lives under `tests/core/`, meaning it's a **core-subject** test
  (deferred to Task 3's bulk core-test copy, not yet copied at all as of
  this note) that also depends on cardiac-domain fixture data. If it needs
  this fixture at runtime, that's a real cross-package test dependency
  (`omnidriver` tests needing `omnidriver-cardiac` package data) worth
  deciding deliberately rather than discovering as a failure during Task 6/7
  verification.

## 4. Suggested next steps

- Before trusting Task 7's full-suite pytest run, check whether
  `test_template_contract.py` and `test_tutorial_keys_are_catalog_addressable.py`
  actually pass with the moved fixture, or whether they were silently
  skipped (both use `skip_without_monorepo`-style guards elsewhere in the
  file, worth confirming this particular fixture path isn't also
  conditionally skipped in a way that's been masking staleness).
- Diff the fixture's `electroProperties` keys against
  `omnidriver.cardiac.dict_entries_catalog`'s current catalog to confirm it
  isn't stale.
- Check `heart_solver_comparison.py` for the same `parents[N]`-depth fragility
  pattern the test had.
- Decide, deliberately, whether this fixture is core-owned bootstrap data
  (available to any plugin) or genuinely cardiac-only — the fact it's
  referenced from a `tests/core/` test suggests someone originally treated it
  as core-shared, which conflicts with the "cardiac-domain data" judgment
  call made in Task 2. Worth resolving before Task 6/7, not after.
