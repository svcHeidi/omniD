# omnidriver: where it stands

The present and what is next. History lives in `plans/` and `specs/`; the
owner's decisions sit with the work they settle.

## 1. Clean state

| repository | remote | notes |
|---|---|---|
| omniD (`svcHeidi/omniD`) | `main` = `origin/main` | The only long-lived branch. The follow-up to cardiacFOAM #59, cardiacCore's new layout and the audit fixes (§2a) are on `audit/2026-10-26`, which lands on `main` next. Local-only and ignored: `.venv`, caches, `.claude/`, `.superpowers/` (agent reports) |
| cardiacFOAM (`solids4foam/cardiacFoam`) | `main` | PR #59 merged on 2026-10-25. v0.1 is not tagged yet; omniD relates to cardiacFOAM by version and PR, never by commit |
| cardiacCore (`svcHeidi/cardiacCore`) | `main` | Carries the repository layout omniD follows (`applications/utilities/`, `applications/scripts/`, `tutorials/idealizedHeart/`) and PR #2 (`generatePurkinjeTree` as named stages). The owner's checkout matches `origin/main` |

Pass 2 (`plans/2026-10-01-pass2-convergence.md`) is complete.

## 2. What omnidriver is now

- **Records are the only entry kind.** A record points at a native case: its
  steps, routes and axes. `--case <dir>` runs any folder as a one-step record.
  Studies are JSON in the native tree.
- **A solver repository declares itself** in `omnidriver.toml`: its plugin,
  tutorials, C++ source and scripts. omnidriver reads it from `--repo`, or
  from the repository of a supplied cases root. It never searches for one, and
  a cases root or a scratch root has no default.
- **Four solvers of three shapes.** cardiacFOAM and cardiacCore (OpenFOAM,
  finite volume, sharing the OpenFOAM layer), openCARP (a binary with `.par`
  files, finite elements) and TorchCor (a PyTorch API with no input file, a
  runner in its own venv, no MPI). cardiacFOAM, openCARP and TorchCor run the
  Niederer benchmark through the same commands.
- **The environment and the machine are data.** `omnidriver env` renders each
  solver's shell from its manifest and reports its MPI launcher, a 2-rank
  probe and the `host`. A plan loads its environment once
  (`--environment-source`) for every member; a parallel run uses the declared
  launcher and is refused at dispatch when the allocation differs
  (`allocation_mismatch`); `sweep-plan` writes each case's run document, so a
  sweep can be one job per case.
- **The C++ is scanned once per source state**, cached under the scratch root
  by a digest of the source. The catalogues are the source of truth for
  descriptions, units, rules and menus; when the C++ changes, nothing fails:

  | change | report |
  |---|---|
  | a key, or an enum value the C++ compares against, that the catalogue lacks | `uncatalogued` note |
  | a catalogued key the C++ no longer reads | `unread` note |
  | a catalogue claim the C++ contradicts, a stated default included | `disagreement` warning |

  `omnidriver catalog --uncatalogued` and `--unread` report the same for each
  utility manifest against its C++ command line, under `utility_manifests`.
- **Before a run**, a staged case passes the catalogue's relations, enum menus
  and numeric bounds, the OpenFOAM layer's `controlDict` and `fvSchemes`
  catalogue, the C++'s required keys and the plugin's cross-field rules
  (`omnidriver.openfoam.case_rules`). A break refuses the plan, naming the key
  and the rule. A plan that is not `ok` carries a code (`plan_failed`,
  `plan_blocked`).
- **A run is stateful through its run document.** `--entry` and `--case`
  always restage; `plan`, then `run`/`step --run-document`, resumes. `--fresh`
  starts a run document or a sweep over. `step --apply` edits the staged case,
  rolls the edit back when the rules refuse it, and runs the step.
- **Every command refuses a bad call in one JSON shape**
  (`{"status": "failed", "code": ..., "error": ...}`, exit 1), `code` from
  `core/refusal.py` `CODES`.
- **The plugin contract is one table** of optional members
  (`provider_stack.MEMBERS`, called through `stack.call`), at API version 3.
- **Commands:** `describe` (records, scripts, utility manifests; with
  `--entry`, keys, axes, readers, the conformance quantity and guidance),
  `catalog`, `env`, `scan`, `build-record`, `check` (C1–C14, reporting and
  never gating, each record listing what it `verified`), `plan`, `step`,
  `run`, `sweep-plan`, `sweep-run`, `compare`, and `omnidriver build` apart
  from the record path.
- **`omnidriver-verify`** holds manufactured problems as data and checks a
  solver's results against them: residuals, a generated cell model, error
  norms keyed by discretisation (finite volume or finite element) and
  convergence orders.
- **`omnidriver-agents` measures agents from outside.** It runs one task under
  several agent CLIs, with and without omniD, and writes a task record per
  trial. It imports nothing from omniD.
- **No pytest test runs a solver** or depends on a native tree's current
  content.

## 2a. The audit of 2026-10-26

Every section of omniD was audited against the owner's rules, and the fixes
the rules already settle are on `audit/2026-10-26`:

- **Environment and machine:** the declared launcher reaches the run; the
  allocation is rechecked at dispatch; `--environment-source` is loaded once
  and accepted by sweeps; sweep cases carry run documents; `env` reports the
  host; `check --regression` stages a record's inputs.
- **One reality for the OpenFOAM family:** the OpenFOAM layer owns
  `controlDict`, `fvSchemes`, the polyMesh list, the dynamic-key matcher, the
  manifest loader, what a case loads at run time and the dictionary reader;
  it names no cardiac vocabulary (`scripts/check-openfoam-shape.py`).
  cardiacFOAM's backend contract and the runtime-config file are deleted;
  `get_solver_builds` is the one build record.
- **Shared mechanisms in core:** one clone-and-patch helper, one
  `program_not_on_path` preflight, `QuantityTarget`'s parallel fields
  optional for a serial-only record, a format with no reader listed as
  `reader: null`.
- **Data an agent can query:** each utility manifest in `describe`, three
  new cardiacFOAM manifests, the utility-manifest drift scan, the openCARP
  catalogue regenerated against v18.1 with `menu_labels`.
- **Verifier and harness:** the `cell-model` and `norms` verbs; a missing
  `symbolic` extra fails the drift gates; the harness counts only coded
  refusals and records the omniD binary that ran.
- **Clean:** history, hashes and dead code removed with their tests.

## 3. cardiacFOAM: exactly where it stands

PR #59 (`feat/mono-bi-eikonal-verification`: monodomain, bidomain and eikonal
verification, the sealed-wall gradient, the bounded eikonal, the sealed-shell
manufactured solutions) merged into `main` on 2026-10-25, carrying #53's PVJ
fixes. v0.1 is released from `main` once tagged.

| branch or PR | state |
|---|---|
| PR #53 (`omnid/tutorials-are-pointers`) | merged with #59 |
| PR #57 (`feat/heart-in-bath`) | closed |
| `feat/bath-transmission-mms` | the bath work; rebase onto `main` |
| `chore/singlecell-sweep-drop-output-dir-template` | the singleCell ionic-model sweep drops its `output_dir_name` dependent; once on `main`, omniD's `output_dir_name_template` derivation goes, having no other user |

**Provisional work.** The bath is only on a feature branch: omniD adds no
catalogue entry and no record for it, and scanning that branch shows its keys
as `uncatalogued` notes. When it lands, the change is catalogue entries and a
record for any tutorial a study needs.

What the catalogue holds of the sealed wall, as #59 has it:

- **Catalogued:** `sealedHeartBoundary` (`Switch`), required for the
  monodomain, bidomain and eikonal solvers; the wall-cell gradient scheme
  `sealedWallLeastSquares`, named per field in `fvSchemes` `gradSchemes`, on
  the menu when the solver source is supplied; `bathHeartPhiETrace`, the
  `conormalHarmonic` heart/bath interface, the three spherical-shell verifiers
  with their keys, and `purkinjeFibreRadius` (metres, required when a coupling
  is bidirectional).
- **Tutorial cases with no omniD record:** the three `sphericalShell` cases.
  `--case` does not plan them either: foamlib cannot decode the `#ifeq` block
  of their `constant/electroProperties` (eikonalECG, pseudo-ECG) nor the
  `#eval` lines of the bidomain shell's `system/blockMeshDict`.

**Order when the owner is ready:**
1. Tag cardiacFOAM v0.1.
2. Land `audit/2026-10-26` on omniD `main`; the verifier's interim #59 pin
   (§5 4a) becomes the v0.1 tag.
3. Rebase `feat/bath-transmission-mms` onto `main`.
4. Run `omnidriver catalog --uncatalogued` and describe the new keys.
5. Add records for the new cases where a study needs them.

**The installed `cardiacFoam`** (in `~/OpenFOAM/simaocastro-v2412`) was built
from the insulated-wall work. A plan compares the source each build was
recorded from with the supplied repository by digest (`stale_build`), and a
run that fails on a key the scanned source never reads says the binary was
built from other source.

## 4. cardiacCore: exactly where it stands

- **Records:** three, `idealizedHeart`, `idealizedHeartEndocardial` and
  `idealizedHeartPigTransmural`, on the `idealizedHeart` variants `humanSlab`,
  `humanEndocardial` and `pigMorphometricTransmural`, each reading the
  variants' shared mesh (Git LFS) as a native input. The
  coordinate-convention and Purkinje-tree keys the C++ reads without a default
  are catalogued as required.
- **The owner's fibre-only conductivity** (`setCardiacConductivity`) is on
  `main`: with a `sheetField` the output is unchanged; without one it writes
  `dt·I + (df − dt)·f⊗f`, checked at every cell of the idealized heart
  (`tutorials/idealizedHeart/humanSlab/regression/fibreOnlyConductivityTest.sh`).
- **Results are not in the repository.** cardiacCore holds the methods; the
  validation results on local anatomies are in the owner's git-ignored
  `local/`, beside the git-ignored `cases/` and
  `tutorials/idealizedBivEllipsoid/`.
- **Purkinje tools, current and legacy:**

  | tool | status | basis |
  |---|---|---|
  | `applications/scripts/place_purkinje_seeds.py` | current | used by the septal-midline seed results |
  | `applications/scripts/check_purkinje_activation.py` | current | the owner's original tool, used by the same results |
  | `applications/scripts/legacy/purkinje_coverage.py` | legacy | the seed-deduction coverage check, superseded and unconfirmed by the owner. Keep it unchanged and separate |

- **Pending native changes omniD follows once they reach `main`:**
  - `feat/rv-septal-faces-always`: `generatePurkinjeTree` writes
    `RVSeptalEndoFaces` in every case, and `place_purkinje_seeds.py` puts the
    RV seed on it. omniD's manifest then declares the face set unconditionally;
  - `feat/morphometry-aha-z`: `setPurkinjeMorphometry` zones on `aha_z`, with
    per-ventricle class weights in its dictionary and named segments. omniD's
    catalogue follows the new keys from `catalog --uncatalogued`.
- **AHA septum, the owner's decision.** Under `cobiveco`, `setCardiacAnatomy`
  assigns LV and RV from `tv`, which splits the septum at mid-wall, so the
  septal AHA segments hold only its LV half. Under `uvc` the septum is LV
  whole. Whether the two conventions should agree, and which way, is open.
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
   - *Units across solvers.* Each axis states the unit of its value in its own
     solver's unit; whether sweeps should be stated in SI across solvers is
     open. It includes the electrode seam: cardiacFOAM reads electrode
     positions in metres, and cardiacCore's
     `applications/scripts/electrode_positions.py` takes a caller-declared unit
     and converts nothing, so a millimetre case gives a pseudo-ECG a factor of
     1000 off.
   - *Bounds and menus the catalogue lacks.* cardiacCore's range bounds depend
     on the mesh; openCARP's ionic-model menu could come from
     `bench --list-imps`.
   - *`compare`.* `--scaffold` to write a request, non-sweep runs, and
     artifacts chosen by format or path.
   - *`build`.* Its grammar and the status of its subcommands.
     `_find_installed_provider` imports every installed plugin to find one
     `requires:` id, a packaging decision.
   - *The scanner* does not read a `found()`-guarded one-of, as in
     `stimulusIO.C`.
   - *fvSchemes interpolation tables* are one menu: OpenFOAM's Mesh and
     MeshFlux tables are merged, so `Gauss upwind` in gradSchemes (upwind needs
     a flux) passes, and `multivariateSelection` gets a false note.
   - *Study values on a single `plan`/`run`.* Today even one change needs a
     sweep spec.
   - *After `step --apply` changes a swept key,* the case record still shows
     the sweep's axis values.
2a. **Where a record run is not the native default run.** The records follow
   #59's Allruns: N, the time step, `writeInterval` and the 1D-3D graph are
   derived as `Allrun -N`/`-endTime` derive them. Measured byte-identical to
   the native run: pseudo-ECG 3D, bidomain 3D and bathBidomain 3D at N = 10,
   and monodomain1D3D at N = 10. They differ here:
   - eikonalECG 3D reports all 161 electrodes unless a study names the
     `electrodes five` axis, where the Allrun's default `-electrodes five`
     keeps 5 (the activation time is identical); `-errorField` is only the
     `tet-errorLocalisation` route, while the Allrun also takes it on hex;
   - gmsh's `seed` (bath and eikonalECG `-seed`) is no axis; a tet study at
     1D or 2D, or naming `numberCells`, is not refused, though the Allrun
     refuses `-mesh tet` below 3D;
   - the four pseudo-ECG studies restate the conductivity, the verifier and
     `anisotropic` as keys where the `field` axis says it in one word; moving
     them to the axis is a native edit;
   - the `sphericalShell` cases (§3), the electromechanical cases
     (`monodomainTotalLagrangianEM`, `springSupportedSlab`) and the idealized
     heart have no record. EM needs per-region documents: `solve_step` reads
     `constant/electroProperties`.
3. **Uncatalogued cardiacFOAM keys:** 12 for electromechanics (parked with
   it) and `offsetField` (a field-file key that no catalogued document holds).
   `torsoSurface`, read by `ecgModelIO::loadSurface`, is catalogued at
   `ecgDomains.<name>.torsoSurface`; the owner wires the call with the
   bath-heart case and confirms the placement. The Purkinje graph file is the
   `purkinjeGraph` document, judged before a case runs
   (`docs/solver-learning/cardiacfoam-conduction-graph.md`).
   `purkinjeConductivity` is S/m with a dimensionless per-edge conductance,
   and `rPvj` and `pvjResistances` are Ω. The owner still has to settle the
   questions that document lists under "Needs owner confirmation", among them
   whether the native code should check the length of `pvjResistances` and
   the range of `rootStimulus.node`.
4. **1D-3D PVJ coupling, fixed on `main` by #53** (the measurements, before
   and after, are in `docs/solver-learning/cardiacfoam-pvj-coupling.md`):
   - a conservative bidirectional junction: the network node loses the
     junction current from the volume `pi rho^2 L` (`purkinjeFibreRadius`)
     and the tissue receives the current the network solved, whatever
     `pvjCouplingScheme`; charge balances every step, and retrograde
     activation of the network occurs;
   - `pvjCouplingScheme implicit` on the tissue's diagonal for both tissue
     algorithms (unidirectional), and `eikonalMonodomainPvjCoupler` reading it;
   - restart of the network's ionic state, the coupler's last observation, the
     restitution network's pending events and the time series.

   omniD refuses an `rPvj` below the stability bound only where the tissue
   receives the term explicitly: a unidirectional `reactionDiffusionPvjCoupler`
   or an `eikonalMonodomainPvjCoupler`, with the explicit scheme (or none);
   junctions that share cells are judged together, once the mesh exists. Open:
   - a parallel restart of a Purkinje network fails on rank 1;
   - `pvjRadius` as a physical size of the junction rather than a numerical
     sphere;
   - the half-open stimulus window;
   - an iterated bidirectional coupling (both sides implicit, the same
     current), deferred by the owner: the design and its cost are in
     `docs/superpowers/reports/pvj-outer-loop-assessment.md`;
   - on the bath-bidomain branch only: its reaction/diffusion split skips the
     SBDF2 `VmRate` and `Iion` refresh that `advance()` does.
4a. **Verifier findings, owner's calls** (`cardiacfoam.md` AB, `opencarp.md`
   N):
   - whether to report openCARP v18.1's Line-element defect upstream
     (quadrature on [-1, 1] against shape functions on [0, 1]);
   - the verifier's two problem files and their drift fixtures pin a #59
     commit, interim provenance until the v0.1 tag replaces it;
   - cardiacFOAM with `gradSchemes Gauss linear` does not converge on gmsh
     tets (FDA and rotated problems alike); the tutorial's base case uses
     `leastSquares` and converges at second order. On hex, Gauss linear
     converges. Whether a tet case should refuse or note `Gauss linear` is
     open;
   - openCARP's generated RK4 blocks read an uninitialised `t`
     (`GlobalData_t t = t + dt/2;`), harmless unless a rate names `t`; with N
     and O's defects, whether to report them upstream.
5. **The Niederer campaign on a cluster** (`benchmarks/niederer2011/campaign/`),
   once the owner decides its shape (§6, item 1). Use `check --checks C13` for
   N-rank evidence, and rescan first if the solver changed.
6. **The Niederer comparison across solvers and meshes** (owner, 2026-10-09).
   The goal is an agent that reasons with each solver's mapping and tries the
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
   - Oblique (45 degrees): cardiacFOAM has no study. #59 removed the native
     `obliqueWall` study pending its redesign (decision D1); its arms under
     `sealedHeartBoundary` and `sealedWallLeastSquares` are the owner's to
     decide. The measurements in `cardiacfoam.md` AA were made on the removed
     walls.
   - Open: dx 0.1 on all three; TorchCor on a GPU (no CUDA here); TorchCor's
     F2-F4, F6-F8 (`torchcor.md`; F6, whether `et = 0.2` upstream is a typo,
     is for its author).
7. **The agent harness's first experiment** (`packages/omnidriver-agents`,
   plan `plans/2026-10-09-agent-harness.md` Task 9). It needs a one-time login
   in a clean home (`HOME=<agent home> claude`, then `/login`), then the
   isolation probe, then the openCARP N-version task: Opus, Sonnet and Haiku,
   `omnid` against `bare`, three trials each. The runner role is the query
   sequence it measures.
8. **What an agent should know as data: measure first** (owner, 2026-10-09).
   `ARCHITECTURE.md` maps what the agent knows as data, as prose and not at
   all; `docs/solver-learning/cross-solver-variables.md` maps cardiacFOAM and
   openCARP variables, each verified by perturbation runs. Before adding
   fields, measure with the agent harness, and add data only where agents
   fail. Candidate fields, held as notes until a measured failure justifies
   one:
   - a concept id per catalogue entry, from a shared vocabulary beside the
     benchmarks;
   - `case_value` on each key in `describe` (the case's current value);
   - `normalised_by` on stimulus strength (cardiacFOAM per tissue volume,
     openCARP per membrane area, so the conversion carries chi);
   - `formation` on conductivity (harmonic mean per direction);
   - missing units: cardiacFOAM `activationThreshold`, `stimulusStartTime`,
     `stimulusLocationMin/Max`; openCARP `lats[].threshold`;
   - an openCARP ionic-model catalogue from `bench --list-imps`/`--imp-info`.
   Wrong prose to correct in the catalogue: cardiacFOAM's `TNNP` description
   says 2006 and 21 states beside a 17-state TT2004 state list, and the note
   on dimensioned values says "a full literal string" where `sweep-plan`
   wants `{"value", "dimensions"}`.
   Native, for the owner: before the stimulus fires, cardiacFOAM's PIMPLE
   loop runs all 1000 iterations every step. The Vm residual oscillates near
   1.16e-3 and never reaches 1e-6. A run with the stimulus at 5 ms took 786 s
   instead of 42 s; the results were unaffected.
9. **Later:**
   - one run using cardiacCore and cardiacFOAM steps
     (`specs/2026-09-18-cross-adapter-workflow-design.md`);
   - region-aware key validation;
   - the licence. There is no `LICENSE`, and `CITATION.cff` states none;
   - held as notes:
     - a study's dimensioned `chi` (`{"dimensions": ..., "value": ...}`) is
       refused as "must be a number", though the C++ reads a
       `dimensionedScalar` and the native file writes one;
     - the `configurationChecks` variant `monodomainVerificationNone` is
       refused when checked without the C++ mapping
       (`verificationModel.type none`);
     - `tetNumberCells`' description says "unit cube", but bathBidomain's mesh
       is three unit boxes;
     - refusal sites in `tutorial_records.py` and `record_execution.py` that
       name no code still report `unclassified`; name a code for each as an
       agent meets it;
     - openCARP's conformance offset unit resolves only with `--benchmarks`;
       `describe` reports `null` without it.

## 6. For the owner, from the audit

1. **The Niederer campaign** (`benchmarks/niederer2011/campaign/`: a runbook,
   a Slurm script, a summariser and the pre-registered requests) breaks "a
   study needs no machinery", but was prepared for the cluster run.
   Recommended: keep `niederer2011.json`, the openCARP study JSON and a short
   per-solver mapping README, and move the requests to the paper repository
   as evidence.
2. **Native post-processing helpers** (`postprocessing.style`,
   `plotting_common`, `table_writer`) are used only by cardiacFOAM's native
   scripts. Recommended: move them into cardiacFOAM's `applications/scripts`,
   and have the Niederer points script use an omniD reader.
3. **`omnidriver build`** writes solver settings no native case states, and
   only cardiacFOAM has a builder. Recommended: build from the closest native
   case and patch it from the catalogue, or retire it until authoring is a
   goal.
4. **Record constants copied from Allruns** (the time-step formula, N, the
   templates, the pseudo-ECG tensors, the s1s2 offsets) are compared only with
   fixture copies. Recommended: an `omnidriver check` probe that reads the
   staged Allrun line each constant mirrors.
5. **Ideas that add a command or a concept:** `omnidriver read` (one run's
   quantities); a per-host connection file and `srun`; a GPU allocation for
   TorchCor; an `electroHeart` record; a reader's `defined_by`; verification
   status as data; model parity (the verifier's level 1).
6. **Native, not edited by omniD:** #59's `dryrun` authorship; the
   eikonal-domain warning of unconstrained regions; eight silent selectors;
   cardiacFOAM's `source = "."`; the eikonalECG `electrodes` default;
   cardiacCore's conventions (RunFunctions, `lib.sh`, PR CI); the electroHeart
   Purkinje provenance; the `solids4foam` fork branch; deleting the native
   utility-manifest copies now that omniD's have landed; `1DgraphToFoam` and
   `newVtkUnstructuredToFoam`, which cardiacCore renames
   (`ccore1DgraphToFoam`, `ccoreVtkUnstructuredToFoam`).
7. **The guidance the OpenFOAM layer serves.** The layer implements no
   `get_agent_guidance`, so the paragraph on its `controlDict` and `fvSchemes`
   catalogue is repeated, word for word, in both cardiac `guidance.md` files.
   Implementing the member in the layer would state it once.
