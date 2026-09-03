# Documentation and Citation Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **COMPLETE — all four phases executed 2026-09-03** (`b3deb3a`, `4e094d5`,
> `d39a3d3`, `50598e0`). Every step below is checked because it was done, not
> as a formality: this plan's own Phase 4 Step 9 exists because another plan's
> boxes were left unchecked long after its work landed. The "Deferred" section
> at the end is still open and is the only outstanding part.
>
> Two phases grew during execution, both recorded in their commits: Phase 1's
> `bin/driverFoam` needed its PYTHONPATH fixed as well as its module name, and
> Phase 2's closing sweep found seven more stale citations than the audit did,
> two of them user-visible strings in JSON Schema output.

**Goal:** Make every in-source citation and every status document in this
repository agree with the code, and repair the two things the audit found that
are broken rather than merely mis-described.

**Architecture:** Four phases, landed as four commits, ordered by blast radius
and by how badly a wrong reading costs a reader. Phase 1 fixes running code and
the errors introduced on 2026-09-03. Phase 2 fixes source comments that
contradict the code they sit next to. Phase 3 resolves citations to documents
that do not exist. Phase 4 fixes the status documents themselves. Each phase is
independently revertable and independently verified.

**Tech Stack:** Python 3.13/3.14, pytest, plain Markdown. No new dependencies.

## Global Constraints

- **Verification venvs:** `/tmp/od_all/bin/python` (all three packages) and
  `/tmp/od_core/bin/python` (core only). Never the repo's own `.venv`.
- **Baseline that must not regress:** full suite **1546 passed, 276 skipped, 1
  deselected, 40 subtests**; core-only **679 passed, 93 skipped**.
- **Gates that must stay green:** `scripts/check-import-boundaries.py` exits 0
  with an EMPTY `KNOWN_VIOLATIONS`; `scripts/export-capability-seams.py --check`
  reports up to date.
- **Today's date is 2026-09-03.** Use it for every new dated marker. Do NOT
  rewrite dates on *historical* measurements — a row saying "Confirmed
  2026-09-02: … 676 passed" is a correct record of what was true that day and
  must be left alone. Only current-state claims get today's date.
- **House style is dense and evidence-first.** Corrections are recorded, not
  erased: follow the existing `**Corrected YYYY-MM-DD**` / `**Re-measured
  YYYY-MM-DD**` convention rather than silently overwriting a wrong claim.
- **Do not delete public functions in this plan.** Dead code is listed under
  "Deferred" and needs a separate decision.

## File Structure

| file | phase | responsibility |
|---|---|---|
| `scripts/regenerate-ionic-catalog.py` | 1 | fix a path that names a package that does not exist |
| `bin/driverFoam` | 1 | fix a stub that execs a module that does not exist |
| `GITHUB_MIGRATION.md` | 1, 4 | round-2 status; its intro contradicts its own licensing row |
| `ARCHITECTURE.md` | 1, 4 | current-state counts, and a self-contradicting metric |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | 2, 3 | three false citations in capability docstrings |
| `packages/omnidriver/src/omnidriver/core/utility_catalog.py` | 2 | header docstring documents a removed public API |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py` | 2 | claims a deleted tree is still tracked |
| `packages/omnidriver-openfoam/src/omnidriver/openfoam/foam_backend.py` | 2 | line citation drifted |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/ionic_model_catalog.py` | 2 | comment names the pre-migration path of the import below it |
| `scripts/export-report-catalog.py` | 2 | docstring points authors at two dead paths |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | 3 | "Phase 4"/"Phase 5" |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/runtime_evidence.py` | 3 | "Phase 4"/"Phase 5" |
| `packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py` | 3 | "Task 2a" |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/case_provenance.py` | 3 | "Task 2b" |
| `KEY_FILES.md` | 4 | every path predates the package split |
| `AGENT_GUIDE.md` | 4 | every import path and CLI example predates the package split |
| `CHANGELOG.md` | 4 | one "Known open" item names a deleted file |
| `SECURITY.md` | 4 | trust-boundary paths predate the package split |
| `MIGRATION_AUDIT_v2.md` | 4 | undated "still live" note that is false |
| `future/ENVIRONMENT_CONTRACT.md` | 4 | two sections numbered 8 |
| `future/STRICT_PLANNING_FOAMLIB_COUPLING.md` | 4 | §6 asserts a fixed problem is still open |
| `docs/superpowers/plans/2026-08-27-core-completion-phase-2.md` | 4 | banner says three completed tasks are "not started" |
| `docs/superpowers/plans/2026-08-25-monorepo-package-migration.md` | 4 | plans a package name that was never used |

---

## Phase 1: Broken code, and the errors introduced on 2026-09-03

Two scripts do not work. Four records are wrong because the 2026-09-03 commits
updated one place and not another.

**Files:**
- Modify: `scripts/regenerate-ionic-catalog.py:55-60`
- Modify: `bin/driverFoam:7`
- Modify: `GITHUB_MIGRATION.md:12-16`
- Modify: `ARCHITECTURE.md:46-47`, `ARCHITECTURE.md:51`
- Modify: `GITHUB_MIGRATION.md` — the two "2026-09-02" markers on Part C work

**Interfaces:**
- Consumes: nothing.
- Produces: nothing later phases depend on. Phase 4 edits `ARCHITECTURE.md` and
  `GITHUB_MIGRATION.md` again, in different sections; make Phase 1's edits
  surgical so the two do not collide.

- [x] **Step 1: Prove the catalog script is broken**

Run:
```bash
/tmp/od_all/bin/python scripts/regenerate-ionic-catalog.py --help
```
Then confirm the path it builds does not exist:
```bash
ls packages/omnidriver-cardiacfoam/src/omnidriver/cardiac/ionic_model_catalog.py
```
Expected: `No such file or directory`. The real file is at
`.../omnidriver/cardiacfoam/ionic_model_catalog.py`.

- [x] **Step 2: Fix the path segment**

In `scripts/regenerate-ionic-catalog.py`, change:

```python
CATALOG_PATH = (
    REPO_ROOT
    / "packages" / "omnidriver-cardiacfoam" / "src" / "omnidriver" / "cardiac"
    / "ionic_model_catalog.py"
)
```
to:
```python
CATALOG_PATH = (
    REPO_ROOT
    / "packages" / "omnidriver-cardiacfoam" / "src" / "omnidriver" / "cardiacfoam"
    / "ionic_model_catalog.py"
)
```

This is a survivor of the `omnidriver-cardiac` -> `omnidriver-cardiacfoam`
rename; the directory `omnidriver/cardiac/` has never existed in this repo.

- [x] **Step 3: Verify the path now resolves**

Run:
```bash
/tmp/od_all/bin/python -c "
import pathlib, sys
sys.path.insert(0, 'scripts')
p = pathlib.Path('packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/ionic_model_catalog.py')
print('exists:', p.exists())"
```
Expected: `exists: True`

- [x] **Step 4: Fix the broken bin/driverFoam stub**

`bin/driverFoam` ends in `exec python3 -m openfoam_driver "$@"`. That module
exists in no install, so the script always fails. It is referenced nowhere
(`git grep "bin/driverFoam"` returns nothing). `python3 -m omnidriver` works
(`packages/omnidriver/src/omnidriver/__main__.py` exists).

Replace the last line:
```bash
exec python3 -m openfoam_driver "$@"
```
with:
```bash
# The installed console script is `omnidriver` (packages/omnidriver/
# pyproject.toml). This wrapper kept the pre-migration name working and
# exec'd `openfoam_driver`, a module that exists in no install, so it always
# failed. Repointed rather than deleted: the old name costs one line to
# support and something outside this repo may still invoke it.
exec python3 -m omnidriver "$@"
```

- [x] **Step 5: Verify the stub runs**

Run:
```bash
./bin/driverFoam --help
```
Expected: the `omnidriver` usage block, exit 0. Before this change it exited
non-zero with `No module named openfoam_driver`.

- [x] **Step 6: Fix GITHUB_MIGRATION.md's self-contradicting intro**

Lines 12-16 still say the GPL header is the largest remaining blocker. The
licensing row at line 181 — and the code — say it is gone. Replace:

```
order for a publication-ready release: **licensing** (no `LICENSE` file, no
declared license, core still carries someone else's GPL header on 58/71
files — the largest remaining blocker), the CI matrix (still 3.11/3.12 only,
no wheel-install job), and the two unused declared dependencies (`numpy`,
`gmsh`).
```
with:
```
order for a publication-ready release: **licensing** — no `LICENSE` file and
no `license` field in any of the three `pyproject.toml`, so `omnidriver` and
`omnidriver-openfoam` ship with no license declared at all (**corrected
2026-09-03**: this paragraph used to name the cardiacFoam GPL header as the
largest blocker; that half was finished in `c8d6172` and `0039753` and the
summary was not updated with the row at §3) — then the CI matrix (still
3.11/3.12 only, no wheel-install job), and the two unused declared
dependencies (`numpy`, `gmsh`).
```

- [x] **Step 7: Correct the two Part C date markers**

`git log --format="%h %ad" --date=short` shows `129f820` and `0039753` landed
**2026-09-03**, not 2026-09-02. In `GITHUB_MIGRATION.md`, change
`The `DriverContext` row is done as of 2026-09-02` to `... as of 2026-09-03`,
and `**Closed 2026-09-02.**` in that row's body to `**Closed 2026-09-03.**`.

Leave every other 2026-09-02 marker alone — they date measurements that were
genuinely taken that day.

- [x] **Step 8: Refresh ARCHITECTURE.md's current-state table**

Lines 46-47 report the suite counts as of the last measurement. Re-measure and
update:

```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
```
Expected: 1546 / 679. Set the rows to:
```
| all three packages installed | **1546 passed, 276 skipped, 40 subtests, 0 failed** |
| core installed alone | **679 passed, 93 skipped, 0 failed** |
```

- [x] **Step 9: Correct ARCHITECTURE.md's org.cardiacfoam count**

Line 51 claims two occurrences, at `plugin_capabilities.py:1361` and
`capability_seams.py:160`. Verify:
```bash
git grep -n "org\.cardiacfoam" -- packages/omnidriver/src
```
Expected: exactly one hit, `plugin_capabilities.py:1362`. The
`capability_seams.py` occurrence was removed in `6a212dd`. Replace the row's
cell with:

```
| `"org.cardiacfoam"` in core | 1 occurrence, in a docstring explaining that the twenty gated fallbacks were deleted (`plugin_capabilities.py:1362`) — zero in executable logic. **Corrected 2026-09-03**: this said 2 occurrences and named `capability_seams.py:160`, whose copy went in `6a212dd`. |
```

- [x] **Step 10: Verify nothing regressed**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od_all/bin/python scripts/check-import-boundaries.py
/tmp/od_all/bin/python scripts/export-capability-seams.py --check
```
Expected: 1546 passed; `Import boundaries OK`; `up to date`.

- [x] **Step 11: Commit**

```bash
git add scripts/regenerate-ionic-catalog.py bin/driverFoam GITHUB_MIGRATION.md ARCHITECTURE.md
git commit -m "fix: repair two broken scripts and the records the 09-03 commits left behind"
```

---

## Phase 2: Source comments that contradict their own code

Nine verified citations inside Python source that name something that does not
exist, or assert something the surrounding code disproves. Documentation only —
no behaviour changes, so the suite count must be identical before and after.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py:304`, `:557`
- Modify: `packages/omnidriver/src/omnidriver/core/utility_catalog.py:1-6`, `:65`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py:38`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/foam_backend.py:172`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/ionic_model_catalog.py:119`
- Modify: `scripts/export-report-catalog.py:30-32`

**Interfaces:**
- Consumes: nothing from Phase 1.
- Produces: nothing. Pure prose.

- [x] **Step 1: Remove the dead `_resolve_entry` citation**

`plugin_capabilities.py:304` says
``(see :func:`strict_planning._resolve_entry`'s call site for why they stay out
of ``plan_diagnostics``)``. Verify it is dead:
```bash
git grep -n "_resolve_entry" -- packages scripts
```
Expected: only the citation itself. Replace that parenthetical with:

```
    human, not a defect -- which is why they stay out of ``plan_diagnostics``
    rather than being reported as plan failures.
```

The reason survives; only the pointer to a function that no longer exists goes.

- [x] **Step 2: Fix the false `--openfoam-bashrc` claim**

`plugin_capabilities.py:557` says ``--environment-bashrc``, with
``--openfoam-bashrc`` kept working as a deprecated alias. Verify that is false:
```bash
git grep -c "openfoam.bashrc\|openfoam_bashrc" -- packages/omnidriver/src/omnidriver/cli.py
```
Expected: no match. `future/ENVIRONMENT_CONTRACT.md` §10 Tier 3 says the alias
was "first shipped as deprecated aliases, then removed outright the same day",
and `test_openfoam_bashrc_kwarg_is_no_longer_accepted` asserts a `TypeError`.
Replace with:

```
    ``--environment-bashrc``. ``--openfoam-bashrc`` was shipped as a deprecated
    alias and then removed outright the same day, pre-publication (future/
    ENVIRONMENT_CONTRACT.md §10, Tier 3) -- this sentence used to claim the
    alias still worked.
```

- [x] **Step 3: Fix utility_catalog.py's header, which documents a removed API**

Verify neither symbol exists:
```bash
git grep -n "^UTILITY_CATALOG\|^UTILITIES_ROOT" -- packages/omnidriver/src
```
Expected: no match. In `utility_catalog.py`, the opening lines call the module
"A static, eagerly-loaded catalog of cardiacFoam utilities" and the `Schema`
block lists ``UTILITY_CATALOG — module-level dict populated at import time``.
Both are wrong, and the first puts cardiac vocabulary in a core module.

Replace the opening description with:
```
Utility Manifest Catalog

Loads utility manifests from ``utility.manifest.toml`` sidecar files placed
next to each utility source directory. The roots are supplied by the selected
plugin, not hardcoded: core names no solver's utilities.
```
and drop the ``UTILITY_CATALOG`` line from the `Schema` block, leaving
``UtilityManifest`` and ``load_utility_manifests``. The eager module-level
catalog and ``UTILITIES_ROOT`` were removed (future/
UTILITY_CATALOG_STANDALONE_GAP.md, status resolved); only this header still
described them.

- [x] **Step 4: Fix dict_builder.py's "still tracked" claim**

`dict_builder.py:38` explains a historical bug and says it went unnoticed
"because the retired `openfoam_driver/` tree is still tracked at the repo
root". Verify:
```bash
git ls-files | grep -c "^openfoam_driver/"
```
Expected: `0` — deleted in `4a5fb48`. Change that clause to past tense:

```
    # any cwd outside this repo, and it went unnoticed because the retired
    # `openfoam_driver/` tree was still tracked at the repo root at the time:
    # running pytest from there put cwd on sys.path and the stale package
    # resolved. That tree was deleted in `4a5fb48`.
```

- [x] **Step 5: Fix the drifted line citation in foam_backend.py**

`foam_backend.py:172` cites ``mutators.py:434`` for the tier-1 rejection.
Verify where the rejection actually is:
```bash
sed -n '400p;434p' packages/omnidriver-openfoam/src/omnidriver/openfoam/mutators.py
```
Expected: line 400 is `raise ValueError("add_if_missing requires a scope")`;
line 434 is `search_start, search_end = _resolve_search_region(lines, scope)`.

The rejection at line 400 sits inside ``update_foam_entry`` (defined at
`mutators.py:329` -- confirmed with
`grep -n "^def " mutators.py | awk -F: '$1<400' | tail -1`).

Cite it by name rather than by number, so it cannot drift again. Change:
```
    reason tier 1 rejects it at ``mutators.py:434``: without a scope there
```
to:
```
    reason tier 1 rejects it in ``mutators.py``'s ``update_foam_entry``:
    without a scope there
```

- [x] **Step 6: Fix ionic_model_catalog.py's pre-migration path**

Line 119 says ``SOLVER_COMPATIBILITY_RULES moved to
openfoam_driver/solver_coupling.py``, while the import on the next line reads
`from omnidriver.cardiacfoam.solver_coupling import SOLVER_COMPATIBILITY_RULES`.
Change the comment to name the real module:

```
# SOLVER_COMPATIBILITY_RULES moved to omnidriver/cardiacfoam/solver_coupling.py;
# re-exported here for backward compatibility with consumers that imported
# it from this module. Prefer the new home for new imports.
```

- [x] **Step 7: Fix export-report-catalog.py's two dead paths**

Its docstring points backend authors at
``openfoam_driver/core/report_catalog.py`` and
``openfoam_driver/plugins/cardiacfoam/reports.py``. Neither exists. Replace
with the real locations:
```
"""Export the active plugin's report catalog to JSON.

Backend authors report definitions against ``omnidriver/core/report_catalog.py``'s
``ReportDefinition`` record; each plugin owns its own catalog (the built-in
cardiac plugin's lives at ``omnidriver/cardiacfoam/reports.py``)
```
Verify both exist first:
```bash
ls packages/omnidriver/src/omnidriver/core/report_catalog.py \
   packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/reports.py
```

- [x] **Step 8: Confirm no citation was missed and nothing regressed**

Run:
```bash
git grep -n "openfoam_driver" -- packages/*/src scripts | grep -v build/
```
Every remaining hit must be a deliberate historical reference in past tense
(e.g. dict_builder.py's, now fixed in Step 4). List any that are not.

```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od_all/bin/python scripts/export-capability-seams.py --check
```
Expected: **1546 passed** — identical to Phase 1, since nothing but prose
changed. `export-capability-seams.py --check` must still say up to date; if it
does not, `plugin_capabilities.py`'s edits touched a generator input, so run
`scripts/export-capability-seams.py` and include the regenerated
`ARCHITECTURE.md` in the commit.

- [x] **Step 9: Commit**

```bash
git add -A
git commit -m "docs: correct nine source citations that contradict their own code"
```

---

## Phase 3: Citations to documents that do not exist

Nine citations name a "Phase 4", "Phase 5", "Task 2a", or "Task 2b". No
document in this repository defines any of them. They are almost certainly
vocabulary from the original driverFOAM roadmap in `noFrontendCardiacFoam`,
which this repo shares no history with.

The fix is **not** to invent the missing documents, and **not** to delete the
reasoning — each comment says something true about why the code is shaped as it
is. The fix is to make each one self-describing, so it survives without an
external document.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py:605-607`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py:192`, `:216`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/runtime_evidence.py:50`, `:286-287`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py:36`, `:341`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/case_provenance.py:35`, `:74`

**Interfaces:**
- Consumes: nothing from Phases 1-2.
- Produces: nothing. Pure prose.

- [x] **Step 1: Confirm the documents really are absent**

Run:
```bash
git grep -l "Phase 4\|Phase 5\|Task 2a\|Task 2b" -- '*.md'
```
Expected: **no output**. If this prints a file, stop and read it — the
citations resolve after all and this phase should be reduced to fixing only the
ones that do not.

- [x] **Step 2: Replace "Phase 4"/"Phase 5" with what they actually mean**

The two names refer to consumers of two capability hooks. Say so directly.

In `plugin_capabilities.py:605-607`, replace:
```
    Phase 4 (telemetry) consumes ``solve_step_commands`` and
    ``telemetry_source_globs``; Phase 5 (observables) will consume
```
with:
```
    Telemetry collection consumes ``solve_step_commands`` and
    ``telemetry_source_globs``; observable extraction will consume
```

In `cardiacfoam_plugin.py:192`, replace
`"""Commands that actually run the solver (Phase 4 telemetry)."""` with
`"""Commands that actually run the solver, for telemetry collection."""`

In `cardiacfoam_plugin.py:216`, replace
`"""Reader for a cardiac artifact format, or None (Phase 5)."""` with
`"""Reader for a cardiac artifact format, or None if unsupported."""`

In `runtime_evidence.py:50`, replace
`# Phase 4's telemetry collector uses these globs to find the real log.` with
`# The telemetry collector uses these globs to find the real log.`

In `runtime_evidence.py:286-287`, replace:
```
    Empty today. Phase 5 registers readers here for cardiac formats such as
    ECG traces and Purkinje time series. Returning ``None`` must make Phase 5
```
with:
```
    Empty today. Readers for cardiac formats such as ECG traces and Purkinje
    time series register here when observable extraction lands. Returning
    ``None`` must make that consumer
```

- [x] **Step 3: Replace "Task 2a"/"Task 2b" with what they actually mean**

In `provenance_inputs.py:36`, replace
`then fingerprinted through Task 2a's` with
`then fingerprinted through`.

In `provenance_inputs.py:341`, replace
`# -- plugin-declared runtime dependencies (Task 2a): the solver binary,` with
`# -- plugin-declared runtime dependencies: the solver binary,`.

In `case_provenance.py:35`, replace
`field's canonical path is not knowable from its name alone -- is Task 2b's`
with
`field's canonical path is not knowable from its name alone -- is the
input-enumeration job's`.

In `case_provenance.py:74`, replace
`"""Deferred to Task 2b. See the module docstring for why ``()`` is safe."""`
with
`"""Deferred: returns ``()`` until input enumeration lands. See the module
    docstring for why ``()`` is safe."""`

- [x] **Step 4: Verify every phantom citation is gone**

Run:
```bash
git grep -n "Phase 4\|Phase 5\|Task 2a\|Task 2b" -- packages/*/src scripts | grep -v build/
```
Expected: **no output**.

- [x] **Step 5: Verify nothing regressed**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
```
Expected: **1546 passed** — prose only.

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: make nine citations self-describing instead of naming absent documents"
```

---

## Phase 4: The status documents

The largest bucket, and the one where a wrong reading costs the most: these are
the files a new reader or agent is pointed at first.

**Files:**
- Modify: `ARCHITECTURE.md` (the self-contradicting metric)
- Modify: `KEY_FILES.md` (every path)
- Modify: `AGENT_GUIDE.md` (banner)
- Modify: `CHANGELOG.md:199`
- Modify: `SECURITY.md` (trust-boundary paths)
- Modify: `MIGRATION_AUDIT_v2.md` (undated false note)
- Modify: `future/ENVIRONMENT_CONTRACT.md` (duplicate section number)
- Modify: `future/STRICT_PLANNING_FOAMLIB_COUPLING.md` §6
- Modify: `docs/superpowers/plans/2026-08-27-core-completion-phase-2.md` (banner)
- Modify: `docs/superpowers/plans/2026-08-25-monorepo-package-migration.md` (banner)

**Interfaces:**
- Consumes: Phase 1 already corrected `ARCHITECTURE.md`'s counts and
  `org.cardiacfoam` row, and `GITHUB_MIGRATION.md`'s intro. Do not redo those.
- Produces: nothing.

- [x] **Step 1: Delete ARCHITECTURE.md's superseded paragraph**

Lines 53-59 say the core-only failure count "is now **zero**". Lines 61-71 are
un-deleted older text saying "The remaining 140 are 129 from the implicit
cardiac `DriverContext` and 11 subprocess failures", followed by a paragraph
analysing those 129. Both sit in the same section with no transition.

Verify the current truth:
```bash
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
```
Expected: `679 passed, 93 skipped` — zero failures, so the first paragraph is
right and the second is stale.

Delete the second paragraph and the "Those 129 are **not** mostly a threading
problem" paragraph that depends on it. In their place put one line preserving
the fact that the measurement history is recorded elsewhere:

```
(The earlier breakdown of 140 remaining failures — 129 from the implicit
cardiac `DriverContext`, 11 from export-script subprocesses — was left standing
here after the count reached zero. **Removed 2026-09-03**; the history is in
`GITHUB_MIGRATION.md` §2 and the Phase 2 plan.)
```

- [x] **Step 2: Add a banner to KEY_FILES.md and fix its paths**

Every path in it uses `applications/scripts/driverFoam/openfoam_driver/…`.
Verify:
```bash
ls applications 2>&1 | tail -1; ls openfoam_driver 2>&1 | tail -1
```
Expected: both `No such file or directory`.

Add immediately under the title:
```
> **Corrected 2026-09-03.** Every path in this file named the pre-package-split
> layout (`applications/scripts/driverFoam/openfoam_driver/…`), which exists
> nowhere in this repository — following any of them failed. They now name the
> real locations under `packages/`. This file's stated purpose is to be a
> navigational map, so stale paths made it worse than useless.
```
Then rewrite each path to its real location. Resolve every one before writing
it:
```bash
git ls-files 'packages/*/src/**/*.py' | sed 's#.*/omnidriver/#omnidriver/#' | sort
```
Also fix the claim that `ARCHITECTURE.md` is "~1400 lines". It is **191**
(`wc -l < ARCHITECTURE.md`). Drop the size claim rather than replacing it with
a new number that will rot the same way.

- [x] **Step 3: Add a supersession banner to AGENT_GUIDE.md**

This file has ~47 `openfoam_driver.*` import paths and 14 CLI examples invoking
`driverFoam`, which is not the installed console script. Verify:
```bash
grep -c "openfoam_driver" AGENT_GUIDE.md
cd /tmp && /tmp/od_all/bin/python -c "import openfoam_driver" 2>&1 | tail -1
```
Expected: a large count; `ModuleNotFoundError`.

A full rewrite of a ~1000-line guide is out of scope for this plan. Add a
banner immediately under the title that stops a reader acting on it:

```
> **Status: predates the package split — read for reasoning, not for
> locations or commands (added 2026-09-03).** Every import path below names
> `openfoam_driver.*`, and every CLI example invokes `driverFoam`. Neither
> exists in any install: the package is `omnidriver` (plus
> `omnidriver-openfoam`, `omnidriver-cardiacfoam`) and the console script is
> `omnidriver`. The behavioural explanations here are still broadly accurate;
> the paths and commands are not. `ARCHITECTURE.md` and `KEY_FILES.md` carry
> the current layout. Rewriting this file is tracked as its own task.
```

This matches the convention `MIGRATION_AUDIT_v2.md` already uses.

- [x] **Step 4: Fix CHANGELOG.md's false "Known open" item**

Line 199 says the `$ELECTRO_MODEL_COEFFS` sentinel is "still hardcoded in …
`scripts/_dict_keys_scanner.py`". Verify:
```bash
ls scripts/_dict_keys_scanner.py 2>&1 | tail -1
```
Expected: `No such file or directory`. `GITHUB_MIGRATION.md` records it as
removed outright.

Mark the item resolved in place rather than deleting it — this is a changelog:
```
  (**Resolved.** `scripts/_dict_keys_scanner.py` no longer exists; it was
  removed, not relocated. Noted 2026-09-03.)
```

- [x] **Step 5: Fix SECURITY.md's trust-boundary paths**

It cites "the `openfoam_driver` package", `specs/apply_overrides.py`, and
`plugins/cardiacfoam/dict_builder.py`. The security *logic* it describes is
correct — only the locations are stale. Verify the real ones:
```bash
ls packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py \
   packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/dict_builder.py \
   packages/omnidriver/src/omnidriver/core/runtime/registry.py
```
Rewrite each path to its real location and add a dated correction note. Do not
change any security claim — those were verified accurate.

- [x] **Step 6: Date and correct MIGRATION_AUDIT_v2.md's "still live" note**

Its top callout says `sweep_materialize.py::_materialize_case_legacy` "is dead
code called from nowhere. It still exists." Verify:
```bash
git grep -n "_materialize_case_legacy" -- packages scripts
```
Expected: no output. Replace the callout with:

```
> **Corrected 2026-09-03.** This callout used to say one item here was still
> live: `sweep_materialize.py::_materialize_case_legacy`, "dead code called
> from nowhere", to be confirmed callerless before removal. That function no
> longer exists anywhere in the repository — `sweep_materialize.py` now
> contains only `materialize_case()`, routed through the capability system.
> Nothing in this document is still live.
```

- [x] **Step 7: Fix the duplicate section number in future/ENVIRONMENT_CONTRACT.md**

Verify:
```bash
grep -n "^## " future/ENVIRONMENT_CONTRACT.md
```
Expected: two headings numbered `## 8.` (lines 214 and 232), with `## Related`
between them.

Code cites §4, §7, §10 and §11 of this document by number, so renumbering is
dangerous. Confirm what is cited before touching anything:
```bash
git grep -o "ENVIRONMENT_CONTRACT.md §[0-9]*" -- packages scripts | sort -u
```
Renumber only the SECOND `## 8.` (line 232, "What only running the code
revealed") to `## 8b.`, leaving 9/10/11 untouched. This resolves the duplicate
without shifting any number that code depends on. Move `## Related` to the end
of the document, where its siblings put it.

- [x] **Step 8: Correct STRICT_PLANNING_FOAMLIB_COUPLING.md §6**

It says `omnidriver/cli.py` "still has two direct `omnidriver.openfoam`
imports". Verify:
```bash
grep -n "^from omnidriver\.openfoam\|^import omnidriver\.openfoam" packages/omnidriver/src/omnidriver/cli.py
```
Expected: no output. Replace the claim with:

```
**Corrected 2026-09-03.** This section used to record `omnidriver/cli.py`'s two
direct `omnidriver.openfoam` imports as a deliberate exception left in place.
They are gone: `cli.py` now reaches both through capabilities
(`environment_preflight.load`, `override_scopes.apply`), and
`scripts/check-import-boundaries.py` records the same fix.
```

- [x] **Step 9: Fix the Phase 2 plan's stale progress banner**

Its top table marks Tasks 3, 6 and 7 "not started". All three are done. Verify
each:
```bash
git grep -n "def legacy_phases" -- packages/omnidriver/src
git grep -n "def get_phases" -- packages/omnidriver/src/omnidriver/core/plugin_interface.py
grep -n "driver_context" packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py | head -3
grep -c "org\.cardiacfoam" packages/omnidriver/src/omnidriver/core/compatibility.py
```
Expected: `legacy_phases` and `get_phases` both exist; `apply_overrides` takes a
required `driver_context`; the grep count is `0`.

Update the three rows to `done`, and add under the banner:
```
**Corrected 2026-09-03.** Tasks 3, 6 and 7 were marked "not started" in this
table long after they landed; their step checkboxes below are likewise still
unchecked. Do not read the unchecked boxes as outstanding work — verify against
the code. Task 7 Step 2's instruction to leave `legacy_generic_case_mutation`
"permanent-for-now" is also superseded: that function was deleted on
2026-09-03.
```

- [x] **Step 10: Add a status banner to the monorepo migration plan**

`2026-08-25-monorepo-package-migration.md` uses `omnidriver-cardiac` /
`omnidriver.cardiac` throughout for a package that shipped as
`omnidriver-cardiacfoam`. Verify:
```bash
grep -c "omnidriver[-.]cardiac\b" docs/superpowers/plans/2026-08-25-monorepo-package-migration.md
ls packages/
```
Add under the title:
```
> **Status: executed, with one name changed in flight (noted 2026-09-03).**
> This plan names the third package `omnidriver-cardiac` /
> `omnidriver.cardiac` throughout. It shipped as `omnidriver-cardiacfoam` /
> `omnidriver.cardiacfoam`; no `omnidriver.cardiac` module has ever existed.
> Read the package name here as the one that shipped. A survivor of this
> rename was still breaking `scripts/regenerate-ionic-catalog.py` until
> 2026-09-03.
```

- [x] **Step 11: Verify nothing regressed and no new stale path was introduced**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od_all/bin/python scripts/check-import-boundaries.py
/tmp/od_all/bin/python scripts/export-capability-seams.py --check
```
Expected: 1546 passed; boundaries OK; seam table up to date.

Then confirm every path newly written into KEY_FILES.md and SECURITY.md exists:
```bash
grep -oE 'packages/[A-Za-z0-9_./-]+\.(py|yaml|toml|md)' KEY_FILES.md SECURITY.md \
  | cut -d: -f2- | sort -u | while read -r p; do [ -e "$p" ] || echo "MISSING: $p"; done
```
Expected: no `MISSING:` lines. A path audit that introduces new bad paths is
worse than the problem it fixes.

- [x] **Step 12: Commit**

```bash
git add -A
git commit -m "docs: reconcile the status documents with the code they describe"
```

---

## Deferred — needs a decision, not in this plan

These were verified by the audit but are **not** addressed above, because each
needs a judgment this plan cannot make:

1. **Five dead public functions** — `get_ionic_model_entry`,
   `list_compatible_ionic_models`, `list_models_by_region`,
   `list_models_by_species` (`cardiacfoam/ionic_model_catalog.py`) and
   `get_active_tension_entry` (`cardiacfoam/active_tension_catalog.py`). Zero
   callers in `packages/` or `scripts/`. They are a plugin package's public
   surface, so deleting them could break an external consumer. Needs a call on
   whether that surface is supported.
2. **`FIELD_NAMES`** (`core/capability_seams.py:38`) — unused, and
   `parse_fields()` re-hardcodes the same four strings fifteen lines below.
   Either wire it in or delete it; both are safe, but it is a code change, not
   a doc fix.
3. **`describe_launch_matrix`** (`core/introspection.py:298`) — no caller; its
   docstring says it is "kept for AGENT_GUIDE.md compatibility", and
   AGENT_GUIDE.md is the document Phase 4 Step 3 marks as superseded. Resolve
   after AGENT_GUIDE's fate is decided.
4. **`packages/omnidriver/tests/drift_guards/`** — contains only an orphaned
   `conftest.py`; the five tests it gated moved to `omnidriver-cardiacfoam` in
   `778eb9c`. Deleting the directory is almost certainly right but is a test-tree
   change.
5. **20 files in `omnidriver-cardiacfoam/tests/` carrying both a GPL banner and
   a module docstring**, which have drifted apart (e.g. `test_validation.py`'s
   banner says "validation logic and specification contracts", its docstring
   says "Tests for `validate_run`"). Explicitly left alone by decision on
   2026-09-03: that package keeps its header, and the duplication predates this
   work.
6. **`scripts/` (7 files) and one `future/` markdown** still carry the
   cardiacFoam GPL header. Out of scope of the test-tree pass; same licensing
   decision as the missing `LICENSE` file.
7. **The real licensing blocker** — no `LICENSE` file, no `license` field in any
   `pyproject.toml`. `omnidriver` and `omnidriver-openfoam` ship with no license
   declared at all.
