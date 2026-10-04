# omnidriver: where it stands

Read this first, after `CLAUDE.md`. It describes the state as of 2026-10-04,
with omniD `main` at `4f5ca53` and CI green. History lives in `plans/` and
`specs/`; this file is only the present and what is next.

## 1. Clean state

| repository | remote | notes |
|---|---|---|
| omniD (`svcHeidi/omniD`) | `main` = `origin/main` | No other branch or worktree. Local-only and ignored: `.venv`, caches, `.claude/`, `.superpowers/` (agent reports), `omnidriver-runtime.yaml` (the owner's machine config) |
| cardiacFOAM (`solids4foam/cardiacFoam`) | `omnid/tutorials-are-pointers` at `083ff47` | omniD's native landing branch. The owner's `main` and feature branches are theirs (§3) |
| cardiacCore (`svcHeidi/cardiacCore`) | `main` at `0b45617` | The owner's checkout is behind, with local work (§4) |

Pass 2 (`plans/2026-10-01-pass2-convergence.md`) is complete. Package source
is about 28,300 non-blank lines and tests about 28,800, down from 48,200 and
51,800.

## 2. What omnidriver is now

- **Records are the only entry kind.** A record points at a native case: its
  steps, routes and axes. `--case <dir>` runs any folder as a one-step record.
  Studies are JSON in the native tree.
- **A solver repository declares itself** in `omnidriver.toml`: its plugin,
  tutorials, C++ source and scripts. omnidriver reads it from `--repo`, or
  from the repository of a supplied cases root. It never searches for one.
- **The C++ is scanned once per source state**, and the scan is cached under
  the scratch root by a digest of the source.
- **The catalogues are the source of truth** for descriptions, units, rules
  and menus. When the C++ changes, nothing fails:

  | change | report |
  |---|---|
  | a key the C++ reads that the catalogue lacks | `uncatalogued` note |
  | a catalogued key the C++ no longer reads | `unread` note |
  | a catalogue claim the C++ contradicts | `disagreement` warning |

  `omnidriver catalog --uncatalogued` and `--unread` give an agent what it
  needs to update the catalogue.
- **Before a run**, a staged case passes the catalogue's rules and the C++'s
  required keys (`omnidriver.openfoam.case_rules`). A missing required key
  refuses the plan, naming the key, its type and the C++ class that reads it.
- **The plugin contract is one table** of 42 optional members
  (`provider_stack.MEMBERS`, called through `stack.call`), at version 3.
  `AGENT_GUIDE.md` "Adding a New Solver" has a tested minimal plugin.
- **Commands:**
  - `omnidriver check` runs conformance C1–C14 against a real solver, plus the
    native regression with `--regression` and N-rank evidence in C13. It
    reports and never gates.
  - `omnidriver build` builds a case from the catalogue when there is no
    native case. It is kept apart from the record path.
  - `describe` lists a repository's `applications/scripts`.
- **No pytest test runs a solver** or depends on a native tree's current
  content. The solvers are under development, and their authors change them
  on purpose.

## 3. cardiacFOAM: exactly where it stands

`omnid/tutorials-are-pointers` branched from native `main` at `044559d2`
(2026-09-26). Since then, native `main` has gained 13 commits (PRs #49 and
#50) and our branch 48. The owner keeps adding work on feature branches.

| branch | relation to `omnid/tutorials-are-pointers` |
|---|---|
| `origin/main` (PR #49 spring-supported slab, PR #50 single-cell pre-pacing) | **merged** into `omnid/tutorials-are-pointers` (`cfd3aeb`). Its 5 pre-pacing keys are catalogued under the `prePacingProperties` document |
| `origin/feat/insulated-wall-boundary` | pre-resolved in **`omnid/insulated-wall`** (`872d4f8`): our branch with this one merged in. Merging it directly conflicts in 11 files: 10 tutorial READMEs and `restitutionCurves_s1s2Protocol/setup/postProcessing_restCurves.py`. We rewrote those READMEs and ported that script; the branch edited the old versions |
| `origin/feat/heart-in-bath` (on top of insulated-wall) | pre-resolved in **`omnid/heart-in-bath`** (`dadb2fe`). Its `bathBidomain/insulatedWall` uses `interfaceConductivityInterpolation conormalHarmonic`, a value chosen by an `if` chain the scan cannot read yet, so it is refused (§5) |
| `origin/codex/regression-and-restart-fixes` | merges cleanly |

What the owner's feature branches add, as omnidriver will see it:

- **Two required keys.** `sealedHeartBoundary` (`Switch`, read in
  `monodomainSolver.C`) and `sealedWallTrace` (`word`, read in
  `bidomainSolver.C`). A case without them is refused before running, with
  an explanation. The branch's own tutorials set them.
- **Optional keys:**
  - `exposedFacesPatch` (`myocardiumDomainInterface.C`);
  - `offsetField` (`conormalZeroFluxFvPatchScalarField.C`);
  - `productionPatches` (`manufacturedEikonalVerifier.C`);
  - on heart-in-bath, also `bathHeartPhiETrace` (`bidomainSolver.C`) and
    `sigmaB` (`manufacturedConormalBathBidomainVerifier.C`).
- **New tutorial cases with no omniD record yet:**
  - `insulatedWall` cases for bidomain, eikonalECG and monodomainPseudoECG;
  - on heart-in-bath, also bathBidomain's `insulatedWall` and
    `idealizedHeart/electroHeartBath`.

  These run through `--case`, or get a record.

**Order when the owner is ready:**
1. Merge `omnid/tutorials-are-pointers` into native `main`, or the reverse;
   it is clean.
2. When a feature branch lands on `main`, resolve its 11 conflicts by keeping
   our README and script versions and re-applying the branch's changes to
   them.
3. Run `omnidriver catalog --uncatalogued`, and describe the new keys in the
   catalogue.
4. Add records for the new cases where a study needs them.

**The installed `cardiacFoam`** (in `~/OpenFOAM/simaocastro-v2412`) was built
from the insulated-wall work. Against tutorials without the new keys it
fails, which omnidriver reports before running. A binary built from source
other than the scanned source is named in the run result.

## 4. cardiacCore: exactly where it stands

The owner's checkout (`~/cardiacCoreStandalone`, branch `main`) is at
`f0fc231`: 11 commits behind `origin/main` and 0 ahead.

- **`git pull --ff-only` is refused today.** The incoming commits change one
  line of `docs/superpowers/specs/2026-09-23-septal-midline-purkinje-seeds-RESULTS.md`
  (the moved script's path, `scripts/` → `applications/scripts/`), and the
  owner has 51 uncommitted added lines in the same file. Commit those edits
  first; the pull should then merge cleanly, since the changes are on
  different lines.
- **An uncommitted C++ change in `src/setCardiacConductivity/setCardiacConductivity.C`.**
  It adds a fibre-only basis: `sheet` and `normal` become optional pointers,
  giving a transversely isotropic tensor with one conductivity across the
  fibre.
  - Nothing incoming touches that file.
  - Once committed, a rescan reports `sheet` as no longer required.
  - The record `humanSlab` and the idealized-heart cases still ship `sheet`,
    which stays valid.
  - The installed utilities in `/Volumes/OpenFOAM-v2412` were rebuilt on
    2026-09-28 at 20:22, after omniD's rebuild that day, so they likely come
    from this local change.
- **Untracked local work, with no path collisions:**
  - `agent/`;
  - `cases/idealizedBivEllipsoid*`, with a pre-cobiveco backup;
  - `tutorials/idealizedBivEllipsoid/`;
  - `docs/purkinje-growth-activation-roadmap.md`.

  `cases/idealizedBivEllipsoidPig/README.md` still names `scripts/`, which
  moved to `applications/scripts/` on `main`.
- **On `main` now:**
  - `omnidriver.toml`;
  - `applications/scripts/` (the former `scripts/`, plus omniD's former
    `operations/`, as command-line scripts with tests);
  - the three idealized-heart cases with regression tests;
  - the ring-closure check, which reads the case's coordinate convention.
    Its base is 1 by default, from `computeAhaFrame`, and ring spacing is
    measured against each chamber's own range.
- **Not on `main`:** the scar work stays on the `scar` branch.

## 5. Next

1. **Menus from `if` chains.** For a word key the C++ compares against literals (`== "conormalHarmonic"`), the scan reads those literals as the menu. A value the C++ accepts and the catalogue lacks is then an `uncatalogued` note, not a refusal.
2. **Electrophysiology testing and training** with the records, `check` and
   the catalogues. Then **electromechanics**: the owner builds its record,
   and omniD supports it through `WorkflowStep` features as needed.
3. **The electrode unit seam.** cardiacFOAM reads electrode positions in
   metres. cardiacCore's `applications/scripts/electrode_positions.py` takes a
   caller-declared unit and converts nothing, so a millimetre case gives a
   pseudo-ECG a factor of 1000 off. This belongs with SI and units: a
   `native_unit` on axes, with sweeps in SI.
4. **The Niederer campaign on a cluster** (`benchmarks/niederer2011/campaign/`).
   Use `check --checks C13` for N-rank evidence, and rescan first if the
   solver changed.
5. **Later:**
   - one run using cardiacCore and cardiacFOAM steps
     (`specs/2026-09-18-cross-adapter-workflow-design.md`);
   - more TOML records;
   - region-aware key validation;
   - the licence. There is no `LICENSE`, and `CLAUDE.md` says not to add one
     without asking.
