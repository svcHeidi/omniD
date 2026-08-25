# `UTILITY_CATALOG` Is Empty in the Standalone Repo

**Status: open, not fixed.** `omnidriver.core.utility_catalog.UTILITY_CATALOG`
loads from `UTILITIES_ROOT = <repo_root>/utilities`, walking
`utilities/*/utility.manifest.toml`. In the monorepo that root is
`applications/utilities/` — 12 lightweight TOML sidecars describing
cardiac-domain C++ utilities (`1DgraphToFoam`, `recomputePseudoECG`,
`runPurkinjeGraph`, etc.), no C++ source required to load them, just the
`.toml` files themselves.

This standalone repo doesn't ship that directory (per `GITHUB_MIGRATION.md`,
only the Python framework is migrated here), so `UTILITY_CATALOG` resolves
to an empty dict. `packages/omnidriver/tests/core/test_utility_catalog_export.py`
is now `skip_without_monorepo`-guarded rather than left to fail — several of
its assertions were written to fail loudly specifically when the catalog is
unexpectedly empty (`assert expected > 0, "... test is vacuous"`), which is
exactly what's happening here.

**Not fixed because it's a real design decision, not a mechanical bug:** the
12 manifests are cardiac-domain content (Purkinje/ECG-specific), so by the
same reasoning already applied to the `electroProperties` template fixture
(see `future/ELECTROPROPERTIES_TEMPLATE_FIXTURE_REVIEW.md`), they arguably
belong copied into `omnidriver-cardiac` as package data — but
`UTILITIES_ROOT`/`load_utility_manifests` currently live in `omnidriver.core`
with a single hardcoded root, not a plugin-declared one. Making the root
plugin-configurable (so `omnidriver-cardiac` can point core at its own
bundled manifests) is the kind of core/plugin boundary change this migration
has been making elsewhere (see the `ConfigValueCapability` work), but doing
it here wasn't started — just flagged.

## Suggested next steps

- Decide: copy the 12 `.toml` sidecars into
  `packages/omnidriver-cardiac/src/omnidriver/cardiac/utilities/` as package
  data, and make `UTILITIES_ROOT` resolve via a plugin capability (mirroring
  `ConfigValueCapability`'s shape) instead of a hardcoded core-relative path.
- Or: accept `UTILITY_CATALOG` as monorepo-only functionality for now and
  leave the guard in place.
- Either way, `scripts/export-utility-catalog.py` needs revisiting once
  decided — it currently runs without error and just exports an empty list
  in the standalone repo.
