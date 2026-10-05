# omnidriver: where it stands

Read this first, after `CLAUDE.md`. It describes the state as of 2026-10-05.
History lives in `plans/` and `specs/`; this file is only the present and what
is next.

## 1. Clean state

| repository | remote | notes |
|---|---|---|
| omniD (`svcHeidi/omniD`) | `main` = `origin/main` | The only long-lived branch; a commit cannot name its own hash, so `git log -1` is the head. Local-only and ignored: `.venv`, caches, `.claude/`, `.superpowers/` (agent reports), `omnidriver-runtime.yaml` (the owner's machine config) |
| cardiacFOAM (`solids4foam/cardiacFoam`) | `origin/main` at `0b1bf13c`; `origin/omnid/tutorials-are-pointers` at `e3e3fc8a` | omniD's native landing branch contains native `main`: 60 commits ahead, none behind. The owner's local `omnid/tutorials-are-pointers` is at `c7d5bd1c`, 19 behind its remote. The owner's feature branches are theirs (§3) |
| cardiacCore (`svcHeidi/cardiacCore`) | `main` at `4d2b22a` | The owner's checkout is behind, with local work (§4) |

Pass 2 (`plans/2026-10-01-pass2-convergence.md`) is complete.

## 2. What omnidriver is now

- **Records are the only entry kind.** A record points at a native case: its
  steps, routes and axes. `--case <dir>` runs any folder as a one-step record.
  Studies are JSON in the native tree.
- **A solver repository declares itself** in `omnidriver.toml`: its plugin,
  tutorials, C++ source and scripts. omnidriver reads it from `--repo`, or
  from the repository of a supplied cases root. It never searches for one, and
  a cases root or a scratch root has no default.
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
- **Before a run**, a staged case passes the catalogue's relations, enum menus
  and numeric bounds, over each catalogued document including `system/controlDict`
  and cardiacFOAM's `prePacingProperties`, plus the C++'s required keys and
  cardiacFOAM's cross-field rules (`omnidriver.openfoam.case_rules`). A break
  refuses the plan, naming the key and the rule; for a required key, its type
  and the C++ class that reads it. A plan whose environment is not ready is
  `blocked`, with a non-zero exit.
- **A run is stateful through its run document.** `--entry` and `--case`
  always restage; `plan`, then `run`/`step --run-document`, resumes. A resume
  is bound to the commands and the stack's declared variables, not to `PATH` or
  file locations, and a refusal names what differs. `--fresh` starts a run
  document or a sweep over. `step --apply` edits the staged case, rolls the edit
  back when the rules refuse it, and runs the step.
- **A failed step is explained.** An OpenFOAM stack reads the solver's own
  `log.<application>` when the exit code hides the failure, and a sweep case or
  a check says why it failed.
- **A sweep case is one folder** under `<output>/cases/<case_id>/`; its status
  lives only in its `workflow_state.json`, and the sweep manifest keeps what the
  sweep observed as `sweep_outcome`.
- **Every command refuses a bad call in one JSON shape**
  (`{"status": "failed", "error": ...}`, exit 1).
- **The plugin contract is one table** of optional members
  (`provider_stack.MEMBERS`, called through `stack.call`), at API version 3.
  `AGENT_GUIDE.md` "Adding a New Solver" has a tested minimal plugin.
- **Commands:**
  - `describe` lists a stack's records (with `serial_only`), its repository
    `scripts` and the installed plugin ids; with `--entry`, the keys a record's
    own solver allows.
  - `omnidriver check` runs conformance C1–C14 against a real solver, plus the
    native regression with `--regression` and N-rank evidence in C13. It
    reports and never gates; a check that verifies nothing for a record is
    `not_applicable`.
  - `omnidriver build` builds a case from the catalogue when there is no
    native case. It is kept apart from the record path.
  - `omnidriver compare` compares quantities read from two runs' artifacts.
- **No pytest test runs a solver** or depends on a native tree's current
  content. The solvers are under development, and their authors change them
  on purpose.

## 3. cardiacFOAM: exactly where it stands

Native `origin/main` (`0b1bf13c`, 2026-10-04) has PRs #49 (spring-supported
slab), #50 (single-cell pre-pacing), #51 (the insulated wall) and #52 (ECG and
conduction-block regressions). `origin/omnid/tutorials-are-pointers` has merged
it. The ten records plan `ok` against that tree, with only `uncatalogued`
notes.

| branch | relation to `origin/omnid/tutorials-are-pointers` |
|---|---|
| `origin/main` | contained in it; native `main` can fast-forward to it |
| `origin/feat/heart-in-bath` (one commit, `bdd84052`, on top of `main`) | merging it directly conflicts in one file, `monodomain1DCableCV/README.md` |
| `origin/omnid/heart-in-bath` (`6b1ecb2f`) | pre-resolved: our branch with heart-in-bath merged in; it merges cleanly. Its `bathBidomain/insulatedWall` uses `interfaceConductivityInterpolation conormalHarmonic`, a value chosen by an `if` chain. The scan reads the literals the chain compares as the menu, so the case plans `ok` and `conormalHarmonic` is an `uncatalogued` note |
| `origin/omnid/insulated-wall` | contained in it; no longer needed |

**Provisional work.** The heart in a bath is only on a feature branch, so it is
provisional, and omnidriver treats it that way:
- it adds no catalogue entry and no record for it;
- nothing on omniD `main` depends on it;
- scanning such a branch shows its keys only as `uncatalogued` notes.

`omnid/heart-in-bath` is provisional too. When the work lands on native `main`,
omnidriver's change is small: catalogue entries for its keys, and a record for
any new tutorial a study needs. A few omniD tests use verbatim snippets of the
C++ as frozen fixtures for the generic scanner; they test the mechanism, not
the feature.

What the catalogue holds of the insulated-wall work, and what it does not:

- **Catalogued:** `sealedHeartBoundary` (`Switch`) and `sealedWallTrace`
  (`zeroGradient` or `conormal`), required for the monodomain, bidomain and
  eikonal solvers: a case without them is refused before running, with an
  explanation. `exposedFacesPatch` (read with `cellZone`) and the eikonal
  verifier's `verificationModel.productionPatches`, both optional.
- **Not an `electroProperties` key:** `offsetField` is an entry of a
  `conormalZeroFlux` patch in a field file (`0/Vm`); the solver names it and
  writes it back. omniD catalogues no field file, so `catalog --uncatalogued`
  still lists it.
- **Tutorial cases with no omniD record:** `insulatedWall` for bidomain,
  eikonalECG and monodomainPseudoECG. They run through `--case`, or get a
  record. On the heart-in-bath branch, also bathBidomain's `insulatedWall` and
  `idealizedHeart/electroHeartBath`, and its keys `bathHeartPhiETrace` and
  `sigmaB`, which stay `uncatalogued` until that branch lands.

**Order when the owner is ready:**
1. Fast-forward native `main` to `omnid/tutorials-are-pointers`, or merge the
   reverse; it contains `main`.
2. When `feat/heart-in-bath` lands on `main`, merge it into our branch (one
   README conflict), or take `omnid/heart-in-bath`.
3. Run `omnidriver catalog --uncatalogued`, and describe the new keys in the
   catalogue.
4. Add records for the new cases where a study needs them.

**The installed `cardiacFoam`** (in `~/OpenFOAM/simaocastro-v2412`) was built
from the insulated-wall work, which is native `main` now. Against tutorials
without the two required keys it fails, which omnidriver reports before
running when it is given that source. Preflight warns `stale_build` when a
binary is older than its sources, and a run that fails on a key the scanned
source never reads says the binary was built from other source.

## 4. cardiacCore: exactly where it stands

`origin/main` is at `4d2b22a`. The owner's checkout (`~/cardiacCoreStandalone`)
is still on `f0fc231`, 17 commits behind. It has no tracked changes, so
`git pull --ff-only` is clean.

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
2. **Left for the electrophysiology tests**, each needing a decision the code
   cannot make alone:
   - *Binary versus source.* `stale_build` compares file times, which a
     `git archive` tree sets to the commit time for every file. Source digests
     recorded in the build manifest (`cardiacFoam.build.json`) and compared by
     digest would replace it, and a manifest that names another source tree
     should be said in preflight. A key only the binary reads is set today in a
     `--case` copy.
   - *Records against the native `Allrun`.* A record restates the native
     script's commands, and no check compares the two: either a check of each
     record's command sequence against its `Allrun`, or steps derived from it.
   - *Units across solvers.* A `native_unit` on axes, with sweeps in SI. It
     includes the electrode seam: cardiacFOAM reads electrode positions in
     metres, and cardiacCore's `applications/scripts/electrode_positions.py`
     takes a caller-declared unit and converts nothing, so a millimetre case
     gives a pseudo-ECG a factor of 1000 off.
   - *Bounds and menus the catalogue lacks.* cardiacCore's range bounds depend on
     the mesh; openCARP's ionic-model menu could come from `bench --list-imps`.
   - *`compare`.* `--scaffold` to write a request, non-sweep runs, and artifacts
     chosen by format or path (the Niederer campaign).
   - *`--case` on a native cardiacCore case* drops its committed
     `constant/polyMesh` (an authored mesh versus a generated one).
   - *`build`.* Its grammar and the status of its subcommands.
     `_find_installed_provider` imports every installed plugin to find one `requires:` id, a packaging
     decision.
   - *The scanner* does not read a `found()`-guarded one-of, as in
     `stimulusIO.C`.
   - *Study values on a single `plan`/`run`.* Today even one change needs a sweep
     spec. Every staged `humanSlab` copies its 333 MB anatomy bundle.
   - *After `step --apply` changes a swept key,* the case record still shows the
     sweep's axis values.
3. **Uncatalogued cardiacFOAM keys:** 12 for electromechanics (they wait for
   it), two `couplingSignal` literals, `offsetField` (a field-file key that no
   catalogued document holds) and `torsoSurface`, read only by
   `ecgModelIO::loadSurface`, which nothing calls yet: the owner wires it with
   the bath-heart case (on a branch, landing soon), and it is catalogued once
   it has a place in `electroProperties`. The Purkinje graph file is
   catalogued as the `purkinjeGraph` document, and a case's graph is judged
   before it runs (`docs/solver-learning/cardiacfoam-conduction-graph.md`).
   `purkinjeConductivity` is S/m with a dimensionless per-edge conductance, and
   `rPvj` and `pvjResistances` are Ω. The owner still has to settle the
   questions that document lists under "Needs owner confirmation", among them
   whether the native code should check the length of `pvjResistances` and the
   range of `rootStimulus.node`;

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
