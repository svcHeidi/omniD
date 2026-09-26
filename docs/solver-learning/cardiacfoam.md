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

Sections: **R** was started by conformance Task 14 (P4); **G** by the tutorial plan's P5 (gmsh). Merged 2026-09-26.

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
