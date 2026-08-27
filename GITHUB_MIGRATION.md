# Migration status: cardiacFoam's driverFOAM → omniD

**Round 1 (the bulk copy) is DONE. One blocker stands in front of round 2:
core does not yet stand alone — §2. Round 2 scope is §3.**

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

## 2. BLOCKER: core does not stand alone — 20 collection errors

*(The previous blocker in this slot — `NameError: name 'DictEntry' is not
defined` on Python < 3.14 — was fixed in `7a4be70` and `078afd4`. The
`test-openfoam` and `test-cardiacfoam` jobs are now genuinely green: 107 and
292 passed on a real 3.13 interpreter. `test-core` is not.)*

Run exactly as CI runs it — **core installed alone**, `pip install -e
"packages/omnidriver[post]"` then `pytest packages/omnidriver/tests` — the core
job produces **20 collection errors**: 11 × `No module named
'omnidriver.openfoam'`, 9 × `No module named 'omnidriver.cardiacfoam'`.

Verify against a core-only virtualenv. This repo's own `.venv` has all three
packages installed and hides the problem entirely.

### The severe part is not the tests

```
$ python -c "import omnidriver.cli"
ModuleNotFoundError: No module named 'omnidriver.openfoam'   (cli.py:37)
```

`cli.py` imports `omnidriver.openfoam` unconditionally at module scope on lines
37 and 53, so **the whole CLI surface — `plan`, `run`, `step`, `sweep-plan`,
`sweep-run` — is unreachable in a core-only install.** Anyone who installs
core as advertised cannot run the tool.

`scripts/check-import-boundaries.py` reported "boundaries OK" throughout,
because it scanned only `src/omnidriver/core/` while `cli.py` sits one level
up. Scope widened in `2f6ce63`; the three pre-existing violations are waived
and printed on every run, and the waiver list can only shrink.

### The 20 failing modules, audited

| category | count | fix |
|---|---|---|
| **misplaced** — tests a sibling's behaviour from core's tree | 10 | move to that package's `tests/` |
| **core test, leaking** — tests core but reaches for a sibling | 7 | remove the sibling dependency; 5 of these fail *only* transitively through `cli.py` and need no edit at all once it is fixed |
| **genuine cross-package integration** | 3 | give them a job that installs all three |

Two files (`test_dict_value_quoting.py`, `test_dict_entries.py`) mix a clean
core test with an embedded cardiac one in the same file — those need a split,
not a `git mv`.

### Do not "fix" this by installing all three packages in the core job

It would go green immediately and **delete the only automated check that core
stands alone** — the check whose absence let `cli.py` rot unnoticed. The
correct moves are a fourth job for the genuine integration tests, and actually
fixing `cli.py`.

## 3. Round 2 — what still has to come across

Measured 2026-08-27 against `noFrontendCardiacFoam` at `5fda4006`. Each is
present there and absent here:

| work | why it matters |
|---|---|
| **explicit `DriverContext` in core** — 21 call sites converted | 7 core files here still call `resolve_public_driver_context`, silently becoming cardiacFoam whenever a caller omits a context. A missed site does not raise; it keeps working and stays cardiac. Ported with a static AST guard. |
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
