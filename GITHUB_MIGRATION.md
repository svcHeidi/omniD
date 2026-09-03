# Migration status: cardiacFoam's driverFOAM → omniD

**Round 1 (the bulk copy) is DONE. The collection blocker that stood in
front of round 2 is CLOSED — §2. Round 2 scope is §3, and §2 turned up
evidence of just how large §3's first item actually is.**

**Re-audited 2026-09-02, after `future/ENVIRONMENT_CONTRACT.md`'s Tier 1–4
work landed.** Most of §3 is now resolved — entry-point group, wheel install,
role-vocabulary enforcement, misplaced modules, and the `DriverContext`
call-site count (21 → 6) all closed or shrank without a dedicated pass, as a
side effect of that separate work. What's genuinely still open, in priority
order for a publication-ready release: **licensing** — no `LICENSE` file and
no `license` field in any of the three `pyproject.toml`, so `omnidriver` and
`omnidriver-openfoam` ship with no license declared at all (**corrected
2026-09-03**: this paragraph used to name the cardiacFoam GPL header as the
largest blocker; that half was finished in `c8d6172` and `0039753`, and this
summary was not updated alongside the licensing row in §3) — then the CI
matrix (still 3.11/3.12 only, no wheel-install job), and the two unused
declared dependencies (`numpy`, `gmsh`). **Both core/plugin decoupling rows are now closed.** The 20
cardiac-gated `legacy_*` branches turned out to be already deleted — that row
was stale, not open. The `DriverContext` row is done as of 2026-09-03: core
contains no runtime cardiac import and no cardiac vocabulary, and
`scripts/check-import-boundaries.py`'s `KNOWN_VIOLATIONS` list is **empty**, so
that gate now asserts core's independence outright instead of enumerating
exceptions to it. See
[`docs/superpowers/specs/2026-09-02-neutral-default-context-design.md`](docs/superpowers/specs/2026-09-02-neutral-default-context-design.md)
for the design and each row in §3 for detail.

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

**Progress, 2026-08-27.** Phase 1 (branch `phase1-core-completion`) closed the
entry-point and wheel-install rows and validated the role vocabulary. Phase 2's
first wave took core-only failures 160 → 140, closing the
`regression_equivalence` and `omnidriver.openfoam` categories entirely. The
`DriverContext` row below is now known to be **two** pieces of work, only one of
which is mechanical — see the Phase 2 plan's "Task 5, remeasured".

### Ported from `driverFoam` (present there, absent here)

| work | status | why it matters |
|---|---|---|
| ~~**explicit `DriverContext` in core**~~ | **done 2026-09-02 — core holds no cardiac import or vocabulary** | Was 21 (18 in core + 3 in `omnidriver-openfoam`); 6 remain — `omnidriver/dict_entries.py:17,25,33`, `omnidriver/sweep_materialize.py:15`, `omnidriver/sweep_routing.py:16`, `omnidriver-cardiacfoam/dict_builder.py:963`. **Corrected 2026-09-02**, three ways. (a) The line numbers this row carried (`dict_entries.py:44,52,60`, `sweep_materialize.py:42`, `sweep_routing.py:43`) were stale. (b) The two guard tests it said were "not yet ported" — `test_core_context_is_explicit.py`, `test_fallback_census.py` — are both present under `packages/omnidriver/tests/core/` and passing. (c) The count was a misleading proxy: all 6 sites sit at what the static guard explicitly blesses as the public edge, so all 6 are legal, while `core/runtime/sweep_runner.py:273` and `:449` call `materialize_case()` **without** threading the context they already hold — a sweep under an explicit non-cardiac plugin materializes through cardiacFoam. Confirmed at runtime. Neither guard catches it: the AST guard only looks inside `core/` for direct `resolve_public_driver_context` calls, and the census exercises capability reads but never the sweep path. **Closed 2026-09-03.** The defect is fixed and guarded two ways (a behavioural sweep census, and a static check that a `core/` call to a context-taking public-edge function threads one). The 6 sites remain — the no-argument public API is deliberately kept — but what they resolve to changed: `legacy_default_driver_context()` now goes through the `omnidriver.plugins` entry-point group rather than importing `CardiacFoamPlugin`. Exactly one plugin registers that group in any real install, so cardiacFoam is still the default without core naming it; zero installed yields the built-in generic context (`source: built-in:generic-openfoam`); several refuse by name. The last two cardiac-shaped defaults — `legacy_generic_case_mutation` and the hardcoded `electroProperties`/`physicsProperties` pair — moved to `cardiacfoam/tutorials/generic_case.py`, and both `legacy_*` functions are deleted. `KNOWN_VIOLATIONS` is now empty. Design and measurements: [`docs/superpowers/specs/2026-09-02-neutral-default-context-design.md`](docs/superpowers/specs/2026-09-02-neutral-default-context-design.md). |
| ~~**`get_phases()` optional hook**~~ | **done, Phase 2** | Landed as described: `get_phases()` on `SolverPluginOptionalHooks` (`plugin_interface.py:517`), `legacy_phases()` fallback (`compatibility.py:502`), `phase_order` threaded through `primary_phase()` (`specs/validation.py:67`). **Closed 2026-09-03**: `run_model.py`'s `Phase = Literal[...]` alias is gone too. It survived as a type nothing walked, re-exported through `dict_entries.py` and read by one cardiac test via `typing.get_args` — the last solver vocabulary core declared. That test now reads `CardiacFoamPlugin().get_phases()`, which returns the same four names from the plugin that owns them. See `future/ENVIRONMENT_CONTRACT.md` §7. |
| ~~**retire the 20 cardiac-gated `legacy_*` branches**~~ | **done — this row was stale, re-measured 2026-09-02** | Already deleted, by Phase 2 Task 7. `grep -c 'org\.cardiacfoam' packages/omnidriver/src/omnidriver/core/compatibility.py` returns **0**, and `packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py` already guards the gated set at empty — its own docstring records the deletion. The precondition this row tracked (`CardiacFoamPlugin` implementing `get_config_resolution_description`, `get_report_catalog`, `get_phases`) was met, the census was re-run, and the branches went. What the deletion left behind was two published sentences still describing the gates as if they existed (`plugin_capabilities.py`, `capability_seams.py`, and the `ARCHITECTURE.md` table the latter generates) — corrected 2026-09-02. Core's *ungated* cardiac vocabulary is a different row: see the `DriverContext` row above. |
| **drop unused declared dependencies** | **half done 2026-09-03; the other half was a wrong call** | `numpy>=1.24` is dropped from `omnidriver-cardiacfoam` — zero mentions of any kind anywhere in the repo. **`gmsh>=4.15.2` stays, and this row was wrong to list it.** The test it failed was "zero Python imports", which is the wrong test for a package whose purpose is to ship a CLI: the wheel installs a `gmsh` **executable**, and cardiacFoam's `manufactured_bath_bidomain` and `manufactured_eikonal_ecg` tutorials invoke `gmsh` as a workflow command. Dropping it would have broken both at runtime, silently — the command would simply not resolve. The reason is now recorded next to the declaration itself. **Resolved 2026-09-03**: the need is now declared where it is felt. A case carrying a `.geo` file declares `gmsh` through core's `RuntimeDependency` seam (`cardiacfoam/runtime_evidence.py`), the same way the cardiacFoam binary and its libraries already were — so a missing gmsh is reported unavailable at plan time instead of dying mid-run. With the need declared properly, the pip wheel became an `omnidriver-openfoam[mesh]` extra rather than a hard dependency: it is ~100 MB, pulls GUI shared libraries on Linux, and is used by four tutorials. That also removed two `apt-get` steps from CI. Verified: all three suites pass with no gmsh installed, and `[mesh]` restores the binary. |

### Found by the audit, not previously listed

| work | why it matters |
|---|---|
| **entry-point group mismatch** | Highest severity found. See the correction in §1 — plugin selection by name does not work in any install. One-line fix plus a test that reads real `importlib.metadata` rather than the `_entry_points()` seam. |
| ~~**core cannot be installed as a wheel**~~ | **fixed.** `capability_seams.py`'s `repo_root_default()` call moved out of module scope into a function, `architecture_path()`, whose docstring names exactly this bug as the reason: "evaluating it at import time made this module unimportable from an installed wheel." Confirmed 2026-09-02: `import omnidriver.core.capability_seams` and the full core-only suite (676 passed, 0 failed) both run clean from a **freshly built** core-only venv, not an editable install. |
| **the role vocabulary is unenforced** | resolved by `future/ENVIRONMENT_CONTRACT.md` §11 (the escape-tier design, landed 2026-09-01) — `KNOWN_ROLES` is a closed, validated enum for `openfoam.*`/`plugin.*`/`case.*`, and a typo in a known namespace still raises at load. See that section for what is and isn't caught. |
| ~~**declared roles that nothing reads**~~ | **`openfoam.entrypoint` fixed.** `entrypoint_relpaths()` now backs `registry.py`'s case-detection/runnability checks and `generic_case.py`'s one-step DAG (Tier 2, 2026-09-01), and, as of Tier 4, a plugin's declared entrypoint resolves case-locally too (`future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md`). `openfoam.cleanup` is still declared (`cardiacfoam/plugin.yaml:68`) and still has **zero readers** — no `cleanup_relpaths()` equivalent exists; deliberately deferred, see that threat-model doc's scope section. `openfoam.mesh_generation` not re-checked. |
| ~~**misplaced modules in core**~~ | **resolved.** `spatial_pacing.py` now lives in `omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/`, not core. `scripts/_rtst_scanner.py`, `_names_parser.py`, and `_dict_keys_scanner.py` no longer exist anywhere in the repo — removed, not just relocated. The `dict_entries.py` PEP 562 lazy re-export these scripts reached cardiacfoam through was itself removed 2026-09-02 during pre-publication alias cleanup (`dict_entries.py` no longer defines `__getattr__` at all), so the escape route is gone even if a similar script reappeared. |
| **licensing** | **the wrong-header half fixed 2026-09-02; the "what license do we actually ship under" half still fully open.** The cardiacFoam GPL header is gone from all 120 core + `omnidriver-openfoam` files that carried it: 70 `src` files in `c8d6172` (`packages/omnidriver/src`: 58, `omnidriver-openfoam/src`: 12), then the 50 test files (`omnidriver/tests`: 41, `omnidriver-openfoam/tests`: 9). The test pass could not reuse the `src` approach of deleting the whole banner: 17 of those files carried a substantial `Description` section that existed nowhere else — about 110 lines of real reasoning — so those were converted to module docstrings and the rest dropped outright (113 insertions, 1412 deletions; only the 17 have any insertion at all). `omnidriver-cardiacfoam`'s own 81 files (44 `src` + 37 tests) keep their header untouched; that package's content genuinely is cardiacFoam-derived. Still carrying it outside that package: `scripts/` (7 `.py`) and one `future/` markdown file — deliberately left, being neither package source nor tests. Still open: no `LICENSE` file anywhere in the repo, no `license` field in any of the three `pyproject.toml` — core and `omnidriver-openfoam` currently ship with **no license declared at all**, which is a blocker in its own right, not a neutral state. Needs an actual decision on what these two packages are licensed under before a release, not just the removal that's now done. |
| ~~**CI does not test what ships**~~ | **closed 2026-09-03.** The matrix is now `["3.11", "3.12", "3.13"]` across all three test jobs, so the version the project is developed on is tested. A new `test-wheel` job builds core's sdist+wheel, installs the wheel into a clean venv, and runs `scripts/check-wheel-artifact.py` against it — the only job that exercises a non-editable install, where a module reading repo-relative state at import time can no longer hide behind the repository being on `sys.path`. `release.yml` now installs and smoke-tests each built wheel *before* publishing, so a broken artifact blocks the release instead of reaching it. Verified locally first: 1546 passed identically on 3.11, 3.12, 3.13 and 3.14. Still open: no job runs the wheel gate for `omnidriver-openfoam`/`omnidriver-cardiacfoam` (their suites need a checkout), and eight core test modules call `repo_root_default()` at import time so they error rather than skip outside one. |

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
