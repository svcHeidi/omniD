# Step S: supplied inputs for a tutorial record

Written 2026-09-28 against `main` at `12533b3`. Design only: no code, no
commits. Roadmap item 3 (`docs/superpowers/ROADMAP.md` §10). It governs how
cardiacCore's four factory workflows become records (item 4), and so how the
factory plumbing is deleted (item 5).

Sources read: native cardiacCore `main` at `d1afc3e` (through `git show`);
native cardiacFOAM `omnid/tutorials-are-pointers` at `c184d702`; the stopped
`cc-records` diff (read-only); the owner's local data directories, listed
but never written.

## 0. The design in one paragraph

A record gains **one field**, `inputs`. Each input has a name, a list of
`(path inside the input, case-relative destination)` pairs, and optionally a
**native location** under the native tree. A native location is native
fact: that is the idealized heart's `../mesh`. With no native location, the
input must be **supplied** with `--input NAME=PATH`, or the plan is refused
by name. Staging copies the native case first, leaving out every input
destination, and then copies each input file to its destination, inside the
same staging lease. Every destination must be read by some step, so the
existing provenance fingerprints it (C8). The run document records where
each input came from. C11 expects the native paths plus the input
destinations. Nothing else changes: `WorkflowStep`, `DefaultArgument`,
`AxisContract`, `ProducedPath` and the runner stay as they are.

## 1. The four cardiacCore workflows

### 1.1 What exists

| omniD factory workflow | native tutorial (`tutorials/biventricularPreprocessing/variants/`) | native case folder on `main` | anatomy bundle (local, git-ignored) |
|---|---|---|---|
| `cardiaccore-human-purkinje-slab` | `humanSlab` | `cases/bivCase`: `Allrun`, `system/` (controlDict, fvSchemes, fvSolution, coordinatesConventionDict, 4 utility dicts) | only inside the owner's checkout, `cases/bivCase/{0,constant}` |
| `cardiaccore-human-purkinje-endocardial` | `humanEndocardial` (the human anatomy bundle) | **none**. `COMPARISON.md` names the human anatomy bundle's directory, which `.gitignore` ignores whole | `~/cardiacCore-local-cases/<human anatomy bundle>` |
| `cardiaccore-pig-morphometric-purkinje` (weighted LV) | `pigMorphometricTransmural` (the pig-extended anatomy bundle) | **none**. The pig-extended bundle's directory is ignored whole | `~/cardiacCore-local-cases/<pig-extended anatomy bundle>` (to confirm, §6) |
| `cardiaccore-pig-transmural-purkinje` (all-leaves LV) | **none**. `.gitignore` lists `variants/pigTransmural/` as exploratory and "redundant with one of the three canonical tutorials" | none | — |

Every factory workflow defaults to `case_dir_name="bivCase"`. So on a clean
native tree the two tree workflows run against a case that has no
`generatePurkinjeTreeDict`. Only `humanSlab` has a native case today.

### 1.2 What each utility reads from outside the case folder

Every utility builds `Time` and `fvMesh` (`#include "createTime.H"`,
`"createMesh.H"`), so each one reads `constant/polyMesh`. Every field is read
at `runTime.timeName()`, which is `0` from `controlDict`'s `startTime 0`: cardiacCore
has no time and always writes `0/`. The case folder holds only `system/`.
Everything below comes from the bundle.

| utility | reads from the bundle (evidence) | writes (evidence) |
|---|---|---|
| `setCardiacConductivity` | `0/<fiberField>`, `0/<sheetField>` (`diffDict.get<word>("fiberField")`/`("sheetField")`, then two `MUST_READ` `IOobject`s); native dict: `fiber`, `sheet` | `0/Conductivity` (`conductivity.write()`); `0/ConductivityIntracellular` and `0/ConductivityExtracellular` only when the dict has both sub-dictionaries (`hasIntracellular`) |
| `setCardiacAnatomy` | `0/<longitudinalField>`, `0/<intraventricularField>`, named by `system/coordinatesConventionDict` (`conventionDict` `MUST_READ`) | `0/aha_angle`, `0/phiRV`, `0/groove_interface`, `0/AHA_Segment` (the four `.write()` calls at the end of `setCardiacAnatomy.C`) |
| `setPurkinjeSlab` | `0/<transmuralField>`, `0/Conductivity` (the `conductivityFields` loop), `coordinatesConventionDict` | `0/PurkinjeLayer`; `0/Conductivity` rewritten in place |
| `setPurkinjeMorphometry` | `0/<longitudinalField>`, `0/<intraventricularField>`, `coordinatesConventionDict` | the four `0/Purkinje*` fields (`AUTO_WRITE`) |
| `generatePurkinjeTree` | `0/<transmuralField>`, `0/<longitudinalField>` (`MUST_READ`), the intraventricular convention; under `weightedField`, the two terminal-weight fields | `constant/polyMesh/sets/{LV,RV,RVSeptal}EndoFaces`, `EpiFaces`; `postProcessing/generatePurkinjeTree/*` |

On `main`, `bivCase`'s convention names `uvc_transmural`, `uvc_intraventricular`
and `uvc_longitudinal`. The native README's "Local case contract" gives
exactly this bundle: `constant/polyMesh/`, `0/fiber`, `0/sheet` and the
three `uvc_*` fields.

**Two drifts the records must fix, found by this reading:**
- `setCardiacAnatomy` also writes `0/phiRV` and `0/groove_interface`.
  omniD's `UTILITY_MANIFESTS` and the `humanSlab` README list only
  `AHA_Segment` and `aha_angle`. A record that omits them fails C11: a
  restage carries them.
- The factory's anatomy, slab and morphometry steps do not list
  `system/coordinatesConventionDict` in `consumes`, but all three read it.

**Why the bundle is listed file by file.** The local bundles hold outputs
from earlier runs. `bivCase/constant/polyMesh/sets/` holds `LVEndoFaces` and
`EpiFaces`, and `bivCase/0/` holds `Diffusivity`, `PurkinjeLayer` and others.
If the whole directory were copied, those old outputs would come in, and C6
would pass `generatePurkinjeTree`'s declared face sets on stale files.

### 1.3 The records, written out

The shared parts, in `cardiaccore/records/anatomy.py`:

```python
MESH = tuple(f"constant/polyMesh/{n}" for n in ("boundary", "faces", "neighbour", "owner", "points"))
UVC = ("0/uvc_transmural", "0/uvc_intraventricular", "0/uvc_longitudinal")
ANATOMY = RecordInput(
    name="anatomy",                       # --input anatomy=<bundle dir>
    files=tuple((p, p) for p in (*MESH, "0/fiber", "0/sheet", *UVC)),
)                                         # no native_relpath: always supplied
CONV = "system/coordinatesConventionDict"

def step(step_id, utility, *, consumes, produces):
    return WorkflowStep(step_id, (utility, "-case", "."), consumes=(f"system/{utility}Dict", *consumes), produces=produces)

CONDUCTIVITY = step("conductivity", "setCardiacConductivity",
    consumes=(*MESH, "0/fiber", "0/sheet"), produces=("0/Conductivity",))
ANATOMY_STEP = step("anatomy", "setCardiacAnatomy",
    consumes=(CONV, "0/uvc_longitudinal", "0/uvc_intraventricular"),
    produces=("0/aha_angle", "0/phiRV", "0/groove_interface", "0/AHA_Segment"))
MORPHOMETRY = step("purkinje_morphometry", "setPurkinjeMorphometry",
    consumes=(CONV, "0/uvc_longitudinal", "0/uvc_intraventricular"),
    produces=("0/PurkinjeLongitudinalRegion", "0/PurkinjeCircumferentialRegion",
              "0/PurkinjeTerminalWeightSubendocardial", "0/PurkinjeTerminalWeightIntramural"))
TREE_OUT = (*(f"constant/polyMesh/sets/{s}" for s in ("LVEndoFaces", "RVEndoFaces", "EpiFaces", "RVSeptalEndoFaces")),
            *(f"postProcessing/generatePurkinjeTree/{f}" for f in ("purkinje.vtk", "lv-purkinje.vtk", "rv-purkinje.vtk", "generation_params.txt")))
```

The three records:

```python
HUMAN_SLAB = TutorialRecord(                       # mirrors cases/bivCase/Allrun
    name="humanSlab", native_case_relpath="cases/bivCase", inputs=(ANATOMY,),
    workflow_steps=(CONDUCTIVITY, ANATOMY_STEP,
        step("purkinje_slab", "setPurkinjeSlab", consumes=(CONV, "0/uvc_transmural", "0/Conductivity"),
             produces=("0/PurkinjeLayer", "0/Conductivity")),
        MORPHOMETRY))

HUMAN_ENDOCARDIAL = TutorialRecord(                # variants/humanEndocardial/README "Active stages" 1-3
    name="humanEndocardial", native_case_relpath="cases/humanEndocardial", inputs=(ANATOMY,),
    workflow_steps=(CONDUCTIVITY, ANATOMY_STEP,
        step("purkinje_tree", "generatePurkinjeTree", consumes=(CONV, *UVC), produces=TREE_OUT)))

PIG_MORPHOMETRIC_TRANSMURAL = TutorialRecord(      # variants/pigMorphometricTransmural/README stages 1-4
    name="pigMorphometricTransmural", native_case_relpath="cases/pigMorphometricTransmural", inputs=(ANATOMY,),
    workflow_steps=(CONDUCTIVITY, ANATOMY_STEP, MORPHOMETRY,
        step("purkinje_tree", "generatePurkinjeTree",
             consumes=(CONV, *UVC, "0/PurkinjeTerminalWeightSubendocardial", "0/PurkinjeTerminalWeightIntramural"),
             produces=TREE_OUT)))
```

- `cases_root` is the native cardiacCore tree root.
- `setPurkinjeSlab` consumes `0/Conductivity`, which an earlier step
  produced. So it is an intermediate, and `record_generated_relpaths`
  already excludes it from a restage.
- No record has axes. A study sets `document:key` directly (for example
  `system/setPurkinjeSlabDict:thickness`), checked against cardiacCore's
  catalog (§5, S3).
- The native READMEs list a fifth stage, `1DgraphToFoam → constant/purkinjeGraph`,
  which the factory never ran. It is left out until the owner decides (§6, D4).

### 1.4 Verdict per workflow

| workflow | verdict |
|---|---|
| `humanSlab` | **fits** with step S; native case exists; needs the bundle supplied |
| `humanEndocardial` | fits once a native case folder is tracked (`system/` only, from dicts the owner confirms; two local copies differ in their seeds, §6 D2) |
| `pigMorphometricTransmural` | fits once a native case folder is tracked. The only dicts are the older form: `uvcConventionDict`, which `main`'s C++ no longer reads (it reads `coordinatesConventionDict`). They must be rewritten and run for real before the record counts |
| `cardiaccore-pig-transmural-purkinje` | **does not fit: no native tutorial**. Deleted (owner rule), not migrated |

## 2. The mechanism

### 2.1 One field and one value type

```python
@dataclass(frozen=True)
class RecordInput:                     # beside DefaultArgument in core/tutorial_records.py
    name: str                          # the supply name
    files: tuple[tuple[str, str], ...] # (path inside the input, case-relative destination); "." = the input itself
    native_relpath: str | None = None  # default location under cases_root; None = must be supplied

TutorialRecord.inputs: tuple[RecordInput, ...] = ()
```

Checked when the record is built, and refused by name:
- a duplicate input name;
- empty `files`;
- a source that escapes the input;
- a destination that is not case-relative, is the case root, or holds `{`
  or `}`;
- two destinations that are equal, or one inside the other;
- a destination that no step consumes, where neither the destination nor a
  path under it appears in any step's `consumes`. This ties every supplied
  file to a step, so C8 covers it;
- a destination some step produces before any step consumes it (the
  destination would be generated, not supplied).

A pair `(".", to)` takes the input itself, which may then be a file.

### 2.2 How it is supplied, and never discovered

| where | form |
|---|---|
| CLI | `--input NAME=PATH`, repeatable, on `describe`, `plan --strict`, `run --strict`, `sweep-plan`: every command that stages |
| Python | `strict_plan(..., inputs={name: Path})`, `commit_record_case(..., inputs=)` |
| already-staged runs | `run`, `step`, `recover` and `sweep-run` read the resolved inputs from the run document or sweep manifest. They never ask again and never rediscover |
| study key | **not built**. Studies are JSON in the native tree, and a machine path there would put the owner's data layout into it. A cohort sweep is §4 |

**Resolution** (`resolve_record_inputs(record, supplied, *, cases_root)`):
- A supplied path wins.
- Otherwise the native location under `cases_root` is used. It is computed
  only when nothing is supplied, following the "evaluate defaults lazily"
  rule.
- Otherwise the plan is refused.

Each refusal is a `TutorialRecordError`, which the CLI prints as JSON:
- `RecordInputNotSupplied`:
  "record 'humanSlab' needs input 'anatomy' (10 files: constant/polyMesh/boundary, …); it has no native location; supply --input anatomy=<dir>";
- `RecordInputIncomplete`: names each missing source file;
- an unknown `--input` name, naming the record's inputs.

`describe` does not refuse. It lists each input with `supplied: true|false`,
so an agent learns the names before it has the data (C2, C10).

### 2.3 Staging: copy, not link, and where

The order in `record_execution._stage`:
1. Copy the native case as today. The excluded paths
   (`record_generated_relpaths`) now also include every input destination,
   so a destination never comes from the case folder, including a run case
   being restaged.
2. Copy each `(source, destination)` into the staged case, making parents
   as needed.
3. Run the axes, then commit, as today.

Steps 1 and 2 happen in one `_stage_entry_case` promotion, under the same
lease. It gains one argument, `overlays: Sequence[tuple[Path, str]]`,
applied to the temporary copy before it is promoted. A crash then never
leaves a half-staged case.

**Copy, never link.** Steps write inside destinations: `generatePurkinjeTree`
writes `constant/polyMesh/sets/*`, and OpenFOAM truncates and rewrites
files. A symbolic link would send those writes into the patient bundle or
the native tree. A hard link would do the same through the shared inode.
Supplied data is read-only, like the native tree. The cost is one copy per
staged case (the anatomy bundles are about 400 MB each, polyMesh plus five
fields). Clone-on-write copies are deferred until a sweep shows the cost.

### 2.4 Provenance

- **Content.** Every destination is consumed by a step (§2.1), so
  `enumerate_case_inputs` fingerprints it as a `case_file`, and it enters
  `input_provenance_digest`. No second hashing pass is needed.
- **Origin.** The run document gains
  `resolvedEntry.inputs: [{name, kind: "native"|"supplied", path, files}]`,
  from `record_case_spec`'s metadata. The sweep manifest carries the same
  list once.
- **Identity.** The source `path` is not part of identity, just as `source`
  is excluded from stack identity. Moving a bundle changes nothing; changing
  its content changes the digest.

### 2.5 The three kinds of case path, and C1-C12

| kind | comes from | restage rule |
|---|---|---|
| authored | the native case folder | copied |
| supplied | an input, native or supplied | re-copied from the input; never taken from the case |
| generated | a step's `produces`, touched first by produces | dropped (`record_generated_relpaths`, A5) |

| check | with inputs |
|---|---|
| C1, C3, C4, C9, C12 | unchanged |
| C2 | unchanged: inputs are not patches |
| C5, C6, C7 | plan and run with `ConformanceTarget.inputs`, forwarded as `--input` to every child CLI |
| C8 | unchanged code; now covers inputs, because §2.1 makes every destination consumed |
| C10 | `record_surface` lists `inputs` (names, files, native location or "must be supplied"); C10 asserts the key is present |
| C11 | restages with the same resolved inputs, and expects the native paths **plus** each input's destination files. It still names every carried and dropped path |

### 2.6 Two questions for each abstraction

| abstraction | which current solver-use problem requires it | why a small solver-specific function is insufficient |
|---|---|---|
| `TutorialRecord.inputs` / `RecordInput` (about 70 code lines) | cardiacCore's workflows read a mesh and five fields that are not in the case folder (§1.2), so no record can run them, and `cc-records` stopped for this reason. The idealized heart's four cases read `../mesh` | Staging is core's (`record_execution._stage`) and runs before any solver code. `WorkflowStep.consumes` must be case-relative. Two plugins need the same thing, so a per-plugin copy would break "one reality" |
| `--input NAME=PATH`, `strict_plan(inputs=)` (about 40) | A patient bundle has no ambient truth (§12), so it must be supplied | The CLI, the planner and the run document are core's. A per-solver environment variable would be discovery under another name |
| `_stage_entry_case(overlays=)` (about 25) | The copy must share the staging lease and promotion, or a crash leaves a half-staged case | Staging is core's |
| `resolvedEntry.inputs` (about 10) | A run must say which bundle it used; the fingerprints say only what the files held | The run document is core's |
| `ConformanceTarget.inputs`; C11's expected set (about 30) | Without them, C5-C7 cannot plan, and C11 names every input as carried | The suite is core's packaged suite |

**Not built, each failing the second question or having no current use:**
- **A "base case" overlay** (the whole bundle under the native case). It
  brings in stale outputs (§1.2), so C6 would pass on old face sets.
- **A `cp` step in the record.** A step cannot name a path outside the case,
  the source would not be fingerprinted, and axes run before steps.
- **Links.** See §2.3.
- **A separate source digest.** The destinations are already fingerprinted.
- **Input kinds or formats** (mesh, field, graph). Core never needs them;
  the record lists files.
- **Input mappings that change with the route.** An agent supplies a
  different file instead (§3).
- **A per-case input in a sweep.** §4.
- **A default location for cardiacCore bundles** (`~/cardiacCore-local-cases`,
  or the owner's `cases/`). It would invent an answer.

## 3. One reality: the same mechanism on the idealized heart

`tutorials/idealizedHeart/mesh/` is tracked in the native cardiacFOAM tree
(through Git LFS, `.gitattributes`). Each case's `Allrun` copies a subset of
it, sometimes under another name. That path is **native fact**, so the
record names it, and an agent may still supply another.

```python
IH_MESH = RecordInput(
    name="mesh", native_relpath="idealizedHeart/mesh",
    files=(("constant/polyMesh", "constant/polyMesh"),
           *((f"0/{f}", f"0/{f}") for f in ("fiber", "sheet", "sheetNormal", "tm", "tv", "apicobasal", "Conductivity")))),
)                                                          # electroHeart/Allrun, "cp -a ../mesh/constant/polyMesh ..." and the seven cp lines
IH_GRAPH = RecordInput(name="purkinjeGraph", native_relpath="idealizedHeart/mesh/constant/purkinjeGraph",
                       files=((".", "constant/purkinjeGraph"),))
ELECTRO_HEART = TutorialRecord(
    name="electroHeart", native_case_relpath="idealizedHeart/electroHeart", inputs=(IH_MESH, IH_GRAPH),
    workflow_steps=(
        WorkflowStep("t_field", ("setExprFields", "-case", "."), consumes=("system/setExprFieldsDict", "0/tm"), produces=("0/t",)),
        WorkflowStep("solve", ("cardiacFoam", "-case", "."), consumes=(*POLYMESH_FILES, "0/fiber", "0/sheet", "0/sheetNormal",
                     "0/tv", "0/apicobasal", "0/Conductivity", "0/t", "constant/purkinjeGraph"), produces=(...)),
    ))
```

- `POLYMESH_FILES` is cardiacFOAM's existing `records/case_outputs.py`
  polyMesh file list.
- The pig tree, which the `Allrun` selects with its `pig` argument, needs no
  route: the agent supplies
  `--input purkinjeGraph=<tree>/idealizedHeart/mesh/constant/purkinjeGraphPig`.
  That is the owner's "loose, let the agent compose" rule, and the run
  document records the choice.
- `pathos/conductionBlock` needs the graph copied to
  `constant/purkinjeGraph.healthy`: the same input, with another
  destination.
- `electroMechHeart` sends the mesh to both `constant/electro/polyMesh` and
  `constant/solid/polyMesh`, and `fiber` to `0/solid/f0`: two pairs with one
  source, which §2.1 allows.

**LFS pointers.** Each idealized-heart `Allrun` refuses a mesh that is still
a Git-LFS pointer. The same rule belongs in staging: refuse, by name, a
staged input file that begins `version https://git-lfs.github.com/spec/`.
That is about 8 lines, it names no solver, and it lands with the first
idealized-heart record (S7).

## 4. Cases that still do not fit

| case | what is missing | what it would need |
|---|---|---|
| `cardiaccore-pig-transmural-purkinje` | no native tutorial | delete (S5) |
| `humanEndocardial`, `pigMorphometricTransmural` | no tracked native case folder | owner-confirmed dicts tracked natively (§6 D1-D3); a real run each |
| `electroHeart`, `pathos/ionicPathology` | no `system/controlDict` or `constant/electroProperties` natively: `Allrun` links `controlDict.<variant>` and `electroProperties.<variant>` in. `controlDict` is the mandatory marker, so the native default does not exist | a native default: the monodomain files under the plain names (owner). ionicPathology also has no default pathology (`Allrun` refuses with no argument) |
| `pathos/conductionBlock` | no default pathology; the graph is cut by an `awk` function inside `Allrun` | a case-local script, or the `lbbb`/`rbbb` graphs committed; the owner picks a default |
| `electroMechHeart` | TL-EM, the owner's own work | step S covers its inputs; the rest is `WorkflowStep.cwd` (solver-descriptions spec §5) |
| a cohort sweep (one record over the eight human anatomy bundles) | a per-case input | a reserved study name, or a sweep-file field, once a real cohort study exists; one sweep per bundle until then |
| a bundle whose field names differ from the native dict's (`fiberField`, the convention's names), or a `cobiveco` anatomy | the record's files are the native names | a native case with its own dicts (a `cobiveco` `coordinatesConventionDict`) and its own record; renaming a field by study is not supported |
| the `1DgraphToFoam` hand-off | `SUPPORT_BOUNDARY["pending"]` says `-maxEdgeLength` must scale with the mesh unit (these meshes are in mm) | owner decision D4 |

## 5. Implementation plan

The prerequisites:
- `compat-delete` has landed (roadmap item 1), because S1 touches `cli.py`
  and `record_execution`.
- Work happens in a worktree made from local `main`, with its own venv.
- All six shapes stay at 0 failed after each task.
- The static gates pass. In particular, core names no OpenFOAM token, so
  core's tests use a toy bundle, never `polyMesh`.

| task | files | code | prose | tests | proof |
|---|---|---|---|---|---|
| **S1** core mechanism | `core/tutorial_records.py` (`RecordInput`, field, checks, `resolve_record_inputs`); `core/runtime/record_execution.py` (`_stage`, metadata, plumbing through preview/commit/spec); `core/runtime/sweep_runner.py` (`overlays`); `core/strict_planning.py`; `core/runtime/record_surface.py`; `cli.py` (`--input`) | +190 | +70 | +260: every §2.1 and §2.2 refusal; destinations never taken from the case; the input copied, not linked; the run document's `inputs`; lazy native default | toy suite |
| **S2** conformance | `conformance/target.py` (`inputs`), `checks.py` (C5-C7 forward, C10 key, C11 expected set); a toy record with a supplied bundle passing C1-C12 in core | +30 | +10 | +70 | toy C1-C12 |
| **S3 first real proof: `humanSlab`** | cardiacCore: `records/{__init__,anatomy,human_slab}.py`; `get_tutorial_records`; a record-key validator and key catalog over `catalogs/inputs.py`, sharing the OpenFOAM half (`system/*` written as asked, unvalidated) with cardiacFOAM's through `omnidriver-openfoam`, per one reality; `UTILITY_MANIFESTS` gains `phiRV` and `groove_interface`; guidance, 10 lines; `tests/test_conformance_native.py`, marker `native_cardiaccore`, with `OMNIDRIVER_CARDIACCORE_TREE` (a clean native worktree) and `OMNIDRIVER_CARDIACCORE_ANATOMY` (the bundle), both supplied, failing rather than skipping when unset; a new `CLAUDE.md` shapes row. Native (the `omnid/records` worktree): the README's expected outputs gain the two fields | +150 (records 60, validator and catalog 75, wiring 15) | +35 | +130 | `plan --strict` and `run --strict --input anatomy=...` for real; C1-C12; **parity**: the factory workflow and the record on the same bundle give byte-identical `0/` outputs (the method of the earlier migrations' parity checks), reported before S5 |
| **S4** the other two | native: `cases/humanEndocardial/system/*`, `cases/pigMorphometricTransmural/system/*` (controlDict, fvSchemes, fvSolution, coordinatesConventionDict, utility dicts; about 250 data lines); omniD: two records (+45 each) and conformance parametrization | +95 | +10 | +20 | each run for real against its anatomy bundle; C1-C12; parity with the factory on the same bundle where the factory can run it |
| **S5** delete cardiacCore's factory | `workflows/preprocessing.py` (−499); the factory parts of `run_config.py`, `overrides.py`, `plugin.py` (`get_tutorial_catalog` empty, `get_override_schema`); `test_biv_preprocessing_contract.py`, `test_entry_case_parity.py`, `test_workflow_inputs_follow_overrides.py`. The `cc-records` diff is a reference, never merged | about −750 | about −120 | about −450 | all shapes at 0 failed; the three records still pass C1-C12 |
| **S6** delete core's factory plumbing (audit O1-O12, less the case folder) | `TutorialSpec` shrinks to the planned-case object records and case folders both build (drop `build_cases`, `apply_case`, `plan_case`, `setup_root`, `output_dir`), and `CaseConfig` goes; delete `tutorial_contracts.py`, `tutorials_display.py`, `specs/validation.py`, `specs/common.py`, `--entry-kind registered_tutorial`, the registry's factory resolution, `describe`'s factory fields (`registered_tutorials`, `special_tutorial_aliases`, `available_tutorials`), the required `get_tutorial_catalog` (M11), cardiacFOAM's `tutorial_displays.py`, and `export-tutorials-catalog.py`. **Kept:** `--entry <case dir>` through `generic_case.py` | about −1,300 to −1,800 (measured when the task starts) | about −300 | about −1,500 | all shapes at 0 failed; the core-shape baseline reaches zero only if the case-folder path's one OpenFOAM token moves too (roadmap item 5, owner) |
| **S7** (optional) idealized heart, the second consumer | native: the monodomain default under the plain names (owner, §4); omniD: `electroHeart` record (+40), the LFS-pointer refusal in staging (+8) | +48 | +10 | +40 | a real serial run; probe against `regression/injection.monodomain.reference`; C1-C12 |

The order is S1 → S2 → S3 (stop and report parity) → S4 → S5 → S6. S7 may
follow S2 at any point. S3 is the first real proof. Nothing is deleted until
S3's parity report is accepted.

## 6. Open decisions for the owner

| # | decision | recommendation |
|---|---|---|
| D1 | Where the two new native cases live | `cases/humanEndocardial/` and `cases/pigMorphometricTransmural/` beside `cases/bivCase`, so the existing `cases/*/0/` and `cases/*/constant/polyMesh/` ignore rules keep the data out. The alternative, un-ignoring the two anatomy-bundle directories under `cases/` to match `COMPARISON.md`, would mark the owner's local data directories as untracked |
| D2 | Which of the human case's dicts are authoritative | The owner's checkout copy (the human bundle's `system/`, 23 September, `coordinatesConventionDict`, seeds from a placement script) differs in its seeds from `~/cardiacCore-local-cases/<human anatomy bundle>`. Recommend the newer one, confirmed by a run |
| D3 | The pig case's dicts and bundle | The only dicts use `uvcConventionDict`. Rewrite them as `coordinatesConventionDict`, and confirm the pig-extended anatomy bundle is the pig-extended case's mesh and fields |
| D4 | `1DgraphToFoam` in the tree records | Leave it out now (the factory never ran it; the edge-length scaling is pending); add it as a step when the graph hand-off is decided |
| D5 | The `humanSlab` bundle for S3 | It exists only inside the owner's checkout (`cases/bivCase/{0,constant}`), which agents must not touch. The owner copies `constant/polyMesh/{boundary,faces,neighbour,owner,points}`, `0/fiber`, `0/sheet` and `0/uvc_*` to `~/cardiacCore-local-cases/bivCase_base/`, or allows a read-only supply from the checkout |
| D6 | Record names | The native variant names (`humanSlab`, `humanEndocardial`, `pigMorphometricTransmural`), replacing `cardiaccore-*` with no alias |
| D7 | The native test marker | `native_cardiaccore`, with the two variables of S3, and the cardiacCore utilities built from the native worktree (the binaries on `/Volumes/OpenFOAM-v2412` were built on different days, and include `setCardiacScar` from 16 September, before `main` removed scar, so which commit built each one is unknown) |
| D8 | S7 and the idealized-heart native defaults | Yes, after S4: it is the second consumer that proves one reality. The native change (monodomain as the plain files) is the owner's |
