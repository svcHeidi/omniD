# `UTILITY_CATALOG` Was Empty in the Standalone Repo

**Status: resolved.** The 12 `utility.manifest.toml` sidecars
(`1DgraphToFoam`, `recomputePseudoECG`, `runPurkinjeGraph`, etc.) are now
bundled as package data at
`packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/utilities/<name>/utility.manifest.toml`,
declared in that package's `pyproject.toml`
(`[tool.setuptools.package-data]`). They ship with an `omnidriver-cardiacfoam`
install regardless of whether a full cardiacFoam monorepo checkout is
present.

## What changed

- `omnidriver.core.utility_catalog` no longer owns a root or an eager
  singleton. `UTILITIES_ROOT` and `UTILITY_CATALOG` are gone; the module now
  only exports `load_utility_manifests(utilities_root: Path)` and the
  `UtilityManifest`/`UtilityFlag`/`PositionalArg`/`ProducesEntry` dataclasses
  — generic parsing machinery with zero knowledge of any plugin's bundled
  path, matching the `dictionaries`/`tutorials`/`named_catalogs` capability
  seams' existing core/plugin split.
- `omnidriver-cardiacfoam/command_authorization.py::utility_roots()` resolves its
  own bundled `Path(__file__).parent / "utilities"` instead of importing a
  core constant. The `command_authorization` capability seam
  (`get_utility_manifests`/`get_utility_roots`, already listed in
  ARCHITECTURE.md) was already correctly plugin-routed end-to-end for the
  three real runtime consumers (`strict_planning.py`, `runtime/artifacts.py`,
  `runtime/workflow.py`) — this was the one place it still reached back into
  core for its root.
- `scripts/export-utility-catalog.py` no longer imports `UTILITY_CATALOG`
  directly (a second, non-plugin-routed path that bypassed the capability
  system entirely). It now goes through
  `driver_context.capabilities.command_authorization`, with a `--plugin` flag
  matching `export-report-catalog.py`'s convention (defaults to cardiac,
  `--plugin none` for generic OpenFOAM). `source_path` in the exported JSON
  is relativized against the plugin's own utility root, not a repo root.
- `packages/omnidriver/tests/core/test_utility_catalog_export.py` moved to
  `packages/omnidriver-cardiacfoam/tests/` (it tests cardiac-owned data through
  cardiac's own `utility_manifests()`) and dropped its
  `skip_without_monorepo` guard — the assertions that used to be vacuous
  (`assert expected > 0, "... test is vacuous"`) now run for real. Two tests
  in `packages/omnidriver/tests/core/test_command_authorization.py` that were
  monorepo-gated for the same reason are also unskipped;
  `test_plugin_utilities_root_matches_the_utility_catalog_root` (which
  asserted cardiac's root was *derived from* a core constant — no longer true
  by design) was replaced with
  `test_plugin_utility_root_is_its_own_bundled_data`.
- A `checkMeshGeometry`-manifest content test that had drifted into
  `omnidriver-openfoam/tests/core/test_mesh_geometry.py` (testing
  cardiac-domain package data from the openfoam package's suite) moved to
  `packages/omnidriver-cardiacfoam/tests/test_check_mesh_geometry_manifest.py`.

## Left as-is, noted in passing

`command_authorization.py`'s comment on `CARDIAC_AUXILIARY_COMMANDS` claims
`bathBidomainInterfaceMetrics` "ships no `utility.manifest.toml`" — the
monorepo source now has one. It was bundled along with the other 11 anyway;
harmless either way since `solver_commands()`/`auxiliary_commands()` and
`utility_manifests()` are authorized as a union, not required to be
disjoint. Whether `bathBidomainInterfaceMetrics` should now be removed from
`CARDIAC_AUXILIARY_COMMANDS` (since it's manifested) is a separate, small
decision left unmade here.
