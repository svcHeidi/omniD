# Migration status: cardiacFoam's driverFOAM → omniD

**Round 1 (the bulk copy) is DONE. The collection blocker that stood in
front of round 2 is CLOSED — §2. Round 2 scope is §3, and §2 turned up
evidence of just how large §3's first item actually is.**

The Python orchestrator was developed inside
`noFrontendCardiacFoam/applications/scripts/driverFoam`. Because the C++
OpenFOAM environment is heavy, only the Python framework moves here, split into
three decoupled packages so that projects other than cardiacFoam can drive their
own solvers with it.

## 1. The architecture (built, not planned)

| package | contains | rule |
|---|---|---|
| `omnidriver` | DAG execution, schemas, provenance, the plugin contract | zero OpenFOAM vocabulary, zero physics rules |
| `omnidriver-openfoam` | `foamlib` mutators, mesh provisioning, OpenFOAM parsing | depends on core; knows no cardiology |
| `omnidriver-cardiacfoam` | electrophysiology, ionic models, the cardiac plugin | depends on both |

Round 1 delivered all three, plus cross-package entry-point discovery
(`dfa07d2`), a `core/` subdirectory free of `foamlib`/OpenFOAM imports
(`a2eb34b`, `39e56d1`, `59fd6a2` — note this holds for `core/`, NOT for the
package: see §2), marker-based path resolution replacing
`Path(__file__).parents[N]` (`6a105d8`), utility manifests as package data
(`5114623`), and GitHub Actions CI (`6cff329`).

## 2. RESOLVED: core installs and collects alone with zero errors

*(The previous blocker in this slot — `NameError: name 'DictEntry' is not
defined` on Python < 3.14 — was fixed in `7a4be70` and `078afd4`. The
`test-openfoam` and `test-cardiacfoam` jobs were already genuinely green: 107
and 292 passed on a real 3.13 interpreter. `test-core` was not — 20 collection
errors, then 14 after `cli.py` was fixed in `f51387b`.)*

`cli.py` imported `omnidriver.openfoam` unconditionally at module scope,
making the entire CLI surface (`plan`, `run`, `step`, `sweep-plan`,
`sweep-run`) unreachable in a core-only install; `f51387b` moved that import
behind a plugin capability seam. The remaining 14 collection errors were each
either misplaced (a sibling's test living in core's tree) or mixed (a clean
core test and a sibling-dependent one sharing a file) — **no file met the
"genuine cross-package integration, needs a fourth CI job" bar** this section
used to anticipate. All 14 were resolved by moving or splitting test files;
see `docs/superpowers/plans/2026-08-27-test-core-decoupling.md` for the exact
per-file disposition and the reasoning behind each call.

Verify against a core-only virtualenv, on the Python 3.13 floor, not this
repo's own `.venv` — it has all three packages installed (and, separately,
was found mid-migration to hold a *stale* editable install of the pre-rename
`omnidriver-cardiac` distribution rather than `omnidriver-cardiacfoam`; fixed
in the venv itself, not tracked in git, so any other clone's `.venv` will
need the same `pip uninstall omnidriver-cardiac && pip install -e
packages/omnidriver-cardiacfoam` if it predates the rename).

```
rm -rf /tmp/core_only_venv_check
/opt/homebrew/bin/python3.13 -m venv /tmp/core_only_venv_check
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" pytest
python -m pytest packages/omnidriver/tests --collect-only -q   # 0 errors
```

### Collecting cleanly is not the same as running cleanly

Running the collected core suite standalone (not `--collect-only`) surfaces
**161 failures, 506 passed, 89 skipped** — all traced to the same root cause:
`compatibility.legacy_default_driver_context()` hard-imports
`omnidriver.cardiacfoam.cardiacfoam_plugin.CardiacFoamPlugin` and is still the
silent default behind `resolve_public_driver_context()`, which many core
functions call when a caller omits an explicit `DriverContext`. This is
exactly §3's first row ("explicit `DriverContext` in core") — this run is
concrete evidence of its blast radius in *this* repo, not a new defect and
not something this collection-error cleanup was scoped to fix. Two tests
that looked core-safe on import inspection alone
(`test_mesh_adapter_flags_non_si`, `test_exempt_short_circuits_unit_domain`)
turned out to need `omnidriver.openfoam` installed even when passed an
explicit `generic_openfoam_context()` — core's own
`_mesh_geometry_diagnostics` delegates its default detection backend to
`omnidriver.openfoam.mesh_geometry` (`compatibility.py:261`) — so they moved
to `omnidriver-openfoam` instead of staying in core; import inspection alone
is not sufficient to categorize a test, only running it standalone is.

Two follow-ups were identified during the cleanup but deliberately left
undone (judgment calls about test doubles, not test-tree surgery):
- Three tests now in `omnidriver-cardiacfoam/tests/test_strict_planning.py`
  (`test_strict_plan_fails_on_unknown_workflow_command`,
  `test_strict_plan_fails_on_unknown_workflow_dependency`,
  `test_strict_dict_key_scanner_fails_on_unallowlisted_key`) use
  `CardiacFoamPlugin` only as a convenient concrete fixture for generic
  strict-planning/scanner behavior — swapping them to `GenericOpenFOAMPlugin`
  or `plugins.minimal_plugin.MinimalOpenFOAMPlugin` would let them move back
  to core.
- `packages/omnidriver-cardiacfoam/tests/plugins/minimal_plugin.py` duplicates
  `packages/omnidriver/tests/plugins/minimal_plugin.py` in spirit (both
  implement the same no-domain plugin contract) — worth deduplicating.

### Do not "fix" the §3 gap by installing all three packages in the core job

It would go green immediately and **delete the only automated check that core
stands alone** — the same reasoning that applied to `cli.py` above applies to
every one of the 161 failures: the fix is converting call sites to accept an
explicit `DriverContext`, not widening what the core CI job installs.

## 3. Round 2 — what still has to come across

Measured 2026-08-27 against `noFrontendCardiacFoam` at `5fda4006`. Each is
present there and absent here:

| work | why it matters |
|---|---|
| **explicit `DriverContext` in core** — 21 call sites converted | 7 core files here still call `resolve_public_driver_context`, silently becoming cardiacFoam whenever a caller omits a context. A missed site does not raise; it keeps working and stays cardiac — until cardiacfoam isn't installed, at which point it doesn't keep working: a core-only `pytest packages/omnidriver/tests` run (§2) hits this in 161 places (506 passed, 89 skipped). Ported with a static AST guard. |
| **`get_phases()` optional hook** | Without it, `primary_phase()` returns `None` for any plugin whose phase words differ from cardiac's four, and validation *silently skips* required-field and enum checks while writing entries into a `"physics"` slice the plugin never declared. The only silent-wrong defect in the set. |
| **retire the 20 cardiac-gated `legacy_*` branches** | `compatibility.py` here still branches on `plugin_id == "org.cardiacfoam"` in 20 places. They became unreachable there once cardiacFoam implemented all 15 optional hooks; deletion was gated on instrumenting each branch and confirming zero were reachable across the full suite. |
| **drop unused declared dependencies** | `omnidriver-cardiacfoam` declares `numpy`, `omnidriver-openfoam` declares `gmsh` — neither is imported anywhere here. `gmsh` is a workflow *binary* name, not a Python import, and pulls a ~100MB wheel. Core's deps are already clean. A guard test asserting every declared distribution is imported comes with it. |

## 4. How to port — no shared history

**The two repositories share no common ancestor.** This one begins at its own
initial commit, so `cherry-pick`, `merge`, and `rebase` are unavailable. Every
port is a deliberate file-level copy followed by a test run here.

Both trees have moved independently, and the same fix has already been made
twice by accident — the dead `initialODEStep` key was removed there in
`a9ee8462` and again here in `0f4d877`. **Check the other tree before fixing
anything in either.**

The flow is not one-way: this repo has solved things the cardiacFoam tree has
not (see §1). Neither side is simply ahead.

## 5. Where each repository's work belongs

- **here** — the orchestrator. All plugin, packaging, and solver-integration work.
- **`noFrontendCardiacFoam`** — the cardiacFoam solver, its C++ sources and
  utilities, its tutorials and cases. Physics content changes belong there.

## Related

- `noFrontendCardiacFoam/applications/scripts/driverFoam/MIGRATION.md` — the
  sending side's view
- `MIGRATION_AUDIT_v2.md`, `future/` — this repo's own decoupling records
