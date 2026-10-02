# Working in this repository

For provider-neutral task routing, start with [`AGENTS.md`](AGENTS.md) and
load the selected role's documents from
[`agent-handbook/guidance-manifest.yaml`](agent-handbook/guidance-manifest.yaml).
This file remains the maintainer-specific package and verification guide.

Read this first. It is the entry point for agents and the fastest way to avoid
re-deriving what the last five sessions established.

## What this is

A solver-agnostic orchestrator, split into five packages under `packages/`:

| package | may know about | must not know about |
|---|---|---|
| `omnidriver` (core) | DAG execution, schemas, provenance, the plugin contract | OpenFOAM, any solver, any physics |
| `omnidriver-openfoam` | `foamlib`, dictionaries, meshing, MPI decomposition | cardiology |
| `omnidriver-cardiacfoam` | electrophysiology, ionic models, the cardiac plugin | — |
| `omnidriver-cardiaccore` | evidence-backed cardiacCore preprocessing workflows | cardiacFoam solver semantics |
| `omnidriver-opencarp` | the openCARP binary, `.par` format, `mesher`, IGB/LAT outputs | OpenFOAM, cardiacFoam |

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
  -e packages/omnidriver-cardiacfoam -e packages/omnidriver-cardiaccore \
  -e packages/omnidriver-opencarp pytest
uv venv --python 3.11 /tmp/odcore && VIRTUAL_ENV=/tmp/odcore uv pip install -q \
  -e "packages/omnidriver[post]" pytest
```

| shape | command | catches |
|---|---|---|
| all packages | `python -m pytest packages/ -q -m "not slow and not native and not native_opencarp and not native_cardiaccore"` | ordinary regressions |
| core alone | `python -m pytest packages/omnidriver/tests -q` | core reaching into a sibling package |
| **installed wheel** | see below | core reading repo-relative state at import time |
| native tree | `OMNIDRIVER_NATIVE_TUTORIALS=<path> python -m pytest packages/ -q -m native`, from the cardiacFOAM shell (below) | drift against the real native cardiacFOAM tree: its tutorials and its C++ source, `$OMNIDRIVER_NATIVE_TUTORIALS/../src` (the profile's `cxx_mapping.source_root`), which every strict plan then scans. Supplied, never discovered; a `native` test FAILS, not skips, without it. It runs the real solver, serial and parallel, so it needs the cardiacFOAM shell: `omnidriver env --plugin cardiacfoam` lists each variable to supply and prints the `shell_prefix` (source OpenFOAM, then export `DYLD_LIBRARY_PATH`, which macOS strips when bash starts). The tree must be clean (a `git archive` of the native branch), since C11 reads git-ignored run output in a case as authored. `test_niederer_cross_solver_native.py` also needs `OMNIDRIVER_OPENCARP_TUTORIALS`. About 25 min |
| native openCARP | `python -m pytest packages/omnidriver-opencarp/tests -m native_opencarp`, from the openCARP shell | drift against the real openCARP binary and its tutorials tree. `omnidriver env --plugin opencarp` lists what to supply and checks it: `OMNIDRIVER_OPENCARP_TUTORIALS`, `DYLD_LIBRARY_PATH` (macOS, `libsundials_cvode`), `OPENCARP_MPI_BIN` first on `PATH` and, on a host whose name does not resolve, `HYDRA_IFACE`. A `native_opencarp` test FAILS, not skips, when one is missing. Outside these tests, planning or running a record against this tree needs `--scratch-dir` outside it |
| native cardiacCore | `OMNIDRIVER_CARDIACCORE_TREE=<clean native worktree/archive> OMNIDRIVER_CARDIACCORE_ANATOMY=<humanSlab bundle dir> python -m pytest packages/omnidriver-cardiaccore/tests -m native_cardiaccore` | drift against the real cardiacCore utilities, its C++ source (`$OMNIDRIVER_CARDIACCORE_TREE/src`) and the native `humanSlab` tutorial; both variables supplied, never discovered — a `native_cardiaccore`-marked test FAILS, not skips, when either is unset. Needs the OpenFOAM shell (`omnidriver env --plugin cardiaccore`) and the cardiacCore utilities (`setCardiacConductivity`, `setCardiacAnatomy`, `setPurkinjeSlab`, `setPurkinjeMorphometry`) built from that same tree's committed `main` into scratch (override `FOAM_APPBIN`) and on `PATH`/`DYLD_LIBRARY_PATH` first — never the owner's own installed binaries, whose build commit is unknown |
| static gates | `python3 scripts/check-import-boundaries.py`, `scripts/export-capability-seams.py --check`, `scripts/check-case-writes.py`, `scripts/check-core-shape.py`, and `scripts/check-benchmark-references.py` | import direction; a stale generated table; a tutorial-record/axis module writing a case directly instead of through `commit_case_write`; core gaining a new OpenFOAM layout token or growing its recorded debt; a benchmark reference under `benchmarks/` that fails to load, misnames its own id, or cites nothing |

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

openCARP's native tests carry `native_opencarp`, a marker distinct from
cardiacFOAM's `native`: `-m native` collects cardiacFOAM's native tests
only, and the all-packages row excludes both markers.

**Both native shapes run a solver in parallel:** conformance C13 runs the
target's declared quantity serial and at N = 2 and compares them, and C14
compares it across a two-case sweep. **The two MPIs must never mix:** each
solver's shell puts only its own MPI first on `PATH` (OpenFOAM's from its
bashrc, openCARP's from `OPENCARP_MPI_BIN`), and preflight refuses the other
one by name (`openfoam_mpi_launcher_mismatch`,
`opencarp_mpi_launcher_mismatch`). Inside a Slurm allocation, `SLURM_NTASKS`
must equal 2 for these checks. One example,
the whole cardiacFOAM shape:

```bash
OPENFOAM_BASHRC=/Volumes/OpenFOAM-v2412/etc/bashrc DYLD_LIBRARY_PATH=/opt/homebrew/lib \
OMNIDRIVER_NATIVE_TUTORIALS=<archive>/tutorials python -m omnidriver env --plugin cardiacfoam
# status ok: run the suite behind the printed shell_prefix
bash -c '<shell_prefix> OMNIDRIVER_OPENCARP_TUTORIALS=<opencarp>/share/tutorials python -m pytest packages/ -q -m native'
```

**The scratch root is supplied, never invented.** Anything that
stages — `plan --strict`/`step`/`run --strict` over a tutorial record (or a
case-folder entry whose source lies inside this checkout), or a sweep with no
`--output-dir` — needs `--scratch-dir <dir>` or `OMNIDRIVER_SCRATCH_DIR`; with
neither it is refused by name as JSON (`ScratchRootNotSupplied`), and a scratch
dir inside `--cases-root` is refused too. Core takes it as `strict_plan(...,
scratch_root=)`; every caller goes through `core.specs.paths.resolve_scratch_root`.
The suites supply their own (`tmp_path`), so the commands above need nothing
extra; a manual CLI run does.

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
| core never invents a filesystem root | `test_core_never_invents_a_filesystem_root`; for the scratch root, `test_the_scratch_resolver_invents_no_default` and `test_nothing_rebuilds_a_dot_omnidriver_scratch_default` |
| core threads its `DriverContext` through the public edge | `test_core_threads_its_context_through_the_public_edge` |
| an explicitly-contexted operation never falls back to the default | `test_fallback_census.py` |
| no compatibility fallback reaches cardiac code | `test_no_fallback_reaches_cardiac_code_at_all` |
| a sentinel is never converted (-1 s is never -1000 ms) | `test_a_sentinel_is_resolved_before_conversion` |
| a comparison report is written once | `test_a_report_is_written_once` |
| the capability-seam table matches the docstrings | `scripts/export-capability-seams.py --check` |
| a tutorial record/axis module never writes a case directly | `scripts/check-case-writes.py` (empty waiver list, scoped to `openfoam/axes/`, `cardiacfoam/records/`, `opencarp/records/`, `cardiaccore/records/` and the writer-free planner module `openfoam/case_planning.py`; relative imports are resolved before matching) |
| a strict plan reads C++ only at a supplied source root (`cxx_mapping.source_root`), scans it when supplied, and says `plugin_cxx_source_not_supplied` once when not | `test_truth_layer_queries.py`; against the real trees `test_strict_planning.py::test_every_strict_plan_scans_the_supplied_source`, `test_cxx_scan_native.py` (`native`) and cardiacCore's `test_dict_key_scanner_native.py` (`native_cardiaccore`) |
| a key or model the C++ reads and the catalog lacks is an `uncatalogued` note, never a failure, and a study may set the key at exactly the path the scan places its read, whether or not the case holds it; a catalog claim an anchored read refutes fails the plan | `test_cxx_scan_native.py` (`native`): `test_keys_added_to_the_cxx_plan_are_uncatalogued_and_settable`, `test_a_new_key_is_refused_at_a_path_the_cxx_does_not_read_or_with_the_wrong_type`, `test_a_model_a_scanned_selection_table_registers_plans_uncatalogued`; `test_dict_keys_scanner.py` (openfoam) |
| a solver's shell is declared in its manifest and rendered from supplied values only; a launcher from the other solver's MPI is refused | `test_environment_and_machine.py`; `test_an_mpirun_from_another_mpi_family_is_refused` (openfoam); openCARP's `opencarp_mpi_launcher_mismatch` (`native_opencarp`) |
| core names no OpenFOAM layout beyond its recorded, shrinking debt | `scripts/check-core-shape.py` (baseline `scripts/core-shape-baseline.txt`; new tokens never added) |
| every conformance target passes C1-C14 (toy, openCARP, cardiacFOAM, cardiacCore), including C11 (restaging a run case carries nothing the run wrote and drops nothing authored), C12 (every declared output format has a reader whose declaration is valid), C13 (a serial run and a parallel run give the same value of a declared quantity) and C14 (a declared quantity compares across a two-case sweep); every migrated record joins its table of targets | `omnidriver.conformance`, parametrized per package (toy in core; openCARP `native_opencarp`; cardiacFOAM `native`, `test_conformance_native.py`, run from a shell with OpenFOAM sourced and `OMNIDRIVER_NATIVE_TUTORIALS` at a clean native tree) |

## One reality

cardiacFOAM and cardiacCore are both OpenFOAM-based, so they do every shared job the same way. That covers records, catalogs and how they are built, validation, case reading and writing, and key scanning. The shared mechanism lives in `omnidriver-openfoam`, never as two variants. openCARP is a different solver and may work differently, but only inside its own package. Nothing is kept for compatibility: no legacy paths, no old format versions, no retired names.

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
- `docs/superpowers/specs/` and `plans/` — design reasoning and executed plans.
  **Start at `plans/`'s newest-dated file's own `## Status` table** for what is
  done and what is open; each phase plan tracks its own tasks there, with
  commit hashes for landed work.

- `AGENT_GUIDE.md` — the domain guide: planning, sweeping, post-processing,
  and authoring a plugin or a tutorial. Its CLI walkthrough is accurate.
  AGENT_GUIDE.md is not import-checked: the only test naming that file
  asserts it links to `SECURITY.md`, nothing verifies its module paths
  resolve. Verify an import before relying on it, and if you build that
  guard, delete this sentence.

**Read for reasoning, not for locations:** `CHANGELOG.md` and
`MIGRATION_AUDIT_v2.md`, which describe the retired flat `openfoam_driver/`
tree. Both carry a banner saying so.

## House style

Code explains what; comments explain why. This repository is prepared for
publication, and these rules bind every agent:

- **Comments only for the non-obvious:** a native solver quirk, a numerical
  trade-off, a workaround, a rule the code cannot show. Never narrate what the
  next line does.
- **Docstrings on the public surface only:** the plugin contract, capability
  seams, CLI commands, and names a package exports. Keep them short: what it
  does, its arguments and errors where not obvious. Private helpers get none,
  or one line.
- **No history in code.** No dated corrections, review or task IDs, plan
  references or "previously this did X". Git keeps history; evidence about a
  solver goes to `docs/solver-learning/`; decisions go to `docs/superpowers/`.
- **No commented-out code, and no untracked TODOs.** An open item goes to
  `docs/superpowers/ROADMAP.md`, or a GitHub issue once the owner opens one.
- **Name a symbol, never `file.py:123`.** Line numbers drift.
- Review agent output like a junior's pull request: trim tutorial-style
  comments and speculative notes before committing.

The licence question is open: there is no `LICENSE` file and no `license`
field in any `pyproject.toml`. Do not add one without asking.
