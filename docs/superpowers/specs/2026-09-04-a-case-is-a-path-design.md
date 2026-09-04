# A case is a path: removing core's ambient root resolution

**Status:** design, approved 2026-09-04.

Closes the defect found on 2026-09-03: **core cannot plan a case from an
installed wheel**, because it discovers a repository root instead of receiving
a case location. The same disease, and the same cure, as the implicit
`DriverContext` removed the day before.

## The evidence

    strict_plan -> registry.load_entry_spec -> registry.resolve_entry
                -> specs/paths.tutorials_root_default() -> repo_root_default()
                -> RuntimeError

`repo_root_default()` walks up from `Path(__file__)` of the *installed module*.
In a wheel install nothing above `site-packages` carries the markers, so it
raises. Thirteen tests fail against a wheel today for this one reason. Every
CI job installs editable, which leaves the repository on disk, so this has
never been visible.

## The insight this design turns on

A case directory already describes itself. `registry._is_case_directory(path,
driver_context)` answers "is this a runnable case?" **purely from the
directory's own contents**, through the plugin's declared marker or entrypoint
contract. It takes a path. It needs no root.

Measured 2026-09-04 against a directory in `/tmp` containing `Allrun` and
`system/controlDict`:

| probe | result |
|---|---|
| `_is_case_directory(/tmp/anycase/mycase, ctx)` | **True** |
| `resolve_entry("/tmp/anycase/mycase", entry_kind="case_folder")` | **KeyError: Unknown entry** |
| `resolve_entry("mycase", overrides={"tutorials_root": "/tmp/anycase"})` | resolves |

So the tool already knows how to recognise a case anywhere on disk, and its
entry API refuses to accept one. `tutorials_root` is not providing capability
or containment; it forces the caller to split a path into two halves so core
can rejoin them. **The root is an artifact, not a requirement.**

## Two directions, only one of which needs a base

The single name `tutorials_root` serves two genuinely different jobs. Keeping
them separate is the whole design.

**Resolve — an existing case.** Identified by its path, absolute or relative
to the current directory, exactly as `docker build .`, `make -C dir` and
`pytest path/` identify their target. `_is_case_directory` decides
runnability. **No base directory is involved**, and this is the direction that
raises `RuntimeError` from a wheel today.

**Construct — a registered tutorial factory.** `niederer2012` and its siblings
are spec *factories*: they build a case named by the tutorial under some base
(`base / case_dir_name`). A base is genuinely required here. It is not a
repository root; it is simply "where should this be built".

## What changes

1. **`resolve_entry` accepts a path as a first-class entry.** An absolute or
   cwd-relative path that satisfies `_is_case_directory` resolves to a
   `case_folder` entry regardless of where it lives. This alone removes the
   wheel-install failure for the run path.

2. **Core keeps no ambient default.** `tutorials_root_default()`,
   `driverfoam_scratch_root()` and `default_sweep_output_dir()` leave core's
   runtime. Core functions that need a base take it as a parameter.
   `repo_root_default()` survives for **dev tooling only** — `architecture_path()`
   and `scripts/` — and moves out of `core/specs/` so runtime code cannot reach
   it.

3. **`--tutorials-root` survives**, with its meaning narrowed to the two jobs
   that are real: where to *enumerate* cases when listing
   (`list_case_directories`, `list_entries`, `list_available_tutorials`), and
   the base a registered factory *builds* under. Both are "a base directory
   for cases", which is one coherent meaning.

4. **The default base becomes the current working directory**, resolved at the
   public edge only:

       explicit argument / --tutorials-root
          -> absent: OMNIDRIVER_CASES_ROOT
          -> absent: current working directory

   Three steps, no fourth. Deliberately **no config-file tier**: the
   environment variable already covers CI, containers and HPC, and the
   existing `driverfoam-runtime.yaml` is plugin-owned machine config. Promoting
   it to core is a larger change with no evidence yet that it is needed.

5. **Listing an empty or non-case directory returns nothing**, rather than
   raising. Zero results is a legitimate answer to "what cases are here".

6. **Scratch moves out of the repository.** `.tmp/driverfoam` becomes
   `OMNIDRIVER_SCRATCH_DIR`, else `<base>/.omnidriver`. Deliberately **not**
   the OS temp directory: sweep outputs default here, and putting them
   somewhere the OS reaps would be worse than today's behaviour. Workspace-local
   keeps them findable and works on a read-only install.

## The registered tutorials must keep working

This is the binding constraint on the design, and it is settled by measurement
rather than argument. Every registered factory was called with a fresh empty
temporary directory as its base (2026-09-04, all three packages installed):

- **18 of 26 catalog entries build under an arbitrary base**, `niederer2012`
  among them. Those 26 entries are 13 tutorials plus their case-folded
  aliases. Changing the default base from the repository root to the current
  directory therefore preserves them: they build under the current directory
  instead.
- **8 entries (4 distinct tutorials — `manufacturedBathBidomain`,
  `manufacturedBidomain`, `manufacturedEikonalECG`,
  `manufacturedMonodomainPseudoECG`) fail with `ValueError: numberOfSubdomains
  not found`.**

  The dependency is exactly **one file and one key**, not "monorepo content"
  generally. These four default to `RUN_IN_PARALLEL = True`, and a parallel
  solve changes the workflow DAG's *shape* — `decomposePar`, then
  `mpirun -np N solver -parallel`, then `reconstructPar`, instead of one plain
  step. `N` is not something the factory can invent, so
  `omnidriver-openfoam/parallel_execution.py:16` reads it off disk at
  **spec-construction time** from `<case>/system/decomposeParDict`. Verified
  2026-09-04: writing only that file (three lines,
  `numberOfSubdomains 4;`) under an arbitrary empty base makes
  `manufacturedBidomain` build. Nothing else from the monorepo is required.
  The other nine tutorials are serial, never read it, and build anywhere.

  **These already fail today, identically.** This repository has no
  `tutorials/` directory, so `tutorials_root_default()` already returns the
  bare repository root and `manufacturedBidomain` raises the same error there
  right now. This design does not regress them; `skip_without_monorepo` is
  what already gates their tests.

  This is **not** an agnosticity leak: `decomposeParDict` and
  `numberOfSubdomains` are OpenFOAM vocabulary living in
  `omnidriver-openfoam`, which is the correct package. It *is* a real coupling
  — planning reads the case — and it is orthogonal to this design. See the
  follow-up below.

The acceptance test below pins both halves so a future change cannot quietly
break the generative tutorials.

## Trust boundary: unchanged

Accepting an arbitrary path introduces no new exposure. `SECURITY.md` already
classes case content as *"untrusted, unsandboxed by design — running a case
runs its scripts"*, and
`future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md` explicitly records
"arbitrary code inside an invoked `Allrun`" as accepted and not mitigated. The
root never provided containment and was never claimed to. Naming a directory
is the operator's explicit opt-in, the same act as naming it under a root
today.

## Success criteria

> **All met 2026-09-04.** `pytest packages/omnidriver/tests` against an
> installed wheel: **544 passed, 237 skipped, 0 failed** — from 13 failures and
> 8 collection errors. Full suite **1566 passed** on 3.11 and 3.13, core-only
> **688**, both static gates green, and CI's `test-wheel` job now runs the
> suite rather than only the artifact gate. Implemented by
> `docs/superpowers/plans/2026-09-04-a-case-is-a-path.md`.

Stated as things that were false before, and are now true:

1. `pytest packages/omnidriver/tests` **passes against an installed wheel**
   (13 failures today, all one cause), and CI's `test-wheel` job runs the suite
   rather than only `scripts/check-wheel-artifact.py`.
2. From any directory, with only `omnidriver` installed from a wheel:
   `resolve_entry("<path to a case dir>", entry_kind="case_folder")` resolves.
   Today it raises `KeyError`.
3. `niederer2012` builds under the current directory with no flags, no
   environment variable and no repository. Verified by an acceptance test that
   also asserts the 4 content-dependent tutorials still need the monorepo, so
   the distinction is recorded rather than rediscovered.
4. A static guard, mirroring `test_core_context_is_explicit.py`: **no module
   under `core/` may call a root-defaulting function.** The named set is
   written out explicitly, with a companion test that fails if a name in it
   stops existing, so the guard cannot rot into passing vacuously.
5. Full suite green on 3.11 and 3.13; `scripts/check-import-boundaries.py` and
   `scripts/export-capability-seams.py --check` still pass.

## Risks

**A breaking change to a public CLI surface, and to the daily loop.** Running
from the repository root will no longer implicitly find a `tutorials/` tree.
Restoring today's behaviour is `export OMNIDRIVER_CASES_ROOT=$PWD/tutorials`
once, or `--tutorials-root`. This is friction felt daily, so it is a
deliberate choice rather than a side effect — the implicit behaviour is
precisely the defect.

**Rename scope.** `tutorials_root` appears 397 times, overwhelmingly in tests
passing the keyword. The threading change and any rename are separable and
must land as separate commits: threading first (behaviour, verified by the
wheel suite going green), rename second (mechanical, verified by the suite
being unchanged). A combined commit makes review harder and a revert
all-or-nothing.

**`resolve_run_script_path` falls back through `repo_root_default()`** as one
of three candidate roots. It must be rechecked when core's default disappears;
it is not covered by the two directions above and is the most likely place for
a surprise.

## Follow-up, deliberately not designed here: execution resources

Recorded because it is the same disease as this spec — a value that should be
*supplied* is instead *discovered* — and because it generalises well beyond
MPI. **Not designed in this document**; it needs its own brainstorm.

Parallelism today is one boolean plus one MPI-specific read:
`run_in_parallel: bool`, and if true, `numberOfSubdomains` from the case's
`decomposeParDict`. That hardcodes a single parallel model. GPU and OpenMP
need different knobs, and — this is the part that matters for the design —
they differ in *kind*, not just in units:

| model | knob | what it changes |
|---|---|---|
| MPI | ranks | the DAG's **shape**: decompose / `mpirun -np N` / reconstruct |
| OpenMP | threads | only the **environment** (`OMP_NUM_THREADS`); same DAG |
| GPU | devices | environment and/or solver flags; usually the same DAG |

Two seams already exist to carry that split. DAG shape is built by the
tutorial/plugin factory. Environment mutation goes through the plugin's
`configure_execution_environment(env)`, reached by a `getattr` probe in
`omnidriver-openfoam/openfoam_environment.py:234` — note that is an
openfoam-mediated hook, **not** a core capability seam, which is itself worth
revisiting.

**Resolved 2026-09-04, by deciding not to build it.** GPU appears in this
codebase only as descriptions of C++ models ("GPU batched implementation") —
a property of the solver, not a launch mode, so omnidriver runs the same
binary either way and has nothing to plumb. OpenMP appears nowhere. Giving
core a `ranks`/`threads`/`devices` vocabulary for hardware that is not wired
up would repeat the `Phase` literal removed on 2026-09-03: core naming a
closed set of one ecosystem's concepts. When a real GPU or OpenMP launch path
exists it will show its own shape, and there will be a concrete case instead
of a guess.

What the discussion did settle is a rule worth stating, recorded in
`future/ENVIRONMENT_CONTRACT.md` §12: **discover only what genuinely exists
ambiently, and declare where you look.** A case root has no ambient truth, so
discovering one invents an answer — that is this document's defect. Execution
resources do have ambient truth (a scheduler allocated them), so discovering
them is correct; the defect there was discovering from a *hardcoded* place at
spec-construction time.

What was built instead, 2026-09-04: `solve_steps()` gained an optional
`num_subdomains`, so a parallel solve step can be built without a case on
disk. Precedence is **the case's `decomposeParDict` wins whenever it exists**,
with `num_subdomains` as the fallback — deliberately that way round, because
`decomposePar` reads the same dictionary: an explicit override would create
six processor directories and then run `mpirun -np 2` against them. The
dictionary is the one place both commands agree.

Note this does **not** make all 26 catalog entries build with no arguments.
The four parallel tutorials still need either their case on disk or an
explicit count; what changed is that a route now exists and the error names
both. Declaring a default rank count per tutorial was considered and rejected:
it would duplicate a number that already lives in each shipped
`decomposeParDict`, creating a second source of truth for no gain, and this
repository has no `tutorials/` tree against which to check what those numbers
are.

## Out of scope

Promoting `driverfoam-runtime.yaml` to core; the AGENT_GUIDE rewrite;
licensing.
