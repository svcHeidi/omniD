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

Round 1 delivered all three, plus a `core/` subdirectory free of
`foamlib`/OpenFOAM imports (`a2eb34b`, `39e56d1`, `59fd6a2` — note this holds
for `core/`, NOT for the package: see §2), marker-based path resolution
replacing `Path(__file__).parents[N]` (`6a105d8`), utility manifests as package
data (`5114623`), and GitHub Actions CI (`6cff329`).

**Corrected 2026-08-27.** This list used to include "cross-package entry-point
discovery (`dfa07d2`)". It does not work. `dfa07d2` registered the `omnidriver`
console script and confirmed that `importlib.metadata` *reports* the
`omnidriver.plugins` group — it never touched
`core/plugin_discovery.py:59`, which still reads `ENTRY_POINT_GROUP =
"driverfoam.plugins"`. On a clean clone with all three packages installed,
`load_plugin_context("cardiacfoam")` raises `KeyError: No installed driverFOAM
plugin named 'cardiacfoam' in entry-point group 'driverfoam.plugins'`. The
legacy `driverFoam` tree is self-consistent on `driverfoam.plugins` and works;
this is a regression the rename introduced. Every discovery test monkeypatches
the `_entry_points()` seam, so nothing has ever read the constant. Fixed in §3.

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
repo's own `.venv` — it runs Python 3.14 (PEP 649 hides annotation-evaluation
bugs that break the 3.11/3.12 CI matrix) and has all three packages installed.

**Corrected 2026-08-27.** This paragraph used to say the stale pre-rename
`omnidriver-cardiac` editable install "was fixed in the venv itself". It was
not — both distributions are still installed there, and both export the
entry-point name `cardiacfoam`, so any discovery measurement taken in that venv
is meaningless. Run `pip uninstall omnidriver-cardiac`. Separately, the
untracked `cardiacfoam_tutorials_driver.egg-info` at the repo root injects a
broken `driverfoam.plugins` entry point into any process started from the repo
root, so run installed-behaviour checks from a neutral cwd.

```
rm -rf /tmp/core_only_venv_check
/opt/homebrew/bin/python3.13 -m venv /tmp/core_only_venv_check
source /tmp/core_only_venv_check/bin/activate
cd ~/omnidriver && pip install -q -e "packages/omnidriver[post]" pytest
python -m pytest packages/omnidriver/tests --collect-only -q   # 0 errors
```

### Collecting cleanly is not the same as running cleanly

Running the collected core suite standalone (not `--collect-only`) surfaces
**161 failures, 506 passed, 89 skipped**.

**Corrected 2026-08-27.** This paragraph used to say those were "all traced to
the same root cause". They are not — re-measured, they are four:

| count | cause |
|---|---|
| 130 | `omnidriver.cardiacfoam` — `legacy_default_driver_context()` behind `resolve_public_driver_context()`. The documented one; §3's first row. |
| 12 | `omnidriver.openfoam` — the **ungated** fallbacks at `compatibility.py:278` (`legacy_environment_diagnostics`) and `:545` (`legacy_config_value_reader`), plus one misplaced core test. Nothing in §3 covers these. |
| 8 | `regression_equivalence` — `f1651b7` moved that package to cardiacfoam and left `packages/omnidriver/tests/equivalence/protocol.py:28` importing it. A regression from this section's own cleanup, invisible to `--collect-only` because `test_protocol.py` imports inside its test methods. |
| 11 | subprocess failures in `scripts/export-*.py`, which resolve the implicit cardiac context one layer out. |

Only the first group is "not a new defect". The second shows core→openfoam is
its own leak, not a corollary of the cardiac default; the third was introduced
here. Two tests
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

Originally measured 2026-08-27 against `noFrontendCardiacFoam` at `5fda4006`.
**Re-verified the same day by an independent audit**, which confirmed three of
the four rows, sharpened the third, and found five items this section never
listed. The executable plan is
[`docs/superpowers/plans/2026-08-27-core-completion.md`](docs/superpowers/plans/2026-08-27-core-completion.md);
the ownership rule it serves is
[`future/ENVIRONMENT_CONTRACT.md`](future/ENVIRONMENT_CONTRACT.md).

### Ported from `driverFoam` (present there, absent here)

| work | status | why it matters |
|---|---|---|
| **explicit `DriverContext` in core** | verified | 7 core files / **18 call sites** still call `resolve_public_driver_context`, silently becoming cardiacFoam whenever a caller omits a context. A missed site does not raise; it keeps working and stays cardiac — until cardiacfoam isn't installed. Measured blast radius: `resolve_public_driver_context(None)` fires **35,395** times per full-suite run against **915** explicit resolutions — 97.5% implicit. Legacy's own census records 51,540 before its conversion and asserts zero after. **Undercounted here:** three more sites live in `omnidriver-openfoam` (`apply_overrides.py:148,288`, `dict_builder.py:276`), so `apply_overrides(…, driver_context=None)` raises `ModuleNotFoundError: omnidriver.cardiacfoam` in a core+openfoam install — a wrong-direction leak the import gate cannot see. 21 sites total. Port legacy's two guards: `test_core_context_is_explicit.py` (static AST) and `test_fallback_census.py` (runtime). |
| **`get_phases()` optional hook** | verified | Confirmed absent here, present in legacy with `legacy_phases()`, `_DictionaryCatalogAdapter.phases()`, and `phase_order` threaded through `primary_phase()`. Here `primary_phase(entry)` walks a fixed `Phase = Literal["anatomy","physics","stimulus","solver"]` in `run_model.py:44`. Still the only silent-wrong defect in the set — and the worked example of the closed-core-enum → plugin-declaration transform `future/ENVIRONMENT_CONTRACT.md` §7 asks for elsewhere. |
| **retire the 20 cardiac-gated `legacy_*` branches** | **much closer than described** | The stated precondition — "unreachable there once cardiacFoam implemented all 15 optional hooks" — does not hold here: `CardiacFoamPlugin` is missing three (`get_config_resolution_description`, `get_report_catalog`, `get_phases`). The instrumentation this row was gated on has now been run. Across the full 1729-test suite the **cardiac branch is taken by exactly one function**, `legacy_describe_config_resolution` (12×); every other call arrives from a non-cardiac plugin and takes the neutral branch. Port the three hooks (two in Phase 1, `get_phases` in Phase 2) and all 20 become deletable. |
| **drop unused declared dependencies** | verified | `omnidriver-cardiacfoam` declares `numpy`, `omnidriver-openfoam` declares `gmsh` — grep confirms **zero** Python imports of either. `gmsh` is a workflow *binary* name and pulls a ~100 MB wheel, and forces both the `test-openfoam` and `test-cardiac` CI jobs to `apt-get install` GUI libraries. Core's deps are already clean. A guard test asserting every declared distribution is imported comes with it. |

### Found by the audit, not previously listed

| work | why it matters |
|---|---|
| **entry-point group mismatch** | Highest severity found. See the correction in §1 — plugin selection by name does not work in any install. One-line fix plus a test that reads real `importlib.metadata` rather than the `_entry_points()` seam. |
| **core cannot be installed as a wheel** | `core/capability_seams.py:50` calls `repo_root_default()` at **module scope**, and that function walks up for a development checkout (`tutorials/+src/`, `tutorials/`, or `packages/+ARCHITECTURE.md`) and raises rather than guess. From site-packages nothing matches, so `import omnidriver.core.capability_seams` raises `RuntimeError`. Editable installs hide it completely — and `release.yml` builds exactly this wheel. Same root cause as the "1 pre-existing unrelated failure" in `test_sweep_plan_contract.py`, which is really a missing `@skip_without_monorepo`. |
| **the role vocabulary is unenforced** | `CaseFileRule.role` is the environment seam — `openfoam.control_dict`, `openfoam.entrypoint`, `plugin.configuration` — and `plugin_profile.py:101` validates it only as "non-empty string". `plugin_capabilities.py:461` warns in prose that a rule written `control_dict` instead of `openfoam.control_dict` is silently reclassified as plugin-owned. Nothing enforces it. |
| **declared roles that nothing reads** | `openfoam.entrypoint` is declared in `cardiacfoam/plugin.yaml:64` and consumed nowhere, while `Allrun` is hardcoded at `registry.py:79,88,302`, `generic_case.py:137` and `workflow.py:74`. Same for `openfoam.cleanup` and `openfoam.mesh_generation`. Only two sites in the repo consume a role semantically. |
| **misplaced modules in core** | `core/specs/spatial_pacing.py` is S1–S2 cardiac pacing-protocol generation emitting OpenFOAM list syntax, with one cardiacfoam consumer. `scripts/_rtst_scanner.py`, `_names_parser.py` and `_dict_keys_scanner.py` are OpenFOAM/cardiacFoam **C++ source** parsers; `_rtst_scanner` reaches cardiacfoam through `dict_entries`'s waived PEP 562 re-export, which is why the import gate cannot see it. |
| **licensing** | No `LICENSE` file anywhere, no `license` field in any of the three `pyproject.toml`, and 72 source files carrying a "This file is part of cardiacFoam / GPLv3" header. Three packages cannot be published under an undeclared licence carrying another project's header. `packages/omnidriver/README.md` — the PyPI long description — also claims "zero OpenFOAM-specific vocabulary" and links to `../../ARCHITECTURE.md`, which will not resolve off-repo. |
| **CI does not test what ships** | Matrix is 3.11/3.12; the dev venv is 3.14; the migration instructions verify on 3.13. No job installs a built wheel. The root `pyproject.toml` puts all three test roots on `pythonpath`, which is what lets `packages/omnidriver/tests/equivalence` pass only when cardiacfoam's test tree is co-collected. |

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

- `future/ENVIRONMENT_CONTRACT.md` — what core owns and how; supersedes
  `ARCHITECTURE.md`'s Rule 1 with a version the code can satisfy
- `docs/superpowers/plans/2026-08-27-core-completion.md` — the executable plan
  for §3, with the definition of "core is finished"
- `noFrontendCardiacFoam/applications/scripts/driverFoam/MIGRATION.md` — the
  sending side's view
- `MIGRATION_AUDIT_v2.md`, `future/` — this repo's own decoupling records.
  Note `MIGRATION_AUDIT_v2.md` predates the package split and its file paths
  all name the retired flat `openfoam_driver/` tree; read it for reasoning,
  not for locations.
