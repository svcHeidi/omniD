# Migration status: cardiacFoam's driverFOAM → omniD

**Round 1 (the bulk copy) is DONE. Round 2 runs soon — see §3 for what it
must bring across.**

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
(`dfa07d2`), a core free of `foamlib`/OpenFOAM imports (`a2eb34b`,
`39e56d1`, `59fd6a2`), marker-based path resolution replacing
`Path(__file__).parents[N]` (`6a105d8`), utility manifests as package data
(`5114623`), and GitHub Actions CI (`6cff329`).

## 2. BLOCKER: CI is red, and one line per file fixes it

`packages/omnidriver/src/omnidriver/core/plugin_interface.py` annotates types
imported only under `if TYPE_CHECKING:` — `DictEntry`, `TutorialSpec`,
`TutorialDisplay`, `DataArtifact`, `Path` — without
`from __future__ import annotations`. Those names are then resolved when the
class body executes, so **importing the module raises**:

```
NameError: name 'DictEntry' is not defined
```

on every Python before 3.14. The CI matrix is **3.11 and 3.12** — exactly the
affected versions — so all six jobs die at collection. Reproduced by running
`ci.yml`'s own command: **38 collection errors.**

Three files need the import:

```
openfoam_driver/core/plugin_interface.py                            (legacy tree)
packages/omnidriver/src/omnidriver/core/plugin_interface.py         (the real one)
packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/validation.py
```

The third is safe today only because its annotations happen to be quoted — one
edit from the same failure.

**Why nobody saw it:** this repo's `.venv` is Python 3.14, where PEP 649 defers
annotation evaluation and hides the bug entirely. A fully green local suite
coexists with a CI that cannot collect a single test. The fix and a mechanical
guard test (a module with a `TYPE_CHECKING` block must defer its annotations)
are already proven in the cardiacFoam tree at commit `6921e4f2`, verified on a
real 3.13 interpreter.

**Nothing else here can be validated until this lands.**

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
