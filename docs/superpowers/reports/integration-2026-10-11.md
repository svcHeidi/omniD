# Integration 2026-10-11: review guide

Branch `integration/2026-10-11`, from `chore/trim-paper-links` (`ffb547cd`),
merged with `feat/verifier-anisotropic`, `chore/cleanup-2026-10-10`,
`design/benchmark-verifier-builder` and `feat/verifier-problem-library`. It is ahead of `main` (`58cccc8f`) by 194
commits (178 outside merges): 299 files, +21414 / -761. `feat/verifier-problem-library`
is merged too: the verifier-temporal branch had left it at `90674a80`.

## Size by area (`git diff --stat main...HEAD`)

| area | files | added | removed |
|---|---|---|---|
| `packages/omnidriver` (core) | 47 | 1707 | 394 |
| `packages/omnidriver-openfoam` | 66 | 2064 | 95 |
| `packages/omnidriver-cardiacfoam` | 37 | 736 | 105 |
| `packages/omnidriver-cardiaccore` | 5 | 21 | 23 |
| `packages/omnidriver-opencarp` | 14 | 190 | 40 |
| `packages/omnidriver-torchcor` (new) | 24 | 6449 | 0 |
| `packages/omnidriver-verifier` (new) | 38 | 3720 | 0 |
| `packages/omnidriver-agents` (new) | 22 | 1123 | 0 |
| `docs/` | 29 | 4993 | 36 |
| `benchmarks/`, `scripts/`, `.github/`, root documents | 20 | about 370 | about 70 |

## What the branch contains

### Core

- Every refusal carries a stable code; the codes are one listed vocabulary and a
  rule refusal carries its rules as data (`05a78436`, `6d985622`).
- A catalogue entry may carry attributes per menu value (`f7938358`); an axis
  states its unit, what it sets and its bounds (`00cf803a`); `describe` lists a
  record's quantities, their readers and the conformance quantity with units
  (`6c1c9a6e`, `10829864`).
- A sampling bound per point (`max_sampling_offset`); non-finite numbers in a
  comparison request are refused (`305fd3d7`, `16abc782`).
- Staging keeps a case's supplied mesh and refuses a case missing a consumed
  path before it runs (`6f56cb35`); a replaced default argument keeps its
  declared position in the argv (`5e0db53f`).
- `check` carries the stack's environment diagnostics in its report
  (`d3c89e71`); a failed parallel probe degrades the environment status
  (`60ba300e`).
- cardiacFOAM: a strict plan refuses a `gmsh -setnumber` the template does not
  declare (`0405a7b5`, plan check `gmsh_setnumber_not_declared`); chi, Cm and
  the uniform conductivity diagonal are positive by construction; an ionic
  model entry names the model it is (`same_model_as`).
- A supplied environment variable may declare `keeps: <name>`: the variable the
  sourced file sets, whose value stays in front of the supplied one when it is
  exported (`896ae226`, `10ead8f0`). The OpenFOAM profile uses it so that
  `DYLD_LIBRARY_PATH` is exported after the bashrc's own
  `FOAM_LD_LIBRARY_PATH`, which macOS would otherwise lose. `keeps` must be a
  bash variable name (ASCII), an item's keys are closed, and nothing stray (a
  `:`) is emitted when the kept variable is unset. It was reviewed adversarially
  in an earlier round, with a follow-up fix (`10ead8f0`); the loader, manifest
  and rendered-shell tests cover it.

### The verifier package (`omnidriver-verifier`, import `omnidriver.verifier`)

It imports core only and nothing imports it (Rule 6 in `ARCHITECTURE.md`). It
holds manufactured problems as data (TOML, each block naming its source in
`[provenance]` and the native commit it was transcribed from) and the
deterministic checks that judge them. It runs no solver: a solver is run by
`omnidriver sweep-run` (or its own tool) and its results are fed to the
comparison.

What it provides:

- **Mesh-size order fit**: when every level of a spatial result carries a
  `mesh_size`, orders are fitted against it instead of edge/N (`spacing` in the
  row says which; a size at only some levels is refused as `results_invalid`)
  (`fd02b867`).
- **Problem library** (`problems/`): `fda_monodomain` (1D, 2D, 3D; hex and tet
  ladders; a temporal ladder) and `anisotropic_monodomain` (3D, a fully
  populated conductivity tensor, the boundary-compatible sin^2 solution; hex and
  tet).
- **Gate 1, residual** (`residual.py`): the exact fields are substituted
  symbolically into the problem's own PDE, cell model and boundary condition.
  Needs the `symbolic` extra (sympy).
- **Gate 2, native drift** (`tests/test_native_drift*.py`): the problem's data
  equals the native code's, read from verbatim committed snippets; a native
  change the data does not follow fails once the snippets are refreshed.
- **Norms and weights** (`convergence.py`, `weights.py`): the shared L1, L2 and
  Linf error norm, weighted by cell volumes (finite volume) or lumped nodal
  control volumes (finite element, line, quadrilateral, hexahedron and linear
  tetrahedron); the same for every solver.
- **Convergence table**: per solver and dimension, errors per level, observed
  order between levels, the least-squares order, the stated orders.
- **Temporal table**: orders in dt at a fixed mesh against the exact solution,
  against each configuration's own finest dt (a finest-dt order never stands
  alone and a floor at the finest level is flagged), and against an
  extrapolated dt -> 0 reference (`646a9196`).
- **Refusals by code** for malformed results (`results_invalid`,
  `spacings_unusable`, `weights_invalid`, `required_check_unavailable`).

How to run it (from an environment with the package installed; add
`omnidriver-verifier[symbolic]` for `residual`):

```bash
omnidriver-verify problems                          # id, title, dimensions, mesh progression
omnidriver-verify show anisotropic_monodomain       # the full definition
omnidriver-verify residual fda_monodomain           # gate 1; exit 1 if it fails
omnidriver-verify compare fda_monodomain --results a.json b.json
omnidriver-verify compare fda_monodomain --temporal --results t_a.json t_b.json
```

A spatial results file is one JSON per solver: `solver`, `problem`, `mesh`,
`stated`, `levels` (each `dimension`, `cells_per_axis`, `dt`, `steps`,
`errors: {field: {kind: value}}`). A temporal file carries `configuration` and
`reference` instead of `mesh`. Every answer, and every refusal, is JSON on
stdout. Worked runs and their numbers are in
`docs/solver-learning/cardiacfoam.md` (AD rows) and `opencarp.md` (P8, P9).

### OpenFOAM numerics catalogue

`system/fvSchemes` is catalogued once for every OpenFOAM-based solver; the
scheme and ODE solver tables are read from `$FOAM_SRC` (a supplied tree is the
authority, the bundled snapshot a labelled default); a scheme's numerics, as its
authors state them, ride on its menu value; cardiacFOAM's own keys carry
numerics citing the native tree, with omniD's inferences labelled.

### Other packages

`omnidriver-torchcor` (plugin, 24 files), `omnidriver-agents` (harness that
measures omniD through its CLI only, Rule 7), openCARP's `niedererNVersion`
fibre imbrication and the 45-degree Niederer slab on openCARP and TorchCor.

### Documents

`docs/solver-learning/` (cardiacFOAM, openCARP, TorchCor, cross-solver
variables, the method), `ROADMAP.md`, the package spec for the
benchmark/verifier builder, the phie-recovery notes and the reports under
`docs/superpowers/reports/`.

## Merges and conflicts in this integration

- `feat/verifier-anisotropic`: one commit, conflicted in
  `docs/solver-learning/cardiacfoam.md` (row AD10). Took the later content and
  changed "the paper's matrix" to "the temporal matrix".
- `chore/cleanup-2026-10-10`: conflicts in `ARCHITECTURE.md` (kept both the
  verifier and the harness; they are Rules 6 and 7), `benchmarks/niederer2011.json`
  (kept the trimmed source list; the manuscript-appendix source stays removed),
  and the two results-as-quantities documents (kept the trimmed text, with the
  moved report path).
- `design/benchmark-verifier-builder`: one new commit (phie-recovery notes),
  clean.
- `feat/verifier-problem-library` (six commits: the tet FDA study notes, the
  mesh-size fit, the tet study commit, the `keeps` mechanism). Conflicts:
  `cardiacfoam.md` and `opencarp.md` had two sections lettered alike (AC and O
  for the temporal study on one side, the tet study on the other); the tet study
  is renamed AE (cardiacFOAM) and Q (openCARP), its rows and cross-references
  with it, and the later wording of row AB4 kept. `test_convergence.py`: both
  sides' tests kept. `test_native_drift.py`: the tet study is read at the commit
  its runs executed (`tet_study_commit`, with the committed fixtures that go
  with it), not at the problem's `commit`. The merged diff carries no manuscript
  reference.

## Reviewed, and not

Adversarially reviewed: the knowledge-as-data core changes, the `keeps` mechanism, the OpenFOAM
numerics catalogue and the cardiacFOAM numerics, the verifier up to the
anisotropic problem and its temporal tables.

**Not reviewed:** the extrapolated temporal reference and the second temporal
mesh (`646a9196`), the gmsh `-setnumber` plan check (`0405a7b5`), the merge
resolutions above, and the cleanup documents.

## Paper-related files still present

Awaiting the move to a separate repository; none deleted, none added here:

- `docs/superpowers/specs/2026-10-10-publication-plan.md`
- `docs/superpowers/reports/literature-2026-10-10/` (four reports, including
  `research-venues.md` and `research-verifier-novelty.md`)
- `docs/superpowers/reports/campaign-report.md`
- `docs/superpowers/reports/niederer-benchmark-definition.md` (names the
  owner's manuscript appendix by path)
- sentences naming "the paper's P8" range in `docs/solver-learning/cardiacfoam.md`
  and `opencarp.md`, and manuscript mentions in `ROADMAP.md`, the agent-harness,
  torchcor and builder specs/plans.

## Verification

Run on this worktree with venvs built for it: the four static gates, the whole
repository, core alone and the installed wheel; totals are in the hand-back
message, since a count rots.
