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
  not found`.** They read pre-existing case content rather than generating it,
  so they need the cardiacFoam monorepo `tutorials/` tree.

  **These already fail today, identically.** This repository has no
  `tutorials/` directory, so `tutorials_root_default()` already returns the
  bare repository root and `manufacturedBidomain` raises the same error there
  right now. This design does not regress them; `skip_without_monorepo` is
  what already gates their tests.

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

Stated as things that are false today and must become true:

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

## Out of scope

The `numberOfSubdomains` dependency in the four manufactured-solution
tutorials; promoting `driverfoam-runtime.yaml` to core; the AGENT_GUIDE
rewrite; licensing.
