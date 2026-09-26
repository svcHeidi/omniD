# Learning cardiacFOAM's toolchain: the evidence log

**Method:** [`method.md`](method.md). **Design it feeds:**
`docs/superpowers/plans/2026-09-25-tutorials-are-pointers-remaining.md` §5e P5
(the tet-mesh route of the 5.4 records).
**Machine:** macOS arm64, the owner's workstation. **Started:** 2026-09-26.

Every entry records the command and what it printed (abridged). Native files
are read from a `git archive` export of the native repo's
`feature/spring-supported-slab-tutorial` (the committed files only, no in-place
run output), never from the working checkout.

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
