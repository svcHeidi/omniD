# Learning cardiacFOAM: the evidence log

**Method:** [`method.md`](method.md). **Plan it feeds:**
`docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §1
("a claim about what the solver or a tool does is settled by a real run").
**Machine:** macOS arm64, the owner's workstation; OpenFOAM v2412
(`/Volumes/OpenFOAM-v2412`), cardiacFoam built into the user platform
directory. **Started:** 2026-09-26, by conformance Task 14.

Every entry records the command and what it printed (abridged). The native
tree is a `git archive` of the native feature branch's committed files (plan
§4, "a clean native tree"), never the owner's checkout. Runs happen in
scratch copies.

Sections: **R** was started by conformance Task 14 (P4); **G** by the tutorial plan's P5 (gmsh); **B** by step 5.4b-B (`manufacturedBidomain`). Merged 2026-09-26. **N** by step 5.4b-N (`niederer2011`); **Q** by topic B Task 7 (the activation-probe reader), 2026-09-26.

## R. restitutionCurves (`electrophysiologyProtocols/restitutionCurves_s1s2Protocol`)

| # | command | observed | conclusion |
|---|---|---|---|
| R1 | `strict_plan("restitutionCurves", {"blockMeshResolution": [40, 6, 14]})`, then `omnidriver run --run-document` (the path conformance C5/C6 take), in a sourced shell | rc 0, 12.9 s. Added to the staged case: `constant/polyMesh/{boundary,faces,neighbour,owner,points}`, `postProcessing/BuenoOrovio_epicardialCells_S1_2000_S2_250.txt`, and core's own `workflow_state.json`, `case_record.json`, `workflow_logs/*`, `.omnidriver-attempt.lock.guard`. Nothing else, and nothing removed | `blockMesh` produces `constant/polyMesh`; `cardiacFoam` produces one trace in `postProcessing/`. The solve log ends `Results written to: ".../postProcessing/BuenoOrovio_epicardialCells_S1_2000_S2_250.txt"` |
| R2 | `singleCellSolver`'s constructor (`src/electroModels/myocardiumModels/singleCellSolver/singleCellSolver.C`) and `stimulusIO::protocolSuffix` (`src/genericWriter/stimulusIO.C`) | the name is `<ionicModel type>_<tissue>_<protocolSuffix>[_<constant-override suffix>].txt`, where the suffix is `noStim`, `S1_<s1>` or `S1_<s1>_S2_<s2>` | the trace name depends on study values (step 4c's run wrote `TWorld_epicardialCells_S1_1000_S2_1500.txt`), so a record declares it as `postProcessing/*.txt` |
| R3 | in a copy of the native case (plus R1's mesh for `cardiacFoam`), remove one file, run `blockMesh -case <copy>` or `cardiacFoam -case <copy>` | `blockMesh`: fatal without `system/blockMeshDict` or `system/controlDict`; rc 0 without any other file. `cardiacFoam`: `cannot find file` without `system/controlDict`, `system/fvSchemes`, `system/fvSolution`, `constant/electroProperties` or `constant/physicsProperties`; rc 0 without `constant/sweepCurrents` or `system/blockMeshDict` | these are the two steps' authored `consumes`. `constant/sweepCurrents` is read by neither; `grep` finds it only in `applications/utilities/sweepCurrents` and `src/genericWriter/ionicModelIO.C` |
| R4 | `ls constant/` after R1 and after every rc-0 run of R3 | `electroProperties physicsProperties polyMesh sweepCurrents`: no `electroProperties.withDefaultValues` | `singleCellSolver::end()` overrides `electroModel::end()` (which renames and writes `.withDefaultValues`) and does not call it. **A single-cell record does not produce `.withDefaultValues`**; plan §2 item 1's "every cardiacFoam solve step produces it" does not hold here. `singleCellSolver` is the only myocardium solver under `src/electroModels/myocardiumModels/` that overrides `end()` (`grep '::end'`), so by source the rule holds for the others; the owner's checkout shows the file after in-place runs of eikonalECG, pseudo-ECG and Niederer (plan §4's table). Each of those records settles it by its own run |

## G. gmsh and the `.geo.template` tet route (P5)

| # | command | observed | conclusion |
|---|---|---|---|
| G1 | `which gmsh`; `gmsh --version` | `/opt/homebrew/bin/gmsh`; `4.15.2` | the binary the tet route calls |
| G2 | `gmsh -3 box.geo.template -o m.msh` (bidomain's committed template, `setup/studies/tetConvergence/box.geo.template`) | exit 0, but `Error : 'box.geo.template', line 21: Unknown variable '__LC__'`, then `Wrong mesh element size lc = 0`; a 1421-byte `.msh` | **gmsh parses a file with the unknown extension `.geo.template` as a `.geo` script** (the error is a parse of its line 21). Exit 0 despite the errors: exit status alone cannot tell a good mesh from a failed one |
| G3 | as G2 with `-setnumber lc 0.2` and `-setnumber lc 0.1` | the same `Unknown variable '__LC__'` error and the same 1421-byte `.msh` for every value | `-setnumber` does nothing to these templates |
| G4 | `grep -nE '__[A-Z_]+__\|DefineConstant\|^\s*lc\s*=' <every *.geo* in the export>` | all five templates (bidomain, eikonalECG, monodomainPseudoECG `box.geo.template`; bathBidomain `three_domain_box.geo.template`; NiedererEtAl2011verification `slab.geo.template`) write `lc = __LC__;`. None uses `DefineConstant` | the native templates are **text-substitution templates**. Today the substitution is omniD Python: `omnidriver-openfoam`'s `tet_mesh_provisioning` (`_LC_PLACEHOLDER`) and `niederer_2011.py`'s `_apply_case`, both slated for deletion by the migration |
| G5 | a copy of G2's template with line 21 replaced by `DefineConstant[ lc = {0.25, Name "lc"} ];`; `gmsh -3` with no flag, then `-setnumber lc 0.2`, then `0.1` | 0 errors each; `143 nodes 704 elements`, `237 nodes 1203 elements`, `1184 nodes 6462 elements` | **`-setnumber lc v` overrides `DefineConstant[ lc = … ]`**, and the `DefineConstant` value is the default when the flag is absent |
| G6 | the templates' own comments | bidomain: "`__LC__` is substituted by run_corrector_study.sh"; bath: "replaced by setup/run_mesh_gate.sh"; Niederer: "substituted by niederer_2011.py's `_apply_case`" | the named scripts are not in the native tree (`find` finds neither); the comments are stale |

**Consequence for the 5.4 records (owner decision, not settled here).** Both P5
facts hold for gmsh itself, but they apply to the native templates only if the
templates declare `lc` with `DefineConstant`. There are two options:
- change the five native templates to `DefineConstant[ lc = {<default>, Name "lc"} ]`,
  after which a record's mesh step is `gmsh -3 <template> -setnumber lc <value>`
  with no rendered file, and the substitution code is deleted;
- or keep `__LC__` and have each record render a `.geo` file through the case
  write channel, which collides with the OpenFOAM layer's
  `generated_file_suffixes` (`.geo` is dropped at staging and git-ignored natively).

The first is the minimum-code route, and the native case stays the pointer.

**Owner decision (2026-09-26, plan §5g Q2/Q3/Q7/Q8), executed.** The first
option: all five native templates were converted to
`DefineConstant[ lc = {<default>, Name "lc"} ]`, native commit `60805b27`
(worktree `omnid-tutorials-are-pointers`, branch `omnid/tutorials-are-pointers`).
Defaults are each study's own coarsest tet level (§5c's mapping,
confirmed by reading each study's `sweep_tet_*.json`): coarsest
`number_cells` is `10` for bidomain, eikonalECG and monodomainPseudoECG's
`box.geo.template` and for bathBidomain's `three_domain_box.geo.template`
(`sweep_tet_electrodePair.json`'s `number_cells: [10, 20, 40]` is coarser
than `sweep_tet_generic.json`'s `[80]`), giving `lc = 1/10 = 0.1`; coarsest
`dx_values` for `NiedererEtAl2011verification/slab.geo.template` is `0.5`
mm `= 0.0005` m.

| # | command | observed | conclusion |
|---|---|---|---|
| G7 | `gmsh -3 <template> -o a.msh -format msh2` at each template's new default, in a `git stash create` export of the worktree (uncommitted templates at the time), gmsh 4.15.2 | 0 errors for all five: bidomain/eikonalECG/monodomainPseudoECG `1184 nodes 6462 elements`; bathBidomain `3304 nodes 18996 elements`; Niederer `3739 nodes 20810 elements` | every template's `DefineConstant` default parses and meshes cleanly with no flag given |
| G8 | as G7 with `-setnumber lc <finer>` (`0.05` for the four box/bath templates, `0.0002` m for Niederer) | 0 errors for all five: bidomain/eikonalECG/monodomainPseudoECG `7408 nodes 42954 elements`; bathBidomain `21243 nodes 127148 elements`; Niederer `45154 nodes 267666 elements` | `-setnumber lc <value>` overrides the default and refines the mesh as expected, matching G5's finding on this repo's actual five templates (not a copy) |
| G9 | `gmsh -3 <template> -o /tmp/x.msh -format msh2 2>&1 \| grep -ci error` for all five, post-conversion | `0` for every template | confirms 0 parse errors by exact count, not by eyeballing the tail of the log |

## B. manufacturedBidomain (`manufacturedSolutions/bidomain`, step 5.4b-B)

Every run below used a `git archive HEAD tutorials/manufacturedSolutions/bidomain`
copy (never the native worktree itself), OpenFOAM v2412 sourced.

| # | command | observed | conclusion |
|---|---|---|---|
| B1 | `blockMesh -dict system/blockMeshDict.3D` at the committed `(20 20 20)`, then again after editing to `(5 5 5)` | rc 0 both times; `constant/polyMesh/{boundary,faces,neighbour,owner,points}` only, no zones | identical to `restitutionCurves`'s own hex mesh outputs (single, zone-free `hex (` block) -- the `mesh` step's `produces` |
| B2 | `cardiacFoam` after B1's `(5 5 5)` mesh | rc 0, ~0.07 s. New: `constant/electroProperties.withDefaultValues`, `postProcessing/3D_5_cells.dat`, and time directories `0.1`/`0.2` (dropped as instances) | bidomainSolver does NOT override `electroModel::end()` (only `singleCellSolver` does, R4), so `.withDefaultValues` IS produced here -- the `solve` step declares it. The verifier's output name is `<dim>_<N>_cells.dat` with `N` the resolved per-direction count (5, not the committed 20), confirming a literal path cannot be declared |
| B3 | `gmsh -3 setup/studies/tetConvergence/box.geo.template -o box.msh -format msh2 -setnumber lc 0.2`, then `gmshToFoam box.msh`, then `checkMesh` | gmsh: rc 0, `237 nodes 1203 elements`. gmshToFoam: rc 0, warns "Found 398 undefined faces ... adding to default patch defaultFaces", writes `constant/polyMesh/{boundary,cellZones,faceZones,faces,neighbour,owner,pointZones,points,sets/internal}` (one cellZone/cellSet `internal`, from the template's single `Physical Volume("internal")`). checkMesh (no `-writeAllFields`): rc 0, "Mesh OK", writes nothing but its own log | the tet route's `gmsh`/`gmshToFoam`/`checkMesh` steps' `produces`, exactly as declared on the record. `-setnumber lc` trailing every other flag (`-o ... -format msh2 -setnumber lc 0.2`) works identically to leading it (re-run at `lc 0.3` gave a different mesh, `143 nodes 706 elements`) -- the record's own `argv()` always appends an axis's contribution after every kept default, so this order had to be checked |
| B4 | `cardiacFoam` on B3's tet mesh | rc 0, ~0.12 s. Same two new files as B2: `.withDefaultValues` and `postProcessing/3D_9_cells.dat` | confirms B2's conclusion holds for the tet route too |
| B5 | direct `omnidriver.openfoam.mutators.update_foam_entry`/`read_foam_entry` against a copy of this case's own `system/fvSolution` | reading the quoted-regex key `solvers."phiE|phiEFinal|phiI|phiIFinal".tolerance` (scope `["solvers", '"phiE|phiEFinal|phiI|phiIFinal"']`) returns `1e-15`; writing `1e-06` to it succeeds and reads back correctly. Writing `1` to `PIMPLE.nNonOrthogonalCorrectors` (absent from this file) with `add_if_missing=False` (the tutorial-record direct-key channel's only mode -- `case_write.ParameterAssignment.operation` defaults to `"set"`, and neither `AxisPatch` nor `patches_to_parameters` carries any per-patch override) raises `KeyError`; the same write with `add_if_missing=True` (what the OLD factory code passed explicitly for this exact key) succeeds | plan §2 item 3's quoted-key question is settled: `sort_study_name`'s dotted-path split and the OpenFOAM reader/writer both handle a quoted segment correctly, proven directly, not assumed. `PIMPLE.nNonOrthogonalCorrectors` is a real gap: a tutorial-record study cannot add a key its native document lacks. Confirmed again end to end through `strict_plan` against the real `corrector`/`correctorN80` studies (all cases, `nNonOrthogonalCorrectors` 0 or 1 alike) -- every one raises the same `KeyError` at plan time, not merely at commit time |
| B6 | `strict_plan("manufacturedBidomain", overrides=<one case from each rewritten study>)` for all 7 rewritten studies | `cartesianConvergence`, `temporalConvergence`, `linearToleranceControl`, `tetConvergence` and `tetTemporalControl` all plan `status="ok"` with no refusal. `corrector` and `correctorN80` both raise the B5 `KeyError` for every case (the `PIMPLE.nNonOrthogonalCorrectors` gap, not a rewrite mistake) | 5 of 7 rewritten studies preview/plan cleanly; the remaining 2 are blocked on a real, confirmed core-adjacent gap, not on anything this migration could rewrite around |
| B7 | `record_key_validator("system/fvSchemes", ("gradSchemes","default"), "Gauss linear")` before/after a `record_key_validation.py` fix | before: `_infer_unvalidated_value_kind` returned `"word"` for any `str`, including a whitespace-containing one, which `"word"`'s own shape check then refuses ("must contain no whitespace") -- so a direct study key naming `system/fvSchemes:gradSchemes.default = "Gauss linear"` was refused before ever reaching the OpenFOAM writer (which `test_foam_backend.py::test_update_entry_writes_bare_multiword_scheme_spec` already proves writes such a value correctly). After: a whitespace-containing `str` infers `"string"` (K6), fixing it | a real defect this tutorial's `grad_scheme`-carrying studies (`linearToleranceControl`, `tetConvergence`, `tetTemporalControl`) exposed; fixed in `omnidriver-cardiacfoam` (an adapter package, not core), following the same "Corrected" pattern this file already used once for `block_mesh_resolution_axis`'s tuple/list value |
| B8 | writing `bidomainSolverCoeffs.dimension = "1D"` (bare, unquoted) through the record channel | `case writer (ValueError): cannot write value '1D' to 'dimension': invalid string: '1D'` (`foamlib`'s own tokenizer: an unquoted `1D` parses as a malformed number, not a word). Pre-quoting the value (`'"1D"'`, literal quote characters -- the old factory code's own `f'"{dimension}"'` convention) writes and reads back correctly | the `dimension` axis's patch value must carry its own quotes; `value_kind="word"`'s shape check (`"1D"'`, no whitespace) is unaffected by the extra quote characters |

**Corrected 2026-09-26 (controller decision, same day as B5/B6): fix it
natively, not in core.** B5/B6 read `PIMPLE.nNonOrthogonalCorrectors`'s
absence as a core-adjacent gap in the write channel. The controller's own
read of the same facts: the native case should state the key its studies
change, and the write channel's `add_if_missing=False` is *correct* -- a
study changes keys that exist, and never invents one. Rows B9-B10 are that
fix, checked directly, not the channel.

| # | command | observed | conclusion |
|---|---|---|---|
| B9 | `regression/regressionTest.sh`, full `Allrun parallel` + real `cardiacFoam`, in two separate `git archive` copies of native `omnid/54b-bidomain`: one at `5f5692c7` (before), one at `b8ad4ee6` (after adding `nNonOrthogonalCorrectors 0;` to `system/fvSolution`'s `PIMPLE` block, with the OpenFOAM v2412 `solutionControl.C`/cardiacFoam `extracellularPotentialDomain.C` default-0 evidence cited in the file itself) | both runs: `23 checks, 0 failures`, `Regression test PASSED`; `diff` of the two full logs is empty (byte-identical) | stating the native default explicitly changes nothing: the fix is behaviour-neutral, proven, not assumed |
| B10 | `strict_plan("manufacturedBidomain", ...)` for all 4 `corrector` cases and all 4 `correctorN80` cases (the same cases B6 found refused), then a real `run --run-document` of `corrector`'s coarsest case (`tetNumberCells=10`, `nOuterCorrectors=1`, `nNonOrthogonalCorrectors=0`) | every one of the 8 cases now plans `status="ok"`. The real run: rc 0, `status="ok"`, every declared artifact `"matched"` (`record.gmsh.0`, the 9 `record.gmshToFoam.*` mesh entries, `record.solve.0`/`.1`, `verification_error_summary`, the `bidomain_*_series` traces) | B5/B6's gap is closed by the native fix alone; no core or `omnidriver-cardiacfoam` write-channel change was needed. All 7 rewritten studies now `strict_plan` cleanly (was 5 of 7) |

Native commits for B9/B10: `b8ad4ee6` (the `fvSolution` fix),
`b203f347` (README corrections to `corrector`/`correctorN80`, reversing
their own B5/B6-era "open gap" notes).

Native commits: `60805b27` (the five templates), `6eb12863` (Q11,
`ecgDomains.ECG.verificationModel.anisotropic yes` in
`monodomainPseudoECG/constant/electroProperties`), `03f02dec` (Q9, drops
bidomain's unapplied `ode_abs_tolerance`/`ode_rel_tolerance` from all 7
studies plus the `temporalConvergence` README), `9cb1213e` + `72038987`
(Q10, deletes the four byte-identical tet overlays and corrects their
case READMEs).

**Q11 regression outcome.** `regression/regressionTest.sh` (`Allrun
parallel`, 6-way `scotch` decomposition, real `cardiacFoam`) against a
`git stash create` export with `anisotropic yes`: **PASSED, 16/16 checks,
0 failures.** Every value in `regression/monodomainPseudoECG.reference`
(cell count, final time, the tissue `Vm`/`u1`/`u2` L1/L2/Linf error
metrics, and the raw `pseudoECG.dat` E1-E5 final samples) matched to
within its existing tolerance (differences of order `1e-10`-`1e-12`,
floating-point noise from a fresh run, not from the flag). The reference
does not compare `manufacturedPseudoECGSummary_ECG.dat`'s error/delta
columns, which are the ones the `anisotropic` flag actually changes (its
internal-accuracy-checking reference branch) -- so the committed
reference is unaffected and was not regenerated. Old vs new: unchanged
(same file, same values, before and after the flag flip, by design of
what the reference actually checks).

## N. niederer2011 (`NiedererEtAl2011verification`)

| # | command | observed | conclusion |
|---|---|---|---|
| N1 | manual, in a `git archive` scratch copy: `blockMesh` (hex block edited to `(40 6 14)`, dx 0.5 mm), then `cardiacFoam`, in a sourced shell, native `system/controlDict` unchanged (`endTime 0.015`, `deltaT 1e-05`) | rc 0 both, cardiacFoam ~50 s. After `cardiacFoam` alone: `constant/electroProperties.withDefaultValues` exists; `postProcessing/Niedererpoints/0/activationTime` exists with **3** data rows (`0.005`, `0.01`, `0.015`, all under the one instance `0`) plus a 9-probe/1-header preamble (13 lines total); `postProcessing/Niedererlines/0/activationTime` likewise, 3 rows under `0`, 101-probe preamble (105 lines total) | `monodomainSolver` calls `electroModel::end()`, so the solve step writes `.withDefaultValues` (unlike `restitutionCurves`'s `singleCellSolver`, R4) -- declared on `solve`. The `Niederer{points,lines}` function objects (`writeControl writeTime`) write every write time into ONE instance directory, `0` (never `0.005/`, `0.01/`, `0.015/`) -- OpenFOAM's own instance numbering restarts at the case's `startTime` for a function object's own output tree, not at wall/solve time |
| N2 | same scratch copy, then `postProcess -func Niedererpoints -latestTime`, then `-func Niedererlines -latestTime` | rc 0 both. No new directory created (still only `postProcessing/{Niedererpoints,Niedererlines}/0/`). Each file is **replaced**, not appended to: `Niedererpoints/0/activationTime` drops from 3 data rows to exactly **1** (`0.015`, the probes' own header lines unchanged, 11 lines total); `Niedererlines/0/activationTime` likewise, 1 row, 103 lines total | confirms plan §5c item 2's own archived-run evidence exactly: **the `samplePoints`/`sampleLines` steps write LAST**, each producing exactly one data row at the run's `endTime`, at the literal path `postProcessing/Niederer{points,lines}/0/activationTime` -- these are declared as the first (only) `produces` entry of each of those two steps, as plain paths (no format: no reader exists yet, topic B Task 7's own job) |
| N3 | `column 2` (probe 0) of N2's `Niedererpoints/0/activationTime` | `0.00119496` at `dx=0.5 mm`, native reference `0.00119338` at the case's own default resolution (dx 0.2 mm, `(100 15 35)`) | expected: coarser mesh, small but real difference -- not a byte-identical check, this run only settles which step/path/row-count, not the reference numbers themselves (those are equivalence_protocol.yaml's own, transcribed verbatim from `regression/NiedererEtAl2011.reference`, §5d) |
| N4 | manual gmsh tet route in a second scratch copy: `gmsh -3 setup/studies/tetConvergence/slab.geo.template -o slab.msh -format msh2 -setnumber lc 0.0005`, then `gmshToFoam slab.msh`, then `checkMesh` | all rc 0. gmsh: `3739 nodes 20810 elements` (matches P5's G7 at the template's own default). `gmshToFoam`: writes `constant/polyMesh/{boundary,cellZones,faces,faceZones,neighbour,owner,pointZones,points,sets/}` (a superset of the hex route's own polyMesh files) plus "Found 4120 undefined faces... adding to default patch defaultFaces". `checkMesh`: `Mesh OK` (max aspect ratio 8.46, max skewness 0.74, non-orthogonality OK) | confirms the tet route's own commands and declared `produces`/`consumes` (`gmsh` consumes the template, produces `slab.msh`; `gmshToFoam` consumes `slab.msh`, produces the same core `constant/polyMesh/*` set the hex `mesh` step declares; `checkMesh` writes nothing declared, only validates) |

**Column numbering** (settled here, for topic B Task 7's own reader and
`test_a_probe_never_reached_is_not_reached`): `regressionTest.sh`'s `awk`
`col` indexes the data line's whitespace-split fields, 1-based, with field 1
the time column -- so `variable "2"` is probe 0 (the first `probeLocations`
entry), `variable "10"` is probe 8 (the ninth and last). At `dx=0.5 mm`
(this section's own coarse proof mesh) N2 found every probe but probe 0
still at `-1` at `t=0.015` -- slower, coarser-mesh conduction than the
committed reference's own default resolution (`dx=0.2 mm`, `(100 15 35)`),
which is expected and not a discrepancy this run is trying to resolve (N3).
The committed `equivalence_protocol.yaml` rows (`variable`s `2`, `4`, `5`,
`6`, `9`, `10`, i.e. probes 0, 2, 3, 4, 7 and 8) are transcribed verbatim
from `regression/NiedererEtAl2011.reference` (§5d), not re-derived from
this coarse run -- probes 2, 3, 7 and 8 (`variable`s `4`, `5`, `9`, `10`)
are the reference's own `-1.0` entries, and this run's own
observation (every non-zero probe still `-1` at this coarser resolution)
is consistent with, though not a proof of, that same set never having
activated by `t=0.015` at the reference's finer resolution either.

## E. manufacturedEikonalECG (`manufacturedSolutions/eikonalECG`, plan 5.4b-E)

Real runs against a `git archive` export of `omnid/54b-eikonalECG` at
`72038987` (before this task's own study-rewrite commit), resolution
shrunk to `10x10x10` (the coarsest any study defines) for a fast run,
`source /Volumes/OpenFOAM-v2412/etc/bashrc`.

| # | command | observed | conclusion |
|---|---|---|---|
| E1 | `blockMesh -dict system/blockMeshDict.3D` then `cardiacFoam`, serial (`Allrun`'s own default: no `parallel` argument) | rc 0 both, 13 s total. `ls constant/` after: `electroProperties electroProperties.withDefaultValues physicsProperties polyMesh`. `find postProcessing`: `eikonalECG.dat`, `manufacturedEikonalActivationTime.dat`, `manufacturedEikonalECGSummary_ECG.dat`, `manufacturedEikonalECG_ECG.dat` | unlike `restitutionCurves`'s `singleCellSolver` (R4), `eikonalMyocardiumDomain`'s solve DOES write `.withDefaultValues` -- it does not override `electroModel::end()` without calling it. The four `postProcessing` names are exactly the ones the brief predicted from the C++, confirmed by a real run rather than assumed |
| E2 | remove `0/activationTime` from a copy of E1's already-meshed case, run `cardiacFoam` | `FOAM FATAL ERROR: cannot find file .../0/activationTime`, rc 1 | `0/activationTime` is a real `consumes` entry for the `solve` step, the same way R3 established the pattern for `restitutionCurves` |
| E3 | `gmsh -3 setup/studies/tetConvergence/box.geo.template -o box.msh -format msh2` (template already has `DefineConstant[ lc = {0.1, Name "lc"} ]`, native `60805b27`), then `gmshToFoam box.msh`, then `checkMesh`, then `cardiacFoam` | gmsh: `1184 nodes 6462 elements`, matching G7 exactly. `checkMesh`: `Mesh OK`, no extra files written. `cardiacFoam`: rc 0, `ls constant/`/`find postProcessing` identical in NAME to E1 (`.withDefaultValues` plus the same four `postProcessing/*.dat`) | the tet route produces the same declared artifact set as hex; `checkMesh` itself writes nothing beyond its own log, so its workflow step declares no `produces` |

Native commit for this task: `db896dd0` (rewrites the six studies to
`document:key` vocabulary; no template/case-content change was needed here,
since `60805b27`/`9cb1213e` had already landed the gmsh `DefineConstant`
conversion and the tet `fvSolution` overlay deletion this task's brief
assumed).

**A record-key-validator defect this task's own studies exposed, fixed in
omniD (not native):** `record_key_validation._infer_unvalidated_value_kind`
used to tag every plain `str` `"word"`, including one containing
whitespace -- but `"word"`'s own shape check refuses whitespace, so a
whitespace-containing string reaching a real `ParameterAssignment` (e.g.
`system/fvSchemes:gradSchemes.default` = `"Gauss linear"`, `errorLocalisation`/
`gradientVerification`/`tetConvergence`'s own `grad_scheme` values) failed at
commit time with "declares value_kind 'word' but its value does not fit".
Never exercised before this task: every prior `system/`-owned string value
committed through the write channel happened to be a single token
(`"leastSquares"`, `"corrected"`, ...). Now returns `"string"` (K6) for a
value that does not fit `"word"`'s own contract, `"word"` unchanged
otherwise -- confirmed by staging all 60 cases the six rewritten studies
expand to with no refusal, and by inspecting a representative case per
study (`constant/electroProperties`'s `conductivity`/
`eikonalAdvectionDiffusionApproach`, `system/fvSchemes`'s `gradSchemes.default`,
`system/fvSolution`'s `PIMPLE.residualControl.activationTime.tolerance`) against
the old module's own literals.

## Q. The activation-time probes as quantities (topic B Task 7)

Every run below used a `git archive` of native `a02902ee`
(`tutorials/NiedererEtAl2011verification`) under the session scratchpad,
OpenFOAM v2412 sourced, except Q8, which is omniD's own `sweep-run`. The
hex mesh is `(40 6 14)` (dx 0.5 mm) unless stated.

| # | command | observed | conclusion |
|---|---|---|---|
| Q1 | `blockMesh`, `cardiacFoam` (native `endTime 0.015`), `postProcess -func Niedererpoints -latestTime`; `cat postProcessing/Niedererpoints/0/activationTime` | 9 lines `# Probe <k> (<x> <y> <z>)` repeating `system/Niedererpoints`' `probeLocations` exactly as configured (`# Probe 2 (0.019999 0 0.007)`), one `# Time 0 1 ... 8` line, one data row `0.015 0.00119496 -1 -1 -1 -1 -1 -1 -1 -1` | the header echoes the agent's input, not a sampled location. Never-activated is spelled `-1`. After `-latestTime` the one row is the final time (N2), so the last row is the value |
| Q2 | `sed -n 17,22p 0.015/activationTime`; `myocardiumDomain.C` (native `src/electroModels/electroDomains/myocardiumDomain/`) | `dimensions [0 0 1 0 0 0 0];`. The field is built as `dimensionedScalar("unactivated", dimTime, -1.0)`; `updateActivationTime` sets `oldTime + w*deltaT` wherever `Vm` crosses `activationThreshold` upward (`lookupOrDefault("activationThreshold", 0.0)`), with no guard on an already-set value | unit **seconds**, sentinel **-1**, both from the solver itself. Two facts for later readers: the threshold is an `electroProperties` key this reader does not report (the brief's deferred M9), and a second upward crossing would overwrite the first, so the value is the *last* crossing, which equals Niederer's "first" only while each cell activates once (true for this single-stimulus case) |
| Q3 | `src/sampling/probes/probes.C` (v2412): `prepare`, `findElements`, `read`; `probesTemplates.C`: `sample` | the header prints `operator[](probei)`, the configured point. `findElements` calls `mesh.findCell(location)`; `samplePointScheme_` defaults to `"cell"`, so `sample` returns the containing cell's value. The cell index is printed only under `debug` (`Pout << "probes : found point ... in cell ..."`), never to the file | option (a) (the solver reports the cell) exists only as a debug log line. Then, in Q1's case: `postProcess -func Niedererpoints -latestTime -debug-switch probes=1` printed cells `3120 0 3159 39 3320 200 3359 239 1539`; `postProcess -func writeCellCentres -latestTime` wrote `0.015/{C,Cx,Cy,Cz}`; `postProcess -func 'Niedererpoints(Cx,Cy,Cz)' -latestTime` wrote `postProcessing/Niedererpoints(Cx,Cy,Cz)/0/{Cx,Cy,Cz}`, same header, one row. For all nine probes `(Cx, Cy, Cz)` equals `0.015/C` at the debug cell exactly, e.g. probe 0 `(0.00025 0.00025 0.00675)`, probe 8 `(0.00975 0.00125 0.00325)`. Probe 8 `(0.01 0.0015 0.0035)` lies on a vertex shared by 8 cells, and OpenFOAM chose cell 1539: a nearest-centre rule (option c) cannot settle that tie, only OpenFOAM's own search can. **Method chosen: probe the cell-centre components with the same function** (option b) |
| Q4 | tet route in a second copy: `gmsh -3 setup/studies/tetConvergence/slab.geo.template -o slab.msh -format msh2 -setnumber lc 0.0005`, `gmshToFoam slab.msh`, `cardiacFoam` (`endTime 0.005`), then Q3's three `postProcess` calls | 16442 cells. Debug cells `15569 15574 15735 15716 15571 15572 15729 15732 11835`; the probed `(Cx, Cy, Cz)` equals `0.005/C` at each, to all six written digits (probe 0 `(0.000182376 0.000182376 0.00681699)`, probe 8 `(0.010088 0.00149746 0.00351858)`) | the method holds on tets too, exact to the case's `writePrecision 6` (both files are written at it). On the hex route the centres are exact in 6 digits; on tets they are rounded there (about 1e-9 m) |
| Q5 | Q1's case: `postProcess -func 'Niedererpoints(C)' -latestTime` | `postProcessing/Niedererpoints(C)/0/C`, each column `(x y z)` | a vector probe file writes parenthesised values; the scalar parser refuses it by name |
| Q6 | Q1's case: `postProcess -func 'Niedererpoints(Cx,probeLocations=((1 1 1) (0 0 0)))' -latestTime` | log: `Did not find location (1 1 1) in any cell. Skipping location.` File `postProcessing/Niedererpoints(Cx,probeLocations=((111)(000)))/0/Cx`: `# Probe 0 (1 1 1)  # Not Found`, value `-1e+300` (-VGREAT); probe 1 `0.00025` | an unfound probe is a number in the file, not a statement; the header flag is what says so, and the reader refuses such a probe by name. The output directory is the whole `-func` argument with whitespace removed (`word::validate`) |
| Q7 | dx 1 mm (`(20 3 7)`) and dx 0.5 mm copies, `endTime 0.2`, `cardiacFoam`, `postProcess -func Niedererpoints -latestTime` | solve 73 s (dx 1 mm) and 396 s (dx 0.5 mm), run concurrently. Final rows, probes 0-8, in s: dx 1 mm `0.00119552 -1 0.0855099 -1 -1 -1 -1 -1 -1`; dx 0.5 mm `0.00119496 0.132315 0.0465183 0.142155 0.0359346 0.133633 0.0559661 0.143067 0.0707206` | picks the self-comparison's `endTime` 0.1 before any comparison was run: by then P1 and P3 (probes 0, 2) are reached at both resolutions, P5, P7, P9 at dx 0.5 mm only, the rest at neither. At dx 1 mm only the probes on the stimulus face along the fibre activate by 0.2 s (the 3-cell-thick direction does not conduct at this resolution) |
| Q8 | `omnidriver sweep-run` of the record at dx 0.5 mm, `endTime 0.015` (`test_activation_probes_native.py`, OMNIDRIVER_NATIVE_TUTORIALS at native `a02902ee`) | the record's `samplePoints`, `writeCellCentres` and `samplePointCentres` steps write the declared files; each is byte-identical to Q1/Q3's manual output, and the debug-cell check of Q3 passes on the staged case | the record reproduces the manual evidence; the committed unit-test fixtures are that output, gated by this test |
