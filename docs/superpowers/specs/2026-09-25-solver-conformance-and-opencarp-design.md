# Solver conformance, and openCARP as the first solver outside OpenFOAM

**Date:** 2026-09-25 · **Status:** implemented. Plan Tasks 1–13 are landed on
`main` (see the Status table at the end of this document for commits); Tasks
14 (the cardiacFoam target) and 15 (per-layer file ownership, which forces K3)
wait for `tutorials-are-pointers` step 5. The dated corrections below record
where the implementation settled differently from this document's original
text.

**Reasoning and evidence:** `docs/audits/2026-09-25-generality-and-landscape.md`.
**Builds on:** `2026-09-24-tutorials-are-pointers-design.md` (tutorial records,
axes, one commit per case). Its core steps are on branch
`claude/festive-cray-9d30ca` and **not yet on `main`**. Nothing here is
implemented before that branch merges.

## 1. Why

omniD's goal is to let an agent drive **any** numerical solver through one
pipeline: plan, run, sweep, post-process. It serves cardiac work today only
because the plugins that exist are cardiac.

Core has **no cardiac vocabulary**, and that is enforced. Core **is shaped like
an OpenFOAM case**, and that is not checked:
- runs are case directories;
- outputs are time directories;
- configuration is dictionaries;
- the environment is a sourced bashrc;
- core's default run script is Allrun/blockMesh;
- core's own records are declared by the OpenFOAM plugin.

So "solver-agnostic" is today a claim, not a property. Audit §2 has the full
inventory.

**Purpose (owner, 2026-09-25): prove it works.** The end goal is a benchmarker
agent that runs the same study on two solvers (cardiacFoam and openCARP) and
compares the results. This spec is step 1 of three:

1. omniD can drive openCARP at all.
2. omniD reads both solvers' results as the same quantities, such as Niederer
   activation times at P1–P9 (§10).
3. The benchmarker compares them.

openCARP is its own environment and solver, so it is one package with no
OpenFOAM layer beneath it. Check C1 proves exactly that.

This design turns the claim into an executable definition: a **solver
conformance suite** that any plugin must pass. **openCARP** is the first solver
made to pass it without going through the OpenFOAM layer. Each core change is
driven by a conformance check that fails, and a **shape gate** keeps the
OpenFOAM layout from creeping back into core.

## 2. Decisions (owner, 2026-09-25)

| item | decision |
|---|---|
| topic | the solver-adapter contract any solver can meet; one topic at a time |
| proving solver | openCARP |
| how openCARP is driven | binary + `.par` + mesh files; the adapter reads and writes `.par` through `commit_case_write`; the catalog comes from `openCARP +Help`; carputils is not used |
| done means | an openCARP record goes through describe → `plan --strict` → run, and a sweep through `sweep-run`; openCARP's own outputs are declared and reconciled; core gains the fixes the suite forces, plus the shape gate |
| approach | conformance suite first; openCARP is the first new plugin to pass it; failures drive core fixes |
| suite location | packaged in core (`omnidriver.conformance`), so third-party solver authors can run it |
| in-flight findings | recorded here as prerequisites P1 and P2 (§3) |
| later topics, not this one | reading result values (QoIs) and cross-solver comparison; executor/HPC; agent tool surface |

## 3. Prerequisites found on the in-flight branch

Both were found by tracing a record through `describe`, `plan`, `run` and
`sweep-*` on `claude/festive-cray-9d30ca` at `19d826a`. Both are
solver-independent. If the tutorials-are-pointers work lands them first, this
work consumes them; otherwise this work does them first, coordinated with that
branch.

**P1: records cannot reach `plan --strict` or `run --strict`.**
- `core/runtime/registry.py::_materialize_resolved_entry` raises
  `TutorialRecordError("tutorial records are not yet runnable through
  load_entry_spec")`, and `cli.main` does not catch it, so the user sees a raw
  traceback.
- `strict_planning._run_launch_description` writes
  `launch.command = run --strict --entry <record>` into every record's run
  document, and that command itself refuses.
- Only `sweep-run` works, through `sweep_runner._sweep_record` →
  `commit_record_case` → `record_case_spec`.
- Fix:
  - `strict_plan` handles the `tutorial_record` resolution kind the way a
    one-case sweep does: commit into a scratch stage via `commit_record_case`,
    then plan with `record_case_spec`.
  - A record's launch command becomes `run --run-document <path>`.
  - `cli.main` turns `TutorialRecordError` into its structured JSON error.
- Forced by C5.

**P2: render snapshots are seeded empty, a latent silent-data-loss path.**
- `commit_record_case` passes an **empty** scratch directory as the renderer's
  `snapshot_root`.
- The OpenFOAM renderer avoids the problem by reading from
  `resolved.request.case_root` (`openfoam/case_rendering._snapshot_copy`). The
  test fixture `tests/plugins/e2e_record_plugin.py::E2ERecordPlugin` reads
  `snapshot_root/<document>`, finds nothing, and writes a file holding **only
  the patched keys**.
- `core/case_transaction` does not refuse `exists_before=False` when the target
  exists on disk, so every other key in that document would be silently lost.
- No test notices, because the toy `mesh.json` has one key.
- Every new format adapter (openCARP's included) would fall into this.
- Fix:
  - Core copies each target document from the case into `snapshot_root` before
    calling `render_case_files`, so renderers patch a real file.
  - `case_transaction` refuses by name when `exists_before` contradicts the
    disk.
  - `E2ERecordPlugin` is fixed to patch rather than replace.
- Forced by C4.

**Owner decision, 2026-09-25: the agent must be agnostic too, not only the
code.** This adds three items; `docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md`
Tasks 10a, 11, 14 and 15 carry them.

1. **C10, discovery.** `describe` on any record returns `record_surface`: its
   axes with value kinds, a catalogue of the keys it can address, the plugin's
   agent guidance, and the case's own documentation (files with role
   `case.documentation`, e.g. a native `README.md`). The hooks are
   `get_record_key_catalog` and `get_agent_guidance`. Before this, an agent
   saw cardiacFOAM's keys through `dict_entries` and nothing for openCARP.
2. **Guidance per solver.** openCARP ships `guidance.md` (the evidence log
   distilled, each line citing its F/G id); cardiacFOAM's comes from what its
   validator and catalogues already enforce.
3. **Each file declared by the layer that reads it**, after step 5. Two guards
   force this: a role namespace has one owner per stack, and no plugin declares
   core's own files. This makes K3, previously deferred, a forced change.

## 4. The solver conformance suite (approved)

**What it is.** An executable definition of "a solver can plug into omniD":
plain library functions in `omnidriver/conformance/`, shipped in the core wheel.
Each returns a `CheckVerdict(check_id, passed, detail)`. There is no skip and
no "not applicable": a check that cannot run for a target is a failure naming
why, because a skip here would hide exactly what the suite exists to find.
Each package adds a thin pytest parametrization over its own targets, one test
per (target, check).

**Input.** One `ConformanceTarget` per solver, everything supplied, nothing
discovered (supplied-vs-discovered, `ENVIRONMENT_CONTRACT.md` §12):

```python
@dataclass(frozen=True)
class ConformanceTarget:
    plugin: str                      # plugin selector, as --plugin takes it
    record: str                      # a registered tutorial-record name
    cases_root: Path                 # supplied; never discovered
    sweep_name: str                  # one study name (a document:key or an axis)
    sweep_values: tuple[Any, Any]    # exactly two values
    unknown_name: str                # a name the record must refuse
    untouched: tuple[str, str]       # (document, key) a patch must not disturb
    environment: Mapping[str, str]   # the environment the solver runs in
```

**Checks.**

| id | check | catches |
|---|---|---|
| C1 load | the plugin validates and its stack composes **without** `openfoam-environment` unless the plugin declares it in `requires:` | a hidden dependency on the OpenFOAM layer |
| C2 describe no-op | with no study values, `describe` proposes zero changes against the real native case | a Python layer restating the native case |
| C3 refuse by name | a study naming `unknown_name` is refused, by that name, before anything runs | silent acceptance |
| C4 patch preserves | a one-key patch changes exactly that key; `untouched` and every other key in the document read back identical | P2 |
| C5 strict plan | `plan --strict` on the record returns no error diagnostics, and its run document's launch command is itself runnable | P1 |
| C6 run | `run` completes; every declared artifact is present and reconciled | outputs that are not time directories |
| C7 sweep | a two-point sweep over `sweep_name` stages, runs and reconciles both cases; the native tree's content hash is unchanged | writes to the native tree; staging leaks |
| C8 provenance complete | every file the case consists of appears in the provenance snapshot | root-level files skipped (§5, K4) |
| C9 environment | preflight is clean under `environment`, and fails with a **named** error when the solver binary is removed from it | the bashrc assumption |

**Tiers.**
- C1–C4 need the native case files, not the solver binary.
- C5–C9 need the real binary and carry the `native` marker. **Corrected
  2026-09-25 (final review S-I1):** openCARP's carry `native_opencarp`, so a
  repo-wide `-m native` (the cardiacFOAM tree) does not collect them.
- Native trees are supplied by environment variable: the existing
  `OMNIDRIVER_NATIVE_TUTORIALS`, plus `OMNIDRIVER_OPENCARP_TUTORIALS`. As with
  today's `native` tests, they **fail, not skip**, when unset. openCARP solves
  in about 0.25 s on a small mesh (measured), so the native tier stays cheap.

**Targets that must all pass.**

| target | package | shapes it runs in |
|---|---|---|
| `E2ERecordPlugin` / `toyTutorial` | core tests | all four, including core-alone and wheel; C4 fails on it first (P2), by design |
| cardiacFoam `restitutionCurves` | cardiacfoam tests | all four + native |
| openCARP `niedererNVersion` (§7) | opencarp tests | all four + native (`native_opencarp` since 2026-09-25) |

**Deliberately excluded:** checks on result *values* (the QoI topic), HPC,
agent-facing tools.

## 5. Core changes, each forced by a check

| id | change | forced by | symbols |
|---|---|---|---|
| K1 | = P1 | C5 | `registry._materialize_resolved_entry`, `strict_planning.strict_plan`, `_run_launch_description`, `cli.main` |
| K2 | = P2 | C4 | `record_execution.commit_record_case`, `case_transaction`, `E2ERecordPlugin` |
| K3 | **Core declares its own bookkeeping.** The names of core's files (`workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `workflow_logs`, `driverPostProcessingArchive*`) move out of `openfoam_case_runtime_conventions()` into core, which merges them into every stack's `CaseRuntimeConventions`. Otherwise a stack without OpenFOAM copies stale driver state into every stage | C7 | `CaseRuntimeConventions`, `sweep_runner._stage_entry_case`, openfoam's `case_runtime_conventions` |
| K4 | **Records declare what steps read and write.** The record `WorkflowStep` gains optional `consumes` / `produces` (case-relative paths or globs). `record_execution._workflow_dag_for_record` emits them into the DAG; artifact prediction for records is derived from `produces`, the one place the fact lives (no separate `expected_artifacts` list). `provenance_inputs.enumerate_case_inputs` walks case-file rules as **files**, not only as first-segment directories | C6, C8 | `tutorial_records.WorkflowStep`, `record_execution._workflow_dag_for_record`, `provenance_inputs._case_root_dirnames` |
| K5 | **Required members that only mean something for dictionaries become optional-neutral.** `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog` and `get_tutorial_displays` get empty fallbacks. `get_tutorial_catalog` stays required until factory tutorials retire (tutorials-are-pointers §7) | C1 | `capability_seams.members_by_tier`, `plugin_interface.validate_plugin`, the seam table |
| K6 | **A `string` value kind.** `VALUE_KINDS` has no kind for a string that may be empty or contain whitespace (`word` rejects both). openCARP's `String`, `RFile` and `WFile` parameters need it | C4 | `contracts/dictionary.VALUE_KINDS`, `validate_value_shape` |
| K7 | **Static gates stop hard-coding the adapter list.** `check-import-boundaries.py` ("whoever adds the fourth adapter must add it here"), `check-case-writes.py` (scoped to `openfoam/axes` and `cardiacfoam/records`) and the root `pyproject.toml` `pythonpath` each list the adapters. One declared list, `scripts/adapters.toml`, is read by all three gates | adding the fifth package | the three scripts |

Every K-change lands with the check that forces it failing first, then passing.
A K-change no check forces is not made here. The one exception is K7, which is
mechanical and needed the moment the package exists.

**Watched, not changed:** `workflow_runner._argv_for_execution` re-exports
`DYLD_*` only for case scripts. A direct binary inherits the environment
through `env=`, which is correct, but a SIP-protected interpreter spawning the
sweep child would strip `DYLD_*`. C7 exercises that path with the real sweep
child. The fix is made only if C7 fails there.

## 6. The shape gate

`scripts/check-core-shape.py`, a sibling of `check-import-boundaries.py`, scans
core's source (code and string literals, not comments) for OpenFOAM layout
tokens:

```
controlDict  fvSchemes  fvSolution  polyMesh  blockMesh  decomposePar
reconstructPar  processor  case.foam  Allrun  Allclean  bashrc
WM_PROJECT  FOAM_  foamlib
```

It exits non-zero on any occurrence not in `scripts/core-shape-baseline.txt`.

**The baseline is not a waiver list.** It records today's occurrences, each with
the symbol and a reason, and it can only shrink: the gate also fails when a
baseline entry no longer matches, so a removed occurrence must be deleted from
the file in the same change. A new occurrence can never be added to it. The
house rule "if you want a waiver, you are solving the wrong problem" applies to
new code from day one; the baseline is the recorded debt. K3 removes its first
entries.

## 7. The `omnidriver-opencarp` package

| may know about | must not know about |
|---|---|
| the openCARP binary, `.par` format, `mesher`, IGB and LAT output files, openCARP tutorials | OpenFOAM, foamlib, cardiacFoam, carputils |

- Entry point: `opencarp = omnidriver.opencarp.plugin:OpenCARPPlugin`.
- Plugin id: `org.omnidriver.opencarp`.
- `requires:` is empty, which is what C1 checks.
- One package: openCARP is both the environment and the application, so it is
  not split yet.

**Components.**

- **`.par` format** (`par_format.py`). Parses `key = value  # comment` lines,
  keeping order and comments. Patches rewrite a value in place. A patch to a
  key absent from the file (openCARP then uses its default) appends the key in
  one marked block. The format name is `opencarp_par`. The renderer reads the
  real document (made reliable for every adapter by K2).
- **Parameter catalog** (`catalog.py`).
  - Built from the binary: `openCARP +Help` lists about 265 parameters with
    types, and `+Help <name>` gives the description, type, default and menu
    (verified on v18.1).
  - Committed as `opencarp_parameters.json`, stamped with the openCARP git hash.
  - A `native` drift test regenerates it from the real binary and diffs. This is
    the "real case or native-source drift gate" rule, with the binary as the
    native source, so no C++ scanning is needed.
  - Types map to value kinds:

    | openCARP type | value kind |
    |---|---|
    | `Int`, `Short` | `integer` |
    | `Float` | `scalar` |
    | a menu | `enum` |
    | `String`, `RFile`, `WFile` | `string` (K6) |
    | `Flag` | decided by evidence (§9) |

  - Indexed names match templates: `stim[0].pulse.strength` matches
    `stim[Int].pulse.strength`.
- **Record-key validator, config-value reader, case-value comparator.**
  - These are the three capabilities `record_execution._resolve_and_split`
    refuses by name without.
  - The validator checks names and values against the catalog.
  - The reader returns the value the case's `.par` holds, or `None` when the
    key is absent. It never substitutes the catalog default: the case holds its
    own values, and defaults are the catalog's fact.
  - The comparator is numeric-aware (`1e-3` equals `0.001`) and quote-agnostic.
- **Case writer:** `clone_and_patch` only.
- **Command authorization:**
  - solver command `openCARP`, since artifacts are credited only to solver
    commands;
  - auxiliary commands `mesher`, `igbextract`, `igbhead`;
  - resolution through `PATH` in the supplied environment.
- **Environment preflight.** Checks that each binary resolves and that
  `openCARP -buildinfo` actually runs. On this machine, the installed binary
  fails to load `libsundials_cvode.7.dylib` until `DYLD_LIBRARY_PATH` includes
  Homebrew's lib directory (verified). The named error `opencarp_binary_unloadable`
  carries the loader's message. The library path is **supplied**, never
  discovered.
- **Runtime conventions.** No time directories and no decomposition prefix. The
  generated directories are the record's `produces` (K4), such as the `-simID`
  output directory.

**The first record: `niedererNVersion`.**
- Native case: openCARP's own `02_EP_tissue/03E_study_resolution`, the Niederer
  2011 N-version benchmark (verified). Its `nversion.par` holds the physics:
  - ionic model tenTusscherPanfilov with `flags=EPI`;
  - conductivities 0.17/0.019/0.019 and 0.62/0.24/0.24;
  - a 1.5 mm stimulus cube at 35.71 for 2 ms;
  - LAT detection.
- Workflow steps:
  1. `mesh`: `mesher` building the 20×7×3 mm slab.
  2. `solve`: `openCARP +F nversion.par -meshname <mesh> -simID <out>`, with
     `produces` the output directory's `vm.igb` and LAT file.
- `tend`, `dt` and `mass_lumping` are real `.par` keys, so studies name them as
  `nversion.par:tend` and so on. They are not command-line flags: the case holds
  every value it can.
- One axis: **`dx`** (µm) → the `mesh` step's `-resolution[i]` arguments.
- The record cites `run.py`'s
  `mesh.Block(size=(20, 7, 3), resolution=dx/1000, centre=(10, 3.5, 1.5))` for
  the slab geometry. Geometry has no native file in this tutorial, so the
  record's `mesh` step is where that fact lives.
- Conformance target:
  - sweep `dx` over two coarse values, so the native tier stays seconds long;
  - a short `tend`;
  - `unknown_name` is a misspelled key;
  - `untouched` is `nversion.par:gregion[0].g_il`.

**Settled 2026-09-25 (evidence: `docs/solver-learning/opencarp.md` F1–F7, G1–G5).**
These supersede the corresponding details above.

- **Flag (F1).** In a `.par`, only `0` and `false` mean off; `no` and `off`
  silently mean on. A Flag's value kind is `boolean`, and the writer emits
  `1`/`0`. The validator refuses any other spelling in a study. The reader
  refuses a non-`0`/`1` Flag in a native file, naming the key, and never
  interprets it.
- **Indexed keys (F2).** openCARP itself refuses `stim[1].*` when
  `num_stim = 1` (exit 5). The validator refuses it earlier, by name, using the
  count key's value in the staged `.par` after patching.
- **Slab (F3).** The `mesh` step runs
  `mesher -size[0] 2.0 -size[1] 0.7 -size[2] 0.3 -center[0] 1.0 -center[1] 0.35
  -center[2] 0.15 -mesh slab`, with size and center in cm. The `dx` axis
  contributes `-resolution[0..2] <dx>` in µm.
- **Physics regions (F4).** The record adds none; outputs are byte-identical
  without them.
- **Working directory (F5).** Relative paths resolve against the working
  directory, so both steps run with the staged case root as their working
  directory. The solve step passes `-imp_region[0].im_sv_init singlecell.sv`
  case-relative, citing `run.py`.
- **Outputs (F6).** The LAT artifact is `<simID>/init_acts_vm_act-thresh.dat`:
  one value per mesh point in point order, `-1` for never activated
  (`lats[0].all = 0` in `nversion.par`).
- **Stimuli (F7).** `num_stim` defaults to 2; `nversion.par` states
  `num_stim = 1`, so the native case is safe.
- **Units (G2).** `dt` is in µs and `tend` in ms.
- **Secrets (G3).** Every openCARP log starts with a build header containing a
  CI token. The adapter declares a log redaction rule, and core applies it
  before writing `workflow_logs/` (plan Task 9).

## 8. Testing

- **The four suite shapes** from `CLAUDE.md`, with `-e packages/omnidriver-opencarp`
  added to the all-packages environment. The conformance module must import and
  pass from the **installed wheel**: it ships in core, so it must not read
  repository-relative state.
- **The native tier:** `-m native` with both native-tree variables set
  (corrected 2026-09-25, S-I1: `-m native` for cardiacFOAM's tree and
  `-m native_opencarp` for openCARP's, each with its own variable). The
  openCARP targets need the real binary, per "fixtures can't settle external
  claims".
- **Static gates:** the existing three, plus `check-core-shape.py`.
- **Per openCARP component:** tests run against real openCARP files. This means
  `nversion.par` and the tutorial `.par` files for the parser and patcher, and
  the real binary for the catalog. There are no invented `.par` or mesh fixtures.

## 9. Order of work

0. The tutorials-are-pointers branch merges to `main`. P1 and P2 are
   coordinated with it (§3).
1. `omnidriver.conformance` skeleton with C1–C4, run over `E2ERecordPlugin` and
   cardiacFoam `restitutionCurves`. C4 fails; land K2 (P2).
2. C5–C8 over both targets; land K1 (P1), K3 and K4 as their checks fail.
3. `check-core-shape.py` with its baseline. K3's entries leave the baseline in
   the same change.
4. `omnidriver-opencarp`: catalog, `.par` format, validator, reader and
   comparator. C1–C4 pass on `niedererNVersion`. K5 and K6 land when openCARP
   hits them. K7 lands with the package.
5. Writer, commands, preflight, artifacts: C5–C9 pass in the native tier.
6. Record the result in this document's status table, with commit hashes.

**Evidence taken from the real binary** (all settled 2026-09-25; see the block above §8) (decided by running it, never
by assumption). These are tracked, with the runs that settle them, as F1–F7 in
`docs/solver-learning/opencarp.md`, which also holds the evidence behind §7;
the method is `docs/solver-learning/method.md`. Two were added after this list
was written: F6 (the LAT file's first column) and F7 (`num_stim` defaults to 2).
The first five:
- how a `Flag` parameter is written in a `.par`;
- what openCARP does with an indexed key beyond its count, such as `stim[1].*`
  when `num_stim = 1`. If it silently ignores the key, the validator refuses
  such keys by name;
- which `mesher` arguments reproduce carputils' `Block(size, resolution,
  centre)` extents. Check by comparing point extents;
- whether the tutorial's `gen_physics_opts` region options are needed, or
  whether openCARP's defaults cover a single-tag slab;
- how `imp_region[0].im_sv_init` (`singlecell.sv`, an absolute path in
  `run.py`) resolves case-relative in a staged clone.

## 10. Out of scope

- Reading result values into quantities (QoIs) and cross-solver comparison,
  such as Niederer LATs from cardiacFoam against openCARP. This is the next
  topic, and this record sets it up.
- Executor/HPC seams, and the agent tool surface (MCP, typed tools, READMEs
  exposed to agents).
- The paradigm layer: in-process Python steps, surrogates.
- Removing the rest of the shape baseline (`scripts/run_case.sh`,
  `specs/paths.py`'s OpenFOAM layout, `{time}` in `DataArtifact`). This is
  recorded debt, removed as later work or later solvers force it.
- The cardiac names in core's `dict_entries.py` that the vocabulary gate misses
  (audit §2). This is a separate small fix.
- carputils, and openCARP's Python experiment scripts as native cases.

## Status

Plan: `docs/superpowers/plans/2026-09-25-solver-conformance-and-opencarp.md`.
Ledger of the working sessions (parallel tracks, review rounds): the (session-
local) `progress-solver-conformance.md` and `task-*-report.md`/`track*-report.md`
files this plan's execution produced.

| task | what | commit(s) |
|---|---|---|
| 1 | conformance skeleton, C1–C3 over the toy target | `5efd986` |
| 2 | C4, a patch preserves its siblings | `9149ac2` |
| 3 | K4 (`WorkflowStep.produces`/`consumes`); C5, C6 | `022688f`, amended `09d205c`/`dbf6692` (fix round: union with utility-manifest `produces`; malformed-field refusal) |
| 4 | K8 (sweep keeps each case's `artifact_reconciliation`); C7 | `e14906b` |
| 5 | C8, consumed inputs are fingerprinted | `0aea2da`, amended `00fcf8f` (fix round: only real fingerprints count) |
| 6 | C9, environment preflight names a missing solver | `4be1e0f` |
| — | Tasks 1–6 fix round (review): a check that cannot run is a failed verdict, native-tree guard, timeouts, C3 name-token matching, bite tests | `d9686c9`, `c40e972`, `ddce4d1`, `b9f17e9`, `95f6716`, `bb7399c`, `d7e5622`, `db2c096`, `d63bbf5` |
| 7 | the core shape gate, `check-core-shape.py` | `dae4585`, amended `8615c59`/`17fa42f` (fix round: normalized/snake_case token matching, `--write-baseline` preserves reasons) |
| 8 | `omnidriver-opencarp` package skeleton, the `.par` format | `383d73f` |
| 9 | the parameter catalog (generated, drift-gated); K6 (`string` value kind) | `0ed15dc` |
| 10 | record-key validator, index-bound check | `b1a065e` |
| — | Tasks 8–10 fix round (review): broken entry point refused by name, import-boundary list derived, CI job + CLAUDE.md line brought forward, string-menu quoting, injection refusal, F10–F13 quoting settled by real runs | `b686817`, `6da2783`, `b3ecc23`, `5bb2da5`, `cc16455`, `bb9daf3`, `688bd93` |
| 10a | the record surface (`record_surface` capability); C10 | `47f2de7` |
| 11 | `OpenCARPPlugin`, `niedererNVersion`; C1–C10 pass against the real openCARP v18.1 binary | `e4bc873` |
| 12 | K9, step logs are redacted by plugin-declared patterns before they are kept | `7e0d11f`, native proof `e9c448c` |
| — | Tasks 10a/11/12 fix round (wave-2 review): command-owned keys refused by name (F14), a case-writer refusal reaches `plan --strict` as JSON, redaction replaces the whole match, a record run carrying its steps is runnable without asking the adapter | `5bf06c0`, `29530d2`, `483408b`, `b7cdaf3`, `458824f`, `ad11256`, `c2a9448` |
| 13 | this document's Status table; CI; CLAUDE.md (this task) | — |
| 14 | cardiacFoam `restitutionCurves` conformance target | waiting for `tutorials-are-pointers` step 5 |
| 15 | per-layer file ownership (forces K3) | waiting for `tutorials-are-pointers` step 5 |

### Dated corrections (2026-09-25)

**K5 (demote the dictionary trio to optional) was not made.** No check forces
it: `OpenCARPPlugin` stubs `get_dict_entries`, `get_dict_groups` and
`get_dictionary_catalog` exactly as `MinimalTestPlugin` already did, and C1
passes with the members still required-but-stubbed. Per §5's own rule ("a
K-change no check forces is not made here"), K5 stays deferred.

**K3 (core declares its own bookkeeping names) moved to Task 15, forced by a
guard, not by a conformance check.** No check in C1–C10 fails without it:
records name their inputs through `consumes` (K4, Task 3), so provenance never
walks core's own bookkeeping files (`workflow_state.json`,
`run_document.json`, and the rest) in the first place, and nothing here
exercises that path. The owner's 2026-09-25 gap-2 decision adds a guard in
Task 15 — one role namespace per stack, no plugin declaring core's own files —
and K3 lands there once that guard is what forces it.

**K7 was reduced to extending the existing lists**, not the single declared
`scripts/adapters.toml` this document originally proposed. `omnidriver-opencarp`
was added directly to each existing enumeration instead:
`check-import-boundaries.py`'s forbidden-import list is now *derived*
(`foamlib`, plus every `packages/*/src/omnidriver/<pkg>` outside core's own
distribution) rather than hand-listed, with a per-adapter `adapter_rules` block
that fails the gate by name if an adapter package has none (`6da2783`);
`check-case-writes.py`'s `SCANNED_ROOTS` and the root `pyproject.toml`'s
`pythonpath` each gained the new package's paths directly (`383d73f`). No
single source-of-truth file was introduced.

**New K8: the sweep runner keeps each case's artifact reconciliation.**
`sweep_runner._record_sweep_run` used to discard the child `run
--run-document`'s `artifact_reconciliation` along with the rest of its stdout;
C7 needs it per case to check both a sweep's cases actually produced their
declared outputs. `_child_reconciliation` parses it out and folds it into
`case_summary["artifact_reconciliation"]` (`e14906b`).

**New K9: step logs are redacted by plugin-declared patterns before they are
kept.** openCARP's build header prints a CI token on every run, and omniD keeps
solver stdout under `workflow_logs/` verbatim, so that credential would be
copied into every run record. `RuntimeEvidenceCapability` gained
`log_redaction_patterns()`; `workflow_runner.redact_step_logs` applies them to
a step's stdout/stderr right after the process ends (`7e0d11f`). **The
contract later changed** (wave-2 review I3, `b7cdaf3`/`458824f`): the original
implementation kept a pattern's first capture group, so the conventional
`password=(\S+)` kept the secret and dropped only its label. Every match is now
replaced whole by `[REDACTED]`, and both the toy's and openCARP's patterns
became lookaround-only (`(?<=://)[^/\s@]+(?=@)`) so they match just the
credential.

**C4 checks the `untouched` key only, not every key in the document.**
`check_patch_preserves` reads back exactly `target.untouched` (one
`(document, key)` pair the target supplies) and compares it before and after
the patch; it does not enumerate every other key in the document. Sibling
enumeration is format-specific (a `.par`'s keys are not a dictionary's
entries), and one sibling is enough to catch the P2 class of defect (a
renderer that replaces the whole document instead of patching it) — proven by
`ReplacingRendererPlugin` in the toy suite.

**C8 is defined over `consumes`, and requires a real fingerprint.**
`check_provenance` walks `report.workflow_dag`'s per-step `consumes` lists (the
K4-derived DAG field, not the record's raw `WorkflowStep.consumes`) and checks
each consumed path is fingerprinted in the provenance snapshot. The fix round
(review I1, `00fcf8f`) narrowed what counts as fingerprinted: a path only
counts when a provenance component has `kind in {"case_file",
"external_link"}` and `strength != "unavailable"` — listing a path is not the
same as fingerprinting it, and a `GhostConsumesPlugin` test proves the check
bites a consumed file that does not exist.

**C10 (agent discovery) was added**, beyond this document's original C1–C9.
`describe` on any record now returns `record_surface`: the record's axes with
value kinds, a catalogue of the keys it can address, the plugin's agent
guidance, and the case's own documentation (files with role
`case.documentation`). `check_discoverable` (C10) checks that this surface
actually names the target's patched key, among other things. Task 10a
(`47f2de7`); openCARP declares both hooks and passes C10 against the real
binary in Task 11 (`e4bc873`). cardiacFOAM does not declare them yet, so C10
fails for that stack until Task 14.

**Core fixes found by the reviews, beyond K1–K9:**
- **A broken plugin entry point is refused by name**, not left to break
  discovery for every other stack. Before this fix, one unimportable entry
  under `omnidriver.plugins` (openCARP's, mid-development, before `plugin.py`
  existed) raised a bare `ModuleNotFoundError` out of default selection and out
  of an explicit `--plugin` for an unrelated, working stack.
  `plugin_discovery.BrokenPluginError` names the entry point, its
  distribution, its target and the original error (`b686817`).
- **A case writer's refusal reaches `plan --strict` as structured JSON, not a
  traceback.** A validator refusal already reached the CLI as JSON, but a
  renderer refusal (openCARP's F2 index-bound check, raised as
  `ParFormatError` at render time) escaped as a bare traceback with empty
  stdout. `record_execution.commit_record_case` now turns a `ValueError` the
  case writer raises while resolving or rendering into a `TutorialRecordError`
  naming the record and the document(s), chained `from` the original (wave-2
  review I2, `29530d2`).
- **A record run carrying its own steps is runnable without asking the
  adapter.** `run_document_exec` used to gate every run document, including a
  tutorial record's, through the adapter's `is_case_runnable_without_workflow`
  — a question meant for a bare case folder without driver-owned workflow
  metadata. A record run's document *is* that metadata. `_is_record_run_with_steps`
  exempts a document whose planner-stated `resolvedEntry.entryKind ==
  "tutorial_record"` carries a non-empty `workflowDag.steps` from that gate
  (wave-2 review I4, `ad11256`); the now-unnecessary hook was deleted from
  `OpenCARPPlugin` and the toy `E2ERecordPlugin` (`c2a9448`). cardiacFOAM keeps
  its own hook, which still serves non-record case folders.

**P1 and P2 landed upstream**, on the `tutorials-are-pointers` branch, before
this plan's Task 1: P1 (records reach `plan --strict`/`run --strict`) as
`156b80d`; P2 (a render snapshot is seeded from the real case, and
`case_transaction` refuses a disk/`exists_before` contradiction) as `56d89d7`.
Task 1 Step 1 verified both were present before any of this plan's own work
began.

**Evidence F10–F14** (`docs/solver-learning/opencarp.md`), each driving a
concrete change:
- **F10** (an unquoted value containing `=` is silently truncated at the first
  `=`): the config reader now refuses rather than reports a wrong raw value —
  `get_config_value_reader` raises `ParFormatError` for a `string`-kind key
  whose unquoted native value contains `=`.
- **F11** (`""` is the empty string, quotes removed): confirms `format_value`
  can always quote a string without changing what a native `""` already meant.
- **F12** (`#` starts a comment even inside quotes, leaving an unbalanced
  quote): `format_value` refuses to write a string containing `#`, by name.
- **F13** (a balanced pair of quotes is otherwise transparent — model names,
  `.sv` paths, multi-word values all round-trip byte-identical): licenses
  `format_value`'s F10/F12-driven "always quote" rule as safe for every
  existing shipped `.par` value, not just the ones that need it.
- **F14** (openCARP reads its arguments in order; the last assignment wins,
  silently, whether from a `.par` or a command-line flag after `+F`):
  ownership of a key is positional, not per-document. `validation.read_documents`
  derives, from each record step's own command, which `+F` document and which
  `-<key>` flags after it are command-owned; the record-key validator refuses a
  study naming a command-owned key by name, and `get_record_key_catalog` omits
  it from the discoverable catalogue.
