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

Sections: **R** was started by conformance Task 14 (P4); **G** by the tutorial plan's P5 (gmsh); **B** by step 5.4b-B (`manufacturedBidomain`). Merged 2026-09-26. **N** by step 5.4b-N (`niederer2011`); **E** by step 5.4b-E (`manufacturedEikonalECG`); **Q** by topic B Task 7 (the activation-probe reader), 2026-09-26. **X** by topic B Task 8 (openCARP against cardiacFOAM, the first cross-solver benchmark), 2026-09-26. **T** by the controller's TNNP integrator timing (owner question), 2026-09-26. **Y** by the Niederer campaign's 0.5 mm proof, 2026-09-27. Rows B11-B12, E4-E6 and N5-N6 were added by the review 54b fixes, 2026-09-26. Corrected 2026-09-26 (review 54b I4): this line did not name section E. **P** by PAR (niederer2011 in parallel), 2026-09-26. **BB** by step 5.4a (`manufacturedBathBidomain`), 2026-09-27. **S** by the controller's Niederer parameter and single-cell check (owner question: do both solvers solve the same problem?), 2026-09-27.

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

**Corrected 2026-09-26 (review 54b I2/I4).** B6 and B10 overstated what
they proved. Each passed one hand-built case per study straight to
`strict_plan`, which bypasses the study's own expansion, so "all 7
rewritten studies now `strict_plan` cleanly" was not shown: three of them
(`tetConvergence`, `tetTemporalControl`, `linearToleranceControl`, 16
cases) derived `caseId`/`output_dir_name` from
`system/fvSchemes:gradSchemes.default`, whose value is now `"Gauss
linear"`, and `sweep-plan` refused them ("caseId 'Gauss linear_10' is not
path-safe"). Native `c048ec1b`/`44037651` restored the path-safe
`gauss_linear`/`least_squares` names; B11 proves every study through its
own expansion. B10 also said "all 4 `corrector` cases": `corrector` has
**12** cases (`correctorN80` has 4), so B10 planned 4 of 16.

| # | command | observed | conclusion |
|---|---|---|---|
| B11 | `omnidriver --plugin cardiacfoam sweep-plan --spec tutorials/manufacturedSolutions/bidomain/setup/studies/<study>/<file>.json --output-dir <scratch>` from the native repository root, for each of the 7 studies; also `test_record_studies_native.py`, which does the same for every study of every record | 52 cases, every one `status: ok` (cartesianConvergence 12, corrector 12, correctorN80 4, linearToleranceControl 4, temporalConvergence 8, tetConvergence 8, tetTemporalControl 4). Against native `e5fdb3e1` (before `c048ec1b`) the same test fails naming exactly the three tet studies | the studies' own expansion is the proof; a hand-built case is not |
| B12 | the tet route through the record, no study values but the route: `plan --strict --entry manufacturedBidomain --config {"mesh": "tet"}`, then the advertised `run --run-document`, from native `44037651` | the gmsh command line carries no `-setnumber` (the record declares no `lc` default any more); gmsh `1184 nodes 6462 elements`, G7's count at the template's own `lc = 0.1`. rc 0, workflow `completed`; reconciliation 22 predicted, 22 matched, 0 missing; the 13 record-declared artifacts (`box.msh`, gmshToFoam's 10 `constant/polyMesh` entries, `.withDefaultValues`, `postProcessing/*_cells.dat`, here `3D_17_cells.dat`) all matched | "absent by default, added by an axis" holds: with no `tetNumberCells` the template's `DefineConstant` default applies. B3's nine-entry `gmshToFoam` output reproduced through the record |

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

| # | command | observed | conclusion |
|---|---|---|---|
| N5 | review 54b, from native `44037651`: `plan --strict --entry niederer2011 --config {"mesh": "tet"}` then the advertised `run --run-document` (no `tetDx`, so the template's own `lc = 0.0005`; native `endTime 0.015`) | gmsh command line with no `-setnumber`; `3739 nodes 20810 elements` (N4's count), `checkMesh` 16442 cells (Q4's). rc 0, workflow `completed`, 245 s; reconciliation 20 predicted, 20 matched, 0 missing; 17 record-declared artifacts matched, including gmshToFoam's `cellZones`, `faceZones`, `pointZones` and `sets/internal`. Final probe row `0.015 0.00119397 -1 -1 -1 0.008078 -1 -1 -1 -1` | N4 observed these four extra entries but the record declared only the hex six; they are declared now. The tet route is proved through the record, not only by hand |
| N6 | N5's case: `grep dimensions 0.015/activationTime` | `dimensions      [0 0 1 0 0 0 0];` | plan §5c 5.4b-N item 5 asked for `activationTime`'s `dimensions` from a run's field file, and this section did not record it (review 54b M10). Q2 had recorded the same line from the hex route, and the reader cites it: the probe values are seconds |
| N7 | native `0489be3c` (owner, from section T on `main` at `7e9f4ef`): `ionicModel TNNPcompactBatched; batchedIntegrator rushLarsen;`, `solver`/`maxSteps` deleted; then `regression/regressionTest.sh` (`Allrun parallel`, 6 ranks) in a `git archive` copy | PASSED 6/6 against the old reference in 31 s; `log.cardiacFoam` `Ionic Model : TNNPcompactBatched`; `.withDefaultValues` `batchedIntegrator rushLarsen;`. Probe values old -> new: col 2 `0.00119338` -> `0.00119338`, col 6 `0.0112286` -> `0.0112285` (1e-7 s), cols 4, 5, 9, 10 `-1` -> `-1`. The reference was regenerated from this run and passes `--check-only` 6/6 | the switch moves one probe by 0.1 microseconds, well inside the 1e-4 s tolerance. `solver`/`maxSteps` are unread for a batched model: `ionicModel::odeSolver()` builds OpenFOAM's `ODESolver` only when a scalar model calls it, and `TNNPBatched.C` never does. `equivalence_protocol.yaml`'s six Niederer rows are re-transcribed from the regenerated reference |

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
| E4 | review 54b, from native `44037651`: `plan --strict --entry manufacturedEikonalECG --config {"mesh": "<route>"}` then the advertised `run --run-document`, for each of `tet`, `tet-errorLocalisation`, `tet-gradientReconstruction` (the coarsest level: no `tetNumberCells`, so the template's `lc = 0.1`) | each: rc 0, workflow `completed`, ~80 s; reconciliation 20 predicted, 20 matched, 0 missing; 16 record-declared artifacts matched (`box.msh`, gmshToFoam's 10 `constant/polyMesh` entries including `cellZones`, `faceZones`, `pointZones` and `sets/internal`, and the 5 solve outputs); gmsh `1184 nodes 6462 elements` | E3's "the tet route produces the same declared artifact set as hex" was true of the solve step only: `gmshToFoam` writes the three zone files and `sets/internal` beside the hex six (as bidomain's B3 found), and `gmsh` writes `box.msh`, which `gmshToFoam` reads. Both are declared now |
| E5 | E4's three case trees, the files newer than the plan (`find -newer plan.json`, run records and logs excluded) | `tet` and `tet-gradientReconstruction` write the same 20 files; `tet-errorLocalisation` adds exactly `1/C`, `1/Cx`, `1/Cy`, `1/Cz` | `writeCellCentres` writes only into the latest time directory, which cannot be declared and is dropped at staging (the record's comment holds); `gradientReconstructionOrder` writes no file beyond its log, so it declares no `produces`. Both extra routes are now observed in a real run, not assumed |
| E6 | `plan --strict --entry manufacturedEikonalECG --config {"mesh": "tet", "dimension": "2D", "tetNumberCells": 10}`, before and after review 54b I3 | before: rc 0, `status: ok`, the `dimension` value silently unused. After: rc 1, `"tutorial record 'manufacturedEikonalECG''s workflow variant 'tet' admits 'dimension' only as one of ['3D'], or unset; 'base' sets it to '2D'"` | the old `make_spec` refusal (`mesh_family='tet' requires dimensions=['3D']`) is restored for every tet route |

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

## X. Cross-solver: openCARP against cardiacFOAM on the Niederer slab (topic B Task 8)

The benchmarker's step 3, run by
`packages/omnidriver-cardiacfoam/tests/test_niederer_cross_solver_native.py`
(markers `native` and `native_opencarp`), on 2026-09-26: one `sweep-run` per
solver, one pre-registered `omnidriver compare` request, the report attached
to both sweeps' experiments. **These numbers are evidence, not a reference.**
Neither solver is the truth here, and `benchmarks/niederer2011.json` is not
changed by them.

**Setup, pre-registered in `627e337` before either run was read.**
- Both solvers: dx 0.5 mm, time step 0.01 ms, 200 ms.
  - openCARP: `niedererNVersion`, `dx 500` µm, `nversion.par:dt 10` µs,
    `nversion.par:tend 200` ms, native `03E_study_resolution`.
  - cardiacFOAM: `niederer2011` (hex, cells (40 6 14)), `dx 0.0005` m,
    `system/controlDict:deltaT 1e-05` s (native), `endTime 0.2` s. This is
    the native `cartesianConvergence` study's own `endTime` for dx 0.5 mm.
    Native tree at `e5fdb3e1`.
- Orientation, from native files only:
  - cardiacFOAM's `constant/electroProperties` stimulus box runs from
    (0, 0, 5.5) mm to (1.5, 1.5, 7) mm, so the stimulus corner is
    (0, 0, 7) mm. With `system/blockMeshDict`'s 20 x 3 x 7 mm slab and
    fibres along x (the conductivity tensor), the reference frame is
    x = a, y = c, z = 7 mm - b. So probe k of `system/Niedererpoints` is
    P(k+1).
  - openCARP's `nversion.par` stimulus box starts at the origin, and its
    slab is the reference frame in µm (`opencarp.md` F3).
- Request:
  - tolerance: absolute, 5 ms;
  - `both_not_reached`: `fail`;
  - `max_sampling_offset`: 1 µm for openCARP (given as 0.001 mm) and
    0.0004331 m for cardiacFOAM (half a cell diagonal).
  - Digest in this run: `sha256:2ecfc1ec03116ab008aaa59e426418d6f4957560e7f43aea2f29c09c8446da42`.
    The request carries absolute run paths, so each run's digest differs.
- The two native cases describe the same tissue in their own terms:
  - both use TNNP epicardial cells;
  - conductivity: cardiacFOAM's monodomain (0.1334, 0.0176, 0.0176) S/m is
    the harmonic mean of openCARP's intra/extracellular `g_il 0.17`,
    `g_el 0.62`, `g_it 0.019`, `g_et 0.24`;
  - surface-to-volume ratio: `chi 140000` 1/m against `cellSurfVolRatio 0.14`
    1/µm;
  - both detect activation at a 0 mV upward crossing:
    `lats[0].threshold 0` for openCARP, `activationThreshold` default 0.0
    (Q2) for cardiacFOAM.
  - Stimulus strength and the time integrators are each solver's own.

**Runtimes (`workflow_state.json`).**

| run | time |
|---|---|
| openCARP `solve` | 9.6 s |
| cardiacFOAM `solve` | 399.8 s |
| the whole test (both sweeps, compare, the debug-cell check) | 416 s |

**Result.** The report's `status` is **`failed`**:
- 3 pairs are `within_tolerance` (P1, P3, P7);
- 6 are `outside_tolerance`;
- none are `not_reached` or `sampled_off_point`.

Both experiments associate the report as `run_verified`.

**What each side reports.**
- openCARP: every side has `declared_unit`/`unit` `ms`, rule `node`,
  `sampled_at_unit` `um` and offset 0, because every point is a slab node.
- cardiacFOAM: every side has `declared_unit` `s`, `unit` `ms`, rule
  `cell-containing` and `sampled_at_unit` `m`. Its `sampled_at` equals the
  solver's own containing-cell centre (the `-debug-switch probes=1` cell's
  `C`, as in Q3).

| pair | openCARP (ms) | openCARP sampled_at (µm) | offset (µm) | cardiacFOAM probe | cardiacFOAM (ms) | cardiacFOAM sampled_at (m) | expected (m) | offset (m) | difference (ms) | status |
|---|---|---|---|---|---|---|---|---|---|---|
| P1 | 1.253986 | (0, 0, 0) | 0 | 0 | 1.19496 | (0.00025, 0.00025, 0.00675) | (0, 0, 0.007) | 0.000433013 | 0.059 | within_tolerance |
| P2 | 113.347596 | (0, 7000, 0) | 0 | 1 | 132.315 | (0.00025, 0.00025, 0.00025) | (0, 0, 0) | 0.000433013 | 18.967 | outside_tolerance |
| P3 | 49.530603 | (20000, 0, 0) | 0 | 2 | 46.5183 | (0.01975, 0.00025, 0.00675) | (0.019999, 0, 0.007) | 0.000432436 | 3.012 | within_tolerance |
| P4 | 125.926870 | (20000, 7000, 0) | 0 | 3 | 142.155 | (0.01975, 0.00025, 0.00025) | (0.019999, 0, 0) | 0.000432436 | 16.228 | outside_tolerance |
| P5 | 26.765282 | (0, 0, 3000) | 0 | 4 | 35.9346 | (0.00025, 0.00275, 0.00675) | (0, 0.003, 0.007) | 0.000433013 | 9.169 | outside_tolerance |
| P6 | 114.232568 | (0, 7000, 3000) | 0 | 5 | 133.633 | (0.00025, 0.00275, 0.00025) | (0, 0.003, 0) | 0.000433013 | 19.400 | outside_tolerance |
| P7 | 55.807756 | (20000, 0, 3000) | 0 | 6 | 55.9661 | (0.01975, 0.00275, 0.00675) | (0.019999, 0.003, 0.007) | 0.000432436 | 0.158 | within_tolerance |
| P8 | 126.268283 | (20000, 7000, 3000) | 0 | 7 | 143.067 | (0.01975, 0.00275, 0.00025) | (0.019999, 0.003, 0) | 0.000432436 | 16.799 | outside_tolerance |
| P9 | 55.556030 | (10000, 3500, 1500) | 0 | 8 | 70.7206 | (0.00975, 0.00125, 0.00325) | (0.01, 0.0015, 0.0035) | 0.000433013 | 15.165 | outside_tolerance |

**What the numbers show, and what they do not.**
- **Where they agree.** The points reached from P1 along the fibres, or
  along the 3 mm edge and then the fibres, agree within 5 ms: P1, P3, P7.
- **Where they differ.** Every point that needs conduction across the 7 mm
  edge (P2, P4, P6, P8, P9) is 15 to 19 ms later in cardiacFOAM. P5, across
  the 3 mm edge, is 9 ms later.
- **The sampling offset does not explain the gap.** cardiacFOAM's cell
  centres sit 0.25 mm inside the slab on each axis, which moves the far
  corners *towards* the stimulus. That offset would make cardiacFOAM
  earlier there, not later.
- **What this does not settle.** This run cannot say which discretisation is
  closer to converged. The paper's P8 range at dx 0.1 mm (37.8–48.7 ms) is
  far below both values, as expected at dx 0.5 mm (`opencarp.md` G8: P8
  halves between dx 500 and dx 250 µm).
- **Reproducibility.** cardiacFOAM's nine values equal Q7's manual dx 0.5 mm
  run to every written digit.
- **The time step moves openCARP only a little.** openCARP's P8 at dt 10 µs
  (126.27 ms) is within 0.2 ms of G4's dt 50 µs value (126.45 ms).

## T. TNNP integration cost (owner question, 2026-09-26: why is cardiacFOAM slower than openCARP?)

Two `git archive` copies of the native `NiedererEtAl2011verification` (branch `omnid/tutorials-are-pointers`), each meshed with its own `blockMeshDict` `(100 15 35)` (Δx 0.2 mm, 52,500 cells). `endTime 0.01`, `deltaT 1e-05` (1,000 steps), serial, on the owner's workstation while other agents were running (load average ~7 on 14 cores).

| # | configuration | observed | conclusion |
|---|---|---|---|
| T1 | native: `ionicModel TNNP; solver RKF45; maxSteps 1000000000;`, `solutionAlgorithm implicit` | `ExecutionTime = 526.65 s` (bash-timed wall 530 s) | the native integrator is an adaptive RKF45 in every cell at every step |
| T2 | the same, with `ionicModel TNNPcompactBatched; batchedIntegrator rushLarsen;` | `ExecutionTime = 93.21 s` (wall 94 s); the log says `Ionic Model : TNNPcompactBatched` | **5.6x faster** |
| T3 | `Vm` at t = 0.01 s, T1 against T2, all 52,500 cells | the ranges match (−85.23 to 21.84 mV); max abs difference 5.9e-5 V (0.059 mV), mean 6.4e-7 V; 4,021 cells above 0 mV in both | the wavefront is identical at 10 ms. Most of cardiacFOAM's speed gap to openCARP (Task 8: 400 s against 9.6 s, both serial) is the cell-model integrator, not the finite-volume discretisation. openCARP's `tenTusscherPanfilov` uses Rush–Larsen with lookup tables |
| T4 | `/usr/bin/time cardiacFoam` | `dyld: Library not loaded: @rpath/libOpenFOAM.dylib` (rc 134) | a pitfall: `/usr/bin/time` is a system binary, and macOS strips `DYLD_*` for it. Time with the shell or with OpenFOAM's own `ExecutionTime` |
| T5 | `otool -L openCARP`; `openCARP +Help pstrat` / `parab_solve` / `ode_fac` | links PETSc, MPI, ParMETIS and METIS; no OpenMP or TBB runtime; `pstrat` 2 = KD-tree (default), 1 = ParMETIS, 0 = linear; `parab_solve` 1 = Crank–Nicolson (default); `ode_fac` = ODE solves per dt | openCARP parallelism is MPI only, with partitioning internal (no decomposition file); one rank is one core. For a fair performance comparison, use equal MPI ranks and one thread per rank |

## P. niederer2011 in parallel (PAR, owner Q6)

The record unchanged, driven through omniD's new parallel form (`openfoam
.parallel_execution.parallel_steps_for_record`), against the clean native tree
(`omnid-tutorials-are-pointers` worktree at native `44037651`), OpenFOAM v2412
sourced, `mpirun` = Homebrew Open MPI 5.0.9, which OpenFOAM is built against
(`WM_MPLIB=SYSTEMOPENMPI`, `MPI_ARCH_PATH=/opt/homebrew/Cellar/open-mpi/5.0.9`).
Runs staged in the session scratchpad and pytest's `tmp_path`.

| # | command | observed | conclusion |
|---|---|---|---|
| P1 | `describe --plugin cardiacfoam --entry niederer2011 --parallel` with `--config` setting `system/decomposeParDict:numberOfSubdomains: 2` (native: 6) | `record_preview.workflow_commands`: `mesh` `blockMesh`; `solve.decompose` `decomposePar -force`; `solve` `mpirun -np 2 cardiacFoam -parallel`; `solve.reconstruct` `reconstructPar`; then `samplePoints`, `writeCellCentres`, `samplePointCentres`, `sampleLines` unchanged. The patch is reported `validated: false` (OpenFOAM keys are written as asked, uncatalogued) | the preview reads N from the study's uncommitted value, not the native 6 |
| P2 | `sweep-run` of the record, dx 0.5 mm, `endTime 0.015`, `parallel: true`, `numberOfSubdomains: 2` | completed, every declared artifact matched, 46 s wall. `solve` log: `Exec : cardiacFoam -parallel`, `nProcs : 2`; the decompose log: `Processor 0`, `Processor 1`, 84 processor faces. The case holds `processor0/`, `processor1/` (each with `0.005 0.01 0.015 constant`), the reconstructed `0.005 0.01 0.015` at the root, and `constant/electroProperties.withDefaultValues` **at the root** (not in `processor*/constant`); `samplePoints`' row `0.015 0.00119496 -1 ...`, N3's serial value | a real two-rank run. `.withDefaultValues` stays where the serial record declares it, so the solve step's `produces` needs no parallel variant; the `postProcess -latestTime` steps read the reconstructed case |
| P3 | `test_parallel_native.py`: two sweeps started together, dx 0.5 mm, `endTime 0.15` (so all nine probes activate, Q7), one serial, one `parallel: true` with `numberOfSubdomains: 2` | both completed, 348 s for the pair. Serial solve `ExecutionTime = 340.48 s`, parallel `181.95 s`. Final `Niedererpoints` rows **identical as written** (`writePrecision 6`): `0.00119496 0.132315 0.0465183 0.142155 0.0359346 0.133633 0.0559661 0.143067 0.0707206`; `Niedererlines/0/activationTime` byte-identical (`cmp`); the reconstructed `0.15/Vm` and `0.15/activationTime` equal the serial ones in all 3360 cells | serial and parallel agree to the precision the case writes. The test's tolerance, 1e-9 s, was fixed before the first comparison and is below that precision, so it requires the written values to be equal. A 1.9x speed-up on two ranks at this size |


## Y. The Niederer campaign's 0.5 mm proof (2026-09-27)

`benchmarks/niederer2011/campaign/`, run with `campaign.sh proof` exactly
as its README says: serial `level` runs of both solvers at dx 0.5 mm, then
`perf` runs at dx 0.5 mm and dt 0.05 ms on 1 and 2 ranks, then the seven
0.5 mm requests pre-registered in `82746b8`. Native tree
`omnid-tutorials-are-pointers` at `0489be3c`, clean before and after.
OpenFOAM v2412; openCARP v18.1 with its bundled MPICH first on PATH and
`HYDRA_IFACE=lo0`. Whole proof 473 s wall, while another agent's native
suite was running. **These numbers are evidence, not a reference.**

**Configuration.**
- cardiacFOAM: the native case and its native `cartesianConvergence`
  rows at dx 0.0005 m, unchanged: `TNNPcompactBatched` with `rushLarsen`,
  `implicit`, `endTime 0.2`.
- openCARP: `niedererNVersion` with `nversion.par:mass_lumping 0`, the full
  mass matrix of openCARP's own `run.py` (`opencarp.md` G10), dx 500 µm,
  tend 200 ms.

| # | request | status | largest difference |
|---|---|---|---|
| Y1 | `cross_dx0.5_dt0.05` | `failed`: P1 within 5 ms, eight pairs outside | P6 86.70 ms |
| Y2 | `cross_dx0.5_dt0.01` | `failed`: the same pattern | P6 85.94 ms |
| Y3 | `cross_dx0.5_dt0.005` | `failed`: the same pattern | P6 85.83 ms |
| Y4 | `temporal_cardiacfoam_dx0.5_dt0.05_vs_dt0.01` | `passed` (1 ms) | P8 0.869 ms |
| Y5 | `temporal_cardiacfoam_dx0.5_dt0.01_vs_dt0.005` | `passed` | P8 0.129 ms |
| Y6 | `temporal_opencarp_dx0.5_dt0.05_vs_dt0.01` | `passed` | P4 0.693 ms |
| Y7 | `temporal_opencarp_dx0.5_dt0.01_vs_dt0.005` | `passed` | P4 0.094 ms |

Every report is associated `run_verified` with both of its cases.

**Activation times at dt 0.005 ms (ms; Y3):**

| point | openCARP | cardiacFOAM | difference |
|---|---|---|---|
| P1 | 1.241 | 1.192 | 0.049 |
| P2 | 47.354 | 132.193 | 84.839 |
| P3 | 32.884 | 46.543 | 13.659 |
| P4 | 57.960 | 142.004 | 84.044 |
| P5 | 11.506 | 35.900 | 24.394 |
| P6 | 47.678 | 133.508 | 85.830 |
| P7 | 33.801 | 55.912 | 22.111 |
| P8 | 58.051 | 142.914 | 84.863 |
| P9 | 24.848 | 70.637 | 45.789 |

**What they show.**
- **The time step barely matters at dx 0.5 mm, for both solvers**, as the
  owner expected. The largest move between successive steps is under
  0.9 ms, and under 0.13 ms from 0.01 to 0.005 ms. cardiacFOAM's
  0.05-to-0.01 ms move, 0.87 ms at P8, is the closest to the 1 ms bar.
- **The solvers disagree by far more than Task 8 showed.** Task 8 saw
  15-19 ms at the far points (section X), but its openCARP was lumped
  (`opencarp.md` G10). With the full mass matrix, openCARP's P8 at dx
  0.5 mm is 58 ms, against cardiacFOAM's 143 ms.
- **cardiacFOAM's values are unchanged from Task 8** at dt 0.01 ms
  (P8 143.043 against X's 143.067, with the batched integrator in place of
  RKF45). The difference comes from openCARP's mass matrix, not from
  cardiacFOAM.
- **Neither is converged at dx 0.5 mm.** The paper's P8 is 37.8-48.7 ms at
  dx 0.1 mm. The finer levels are the cluster's job.

**Serial against parallel (dx 0.5 mm, dt 0.05 ms, 4,000 steps; wall
seconds from `workflow_state.json`):**

| solver | ranks | solve | decompose + reconstruct | values against serial |
|---|---|---|---|---|
| cardiacFOAM | 1 | 22.4 | — | — |
| cardiacFOAM | 2 | 13.3 | 2.8 | final `Niedererpoints` row identical as written |
| openCARP | 1 | 3.5 | — | — |
| openCARP | 2 | 3.1 | — | LAT file differs by at most 1e-6 ms (the last printed digit, as PAR's I7) |

cardiacFOAM's solve is 1.7x faster on 2 ranks (1.4x counting the
decomposition). openCARP's is too small to scale here. The parallel run
documents carry `resolvedEntry.parallel` (`{"requested": true}` for
cardiacFOAM, `{"requested": 2}` for openCARP, `allocation` null outside a
scheduler), and the solve steps read `mpirun -np 2 ...`. The cardiacFOAM
log reads `nProcs : 2`.

## BB. manufacturedBathBidomain (`manufacturedSolutions/bathBidomain`, plan 5.4a)

Every run used a `git archive HEAD tutorials/manufacturedSolutions/bathBidomain`
copy of native `omnid/bath` (based on `e5fdb3e1`), OpenFOAM v2412 sourced, gmsh
`/opt/homebrew/bin/gmsh`. Each step's outputs were listed by hashing every
file before and after the step.

| # | command | observed | conclusion |
|---|---|---|---|
| BB1 | the native hex route, serially, on the case as committed: `blockMesh -dict system/blockMeshDict.1D`, `topoSet`, `setTorsoOrganConductivityField`, `cardiacFoam` | all rc 0. blockMesh: `constant/polyMesh/{boundary,faces,neighbour,owner,points}`. topoSet: `constant/polyMesh/cellZones` and `sets/{bath,bathCells,myocardium,myocardiumCells}`. setTorsoOrganConductivityField: creates `0/` (the case has none) holding only `0/bodyAndOrgansConductivity` ("Assigned cells: 240 / 240"). cardiacFoam (1.2 s, 357 steps): `constant/electroProperties.withDefaultValues`, `postProcessing/1D_80_cells.dat`, and the time directories. It accepts the case's `writeControl adjustableRunTime` | each hex step's `produces`. `0` itself must be declared beside the field, or a restage carries the empty directory (C11 said so on the first run: "carried ... ['0']"). The summary is `<dim>_<N>_cells.dat`, with no `bathBidomain_` prefix (native `7ae47527c`) |
| BB2 | the tet route on a copy with `dimension "3D"`, `endTime 0.02`: `gmsh -3 setup/studies/tetConvergence/three_domain_box.geo.template -o three_domain_box.msh -format msh2 -setnumber lc 0.1`, `gmshToFoam three_domain_box.msh`, `checkMesh`, `setTorsoOrganConductivityField`, `cardiacFoam`, `bathBidomainInterfaceMetrics -latestTime` | all rc 0. gmsh: `three_domain_box.msh` only. gmshToFoam: `constant/polyMesh/{boundary,cellZones,faceZones,faces,neighbour,owner,pointZones,points}` and `sets/{bath,myocardium}`. checkMesh: nothing. setTorsoOrganConductivityField: `0/bodyAndOrgansConductivity`. cardiacFoam (2.7 s): `.withDefaultValues` and `postProcessing/3D_17_cells.dat`. bathBidomainInterfaceMetrics: `postProcessing/bathBidomainInterfaceMetrics.csv` (a second run changed no file) | each tet step's `produces`. No `topoSet` on this route: the template's two Physical Volumes are the two cellZones |
| BB3 | the native `phiERefPoint (-0.9 0.05 0.05)` under the native `electrodePair`, one step of cardiacFoam at 1D N=10 and 80, 2D N=10/20/40/80 and 3D N=10/20/40 (each blockMeshDict's three blocks set to that N, keeping a direction at 1 at 1) | rc 0 and no `FATAL` at every one; each wrote its `<dim>_<N>_cells.dat` | the native point works serially at every hex resolution the electrodePair studies use, except 3D N=80 (1.5 M cells, not run). It is not in a cell interior: x = -0.9 is a cell face at every N that is a multiple of 10, and in 2D z = 0.05 is the domain's top face. `findCell` still returns one cell serially; a parallel run is where two partitions can both claim it (the old module's reason for its half-cell shift, owner Q5) |
| BB4 | `update_foam_entry` on a copy of the real `constant/electroProperties`: `surfaceCurrentPatches = {"xMax": 0.01}`, `groundPatches = {"xMin": 0}` (scope `bidomainSolverCoeffs.bathPotentialDomain`) | `surfaceCurrentPatches` now holds `xMax 0.01` only (the native `xMin -0.01` is gone), and `groundPatches` holds `xMin 0`. The rewritten block headers gain extra indentation, which OpenFOAM ignores | the writer **replaces** a sub-dictionary rather than merging (owner Q4's condition), so no removal kind is needed |
| BB5 | the same `groundElectrode` keys through the record: `sweep-plan` of `coupling/sweep_coupling_study.json`, then a real `sweep-run` of `{"dimension": "2D", "numberCells": 10, "system/controlDict:endTime": 0.02}` plus the three keys | the staged file is BB4's; the run completes, every declared artifact `matched`, and `2D_10_cells.dat` reports `# fdaBathVariant groundElectrode` | the whole-map study key works end to end. `record_key_validation` checks each member against `bathPotentialDomain.groundPatches.<patch>` / `surfaceCurrentPatches.<patch>` (a scalar) |
| BB6 | `strict_plan` of the old factory on any bath case | refused: `'adjustableRunTime' is not one of ['runTime', 'timeStep', 'clockTime', 'cpuTime']` (field `writeControl`) | the catalogue listed four of OpenFOAM's seven `Foam::Time::writeControlNames` (v2412 `src/OpenFOAM/db/Time/Time.C`: `none`, `timeStep`, `runTime`, `adjustable`, `adjustableRunTime`, `clockTime`, `cpuTime`). Corrected in `common_dict_entries`; BB1's real run accepts the value |
| BB7 | parity: `sweep-plan` of all 14 old studies through the old factory (on a copy with the pre-`60805b27` template and the byte-identical overlay restored), and of the 14 rewritten studies through the record; every case compared document by document (parsed with foamlib, `yes`/`true` and numbers normalised) | 70 cases, identical case ids. `electroProperties`, `controlDict`, `fvSchemes`, `fvSolution` and the selected `blockMeshDict.<dim>` agree in every case; gmsh's `lc` equals the old rendered `lc` in all 26 tet cases. Differences: `phiERefPoint` in 16 cases (the electrodePair 2D, 3D and tet cases, old half-cell shift vs the native point), and the two unselected `blockMeshDict.<dim>` files, which `numberCells` also writes | no case value is lost. `phiERefPoint` does not enter the error norms: the verifier compares zero-mean potentials under `electrodePair` (`manufacturedFDABathBidomainVerifier.C`) |
| BB8 | one real tet run through the record (`test_manufactured_bath_bidomain_tet_native.py`): `{"mesh": "tet", "dimension": "3D", "system/controlDict:endTime": 0.02, "tetNumberCells": 10}` | completes; every declared artifact is found; `3D_*_cells.dat` and `bathBidomainInterfaceMetrics.csv` written | the tet route is proved through the record, not only declared |

## S. Is it the same problem? Niederer parameters and the single cell (2026-09-27)

Owner question: before the full grid is read, do openCARP and cardiacFOAM
solve the same Niederer 2011 problem, and is the 0.5 mm gap at P8 (58.14 ms
against 143.04 ms, section Y) the model or the mesh? cardiacFOAM read from
native `omnid/tutorials-are-pointers` (`git show` / `git archive`); openCARP
from `/usr/local/lib/opencarp/share/tutorials`. Its probes are in
[`opencarp.md`](opencarp.md) J. Runs: the controller's scratch
`niederer-singlecell/` (`oc/`, `cf/`, `cable/`, `slab/`).

**Verdict.** Every tissue parameter matches the paper, within 0.01 %. The cell
model does not: cardiacFOAM runs TNNP **2004**, openCARP the **2006** model the
paper specifies. That costs about 1 ms at a converged P8. The 85 ms gap at
0.5 mm is the discretisation: coarse finite volumes behave like openCARP with
a lumped mass matrix.

| quantity | paper | openCARP (where) | cardiacFOAM (where) | status |
|---|---|---|---|---|
| ionic model | ten Tusscher–Panfilov 2006, epi | `imp_region[0].im tenTusscherPanfilov` (`nversion.par`); `limpet/models/tenTusscherPanfilov.model` has the 2006 structure and constants | `ionicModel TNNPcompactBatched`, which is TNNP 2004 (`src/ionicModels/TNNPBatched/TNNP_2004Batch.H`, `TNNP/TNNP_2004.H`): 17 states, g_Kr 0.096, g_Ks 0.245, g_CaL 1.75e-4 | **mismatch**. Neither solver offers the other's version |
| cell type | epi | `im_param "flags=EPI"` | `tissue epicardialCells` → flag 1 (`ionicSelector::tissueFlag`) | match, within each model |
| initial state | — | `-imp_region[0].im_sv_init singlecell.sv` (Vm −85.23 mV) | Vm −84.0 mV everywhere: the `myocardiumDomain` constructor's default (`-0.084` V), since the case has no `0/Vm`; it overrides the model's −86.2 mV for every ionic model | **mismatch** (S5) |
| cell integration | — | Rush–Larsen gates, forward Euler concentrations, lookup tables | `rushLarsen` on 10 gates, forward Euler on the rest, one ODE solve per step | same family |
| PDE time scheme | — | `parab_solve 1`, Crank–Nicolson | `backward` (BDF2), `implicit`, `godunov` | differ; both Δt-converged (Y) |
| Cm | 1 µF/cm² | fixed `Cm = 1.0` (`electrics.cc`) | `cm 0.01` F/m² | match |
| χ | 140 mm⁻¹ | `cellSurfVolRatio 0.14` µm⁻¹, `volFrac 1` | `chi 140000` m⁻¹ | match |
| σ (monodomain) | harmonic mean of σi (0.17, 0.019) and σe (0.62, 0.24) S/m | `g_il/g_it/g_el/g_et`; `bidm_eqv_mono` 1 takes the harmonic mean per direction (`electric_integrators.cc`) | `conductivity` given as (0.1334177215, 0.01760617761, 0.01760617761) S/m | match (1e-10) |
| fibres, frame | long axis, 20×7×3 mm | along x; x, y, z = 20, 7, 3 mm | along x; x, y, z = 20, 3, 7 mm (exact, since σt = σn) | match |
| stimulus strength | 50,000 µA/cm³ | `35.71` µA/cm² × 1400 cm⁻¹ = 49,994 µA/cm³ | `stimulusIntensity 50000` A/m³ | match (0.01 %) |
| stimulus duration | 2 ms | 2 ms | `updateExternalStimulusCurrent` includes the end time: one extra step (2.01 ms at Δt 0.01 ms) | minor |
| stimulus volume | 1.5 mm cube | the 64 nodes in the closed box, reaching 1.75 mm | the 27 cells whose centres are inside, exactly (1.5 mm)³ | minor; moves P1 only (1.25 vs 1.19 ms, X) |
| activation | 0 mV, upward | `lats threshold 0` | `activationThreshold 0` | match |

| # | probe | observed | conclusion |
|---|---|---|---|
| S1 | read `TNNP_2004Batch.H`, `TNNP_2004.H` | 17 states, 2004 constants (`TNNPinitConsts`) | `TNNPcompactBatched` is TNNP 2004, not the benchmark's 2006 model |
| S2 | the Niederer case for 3 steps with `debug (Vm)` | log `Vm=-84`; `0.0001/Vm` −0.0840222 V | the tissue starts at −84 mV, the domain default |
| S3 | native `singleCell` copy: `TNNPcompactBatched`, `rushLarsen`, `epicardialCells`, `stim_start 10; stim_duration 2; stim_amplitude 35.7142857; nstim1 1`, `endTime 0.51`, `deltaT 5e-06`; `blockMesh; cardiacFoam` | Vrest −85.58 mV (drifting from −86.2), peak 53.1 mV, max dV/dt 351 mV/ms, 0 mV at 1.244 ms after onset, APD90 274.5 ms | against openCARP 2006 (J1): the upstroke agrees within 0.02 ms (shared I_Na and I_K1); repolarisation differs (max trace gap 32 mV at 287.6 ms, APD90 15 ms shorter) |
| S4 | 15 mm cables, Δt 0.01 ms, dx 10, 50, 500 µm | along fibres 0.5972, 0.5935, 0.4105 m/s; across 0.2169, 0.2068, blocked | at 10 µm, 1.7 % (along) and 2.2 % (across) slower than openCARP full mass (J3): the model's effect, about +1 ms at a converged P8. At 500 µm, along −29 % and across blocked, like openCARP lumped (J3) |
| S5 | dx 0.5 mm slab, native and with `0/Vm` −0.08523 V | P8 143.043 and 143.651 ms | the initial state moves P8 by 0.6 ms |

Owner decisions, 2026-09-28: TNNP 2004 is intended for this benchmark, and the
−84 mV domain default stays for now. A single-cell initialization will come
later as its own native implementation.

## SC. singleCell (`electrophysiologyProtocols/singleCell`, plan 5.1)

Every run used a `git archive HEAD tutorials/electrophysiologyProtocols
/singleCell` copy of native `omnid/single-cell` (based on `853ff09e`),
OpenFOAM v2412 sourced. Each step's outputs were listed by hashing every
file before and after the step.

| # | command | observed | conclusion |
|---|---|---|---|
| SC1 | the native route, serially, on the case as committed: `blockMesh`, `cardiacFoam` (native default `endTime 2`, `deltaT 1e-6` -- 2,000,000 steps) | both rc 0. blockMesh: the standard `constant/polyMesh/{boundary,faces,neighbour,owner,points}` (and the directory itself). cardiacFoam (~24-26 s wall clock): `postProcessing/TWorld_endocardialCells_S1_1000.txt` and `..._S1_1000_Ta.txt` (the native case's own `activeTensionModel LandNiedererTWorld` also writes a second trace). No `constant/electroProperties.withDefaultValues`, no `0/` directory | each step's `produces`/`consumes`; `singleCellSolver::end` overrides `electroModel::end` without calling it, the same as `restitutionCurves` (R4) |
| SC2 | the record's `ionicModel` axis, swept `{"ionicModel": ["TNNP", "BuenoOrovio"]}` at a shortened `endTime 0.05`, native `tissue`/`activeTensionModel` otherwise untouched | `TNNP` completes (rc 0). `BuenoOrovio` aborts: `FOAM FATAL ERROR: Active tension model requires signal 'Cai' but provider does not supply it` (`activeTensionModel::validateProvider`), a 1-byte trace file | a native-case quirk, not a record defect: the case's own `activeTensionModel LandNiedererTWorld` is a fixed global default the `ionicModel` axis (unchanged from `restitutionCurves`, whose own case sets no `activeTensionModel` at all) was never asked to touch, and BuenoOrovio's ionic model does not export a `Cai` signal that model needs. `TWorld` (the native default) and `TNNP` both supply it and were used for C7 instead. A study that wants to sweep an ionic model incompatible with the native `activeTensionModel` must also clear or replace it directly (a direct `singleCellSolverCoeffs.activeTensionModel` key removal is untested here) |
| SC3 | the two committed native studies (`setup/sweep_ionic_model_tissue.json`, `setup/studies/tworldVsGaur/sweep_tworld_vs_gaur.json`), read against the ionic model catalog | all 24 distinct `ionic_model` values in the full sweep carry a catalogued `single_cell_stimulus_amplitude` (the `ionicModel` axis's own requirement); the old Python-vocabulary base keys `stim_start_ms`/`n_s1`/`end_time_buffer_s`/`write_after_time_s` in `sweep_tworld_vs_gaur.json`'s `base` matched no keyword of the deleted factory's own `make_spec` either -- already dead before this rewrite | both studies rewrite cleanly onto `ionicModel` plus direct `document:key` literals (`tissue`, `stim_period_S1`, `outputVariables.ionic.export`); the four dead base keys are dropped, not carried forward |
| SC4 | `setup/driver_config.json` (`{"ionic_models": ["Stewart"]}`) | named no key any current path reads (the same fate `restitutionCurves`'s own `driver_config.json` already met) | deleted natively, not migrated |
