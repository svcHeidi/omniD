# Working in this repository

Read this first. It is the entry point for agents and the fastest way to avoid
re-deriving what the last five sessions established.

## What this is

A solver-agnostic orchestrator, split into three packages under `packages/`:

| package | may know about | must not know about |
|---|---|---|
| `omnidriver` (core) | DAG execution, schemas, provenance, the plugin contract | OpenFOAM, any solver, any physics |
| `omnidriver-openfoam` | `foamlib`, dictionaries, meshing, MPI decomposition | cardiology |
| `omnidriver-cardiacfoam` | electrophysiology, ionic models, the cardiac plugin | — |

Core containing **zero** cardiac vocabulary is not aspirational — it is
enforced. `scripts/check-import-boundaries.py` exits non-zero on any cardiac
import in core, and its waiver list is **empty**. If you find yourself wanting
to add a waiver, you are solving the wrong problem.

## How to verify anything

The suites must pass in four different shapes, and each catches something the
others cannot. Editable installs leave the repository on `sys.path`, so a
module that reads repo-relative state at import time still works — that class
of defect is only visible from a wheel.

```bash
# Python floor is 3.11; CI matrixes 3.11/3.12/3.13. `uv python install 3.11`
# if needed. Build these once; they are not in the repo.
uv venv --python 3.11 /tmp/od311 && VIRTUAL_ENV=/tmp/od311 uv pip install -q \
  -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam \
  -e packages/omnidriver-cardiacfoam pytest
uv venv --python 3.11 /tmp/odcore && VIRTUAL_ENV=/tmp/odcore uv pip install -q \
  -e "packages/omnidriver[post]" pytest
```

| shape | command | catches |
|---|---|---|
| all three | `python -m pytest packages/ -q -m "not slow"` | ordinary regressions |
| core alone | `python -m pytest packages/omnidriver/tests -q` | core reaching into a sibling package |
| **installed wheel** | see below | core reading repo-relative state at import time |
| static gates | `python3 scripts/check-import-boundaries.py` and `scripts/export-capability-seams.py --check` | import direction; a stale generated table |

The wheel shape is the one people skip and the one that found the worst
defects. Rebuild it after **every** source change or it tests stale code:

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py          # artifact gate
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q   # 0 failed
```

Do not quote suite totals from documentation — they rot within days. Run the
command. The only durable claim is **0 failed**.

## Invariants, and the test that guards each

Breaking one of these should fail a test. If you change behaviour such that a
guard fails, fix the cause — do not weaken the guard, and do not add a skip.
A skip here hides exactly what the guard exists to find.

| invariant | guarded by |
|---|---|
| core imports nothing cardiac | `scripts/check-import-boundaries.py` (empty waiver list) |
| core declares no solver vocabulary | `test_core_declares_no_phase_vocabulary`, `test_core_exports_no_phase_vocabulary` |
| core never invents a filesystem root | `test_core_never_invents_a_filesystem_root` |
| core threads its `DriverContext` through the public edge | `test_core_threads_its_context_through_the_public_edge` |
| an explicitly-contexted operation never falls back to the default | `test_fallback_census.py` |
| no compatibility fallback reaches cardiac code | `test_no_fallback_reaches_cardiac_code_at_all` |
| the capability-seam table matches the docstrings | `scripts/export-capability-seams.py --check` |

## Two rules that were learned the hard way

**Supplied versus discovered.** Discover only what genuinely exists ambiently,
and declare where you look; supply everything else. A case root has no ambient
truth, so discovering one *invents* an answer — that is why core could not plan
a case from a wheel. Scheduler-allocated resources (MPI ranks, `OMP_NUM_THREADS`)
do have ambient truth, so reading them is right. Full reasoning:
`future/ENVIRONMENT_CONTRACT.md` §12.

**Evaluate defaults lazily.** The same bug appeared twice in `core/specs/paths.py`
consumers: a fallback computed *before* the branch that would have avoided it.
`resolve_entry` raised from a wheel even when a path was supplied, and
`resolve_run_script_path` raised even when a root was supplied and the file
existed under it. If a default can raise, compute it only when you need it.

## Traps

**`from conftest import X` is unreliable.** Both packages' `tests` directories
are reachable when the whole repo is collected, and **core's conftest wins**.
The existing `from conftest import monorepo_root` in the cardiac tree only
works because core's conftest happens to define the same name. For a
package-specific helper, use a uniquely named module inside an importable
package — see `packages/omnidriver-cardiacfoam/tests/regression_equivalence/tutorials_tree.py`.

**A test module that calls a raising function at import time cannot be
skipped.** It errors during collection, before any marker applies. Use
`conftest`'s `repo_root` / `skip_without_repo` (non-raising) rather than
`repo_root_default()` at module scope.

**"No Python imports" does not mean unused.** `gmsh` is declared for the
**binary** its wheel installs, which cardiac tutorials invoke as a workflow
command. An import scan reads it as dead; removing it breaks four tutorials at
runtime, silently.

## Where authority lives

- `future/ENVIRONMENT_CONTRACT.md` — what core owns and how. Supersedes
  `ARCHITECTURE.md`'s Rule 1. §12 is the supplied-vs-discovered rule.
- `ARCHITECTURE.md` — layer map and the generated capability-seam table.
- `GITHUB_MIGRATION.md` — what is done and what is open. **Start at its "Next steps" section**, which names the two things that actually remain. Check it before
  starting anything; several rows have been stale in the past, so verify a
  claim against the code before acting on it.
- `docs/superpowers/specs/` and `plans/` — design reasoning and executed plans.

- `AGENT_GUIDE.md` — the domain guide: planning, sweeping, post-processing,
  and authoring a plugin or a tutorial. Its paths and commands were corrected
  2026-09-04 and every module path in it is import-checked.

**Read for reasoning, not for locations:** `CHANGELOG.md` and
`MIGRATION_AUDIT_v2.md`, which describe the retired flat `openfoam_driver/`
tree. Both carry a banner saying so.

## House style

Comments and docstrings here are dense and cite specific code locations, and
that is deliberate — but citations rot. Prefer naming a **symbol** over a
`file.py:123` line number, which drifts. When you correct a claim, record the
correction with a date rather than silently overwriting it; that convention is
why several defects in this repository were findable at all.

The licence question is open: there is no `LICENSE` file and no `license`
field in any `pyproject.toml`. Do not add one without asking.
