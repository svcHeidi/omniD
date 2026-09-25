# Tutorials are pointers: the remaining work, and the rules for doing it

**Date:** 2026-09-25 · **Design:** [`../specs/2026-09-24-tutorials-are-pointers-design.md`](../specs/2026-09-24-tutorials-are-pointers-design.md)
(approved; its own Status section records steps 1–5.0 in detail).

This plan is the tracker for everything after step 5.0. It runs in parallel with
the openCARP work (`../specs/2026-09-25-solver-conformance-and-opencarp-design.md`,
on `main`). Together the two answer one question: **is the core general?** The
tutorials test whether core can express cardiacFOAM's real cases without
cardiacFOAM leaking in; openCARP tests whether core works for a solver that is
not OpenFOAM at all.

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

**Baseline for the cleaning, measured 2026-09-25 at `0cf5bfb`:**
- tutorial modules plus `tutorials/defaults/`: 5,884 lines;
- all package source: 53,965 lines;
- all package tests: 57,953 lines.

Every step records its own before/after for these three numbers. Totals are
measured with the command, never copied from here.

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

## 3. Final cleanup (step C)

Once the last migratable tutorial is done:
- delete `tutorials/defaults/` and the factory machinery only
  `totalLagrangianEM` still uses. The factory path stays for that one tutorial,
  and only it;
- delete every legacy writer left without a caller;
- re-run the widened write inventory from the Phase 3 close-out and close G3,
  listing the declared exceptions (file placement, `write_cell_set`,
  `totalLagrangianEM`).

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

## 5. Generality log

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
