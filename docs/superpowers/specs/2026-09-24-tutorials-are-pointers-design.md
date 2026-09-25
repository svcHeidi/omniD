# Tutorials are pointers: the native case is the default

**Date:** 2026-09-24 · **Status:** design approved section by section by the
owner; awaiting review of this written form before an implementation plan.

## 1. Why

omniD exists so that everything that changes a case passes through one
channel. G3 never closed (Phase 2 close-out, then Phase 3 Task 11's nine open
bypasses) because the migration was additive: the write channel was built
beside cardiacFOAM's standalone-era writers instead of replacing them, and
each tutorial moved only its catalog-addressable parameters onto it.

The deeper cause is that a native cardiacFOAM tutorial is already a complete,
purposeful case, and the Python layer restates it. Measured 2026-09-24 by
collapsing every tutorial to the case its native files are checked in as,
running `describe` against a scratch copy of
`noFrontendCardiacFoam_minor_errors/tutorials`, and comparing every proposed
write with the native file:

| tutorial | default writes vs native | notable |
|---|---|---|
| cable1DRestitution | 12/12 no-op | pure derived functions |
| singleCell | 3/3 no-op | its native study uses kwargs it does not accept |
| restitutionCurves | 9/9 no-op | |
| manufacturedEikonalECG | 11/11 no-op (hex) | tet branch has direct writes |
| manufacturedBidomain | 6/6 no-op | all 7 native studies pass unaccepted kwargs |
| niederer2012 | 5 no-op, 1 study-driven change | tet branch has direct writes |
| manufacturedMonodomainPseudoECG | 11 no-op, 1 contradiction | `anisotropic` |
| manufacturedMonodomain1D3D | 3 no-op, 1 contradiction | default `endTime` 0.1 vs 0.200028 |
| manufacturedPurkinjeGraph | 1 no-op | its only action is a file copy |
| cable1DCVConvergence | 6 no-op, `endTime` differs | shares a native case with cable1DRestitution |
| manufacturedBathBidomain | 10 no-op, 1 contradiction | preview fails on `main` (dead key) |
| manufacturedMonodomainTotalLagrangianEM | wrong key, does not run | deferred, see §8 |
| heartSolverComparison | preview fails | points at a case that does not exist |

About 85 of about 90 default writes put back a value the native file already
holds. The five that do not are either contradictions (the Python default is
wrong against the case) or study-driven.

**How it got this way.** Native commit `54b1fb65` (2026-08-19, "migrate
bathBidomain off bash to driverFOAM sweep.json") deleted the tutorials'
orchestration bash scripts (the `__LC__` mesh gate, the tet overlay swap, the
gradient-scheme screen) and moved their logic into driverFOAM's Python;
`17eb3010` did the same for eikonalECG. driverFOAM became external (omniD) on
2026-09-07. The same commit *added* `fdaBathVariant` to the native
`electroProperties` because the Python always wrote it — the dependency points
the wrong way. 32 native study JSONs now speak Python-only vocabulary
(`mesh_family`, `numerics_profile`, `fv_scheme_overrides`, `grad_scheme`, ...).

## 2. Decisions

| item | decision |
|---|---|
| Python defaults (`tutorials/defaults/`) | deleted; the native case is the default |
| derived functions | kept, as named **axes** |
| study vocabulary | native study JSONs rewritten to name real dictionary keys plus axes (option A) |
| tutorial structure | a small data registration per tutorial (option 1) |
| `heartSolverComparison` | deleted |
| `manufacturedMonodomainTotalLagrangianEM` | deferred, untouched until electromechanics; then built in this same shape |
| `synthesize` mode (`dict_builder.py`) | frozen: nothing added, nothing deleted now |
| single-cell stimulus amplitude | a per-model field in the ionic model catalog; `STIMULUS_MAP`'s rule deleted |
| (N, dt) grids | written in the study JSONs, including 1D3D's (its N⁻² formula is not kept) |
| bath `phiERefPoint` | stays a derived axis, reading extents from `blockMeshDict.<dim>` instead of a copied table |
| pseudo-ECG `ecgDomains.ECG.verificationModel.anisotropic` | native file set to `yes`; the Python derivation deleted |
| tet `.geo` generation | native templates use `DefineConstant[ lc = ... ]`; the workflow passes `gmsh -setnumber lc <value>`; `render_tet_geo`'s file write deleted |
| tet numerics overlay copy | deleted (the overlay is byte-identical to the case's own `system/fvSchemes`) |
| dead `manufacturedBidomain.fdaBathVariant` key | removed from native and Python |
| OpenFOAM-owned keys | written as asked, flagged `unvalidated`, see §5 |
| cable1DCVConvergence stimulus | its study states its own `externalStimulus` explicitly |

**The gmsh claim was checked with the real binary** (gmsh 4.15.2): with
`DefineConstant[ lc = 0.5 ];`, `-setnumber lc 0.25` gives 143 nodes against 45
at 0.5; with a plain `lc = 0.5;` assignment the flag is ignored (45 nodes).

## 3. Components and ownership

**Native repo (owner).** The case holds every value. Studies are
`setup/studies/*.json`. The native fixes above land here.

**Core (`omnidriver`), no cardiac vocabulary.**

- The existing sweep engine (`core/sweep/sweep_expansion.py`, versioned
  `sweep-spec.schema.json`) runs studies unchanged in shape: `entry`, `base`,
  `sweep` with `independent`/`dependent` and `zip`/`product`.
- A **study name** is one of two things. A `document:dotted.path` name is a
  dictionary key, written as the literal path in the file (no
  `$ELECTRO_MODEL_COEFFS`-style placeholder in studies). A bare name is an
  axis.
- An **axis** is a contract: a name, the kind of value it accepts, and a pure
  function `(value, read-only view of the staged case) -> (patches, command
  arguments)`. Core defines the contract and ships no solver axes. The
  existing naming derivations (`case_id_template`,
  `output_dir_name_template` in `core/sweep/sweep_derivation_catalog.py`) stay
  as they are. Adapters provide axes through a capability, like every other
  capability on the provider stack.
- Every patch is committed in the case's one `commit_case_write`.

**OpenFOAM package.** Generic axes: N → blockMesh resolution
(`plan_block_mesh_resolution` plus the per-dimension formula), N → gmsh
`-setnumber lc`, the dt unit conversion (`plan_delta_t`).

> **Corrected 2026-09-25 (owner, step 3 scope change).** OpenFOAM owns only
> the blockMesh-resolution axis (`block_mesh_resolution_axis`, built on
> `plan_block_mesh_resolution`). gmsh is not part of OpenFOAM: its `lc ->
> -setnumber` derivation is a derived function of whichever cardiac record
> meshes with gmsh (step 5), not this package's. The dt unit conversion is
> not needed at all -- it existed only because the old Python kwargs spoke
> milliseconds; studies now name real keys directly (e.g.
> `system/controlDict:deltaT` in seconds), so there is nothing left to
> convert.

**cardiacFOAM package.**

- A tutorial is a data record: name, native case path, allowed axes, workflow
  steps (`blockMesh -dict ...`, `gmsh ...`, `cardiacFoam`, ...). Where the
  native case supports two meshing routes, the record declares both workflow
  variants, and the `mesh` selector (`hex` or `tet`) picks one. It selects
  declared steps; it writes nothing.
- Cardiac axes: dx → cells (`cell_counts_from_dx`), the S1-S2 schedule →
  `externalStimulus` arrays (`generate_spatial_stimulus_lists`), restitution
  `endTime`/`writeAfterTime`, `phiERefPoint` from `blockMeshDict.<dim>`, and
  dimension (the `blockMeshDict.<dim>` choice plus the `dimension` key).
- The ionic model catalog gains the per-model single-cell amplitude. The key
  catalog keeps `typical_value='60'` as its generic hint.

**Deleted:** `tutorials/defaults/`; the twelve `make_spec`/`_plan_case`
modules (their derived logic moves into axes); every side-door writer they
call; `heartSolverComparison`; the tests of all of these.

## 4. One case, step by step

1. **Expand.** The sweep engine turns the study into cases; each is one flat
   set of values (`base` plus that case's sweep values). `base` is how a value
   is set for all cases.
2. **Resolve the entry.** A registered name gives the native case path and the
   allowed axes. A plain case path is accepted too, but allows only direct
   dictionary keys, no axes.
3. **Stage.** The native case is cloned into the sweep's staging directory.
   The native tree is never written.
4. **Sort names.** Each name is a dictionary key or an allowed axis; anything
   else is refused by name before anything runs.
5. **Run axes** on the staged case (read-only), collecting patches and command
   arguments.
6. **Combine.** Direct keys and axis patches form one list. Two sources
   setting one key to different values is refused (this replaces
   `merge_assignments`' "later write wins").
7. **Validate and commit.** cardiacFOAM keys are checked against the catalog;
   everything goes in one `commit_case_write`. A patch equal to the case's
   current value is reported as unchanged and not written.
8. **Run** the workflow steps with the axes' command arguments.

`describe` performs steps 1–7 without committing: that is the preview.

Example, bath's gradient-scheme study rewritten:

```json
{
  "entry": "manufacturedBathBidomain",
  "base": {
    "dimension": "3D",
    "mesh": "tet",
    "constant/electroProperties:bidomainSolverCoeffs.bathPotentialDomain.interfaceConductivityInterpolation": "distanceWeightedHarmonic",
    "system/fvSchemes:gradSchemes.default": "Gauss linear",
    "system/fvSchemes:laplacianSchemes.default": "Gauss linear corrected",
    "system/fvSchemes:snGradSchemes.default": "corrected",
    "system/controlDict:endTime": 0.02
  },
  "sweep": {
    "mode": "zip",
    "independent": { "number_cells": [20], "system/controlDict:deltaT": [0.00224215] },
    "dependent": [{ "name": "caseId", "derive": "case_id_template", "of": ["number_cells"] }]
  }
}
```

## 5. Refusals, the OpenFOAM-key exception, and enforcement

Refused before anything runs, naming the offending key:

- a name that is neither `document:path` nor an allowed axis (catches old
  vocabulary and typos);
- a cardiacFOAM key absent from the catalog (a key the C++ reads but the
  catalog lacks is added to the catalog, never bypassed);
- two sources setting one key to different values;
- an entry whose native case path does not exist.

**OpenFOAM-owned keys** (`system/fvSchemes`, `fvSolution`, `controlDict`, ...)
are a different kind of key: read by upstream OpenFOAM, and there is no full
catalog for them today. They are written as the study asks, with no check
invented in place of a catalog, but through the channel (planned, previewed,
journaled, rolled back), and every such patch carries an `unvalidated: no
OpenFOAM catalog` flag in `describe`'s preview and in the write record. An
OpenFOAM catalog is a named future step, for when omniD's builder can define
each key properly, defaults included. Nothing here depends on it or blocks
it.

**Enforcement.** A static gate, like `scripts/check-import-boundaries.py`,
with an empty waiver list: tutorial registrations and axis modules may not
import or call a writer (`update_foam_entry`, `apply_*_overrides`, `shutil`,
`write_text`, `open(..., "w")`). Axes return patches and command arguments;
only `commit_case_write` writes a case. Frozen `synthesize` code is outside the
gate's scope. G3's "no bypasses" becomes a build failure instead of a
close-out search.

## 6. Testing

- **Per tutorial:** its registration, previewed with no study values against
  the real native case, proposes zero changes. This would have caught all
  three contradictions in §1. It needs the native tree, per the rule "real
  case or native-source drift gate, nothing invented".
- **Per axis:** its function against real native files (e.g. `number_cells:
  20` on bath's `blockMeshDict.3D` gives `(20 20 20)`).
- **Per rewritten study:** it expands and previews without a refusal.
- Old tests are deleted with the code they test.

## 7. Order of work

1. Delete `heartSolverComparison`.
2. Core: the axis contract, name sorting, conflict refusal, "unchanged"
   reporting, the `unvalidated` flag, the static gate (on from the start,
   scoped to the new registration and axis modules).
3. OpenFOAM package: the generic axes. **Corrected 2026-09-25 (owner):**
   this is `block_mesh_resolution_axis` only -- gmsh `lc` and the dt unit
   conversion moved out of this step; see §3's own dated correction.
4. Pilot `cable1DRestitution`: registration, axes, rewritten native study;
   match the old module's output on the real case; then delete the old module,
   its defaults and its tests.
5. The remaining tutorials, one at a time, in the same steps. Native fixes land
   with their tutorial (`anisotropic yes` with pseudo-ECG, `DefineConstant`
   with the tet studies, the dead key with bath; cable1DCVConvergence's study
   states its own `externalStimulus`).
6. The per-model single-cell amplitude in the ionic model catalog, with
   `singleCell`.

## 8. Out of scope

- `manufacturedMonodomainTotalLagrangianEM`: deferred until electromechanics.
- `synthesize` mode: frozen.
- An OpenFOAM key catalog: future (§5).
- Generating the cardiacFOAM key catalog from the C++: `dict_entries_catalog.py`
  is hand-written, each entry citing its C++ reader, and
  `scripts/scan-dict-keys.py` is an approximate (~80%) drift report, not a
  contract. Making it generated or enforced is separate work.
- Artifact staging (placing a source file such as a Purkinje graph into a
  case). `manufacturedPurkinjeGraph` and `manufacturedMonodomain1D3D` still
  need it; they are migrated last, or wait for it.

## Status (added 2026-09-25)

Steps 1-3 of §7's order of work are done, each verified in all four suite
shapes (`packages/ -q -m "not slow and not native"`, core alone, the
installed wheel, and `-m native` against the real
`noFrontendCardiacFoam_minor_errors` tutorials tree) plus the three static
gates (`check-import-boundaries.py`, `export-capability-seams.py --check`,
`check-case-writes.py`), all 0 failed.

| step | what | commits |
|---|---|---|
| 1 | Delete `heartSolverComparison` | `4ee4354` |
| 2 | Core: axis contract, name sorting, conflict refusal, "unchanged" reporting, `unvalidated` flag, the static gate | `4ee4354..2c6c964` (`git log 0edb21e..HEAD`) |
| 3 | OpenFOAM package: the generic axes -- scope-changed by the owner (2026-09-25) to `block_mesh_resolution_axis` only; see §3/§7's own dated corrections above for why gmsh `lc` and the dt unit conversion moved out | `f178f1a` (core: pin the axis-map duplicate-name refusal), `3fa1170` (openfoam: `block_mesh_resolution_axis` + unit/native tests) |
| 4a | The cardiac stack support every tutorial record needs before the first real record exists: cardiacFOAM's `RecordKeyValidationCapability` (`record_key_validation.py`, catalog-checked for `constant/electroProperties`/`constant/physicsProperties`, accepted-unvalidated for `system/...`, refused otherwise), OpenFOAM's `CaseValueComparisonCapability` (`_case_value_agree`, delegating to the existing `apply_overrides.effective_values_agree`) and its `ConfigValueCapability` reader for the synthetic `hex_cell_counts` key (`case_planning.read_hex_cell_counts`). No core contract change: `DirectKeyValidator` stays `(document, key_path, value) -> (value_kind, validated)` -- the `<solver>Coeffs` first-segment substitution the validator needs is syntactic and catalog-vocabulary-derived, never a read of the staged case's actual `myocardiumSolver` value, so no staged-case-root parameter was needed. Verified against the real `electrophysiologyProtocols/restitutionCurves_s1s2Protocol` case (`myocardiumSolver singleCellSolver`, `stim_amplitude 0.4`, `system/controlDict` `deltaT 1e-5`, one real `hex (` block `(200 30 70)`) through `record_execution.preview_record_case` on the real cardiac stack (`load_discovered_plugin("cardiacfoam")`), with a test-only `TutorialRecord` and no test doubles for validator, comparator or reader. | `9759fb2` (cardiacfoam: the record-key validator), `8d4a08d` (openfoam: the case-value comparator and hex-cell-counts reader), `d3b7afb` (cardiacfoam: native evidence) |

## Owner decisions, 2026-09-25 (recorded alongside step 4a)

(a) **The pilot tutorial (§7 step 4) is `restitutionCurves`, not
`cable1DRestitution`.** `restitutionCurves` (native path
`electrophysiologyProtocols/restitutionCurves_s1s2Protocol`) is the first
tutorial actually migrated onto tutorial records; `cable1DRestitution`
follows later, per its own post-processing decision below.

(b) **`cable1DRestitution`'s post-processing**, once it migrates: its record
runs the native `setup/postProcessing_cableRestitution.py` as a workflow
step, invoked with `--case-id`. The script reads the case's own dictionaries
plus omniD's per-case case record -- not a Python-side restatement of either.
Both sidecar files the pre-migration tooling wrote per case
(`.driverfoam_case_id`, `.cardiacfoam_protocol.json`) and the committed
`.driverfoam_case_id` are deleted at the point this tutorial migrates (§7
step 5), not before -- they are retired alongside the code that reads them,
not left as dead files a later session has to notice separately.

Step 3's own note for step 5: multi-dimension tutorials will need an axis
that reads a SECOND study value (e.g. `N` together with `dimension`, to pick
which `blockMeshDict.<dim>` document to patch) -- `AxisFunction` today is
`Callable[[value, staged_case_root], AxisResult]` and sees only the one
value it was invoked with. The minimal contract change: let an
`AxisContract` declare the OTHER study names it reads (e.g.
`reads_also: frozenset[str] = frozenset()`), and have
`resolve_case_patches` resolve those named values from the same
`study_by_source` and pass them alongside the axis's own value -- refused
by name (before `resolve` ever runs) when a declared name is absent from
the study, the same "refuse by name before anything runs" posture every
other axis refusal already has. Not built here: step 5 decides it, once a
cardiac record actually needs it.

## Step 4b (added 2026-09-25): the pilot, `restitutionCurves`

Done, verified in all four suite shapes plus the three static gates, all
0 failed (core-only venv, the installed wheel, `-m native` against the real
`noFrontendCardiacFoam_minor_errors` tutorials tree, and the rest).

| what | commits (omniD / native) |
|---|---|
| core: `mapping` value_kind for an axis whose own study value is a small parameter set | `3fdf9f5` |
| core: fix `commit_record_case` rendering into the case root itself (found running this pilot end to end against the real OpenFOAM renderer) | `86a110e` |
| cardiacfoam: single-cell stimulus amplitude migrated into the ionic model catalog, `STIMULUS_MAP` deleted | `986bede` |
| cardiacfoam: `restitutionCurves` tutorial record (`ionicModel`/`s1s2Protocol` axes), old factory tutorial deleted in the same commit | `46bd2f0` |
| native: `driver_config.json` rewritten as `setup/studies/tworldS1S2Restitution/sweep.json` | `38a451c4` |

**Every write the old `_plan_case` made, accounted for** (9 total, matching
§1's own 9/9 measurement): `tissue` is a direct study key; `ionicModel` and
`singleCellStimulus.stim_amplitude` come from the new `ionicModel` axis
(the amplitude from the ionic model catalog's migrated field);
`stim_period_S1`/`nstim1`/`stim_period_S2`/`nstim2`/`writeAfterTime`/
`system/controlDict:endTime` come from the new `s1s2Protocol` axis, whose
own study value is one mapping (`s1_interval_ms`/`n_s1`/`s2_interval_ms`/
`n_s2`) -- taken as a whole, not read back off the staged case, per §4's own
"an axis must not silently read case values the same study could also patch
directly." `electro_property_overrides`/`physics_property_overrides` were
always `None` by default (no write) and are simply gone.

**Workflow steps corrected against the real native `Allrun`**: `mesh`
(`blockMesh`) then `solve` (`cardiacFoam`) -- the old factory's DAG declared
`solve` only. `plotVoltage` is conditional (skipped by default via
`CF_SKIP_PLOTS`) and is not one of this record's steps either, matching what
`Allrun` actually runs by default.

**Parity** (before the old module was deleted, per this step's own
instruction): a scratch harness restored the old module's content from git
history (never committed), ran both paths over every case the new native
study expands to (TWorld, S1=1000ms/10 beats, S2 from 1500ms down to 250ms --
19 cases), and compared every flat key in `electroProperties` and
`controlDict` (both directions' key union, 779 keys total across all cases)
plus a byte-identical check on the untouched `blockMeshDict`. Zero
differences.

**The zero-changes design test (§6)**: `describe --entry restitutionCurves
--cases-root <native tutorials>` with no study values shows zero patches
against the real native case (`test_restitution_curves_record_native.py`,
`@pytest.mark.native`).

**Design gap found, not worked around (this step's own instruction)**: real
execution of a generic-case/tutorial-record `RunDocument` (`omnidriver run
--run-document ...`, `core/runtime/run_document_exec.py`) runs `validate_run`
unconditionally, with no `generic_case` exemption -- unlike
`run_document_adapter.py`'s planning-time skip, and contrary to that
module's own comment ("a generic case's all-empty config satisfies the
plugin schemas in-tree regardless"), which is false for cardiacFOAM's own
schema (`endTime`, `myocardiumSolver`, and others are `required`). This was
never caught before because no in-tree test ran a real, schema-enforcing
plugin's generic-case `RunDocument` through actual execution -- only through
planning, where the exemption already exists. It blocks `sweep-run`'s actual
solver launch for EVERY generic-case or tutorial-record entry today, not
only `restitutionCurves`; commit/staging themselves are unaffected (proven
correct via the native test and the parity check above). Left to the owner:
whether execution-time `validate_run` should gain the same exemption
planning-time already has, and how a `RunDocument` would carry that marker
forward (today it does not, per that module's own comment).

## Step 4c (added 2026-09-25): planning/execution agreement, and the pilot's real run

Done, verified in all four suite shapes plus the three static gates, all
0 failed (core-only venv, the installed wheel, `-m native` against the real
`noFrontendCardiacFoam_minor_errors` tutorials tree, and the rest), **plus**
a real, unmocked solver run of the `restitutionCurves` pilot.

**The fix, per the owner's rules (explicit, not inferred; one rule for both
paths; no fallback; no exemption heuristic).** `schemas/run-document.json`
gains a required, no-default `configurationSource` (`"document"` |
`"case"`) field. `core.runtime.configuration_source
.resolve_configuration_source` is the one function both
`run_document_adapter._run_document_from_case` (planning) and
`run_document_exec.build_execution_inputs` (execution) call to decide
whether `validate_run`/the plugin's declared config schema apply to a
document's `config`. Planning still reads `spec.metadata["generic_case"]`
(legitimately available only there) to SET the field to `"case"` for a
generic case or tutorial record, `"document"` otherwise; execution now
reads the field the document itself carries, rather than re-inferring
anything. The deleted `generic_case` boolean and the false "a generic
case's all-empty config satisfies the plugin schemas in-tree regardless"
comment are gone from both modules.

A `"case"`-sourced document whose `config` is not structurally empty (every
leaf absent -- a phase-shell of empty sub-dicts counts as empty; a real
value anywhere does not) is refused by name
(`case_configuration_source_carries_config`) at both planning and
execution -- an ingested, agent-authored document cannot declare `"case"`
to smuggle unvalidated document config past the plugin schema check, and
the existing plugin-identity gate applies regardless of source. A missing
or unrecognized source is refused by the schema itself (required, closed
enum, no default) and, independently, by
`resolve_configuration_source`'s own `unknown_configuration_source`
diagnostic for a `RunDocument` constructed in-process rather than loaded
from JSON.

**What validates a `"case"`-sourced document's case files.** Nothing new:
`validate_configuration` (the `ConfigurationValidatorCapability`) and the
record key validator (`RecordKeyValidationCapability`, step 4a) already ran
at plan/commit time, before this document was ever built -- execution runs
the workflow steps against an already-validated, already-committed case. No
execution-time case validator was invented in this step, per the owner's
instruction.

| what | commits |
|---|---|
| core: `configurationSource` field (schema + packaged copy), `RunDocument` dataclass, the shared `resolve_configuration_source` decision, both producers wired to it | `dbc9043` |
| openfoam: mechanical fix for `dict_builder`'s own synthetic `RunDocument` (forced by the new required field) | `06ceca8` |
| tests: `configurationSource` added to every existing `RunDocument` fixture across core/cardiacfoam/openfoam, plus the schema-level missing/unknown-source refusal tests | `0630cd1` |
| tests: configuration-source agreement across all three entry kinds (factory/generic-case/tutorial-record), the smuggling refusal, and the shared-function unit contract | `abd440c` |
| tests: a `native`+`slow` regression gate running `restitutionCurves` end to end through the real CLI, cardiacFoam binary, and OpenFOAM v2412 runtime | `106f71f` |

**The real run.** A scratch copy of the native tutorials tree (never the
native tree itself), narrowed to one case of the real
`tworldS1S2Restitution/sweep.json` study (TWorld, S1=1000ms x10 beats,
S2=1500ms x2 -- the sweep's own first point, unchanged) via a scratch
`scratch_sweep.json` alongside the native one, run through
`omnidriver --plugin cardiacfoam sweep-run --spec <scratch>/.../scratch_sweep.json
--output-dir <scratch>/out` (`--cases-root` is rejected by the CLI's own
argument validation for `sweep-run`/`sweep-plan` -- `cases_root` is instead
supplied inside the spec's own `base`, an absolute path to the scratch
tutorials copy). OpenFOAM v2412 and the native `cardiacFoam` build were
both found ambiently (`openfoam.openfoam_environment
.discover_openfoam_bashrc` -> `/Volumes/OpenFOAM-v2412/etc/bashrc`;
`cardiacFoam` from `$WM_PROJECT_USER_DIR`), exactly as a real developer
environment would supply them -- nothing scratch-supplied stood in for
either. The scratch copy's `system/blockMeshDict` was switched to the
tutorial's own smallest documented mesh alternative (40x6x14 = 3360 cells,
one of three resolutions the file already documents as commented-out
options, deltaX 0.5/0.2/0.1mm) instead of the checked-in default
(200x30x70 = 420000 cells), solely so the real solve finishes in seconds
rather than tens of minutes on this developer machine -- physics
(`deltaT`, ionic model, protocol timing) were left exactly as the real
study specifies.

Result: `workflow_state.status == "completed"`, both steps (`mesh`,
`solve`) `completed` with `exit_code 0`, in ~24-27s wall time (measured
across three runs, well inside the ~2 minute budget). The committed case's
`run_document.json` carries `"configurationSource": "case"` with the
expected empty phase-shell `config`
(`{"anatomy": {}, "physics": {}, "stimulus": {}, "solver": {}}`) -- exactly
the document shape that, before this step's fix, `run_document_exec` would
have refused outright with `plugin_config_schema_violation` (missing
`myocardiumSolver`, `endTime`, and the rest of cardiacFOAM's required
config fields). cardiacFoam's own real solver log shows `Time = 14` (the
protocol's derived `endTime`, `(1000*9 + 1500*2)/1000 + 2.0 = 14.0`) and
`ExecutionTime = 20.7 s`; its post-processing trace file
(`TWorld_epicardialCells_S1_1000_S2_1500.txt`) has 700001 lines of real
`[time Vm]` samples. The `native`+`slow` regression test above pins this
exact result (`workflow_state.status`, both steps' `exit_code`, the
committed document's `configurationSource`, and a non-trivial trace file)
so it does not silently regress.

No design gap was found this step -- the gap step 4b recorded is what this
step closes.

**Corrected 2026-09-25** (small follow-up): the real-run test's coarse mesh
used to come from a direct text edit of the scratch copy's `blockMeshDict`
(swapping which `hex (` line was commented) -- a case edit beside the
channel. It now comes from the study itself, via a new `blockMeshResolution`
axis (`openfoam.axes.block_mesh_resolution_axis`, given `value_kind=
"integer_list"` for the record's explicit `[40, 6, 14]`, no scaling formula
invented) named in the scratch study's `base`; the test no longer touches
any case file, and a native test pins the axis reporting the case's own
active resolution (read from the file) `unchanged`.

This follow-up also found (not worked around) two real defects this axis's
COMMIT path had never once exercised before (every prior use only
previewed a patch, or asserted it "unchanged" -- neither reaches
`patches_to_parameters`): (1) the axis's patch `value` was pre-joined text
(e.g. `"40 6 14"`), which no `VALUE_KINDS` member accepts (`word`/`enum`
both refuse embedded whitespace) -- fixed by having `resolve()` return the
validated typed tuple instead, deferring space-joining to the writer;
`cardiacfoam.record_key_validation._infer_unvalidated_value_kind` gained a
`list`/`tuple` branch (`integer_list`/`scalar_list`) to classify it, and
`apply_overrides._as_comparable_text` gained a branch parsing an
UNPARENTHESISED all-numeric multi-token string (the hex-cell-counts
convention) into a tuple, so "unchanged" detection still agrees. (2)
`cardiacfoam.overrides._target_for_parameter` had no case for
`case_planning.HEX_CELL_COUNTS_KEY_PATH` at all -- despite its own
docstring already describing one -- so a real commit would have built an
ordinary `update_foam_entry` target and literally SET a top-level
`hex_cell_counts` dictionary key instead of rewriting a `hex (` line; it
now special-cases that key path and reuses `plan_block_mesh_resolution`,
the "future writer" `block_mesh_resolution_axis`'s own docstring already
anticipated. All four suite shapes plus the three static gates are 0
failed with these fixes in place, and the real run reaches `completed`
with the committed `blockMeshDict`'s active `hex (` line reading
`(40 6 14)`.
