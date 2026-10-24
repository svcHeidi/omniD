# omnidriver: where it stands

Read this first, after `CLAUDE.md`. It describes the state as of 2026-10-24.
History lives in `plans/` and `specs/`; this file is only the present and what
is next.

## 1. Clean state

| repository | remote | notes |
|---|---|---|
| omniD (`svcHeidi/omniD`) | `main` = `origin/main` | The only long-lived branch; a commit cannot name its own hash, so `git log -1` is the head. Local-only and ignored: `.venv`, caches, `.claude/`, `.superpowers/` (agent reports), `omnidriver-runtime.yaml` (the owner's machine config) |
| cardiacFOAM (`solids4foam/cardiacFoam`) | cardiacFOAM `main`; PR #59 merges into it with a merge commit | omniD relates to cardiacFOAM by version, not by commit: v0.1, released after #59 merges. The owner's feature branches are theirs (§3) |
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
- **Three solvers of different shapes.** cardiacFOAM (OpenFOAM, finite
  volume), openCARP (a binary with `.par` files, finite elements) and TorchCor
  (a PyTorch API with no input file, a runner in its own venv, no MPI). All three
  run the Niederer benchmark through the same commands.
- **`omnidriver-agents` measures agents from outside.** It runs one task under
  several agent CLIs, with and without omniD, and writes a task record per
  trial: guidance hashes, tokens, cost, solver launches, refusals, and an
  oracle's verdict. It imports nothing from omniD.
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
  (`{"status": "failed", "code": ..., "error": ...}`, exit 1). `code` is one of
  the listed vocabulary (`core/refusal.py` `CODES`), and a refusal that knows
  which rules a value broke carries them as data (`refusals`).
- **The plugin contract is one table** of optional members
  (`provider_stack.MEMBERS`, called through `stack.call`), at API version 3.
  `AGENT_GUIDE.md` "Adding a New Solver" has a tested minimal plugin.
- **Commands:**
  - `describe` lists a stack's records (with `serial_only`), its repository
    `scripts` and the installed plugin ids; with `--entry`, the keys a record's
    own solver allows, each axis with its unit and bounds, the record's
    conformance quantity and the readers of its outputs (`record_surface`).
  - `omnidriver check` runs conformance C1–C14 against a real solver, plus the
    native regression with `--regression` and N-rank evidence in C13. It
    reports and never gates; a check that verifies nothing for a record (C13
    for a serial-only one) is `not_applicable`.
  - `omnidriver build` builds a case from the catalogue when there is no
    native case. It is kept apart from the record path.
  - `omnidriver compare` compares quantities read from two runs' artifacts.
- **No pytest test runs a solver** or depends on a native tree's current
  content. The solvers are under development, and their authors change them
  on purpose.

## 3. cardiacFOAM: exactly where it stands

PR #59 (`feat/mono-bi-eikonal-verification`: monodomain, bidomain and eikonal
verification, the sealed-wall gradient, the bounded eikonal, the sealed-shell
manufactured solutions) merges into cardiacFOAM `main` with a merge commit, and
cardiacFOAM v0.1 is released after it. omniD follows v0.1; nothing in omniD
relates to a cardiacFOAM commit except the interim pin noted in §5 4a.

| branch or PR | state |
|---|---|
| PR #53 (`omnid/tutorials-are-pointers`) | superseded by #59: its head is contained in #59, so the merge commit marks it merged |
| PR #57 (`feat/heart-in-bath`) | closed |
| `feat/bath-transmission-mms` | the bath work. A follow-up: rebase onto `main` after #59 |
| `omnid/heart-in-bath`, `omnid/insulated-wall` | superseded; no longer needed |

**Provisional work.** The bath is only on a feature branch, so it is
provisional, and omnidriver treats it that way:
- it adds no catalogue entry and no record for it;
- nothing on omniD `main` depends on it;
- scanning such a branch shows its keys only as `uncatalogued` notes.

When it lands on native `main`, omnidriver's change is small: catalogue entries
for its keys, and a record for any new tutorial a study needs. A few omniD
tests use verbatim snippets of the C++ as frozen fixtures for the generic
scanner; they test the mechanism, not the feature.

What the catalogue holds of the sealed wall, as cardiacFOAM PR #59
(`feat/mono-bi-eikonal-verification`) has it:

- **Catalogued:** `sealedHeartBoundary` (`Switch`), required for the
  monodomain, bidomain and eikonal solvers; a case without it is refused
  before running. #59 removed `sealedWallTrace` and the `conormalZeroFlux`
  wall, and omniD with them. The wall-cell gradient is the scheme
  `sealedWallLeastSquares`, named per field in `fvSchemes` `gradSchemes`; a
  plan judges `fvSchemes` against OpenFOAM's tables and the schemes the
  supplied solver source registers, so it is on the menu when that source
  is. Also `bathHeartPhiETrace` (`zeroGradient` or `global`), the
  `conormalHarmonic` heart/bath interface, and the three spherical-shell
  verifiers with their keys.
- **Tutorial cases with no omniD record:** the three `sphericalShell` cases
  (bidomain, eikonalECG, monodomainPseudoECG). `--case` does not run them
  either (open, §5 2a): `plan --strict --case` refuses the eikonalECG and
  pseudo-ECG shells (`case_rule`: foamlib cannot decode the `#ifeq` block at
  line 21 of `constant/electroProperties`) and stops the bidomain shell on the
  `#eval` lines of `system/blockMeshDict` (`configuration_unresolved`).

**Order when the owner is ready:**
1. Merge #59 into cardiacFOAM `main` (merge commit), then tag v0.1.
2. Land omniD's follow-up to #59 on omniD `main`.
3. Rebase `feat/bath-transmission-mms` onto `main` (follow-up).
4. Run `omnidriver catalog --uncatalogued`, and describe the new keys in the
   catalogue.
5. Add records for the new cases where a study needs them.

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
   the catalogues. omniD's goal is normal use of the solver, not the details
   of its manufactured cases. **Electromechanics is parked** until the owner
   moves to it; its keys and records wait with it.
2. **Left for the electrophysiology tests**, each needing a decision the code
   cannot make alone:
   - *A key only the binary reads* is set today in a `--case` copy.
   - *Records against the native `Allrun`.* A record restates the native
     script's commands, and no check compares the two: either a check of each
     record's command sequence against its `Allrun`, or steps derived from it.
   - *Units across solvers.* Each axis states the unit of its value
     (`record_surface.axes[].unit`), in its own solver's unit; whether sweeps
     should be stated in SI across solvers is open. It includes the electrode
     seam: cardiacFOAM reads electrode positions in
     metres, and cardiacCore's `applications/scripts/electrode_positions.py`
     takes a caller-declared unit and converts nothing, so a millimetre case
     gives a pseudo-ECG a factor of 1000 off.
   - *Bounds and menus the catalogue lacks.* cardiacCore's range bounds depend on
     the mesh; openCARP's ionic-model menu could come from `bench --list-imps`.
   - *`compare`.* `--scaffold` to write a request, non-sweep runs, and artifacts
     chosen by format or path (the Niederer campaign).
   - *`build`.* Its grammar and the status of its subcommands.
     `_find_installed_provider` imports every installed plugin to find one `requires:` id, a packaging
     decision.
   - *The scanner* does not read a `found()`-guarded one-of, as in
     `stimulusIO.C`.
   - *fvSchemes interpolation tables* are one menu: OpenFOAM's Mesh and MeshFlux tables are merged, so `Gauss upwind`
     in gradSchemes (upwind needs a flux) passes, and `multivariateSelection` gets a false note.
   - *Study values on a single `plan`/`run`.* Today even one change needs a sweep
     spec. Every staged `humanSlab` copies its 333 MB anatomy bundle.
   - *After `step --apply` changes a swept key,* the case record still shows the
     sweep's axis values.
2a. **Left from following cardiacFOAM PR #59.** The records follow #59's
   Allruns: N, the time step, `writeInterval` and the 1D-3D graph are derived
   as `Allrun -N`/`-endTime` derive them. Measured byte-identical to the
   native run: pseudo-ECG 3D, bidomain 3D and bathBidomain 3D at N = 10, and
   monodomain1D3D at N = 10. A record run is not the native default run in
   these places:
   - eikonalECG 3D reports all 161 electrodes unless a study names the
     `electrodes five` axis, where the Allrun's default `-electrodes five`
     keeps 5 (the activation time is identical); `-errorField` is only the
     `tet-errorLocalisation` route (`writeCellCentres`, and a study sets
     `writeErrorField`), while the Allrun also takes it on hex;
   - gmsh's `seed` (bath and eikonalECG `-seed`) is no axis; a tet study at
     1D or 2D, or naming `numberCells`, is not refused, though the Allrun
     refuses `-mesh tet` below 3D;
   - the four pseudo-ECG studies restate the conductivity, the verifier and
     `anisotropic` as keys where the `field` axis now says it in one word;
     moving them to the axis is a native edit;
   - the three `sphericalShell` cases have no record, and `--case` does not
     plan them (§3): foamlib reads neither the `#ifeq` block of their
     `electroProperties` nor the `#eval` lines of their `blockMeshDict`;
   - the electromechanical cases (`monodomainTotalLagrangianEM`,
     `springSupportedSlab`) and the idealized heart have no record; parked by
     the owner. EM needs per-region documents: `solve_step` reads
     `constant/electroProperties`.
3. **Uncatalogued cardiacFOAM keys:** 12 for electromechanics (parked with
   it) and `offsetField` (a field-file key that no catalogued document holds).
   `torsoSurface`, read by `ecgModelIO::loadSurface`, is catalogued at
   `ecgDomains.<name>.torsoSurface`, the block that function's dictionary
   argument matches; the owner wires the call with the bath-heart case (on a
   branch, landing soon) and confirms the placement. The Purkinje graph file is
   catalogued as the `purkinjeGraph` document, and a case's graph is judged
   before it runs (`docs/solver-learning/cardiacfoam-conduction-graph.md`).
   `purkinjeConductivity` is S/m with a dimensionless per-edge conductance, and
   `rPvj` and `pvjResistances` are Ω. The owner still has to settle the
   questions that document lists under "Needs owner confirmation", among them
   whether the native code should check the length of `pvjResistances` and the
   range of `rootStimulus.node`;

4. **1D-3D PVJ coupling: fixed on cardiacFOAM PR #53**, which reaches native
   `main` with #59 (the measurements, before and after, are in
   `docs/solver-learning/cardiacfoam-pvj-coupling.md`). It has:
   - a conservative bidirectional junction: the network node loses the junction
     current from the volume `pi rho^2 L` (`purkinjeFibreRadius`, read only on that branch)
     and the tissue receives the current the network solved, whatever `pvjCouplingScheme`; charge balances every step, and
     retrograde activation of the network occurs;
   - `pvjCouplingScheme implicit` on the tissue's diagonal for both tissue
     algorithms (unidirectional), and `eikonalMonodomainPvjCoupler` reading it;
   - restart of the network's ionic state, the coupler's last observation, the
     restitution network's pending events and the time series.

   omniD refuses an `rPvj` below the stability bound only where the tissue receives
   the term explicitly: a unidirectional `reactionDiffusionPvjCoupler` or an
   `eikonalMonodomainPvjCoupler`, with the explicit scheme (or none); junctions that
   share cells are judged together, once the mesh exists. Open after the fixes:
   - a parallel restart of a Purkinje network fails on rank 1, as before the fixes;
   - `pvjRadius` as a physical size of the junction rather than a numerical sphere;
   - the half-open stimulus window;
   - an iterated bidirectional coupling (both sides implicit, the same current),
     deferred by the owner: an outer loop around today's conservative pass, with
     the solves made repeatable (about 15 files); the design and its cost are in
     `docs/superpowers/reports/pvj-outer-loop-assessment.md`;
   - on the bath-bidomain branch only: its reaction/diffusion split skips the
     SBDF2 `VmRate` and `Iion` refresh that `advance()` does, so bath with SBDF2
     differs from the normal advance.
   - `purkinjeFibreRadius`: not catalogued, because native `main` reads no such key
     (the scan reports it `unread` there). An `omnid/*` branch, not on `main`, reads
     it with `lookupOrDefault` 2e-5 m; the catalogue entry follows if that reaches `main`.
4a. **Verifier findings, owner's calls** (2026-10-10, `cardiacfoam.md` AB,
   `opencarp.md` N):
   - whether to report openCARP v18.1's Line-element defect upstream (quadrature
     on [-1, 1] against shape functions on [0, 1]).
   - the gmsh tet templates (`cardiacfoam.md` AD6): native `main` before #59 has
     `lc = __LC__;`, which omniD's `gmsh -setnumber lc` cannot set. #59 moves each template
     to its case root with `DefineConstant[ lc ... ]`, which the records follow; settled when
     #59 merges. omniD's strict plan refuses a `-setnumber` name a template does not declare;
   - the verifier's two problem files (`fda_monodomain.toml`, `anisotropic_monodomain.toml`)
     and their drift fixtures pin a cardiacFOAM #59 commit. That pin is interim
     provenance until the v0.1 tag, which replaces it;
   - cardiacFOAM with `gradSchemes Gauss linear` does not converge on gmsh tets
     (FDA and rotated problems alike); the tutorial's base case uses `leastSquares`
     and converges at second order. On hex, Gauss linear converges. Whether a tet case should refuse or note `Gauss linear` is open;
   - openCARP's generated RK4 blocks read an uninitialised `t` (`GlobalData_t t = t + dt/2;`),
     harmless unless a rate names `t`; with N and O's defects, whether to report them upstream.
5. **The Niederer campaign on a cluster** (`benchmarks/niederer2011/campaign/`).
   Use `check --checks C13` for N-rank evidence, and rescan first if the
   solver changed.
6. **The Niederer comparison across solvers and meshes** (2026-10-09). The
   goal is an agent that reasons with each solver's mapping and tries the
   benchmark on each one. Frame and mesh alignment is the agent's own
   preprocessing, not an omniD feature. Evidence: `torchcor.md` G-I,
   `opencarp.md` M, `cardiacfoam.md` Y, Z and AA. The openCARP and TorchCor
   oblique studies are in `benchmarks/niederer2011/oblique/`.
   - At dx 0.5, the mesh decides the result. The finite-element solvers agree
     within 0.5 ms on a shared mesh, but move 17-26 ms between structured and
     unstructured tets. cardiacFOAM on any tet mesh agrees with itself within
     1.1 ms (P8 50 ms). Its 143 ms P8 belongs to the 0.5 mm hex mesh.
   - At dx 0.2, on native meshes, P8 is 38.0 (TorchCor), 40.6 (openCARP) and
     54.6 ms (cardiacFOAM). The first two are inside the paper's 37.8-48.7 ms
     at dx 0.1.
   - Oblique (45 degrees): cardiacFOAM has no study now. #59 removed the
     native `obliqueWall` study pending its redesign (decision D1), since every
     arm set a wall trace the sealed-wall design no longer reads; its arms
     under `sealedHeartBoundary` and `sealedWallLeastSquares` are the owner's
     to decide. The measurements in `cardiacfoam.md` AA were made on the
     removed walls.
   - Open: dx 0.1 on all three; TorchCor on a GPU (no CUDA here); TorchCor's
     F2-F4, F6-F8 (`torchcor.md`; F6, whether `et = 0.2` upstream is a typo, is
     for its author).
7. **The agent harness's first experiment** (`packages/omnidriver-agents`,
   plan `plans/2026-10-09-agent-harness.md` Task 9). It needs a one-time login
   in a clean home (`HOME=<agent home> claude`, then `/login`), then the
   isolation probe, then the openCARP N-version task: Opus, Sonnet and Haiku,
   `omnid` against `bare`, three trials each. A task such as "compare Niederer
   across the three solvers on one mesh" tests whether the mappings suffice.
8. **What an agent should know as data: measure first** (owner, 2026-10-09).
   `docs/solver-learning/cross-solver-variables.md` maps cardiacFOAM and
   openCARP variables, each verified by perturbation runs, and logs where omniD
   gave the agent only prose or nothing. Before adding fields, measure with the
   agent harness. Ask questions whose answers that document settles (for
   example, openCARP's equivalent of cardiacFOAM `chi 140000`; matching the
   stimulus), on today's omniD, and add data only where agents fail. Candidate
   fields, held as notes until a measured failure justifies one:
   - a concept id per catalogue entry, from a shared vocabulary beside the
     benchmarks;
   - `case_value` on each key in `describe` (the case's current value);
   - `normalised_by` on stimulus strength (cardiacFOAM per tissue volume,
     openCARP per membrane area, so the conversion carries chi);
   - `formation` on conductivity (harmonic mean per direction);
   - missing units: cardiacFOAM `activationThreshold`, `stimulusStartTime`,
     `stimulusLocationMin/Max`; openCARP `lats[].threshold`;
   - an openCARP ionic-model catalogue from `bench --list-imps`/`--imp-info`;
   - cardiacFOAM's `TNNP` catalogue description says 2006 and 21 states beside
     a 17-state TT2004 state list;
   - the catalogue note on dimensioned values says "a full literal string",
     but `sweep-plan` wants `{"value", "dimensions"}`.
   Native, for the owner: before the stimulus fires, cardiacFOAM's PIMPLE loop
   runs all 1000 iterations every step. The Vm residual oscillates near 1.16e-3
   and never reaches 1e-6. A run with the stimulus at 5 ms took 786 s instead
   of 42 s; the results were unaffected.
9. **Later:**
   - one run using cardiacCore and cardiacFOAM steps
     (`specs/2026-09-18-cross-adapter-workflow-design.md`);
   - more TOML records;
   - region-aware key validation;
   - the licence. There is no `LICENSE`, and `CLAUDE.md` says not to add one
     without asking.
   - cardiacFOAM's backend inspection (`cardiacFoam.build.json`: full or
     lightweight, the linked libraries) still refreshes itself by file time;
     whether it moves into the build record is open.
   - three defects that predate the knowledge-as-data branch (found probing it,
     2026-10-09), held as notes:
     - a study's dimensioned `chi` (`{"dimensions": ..., "value": ...}`) is
       refused as "must be a number", though the C++ reads a `dimensionedScalar`
       and the native file writes one;
     - the `configurationChecks` variant `monodomainVerificationNone` is refused
       when checked without the C++ mapping (`verificationModel.type none`);
     - `tetNumberCells`' description says "unit cube", but bathBidomain's mesh
       is three unit boxes.
     - 109 refusal sites in `tutorial_records.py` and `record_execution.py` still
       report `unclassified`; name a code for each as an agent meets it;
     - openCARP's conformance offset unit resolves only with `--benchmarks`;
       `describe` reports `null` without it.
