# Tutorials are pointers: the remaining work, and the rules for doing it

**Date:** 2026-09-25 · **Design:** [`../specs/2026-09-24-tutorials-are-pointers-design.md`](../specs/2026-09-24-tutorials-are-pointers-design.md)
(approved; its own Status section records steps 1–5.0 in detail).

This plan is the tracker for everything after step 5.0. It runs in parallel with
the openCARP work (`../specs/2026-09-25-solver-conformance-and-opencarp-design.md`,
on `main`). Together the two answer one question: **is the core general?** The
tutorials test whether core can express cardiacFOAM's real cases without
cardiacFOAM leaking in; openCARP tests whether core works for a solver that is
not OpenFOAM at all.

> **Revised 2026-09-26, before the next agent starts 5.4.** The plan's executing
> agent stopped after step 5.0 and the merge. Since then `main` gained topic A
> (`2026-09-26-core-generality.md`), topic B Tasks 1–6
> (`2026-09-26-results-as-quantities.md`), the openCARP conformance work's
> close-out and a catalogue re-sync with the native C++. The native repo moved
> too: the Niederer case left `NiedererEtAl2011/`, and the owner deleted two
> dead native keys. This revision corrects every claim that no longer holds.
> Each correction is dated. Nothing below was measured from memory; every
> number was taken at `2046cc9` and against the native repo at `c15e2fcf`.
> What changed:
> - the Status table (below);
> - §1 names the three owner rules it assumed but did not state;
> - §2's recipe is restated for the current APIs;
> - §4 has a native-base rule and a clean-native-tree rule;
> - §5a's facts are corrected inline;
> - there are new sections: §5b (5.4a as tasks), §5c (5.4b as tasks, one per tutorial), §5d (the stale Niederer references), §5e (order and parallelism), §5f (conformance Tasks 14–15) and §5g (owner questions).
>
> **Naming (2026-09-26, owner).** The Niederer tutorial is `niederer2011`
> throughout this plan. The benchmark is Niederer et al. 2011, and the native
> case folder is `NiedererEtAl2011verification`. A parallel agent is renaming
> `niederer2012` to `niederer2011` on `main` (worktree `rename-niederer2011`),
> and it does not edit this file. Where this plan's older text says
> `niederer2012`, read `niederer2011`.

## Status

| step | what | state | commits |
|---|---|---|---|
| 1–5.0 | design, deletion of heartSolverComparison, core records/axes/channel/gate, blockMesh axis, the restitutionCurves pilot, P1/P2 | done (see the design's Status) | up to `0cf5bfb` |
| M | merge into `main` (§4) | done 2026-09-25: `main` fast-forwarded to this branch (local; push pending the owner's go-ahead) | see `git log main` |
| 5.4a | manufacturedBathBidomain (hardest first; see §5a) | next | — |
| 5.4b | manufacturedBidomain, manufacturedMonodomainPseudoECG, manufacturedEikonalECG, niederer2012 | not started; pseudo-ECG also waits on the owner's uncommitted `box.geo.template` and six temporal sweeps | — |
| 5.1 | singleCell | not started | — |
| 5.2 | cable1DRestitution (post-processing reads the case plus omniD's case record; both sidecars deleted) | not started | — |
| 5.3 | cable1DCVConvergence (its study states its own `externalStimulus`) | not started | — |
| 5.5 | manufacturedPurkinjeGraph, manufacturedMonodomain1D3D | blocked: need file placement (future scope) | — |
| — | manufacturedMonodomainTotalLagrangianEM | deferred until electromechanics | — |
| C | final cleanup (§3) and G3 close-out | not started | — |

**Corrected 2026-09-26 (plan revision).** The table above is kept as written
on 2026-09-25. This one replaces it, built from `git log 0cf5bfb..2046cc9`
and the native repo's own log:

| step | what | state | commits |
|---|---|---|---|
| 1–5.0 | as above | done | up to `0cf5bfb` |
| M | merge into `main` | done. **Pushed**: `origin/main` is `2046cc9` | — |
| A | topic A, core generality. What it changed for tutorials: `environment_source`/`--environment-source` (A1); `{instance}`/`instance_indexed` (A2a); `replica_directory_globs` (A2b); `input_roots(case_root, resolved_case, *, conventions)` (A2c); the four dictionary members made optional (A3); `CORE_RUNTIME_RECORDS`, and record staging excluding each step's `produces` (A5, plus R1 I2: intermediates stay excluded), conformance C11; the mesh-scale exemption only through cardiacFOAM's hook and `physics_layout.json` (A7); `selected_start_time` following `Foam::Time::setControls` | done | `03b0727`, `17f2906`, `95797a9`, `7bc7777`, `1983749`, `64eb550`, `ca5a394`, `9cf5485`, `bf55217`, `8abb187`, `ea6237c`; the full list is in that plan's Status |
| K | cardiacFOAM dictionary catalogue re-synced with the native C++: `gradientAxes` catalogued, removed keys deleted, waivers, `supports_gradient_axis_heterogeneity`; then the `manufacturedBidomain`/`manufacturedEikonalECG` waivers dropped after native `c15e2fcf` | done | `a0eb381`, `3ad3d43`, `f6ef43f`, `2046cc9` |
| B | topic B, results as quantities, Tasks 1–6: `ProducedPath`, `core.quantities`, `omnidriver compare`, conformance C12, `benchmarks/niederer2011.json`, openCARP's LAT reader. **Tasks 7–8 are blocked on this plan's 5.4b-N** (§5c) | done | `26a8da6`, `3f16fe8`, `13ba8b6`, `5259160`, `767f70a`, `422d549`, `ff6331e`, `5a0778e`, `04a1093`, `9923621` |
| O | solver conformance and openCARP, Tasks 1–13 and the final-review fixes. **Tasks 14–15 are open**; §5f says when each unblocks | done | `5efd986` … `cadbe17`, `2182f76`, `45e4ce5`, `7e4e4b9` |
| N | native, owner: `7a04349b` moved `NiedererEtAl2011/NiedererEtAl2011verification` to `NiedererEtAl2011verification` and replaced the EM case with `electromechanicsProtocols/springSupportedSlab`; `c15e2fcf` deleted the `manufacturedBidomain` pass-through and the `manufacturedEikonalECG` alias. Both are on native `feature/spring-supported-slab-tutorial`, **not** on native `main`, and **not** on this plan's native branch `omnid/tutorials-are-pointers` (`38a451c4`, based on `dbc0ec6b`) | done natively; integrating it into the native branch is §5e P1 | native `7a04349b`, `c15e2fcf` |
| R | rename `niederer2012` → `niederer2011` in omniD | in progress (parallel agent) | — |
| P | prerequisites for 5.4 (§5e, P1–P5) | not started | — |
| 5.4a | manufacturedBathBidomain, as tasks in §5b | next after P1–P3 | — |
| 5.4b | manufacturedBidomain, manufacturedMonodomainPseudoECG, manufacturedEikonalECG, **niederer2011**, as tasks in §5c. **Corrected 2026-09-26:** pseudo-ECG is **not** blocked on the owner. `setup/studies/tetConvergence/box.geo.template` is committed natively (`21f7bc82e`, 2026-08-18, last touched `a72870bee`, 2026-09-21), as are bidomain's and eikonalECG's `box.geo.template` and bath's `three_domain_box.geo.template`. The six `sweep_temporal_*.json` were untracked exploratory files that no committed file referenced. They were deleted from the owner's working tree at 14:04 today, and only a copy under the git-ignored `tutorialsTest-regression/` survives. The committed temporal study is `sweep_temporal_convergence.json` with its README | not started | — |
| 5.1–5.3, 5.5, TL-EM | unchanged from the table above | — | — |
| C | final cleanup (§3); also where conformance Task 14's "delete the old factory path" lands | not started | — |
| P4 | conformance Task 14, all four steps: `restitutionCurves` passes C1–C12 against the real binary (added 2026-09-26). Branch `tut-p4`, not merged | done on the branch | `8acbce2`, `36c99c1`, `0e736f8`, `a6e79e2`, `a982d6c` |
| P3 | core record additions (§5g answered): `TutorialRecord.default_variant` (Q2); replaceable default arguments on `WorkflowStep` (Q3/Q7); `reads_also` not built (Q5); Q6 investigated, not built (answer and smallest change in `.superpowers/sdd/tut-p3-report.md` §3: one optional core hook through which the OpenFOAM layer wraps the solve step, found by `get_solve_step_commands`, in decomposePar → mpirun -np N → reconstructPar, N from the staged `decomposeParDict`). Branch `tut-p3`, not merged | done on the branch | `8737e6a`, `5cea253` |
| 5.4b-B | manufacturedBidomain (§5c). Record + shared `records/manufactured_solution_axes.py` (`dimension_axis`/`hex_number_cells_axis`/`tet_number_cells_axis`, reusable by bath/eikonalECG/pseudo-ECG); all 7 native studies rewritten; passes C1-C12 (`test_conformance_native.py`). A `record_key_validation.py` fix (whitespace-containing `str` now infers `"string"`, not `"word"`) and a `dict_entries_catalog.py` fix (`verificationModel.k`'s `applicable_when` now includes `manufacturedFDABidomainVerifier`, matching its own already-cited source_refs) landed alongside it -- both `omnidriver-cardiacfoam`, not core. **Corrected 2026-09-26 (controller decision, same day):** B5/B6's `PIMPLE.nNonOrthogonalCorrectors` gap was fixed natively, not in core -- the case's own `system/fvSolution` now states `nNonOrthogonalCorrectors 0;` explicitly (OpenFOAM's/cardiacFoam's own default, proven behaviour-neutral by `regression/regressionTest.sh`, byte-identical before/after). All 7 rewritten studies now `strict_plan` cleanly, and `corrector`'s coarsest case has been run for real end to end. See `.superpowers/sdd/t54-bidomain-report.md` and `docs/solver-learning/cardiacfoam.md`'s B9/B10. Worktree `t54-bidomain`, not merged | done on the branch, no open gaps | see report |

**Roadmap, 2026-09-26 (current; replaces the rows above where they differ).**

| step | what | state | where |
|---|---|---|---|
| R | rename `niederer2012` → `niederer2011` | **done** | omniD `99a6bac`; native `044559d2` |
| P1 | native base: `feature/spring-supported-slab-tutorial` merged into `omnid/tutorials-are-pointers` in the native worktree `.claude/worktrees/omnid-tutorials-are-pointers` (clean; native `-m native` shape 55 passed against it). **All native migration work happens here**, and `OMNIDRIVER_NATIVE_TUTORIALS` points at its `tutorials/` | **done**, local, not pushed | native `bbdd4a6b` |
| P2 | `block_mesh_resolution_axis`: several documents, `expected_blocks`, a resolution that sees each file's current counts | **done** | `4193cf5` |
| P4 | conformance Task 14: cardiacFOAM `restitutionCurves` passes C1–C12 on the real binary | **done** | `8acbce2` … `b9c46eb` |
| P5 | gmsh facts, from the real binary (`docs/solver-learning/cardiacfoam.md` G1–G6) | **done** | `6c6f93e` |
| P3 | core record features: `default_variant` (blockMesh is the default route) and replaceable default step arguments; Q6 (parallel through the OpenFOAM layer) investigated only | **in progress** | branch `tut-p3` |
| NF | native fixes: `DefineConstant` in the five gmsh templates; pseudo-ECG `anisotropic yes`, with a regression re-run; bidomain's never-applied tolerance references deleted; identical tet overlays deleted. Plus, in omniD, the Q11 catalogue relation and its validation | **in progress** | native worktree; omniD branch `q11-catalog` |
| 5.4a | bath (§5b) | next, after P3 + NF | — |
| 5.4b | bidomain, eikonalECG, **niederer2011**, then pseudo-ECG (§5c) | after P3 + NF; parallel with 5.4a except pseudo-ECG | — |
| B7–B8 | topic B: cardiacFOAM's probe reader, then the cross-solver Niederer comparison | after 5.4b-N | — |
| O15 | conformance Task 15 (the OpenFOAM half of K3) | after P4; not beside step C | — |
| 5.1–5.3 | singleCell, cable1DRestitution, cable1DCVConvergence | parallel with 5.4 | — |
| PAR | records running parallel through the OpenFOAM layer (Q6) | after P3's investigation | — |
| S | supplied inputs (mesh and anatomy) for a record | when the first idealized-heart or cardiacCore case migrates | — |
| 5.5, TL-EM | Purkinje graph, 1D3D; electromechanics | blocked or deferred, as above | — |
| C | final cleanup (§3), including deleting the old factory path | last | — |

**Baseline for the cleaning, measured 2026-09-25 at `0cf5bfb`:**
- tutorial modules plus `tutorials/defaults/`: 5,884 lines;
- all package source: 53,965 lines;
- all package tests: 57,953 lines.

Every step records its own before/after for these three numbers. Totals are
measured with the command, never copied from here.

**Re-measured 2026-09-26 at `2046cc9`.** Tutorial modules plus defaults are
still 5,884 lines, because nothing migrated. All package source is 58,271
lines, and all package tests are 63,594; topics A and B added both. The
command, which reproduces the 2026-09-25 numbers exactly at `0cf5bfb`:

```bash
rev=HEAD
lines() { git ls-tree -r --name-only $rev -- "$1" | grep -E "$2" | xargs -I{} git show $rev:{} | wc -l; }
lines packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/tutorials '\.py$'   # tutorials + defaults
lines packages '/src/.*\.py$'                                                          # all package source
lines packages '/tests/.*\.py$'                                                        # all package tests
```

## 1. The rule from now on: minimum code, no lost content

The goal is not to move the old Python onto the new architecture. It is to
**replace it with the least code that keeps every piece of content**. Content is
what the case, the study or the solver actually needs:
- a derived value;
- a native file's meaning;
- a real refusal;
- a test that guards real behaviour.

Everything else goes:

- **The native case is the default.** Any Python value that restates a native
  file is deleted, not migrated.
- **Delete with the code, not after it.** When a function is removed, the tests
  that only test that function are removed in the same commit, and so are the
  helpers only it used. A test survives only if the behaviour it guards
  survives. When a test is deleted or changed, the commit says why its
  expectation no longer holds.
- **Look one level further.** After a module is deleted, check what it was the
  last caller of (legacy writers, `merge_assignments`, `apply_*_overrides`,
  `update_foam_entry` call sites, the `apply_case` fallback, `synthesize`
  helpers outside the frozen path). Anything left without a caller is deleted in
  the same step. `grep` for callers and name them in the commit.
- **No fallbacks, no compatibility shims, no skips, no waivers.** Refuse by
  name. One implementation per concern: when two exist, reconcile them, never
  keep both.
- **Every step shows the numbers.** Lines deleted versus added, split into source
  and tests. A step that grows the code must say why the growth is content.
- **Native changes are real changes.** They land on the native branch
  `omnid/tutorials-are-pointers`, in the owner's repository, never in the owner's
  own checkout.

Added 2026-09-26: three more owner rules. This plan relied on them without
stating them.

- **Testing against real meshes.** A test reads a real native case or is a
  drift gate against native source. There is nothing in between, and no
  invented geometry. A claim about what the solver or a tool does (a file it
  writes, a flag gmsh accepts) is settled by a real run. It is logged as
  command, observed and conclusion in `docs/solver-learning/cardiacfoam.md`,
  which the first task that settles such a fact creates, as
  `docs/solver-learning/opencarp.md` did for openCARP. A fixture cannot settle
  it.
- **One source of truth.** A record, axis or study never restates a fact
  another layer owns. That includes a native value, a catalogue fact and a
  convention. Model the relation between existing keys instead. A value the
  native case already holds is deleted from Python, not moved.
- **Supplied versus discovered** (`future/ENVIRONMENT_CONTRACT.md` §12). The
  native tree comes from `OMNIDRIVER_NATIVE_TUTORIALS`, the scratch root from
  `--scratch-dir`/`scratch_root=`, and the OpenFOAM environment from
  `--environment-source` or an already-sourced shell. Nothing is found by
  walking up from a file.

## 2. One tutorial, step by step

The same seven sub-steps the pilot proved:

1. **Record:** name, native case path, allowed axes, workflow steps taken from
   the native `Allrun`.
2. **Axes:** only genuinely derived values, reusing existing axes before writing
   one.
3. **Native study:** rewritten to real `document:path` keys plus axis names.
   Delete the old Python-vocabulary config it replaces.
4. **Parity:** for every case the study expands to, the new path commits the same
   values as the old module, compared with the typed comparator or byte by byte.
   The evidence goes in the commit message.
5. **Delete:** the old module, its defaults, its tests, and everything it was
   the last caller of (§1, "look one level further").
6. **Proof:** `describe` with no study values proposes zero changes (a `native`
   test), plus one real solver run through `plan --strict` → `run
   --run-document`.
7. **Numbers:** before/after lines for source and tests, in the commit and in
   the Status table.

**Corrected 2026-09-26 (plan revision): the seven sub-steps against the APIs on
`main` at `2046cc9`.** The recipe above predates topics A and B. Each symbol
named here was checked with `grep` at `2046cc9`. Where this list and the text
above disagree, this list wins.

1. **Record** (`core.tutorial_records.TutorialRecord`, `WorkflowStep`).
   - `native_case_relpath` is relative to the supplied native tutorials root.
     For Niederer it is now `NiedererEtAl2011verification` (native `7a04349b`).
   - Steps are copied from the native `Allrun`. Where the `Allrun` does not
     mesh (bidomain, pseudo-ECG), or has no tet route (all five), see §5g Q7
     and Q8.
   - **Every step declares `produces` and `consumes`**, as observed in a
     real run (K4). C6 checks the declared outputs exist, and C8 checks the
     consumed inputs are fingerprinted. A5's `record_generated_relpaths` keeps
     a step's outputs out of the next staging, and C11 checks that it did.
     The restitutionCurves pilot declares none, which is why conformance
     Task 14 starts by adding them (§5f).
   - **Every cardiacFoam solve step produces
     `constant/electroProperties.withDefaultValues`** (corrected 2026-09-26,
     P4: every step whose solver runs `electroModel::end`. `singleCellSolver`
     overrides it, and `restitutionCurves` writes no such file; R4 in
     `docs/solver-learning/cardiacfoam.md`). Native
     `electroModel::end` (`src/electroModels/core/electroModel.C`) renames the
     dictionary and writes it. No convention excludes it: the OpenFOAM
     layer's suffix rule covers `.foam`, `.msh` and `.geo`. So a restage of a
     run case carries it, and C11 fails with "carried", unless the step
     declares it. See §5g Q13 for where that declaration lives.
   - **Paths are literal.** `WorkflowStep` refuses `{` and `}`, so
     `{instance}` cannot appear in a record. Time-directory outputs cannot be
     declared at all, and they need not be: A2a's `instance_directory_pattern`
     already drops them at staging.
   - A `*` is accepted by `WorkflowStep` and globbed by the reconciler
     (`runtime.reconciler._glob_under`), so C6 can check
     `postProcessing/*_cells.dat`. A5's exclusion, however, matches literal
     relpaths only. A globbed output must therefore sit under a directory a
     convention already drops (`postProcessing` does), or C11 will name it.
   - **A `produces` entry is a plain path unless a reader for its format
     exists.** C12 fails on a declared format that no
     `artifact_value_reader` answers. A `ProducedPath` is added by the task
     that adds its reader (topic B Task 7 for Niederer).
   - **Variants.** A record with `workflow_variants` must declare its own
     `variant_selector`; core reserves no name, and cardiacFOAM's records
     declare `"mesh"`. `_resolve_workflow_step_ids` then **requires** the
     study to name the selector. Today that makes `describe` with no values
     (design §6's zero-change test, and C2) refuse every variant record. No
     production record uses variants yet, so nothing has hit this. See §5g Q2.
     **Corrected 2026-09-26 (P3, owner Q2):** a record with
     `workflow_variants` now declares `default_variant`, the route its native
     case runs, and `record_execution._resolve_workflow_route` runs it when
     the study does not name the selector. A variant record without a
     default, a default that is not a declared variant, and a default on a
     record without variants are each refused at construction, by name. A
     study that names the selector as `null` is refused, never defaulted.
     `describe`'s `record_preview.workflow_variant` says which route was
     chosen and whether it came from the study or the record.
   - **Commands.** One step's extra arguments come from exactly one axis:
     `resolve_case_patches` refuses two axes contributing to one step unless
     they agree byte for byte. An axis may contribute to a declared step that
     the selected variant does not run. An axis cannot remove or replace a
     base argument, only append (§5g Q3).
     **Corrected 2026-09-26 (P3, owner Q3/Q7):** a step may declare
     `default_arguments`, each a `DefaultArgument(key, values)` fixed on the
     step and independent of any study (`blockMesh -dict
     system/blockMeshDict.3D`, from the case's own `regressionTest.sh`). An
     axis replaces one by passing its `key` tokens, contiguously, anywhere in
     its contribution; otherwise it appends and the default stays. `key` is
     as many tokens as name the argument (`("-dict",)`, or
     `("-setnumber", "lc")` for gmsh). Refused by name: a key that does not
     occur exactly once in the step's default command line (it is in
     `command`, repeated, or inside another default), and a contribution
     holding a key twice. `command` itself is still never replaced.
     `record_preview.workflow_commands` shows each selected step's argv.
   - The record is registered in `records/__init__.py`, and the factory is
     removed from `tutorials/registry.py`/`ids.py` **in the same commit**.
     `runtime.registry.classify_entry` refuses a name registered as both.
2. **Axes.**
   - Reuse before writing: `openfoam.axes.block_mesh_resolution_axis`,
     `records.ionic_model_axis` and `records.s1_s2_protocol_axis`; the
     reader `openfoam.case_planning.read_hex_cell_counts`; and the pure
     function `openfoam.mesh_provisioning.cell_counts_from_dx`, which the
     cable tutorials also use.
   - An axis reads the staged case read-only. `scripts/check-case-writes.py`
     scans `cardiacfoam/records/`, `openfoam/axes/` and
     `openfoam/case_planning.py`, and refuses any writer there, with an empty
     waiver list.
   - An `AxisPatch` sets a value. **It cannot remove a key** (§5g Q4), and
     **an axis sees only its own study value** (§5g Q5).
3. **Native study.**
   - Rewritten to `document:dotted.path` keys, axis names and the selector
     name.
   - `sort_study_name` splits the dotted path on `.`. A quoted OpenFOAM
     regex key such as `solvers."phiE|phiEFinal|phiI|phiIFinal".tolerance`
     therefore splits into three segments, one of them quoted. Whether
     `record_key_validation` and the OpenFOAM renderer and reader resolve
     that quoted segment is **unverified**. Prove it with a real preview
     before rewriting any study that needs it.
   - cardiacFOAM keys are checked against the catalogue as re-synced in K.
     A key the C++ reads that the catalogue lacks is added with its
     `source_refs`, never bypassed. OpenFOAM keys are written and flagged
     `unvalidated`.
   - Every Python-vocabulary key the rewrite drops (`case_dir_name`,
     `setup_dir_name`, `archive_dir_name`, `postprocess_strict_artifacts`,
     `numerics_profile`, `ecg_enabled`, and so on) is listed in the native
     commit, each with the reason it has no effect.
   - The native study's `"entry"` names the record, and `niederer2011` for
     Niederer.
4. **Parity** is as above, with one addition. A study the old module could
   not run has no old output to compare against: bidomain's seven studies
   all pass `ode_abs_tolerance`/`ode_rel_tolerance`, which its `make_spec`
   does not accept. Say so in the commit, and prove the rewritten study by a
   preview with no refusal instead.
5. **Delete**, as above. The fallout that every migration in this family
   hits, taken from the pilot's `46bd2f0`, is edited in the same commit:
   - `tutorials/registry.py` (the name and its `.lower()` alias) and `ids.py`;
   - `display.py`: its `TutorialDisplay.id` must equal the record name, and
     `scripts/export-tutorials-catalog.py` cross-checks factories and records
     together;
   - `test_registered_tutorials_need_no_repository.py`: its
     `_NEEDS_CASE_CONTENT`, and whether the `built == 14` pin moves;
   - `test_dead_postprocess_constants.py`'s `_MODULES`;
   - `tests/regression_equivalence/`: `test_staging.py`'s
     `test_mapped_entry_resolves_registered` expects `"registered"`, but a
     record resolves as `"tutorial_record"`, so each mapped case changes as
     it migrates.
6. **Proof.** A record is proved by three things:
   - (a) one `native` test, in which `describe` with no values proposes
     zero changes. This is design §6 and equal to C2, so the conformance
     parametrization can **be** that test, and no separate module is needed;
   - (b) joining the cardiacFOAM conformance target's parametrization
     (§5f) with **every** check in `omnidriver.conformance.CHECKS`, C1–C12,
     passing. C5 and C6 already run `plan --strict` and then
     `run --run-document`, so a separate real-run test per record, as the
     pilot's `test_restitution_curves_real_solver_run_native.py` is, is not
     written again;
   - (c) the axis tests against real native files (design §6).

   The OpenFOAM environment comes from an already-sourced shell, which the
   conformance child processes inherit (`checks._child_env`), or from
   `--environment-source`. `OMNIDRIVER_NATIVE_TUTORIALS` points at a **clean
   native worktree** (§4), never at the owner's checkout.
7. **Numbers.** Run the command under the Status table, before and after.

## 3. Final cleanup (step C)

Once the last migratable tutorial is done:
- delete `tutorials/defaults/` and the factory machinery only
  `totalLagrangianEM` still uses. The factory path stays for that one tutorial,
  and only it;
- delete every legacy writer left without a caller;
- re-run the widened write inventory from the Phase 3 close-out and close G3,
  listing the declared exceptions (file placement, `write_cell_set`,
  `totalLagrangianEM`).

Added 2026-09-26: what else step C must do, now that topic A has landed.
- `manufactured_monodomain_total_lagrangian_em.py` stays on the factory path.
  It imports `_build_cases` and `_case_output_filename` from the pseudo-ECG
  module, and its defaults import pseudo-ECG constants. Whatever of those
  survives 5.4b-P (§5c) now lives in the TL-EM module, and it is the only
  place such code remains.
- Conformance Task 14 ends "when all of them pass, the old factory path can be
  deleted". That deletion is step C, and only once every migrated record is in
  the cardiacFOAM conformance parametrization and passes.
- These helpers lose their last production caller in 5.4 (§5b, §5c). Each is
  deleted in the step that removes that caller, not left for step C:
  `case_planning.plan_write_interval`, `overrides.resolve_electro_property_removal`,
  `render_tet_geo`'s file write, the tet-overlay copy code, and the `update_foam_entry`
  post-commit loops.

## 4. Working in parallel with openCARP without losing anything

- **Who touches what:**

  | stream | touches |
  |---|---|
  | tutorials (this plan) | `omnidriver-cardiacfoam`, `omnidriver-openfoam` where a tutorial needs it, the native branch |
  | openCARP | core conformance and the executor seam, plus its own package |

  Core is the only shared ground.
- **Core changes land small and early.** Either stream's core change goes to
  `main` as its own commit, and the other stream rebases promptly. Nobody holds
  core changes in a long-lived branch.
- **The generality log.** Every core change either stream needs gets a line in
  §5: which stream needed it, what it is, and why.

  | what the log shows | meaning |
  |---|---|
  | small neutral additions | the core is general |
  | solver vocabulary or solver-shaped assumptions surfacing in core | it is not general yet, and the log says where |

- **For the tutorial stream, when you rebase onto the supplied-scratch-root
  commit (2026-09-26):** the scratch root no longer defaults to
  `<cases_root>/.omnidriver`. Every `plan --strict`, `step`/`run --strict` over
  a record, and every `sweep-plan`/`sweep-run` without `--output-dir`, now
  needs `--scratch-dir <dir>` (or `OMNIDRIVER_SCRATCH_DIR`) outside the
  tutorials tree, or it is refused as JSON naming `--scratch-dir`. Add
  `--scratch-dir <tmp>` to the commands in your plans and handoffs, pass
  `scratch_root=tmp_path / "scratch"` to any in-process `strict_plan` over a
  record, and add `"--scratch-dir", str(tmp_path / "scratch")` to any native
  test that plans a record through `main([...])` (as
  `test_restitution_curves_strict_plan_run_document_native.py` now does). A
  stale `from omnidriver.core.specs.paths import scratch_root` fails to import
  by design: use `resolve_scratch_root`. `describe` needs nothing.
- **Corrected 2026-09-26: who touches what now.** The openCARP stream is done
  (Tasks 1–13). Topic A is done, and so are topic B Tasks 1–6. The streams
  that remain:

  | stream | touches | waits on |
  |---|---|---|
  | tutorials (this plan) | `omnidriver-cardiacfoam`, `omnidriver-openfoam` (§5e P2), small neutral core additions if the owner agrees (§5g Q2–Q5), the native branch | §5e P1 |
  | rename `niederer2011` | the cardiacFOAM tutorial and test names, `equivalence_protocol.yaml`'s `source_reference`, docs | nothing; in flight |
  | conformance Tasks 14–15 | `records/restitution_curves.py`, `cardiacfoam_plugin.py`, `introspection`, `conformance/checks.py` (C10 grammar), `plugin.yaml`, `openfoam-environment.yaml` | nothing (§5f) |
  | topic B Tasks 7–8 | `openfoam/probes.py`, `cardiacfoam/activation_probes.py`, `runtime_evidence.py`, the `niederer2011` record | this plan's 5.4b-N |

  Several files are shared by these streams: `records/__init__.py`,
  `tutorials/registry.py`, `ids.py`, `display.py`, `equivalence_protocol.yaml`,
  `tests/regression_equivalence/registry.py` and
  `test_registered_tutorials_need_no_repository.py`. A change to any of them
  is a small commit that rebases, and is never held in a long-lived branch.
- **The native base (added 2026-09-26).** The native branch
  `omnid/tutorials-are-pointers` (`38a451c4`) is based on native `dbc0ec6b`.
  It lacks the owner's `7a04349b` (the Niederer case move) and `c15e2fcf`
  (the dead keys), and the owner's current line lacks its `38a451c4` (the
  pilot's `tworldS1S2Restitution/sweep.json`: the owner's
  `restitutionCurves_s1s2Protocol/setup/` is empty). Before any 5.4 native
  change, the owner's line is merged into the native branch (§5e P1, §5g
  Q1). It is merged, not rebased, because `origin/omnid/tutorials-are-pointers`
  exists and nothing is force-pushed.
- **A clean native tree (added 2026-09-26).** Native tests and conformance
  run with `OMNIDRIVER_NATIVE_TUTORIALS=<native worktree>/tutorials`, from a
  `git worktree add` of the native branch, never from the owner's checkout.
  That worktree also gives the `../src` sibling that the key-scanner test
  reads. The owner's checkout holds git-ignored output from runs made in
  place. Staging a record drops most of it, but not all; measured at
  `2046cc9` with `sweep_runner._stage_entry_case` on the real cardiac stack:

  | native case (owner's checkout) | paths on disk | staged | staged but untracked |
  |---|---|---|---|
  | `manufacturedSolutions/bathBidomain` | 61 | 61 | none |
  | `manufacturedSolutions/bidomain` | 52 | 52 | `setup/__pycache__/*.pyc` |
  | `manufacturedSolutions/eikonalECG` | 2,493 | 70 | 14 `checkMesh -writeAllFields` fields in `0/` (`0/aspectRatio`, `0/cellVolume`, …, sized for a 289,388-cell mesh), `constant/electroProperties.withDefaultValues`, `__pycache__` |
  | `manufacturedSolutions/monodomainPseudoECG` | 389 | 49 | `constant/electroProperties.withDefaultValues`, `.DS_Store`, `__pycache__`, and the six untracked sweeps, since deleted |
  | `NiedererEtAl2011verification` | 29 | 29 | `constant/electroProperties.withDefaultValues` |

  Two consequences follow.
  - **Staging carries whatever `0/` holds.** `"0"` is a preserved instance,
    and nothing under it is excluded. A step that writes into `0/` must
    therefore declare that output, or its restage carries it. Two candidates
    are `setTorsoOrganConductivityField`'s field and `checkMesh
    -writeAllFields`. A native case that already holds stale `0/` fields is
    not a valid source; the native cleanup's own report hit this, when
    `decomposePar` failed on `0/aspectRatio`.
  - **C11 fails on the owner's checkout for a reason that is not the
    record's.** `check_restage_is_clean` compares the restage with
    `_relpaths(target.cases_root / record.native_case_relpath)`, meaning
    every path on disk, ignored run output included. Against
    `monodomainPseudoECG` in the owner's checkout it would report some 340
    "dropped" paths. Against a clean worktree it measures what it should.
- **Merging and pushing:**
  - Nothing is pushed to `main` without the owner's explicit go-ahead.
  - Nothing is ever force-pushed.
  - Before any merge, every uncommitted state in every worktree is snapshotted
    under `refs/preserve/<date>/*`.
  - `main` is only updated by a fast-forward, or by a merge made in a worktree
    no running session uses. Never in a checkout another agent is working in.
  - Before a push, `origin/<branch>` is checked to be an ancestor of what is
    pushed.

## 5a. Next: step 5.4a, manufacturedBathBidomain

Chosen first because it is the hardest; it stresses more of the core than any
other tutorial. The seven sub-steps of §2, concretely:

> **Corrected 2026-09-26 (plan revision).** The executable task list for 5.4a
> is now §5b. The reasoning below stands, except for these facts, each checked
> against the native case at `c15e2fcf` and omniD at `2046cc9`:
> - **There are 14 studies, not nine.**
>   - hex: 4 (`cartesianConvergence/` ×3, `temporalConvergence/sweep_hex_temporal_godunov`);
>   - tet: 10 (`coupling/`, `gradientScheme/` ×4, `interfaceCurrentConvergence/` ×2, `tetConvergence/` ×2, `tetTemporalControl/`).
> - **The native `Allrun` has no tet route.**
>   - It runs `blockMesh -dict system/blockMeshDict.${DIM:-1D}` (skipped
>     when the first argument is `parallel`), `topoSet`,
>     `setTorsoOrganConductivityField`, then `cardiacFoam`, or the parallel
>     trio with a `parallel` argument.
>   - The tet route exists only in the old module's DAG: `gmsh` →
>     `gmshToFoam` → `checkMesh` → `setTorsoOrganConductivityField` →
>     solve → `bathBidomainInterfaceMetrics -latestTime`, with no `topoSet`.
>     Native files acknowledge it: the template, and `Allclean` removing
>     `*.msh`, `.geo` and the metrics CSVs. See §5g Q8.
> - **`three_domain_box.geo.template` has `lc = __LC__;`, not
>   `DefineConstant`.** No native `.geo.template` has one (bath, bidomain,
>   eikonalECG, pseudo-ECG, Niederer's `slab.geo.template`), so the
>   `DefineConstant` change is five native edits.
> - **`block_mesh_resolution_axis` cannot do what item 2 asks.**
>   - Its instance is bound to one `document`.
>   - The production writer (`overrides._target_for_parameter` →
>     `plan_block_mesh_resolution`) and reader
>     (`environment._read_config_value_by_key_path` →
>     `read_hex_cell_counts`) both default to `expected_blocks=1`, so a
>     three-block bath file is refused on write **and** on the "unchanged"
>     read.
>   - `test_axes_block_mesh_resolution.py::test_the_axis_produced_value_still_refuses_the_wrong_block_count_when_rendered`
>     pins that refusal. §5e P2 changes it, and that test changes with it.
> - **`phiERefPoint` depends on N as well as on the dimension.**
>   - The old `_phi_e_ref_point_yz` computes y and z as `ext/2 + ext/(2N)`
>     in each subdivided direction, which is a cell centre.
>   - It writes the point only on the `electrodePair` route.
>   - An axis sees only its own value (§5g Q5).
> - **The `groundElectrode` route needs a key removed.** It removes
>   `surfaceCurrentPatches.xMin` and adds `groundPatches.xMin`. Native
>   `extracellularPotentialDomain.C` stops with a fatal error when one patch
>   is in both, and the catalogue declares them `mutually_exclusive_with`.
>   An `AxisPatch` cannot remove (§5g Q4). Seven of the 14 studies use
>   `groundElectrode`; two use `electrodePair`; five name no variant, so they
>   run the native `electrodePair`.
> - **Direct `update_foam_entry` loops:** only `fv_scheme_overrides` (the four
>   `gradientScheme/` studies) and `phi_tolerance` (`tetTemporalControl/`,
>   `1e-15`, which equals the native value) are used. `grad_scheme` and
>   `fv_solution_overrides` appear in no bath study.
> - **The tet overlay** `setup/studies/tetConvergence/fvSchemes` is
>   byte-identical to `system/fvSchemes` (`cmp`). It is the only overlay under
>   `setup/`.
> - **`bath_predictor_corrector` defaults to `False` in Python**, where native
>   says `yes`. Every study passes `true` except `coupling/`, which sweeps it,
>   so parity holds per study.
> - **The output name is `postProcessing/<dim>_<N>_cells.dat`**, from
>   `manufacturedFDABathBidomainVerifier.C`. The `bathBidomain_` prefix was
>   dropped natively in `7ae47527c`. Three things are stale as a result:
>   omniD's `test_artifacts_predictor.py`, native
>   `setup/post_processing_manufactured_bath.py`'s `FILENAME_PATTERN`, and
>   `regressionTest.sh`'s header comment. The native ones are the owner's. The
>   omniD test is corrected or deleted in 5.4a (§5b T5), whichever its
>   remaining callers need.

1. **Record.**
   - Native case: `manufacturedSolutions/bathBidomain`.
   - Workflow steps, from its `Allrun`: `blockMesh -dict
     system/blockMeshDict.<dim>` → `topoSet` → `setTorsoOrganConductivityField`
     → `cardiacFoam`.
   - The parallel route (`decomposePar` → `cardiacFoam -parallel` →
     `reconstructPar`) is a second workflow variant.
   - The expected hex-block count, 3, is stated in the record.
2. **Axes**, all in this tutorial's own cardiac record (the owner decisions of
   2026-09-25):
   - `dimension` sets `bidomainSolverCoeffs.dimension` and the mesh step's `-dict
     system/blockMeshDict.<dim>` together.
   - N patches all three `blockMeshDict.<dim>` files. It puts the same counts
     on every hex block and keeps each file's own directions at 1.
   - `phiERefPoint` is derived from the chosen `blockMeshDict`'s extents, read
     from the file with no copied table.
   - The tet route: `lc = 1/N` as the gmsh step's `-setnumber lc <value>`. Its
     real-binary test moves here from step 3.
3. **Native changes**, on the native branch:
   - `DefineConstant[ lc = ... ];` in
     `setup/studies/tetConvergence/three_domain_box.geo.template`.
   - The nine `setup/studies/*/sweep*.json` rewritten to real keys: the
     gradient-scheme studies become plain `system/fvSchemes:...` keys.
   - The tet numerics-overlay copy is dropped, because the overlay is
     byte-identical to the case's own `system/fvSchemes`.
   - The case's own `bathPredictorCorrector yes` is the default; a study that
     wants `false` states it.
4. **Parity:** every case of those nine studies, new output against the old
   module's.
5. **Delete:**
   - the 724-line module, `tutorials/defaults/manufactured_bath_bidomain.py` and
     their tests;
   - everything they were the last caller of: `render_tet_geo`'s file write,
     the overlay-copy code, and the direct `update_foam_entry` loops for
     `grad_scheme` / `phi_tolerance` / `fv_*_overrides`.
6. **Proof:** zero changes with no study values, and one real solver run at a
   coarse N set through the study.
7. **Numbers:** lines before and after, source and tests.

**Open for the owner during 5.4a:**
- whether the parallel route should be a workflow variant (as above) or be
  dropped from the record;
- whether any of the nine bath studies are obsolete and should be deleted rather
  than rewritten.

Corrected 2026-09-26: both questions are restated, with recommendations, as
§5g Q6 (parallel route) and Q10 (the studies, which number 14).

## 5b. Step 5.4a, manufacturedBathBidomain, as tasks (added 2026-09-26)

**Before, measured at `2046cc9`:**
- source: `tutorials/manufactured_bath_bidomain.py` (719 lines) + `tutorials/defaults/manufactured_bath_bidomain.py` (97) = 816 lines;
- tests: `test_manufactured_bath_bidomain_tet.py` (284) + `test_manufactured_bath_bidomain_write_channel.py` (252) + `test_bath_bidomain_variant_apply.py` (124) = 660 lines.

The helpers it is the last caller of are counted as they are deleted.

**Needs:** §5e P1 (native base), P2 (block-mesh axis), P3 (the core additions of §5g Q2–Q5, as the owner answers them) and P5 (the gmsh facts). Its proof sub-step also needs P4 (the cardiacFOAM conformance target).

- **T1, native** (native worktree, native branch; one commit per bullet):
  - `setup/studies/tetConvergence/three_domain_box.geo.template`: replace
    `lc = __LC__;` with `DefineConstant[ lc = { <default>, Name "lc" } ];`. The
    default is the owner's (§5g Q8). P5 has proved that gmsh reads the
    template file as it is and that `-setnumber lc` overrides the default.
  - Delete `setup/studies/tetConvergence/fvSchemes`, which is byte-identical
    to `system/fvSchemes` (§5g Q10). No study names it once T3 lands.
  - Rewrite the 14 studies. The mapping:

    | old key | new |
    |---|---|
    | `dimensions` | `dimension` axis |
    | `number_cells` (hex) / (tet) | `numberCells` axis / `tetNumberCells` axis |
    | `dt_values` | `system/controlDict:deltaT` |
    | `end_time` | `system/controlDict:endTime` **and** `system/controlDict:writeInterval` with the same value; the old `plan_write_interval(end_time)` set both |
    | `mesh_family` | `mesh` (the record's selector: `hex`/`tet`) |
    | `fda_bath_variant` | `fdaBathVariant` axis |
    | `bath_predictor_corrector` | `constant/electroProperties:bidomainSolverCoeffs.bathPredictorCorrector`, **omitted** where `true`, which is the native value (all but `coupling/`, which sweeps it) |
    | `electro_property_overrides` (`…interfaceConductivityInterpolation`) | the direct key; omitted where it equals native `distanceWeightedHarmonic` (6 of 7) |
    | `fv_scheme_overrides` | `system/fvSchemes:gradSchemes.default`, `…laplacianSchemes.default`, `…snGradSchemes.default` |
    | `phi_tolerance 1e-15` (`tetTemporalControl/`) | omitted: native `system/fvSolution` already has `1e-15`. So bath needs no quoted-regex key (§2 item 3) |
    | `solver_types ["implicit"]` | omitted: native `solutionAlgorithm implicit` |
    | `piecewise_sweep` true/false | sweep `mode` `zip`/`product` |
    | `run_in_parallel` | §5g Q6 |
    | `numerics_profile`, `ecg_enabled false`, `case_dir_name`, `setup_dir_name`, `archive_dir_name`, `postprocess_strict_artifacts` | dropped, each named in the commit (overlay identical; native has no `ecgDomains`; core owns sweep output) |
    | dependent `case_id_template` / `output_dir_name_template` | kept; `of` renamed to the new names |
- **T2, omniD record** `records/manufactured_bath_bidomain.py` (`RECORD`, `AXES`), registered in `records/__init__.py`, with the factory removed in the same commit (§2 item 1):
  - `native_case_relpath="manufacturedSolutions/bathBidomain"`, `variant_selector="mesh"`, and `default_variant="hex"` if Q2 is accepted, since that is the route `Allrun` runs.
  - Steps, each with the `produces`/`consumes` **observed** in one real run of that step. The expected values are listed; the run decides.
    - `mesh`: `blockMesh`, with `-dict system/blockMeshDict.<dim>` from the `dimension` axis. It consumes the `blockMeshDict` candidates, and its mesh goes to `constant/polyMesh`, which is dropped by name.
    - `topoSet` (hex only; consumes `system/topoSetDict`).
    - `setConductivity`: `setTorsoOrganConductivityField`. It consumes `system/setTorsoOrganConductivityFieldDict`. It is expected to write a field into `0/`; if so, it **must** declare it (§4, "staging carries whatever `0/` holds").
    - `solve`: `cardiacFoam`. It produces `constant/electroProperties.withDefaultValues` and `postProcessing/*_cells.dat`.
    - Tet only:
      - `gmsh`: `gmsh -3 setup/studies/tetConvergence/three_domain_box.geo.template -o three_domain_box.msh -format msh2`, with `-setnumber lc <1/N>` from `tetNumberCells`;
      - `gmshToFoam three_domain_box.msh`;
      - `checkMesh`;
      - `interfaceMetrics`: `bathBidomainInterfaceMetrics -latestTime`, producing `postProcessing/bathBidomainInterfaceMetrics.csv`.
    - Variants:
      - `hex = (mesh, topoSet, setConductivity, solve)`;
      - `tet = (gmsh, gmshToFoam, checkMesh, setConductivity, solve, interfaceMetrics)`.
  - Axes. Declare none that restates a native value.
    - `dimension` (`1D`/`2D`/`3D`) sets `bidomainSolverCoeffs.dimension`, and adds the `mesh` step's `-dict`. With Q5 it also derives `bathPotentialDomain.phiERefPoint`:
      - x is kept from the case's own value;
      - in each direction the chosen `blockMeshDict.<dim>` refines, y and z are `ext/2 + ext/(2N)`, with extents read from that file and N the study's `numberCells` or, absent, that file's own counts;
      - otherwise they are `ext/2`.

      It is written on both variant routes. Native `extracellularPotentialDomain::referenceCell` reads it only for pure-Neumann `phiE`, the `electrodePair` route, so it is inert under `groundElectrode`, and the old module's route test is not needed.
    - `numberCells` comes from P2's builder over `system/blockMeshDict.1D`, `.2D` and `.3D`, with `expected_blocks=3`. A direction whose count is 1 stays 1 (decision (d)).
    - `tetNumberCells` adds `-setnumber lc <1/N>` to `gmsh`. It is a separate axis so that a tet case writes nothing into the unused `blockMeshDict`s, and parity with the old tet route holds.
    - `fdaBathVariant` (`groundElectrode`/`electrodePair`) sets `verificationModel.fdaBathVariant`. For `groundElectrode` it also sets `groundPatches.xMin 0` and **removes** `surfaceCurrentPatches.xMin` (Q4). `electrodePair` is the native state, so it proposes no change on the native case.
- **T3, parity.** For every case the 14 studies expand to, the committed `constant/electroProperties`, `system/controlDict`, `system/fvSchemes` and the three `blockMeshDict`s from the record equal the old `_plan_case` + post-commit loops' output. Use the typed comparator (`effective_values_agree`), or byte equality for untouched files. Each difference is either a restated default now "unchanged", or named and explained. The evidence goes in the commit, as in `46bd2f0`.
- **T4, proof.**
  - The zero-change `describe` is C2 in the conformance parametrization.
  - The record joins the cardiacFOAM target parametrization (§5f), and all of `CHECKS` pass. A suggested target:
    - `base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10, "system/controlDict:endTime": 0.02}`;
    - `patch=("constant/electroProperties:bidomainSolverCoeffs.verificationModel.alpha", 0.02)`;
    - `untouched=("constant/electroProperties", ("bidomainSolverCoeffs", "verificationModel", "k"))`;
    - `sweep_name="numberCells"`, `sweep_values=(10, 20)`;
    - `unknown_name="constant/electroProperties:bidomainSolverCoeffs.bathPredictorCorector"`, the typo on purpose;
    - `solver_command="cardiacFoam"`.
  - One real tet run, `{"mesh": "tet", "dimension": "3D", "tetNumberCells": 10}`. This is the gmsh real-binary test that step 3 moved here.
- **T5, delete** (same commit as T2):
  - the module and its defaults;
  - the three test files above;
  - the helpers left without a production caller: `case_planning.plan_write_interval`, and `overrides.resolve_electro_property_removal` together with the part of `test_describe_proposed_changes.py` that tests only it;
  - bath's private tables: `DOMAIN_YZ_EXTENT_BY_DIMENSION`, `YZ_SUBDIVIDED_BY_DIMENSION`, `FDA_ALPHA`, `_TET_NUMERICS_PROFILES` and its `_GRAD_SCHEME_TOKENS` copy;
  - `write_channel_test_support.py`'s `BLOCK_MESH_DICT_TEXT_3_BLOCKS`/`three_blocks=`, which are already callerless;
  - the dead-key residue: `test_rtst_enum_contract.py`'s `NON_RTST_DRIVER_PATHS` entry `$ELECTRO_MODEL_COEFFS.manufacturedBidomain.fdaBathVariant`, and a dated correction on `overrides.py`'s docstring naming it.

  Edit, in the same commit, the §2 item 5 list, plus `test_validation.py`'s `"manufactured_bath_bidomain"` row (a label: check whether it needs changing) and `test_artifacts_predictor.py`'s `bathBidomain_3D_19_cells.dat`. Removing bath also removes its import of pseudo-ECG's `_build_cases`, which 5.4b-P needs gone first.
- **T6, numbers:** before/after for source and tests, plus the three totals.

## 5c. Step 5.4b as tasks, one per tutorial (added 2026-09-26)

The order inside 5.4b follows the import graph, not the old list:
- `manufactured_bidomain.make_spec` is a pass-through to pseudo-ECG's;
- bath imports pseudo-ECG's `_build_cases`;
- the bidomain and bath defaults import pseudo-ECG's constants;
- TL-EM, which stays a factory, imports `_build_cases` and `_case_output_filename`.

So pseudo-ECG goes **last** (5.4b-P). Bidomain (5.4b-B), eikonalECG (5.4b-E)
and niederer2011 (5.4b-N) are independent of each other.

The four multi-dimension manufactured cases (bath, bidomain, eikonalECG and
pseudo-ECG) share their axis shapes: `dimension`, `numberCells` and
`tetNumberCells`. Build them once, in a shared `records/` module, when 5.4a
or the first 5.4b task needs them. Each record instantiates them with its own
`<solver>Coeffs` scope and file set. That is reuse, not a second copy.

### 5.4b-B, manufacturedBidomain

- **Before:** source `tutorials/manufactured_bidomain.py` (115) + `defaults/manufactured_bidomain.py` (77) = 192; tests `test_manufactured_bidomain_tet.py` (83), plus `test_strict_planning.py::test_strict_plan_succeeds_for_manufactured_tutorial`.
- **Native case:** `manufacturedSolutions/bidomain`. `Allrun` only solves, serially or with `parallel`; it has **no mesh step**. `regression/regressionTest.sh` runs `blockMesh -dict system/blockMeshDict.3D` and then `./Allrun` (§5g Q7). There is no plain `system/blockMeshDict` (§5g Q3). Native `dimension "3D"`.
- **Native changes:**
  - `DefineConstant` in `setup/studies/tetConvergence/box.geo.template`.
  - Delete the `setup/studies/tetConvergence/fvSchemes` overlay, which is byte-identical to `system/fvSchemes`.
  - Rewrite the 7 studies:
    - `grad_scheme` → `system/fvSchemes:gradSchemes.default` (`"Gauss linear"`/`leastSquares`);
    - `phi_tolerance` → `system/fvSolution:solvers."phiE|phiEFinal|phiI|phiIFinal".tolerance`. It is omitted at the native `1e-15`, but `linearToleranceControl/`'s `1e-6` **needs the quoted key**, which must be proven first (§2 item 3);
    - `n_outer_correctors` → `system/fvSolution:PIMPLE.nOuterCorrectors`;
    - `n_nonorthogonal_correctors` → `system/fvSolution:PIMPLE.nNonOrthogonalCorrectors`. It is absent natively, since the old code used `add_if_missing`. Check that the channel writes a key the document lacks;
    - `control_dict_overrides` → `system/controlDict:writeControl`/`writeInterval`/`writeFormat`;
    - `end_time` → `system/controlDict:endTime`;
    - `ode_abs_tolerance`/`ode_rel_tolerance` → §5g Q9;
    - the rest as in 5.4a's T1 table.
- **Record** `records/manufactured_bidomain.py`:
  - variants:
    - `hex = (mesh, solve)`;
    - `tet = (gmsh, gmshToFoam, checkMesh, solve)`. It uses `box.geo.template`/`box.msh`. The old tet DAG's `Allclean` step is dropped, because staging is already clean.
  - `solve` produces `constant/electroProperties.withDefaultValues` and `postProcessing/*_cells.dat`. The verifier names it `<dim>_<round(nCells^(1/d))>_cells.dat`, so a literal path cannot be written.
  - Axes: `dimension` (`bidomainSolverCoeffs.dimension` + `-dict`, with no `phiERefPoint` derivation, since the old module had none), `numberCells` (one block ×3 files) and `tetNumberCells`.
- **Parity:** none is possible. All 7 studies are unrunnable through today's `make_spec`, because of the ODE kwargs (§2 item 4). Prove instead that every rewritten study previews with no refusal, and that the hex cases' committed values equal what the old module writes for the same `(dimension, N, dt)` with the ODE kwargs removed.
- **Proof:** conformance parametrization. For example: `base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10}`; sweep `numberCells` `(10, 20)`; patch `constant/electroProperties:bidomainSolverCoeffs.verificationModel.k`.
- **Delete:**
  - the module, its defaults and `test_manufactured_bidomain_tet.py`;
  - pseudo-ECG's `_NUMERICS_PROFILES["bidomain_tet"]` entry and the pseudo-ECG tet test's cases that exercise it;
  - `test_strict_plan_succeeds_for_manufactured_tutorial` is re-pointed at the record, or deleted if conformance C5 covers what it asserts (the factory's `verification_error_summary` artifact and `current_step_id == "mesh"`). Say which, and why;
  - the §2 item 5 list.

### 5.4b-E, manufacturedEikonalECG

- **Before:** source `tutorials/manufactured_eikonal_ecg.py` (617) + `defaults/manufactured_eikonal_ecg.py` (90) = 707; tests `test_manufactured_eikonal_ecg_tet.py` (233) + `test_manufactured_eikonal_ecg_write_channel.py` (116) = 349.
- **Native case:** `manufacturedSolutions/eikonalECG`. `Allrun` runs `blockMesh -dict system/blockMeshDict.3D` unconditionally, then solves. `0/activationTime` is tracked, and the solve consumes it. **The owner's checkout also holds 14 stale `checkMesh -writeAllFields` fields in `0/`** (§4), which is why a clean native worktree is required.
- **Native changes:**
  - `DefineConstant` in `box.geo.template`.
  - Delete the `setup/studies/tetConvergence/fvSolution` overlay, which is byte-identical.
  - Rewrite the 6 studies:
    - `conductivity` → `constant/electroProperties:eikonalSolverCoeffs.conductivity`;
    - `conductivity_label` → naming only: a dependent name, or dropped;
    - `eikonal_advection_diffusion_approach` → `…eikonalSolverCoeffs.eikonalAdvectionDiffusionApproach`;
    - `grad_scheme` → `system/fvSchemes:gradSchemes.default`;
    - `fv_solution_overrides` `[PIMPLE, residualControl, activationTime].tolerance` → `system/fvSolution:PIMPLE.residualControl.activationTime.tolerance`;
    - the dotted `electro_property_overrides` `eikonalSolverCoeffs.verificationModel.writeErrorField` → `constant/electroProperties:eikonalSolverCoeffs.verificationModel.writeErrorField`;
    - `error_localisation_analysis`/`gradient_reconstruction` → variants (below);
    - `numerics_profile` → dropped.
- **Record:**
  - variants:
    - `hex = (mesh, solve)`;
    - `tet = (gmsh, gmshToFoam, checkMesh, solve)`;
    - `tet-errorLocalisation`, which adds `writeCellCentres`: `postProcess -func writeCellCentres -latestTime`. Its output goes into a time directory, so it cannot be declared, and it is dropped at staging anyway;
    - `tet-gradientReconstruction`, which adds `gradientReconstructionOrder`. That command is already authorised in `command_authorization`.

    One selector holds four values, because a record has one selector.
  - `solve` produces:
    - `constant/electroProperties.withDefaultValues`;
    - `postProcessing/manufacturedEikonalActivationTime.dat`;
    - `postProcessing/eikonalECG.dat`;
    - `postProcessing/manufacturedEikonalECG_ECG.dat`;
    - `postProcessing/manufacturedEikonalECGSummary_ECG.dat`.

    These names come from the C++. Confirm them in a real run.
  - Axes:
    - `dimension`: eikonal has no `dimension` key, so it sets the `-dict` and the 1D/2D `E1`–`E5` electrode positions. Today those positions exist only in Python (`defaults.ECG_ELECTRODES_BY_DIMENSION`), and the 3D ones restate native. First check whether a formula over the chosen file's extents reproduces them. If it does, derive them in the axis. If not, they are study content: move them into the hex study as direct keys, and do not keep a Python table;
    - `numberCells`;
    - `tetNumberCells`.
- **Dead native key (after `c15e2fcf`):**
  - Delete `validation._evaluate_personalized_templates`'s `manufacturedEikonalECG.` prefix clause.
  - Switch `test_validation.py::test_personalized_templates_rejects_manufactured_ecg_before_execution` to `verificationModel.type` (the surviving selectors are `ecgVerificationModel` and `verificationModel.type`).
- **Parity:** all 6 studies, hex and tet. The old tet route wrote through `apply_electro_property_overrides`, not the channel, so compare the committed documents, not the write path.
- **Proof:** conformance parametrization, `base_study={"mesh": "hex", "dimension": "1D", "numberCells": 10}`.
- **Delete:**
  - the module, its defaults and the two test files;
  - `apply_physics_property_overrides` loses this caller, leaving Niederer and `generic_case_mutation`;
  - the §2 item 5 list.
- **For the owner, not this plan:** native `constant/electroProperties` ends with a top-level `useGraphPrePopulation false;` that `eikonalMyocardiumDomain.C` probably never reads, since it reads from `eikonalSolverCoeffs`. Also, native `setup/post_processing_manufactured_eikonal_ecg.py` looks for `*manufacturedEikonalECGSummary.dat` without the `_ECG` suffix.

### 5.4b-N, niederer2011

- **Starts after R** (the rename) is on `main`. By then the old module is `tutorials/niederer_2011.py`.
- **Before**, at `2046cc9` under the old names: source `tutorials/niederer_2012.py` (468) + `defaults/niederer_2012.py` (92) = 560; tests `test_niederer_2012_write_channel.py` (127).
- **Native case:** `NiedererEtAl2011verification`. It moved in native `7a04349b`, and omniD's `defaults.CASE_DIR_NAME` still names the old path, which no longer exists.
- **Native `Allrun`:**
  - `blockMesh`;
  - `cardiacFoam` (or the parallel trio);
  - then, unconditionally, `postProcess -func Niedererpoints -latestTime` and `postProcess -func Niedererlines -latestTime`.
- **Native `system/controlDict`:** `startFrom startTime; startTime 0; endTime 0.015; deltaT 1e-05`. It includes both function objects.
- **The function objects:** both are `type probes` with `fields (activationTime)` and no `interpolationScheme`. `Niedererpoints` has 9 probe locations; `Niedererlines` has 101.
- **Native changes:**
  - `DefineConstant` in `setup/studies/tetConvergence/slab.geo.template` (in metres).
  - Rewrite both studies:
    - `"entry": "niederer2011"`;
    - `dx_values` → `dx` axis (hex) / `tetDx` axis (tet);
    - `dt_values` (ms) → `system/controlDict:deltaT` in seconds;
    - `end_time_by_dx` → an explicit `system/controlDict:endTime` per case. The hex study becomes a 9-case zip that lists dx, deltaT and endTime, because the old table maps dx to endTime (0.5→0.2, 0.2→0.08, 0.1→0.055);
    - `solvers ["implicit"]` → dropped.
- **Record** `records/niederer_2011.py`:
  - `native_case_relpath="NiedererEtAl2011verification"`.
  - Steps, with the ids the old DAG used:
    - `mesh`: `blockMesh`; consumes `system/blockMeshDict`;
    - `solve`: `cardiacFoam`. It consumes `constant/electroProperties`, `constant/physicsProperties`, `system/controlDict`, `system/fvSchemes`, `system/fvSolution`, `system/Niedererpoints` and `system/Niedererlines`, and produces `constant/electroProperties.withDefaultValues`;
    - `samplePoints`: `postProcess -func Niedererpoints -latestTime`;
    - `sampleLines`: `postProcess -func Niedererlines -latestTime`.
  - Variants:
    - `hex = (mesh, solve, samplePoints, sampleLines)`;
    - `tet = (gmsh, gmshToFoam, checkMesh, solve, samplePoints, sampleLines)`, with `slab.geo.template` → `slab.msh`.
  - The two probe files, `postProcessing/Niedererpoints/0/activationTime` and `postProcessing/Niedererlines/0/activationTime`, are declared as **plain literal paths**. They go on the step a real run shows writes each file **last**, as the first entry of that step's `produces`.
    - Which step that is must be observed, not assumed. The solve writes the probes at each write time. The `-latestTime` `postProcess` evaluates them again.
    - An archived Sep 15 run (`tutorialsTest-regression/`) held one data row at t = 0.015 in `…/0/activationTime`, next to empty `0.005/`, `0.01/` and `0.015/` directories.
    - Log what the run shows in `docs/solver-learning/cardiacfoam.md`: the writing step, the row count, the header lines and the empty directories.
  - Axes:
    - `dx`, in metres, the case's own length unit after `blockMeshDict`'s `scale 0.001`. It gives `hex_cell_counts` through `cell_counts_from_dx` over the slab extents, **read from `system/blockMeshDict`** (vertices × `scale`). There is no `SLAB_SIZE_MM` table, and it goes through P2's builder with one document and one block;
    - `tetDx` adds `-setnumber lc <dx>` to `gmsh`.
- **Parity:** every case of both studies. The old tet route writes through `_apply_case` alone, with its own regex `endTime` writer, so compare the committed documents.
- **Proof:** conformance parametrization with a coarse, short target: `base_study={"mesh": "hex", "dx": 0.0005, "system/controlDict:endTime": 0.015}`, which gives cells `(40 6 14)`; sweep `dx` `(0.0005, 0.001)`.
- **Delete:**
  - the module, its defaults and its write-channel test;
  - `_closest_key` and the regex `_update_end_time`;
  - `set_delta_t` and `apply_physics_property_overrides` lose this caller; delete each one that is left with none.
- **Edit:**
  - `test_registered_tutorials_need_no_repository.py`: its `test_niederer…_builds_under_any_base` goes, and the `built` pin drops by the factory names removed;
  - `test_all_packages_wheel_install.py`: `describe --entry niederer2011`; check that a record's payload still has `resolved_name`;
  - the reference-experiment fixture and every stale reference in §5d.
- **What topic B Task 7 needs from this record,** so that it can start straight after:
  1. The record `niederer2011` in `records/niederer_2011.py`, with step ids `mesh`, `solve`, `samplePoints` and `sampleLines`.
  2. `postProcessing/Niedererpoints/0/activationTime` as a **plain** path, at a stated index of a stated step. Its artifact id (`record.<step>.<index>`, from `record_execution.record_artifact_id`) is written in the record's docstring. Task 7 turns only that entry into `ProducedPath(path, "cardiacfoam_activation_probes")`. Declaring the format earlier would make C12 fail, because no reader exists yet.
  3. The path is literal, so `comparison._artifact`'s `{` refusal cannot bite, and Task 7's "open item" is closed. A study that changes `startTime` moves the file, and the comparison then reports it as a named `not_evaluated`.
  4. A helper in `packages/omnidriver-cardiacfoam/tests/cardiacfoam_native.py` (§5f): `niederer_run(tmp_path, *, dx, end_time=None) -> (case_root, probe DataArtifact)`, the counterpart of `opencarp_native.niederer_run`, and `niederer2011_conformance_target(tmp_path)`.
  5. The facts from the real run, in `docs/solver-learning/cardiacfoam.md`: which step writes the probe file last, the header lines, the row count, the `-1` spelling, and `activationTime`'s `dimensions` from the run's field file. Also the probes that are `-1` at the native `endTime 0.015`: the reference's columns 4, 5, 9 and 10, that is probes 2, 3, 7 and 8, all `-1`. That gives Task 7's `test_a_probe_never_reached_is_not_reached` its settings without a new run.
  6. Its conformance target passing C11, which is Task 7's own Step 3 precondition.

### 5.4b-P, manufacturedMonodomainPseudoECG (last in 5.4b)

- **Before:** source `tutorials/manufactured_monodomain_pseudo_ecg.py` (689) + `defaults/manufactured_monodomain_pseudo_ecg.py` (247) = 936; tests `test_manufactured_monodomain_pseudo_ecg_tet.py` (531) + `…_write_channel.py` (240) = 771, plus the pseudo-ECG class in `test_describe_proposed_changes.py`.
- **Needs** 5.4a and 5.4b-B landed, because their imports of this module must be gone.
- **Not blocked on the owner** (Status, corrected).
- **Native case:** `manufacturedSolutions/monodomainPseudoECG`. `Allrun` only solves. `regressionTest.sh` runs `blockMesh -dict system/blockMeshDict.3D`, then `./Allrun parallel`. `controlDict` has no `functions`; `sampleDict` is unused.
- **Native values that contradict Python:**
  - `monodomainSolverCoeffs.verificationModel.type` is `manufacturedAnisotropicMonodomainVerifier`, while the Python default is FDA. The native value is the default, and the Python default is deleted.
  - `ecgDomains.ECG.verificationModel.anisotropic no`. The design says to set it to `yes` natively and delete the derivation, but see §5g Q11.
- **Native changes:**
  - `DefineConstant` in `box.geo.template`.
  - `anisotropic` as §5g Q11 decides. After that change, run `regression/regressionTest.sh` on a clean copy; if the reference moves, stop and ask.
  - `cmp` the `monodomain_tet` overlays (`fvSchemes`, `fvSolution`) against `system/`. Delete each one that is identical. Entries that differ become study keys.
  - Rewrite the 4 committed studies. The mapping is as for bidomain; `verification_model_type` and `conductivity` become direct keys. `phi_tolerance` is a bidomain key and means nothing for monodomain, so drop it wherever it appears.
- **Record:**
  - variants: `hex = (mesh, solve)`; `tet = (gmsh, gmshToFoam, checkMesh, solve)`.
  - `solve` produces:
    - `constant/electroProperties.withDefaultValues`;
    - `postProcessing/*_cells.dat` (the anisotropic verifier always writes `3D_`);
    - `postProcessing/pseudoECG.dat`;
    - `postProcessing/manufacturedPseudoECG_ECG.dat`;
    - `postProcessing/manufacturedPseudoECGSummary_ECG.dat`.

    These are C++ names; the owner's ignored `postProcessing/` is from Aug 26 and uses older names. Confirm in a real run.
  - Axes:
    - `dimension` sets `monodomainSolverCoeffs.dimension` **and** `ecgDomains.ECG.dimension` together, which models the relation, plus the `-dict` and the 1D/2D electrodes as for 5.4b-E. The 3D electrode set restates native exactly, all 161 in order;
    - `numberCells`;
    - `tetNumberCells`.
- **Parity:** all 4 studies.
- **Proof:** conformance parametrization.
- **Delete:**
  - the module, its defaults, the two test files, and the pseudo-ECG part of `test_describe_proposed_changes.py`, which is re-hosted only if its behaviour survives elsewhere;
  - the helpers left with no production caller: `plan_dict_block`, `resolve_electro_property_ensure`, `openfoam.tet_mesh_provisioning.render_tet_geo` (its callers are bath, eikonalECG and pseudo-ECG; Niederer used its own `str.replace`), `openfoam.parallel_execution.solve_steps` (if Q6 drops the parallel route), and `_NUMERICS_PROFILES`/`_GRAD_SCHEME_TOKENS`.
- **Move** exactly what TL-EM still imports (`_build_cases`, `_case_output_filename`, and the constants its defaults import) into TL-EM's own module and defaults. It is the last caller, and the factory path stays only for it (§3).

## 5d. The stale Niederer references (added 2026-09-26)

Topic B's plan leaves these to this migration. The rename (R) changes names
only. Its uncommitted diff renames the six `source_reference` lines and
`registry.py`'s entry name and reference file. Whatever R leaves, 5.4b-N
does, in one commit with the evidence below.

**`equivalence_protocol.yaml`** (repo root; schema v1; header: "Do not edit a
tolerance after seeing a comparison result; add a new row with its own
rationale"):
- **The six rows with `case_dir: NiedererEtAl2011/NiedererEtAl2011verification`
  are stale in three ways:**
  - the case directory moved (native `7a04349b`);
  - the reference was renamed from `NiedererEtAl2012.reference` to
    `NiedererEtAl2011.reference` (native `924bc72ec`);
  - the values changed in native `39fe76eb0` (2026-08-26, "faster Niederer
    TNNP case"). `time` went from `0.03` to `0.015`, and column `10` from
    `0.02396` to `-1`.

  They are replaced, not edited (§5g Q12), by six rows transcribed verbatim
  from the current `regression/NiedererEtAl2011.reference`. Every new row
  has:
  - `case_dir: NiedererEtAl2011verification`;
  - `data_file: Niedererpoints/0/activationTime`;
  - `time: 0.015`;
  - `tolerance: 0.0001`, unchanged;
  - `source_reference: regression/NiedererEtAl2011.reference`.

  Their `variable`/`expected` pairs are `'2'` `0.00119338`, `'4'` `-1.0`,
  `'6'` `0.0112286`, `'10'` `-1.0`, `'5'` `-1.0` and `'9'` `-1.0`. Each new
  row's rationale says it is transcribed from the reference as of
  `39fe76eb0`/`924bc72ec`, and that it replaces a row whose source no longer
  exists. The rows involve no threshold chosen after seeing a result.
- **The three rows with `case_dir: NiedererEtAl2011/electroMechanicalNiedererEtAl2011`**
  (`Taprobes/solid/0/Ta`, variables `2`/`3`/`4`) are deleted. Native
  `7a04349b` removed the case. Its successor,
  `electromechanicsProtocols/springSupportedSlab`, has a different reference
  (`springSupportedSlab.reference`), and it is not added here (§5g Q12).

**`packages/omnidriver-cardiacfoam/tests/regression_equivalence/`:**
- `registry.py`: the Niederer row becomes `RegressionCase("NiedererEtAl2011verification", "niederer2011", (_ELECTRO, _PHYSICS), "regression/NiedererEtAl2011.reference")`. The `NiedererEtAl2011/electroMechanicalNiedererEtAl2011` row is deleted.
- `test_cli_matrix.py`: delete its filter on the EM case.
- `test_dual_run.py`: `_SERIES_CASE` becomes `"NiedererEtAl2011verification"`.
- `staging.py`: its comment naming the old layout gets a dated correction.
- `test_staging.py`: the mapped Niederer entry now resolves as `"tutorial_record"` (§2 item 5).

**Also stale and fixed in 5.4b-N:**
- `tests/fixtures/reference_experiments/niederer_tissue.json`: `source_case_root` and every `source` path go to `tutorials/NiedererEtAl2011verification/…`. The survey found all 12 input sha256 values unchanged at the new path; re-check that before committing.
- `test_reference_experiment_manifests.py`'s expected case path.
- `defaults.CASE_DIR_NAME`, which is deleted along with the module.

**Not stale:**
- `benchmarks/niederer2011.json`: it has no case path, and its frame maps to the native probes via `(x, 7−z, y)`;
- `equivalence_protocol.yaml`'s `data_file` path.

## 5e. Order and parallelism (added 2026-09-26)

Prerequisites:
- **P1, native base.**
  - Merge the owner's `feature/spring-supported-slab-tutorial` (`c15e2fcf`) into `omnid/tutorials-are-pointers`, in a native worktree, with no force-push (§4, §5g Q1).
  - Point `OMNIDRIVER_NATIVE_TUTORIALS` at that worktree's `tutorials/`.
  - Prove the pilot's `-m native` tests pass there before any 5.4 native change.
- **P2, the block-mesh axis** (`omnidriver-openfoam`, decision (d)). `block_mesh_resolution_axis` takes the following, each refused by name:
  - one or more documents;
  - an `expected_blocks` stated by the record;
  - a resolution callable that also sees each file's current counts, which makes "a direction at 1 stays 1" a reusable resolution.

  One count is written to every `hex (` block. The writer
  (`overrides._target_for_parameter`) and the reader
  (`environment._read_config_value_by_key_path`) take the block count through
  the patch rather than defaulting to 1. The reader answers the triple every
  block shares, and refuses blocks that disagree.
  - Tests: extend `test_axes_block_mesh_resolution_native.py` over bath's three files and bidomain's.
  - The pinning test `test_the_axis_produced_value_still_refuses_the_wrong_block_count_when_rendered` changes, and its expectation says why.

  No core change and no owner decision is needed; decision (d) is the owner's.
- **P3, core record additions**, as the owner answers §5g:
  - Q2, `default_variant`;
  - Q3, a step's replaceable default arguments;
  - Q4, a removal patch;
  - Q5, `reads_also`.

  Each lands on `main` as its own commit, with a generality-log row (§5) and
  a toy-record test. Q2 and Q3 are needed by every 5.4 record; Q4 and Q5
  only by bath.
- **P4, the cardiacFOAM conformance target:** conformance Task 14, all four steps (§5f).
- **P5, the gmsh facts, from the real binary:**
  - that `gmsh -3 X.geo.template` parses an unknown-extension file as a `.geo` script;
  - that `-setnumber lc v` overrides `DefineConstant[ lc = … ]`.

  Log both in `docs/solver-learning/cardiacfoam.md`. If gmsh refuses the
  extension, stop: renaming the template to `.geo` collides with the OpenFOAM
  layer's `generated_file_suffixes` (`.geo` is dropped at staging and
  git-ignored natively), and the owner decides.

| step | needs | parallel with | blocked on the owner |
|---|---|---|---|
| R (rename) | — | everything except 5.4b-N | no |
| P1 | — | P2, P4, P5 | **yes**, Q1 |
| P2 | — | P1, P3, P4, P5 | no |
| P3 | the answers | P1, P2, P4, P5 | **yes**, Q2–Q5 |
| P4 | — | P1, P2, P3, P5, 5.4 sub-steps 1–5 | no |
| P5 | the gmsh binary | everything | no |
| 5.4a bath | P1, P2, P3 (all four), P5; proof needs P4 | 5.4b-B, 5.4b-E, 5.4b-N, 5.1 | Q4, Q5, Q6, Q8, Q10 |
| 5.4b-B bidomain | P1, P2, P3 (Q2, Q3), P5; proof P4 | 5.4a, 5.4b-E, 5.4b-N, 5.1 | Q7, Q9 |
| 5.4b-E eikonalECG | as 5.4b-B | 5.4a, 5.4b-B, 5.4b-N, 5.1 | Q8 |
| 5.4b-N niederer2011 | R, P1, P2, P3 (Q2, Q3), P5; proof P4 | 5.4a, 5.4b-B, 5.4b-E, 5.1 | Q12 |
| 5.4b-P pseudo-ECG | 5.4a **and** 5.4b-B landed (imports); P1–P5 | 5.4b-E, 5.4b-N, 5.1–5.3 | Q11 |
| topic B Task 7 | 5.4b-N (and so P4) | 5.4b-P, 5.1–5.3 | no |
| topic B Task 8 | Task 7 | anything | no |
| 5.1 singleCell | P1, P4 | any 5.4 step | no |
| 5.2 cable1DRestitution | P1, P4 | any 5.4 step | no; decision (b) is made |
| 5.3 cable1DCVConvergence | 5.2 (same native case `cableProtocol`) | any 5.4 step | no |
| conformance Task 15 | P4 | any tutorial step; not concurrent with C | no |
| C | 5.1–5.4 and 5.5's decision | — | 5.5 (file placement) |

- **Independence and conflicts.** Steps listed as parallel touch different
  tutorial modules and native case folders. They share the small files named
  in §4. Each such conflict is a rebase, not a design clash.
- **Keeping 5.4a first.** The owner chose "hardest first" so that bath
  exposes the core's gaps first. It still does, because P3 is driven by
  bath's needs. The other 5.4b tasks may run beside it once P1–P3 land.
- **What waits on the owner:** P1 (Q1) and P3 (Q2–Q5) block every 5.4
  record. Nothing blocks P2, P4, P5 or R, and the first task below starts
  with no answers at all. The pseudo-ECG files are **not** a blocker; see
  the Status correction.

**Recommended first task for the migration agent: P2.** It needs no owner
answer and no native change. It touches only `omnidriver-openfoam`, has a
native drift test, and unblocks 5.4a and three of the four 5.4b tutorials.
Decision (d) already specifies it. If a second agent is available, run P4
beside it.

## 5f. Conformance Tasks 14 and 15: when they unblock (added 2026-09-26)

`2026-09-25-solver-conformance-and-opencarp.md` holds both tasks "after
tutorials-are-pointers step 5 is finished".

- **Task 14 (cardiacFOAM as a conformance target) is unblocked now, as P4.**
  It does not need step 5 finished.
  - Its steps 1–3 target `restitutionCurves`, which has been a record on
    `main` since `46bd2f0`.
  - Its step 4 (C10: `get_record_key_catalog`/`get_agent_guidance`, the
    `<name>` key-template segment and the one-catalogue `describe`) is
    cardiacFOAM and core work that no tutorial migration touches.
  - The reason it waited, "its records are owned there until then", is
    settled by sequencing. P4 runs before any 5.4 record is written, and
    `records/restitution_curves.py` is edited only by P4.
  - It must be **finished before any 5.4 record's proof sub-step**, because
    §2 item 6 has every record pass all of `CHECKS`, C10 included. A
    parametrization that leaves C10 out would be a waiver.
  - Its step 1 must add `constant/electroProperties.withDefaultValues` to
    the solve step's `produces` (§2 item 1). Otherwise its C11 fails with
    "carried".
    **Corrected 2026-09-26 (P4, by real runs):** not for `restitutionCurves`.
    Its solver, `singleCellSolver`, overrides `electroModel::end()` without
    calling it, and no run of the case writes the file
    (`docs/solver-learning/cardiacfoam.md` R4). Declaring it would fail C6;
    C11 passes without it. So no shared constant was added yet: the first
    record whose solve step writes the file (every 5.4 record, by source)
    adds it, as §5g Q13 recommends.
  - It creates `packages/omnidriver-cardiacfoam/tests/cardiacfoam_native.py`,
    a uniquely named module (CLAUDE.md's conftest trap). It holds
    `native_tutorials_root()`, which three pilot tests each copy today, and
    one `*_conformance_target(tmp_path)` per record. Every 5.4 record adds
    its own target there and joins the parametrization.
  - Its closing line, "when all of them pass, the old factory path can be
    deleted", is step C.
- **Task 15 (the OpenFOAM half of K3 layer ownership) is unblocked now too.**
  - It never needed a record. It waited only because it edits cardiacFOAM's
    `plugin.yaml`, which no 5.4 task edits. If §5g Q13 chooses conventions
    over `produces`, that task edits the OpenFOAM or cardiacFOAM conventions
    and must not run beside Task 15.
  - A5 already landed its core half (`CORE_RUNTIME_RECORDS`).
  - Run it after P4, so that cardiacFOAM's C1–C12 are the baseline it must
    keep green. Do not run it concurrently with step C.
  - Its guard `test_no_plugin_declares_cores_own_files` fails today on
    `openfoam_case_runtime_conventions()`, which still lists
    `workflow_state.json`, `run_document.json`, `sweep_manifest.json` and
    `workflow_logs`. That failure is the work.

## 5g. Questions for the owner (added 2026-09-26)

Each question has a recommendation. Q1–Q5 block work; the rest are needed
only by the task named.

- **Q1, native base.** Merge `feature/spring-supported-slab-tutorial` (`c15e2fcf`) into `omnid/tutorials-are-pointers`, and do all native work in a worktree of that branch? *Recommend: yes. Merge, do not rebase, because the branch is on `origin`.* Say whether the owner would rather land the spring-slab branch on native `main` first and base the native branch there.
- **Q2, default route.** Every 5.4 record has a tet variant, and today a variant record refuses `describe` and C2 with no study values. Add a neutral `TutorialRecord.default_variant`, meaning the route the native `Allrun` runs? *Recommend: yes. It is "the native case is the default", applied to routes.*
- **Q3, default mesh arguments.** Bidomain, eikonalECG and pseudo-ECG have no plain `system/blockMeshDict`, and an axis can only append arguments. Add a neutral `WorkflowStep` field for default arguments, used when no axis contributes (`-dict system/blockMeshDict.3D`, copied from the native `Allrun`/`regressionTest.sh`)? *Recommend: yes.* The alternatives are to make `dimension` mandatory, which breaks C2, or to add a native plain `blockMeshDict`, which duplicates a file the way bath's `blockMeshDict` already duplicates `.1D`.
- **Q4, removal.** bath's `groundElectrode` must remove `surfaceCurrentPatches.xMin`, because the C++ is fatal on a patch listed in both. Add a removal kind to `AxisPatch`, mapped onto `case_write`'s existing `operation="remove"`? *Recommend: yes.* The alternative is a `mapping`-valued key that replaces the whole `surfaceCurrentPatches` dictionary, but only if the renderer replaces rather than merges, which is unverified.
- **Q5, a second study value.** bath's `phiERefPoint` needs the dimension and N. Build the `reads_also` contract the design sketched in step 3's note, where the named value is passed when the study gives it and the case's own counts are used otherwise? Or use one `mapping`-valued bath axis? *Recommend: `reads_also`. It keeps decisions (d) and (e) as made.*
- **Q6, parallel route.** Drop `decomposePar`/`mpirun`/`reconstructPar` from the 5.4 records for now? The reasons: one selector would multiply the variants, and `-np` would restate `decomposeParDict`. *Recommend: drop now, serial only, and record a follow-up for a parallel variant whose rank count an axis reads from `decomposeParDict`.* This supersedes §5a's open question.
- **Q7, where mesh steps come from** when `Allrun` does not mesh (bidomain, pseudo-ECG). *Recommend: copy them from the case's own `regression/regressionTest.sh` and cite it, with no native `Allrun` change.*
- **Q8, tet routes and the `lc` default.** No native `Allrun` has a tet route. Declare it in records, citing the template and study READMEs? *Recommend: yes, with no `Allrun` change.* And which default `lc` should each `DefineConstant` carry? *Recommend: the coarsest level its own tet study uses: `1/10` for the boxes, `0.0005` m for Niederer's slab.*
- **Q9, bidomain's ODE kwargs.** `ode_abs_tolerance 1e-10`/`ode_rel_tolerance 1e-8` appear in all 7 studies and were never applied; `make_spec` refuses them. *Recommend: drop them, and correct the temporalConvergence README that claims them. This keeps the regression reference valid. Make them real `bidomainSolverCoeffs.absTol`/`relTol` keys only if the owner wants that numerics.*
- **Q10, bath's studies and overlays.** Keep all 14 studies, and delete the byte-identical tet overlay files natively (bath's `fvSchemes`, bidomain's `fvSchemes`, eikonalECG's `fvSolution`, and pseudo-ECG's if identical)? *Recommend: keep all 14, and delete the identical overlays.* This supersedes §5a's open question on obsolete studies.
- **Q11, pseudo-ECG `anisotropic`.** The design (2026-09-24) says set `yes` natively. Native `7ae47527c` (2026-09-09, "add anisotropic pseudo-ECG reference") set `no`. Is `yes` still wanted? *Recommend: confirm before 5.4b-P; if yes, re-run `regressionTest.sh` and stop if the reference moves.*
- **Q12, equivalence protocol.** Replace the six Niederer rows with rows transcribed from the current reference, delete the three EM rows, and do not add `springSupportedSlab` (§5d)? *Recommend: yes. The protocol's "add a new row" rule is about a tolerance chosen after seeing a result; these rows' source no longer exists, and no tolerance changes.*
- **Q13, `withDefaultValues`.** Declare `constant/electroProperties.withDefaultValues` on each record's solve step, as one shared constant in `records/`, so C6 checks it and A5 excludes it? Or once in cardiacFOAM's case-runtime conventions? *Recommend: the shared `produces` constant. It is checked, and it does not touch Task 15's files.*
- **Q14, the six exploratory temporal sweeps.** They were deleted from the working tree at 14:04 today; a copy survives under the git-ignored `tutorialsTest-regression/`. Was that intended? *Recommend: yes. Nothing to commit; pseudo-ECG does not need them.*

### 5g answered (owner, 2026-09-26)

These answers govern. Where one differs from a recommendation above, the answer wins.

- **Q1, native base: merge.** The controller makes a native worktree of `omnid/tutorials-are-pointers` and merges `feature/spring-supported-slab-tutorial` into it, including `c15e2fcf` (the dead-key removal) and `044559d2` (the `niederer2011` rename). All native migration work happens in that worktree. Nothing is pushed. The owner's checkout is not touched.
- **Q2, Q3, Q7, Q8 are one decision: blockMesh is always the default, and gmsh is an optional extra mesher.**
  - Every record's default route is the blockMesh route (`default_variant`).
  - The default mesh arguments are the ones the case's own `regression/regressionTest.sh` uses: `-dict system/blockMeshDict.3D` for bidomain, pseudo-ECG and eikonalECG, and `.1D` for bath. They are fixed on the step and independent of any study. A study replaces them.
  - The native `Allrun` of bidomain and pseudo-ECG does not mesh at all; it goes straight to `cardiacFoam`, and neither case ships a mesh. This is a native gap. **Recommended native fix, to be confirmed:** add the regression test's `blockMesh` line to those two `Allrun`s, so the native default is self-contained, as eikonalECG's already is.
  - The tet route (gmsh) is declared in the record as the alternative a study picks.
  - **The gmsh templates change natively to `DefineConstant[ lc = {<coarsest>, Name "lc"} ]`**, and the record runs `gmsh -3 <template> -setnumber lc <v>` (evidence: `docs/solver-learning/cardiacfoam.md` G1–G6). gmsh stays outside OpenFOAM's layer; nothing OpenFOAM-side needs to know about it. The template comments that name deleted scripts are corrected.
- **Q4, removal: first try replacing the whole sub-dictionary.** A study sets `bathPotentialDomain.surfaceCurrentPatches` and `.groundPatches` as whole dictionaries (`{ xMax 0.01; }`, `{ xMin 0; }`). Verify on the real file that the case writer **replaces** a sub-dictionary rather than merging into it. Add a removal kind to `AxisPatch` only if it merges, and say so.
- **Q5, the reference point: no new contract.** `phiERefPoint` is a case fact the user or agent chooses by reasoning. The native case already fixes `(-0.9 0.05 0.05)`. The Python's half-cell shift existed only because a point on a cell face is claimed by two partitions in a parallel run. Guidance gets one line: choose a point in a cell interior at every resolution the study uses. `reads_also` is not built.
- **Q6, serial and parallel belong to the OpenFOAM layer, which must know about them.** A record declares its solve step once. Running it serial (the native `Allrun` default) or parallel (`decomposePar` → `mpirun -np N` → `reconstructPar`, with N read from `decomposeParDict`, never restated) is the OpenFOAM layer's job, through its existing `parallel_execution`. Records don't carry parallel variants. Serial is the default.
- **Q9: delete** the `ode_abs_tolerance`/`ode_rel_tolerance` references from bidomain's studies and its temporalConvergence README (natively).
- **Q10: keep all 14 bath studies; delete the byte-identical tet overlay files natively.**
- **Q11: get the physics right.** `ecgDomains.<name>.verificationModel.anisotropic yes` exactly when the tissue verifier is `manufacturedAnisotropicMonodomainVerifier`. The native pseudo-ECG case uses that verifier with `anisotropic no`, which is wrong, so it changes natively to `yes`. The catalog must make the relation clear: the `anisotropic` entry's description states it, and validation refuses a mismatch by name. This models the relation between two existing keys, adding no new key. Re-run the pseudo-ECG `regressionTest.sh`. If its reference numbers move, regenerate the native regression reference and report old against new.
- **Q12, Q13:** recommendations as above. Q13 is corrected by P4's R4: `withDefaultValues` is declared only by records whose own run writes it.
- **The pre-processing stage (owner, 2026-09-26, later the same day). This governs how every record gets its starting state.**
  - What a solver needs before it runs is a **starting state**: a mesh, and possibly fields, graphs or other anatomy. Producing it is the record's **pre-processing stage**: the steps before the solve. There are two kinds of provider, and both give the solve a mesh to start from:
    - **generated**: the case owns a recipe and each run rebuilds from it. The default is blockMesh, with the OpenFOAM default `system/blockMeshDict`, or the dict the case's own scripts name (e.g. `.3D`, `.1D`). The gmsh tet route (`gmsh -3 <template> -setnumber lc <v>`, then `gmshToFoam`) is an alternative generator, not a different kind;
    - **supplied**: a finished artifact brought in, not rebuilt. Examples are the idealized heart's shared `../mesh` (mesh plus `0/` fields plus Purkinje graphs) and cardiacCore patient meshes. A path the native case names is native fact. Anything from outside the native tree is supplied by the user or agent, never discovered.
  - **Keep it general and loose, not tight.** Core knows only steps, inputs and outputs, a default route and replaceable default arguments. The record declares the **default** pre-processing, taken from the native case, and does not enumerate every possible route. An agent reads the native case (`Allrun`, `regressionTest.sh`, the READMEs, the studies) and chooses or composes another route through study values and step arguments. The agent guidance says so. Determinism is kept where it's checkable: what ran, what it read and wrote, and the fingerprints. Choices stay with the agent.
  - `Allrun` is a convenience for humans. A record mirrors its commands and doesn't call it, because `./Allrun` would hide where the starting state came from. No native `Allrun` change is needed for bidomain or pseudo-ECG: their split (solve only, with the mesh made by the regression test) is already the general shape.
  - **Supplied inputs for a record are a named later item (S),** designed once when the first idealized-heart or cardiacCore case migrates. They are not built in 5.4, because every 5.4 case generates its mesh.
- **P4 extras, deferred:**
  - filtering catalogue coefficient keys by `myocardiumSolver`;
  - a guard in the native-tree helper that refuses a dirty git checkout. Recommended soon.

## 5. Generality log

Added 2026-09-26: each core addition §5e P3 makes (§5g Q2–Q5) adds a row here
when it lands, stream `tutorials`.

| date | stream | core change | why | verdict |
|---|---|---|---|---|
| 2026-09-24 | tutorials | tutorial records, axes, study-name sorting, conflict refusal, the `validated` flag | the design itself | neutral: no solver vocabulary; guarded by the import and case-write gates |
| 2026-09-25 | tutorials | `configurationSource` on the run document | planning and execution disagreed for case-sourced runs | neutral |
| 2026-09-25 | tutorials | P1: records through `plan`/`run --strict`; P2: snapshot seeding plus the `exists_before` refusal | found by the openCARP design tracing a record; P2 would silently lose keys for any non-OpenFOAM renderer | neutral: both solver-independent |
| 2026-09-25 | tutorials | the `mapping` value kind for axis values | the S1-S2 protocol axis | neutral |
| 2026-09-25 | openCARP | K4: `WorkflowStep` gains `produces`/`consumes` (case-relative paths); the DAG's per-step dict and `record_case_spec`'s `expected_artifacts` derive from them (`022688f`) | a record step declared no outputs or inputs, so C5/C6 could not check a run actually wrote anything, and C8 could not check provenance covered a step's inputs | neutral: no solver vocabulary; both fields default to `()` so every existing record is unaffected. Amended 2026-09-25 (fix round 1): a step's own `produces` is now **unioned** with its command's utility-manifest `produces` in `normalize_workflow_dag`, not a replacement (`09d205c`, review I6), so declaring `produces` on a utility step no longer re-credits the manifest's artifacts to the last solver step; no step in `packages/*/src` relied on replacement. `__post_init__` also refuses a bare `str`, `""`/`"."`, braces and non-`str` items (`dbf6692`, M1) |
| 2026-09-25 | openCARP | K8: `sweep_runner._record_sweep_run` keeps each case's child `artifact_reconciliation` (new `_child_reconciliation`) (`e14906b`) | a sweep discarded the child `run --run-document`'s reconciliation with the rest of its stdout, so no record of a sweep said whether a case produced its declared outputs; C7 needs it per case | neutral |
| 2026-09-25 | openCARP | the `omnidriver.conformance` package, C1-C9 (`5efd986`, `9149ac2`, `022688f`, `e14906b`, `0aea2da`, `4be1e0f`) | an executable, solver-agnostic definition of "a solver can plug into omniD", exercised over a toy plugin so a third-party solver's authors can run it against their own; several checks (C4, C8) are written specifically because they catch known historical defect classes (P2's sibling-key loss; unfingerprinted inputs) | neutral: ships in core's wheel, imports nothing solver-specific, discovers nothing (`future/ENVIRONMENT_CONTRACT.md` §12) |
| 2026-09-25 | openCARP | the `string` value kind (K6) | openCARP's String/RFile/WFile parameters may be empty or contain spaces; `word` refuses both | neutral |
| 2026-09-25 | openCARP | a broken plugin entry point is refused by name instead of breaking discovery for every stack (`plugin_discovery.BrokenPluginError`) | one unimportable entry in `omnidriver.plugins` raised a bare `ModuleNotFoundError` out of default selection and out of an explicit `--plugin` for an unrelated, working stack; found while adding `omnidriver-opencarp` before its plugin module existed | neutral: no solver vocabulary; refuses rather than skips |
| 2026-09-25 | openCARP | the record surface: describe lists any record's axes, keys, guidance and case documentation (C10) -- new optional-neutral capability `record_surface` (hooks `get_record_key_catalog(case_root)`, `get_agent_guidance()`, both `sequence`), `runtime.record_surface.record_surface`, and conformance check C10 | `describe` showed cardiacFOAM's keys only through `dict_entries` and nothing for openCARP, so an agent had to know which solver it faced to find what it may address; the native README was human-only | neutral: no solver vocabulary (shape and vocabulary gates pass); both hooks degrade to empty, which C10 reports as a failure rather than a skip; `[Int]` is documented as generic index notation. Not yet implemented by the cardiacFOAM or openCARP stacks, so C10 fails for both until they declare the hooks. Corrected 2026-09-25: openCARP now declares both hooks and passes C10 against the real binary (Task 11, `5b7fb2d`); only cardiacFOAM still fails it |
| 2026-09-25 | openCARP | **no core change needed** (Task 11: `OpenCARPPlugin` and `niedererNVersion`) | `OpenCARPPlugin` implements the plugin contract and the `niedererNVersion` record entirely inside `packages/omnidriver-opencarp`, declaring `config_value`, `case_value_comparison`, `environment_preflight`, `command_authorization`, `case_writer` and `record_surface`; C6/C7 needed `is_case_runnable_without_workflow` (already part of the optional `CaseCompatibilityCapability` contract from an earlier task, unused by any prior adapter's own test), which the plugin now implements | proof that core's existing seams are enough for a solver outside OpenFOAM: all ten conformance checks (C1-C10) pass against the real openCARP v18.1 binary with zero lines changed under `packages/omnidriver/src`. **Corrected 2026-09-25 (wave-2 review I4):** "no core change needed" was not quite true. The plugin's `is_case_runnable_without_workflow` answered a question core should not have asked of a record run: whether a case *without* driver-owned workflow metadata is runnable, when a record run document carries its record's steps. It told core something record-specific (`nversion.par` exists) to get past an OpenFOAM-era gate in `run_document_exec`. Core now exempts a record run carrying its steps from that gate (the I4 row below), and the hook is gone from `OpenCARPPlugin` |
| 2026-09-25 | openCARP | K9: step logs are redacted by plugin-declared patterns before they are kept -- new `RuntimeEvidenceCapability` member `log_redaction_patterns()` (hook `get_log_redaction_patterns()`, composed as `set`), and `workflow_runner.redact_step_logs`, applied to a step's stdout/stderr log right after its process finishes | openCARP's build header prints a CI token in every run, and omniD keeps solver stdout in `workflow_logs/`, so that credential would be copied into every run record verbatim | neutral: no solver vocabulary; the member degrades to an empty set for a plugin that declares nothing, so an undeclaring plugin's logs are untouched (no compatibility fallback, matching `RuntimeEvidenceCapability`'s existing members). Proved end to end over the toy plugin (`LogRedactingPlugin`, `packages/omnidriver/tests/plugins/conformance_toy.py`) rather than openCARP's real plugin, which does not exist on this branch yet (Task 11, a sibling worktree). Corrected 2026-09-25: it exists now, and `test_conformance_native.py::test_no_token_survives_in_workflow_logs` (`9cbccfd`) proves K9 against the real openCARP binary. Amended 2026-09-25 (wave-2 review I3): the contract is now **every match is replaced whole by `[REDACTED]`**; the runner used to keep capture group 1, so the conventional `password=(\S+)` kept the secret and dropped its label. The hook and Protocol docstrings say so; the toy's and openCARP's patterns became `(?<=://)[^/\s@]+(?=@)`, which matches only the credential |
| 2026-09-25 | openCARP | I2 (wave-2 review): `record_execution.commit_record_case` turns a `ValueError` the case writer raises while resolving or rendering into a `TutorialRecordError` naming the record and the document(s), the original message kept and chained with `from` (`_refusal_as_record_error`) | a validator refusal reached `plan --strict` as JSON, but a renderer refusal (openCARP's F2 index bound, raised as `ParFormatError` at render) escaped as a traceback with empty stdout, so the shape of a refusal depended on which layer refused | neutral: no solver vocabulary; a `ValueError` is the case writer's documented refusal type, and any other exception still propagates as itself. Tested through the CLI with a toy renderer and resolver (`test_cli_plan_strict_tutorial_record.py`) and with openCARP's F2 refusal against the real tutorial (`test_plan_refusals_native.py`) |
| 2026-09-25 | openCARP | I4 (wave-2 review): `run_document_exec.build_execution_inputs` no longer asks the adapter's `is_case_runnable_without_workflow` for a tutorial-record run whose document carries its steps (`_is_record_run_with_steps`: planner-stated `resolvedEntry.entryKind == "tutorial_record"` and a non-empty `workflowDag.steps`); every other run document is gated exactly as before | the hook's contract is whether a case *without* driver-owned workflow metadata is runnable, but a record run's document *is* that metadata. openCARP and the toy record plugin declared the hook only to pass the gate, and cardiacFOAM's records passed it only through an `Allrun` they never use | neutral: no solver vocabulary; the gate is narrowed for record runs only (tested both ways in `test_run_document_exec.py`), and a toy record plugin with no hook passes C5-C7 (`test_conformance_toy.py`). The hook was deleted from `OpenCARPPlugin` and from `E2ERecordPlugin`, which needed it only for record runs; cardiacFOAM keeps its own, which serves non-record case folders |
| 2026-09-25 | openCARP | S-I2 (final review; A-M5, W2-M2): conformance C9 removes the empty PATH it supplied from each preflight message, then requires the solver command as a quoted token (`checks._quotes`, now also `_names`' first rule) instead of `solver_command in m` | a preflight that never named the solver passed C9 whenever the PATH it echoed, which lives under `scratch_root`, contained the solver's name (`~/openCARP-runs/`): a false certification | neutral: no solver vocabulary; stricter, never looser. Bite test `test_c9_is_not_satisfied_by_the_solver_name_in_the_echoed_scratch_path_S_I2` (toy `AuxiliaryOnlyPreflightPlugin`, four scratch spellings); the toy and openCARP already quote the command, and still pass C9 |
| 2026-09-25 | openCARP | S-M1 (final review): `record_execution._resolve_and_split` hands `split_unchanged` the config-value reader wrapped by `_reader_refusing_as_record_error`, so a `ValueError` the reader raises becomes a `TutorialRecordError` naming the record and `document:key`, chained (`_refusal_as_record_error` gains `refused_by`); `cli describe` reports a `TutorialRecordError` as the same JSON failure `plan --strict` does | the config reader is a third refusal layer (openCARP's F1/F10 `ParFormatError`), and its refusal escaped `plan --strict` and `describe` as a traceback with empty stdout, the class I2 closed for the case writer | neutral: no solver vocabulary; `split_unchanged` still propagates the refusal, never reading it as "changed"; a non-`ValueError` still propagates as itself. Tested over a toy reader (`test_cli_plan_strict_tutorial_record.py`) and openCARP's F10 refusal on a copied tutorial (`test_plan_refusals_native.py`) |
| 2026-09-25 | openCARP | S-I3 minimum (final review): `strict_planning`'s record branch turns a `PermissionError` while staging into a `TutorialRecordError` naming the staged path and `OMNIDRIVER_SCRATCH_DIR`, so the CLI reports it as its JSON failure; the scratch default itself (`<cases_root>/.omnidriver`) is unchanged | with the variable unset, `plan --strict` against openCARP's root-owned installed tutorials tree died with a `PermissionError` traceback and empty stdout | neutral: no solver vocabulary; a refusal, not a fallback, and no change to where scratch resolves. Tested over a read-only toy tree (`test_cli_plan_strict_tutorial_record.py`); the supplied-scratch-root K-change stays the owner's decision Corrected 2026-09-26: fixed -- the default is gone, see the next row |
| 2026-09-26 | core generality (A) | A5: `core/runtime_records.py` -- `CORE_RUNTIME_RECORDS` (every file core writes into a case: `workflow_state.json`, `run_document.json`, `sweep_manifest.json`, `case_record.json`, the attempt lock and its guard, `workflow_logs/`, the case-transaction directory) merged into every stack's conventions by `_CaseRuntimeConventionsAdapter.conventions`; record staging also drops each step's `produces` (`record_generated_relpaths`, minus paths a step consumes); conformance C11; openCARP's record declares its full outputs (F15) | openCARP declares no conventions, so staging a case a run had written carried that run's state and `out/` into the new stage | neutral: no solver vocabulary; C11 fails first for the toy and openCARP (`test_toy_passes[C11]`, `test_niederer_passes[C11]`) and passes after |
| 2026-09-26 | openCARP | the scratch root is supplied (`--scratch-dir` / `OMNIDRIVER_SCRATCH_DIR`) or refused by name; no default under cases_root. `core.specs.paths.scratch_root(base)` is replaced by `resolve_scratch_root(supplied, *, cases_root=)` (lazy; refuses with `ScratchRootNotSupplied`, and a root inside cases_root with `ScratchRootInsideCasesRoot`, both `TutorialRecordError`s so the CLI prints JSON); `strict_plan(..., scratch_root=)`, `default_sweep_output_dir(spec, scratch_root=)`, CLI `--scratch-dir`; the conformance suite passes `target.scratch_root` explicitly and no longer mutates `os.environ` (`_scratch_environment` and its lock deleted) | planning a record wrote `<cases_root>/.omnidriver` into native tutorials trees, and failed with `PermissionError` on a read-only install (openCARP's `/usr/local/lib/opencarp/share/tutorials`); a scratch location has no ambient truth, so defaulting one invented it (ENVIRONMENT_CONTRACT §12) | neutral: no solver vocabulary; removes a default rather than adding a mechanism. Guarded by `test_the_scratch_resolver_invents_no_default` and `test_nothing_rebuilds_a_dot_omnidriver_scratch_default` |
| 2026-09-26 | results-as-quantities | `ProducedPath(str)`: a record step's `produces` entry may name its format; `record_step_artifacts` passes it (`format` was always `"file"`) | a result reader is chosen by artifact format, and every record output looked the same | neutral: the format string is plugin vocabulary core never reads; a `ProducedPath` is its path, so every existing reader of `produces` (A5's staging exclusion included) is untouched |
| 2026-09-26 | core generality (A) | A3: `get_dict_entries`, `get_dict_groups`, `get_dictionary_catalog`, `get_tutorial_displays` are optional-neutral (adapters answer `()`/`{}`/`DictionaryCatalog({})`/`()`; `_declared_dict_entries` feeds validation and identity); the stubs in the OpenFOAM layer, openCARP and both minimal test plugins are deleted; `get_tutorial_catalog` stays required | every plugin had to stub dictionary-shaped members core has no record-path need for | neutral: every provider digest unchanged and the cardiac stacks' identities unchanged (`test_the_cardiac_stack_identity_is_unchanged_by_deleting_the_stubs`); `opencarp` and standalone `openfoam-environment` now record `dictionaries` as `<unclaimed>` -- their stub had been its false winner |
| 2026-09-26 | core generality (A) | A6: `get_heterogeneity_models`, `get_electro_property_entry_groups` move to `omnidriver.cardiacfoam.dict_entries`, and `cardiacfoam_monorepo_root` to `omnidriver.cardiacfoam.monorepo` (core and openfoam conftests keep a test-local walk); CLI help names no solver or tutorial; `check-wheel-artifact.py` probes `all_documented_driver_paths` | core carried cardiac vocabulary with no core caller | neutral: guarded by `test_core_carries_no_cardiac_names.py` |
| 2026-09-26 | core generality (A) | A7: `strict_planning._is_nondimensional_entry` (exempted a case by "manufactured"/"verification" in its name) deleted; `_mesh_geometry_exempt` asks only the plugin hook and `generic_case`; `SKIP_MESH_DIAGNOSTICS` renamed `SKIP_GEOMETRY_DIAGNOSTICS` (`strict_audit.SKIP_GEOMETRY_DIAGNOSTICS_ENV`); cardiacfoam's hook finds electroProperties through the new physics layout table (`physics_layout.json`, one row per physics type; region names read from the case) | an exemption by name is solver vocabulary in core; the native proof found the hook missed `manufacturedMonodomainTotalLagrangianEM` | neutral: proved first by `test_every_case_the_name_rule_exempted_is_exempted_by_the_hook` (native) |
| 2026-09-26 | results-as-quantities | `omnidriver.core.quantities`: `Quantity`, a seven-unit table, `read_quantities` (sentinels resolved before conversion), the `ArtifactValueReader` contract behind `RuntimeEvidenceCapability.artifact_value_reader` (was declaration-only), and conformance C12 | no core code read a value or compared numbers; a reader could not declare its units | neutral: no solver or physics vocabulary (shape and vocabulary gates pass); sampling rules and formats are plugin strings core only carries; every shipped plugin still returns `None`, which C12 and the comparison report as a named gap, never a pass |
| 2026-09-26 | core generality (A) | R1 fix, finding I2: `record_execution.record_generated_relpaths` no longer treats a path any step consumes as an authored input; only a path whose FIRST touch (in step order) is a consume is kept. A path a step produces before a later step consumes it (a mesh a solve step reads) is an intermediate and stays excluded | "produced minus consumed" exempted an intermediate a later step consumes from exclusion, so a restage would carry a prior run's mesh forward once a record's solve step honestly declared `consumes` on it (no current record does yet, but C8 pushes records that way) | neutral: no solver vocabulary; new case added to `test_a_records_generated_paths_are_what_it_produces_and_does_not_consume`'s suite (`test_an_intermediate_a_later_step_consumes_is_still_excluded`) |
| 2026-09-26 | core generality (A) | R1 fix, finding I3: `core/runtime_records.py`'s `CORE_RUNTIME_RECORDS` gains the remediation-transaction marker (`runtime.remediation_transaction.MARKER_NAME`) and its two directories (new constants `TRANSACTIONS_DIRECTORY`, `CANDIDATES_DIRECTORY` in that module, used at both write sites) | the module docstring claimed "every file core writes into a case" while these three were missing -- a rejected repair's marker would survive a restage and wrongly block reuse without `--apply` | neutral: no solver vocabulary; `test_core_names_every_file_it_writes_into_a_case` now derives its expected set from each owning module's own constant rather than a restated literal |
| 2026-09-26 | core generality (A) | R1 fix, finding M1: `conformance.checks.check_restage_is_clean` (C11) now asserts `restaged == native` (both directions), not `restaged <= native`; docstring/verdict corrected to say only path sets are compared, not content (a restage intentionally inherits the run's patched content) | the subset-only check could not see a staging rule that wrongly *drops* an authored native file | neutral: no solver vocabulary; both directions still hold for the toy and openCARP (verified before landing); new toy plugin `OverGeneratedConventionsPlugin` proves the "dropped" direction bites |
| 2026-09-26 | core generality (A) | R1 fix, finding M3: `attempt_lease.py` gains `_guard_filename()`; `ATTEMPT_LOCK_GUARD_FILENAME` and `_lease_record_guard`'s per-call guard path both derive from it; `cli.py`'s `--fresh` `preserve_names` now imports `ATTEMPT_LOCK_FILENAME`/`ATTEMPT_LOCK_GUARD_FILENAME` instead of spelling them | the attempt-lock names were spelled in three places; a changed `ATTEMPT_LOCK_FILENAME` would have let `--fresh` delete the live lease out from under itself | neutral: no solver vocabulary; no behaviour change on any current name |
| 2026-09-26 | core generality (A) | R1 fix, finding M7: `plugin_capabilities.py`'s `DictionaryCatalogCapability` `:consumed-by:` gains `omnidriver/cardiacfoam/dict_entries.py` (calls `.groups()`); `capability_seams.render`'s prose corrected -- an optional-neutral member degrades through a named `compatibility.py` fallback only where the table's `fallback` column names one, not always (A3's four dictionary-shaped members answer empty inline, in the adapter, with none); `ARCHITECTURE.md` regenerated | the seam table's `:consumed-by:` list and the prose above it had drifted from what A3 actually changed | neutral: doc-only; `scripts/export-capability-seams.py --check` passes |
| 2026-09-26 | results-as-quantities | the comparison: `point-reference` and `quantity-comparison` schemas (packaged), `run_quantity_comparison` / `omnidriver compare`, and `experiments._association_status` accepting a list of `run_evidence` | an agent needs one call that reads named quantities from runs of any solver, compares agent-stated pairs against a pre-registered tolerance, and leaves a report bound to each run's evidence | neutral: no frame conversion, pairing or tolerance of core's own (owner, 2026-09-26); every input is supplied in the request; a report is written once; the envelope change is additive (a single object still works) |
| 2026-09-26 | results-as-quantities | the comparison: `point-reference` and `quantity-comparison` schemas (packaged), `run_quantity_comparison` / `omnidriver compare`, and `experiments._association_status` accepting a list of `run_evidence` | an agent needs one call that reads named quantities from runs of any solver, compares agent-stated pairs against a pre-registered tolerance, and leaves a report bound to each run's evidence | neutral: no frame conversion, pairing or tolerance of core's own (owner, 2026-09-26); every input is supplied in the request; a report is written once; the envelope change is additive (a single object still works). **Corrected 2026-09-26 (controller review of `fee7899`):** the run-planned-with-a-different-stack check first compared full provider records (id, version, api_version, source, provider_digest), which refused a stack reloaded from a different import path with identical content -- `source` is deliberately excluded from stack identity. `quantities.comparison._resolve_run` now calls the same `provider_identity.stack_identity_mismatch(planned, selected)` helper `run_document_exec.build_execution_inputs` and `cli.py`'s `_context_from_run_document` already used (each previously kept its own copy of the same key list and reasoning; now one). `run_evidence` is also deduplicated by `(case_id, workflow_digest, input_provenance_digest)`, so two run names resolving to one case do not appear twice and defeat `_association_status`'s "exactly one match" rule; a pair whose two sides resolve to the same (sweep, case, artifact, quantity) is refused whatever the run names; `points`/`max_sampling_offset` for a stack with no reader is refused before any read; any reader exception (not only `ValueError`) becomes a `not_evaluated` gap naming the exception type, and a hard-link failure in `_write_once` is a named `QuantityComparisonError`, never a traceback or an overwrite |
| 2026-09-26 | core generality (A) | A1: `explicit_bashrc`/`--environment-bashrc` renamed `environment_source`/`--environment-source` in every hook, adapter, CLI path and test; removed from `generic_case`; OpenFOAM's own helpers take `bashrc_path` | a shell-profile word named a parameter every environment shares | neutral: core passes the value through unchanged (`test_environment_source_is_opaque.py`); the shape baseline loses all six `bashrc` lines (69 hits) |
| 2026-09-26 | core generality (A) | A2a: instance directories -- `CaseRuntimeConventions.instance_directory_pattern`/`preserved_instance_names` replace the time-directory fields; `DataArtifact.instance_indexed` and the `{instance}` placeholder replace `time_indexed`/`{time}` (run-document schema and utility-manifest key renamed); `reconciler.declared_instance_names`, `sweep_runner._clean_stale_instances` | core named OpenFOAM's time directories; openCARP has none | neutral: OpenFOAM declares the same regex and `"0"`, and the vocabulary-only tests keep every assertion; a stack declaring none has none (`test_instance_directories.py`) |
| 2026-09-26 | core generality (A) | A2b: replica directories -- `CaseRuntimeConventions.replica_directory_globs` replaces `decomposition_directory_prefix`; `plugin_profile.replica_directory_globs`/`is_replica_directory_name` replace `decomposition_dirname_prefix` in staging, discovery, step snapshots and provenance | core named OpenFOAM's `processor*` layout | neutral: OpenFOAM declares `("processor*",)`, equivalent to its old prefix; a stack declaring none stages and discovers inside `processor0/` (`test_replica_directories.py`); the shape baseline loses its `processor` line |
| 2026-09-26 | core generality (A) | A2c: provenance hook `CaseProvenanceCapability.input_roots(case_root, resolved_case)` (member `get_input_roots`, `sequence`); `CaseIntrospectionCapability.selected_start_time` and `get_selected_start_time` deleted; `required_inputs`/`generated_output_globs` lose the start-time argument; the OpenFOAM layer declares its start time and replicas | core computed OpenFOAM's restart directory and walked its replicas | neutral: characterization test `test_the_start_time_is_walked_serially_and_in_every_replica` passes before and after; native provenance of every registered cardiacFOAM/cardiacCore tutorial is byte-identical; a stack declaring no roots walks only its case-file roots |
| 2026-09-26 | core generality (A) | R2 fix, finding I1: `run_document_exec.load_run_document` now re-raises a schema `jsonschema.ValidationError` as `ValueError`, matching its own docstring's long-false claim; `sweep_runner._completed_case_is_reusable` therefore reports a pre-A2 completed case (every artifact still carrying the removed `time_indexed` key) as not reusable, by name, instead of letting the sweep crash | A2a's schema refuses `time_indexed` with `additionalProperties: false`, but `jsonschema.ValidationError` is not a `ValueError` and escaped `_completed_case_is_reusable`'s except tuple uncaught, crashing `sweep_run` on the first pre-A2 completed case it met | neutral: no solver vocabulary; `test_completed_pre_a2_run_document_is_reported_not_reusable_and_rerun` reproduces the reviewer's probe scenario end to end |
| 2026-09-26 | core generality (A) | R2 fix, finding M1: `runtime.models.data_artifact_from_json` refuses any key outside the new `_ARTIFACT_JSON_KEYS` closed set (a `time_indexed` entry among them) by name, naming the actual key(s) found -- read back from the caller's own data, not hardcoded -- instead of silently dropping it via `data.get(...)`. Closes the one reader that did not schema-validate (`core.quantities.comparison._artifact`, which reads a run document as raw JSON). Written this way (generic unknown-key refusal) rather than a literal `"time_indexed"` comparison so the fix does not itself reintroduce the token M7 (same fix round) adds to `check-core-shape.py`'s `TOKENS` | a pre-A2 artifact with a literal `path_pattern` (no `{time}`) was accepted by `_artifact` and had its now-meaningless `time_indexed` flag dropped with no diagnostic | neutral: no solver vocabulary; `test_time_indexed_key_is_refused_by_name`; `check-core-shape.py` stays silent with `time_indexed` in `TOKENS` |
| 2026-09-26 | core generality (A) | R2 fix, finding I2: `CaseProvenanceCapability.input_roots`/`get_input_roots` gain a required keyword `conventions`, the stack's merged `CaseRuntimeConventions` (the same value staging/discovery read); `OpenFOAMEnvironmentPlugin.get_input_roots` reads `conventions.replica_directory_globs` instead of its own `openfoam_case_runtime_conventions()` | provenance and staging read the replica rule from two different places, so a stacked provider redeclaring `replica_directory_globs` had its replicas honoured by staging/discovery but walked past, unfingerprinted, by provenance -- the exact silent stale-replay direction I9 exists to prevent (latent: no current stack overrides the conventions) | neutral: no solver vocabulary; `test_a_stacked_providers_merged_replica_globs_are_what_provenance_walks` (openfoam package) proves the merged value, not OpenFOAM's default, is what provenance walks |
| 2026-09-26 | core generality (A) | R2 fix, finding M8: `_CaseProvenanceAdapter.input_roots`'s refusal message for a non-`str` input root now says "must return \`str\` case-relative paths, got Path" instead of "must return non-empty case-relative paths", which read as though a `pathlib.Path` were not a path at all | the check is really "must be `str`"; the old message misdescribed a `Path` return, the natural type a plugin author reaches for | neutral: doc/message-only; `test_an_input_root_must_be_a_case_relative_path_inside_the_case` still passes (parametrized on non-`str`/empty/absolute/escaping cases) |
| 2026-09-26 | core generality (A) | R2 fix, finding I3: `CaseRuntimeConventions.__post_init__` refuses a non-tuple or a tuple holding a non-`str`/empty item for `replica_directory_globs` and `preserved_instance_names` by name, and a `instance_directory_pattern` that does not compile as a regex, by name | a bare `str` (the natural migration mistake from the old bare-`str` `decomposition_directory_prefix` field) silently exploded into one-character globs via `tuple(...)`, matching every name and dropping every authored directory at staging with nothing reported at plan time | neutral: no solver vocabulary; every existing construction in the suite already passes proper tuples/valid regexes, so no baseline or behaviour change for a real stack |
| 2026-09-26 | core generality (A) | R2 fix, finding M2 (prose-only): `CaseRuntimeConventions.replica_directory_globs`/`instance_directory_pattern` and `DataArtifact.instance_indexed` docstrings, and `plugin_profile.is_replica_directory_name`, corrected -- the rules apply at every depth in the case tree, not only the case root; the instance rule also applies to files, not only directories; and only `workflow_runner._artifact_snapshot` looks inside a replica for an instance-indexed output, never `reconcile_artifacts` | the A2 prose claimed "case-root directory" and "looks inside them", both narrower than what the code (unchanged by A2, verified byte-for-byte before/after) actually does | neutral: doc-only, no behaviour change; the depth/file-vs-directory behaviour itself is flagged here as pre-existing and open, not fixed by this correction |
| 2026-09-26 | core generality (A) | R2 fix, finding M7: `scripts/check-core-shape.py`'s `TOKENS` gains `start_time`, `startTime`, `latestTime`, `time_indexed`, `{time}` -- A2 removed this vocabulary from core, but nothing guarded against it regrowing. Landing this also surfaced (and fixed) a real gap in the gate's own docstring exemption: `_docstring_ids` only exempted `body[0]` (a module/class/function's true docstring), not a dataclass field's trailing string-literal "docstring" -- this codebase's own dated-correction convention -- so two already-committed, pre-existing corrections (naming the retired `time_indexed` token by name, exactly as the module's own docstring says prose should) became false new hits the moment the token was added. `_docstring_ids` now exempts a bare string statement anywhere in a body, not only `body[0]` | the codebase's own dated-correction convention writes a field's trailing string exactly like a docstring, and the module's own docstring already promises "comments and docstrings are prose, not coupling" -- the implementation just did not keep that promise for this one form | neutral: no solver vocabulary; `test_a_field_trailing_docstring_does_not_count` and `test_a_string_used_as_a_comparison_value_still_counts` (the latter proving the broadened exemption still catches a string literal actually used as a value, not only prose); gate silent, no baseline lines added |
| 2026-09-26 | results-as-quantities | Opus review fixes (B, `.superpowers/sdd/B-review.md`/`B-fix-decisions.md`): a `takes_points` reader's sample with no `sampled_at` is refused by name (`reading.read_quantities`, I1); the request gains a required, no-default `both_not_reached` (`"agree"`/`"fail"`), recorded in the report, and `overall_status` now returns `(status, reason)`, never `passed` unless a pair is `within_tolerance` (I2/M1); a `takes_points=False` reader may now be given `points` as an *expected* location with a required `max_sampling_offset`, checked against its reported `sampled_at` and never handed to the reader (`comparison._points`/`_quantities`, I3 -- the cardiacFOAM half is recorded, not implemented, in the spec and Task 7); `_location` normalises paths (`.resolve()`) before the N1 self-comparison check (M2); every location number in the report carries its own unit (`requested_at_unit`, `sampling_offset_unit`, `max_sampling_offset_unit`, M7); the written report is `chmod 0o444` (M6), and `experiments._read_comparison` recomputes a checker `omnidriver.quantities` report's status from its own `metrics` rather than trusting a stated `status` (new `_quantities_status`, lazy-imported to avoid a cycle); `_write_once` and `_artifact` turn `OSError`/`KeyError`/`ValueError` into named `QuantityComparisonError`s instead of tracebacks (M10); `Quantity`'s docstring drops "mesh point"/"containing cell" (M4) | the review found a stated `max_sampling_offset` guard silently unenforced, a report that could pass with nothing ever compared, and the cardiacFOAM design (Task 7) would have reported a configured probe location as "where the solver sampled" | neutral: no solver vocabulary added; `scripts/check-core-shape.py` and the phase-vocabulary tests still pass. `overall_status` and `_read_comparison`'s recompute path are new core behaviour, covered by `test_quantities.py`, `test_quantity_comparison.py` and `test_experiments.py` |
| 2026-09-26 | core generality (A) | final review M1: `plugin_interface.validate_plugin` refuses a plugin that still implements the retired `get_selected_start_time` hook (A2c) or still declares `get_environment_diagnostics`/`get_loaded_environment` with the retired `explicit_bashrc` keyword (A1), detected by `inspect.signature`; the two retired spellings are built from concatenated fragments so they do not themselves trip `check-core-shape.py`'s `start_time`/`bashrc` tokens | a v2 plugin implementing the retired hook loaded silently, with its restart directory un-walked for provenance and no warning; one still using the retired keyword crashed with a bare `TypeError` mid-plan instead of being refused at load | neutral: no solver vocabulary; `test_plugin_contract_refuses_a_retired_hook_by_name`, `test_plugin_contract_refuses_a_retired_keyword_parameter`; shape gate stays silent |
| 2026-09-26 | core generality (A) | final review M6: `runtime_records.CORE_RUNTIME_RECORDS` and ~20 write sites (`cli.py`, `conformance/checks.py`, `execution_context.py`, `fresh.py`, `postprocess_phase.py`, `run_discovery.py`, `run_document_exec.py`, `step_candidate.py`, `sweep_manifest.py`, `sweep_runner.py`, `strict_planning.py`) now import named constants from their owning module (`workflow_orchestrator.STATE_FILENAME`/`.WORKFLOW_LOGS_DIRNAME`, `run_document_exec.RUN_DOCUMENT_FILENAME`, `sweep_manifest.SWEEP_MANIFEST_FILENAME`, `postprocess_phase.CASE_RECORD_FILENAME`) instead of restating five literal filenames; `fresh._OMNIDRIVER_MARKER_NAMES` now derives from three of the same constants, documented as deliberately not identical to `generated_case_markers` (different question, different root) rather than left to silently diverge | the restated literals meant a new core-written case file added at one write site but missed at another was invisible to staging exclusion and to conformance C11; `test_core_names_every_file_it_writes_into_a_case`'s own docstring claimed derivation from owning constants while three of five names were not | neutral: no behaviour change, every constant equals the literal it replaces; `test_core_names_every_file_it_writes_into_a_case` now imports the same constants rather than restating them, so a rename at the owner is what it actually catches |
| 2026-09-26 | core generality (A) | final review M5, kept half only: `openfoam.time_selection.selected_start_time` selects candidate time directories with the stack's merged `CaseRuntimeConventions.instance_directory_pattern` (already threaded into `get_input_roots` by R2 I2) instead of a bare `float(name)`. The other half of M5 -- refusing a missing `controlDict`/`startTime` instead of the silent `"0"` default -- was attempted and reverted the same day: it broke `omnidriver-cardiaccore`'s real, pre-existing `test_controlled_allrun_executes_without_domain_claims`, which runs a deliberately non-OpenFOAM-shaped (no `controlDict`) case through the composed OpenFOAM+cardiaccore stack and must keep succeeding | `float()` and the conventions regex disagreed on names like `inf`/`nan`/`1_0`/`+1`/`1E-05` (regex: not an instance; `float()`: parses, so `latestTime` could pick `inf`) | neutral: no solver vocabulary; `test_latest_time_selection_uses_the_conventions_regex_not_float`; the reverted refusal half is left for an owner decision (`final-fix-report.md` concerns), not silently reintroduced |
| 2026-09-26 | core generality (A) | M5's reverted half, settled by the owner: `openfoam.time_selection.selected_start_time` now implements `Foam::Time::setControls` (OpenFOAM v2412, `src/OpenFOAM/db/Time/Time.C`) exactly -- `startFrom` absent defaults to `latestTime` (`getOrDefault<word>("startFrom", "latestTime")`), not `startTime`; `startFrom startTime` with no `startTime` entry, and any `startFrom` outside `startTime`/`firstTime`/`latestTime`, both raise the new `TimeSelectionError` (subclasses `TutorialRecordError`) instead of silently answering `"0"`; `firstTime`/`latestTime` with no time directories still answers `"0"`, OpenFOAM's own `Time` constructor default (`startTime_(0)`), not a fallback. A missing `controlDict` now answers `None`, not `"0"`, and `OpenFOAMEnvironmentPlugin.get_input_roots` treats `None` as "contribute no roots at all" (no start folder, no replica start folders) -- the owner's rule: "`controlDict` is how we know an OpenFOAM case exists; that is what we use. The rule is mandatory and the same for every case, with no exceptions." | the previous default (`startTime`) and silent `"0"` on a missing/malformed entry both disagreed with real OpenFOAM, and the missing-`controlDict` case had no way to say "not my problem" other than inventing `"0"` | neutral: no solver vocabulary; one test per table row (`test_time_selection.py`); native parity proved for all 17 native cardiacFOAM `controlDict`s, which all set `startFrom` explicitly (`test_time_selection_native.py`, `native`); `omnidriver-cardiaccore`'s `test_controlled_allrun_executes_without_domain_claims` (no `controlDict` at all) still passes |
| 2026-09-26 | tutorials | P4 (conformance Task 14 step 4, decisions 2 and 3): the record-surface key grammar. `runtime.record_surface` gains `key_pattern`/`lists_key` and `ANY_KEY`: in a catalogue key `[Int]` is any index and a whole `<identifier>` segment (`<name>`, `<region_name>`) is any one dot-free segment; a document-level entry `{"document": d, "key": "<any>", "validated": False}` needs no `value_kind` and lists every key of `d`. C10 (`check_discoverable`) matches the target's patch key through it, replacing `_ANY_INDEX`'s rewrite-then-compare. Documented in `get_record_key_catalog`'s docstring | cardiacFOAM's catalogue carries named segments (`regions.<region_name>.baseline`) and writes OpenFOAM `system/` keys it has no catalogue for; neither was expressible, so C10 could only fail or lie | neutral: two generic placeholders and an honesty flag, no solver vocabulary; toy tests for each form (named segment matches one segment only, `[Int]` refuses a non-index, an open document lists its own document only, a kindless entry that does not say `validated: False` is incomplete) |
| 2026-09-26 | tutorials | P4 (conformance Task 14 step 4, decision 4): `introspection._describe_tutorial_record` no longer carries `dict_entries`; a record's keys are in `record_surface.keys` only. Factory and case-folder payloads keep `dict_entries` until step C deletes the factory path | a record's describe answered "which keys may I name" twice, in two shapes, one with unconcretised `$ELECTRO_MODEL_COEFFS` tokens and none of the record's own documents | neutral: a removal; no caller reads `dict_entries` from a record payload (`grep`), toy test `test_describe_of_a_record_carries_its_keys_only_in_the_record_surface` |
| 2026-09-26 | tutorials | P3, owner Q2: `TutorialRecord.default_variant`, the route a study runs when it names no `variant_selector`. Required when `workflow_variants` is declared, refused when it is not one of them (exact comparison) or when there are no variants; a `null` selector value is refused, not defaulted. `record_execution._resolve_workflow_step_ids` becomes `_resolve_workflow_route`, which also returns the choice; `describe`'s `record_preview` gains `workflow_variant` (`selector`, `selected`, `source` `"study"`/`"default"`, `default`, `declared`) | every 5.4 record has a blockMesh route (native) and a gmsh route (a study's choice); a variant record refused `describe`, C2 and `plan --strict` with no study values, so none could pass conformance | neutral: core names no route and gives none a meaning; the record says which is native. Toy tests: the refusals, the default preview/commit, and `DefaultRoutePlugin` passing C1-C12 with an empty base study |
| 2026-09-26 | tutorials | P3, owner Q3/Q7: `WorkflowStep.default_arguments`, a tuple of `DefaultArgument(key, values)`, and `WorkflowStep.argv(contributed)`, which `_workflow_dag_for_record` now builds each step's command line from. The rule: an axis replaces a default by passing its `key` tokens contiguously in its `AxisResult.command_arguments` for that step, and otherwise appends; refused by name are a key that does not occur exactly once in `command` plus the defaults, and a contribution holding a key twice (checked in `resolve_case_patches`, naming the axis). `describe`'s `record_preview` gains `workflow_commands` | bidomain, pseudo-ECG and eikonalECG have no `system/blockMeshDict`, only `.1D`/`.2D`/`.3D`; their mesh step's default is `-dict system/blockMeshDict.3D` (bath: `.1D`), and a `dimension` axis must replace it, not add a second `-dict` | neutral: core compares tokens for equality and parses no flag; the key's width is the record's statement, and the record never declares replacement values, so any value after the key replaces the default (owner, 2026-09-26, the pre-processing stage: loose, not tight), so `-dict <file>` and gmsh's `-setnumber lc <v>` need no core knowledge. Toy tests over both shapes, the refusals, the DAG, the preview, and `DefaultArgumentPlugin` passing C1-C12, whose run writes the one file only the default argument names |
| 2026-09-26 | tutorials | Record-scoped axes: `TutorialRecord.allowed_axes` (a set of names) becomes `TutorialRecord.axes`, a tuple of `AxisContract`, each named by its own `name`; `sort_study_name(name, *, axes)` and `resolve_case_patches` resolve a bare study name against the record's own axes. A record declaring two axes with one name, a `name -> contract` mapping, or a non-`AxisContract` is refused by name at construction. The stack-wide catalog is deleted with no shim: `AxisCapability`, `PluginCapabilities.axes`, the `get_axis_catalog` hook and its `map` shape; `validate_plugin` refuses a plugin that still declares `get_axis_catalog` (`_RETIRED_PLUGIN_MEMBERS`). `describe`'s `record_surface.axes` and C10 read `record.axes` | `manufacturedBidomain` and `manufacturedEikonalECG` both define `dimension`, `numberCells` and `tetNumberCells`, and bidomain's `dimension` also writes `bidomainSolverCoeffs.dimension`; the flat catalog's `dict.update` made bidomain run eikonalECG's axes, so a 1D/2D bidomain case left `dimension "3D"` in `constant/electroProperties` (seen in `sweep-plan` output). bath and pseudo-ECG define `dimension` too | neutral: core resolves names within a record and knows no axis; the capability seam table loses one row (31 seams) |
| 2026-09-26 | tutorials | `tutorial_records.build_tutorial_record_catalog(records)`: reduces a tuple of `TutorialRecord`s to a `name -> record` dict, refusing (`TutorialRecordError`, naming both `native_case_relpath`s) a duplicate `.name` instead of the last one silently winning. `cardiacfoam.records.TUTORIAL_RECORDS` and `opencarp.records.TUTORIAL_RECORDS` both build their catalog through it now, in place of a `{record.name: record}` dict comprehension | the same hazard record-scoped axes (the row above) just closed for two axes sharing a name inside one record, still open one level up: two records sharing a name across a plugin's own `TUTORIAL_RECORDS` would silently overwrite one another, with no error and no trace of which record was actually reachable | neutral: no solver vocabulary, a pure reduction function; `test_build_tutorial_record_catalog_keys_by_name`, `test_build_tutorial_record_catalog_refuses_a_duplicate_name` |
| 2026-09-26 | tutorials | Review 54b I3: `TutorialRecord.variant_constraints`, `{variant: {study name: (admitted value, ...)}}`, and `tutorial_records.check_variant_constraints`, which `record_execution._resolve_and_split` calls right after `_resolve_workflow_route`, before any axis runs, so `describe`, `plan --strict`, `run --strict` and every sweep case refuse alike. When a variant runs (named by the study or the default), a study that sets a constrained name must set it to an admitted value, compared with `_strictly_equal`; leaving it unset is always admitted. Refused by name at construction: a constraint on an undeclared variant, on the selector itself, on a name `sort_study_name` does not resolve for the record, an empty, bare-`str` or non-sequence value set, and a non-mapping at either level | a real refusal was lost in the 5.4b wave: the old pseudo-ECG and eikonalECG `make_spec` raised `mesh_family='tet' requires dimensions=['3D']`, and `{"mesh": "tet", "dimension": "1D"}` on `manufacturedBidomain` then planned `status: ok`, staging `dimension "1D";` next to gmsh's 3D cube (on eikonalECG the value was silently ignored). Axes see only their own value (§5g Q5), so no axis could know the route | neutral: core compares opaque values against a record-declared set and knows no route or axis; toy-record tests `test_a_variant_constraint_*` and `test_variant_constraints_without_variants_are_refused` |
| 2026-09-26 | tutorials | Review 54b M12: `cli._sweep_refusal`. `sweep-plan` and `sweep-run` turn a `SweepValidationError` or `TutorialRecordError` refusing the sweep as a whole into the CLI's JSON failure (`status`, `action`, `spec`, `error`; exit 1), the shape `_sweep_output_dir`'s refusal and `plan --strict` already use. A per-case refusal stays that case's `materialization_error` | a record sweep's missing `base.cases_root`, a study name the record does not resolve, and a case id that is not path-safe all escaped as a Python traceback with nothing on stdout (seen on niederer2011's two studies and bidomain's three tet studies) | neutral: CLI error shaping only; `test_a_record_sweep_refusal_is_the_clis_json_failure` (6 cases, each failing before with the traceback's exception) |
