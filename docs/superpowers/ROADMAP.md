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
  | a key, or an enum value the C++ compares against, that the catalogue lacks | `uncatalogued` note |
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
| `origin/feat/heart-in-bath` (on top of insulated-wall) | pre-resolved in **`omnid/heart-in-bath`** (`dadb2fe`). Its `bathBidomain/insulatedWall` uses `interfaceConductivityInterpolation conormalHarmonic`, a value chosen by an `if` chain. The scan reads the literals the chain compares as the menu, so the case plans `ok` and `conormalHarmonic` is an `uncatalogued` note |
| `origin/codex/regression-and-restart-fixes` | merges cleanly |

**Provisional work.** Everything only on a feature branch is provisional:
the insulated wall, the heart in a bath, the conormal interpolation and their
keys and cases. omnidriver treats it that way:
- it adds no catalogue entry and no record for it;
- nothing on omniD `main` depends on it;
- scanning such a branch shows its keys only as `uncatalogued` notes.

`omnid/insulated-wall` and `omnid/heart-in-bath` are provisional too. When
the work lands on native `main`, omnidriver's change is small: catalogue
entries for its keys, and a record for any new tutorial a study needs. A few
omniD tests use verbatim snippets of that C++ as frozen fixtures for the
generic scanner; they test the mechanism, not the feature.

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

`origin/main` is at `4d2b22a`. The owner's checkout (`~/cardiacCoreStandalone`)
is still on `f0fc231`. It has no tracked changes, so `git pull --ff-only` is
clean.

- **The owner's fibre-only conductivity** (`setCardiacConductivity`) is on
  `main`, authored by the owner (`bf3b9c4`):
  - with a `sheetField`, the output is byte-identical to before;
  - without one, it writes `dt·I + (df − dt)·f⊗f`, checked at every cell of
    the idealized heart (`cases/idealizedHeart/regression/fibreOnlyConductivityTest.sh`);
  - the installed utility in `/Volumes/OpenFOAM-v2412` is built from this
    change.
- **Results are not in the repository.** cardiacCore holds the methods. The
  validation results on local anatomies live in the owner's git-ignored
  `local/` folder, which holds `results/`, `notes/` and `reference_assets/`.
- **Purkinje tools, current and legacy:**

  | tool | status | basis |
  |---|---|---|
  | `applications/scripts/place_purkinje_seeds.py` | current | used by the 2026-09-23 septal-midline seed results |
  | `applications/scripts/check_purkinje_activation.py` | current | the owner's original tool, verbatim, used by the same results |
  | `applications/scripts/legacy/purkinje_coverage.py` | legacy | the June 2026 seed-deduction coverage check, superseded. The owner has not confirmed its correctness. Keep it unchanged and separate |

- **Also on `main`:**
  - `omnidriver.toml`;
  - `applications/scripts/` (the former `scripts/`, plus omniD's former
    `operations/`);
  - the three idealized-heart cases with regression tests;
  - the ring-closure check. It reads the case's coordinate convention; the
    base is 1 by default, from `computeAhaFrame`, and spacing is measured
    against each chamber's own range.
- **The catalogue matches the C++:** the four records plan with no
  diagnostics. The coordinate-convention and Purkinje-tree keys the C++
  reads without a default are catalogued as required. A
  `coordinatesConventionDict` must therefore carry every block, as all
  native cases do.
- **Untracked local work, left as it is:**
  - `cases/idealizedBivEllipsoid*`;
  - `tutorials/idealizedBivEllipsoid/`;
  - `local/`.

  `cases/idealizedBivEllipsoidPig/README.md` still names `scripts/`, which
  is now `applications/scripts/`.
- **Not on `main`:** the scar work stays on the `scar` branch.

## 5. Next

1. **Electrophysiology testing and training** with the records, `check` and
   the catalogues. Then **electromechanics**: the owner builds its record,
   and omniD supports it through `WorkflowStep` features as needed.
2. **The electrode unit seam.** cardiacFOAM reads electrode positions in
   metres. cardiacCore's `applications/scripts/electrode_positions.py` takes a
   caller-declared unit and converts nothing, so a millimetre case gives a
   pseudo-ECG a factor of 1000 off. This belongs with SI and units: a
   `native_unit` on axes, with sweeps in SI.
3. **The Niederer campaign on a cluster** (`benchmarks/niederer2011/campaign/`).
   Use `check --checks C13` for N-rank evidence, and rescan first if the
   solver changed.
4. **Later:**
   - one run using cardiacCore and cardiacFOAM steps
     (`specs/2026-09-18-cross-adapter-workflow-design.md`);
   - more TOML records;
   - region-aware key validation;
   - the licence. There is no `LICENSE`, and `CLAUDE.md` says not to add one
     without asking.
