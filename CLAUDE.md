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

The suites must pass in three different shapes, and each catches something the
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
| all packages | `python -m pytest packages/ -q -m "not slow"` | ordinary regressions |
| core alone | `python -m pytest packages/omnidriver/tests -q` | core reaching into a sibling package |
| **installed wheel** | see below | core reading repo-relative state at import time |
| static gates | `python3 scripts/check-import-boundaries.py`, `scripts/check-case-writes.py`, `scripts/check-core-shape.py`, and `scripts/check-benchmark-references.py` | import direction; a tutorial-record/axis module writing a case directly instead of through `commit_case_write`; core gaining a new OpenFOAM layout token or growing its recorded debt; a benchmark reference under `benchmarks/` that fails to load, misnames its own id, or cites nothing |

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

**No pytest test runs a solver.** The only tests that meet an OpenFOAM install
are six probes of omnidriver's own dictionary reader against `foamDictionary` and
`foamEtcFile`, which run when a bashrc is sourced and say nothing of any solver.
The solvers are in development: their authors add required keys, rename models and
rebuild on purpose, and a test pinned to their current state would fail for
doing so. Pytest tests omnidriver itself: unit tests, the toy conformance
target, and the scanner on verbatim snippets of the native C++ committed as
fixtures (a snippet is real source, never invented).

**Against a solver you are working on, `omnidriver check` reports; it never
gates.** It runs the conformance checks C1-C14 (and with `--regression` the
record's native regression script, in a copy) against the real solver and
prints the verdicts as JSON; the exit code is 0 whenever the checks ran. Each
record declares how it is exercised briefly (`TutorialRecord.conformance`).
Run it from the solver's own shell: `omnidriver env --plugin <p>` lists each
variable to supply and prints the `shell_prefix` (source OpenFOAM, then
export `DYLD_LIBRARY_PATH`, which macOS strips when bash starts).

```bash
omnidriver check --repo <cardiacFOAM> --scratch-dir <scratch> --record singleCell --benchmarks <omnidriver>/benchmarks
omnidriver check --plugin opencarp --cases-root <opencarp>/share/tutorials --scratch-dir <scratch> --benchmarks <omnidriver>/benchmarks
omnidriver check --plugin cardiaccore --cases-root <cardiacCore> --scratch-dir <scratch> --input anatomy=<humanSlab bundle>
```

The tree under check should be clean (a `git archive` of the branch), since C11
reads git-ignored run output in a case as authored. **The two MPIs must never
mix:** each solver's shell puts only its own MPI first on `PATH` (OpenFOAM's from
its bashrc, openCARP's from `OPENCARP_MPI_BIN`), and preflight refuses the other
one by name (`openfoam_mpi_launcher_mismatch`, `opencarp_mpi_launcher_mismatch`).
C13 runs a record's declared quantity serial and at N = 2, compares them, and
reads the solver's own output for the rank count (`RankEvidence`: a log pattern,
and for OpenFOAM the `processor*` directories), so N serial copies cannot pass;
C14 compares it across a two-case sweep; a record that declares no quantity passes
both and says so. Inside a Slurm allocation, `SLURM_NTASKS` must equal 2.

**The scratch root is supplied, never invented.** Anything that
stages — `plan --strict`/`step`/`run --strict`/`check` over a tutorial record or a
`--case` folder, or a sweep with no `--output-dir` — needs `--scratch-dir <dir>`
or `OMNIDRIVER_SCRATCH_DIR`; with neither it is refused by name as JSON
(`ScratchRootNotSupplied`), and a scratch dir inside the cases root is refused
too. Core takes it as `strict_plan(...,
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
| core never invents a filesystem root | `test_core_never_invents_a_filesystem_root` (no `__file__`, `Path.cwd`, `Path.home` or `os.getcwd` in the package but two named uses); for the scratch root, `test_the_scratch_resolver_invents_no_default` and `test_nothing_rebuilds_a_dot_omnidriver_scratch_default` |
| core threads its `DriverContext` through the public edge | `test_core_threads_its_context_through_the_public_edge` |
| every plugin contract member is optional: `provider_stack.MEMBERS` gives each its composition and its answer when no provider implements it, and an operation that needs one refuses by name; a provider's public callable that names no member is refused | `test_plugin_contract.py` |
| no fallback reaches cardiac code: the stack's only fallbacks are the member table's absent answers, which take no argument and sit in a module importing nothing outside core | `test_no_fallback_reaches_cardiac_code_at_all` |
| a sentinel is never converted (-1 s is never -1000 ms) | `test_a_sentinel_is_resolved_before_conversion` |
| a comparison report is written once | `test_a_report_is_written_once` |
| a tutorial record is the only entry kind; a case folder that is no record runs as an ad hoc one-step record of the stack's declared entrypoint (`--case`), staged from the folder and never written | `test_case_folder_record.py`; `test_tutorial_records.py` |
| a solver repository names its plugin, tutorials, C++ source and scripts in `omnidriver.toml`, read only from `--repo` or the repository of a supplied cases root (never searched for); `--plugin` alone serves a solver with no repository, and when both are given they must select the same stack | `test_repository.py`; `test_repository_source.py` (cardiacfoam) |
| a repository's scripts folder (`omnidriver.toml`'s `scripts`, carried on the `DriverContext` as `repository`, which every child process the stack starts receives as `--repo`) is the only truth about its scripts: `describe` lists them with a usage line read from the file and runs none, and only a script a step may run is listed; a step may name one, which then runs under the `python3` on the stack's own `PATH`; a name outside the folder is an unknown command, and a script named like a case script, plugin command or installed command is refused as ambiguous | `test_scripts.py` (core) |
| a plan report carries one `plugin_diagnostics` list, composed by the stack's `get_plan_diagnostics`; core names no function-object, nondimensional or dictionary-resolution concept | `scripts/check-core-shape.py`; `test_strict_planning.py`; `test_plan_diagnostics.py` (openfoam) |
| a tutorial record/axis module never writes a case directly | `scripts/check-case-writes.py` (empty waiver list, scoped to `openfoam/axes/`, `cardiacfoam/records/`, `opencarp/records/`, `cardiaccore/records/` and the writer-free planner module `openfoam/case_planning.py`; relative imports are resolved before matching) |
| a strict plan reads C++ only at a supplied source root (`cxx_mapping.source_root`), scans it when supplied, caches the scan under the supplied scratch root by a digest of the source and the scanner, and says `plugin_cxx_source_not_supplied` once when not | `test_plan_diagnostics.py`, `test_dict_keys_scanner.py` (openfoam) |
| a key or model the C++ reads and the catalog lacks is an `uncatalogued` note carrying what the scan knows, a catalogued key the C++ no longer reads an `unread` note (a case that sets it a warning), a catalog claim the C++ refutes a `disagreement` warning stating both sides: none of them fails a plan, and a study may set an uncatalogued key at exactly the path the scan places its read; a value is judged against the kind the C++ reads | `test_dict_keys_scanner.py`, `test_plan_diagnostics.py`, `test_runtime_selection_report.py`, `test_cxx_requirements.py` (openfoam) |
| a resolved record case passes the catalogue's relations, the enum menus (the names the C++'s selection table registers when its source is supplied) and the cross-field rules before it runs, `omnidriver.openfoam.case_rules` being the one evaluator of them; a key the supplied C++ reads with no default in a class the case builds is refused when missing, and noted when the scan cannot tell whether the case builds the class; `step --apply` runs the same rules after its edit | `test_case_rules.py`, `test_cxx_requirements.py` (openfoam), `test_case_rules.py` (cardiacCore), the commit and apply tests in core's `test_tutorial_records.py` |
| a solver's shell is declared in its manifest and rendered from supplied values only; a launcher from the other solver's MPI is refused | `test_environment_and_machine.py`; `test_an_mpirun_from_another_mpi_family_is_refused` (openfoam) |
| core names no OpenFOAM layout beyond its recorded, shrinking debt | `scripts/check-core-shape.py` (baseline `scripts/core-shape-baseline.txt`; new tokens never added) |
| every conformance check C1-C14 passes for the toy target, and C3 to C14 are each given a deliberate break it must catch (a broken toy plugin; for C14, a quantity pair the target breaks; C1 and C2 fail only for a record the stack does not serve); a real solver's records are exercised by `omnidriver check`, which reports and never gates | `test_conformance_toy.py` (core); `test_check_command.py` (core) |

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
consumers: a fallback computed *before* the branch that would have avoided it,
so a call that supplied its path still raised. If a default can raise, compute
it only when you need it: `resolve_scratch_root` runs only once an operation
stages.

## Traps

**A test module that calls a raising function at import time cannot be
skipped.** It errors during collection, before any marker applies. Use
`conftest`'s `repo_root` / `skip_without_repo` (non-raising) rather than a
lookup that raises at module scope.

**"No Python imports" does not mean unused.** `gmsh` is declared for the
**binary** its wheel installs, which cardiac tutorials invoke as a workflow
command. An import scan reads it as dead; removing it breaks four tutorials at
runtime, silently.

## Where authority lives

- `future/ENVIRONMENT_CONTRACT.md` — what core owns and how. Supersedes
  `ARCHITECTURE.md`'s Rule 1. §12 is the supplied-vs-discovered rule.
- `ARCHITECTURE.md` — the layer map.
- `docs/superpowers/specs/` and `plans/` — design reasoning and executed plans.
  **Start at `plans/2026-10-01-pass2-convergence.md`**: its `## Decisions` are
  the owner's, and its `## Tracks` say what each piece of work was for; the
  older plans are the executed record.

- `AGENT_GUIDE.md` — the domain guide: planning, sweeping, post-processing,
  and authoring a plugin or a tutorial. Its minimal plugin is a tested fixture
  (`test_agent_guide_plugin.py`); the rest is not import-checked, so verify a
  module path before relying on it.

**Read for reasoning, not for locations:** `CHANGELOG.md` and
`MIGRATION_AUDIT_v2.md`, which describe the retired flat `openfoam_driver/`
tree. Both carry a banner saying so.

## House style

Code explains what; comments explain why. This repository is prepared for
publication, and these rules bind every agent:

- **Comments only for the non-obvious:** a native solver quirk, a numerical
  trade-off, a workaround, a rule the code cannot show. Never narrate what the
  next line does.
- **Docstrings on the public surface only:** the plugin contract, CLI
  commands, and names a package exports. Keep them short: what it
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
