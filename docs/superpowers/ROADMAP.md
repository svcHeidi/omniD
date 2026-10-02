# omnidriver: where it stands, and the roadmap

Written 2026-09-28 against `main` at `9ec4e69`. This file replaces the
per-plan Status tables as the place to read what is done and what is left.
The plans stay as history. Every state below was checked against git and the
code on `main`, not taken from a plan's own table. Where a claim comes only
from a ledger or report under `.superpowers/sdd/`, it says so.

---

## Current plan (2026-10-01)

Pass 2, convergence: `plans/2026-10-01-pass2-convergence.md`, with the owner's
decisions A, B, G1, G4, G7, G13, G15 and G18. It supersedes items 5, 7, 8, 9,
12 and 13 below.

## 0. Checkpoint, 2026-09-28 (end of day), `main` at `dc021e0`

This section supersedes sections 1, 8, 9 and the first items of 10 where they
differ. The rest of the file is the 9ec4e69 review and still holds.

**Clean state.**

| repository | state |
|---|---|
| omniD (`svcHeidi/omniD`) | `main` = `origin/main` = `dc021e0`, nothing uncommitted, no other branch or worktree. Superseded local branches were deleted, and patch backups kept in the controller's scratchpad |
| cardiacFOAM (`solids4foam/cardiacFoam`) | `omnid/tutorials-are-pointers` = `origin`, `c184d702`: every record's native changes. `omnid/scripts` is local, a stopped WIP (see "Next", item 3) |
| cardiacCore (`svcHeidi/cardiacCore`) | `main` = `origin/main` = `f0fc231`: your fix branch merged, no dataset names, seeds documented. `omnid/records` is local at `6757536`, waiting on your review (see "Next", item 1) |

**Landed since the 9ec4e69 review:**

| what | commit |
|---|---|
| Compatibility cleanup: delete list applied, `omnidriver.postprocessing` kept, `DRIVERFOAM_*` → `OMNIDRIVER_*`, `legacy_*` → `absent_*`, single cell always meshes with `blockMesh` | omniD `01133f7`..`da0e8db` |
| Step S: records take supplied inputs (`--input NAME=PATH`) | omniD `28845ac`..`dc021e0` |
| Step S: four cardiacCore records (`humanSlab`, byte-identical to the old workflow; three idealized-heart variants), 48/48 conformance | same |
| Step S: cardiacCore's and core's factory code deleted, net −1,944 lines | same |
| cardiacCore `main`: fix branch merged, dataset names removed, `.gitignore` covers every local case and every wmake platform directory, seed docs point at `scripts/place_purkinje_seeds.py` | `1b7ebf1`, `9c0c77f`, `f0fc231` |
| Niederer rerun with exact-point sampling on both solvers: 18/18 cases complete | report in the controller's scratchpad, `niederer-campaign-2026-09-28-report.md` |

**Niederer, current numbers.**
- **Agreement.** At Δx 0.1 mm and Δt 0.005 ms, P8 is 40.07 ms for openCARP and 45.50 ms for cardiacFOAM. Both are inside the paper's 37.8–48.7 ms, but the two differ by more than the pre-registered 5 ms, so all 9 cross-solver requests fail.
- **Speed.** cardiacFOAM's solve step is 2.4–7.8× slower than openCARP's at N = 6. openCARP's own timing puts its time in the PDE solve (595 s) against 87 s in its ionic model. cardiacFOAM prints no breakdown. An estimate from `docs/solver-learning/cardiacfoam.md` T puts its ionic model at about 70% of the solve and about 15× openCARP's per node.

**Update, same evening (`main` at `28c6ece`).** Items 1–5 below are done:
- **1.** cardiacCore `main` is at `15c6dfe`, pushed. The seed script uses the C++ default and gives identical seeds on `bivCase`; the three idealized-heart cases and their regression tests are committed.
- **2.** The five installed utilities were rebuilt from `15c6dfe`. The regression tests pass with them, and nothing else in the install changed.
- **3.** The native post-processing scripts are ported (native `eb5897b3`, pushed), and `Niedererlines` samples with `cellPoint`.
- **4.** The C++ source root is supplied, never guessed. Strict plans scan it, `rtst_scanner` is in `omnidriver-openfoam`, and `omnidriver catalog` answers "entries of dictionary X".
- **5.** Each manifest declares its shell, `omnidriver env --plugin P` renders and checks it, and every step records its host.

Tests: all packages, core, wheel and static gates at 0 failed; native cardiacFOAM 197 passed, native openCARP 32 passed, native cardiacCore 49 passed.

Left over:
- item 6 (cardiacFOAM timing split), not a priority;
- `plan --strict` still searches the disk for OpenFOAM when no bashrc is supplied;
- two sources for the bashrc: `OPENFOAM_BASHRC` and the runtime config;
- the stale opt-in fixture `reference_experiments/niederer_tissue.json`: re-pin it or delete it;
- tests that skip on every machine;
- `campaign.sh` still builds its own shells.

**Next, in order (as written before the update):**
1. **Owner: review cardiacCore `omnid/records`,** then merge it to `main`. It holds:
   - the three idealized-heart cases, with the mesh in Git LFS;
   - their regression tests;
   - the `place_purkinje_seeds.py` change. The script now reads the coordinate convention and uses `RVEndoFaces` under cobiveco. Two risks: it defaults to `apicobasal` when `longitudinalField` is absent, and it skips the outflow-tract search on the idealized mesh.

   The omniD idealized-heart records run from `main` only once this is merged.
2. **Owner: the five cardiacCore binaries in `/Volumes/OpenFOAM-v2412`.** An agent overwrote them with builds from pre-merge `main`. Rebuild them from current `main`.
3. **Native post-processing scripts:** point them at `omnidriver.postprocessing` and the sweep layout. This is branch `omnid/scripts`. Only `singleCell/calc_apd.py` and `plot_bueno.py` are deleted; every other script stays.
4. **The truth layer made first-class:**
   - fix `source_roots`, so `plan --strict` actually scans the C++;
   - take `rtst_scanner` out of test-only use;
   - add one query for "entries of dictionary X for solver Y".
5. **Declare the environment and machine connections** (sections 4 and 10). Today they are `CLAUDE.md` prose and hand-typed variables.
6. **Measure cardiacFOAM's speed:** a timing split inside cardiacFOAM (ionic, PDE, I/O) to confirm where it is slower.
7. **Then,** from section 10:
   - the solver-descriptions steps: `niedererNVersion` to TOML, argument merging, `run.py` defaults;
   - SI values with native units per axis;
   - mesh checks for records;
   - conformance Task 15;
   - the electromechanics record, which is the owner's.

## 1. Summary

**Are most plans finished? Yes.** Of the 15 plans, 13 are done. The other two
each have one item left: conformance Task 15 (the OpenFOAM layer still names
core's own files) and the Niederer campaign rerun on a cluster. But the work
that remains is not in the plans. It comes from the owner's decisions of
27-28 September and from the gaps the compatibility audit found.

**What omnidriver is now.** The last four days (24-28 September, about 230 of
690 commits) were a redesign, not patches. A tutorial is now a *record*: a
pointer to a native case, with its steps, routes and axes. There are 11
records (10 cardiacFOAM, 1 openCARP). Every record passes one conformance
suite, C1-C12. Results come back as named quantities with units, and
`omnidriver compare` checks them against pre-registered requests. openCARP
shows that nothing in core is tied to OpenFOAM.

**The goal the design serves.** The tool should be "not simple but easy". An
agent reaches each solver deterministically through a few known places, and
keeps its effort for reasoning. On top come benchmarking, comparing solvers,
and improving one solver. What is missing is a clear connection to each
**solver**, **environment** and **machine**:

| connection | how clear today |
|---|---|
| solver | mostly declared and checked: plugins, records, catalogs, readers, C1-C12 |
| environment | partly declared. OpenFOAM is found by searching the disk; openCARP is taken from the ambient shell; the order of `source`, `DYLD_LIBRARY_PATH`, MPI `PATH` and `HYDRA_IFACE` lives only in `CLAUDE.md` prose |
| machine | mostly prose and one shell script. Core reads `SLURM_NTASKS` and nothing else about the machine; the run document does not record the host |

**The four largest gaps on `main`:**
1. The C++ key scanner never scans during `plan --strict`. Its root in
   `plugin.yaml` points at the retired layout (`/Users/simaocastro/src`).
   Two more walk-ups to that layout fail the same way.
2. Mesh checks never run for a record. Records are marked generic cases, and
   generic cases are exempt.
3. cardiacCore has no records. Its four factory workflows keep core's factory
   plumbing alive.
4. Environment and machine facts are prose and hand-typed variables.

**In flight:** `compat-delete` (another agent, now). **Stopped:** `cc-records`,
native `omnid/scripts`, native cardiacCore `omnid/records` (no commits).
**Unpushed:** omniD `main` (2 commits) and native `omnid/tutorials-are-pointers`
(58 commits ahead of GitHub's copy).

**Next, in order** (section 10): land `compat-delete`; supplied inputs, then
cardiacCore onto records, then delete the factory plumbing; the native script
ports; the truth layer made first-class; the environment and machine
connections declared; the solver-descriptions plan and SI; mesh checks; the
electromechanics record (owner); the Niederer rerun last.

**Worktrees:** drop five (`awesome-bose-223e51`, `vigilant-torvalds-f7721a`,
`focused-franklin-c49d74`, `relative-sweep-paths`, `festive-cray-9d30ca`);
`main` already has every change they hold. Keep `cc-records` and
`compat-delete`.

---

## 2. The design

**Core** (`omnidriver`) runs workflows and names no solver. It owns the plugin
contract, the provider stack, strict planning, the RunDocument (version 3
only), the single case-write channel (`commit_case_write`), provenance,
sweeps, the conformance suite and quantities. Two gates enforce the
boundary: `check-import-boundaries.py` (no cardiac imports) and
`check-core-shape.py` (no new OpenFOAM layout tokens). The shape gate's
recorded debt is one entry, in `core/runtime/generic_case.py`, so deleting
the factory path takes it to zero.

**Plugins** stack. A plugin declares `requires:` and `provides:`, and core
composes an ordered stack per capability. cardiacFOAM and cardiacCore each
require the OpenFOAM environment provider. openCARP stands alone.

**Tutorials are pointers.** The native case is the default. A record
(`TutorialRecord`) holds the native case path, its workflow steps (command,
`consumes`, `produces`, default arguments), its routes (for example hex or
tet) and its axes. An axis turns a study value into patches or command
arguments. Studies are JSON files in the native tree. Python holds only
derived values (blockMesh counts from `dx`, `lc = 1/N`) and each solver's
rules. Nothing in a record writes a case; `check-case-writes.py` enforces it.

**Parallel** is a request, not a record change: a `parallel` study key or
`--parallel [N]`. Each solver says how through one hook,
`get_parallel_steps`. OpenFOAM decomposes, runs `mpirun`, and reconstructs,
with N from the case's `decomposeParDict`. openCARP runs `mpirun -np N` with
N from `SLURM_NTASKS` or supplied, and first checks the launcher belongs to
its own MPI.

**Conformance C1-C12** is one packaged suite (`omnidriver.conformance`) that
every record must pass against its real solver:

| check | proves |
|---|---|
| C1 | the stack has exactly one root provider |
| C2 | `describe` proposes no change to an untouched native case |
| C3 | an unknown key is refused by name |
| C4 | a patch changes one key and leaves its sibling alone |
| C5 | a strict plan gives a launchable command |
| C6 | a real run produces every declared artifact |
| C7 | a two-case sweep completes, reconciles, and leaves the native tree unchanged |
| C8 | every file a step consumes is fingerprinted |
| C9 | a missing solver is named by preflight |
| C10 | an agent finds any record's axes, keys and guidance the same way (`record_surface`) |
| C11 | restaging a run case carries nothing the run wrote and drops nothing authored |
| C12 | every declared output format has a valid reader |

**Results as quantities.** A step's outputs name their format
(`ProducedPath`). Each solver's reader turns them into quantities that carry
a unit, a status, the sampled location and the sampling rule. `omnidriver
compare` checks a pre-registered request against a reference (for example
`benchmarks/niederer2011.json`) and writes its report once. Sampling is at
the exact point: openCARP interpolates inside the containing tetrahedron
(`f2cd0fd`), and cardiacFOAM requires `interpolationScheme cellPoint`
(`c0a48de`).

**One reality for the OpenFOAM family** (owner, 2026-09-28, `CLAUDE.md`).
cardiacFOAM and cardiacCore do every shared job the same way, through
`omnidriver-openfoam`: records, catalogs, validation, case reading and
writing, key scanning. openCARP may differ, but only inside its own package.
Nothing is kept for compatibility.

**The truth layer** is how omnidriver knows each solver's dictionaries and
keys (section 5.4). It is kept by owner decision and must become first-class.

**SI** (owner, D17). Studies, requests and reports state SI. Each axis knows
its solver's native unit and converts, using core's unit table. Not built yet.

**Supplied, never discovered.** A root with no ambient truth (a case root, a
scratch root, a native tree) is supplied, or refused by name. Only
scheduler facts such as `SLURM_NTASKS` are read from the environment.

---

## 3. The deterministic access surface today

These are the places an agent uses. "Deterministic" means the same inputs
give the same answer and the same files, and a missing input is refused by
name rather than guessed.

| place | what the agent gets | how deterministic | caveat, with evidence |
|---|---|---|---|
| `describe --plugin P --entry E` | JSON: the record surface (axes, 168 keys for `niederer2011`, 247 for `niedererNVersion`), guidance, catalogs | high; reads only | still returns factory-era fields (`registered_tutorials`, `special_tutorial_aliases`, `available_tutorials`). Without `--plugin`, the default refuses when two independent solver-tier plugins are installed, as they are with all five packages |
| `plan --strict` | a staged copy, a RunDocument v3, diagnostics | high for records; needs `--scratch-dir` | for cardiacFOAM, the dictionary-key scan is skipped with `plugin_cxx_source_unavailable` on every plan (openCARP and cardiacCore have no scanner); mesh checks are skipped for records (section 5.4) |
| `run`, `step`, `recover` | execution of the plan's DAG, provenance, recovery | high | `step --apply` takes the `document:key` patches a study takes, for every record of all three plugins, but only with `--run-document`: `--entry` re-stages the case, so it cannot reach a staged one; a patch that fails the replan after its commit stays in the case, and `recover` restores only an interrupted commit |
| `sweep-plan`, `sweep-run` | one staged case per study row, each through the record path | high for records | two other sweep paths remain: the from-scratch cardiacFOAM sweep (no `base.entry`) and the factory `base.entry` sweep |
| `compare` | a report checked against a pre-registered request | high; written once; relative paths resolve from the request's own directory | none known |
| records | pointers, steps, routes, axes | high; pure data, gated | cardiacCore has none |
| catalogs | cardiacFOAM hand-curated with C++ `source_refs`; openCARP generated from its binary | openCARP high (drift-gated); cardiacFOAM medium; cardiacCore low (one manual scan, no gate) | section 5.4 |
| guidance | `record_surface` guidance; `guidance.md` for cardiacFOAM, cardiacCore and openCARP; `AGENTS.md` and `agent-handbook/` | prose, by nature | the environment and machine steps an agent needs are in `CLAUDE.md`, not in any of these |

---

## 4. The three connections

### 4.1 Solver

| | cardiacFOAM | openCARP | cardiacCore |
|---|---|---|---|
| plugin | `CardiacFoamPlugin`, requires OpenFOAM env | `OpenCARPPlugin`, alone | `CardiacCorePlugin`, requires OpenFOAM env |
| records | 10 | 1 | 0 (4 factory workflows) |
| key catalog | hand-curated, `source_refs` to C++ | generated from `openCARP +Help` (266 parameters) | hand-curated, one manual scan |
| drift gate | `omnidriver catalog --uncatalogued/--unread` and every strict plan scan the supplied C++ | `omnidriver check` against the binary | same scan |
| result reader | activation probes (`cellPoint`) | LAT reader (interpolating) | none |
| conformance | `omnidriver check` over every record's declared study | `niedererNVersion` | `omnidriver check` |

Declared and checkable: plugins, records, readers, openCARP's catalog.
Prose or tribal: how cardiacFOAM's catalog was built (by reading C++), and
all of cardiacCore's catalog.

### 4.2 Environment

| solver | how it is found or supplied | what preflight checks | prose only |
|---|---|---|---|
| OpenFOAM (for cardiacFOAM, cardiacCore) | in order: `--environment-source`; `DRIVERFOAM_RUNTIME_CONFIG`'s `openfoam.bashrc` (cardiacFOAM only); `OPENFOAM_BASHRC`; `WM_PROJECT_DIR`; then a disk search of `/opt/openfoam*`, `/usr/local/openfoam*`, `/Volumes/OpenFOAM-v*` and `which foamVersion`, taking the reverse-sorted first (`openfoam_environment._discover_openfoam_bashrcs`) | `missing_openfoam_env`, `openfoam_env_not_sourced`, `openfoam_env_source_failed`, `partial_openfoam_env`, `missing_executable`, `missing_mpi` | which MPI `mpirun` belongs to (no check, unlike openCARP); `DYLD_LIBRARY_PATH` must be exported *after* sourcing, because macOS strips `DYLD_*` across `bash` |
| cardiacFOAM backend | `DRIVERFOAM_CARDIACFOAM_BACKEND`, `..._SOLIDS4FOAM_ROOT`, `..._BUILD_MANIFEST`, or the runtime YAML; `plugin.yaml` declares the `lightweight`/`full` options and their libraries | required and forbidden libraries | `configured_openfoam_bashrc` returns `None` when the configured file is missing, so a supplied path silently falls through to the disk search |
| openCARP | ambient `PATH` and `DYLD_LIBRARY_PATH`; nothing is sourced | `opencarp_command_not_found`, `opencarp_binary_unloadable`, the version against the catalog, `opencarp_mpi_launcher_mismatch` | the MPI `PATH` prefix (`/usr/local/lib/opencarp/lib/petsc/bin`) and `HYDRA_IFACE=lo0` on a host whose name does not resolve: code never mentions `HYDRA_IFACE` outside tests |
| cardiacCore | inherits OpenFOAM's; no hooks of its own | OpenFOAM's | where its utilities are built |
| stale build | `environment_preflight._discover_src_root` walks up for `src/` beside `tutorials/` | `stale_build` | never fires: that layout is retired, so it finds nothing |

Declared and checkable: openCARP's environment, OpenFOAM's missing pieces,
the cardiacFOAM backend. Prose: the order of operations for a native shell,
the two MPIs, `HYDRA_IFACE`. Discovered where the rule says supplied: the
OpenFOAM disk search. `compat-delete` renames `DRIVERFOAM_*` to
`OMNIDRIVER_*`, which fixes the names but not the shape.

### 4.3 Machine

| concern | declared in code | prose, script or missing |
|---|---|---|
| process count | `SCHEDULER_ALLOCATION_VARIABLES = ("SLURM_NTASKS",)` in `record_execution`; each solver's `get_parallel_steps`; OpenFOAM's N from `decomposeParDict`; a disagreeing count is refused | the campaign overrides `SLURM_NTASKS=$n` inside a 64-task allocation to run fewer ranks, which misstates the allocation (spec §3.1) |
| launcher | `mpirun` for both solvers; openCARP checks it is its own MPI's | OpenFOAM does not check; `srun` is not supported (spec §6 defers it until a cluster shows the need) |
| host identity | only the attempt lease records `hostname` | the run document does not; `campaign.sh` writes `runs/hosts/*.txt` itself |
| cluster layout | none | `benchmarks/niederer2011/campaign/README.md`: link `runs/` to cluster scratch; export `OPENFOAM_BASHRC`, `OPENCARP_MPI_BIN`, `CAMPAIGN_DYLD_LIBRARY_PATH` |

The machine connection is the least declared of the three.

---

## 5. What exists today

### 5.1 Packages

Measured at `9ec4e69`: raw lines of tracked files, blank lines and comments
included.

| package | source `.py` | other source (YAML, JSON, Markdown) | tests `.py` |
|---|---|---|---|
| `omnidriver` (core) | 29,177 (97 files) | 749 | 31,627 (158 files) |
| `omnidriver-openfoam` | 7,246 (25) | 67 | 8,894 (49) |
| `omnidriver-cardiacfoam` | 13,432 (57) | 1,807 | 20,320 (120) |
| `omnidriver-cardiaccore` | 4,626 (19) | 178 | 1,929 (16) |
| `omnidriver-opencarp` | 1,173 (11) | 2,921 (mostly the generated `opencarp_parameters.json`) | 1,250 (19) |
| **total** | **55,654** | 5,722 | **64,020** |

`scripts/` adds 2,359 lines of Python. Tracked Markdown is 48,954 lines in
94 files; the 15 plans alone are 30,439.

### 5.2 Records

| record | plugin | native case | landed |
|---|---|---|---|
| `restitutionCurves` | cardiacFOAM | `electrophysiologyProtocols/restitutionCurves_s1s2Protocol` | `46bd2f0` (pilot); conformance `a0ca350` |
| `manufacturedBidomain` | cardiacFOAM | `manufacturedSolutions/bidomain` | `c15d5c5` |
| `niederer2011` | cardiacFOAM | `NiedererEtAl2011verification` | `1811e2e` |
| `manufacturedEikonalECG` | cardiacFOAM | `manufacturedSolutions/eikonalECG` | `3e04030` |
| `manufacturedBathBidomain` | cardiacFOAM | `manufacturedSolutions/bathBidomain` | `cc5a955` |
| `singleCell` | cardiacFOAM | `electrophysiologyProtocols/singleCell` | `11dcb2f` |
| `manufacturedMonodomainPseudoECG` | cardiacFOAM | `manufacturedSolutions/monodomainPseudoECG` | `14c75ef` |
| `cable1DRestitution` | cardiacFOAM | `electrophysiologyProtocols/cableProtocol/monodomain1DCableCV` | `232af42` |
| `cable1DCVConvergence` | cardiacFOAM | same case | `232af42` |
| `manufacturedMonodomain1D3D` | cardiacFOAM | `manufacturedSolutions/monodomain1D3D` (also covers the Purkinje graph) | `b596cdd` |
| `niedererNVersion` | openCARP | `02_EP_tissue/03E_study_resolution` | `e4bc873` |

The factory tutorial package was deleted in `1c5bb57`. The native shapes were
not re-run for this review; their last results are in the reports.

### 5.3 Paths besides records

| path | what it is | who uses it |
|---|---|---|
| cardiacCore factory tutorials | 4 `TutorialSpec` workflows in `cardiaccore/workflows/preprocessing.py` (`cardiaccore-human-purkinje-slab`, `-human-purkinje-endocardial`, `-pig-morphometric-purkinje`, `-pig-transmural-purkinje`) | cardiacCore's only entries. They keep `TutorialSpec`, `generic_case`, `tutorial_contracts`, `specs/validation` and `--entry-kind registered_tutorial` alive (audit §6, O1-O12) |
| generic case-folder path | `--entry` given a case directory; `core/runtime/generic_case.py`, `cardiacfoam/generic_case.py`, `generic_case_mutation.py` | an agent pointing at any case. `generic_case_mutation.apply_case_mutation` still writes outside the channel |
| from-scratch sweep | `sweep-plan`/`sweep-run` with no `base.entry`: `cardiacfoam/sweep.py`, `dict_builder.build_case` | builds a case from the catalog alone. Possible defect: it passes `dry_run=True`, so a `singleCellSolver` case gets no mesh (audit K4, not run) |

### 5.4 The truth layer (audit §2)

| piece | reads | runs in production? |
|---|---|---|
| cardiacFOAM `case_builder` (build and parse `electroProperties`, `physicsProperties`; `omnidriver build`) | the catalogs | `omnidriver build` and the `check` ionic probe |
| `openfoam/case_builder`, `openfoam/literals` | caller's entries | `omnidriver build`; `literals` in the record path |
| `openfoam/dict_keys_scanner` (C++ dictionary reads) | C++ at the supplied `cxx_mapping.source_root` | every strict plan, cached by source digest; `omnidriver scan` and `catalog --uncatalogued` |
| `cardiacfoam/rtst_scanner` (runtime-selection tables) | C++, found by walking up (`monorepo.py`) | test-only, behind a silent `skip_without_monorepo` |
| `names_parser`, `ionic_catalog_verification` | C++ headers; the `listCellModelsVariables` binary | a script; tests behind skips |
| openCARP `catalog_generation` | the binary's `+Help` | a script and a `native_opencarp` drift gate |
| cardiacFOAM catalogs (`dict_entries_catalog` 1,641 lines, `ionic_model_catalog`, ...) | hand-curated from C++ | yes |
| cardiacCore `catalogs/inputs.py` (1,038 lines) | one manual scan of `cardiacCoreStandalone/src` | yes; nothing re-verifies it |

Two more facts from the audit:
- **Mesh checks never run for records.** `record_case_spec` sets
  `metadata["generic_case"] = True`, and `strict_planning._mesh_geometry_exempt`
  exempts generic cases. `openfoam/mesh_geometry.py` and
  `cardiacfoam/mesh_geometry.py` are reachable only from factory specs.
- **There is no "entries of dictionary X" query.** Today an agent runs
  `describe` and reads `record_surface.keys`.

---

## 6. The owner's binding decisions

| decision | where recorded | what it means for the work |
|---|---|---|
| one reality for cardiacFOAM and cardiacCore | `CLAUDE.md`, "One reality", `1f856df` | cardiacCore moves to records; scanning and catalogs are shared in `omnidriver-openfoam`, never two variants |
| no compatibility layers, no retired names | same | `compat-delete`; `DRIVERFOAM_*` becomes `OMNIDRIVER_*` with no alias |
| the dict builder and catalog tooling are kept and become first-class | compat audit, scope note; this brief | nothing in the truth layer is deleted; its test-only parts become real gates |
| SI is the normalisation; axes convert to each solver's unit; any key with a unit is sweepable in SI | spec D17, `2b09af0`, `f0d094d` | new `native_unit` on axes; a unit-aware direct-key path |
| TNNP 2004 and the −84 mV default accepted for Niederer | `docs/solver-learning/cardiacfoam.md`, `70378bd` | a single-cell initialisation comes later, natively |
| probes sample at the exact point | `f2cd0fd` (openCARP interpolates), `c0a48de` (cardiacFOAM `cellPoint`) | the campaign is rerun with these readers |
| electromechanics deleted from omniD; the owner rebuilds it as a record | step C, `1c5bb57` | needs `WorkflowStep.cwd` (spec §5) |
| a single cell always meshes with `blockMesh` | this brief; part of `compat-delete` | the from-scratch sweep's meshless single cell goes |
| Revision 2 restraint rules | `specs/2026-09-27-solver-descriptions-design.md` §0, §3; review `99f8b40` | every new abstraction must name the current problem that needs it and say why a small solver function is not enough; the dropped list in §3.2 stays dropped |

---

## 7. The plans

### 7.1 The redesign (24-27 September)

| plan | goal | state | evidence on `main` | left |
|---|---|---|---|---|
| `2026-09-25-tutorials-are-pointers-remaining` | every cardiacFOAM tutorial becomes a record; delete the factory | **done** | 10 records (5.2); factory deleted `1c5bb57`; step C through `0b615c8` | step S (supplied inputs for a record) is open and now blocks cardiacCore. TL-EM is the owner's. Its four Status tables are superseded by this file |
| `2026-09-25-solver-conformance-and-opencarp` | prove omniD drives a solver outside OpenFOAM | **done except Task 15** | suite `5efd986`; openCARP `e4bc873`; Task 14 `a0ca350`..`b9c46eb`; C11, C12 added by topics A and B | Task 15 ("O15"): `test_layer_ownership.py` does not exist, and `openfoam/case_runtime_conventions.py` still lists `run_document.json` and `workflow_state.json`. Still applies; small |
| `2026-09-26-core-generality` (topic A) | replace core's OpenFOAM-shaped concepts | **done** | `03b0727`..`9cf5485`, review fixes to `dc82def` | deferred findings: M2 (scanner schema in core) and M12 (silent-skip C++ tests) go to the truth layer; M11 (required members that are empty for openCARP) goes with the factory deletion; M3 (region-aware validation) is in spec §6 |
| `2026-09-26-results-as-quantities` (topic B) | results as named quantities; compare across solvers | **done** | Tasks 1-6 `26a8da6`..`5a0778e`; T7 `4300c81`; T8 `4860ea9`; campaign `82746b8`, `a9a96fd`; exact-point readers; 0.2 mm re-read `96927c5` | the campaign rerun on a cluster (owner, last) |

### 7.2 The specs

| spec | state | left |
|---|---|---|
| `2026-09-27-solver-descriptions` (Revision 2) and its review | spec only; not started | its steps 1-4 and D17 are roadmap items 10-11. Open decisions D2, D3, D11 |
| `2026-09-26` core generality, results as quantities; `2026-09-25` solver conformance; `2026-09-24` tutorials are pointers | implemented | step S, O15 |
| `2026-09-20` provider composition, and its spike | implemented by phases 0-1 | none |
| `2026-09-18` coverage as evidence (design, review, consolidation) | partly. Mechanism steps 1-2 landed: an owed check that cannot run blocks launch, and a stage that did not run earns no points (`ce97d23`, `10980fd`, `909a279`) | evidence fields on catalog entries, a catalog gate, and a cardiacCore scanner fold into the truth layer (item 7). Its programme steps 4-6 (cardiacCore workflow, then cardiacCore feeding cardiacFOAM) are items 3-5 and "later" |
| `2026-09-18` cross-adapter workflow | not implemented (`WorkflowStep` has no adapter field) | still the long-term goal: one run whose steps come from cardiacCore and cardiacFOAM. After cardiacCore has records |
| `2026-09-04` a case is a path; `2026-09-02` neutral default context | implemented | none |

### 7.3 History: plans the redesign superseded (25 August - 23 September)

All are finished. What they built still stands under the new design; their
open items are obsolete unless noted.

| plan | what survives | open items |
|---|---|---|
| `2026-08-25` monorepo migration | the package split and the import gate | none |
| `2026-08-27` core completion, phase 1 | core imports from a wheel; plugins selected by entry-point name | none |
| `2026-08-27` core completion, phase 2 | core suite runs alone; the 20 cardiac gates deleted | its Task 5 was finished by the neutral-default-context spec |
| `2026-08-27` test-core decoupling | core's tests collect without the sibling packages | none |
| `2026-09-03` documentation citation remediation | the dated-correction and cite-a-symbol habits | deferred items 1-4 are resolved (the symbols are gone). Items 5-7 are the licence question, still open: there is no `LICENSE` and no `license` field, while `CITATION.cff` says `GPL-3.0-or-later` and names driverFOAM |
| `2026-09-04` a case is a path | explicit roots; the wheel suite | none |
| `2026-09-20` phase 0, contract coherence | one fact per seam; required members derived | none |
| `2026-09-20` phase 1, provider stack | the provider stack (merged `02fde13`) | none |
| `2026-09-22` phase 2 prerequisites | deterministic provider order, typed readback, `#includeEtc` matching the real `foamEtcFile` | none |
| `2026-09-20` phase 2, one write channel | `commit_case_write`, `CaseWriterCapability`, recovery | "G3 does not close" is obsolete, see the next row |
| `2026-09-23` phase 3, finish the write channel | resolvers, `--apply` through the channel, the `describe` write surface | its open bypasses were all in factory tutorial modules, deleted by `1c5bb57`. Two writes remain outside the channel: `generic_case_mutation` (goes with item 5) and cardiacCore's `write_cell_set` (a declared exception) |

---

## 8. In flight, not landed

**`compat-delete`** (another agent, worktree at `17b5526`; not read for this
review). Scope, from `.superpowers/sdd/compat-audit.md` and the controller:
- the audit's DELETE list D2-D15 (RunDocument v1/v2 migrations, the root
  schema copy, `build_and_launch`'s launch half, the `driverFOAM` artifact
  alias, the old repair-journal directory, dead helpers, `bin/driverFoam`,
  implicit default contexts), but **not** D1: `omnidriver.postprocessing`
  stays, because the native scripts are being ported to it;
- `DRIVERFOAM_*` renamed to `OMNIDRIVER_*`, with no alias;
- the audit's §8 documentation fixes;
- the single-cell `blockMesh` unification.

The audit's trial of D1-D15 kept every non-native shape at 0 failed. The
native shapes were not run, and D4, D11 and D15 touch code they run.

**Stopped branches:**

| branch | where | state |
|---|---|---|
| `cc-records` (omniD) | worktree at `668cc8f` | uncommitted: deletes the 4 cardiacCore factory workflows and 3 test files, and `get_override_schema` (+164, −1,078 lines). It adds **no records**: its own comment says the workflows need a mesh and field bundle from outside the case, and step S does not exist yet. It cites `.superpowers/sdd/cc-records-report.md`, which does not exist. The controller reports its suite green |
| native `omnid/scripts` (cardiacFOAM) | worktree in this session's scratchpad (`.../scratchpad/native-wt/scripts`) | 2 commits on `omnid/tutorials-are-pointers` (`10d12b62`, `b810dda8`, both singleCell) plus one uncommitted edit (`singleCellinteractivePlots.py`). 12 of the 13 tutorial scripts that import `openfoam_driver` still do. Scope: port to `omnidriver.postprocessing` and the sweep layout; keep every script except `singleCell/calc_apd.py` and `plot_bueno.py` |
| native `omnid/records` (cardiacCore) | worktree in the scratchpad (`.../scratchpad/native-wt/cardiaccore`) | no commits beyond `main`; clean |

Both native worktrees live under `/private/tmp`. If that is cleared, the
uncommitted `omnid/scripts` edit is lost.

**Unpushed:**
- native `omnid/tutorials-are-pointers` at `c184d702`: 58 commits ahead of
  `github/omnid/tutorials-are-pointers`, 40 ahead of `github/main`, 0 behind.
  Every native `omnid/*` migration branch is merged into it.
- omniD `main`: `1f856df`, `9ec4e69` (origin is at `668cc8f`).

---

## 9. Worktrees

**Removed today by the controller:** four merged native migration worktrees,
and `lucid-murdock-303ba0`.

**Remaining** (omniD `.claude/worktrees/`):

| worktree | branch | state | does it still apply? | recommend |
|---|---|---|---|---|
| `awesome-bose-223e51` | `claude/awesome-bose-223e51` | 2 commits, clean, 265 behind | no. Both fixes are on `main` as `f8a5fdd` and `6d23503`; `_materialize_entry_case` on `main` returns `MaterializedEntry` and refuses a factory that ignores staging | drop |
| `vigilant-torvalds-f7721a` | `claude/kind-mcnulty-ecee51` | 1 commit, clean, 266 behind | no. On `main` as `24d30f0` (`describe` reads `record.to_json()["parameters"]`) | drop |
| `focused-franklin-c49d74` | `claude/quirky-elion-adb252` at `ff64ba3` | no commits; 7 files modified, 1 untracked | no. The edit adds `DriverContext.plugin_selector` and `--plugin` on the sweep child. `main` has both, consolidated into `core/runtime/run_command.omnidriver_run_command` (`e598b78`), tested by `test_sweep_run_plugin_propagation.py` | drop |
| `relative-sweep-paths` | `claude/relative-sweep-paths` at `ff64ba3` | no commits; 9 files modified, 1 untracked | no. The same edit plus absolute launch paths in `_run_launch_description`; `main` has that paragraph and code (`e598b78`) | drop |
| `festive-cray-9d30ca` | `claude/festive-cray-9d30ca` | merged at `eb47f6e`, clean, 195 behind | no; it is the old tutorials-are-pointers branch, fully merged | drop |
| `cc-records` | `cc-records` | uncommitted work (section 8) | yes, but not as it is: it deletes four working workflows with nothing in their place | keep; do not merge until step S and records exist, or the owner accepts losing them |
| `compat-delete` | `compat-delete` | in flight | yes | keep |

Two worktree folders hold branches with other names (`focused-franklin-c49d74`
holds `claude/quirky-elion-adb252`; `vigilant-torvalds-f7721a` holds
`claude/kind-mcnulty-ecee51`). The branches with those folder names exist
without worktrees.

**Local branches with no worktree**, all from 24 September or earlier:

| branch | state |
|---|---|
| `claude/focused-franklin-c49d74`, `claude/vigilant-torvalds-f7721a`, `claude/elastic-kapitsa-a55a4d` | on `main` as `ad165fe`, `cf024a9`, `7a32700` |
| `claude/lucid-murdock-303ba0` | merged |
| `claude/compassionate-gates-967e8d`, `claude/sharp-cannon-7e5e7c` | touch factory tutorial files that no longer exist |
| `fix/drop-bath-ecg-verifier` | same subject landed as `6dcc03a`; the patch differs, so compare before deleting |

Nothing was removed for this review.

---

## 10. Roadmap

Ordered by the goal: each item makes access more deterministic, or makes a
solver, environment or machine connection clear. **Kind:** *owner decision*,
*owner work*, or *agent work*.

| # | item | kind | depends on | why |
|---|---|---|---|---|
| 1 | **Land `compat-delete`**, including a native-shape run, since D4, D11 and D15 touch code it runs | agent work; owner review | — | removes the retired names and dead paths an agent could land on, and makes the environment names one family |
| 2 | Drop the five superseded worktrees and stale branches; push omniD `main` and native `omnid/tutorials-are-pointers` | owner decision | 1 | nothing unpushed or duplicated for an agent to mistake for current |
| 3 | **Supplied inputs for a record** (step S): a record may point at a mesh and field bundle outside its case, supplied like a native tree | agent work | 1 | cardiacCore's four workflows need it; `cc-records` stopped for want of it |
| 4 | **cardiacCore onto records under one reality**: native `omnid/records`, then omniD records sharing `omnidriver-openfoam`'s machinery, each passing C1-C12 | agent work; owner decides which of the four workflows migrate | 3 | one way to reach every OpenFOAM-family solver |
| 5 | **Delete core's factory plumbing** (audit O1-O12): `TutorialSpec`, `generic_case`, `tutorial_contracts`, `specs/validation`, `--entry-kind registered_tutorial`, `describe`'s factory fields, the required `get_tutorial_catalog` (M11). Decide the fate of the generic case-folder path and the from-scratch sweep | agent work; owner decision on the two paths | 4 | one entry kind for an agent; takes the core-shape debt to zero; closes the last write outside the channel |
| 6 | **Native script ports** (`omnid/scripts`): the 12 scripts left, to `omnidriver.postprocessing` and the sweep layout; delete `calc_apd.py` and `plot_bueno.py` | agent work | 1 (D1 kept) | post-processing reads runs from the one layout omniD writes |
| 7 | **The truth layer made first-class**: a supplied C++ source root, refused by name when missing, for the scanner, `rtst_scanner`, `names_parser` and the stale-build check (replacing three walk-ups to the retired layout); `rtst_scanner` and the ionic verification as native drift gates, not silent skips (M12); the scanner shared in `omnidriver-openfoam` and run for cardiacCore too; one "entries of dictionary X for solver Y" query; the export scripts in CI | agent work | 1; the cardiacCore part after 4 | an agent can trust a key because the catalog is checked against the source it cites |
| 8 | **The environment connection declared**: one supplied, per-machine environment description (the renamed runtime file) covering the OpenFOAM bashrc, `DYLD_LIBRARY_PATH` after sourcing, openCARP's MPI `bin`, `HYDRA_IFACE`; preflight checks each and names what is missing; the OpenFOAM disk search replaced by the supplied value; a missing configured file refused, not skipped; an OpenFOAM launcher check like openCARP's | agent work; owner decides the file's shape | 1 | moves what `CLAUDE.md` says in prose into something checked |
| 9 | **The machine connection declared**: the ranks-within-allocation flag (spec §4.4); host and launcher recorded in the run document; `campaign.sh`'s host recording taken into omniD; a site launcher such as `srun` only when a cluster shows the need (spec §6) | agent work; owner decision on the cluster | 8 | a run says where and how it ran, without a wrapper script |
| 10 | **The solver-descriptions plan**, steps 1-4: `niedererNVersion` to TOML; argument merging by `(step, key)`; `run.py`'s defaults (`-tend`, `-dt`, `-mass_lumping`); `manufacturedBidomain` to TOML | agent work; owner decisions D2, D3, D11 (freeze the current campaign first) | 1 | records become data an agent can read and edit without Python; `dt` and `tend` can be set together |
| 11 | **SI and units** (D17): `native_unit` on axes; any catalogued key with a unit sweepable in SI; openCARP units added with evidence for the keys a study sweeps | agent work | 10 (loader), 7 (catalog units) | one unit for every study, request and report |
| 12 | **Mesh checks for records**: run them, or delete the two `mesh_geometry` modules | owner decision, then agent work | 5 (their only callers go) | today a record's mesh is never checked |
| 13 | **O15**: the OpenFOAM layer stops naming core's files; the two layer-ownership guards | agent work | 1 | each file declared by the layer that reads it |
| 14 | **The electromechanics record** | owner work, with agent support for `WorkflowStep.cwd` (spec §5) | 10 | the owner's own test of the record form |
| 15 | **The Niederer campaign rerun** with exact-point sampling, on a cluster | owner work; last | 9, 10 (step 3 and the campaign's own revision), 11 (SI requests) | the benchmark result, with readers already on `main` (`f2cd0fd`, `c0a48de`) |

**Open defects found during the publication clean (2026-09-28):**
- **Electrode units across cardiacCore and cardiacFOAM.** cardiacFOAM reads
  electrode positions in metres. cardiacCore's `operations/electrodes.py`
  takes a caller-declared `coordinate_unit` and converts nothing. A
  millimetre case that feeds cardiacCore electrode coordinates into
  cardiacFOAM runs cleanly, with a pseudo-ECG a factor of 1000 off. It
  belongs with item 11 (SI and units).

**Later, not scheduled:**
- the cross-adapter workflow: one run using cardiacCore and cardiacFOAM
  steps (spec `2026-09-18-cross-adapter-workflow-design.md`), after item 4;
- spec §6's deferred items: more TOML records, carputils options (step 3b),
  the diagonal profile, parallel TL-EM, region-aware key validation, a shared
  electrophysiology vocabulary;
- the licence and `CITATION.cff` (owner decision; `CLAUDE.md` says not to add
  a licence without asking).
