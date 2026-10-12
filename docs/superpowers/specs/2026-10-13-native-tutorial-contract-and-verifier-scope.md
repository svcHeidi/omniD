# Native tutorial contract, provenance and verifier scope

Status: open decision, written 2026-10-13 for the owner. Nothing here is
implemented. Facts are marked **read** (seen in a file) or **inferred**
(concluded, not run). Items nobody checked are listed under "Not verified".

## 1. Why this exists

Two cardiacFOAM pull requests touch the same manufactured-solution tutorials
from different directions, and omniD's records, verifier and drift tests are
written against the layout one of them changes.

- **PR #59** (`feat/mono-bi-eikonal-verification`): one case pattern for the
  manufactured cases.
- **PR #53** (`omnid/tutorials-are-pointers`): the omniD bridge, tutorials as
  records, post-processing ported to `omnidriver.postprocessing`. Not ready
  (owner, 2026-10-12).

A merge forecast gives 44 conflicts (43 files touched by both). About 30 are
modify/delete: #59 deleted scripts that #53 edits in place.

The conflict is a symptom. The open question is what contract should sit
between the native repository and omniD, and what omniD's verifier and
benchmarker are for.

## 2. What omniD is for (owner's statement)

omniD guides agents through important tasks.

- **Verifier.** A set of manufactured solutions, chosen from what is
  physically correct, is exercised first. Several codes then solve the same
  problems. Cross-solver comparison also locates where problems can exist.
- **Benchmarker.** An agent runs a set of problems through omniD on every code
  it can reach, and the results are compared across solvers and across what
  each agent produced. This is the hypothesis of the paper.
- **Reproduction variant (proposed here).** The agent gets a problem it does
  not have in the library, for example a native case it has not read, and must
  reconstruct and run it. Same agent movement, different reasoning.

## 3. State of the two native layouts (read)

| | PR #59 | omniD records and #53 |
|---|---|---|
| Varying a case | `Allrun` options (`-mesh`, `-dim`, `-N`, `-dt`, ...) validated, written to `local/`, included by the dictionaries | an axis patches dictionary text on a staged copy of the case |
| Cells N | `system/blockMeshDict.<dim>` holds `($N $N $N)` | `numberCells` axis rewrites the integers in the `hex (` block |
| Mesh defaults | in the `Allrun` | the record's own steps and defaults |
| Meshing | the `Allrun` meshes (`-mesh hex\|tet`) | omniD runs blockMesh/gmsh itself; the record comment says the native `Allrun` does not mesh (true for `main`, not for #59) |
| Tet template | `box.geo.template` at the case root, `DefineConstant` | `setup/studies/tetConvergence/box.geo.template`, hard-coded in the Python records and in the verifier drift tests |
| Study results | in the study READMEs; `results/` git-ignored | omniD sweep archive with run documents |
| Studies | `sweep_*.json` kept, and a README bash loop with the same N/dt ladder | `sweep_*.json` consumed by omniD |
| Post-processing | one `setup/studies/summarize.py` per case | per-study scripts kept and ported (#53) |

Consequences for omniD if #59 lands unchanged:

1. The `numberCells` axis finds a macro instead of integers and fails or does
   not patch.
2. The tet template path in four records and in the verifier drift tests
   disappears.
3. omniD meshes by its own steps and can bypass the native `Allrun`, so the two
   paths can build different meshes from the same stated inputs.

The 14 post-processing scripts #59 removes were already unrunnable from the
native `main` alone (they import `openfoam_driver` and `adapters`, absent from
the repository). #53 keeps and ports 7 of them, deletes 1, leaves 6 unchanged.
Nothing in omniD or the paper calls them by path (read). The paper uses frozen
CSVs under `data/paperI/solver/.../reference/`.

## 4. Provenance

- omniD writes a run document, a workflow state file, a sweep manifest and a
  case record into each run copy (read, `runtime_records`). Without them a
  results directory is a claim, not evidence.
- A run made directly with `Allrun` writes none of them.
- PR #59's README results sit beside git-ignored `results/` and state no commit
  or options, so they are not provenance.
- Whether the run document records the solver commit and binary is **not
  verified**.

## 5. The verifier today (read)

- Two problems, as TOML: `fda_monodomain` and `anisotropic_monodomain`.
- Vocabulary: equation `monodomain`, boundary `zero_normal_gradient`,
  unit-cube domain, `hex`/`tet` ladders, expression functions
  `sqrt cos sin exp log`, tensors `diagonal` or `symmetric` as named
  parameters.
- The data is transcribed by hand from the native C++ and guarded by the drift
  test, pinned to a native commit. Snippets include the conormal wall and
  `sealedWallTrace`, which #59 removes: refreshing the pin will fail by design.
- It does not use or duplicate the sympy generators of #59
  (`shell_monodomain_mms.py`, `shell_bidomain_mms.py`, `shell_eikonal_mms.py`,
  `mms_codegen.py`). The shell problems are not in the verifier and cannot be
  represented in its current vocabulary (shell domain, position-dependent
  tensor, bidomain and eikonal equations, sealed-wall boundary kind).

So the same exact solution can exist twice: as C++ emitted by the generators,
and as hand-written TOML. They are tied together only by the drift test.

## 6. The decisions

### D1. What is the native contract omniD builds on?

Options:

- **A. Native `Allrun` options are the contract.** omniD's axes map to options
  (`numberCells` to `-N`, `dimension` to `-dim`, `dt` to `-dt`); omniD stops
  patching `blockMeshDict` text and stops meshing for itself.
- **B. omniD keeps its own steps and axes; #59 keeps the old template and
  `blockMeshDict` shapes.** Smallest change on omniD, but two entry points to
  one case remain, and they can diverge.

Reasoning for A (inferred): a benchmark compares solvers, so every problem
parameter must be passed explicitly to every adapter and recorded, never taken
from a solver's default. The native `Allrun` is already a validated CLI that
writes only to `local/`, which also makes the fast path (bash) safe for agents.

### D2. Who owns paths?

omniD records currently hard-code native paths in Python. Proposal: the native
repository publishes the entry point, options with defaults, template and sweep
paths and summarizer in a per-tutorial manifest (`omnidriver.toml` exists at the
repository level, with `plugin`, `tutorials`, `source`, `scripts`). Moving a
file is then a one-line change in the same native pull request.

### D3. Where does post-processing and the paper table logic live?

Per-case scripts with external imports do not fit the goal. Proposal: results
flow through omniD's quantity readers and table writer; the tutorial keeps one
self-contained `summarize.py` that reads the verifier summaries and offers a
machine-readable output. Paper tables are regenerated from omniD archives; the
frozen CSVs remain valid until then.

### D4. One source for each manufactured solution

Proposal: each generator emits the C++ header and the verifier's TOML problem
from the same symbolic definition, so there is no hand transcription for new
problems. The verifier schema then grows only as far as the next problems need.

### D5. The reproduction benchmark

Proposed task type, separate from the verifier:

| | Verifier | Reproduction |
|---|---|---|
| Truth | analytic, known in advance | a held-out native result |
| Agent receives | a library problem | a problem statement, not the case files |
| Agent delivers | errors per solver | the problem built and run on every reachable solver, with run documents |
| Score | error to the exact field | spread across solvers, distance to each, provenance |

Design points:

- **Leakage.** A native case contains its own answer: README study tables,
  `regression/*.reference`, `postProcessing` outputs in a run copy. The task
  builder must produce a stripped copy, and the agent's sandbox must not
  contain the repository.
- **Defaults.** The statement must give N, dt, end time and tolerances so the
  agent sets them explicitly; running `Allrun` with its defaults is copying.
- **No analytic truth.** Agreement with one solver is not correctness. Report
  the spread and the distances.
- Two task types should stay separate: "read and port" (case files visible)
  and "reconstruct from a statement" (they are not).
- A result with no run document is not scored.

## 7. Recommended order

1. Land #59 after CI; nothing in the benchmark depends on the removed scripts.
2. Decide D1 and D2. Rewrite the cardiacFOAM adapter's axes to pass `Allrun`
   options and make every parameter explicit. This is the core of #53.
3. Record the resolved options and the solver commit in every run document;
   have the README tables quote it.
4. Check and then remove duplication between the generators and the verifier
   (D4).
5. Refresh the drift-test pin against the post-#59 native commit and re-express
   the wall boundary as the sealed-wall treatment that replaces the conormal
   wall.
6. Write the task-type spec for the reproduction benchmark (D5).

## 8. Not verified

- omniD's tests were not run against #59's tree; the count of broken records
  beyond the four template references is unknown.
- Whether `summarize.py` exists in every #59 case (confirmed for `bidomain`).
- Whether the run document records the solver commit and binary.
- Whether openCARP and TorchCor adapters pass every parameter explicitly or
  rely on defaults.
- Whether the benchmarker's problem set includes the manufactured cases.
- How much of D1 `fix/pr53-studies` already does.
- Whether the agent harness already has a held-out task format.
- Whether the anisotropic verifier problem allows a position-dependent tensor.

## 9. Related

- Native: cardiacFOAM issues #19, #58 (cellZone sub-mesh scheme lookup on
  OpenFOAM v2312) and #60 (bidomain `sphericalShell` regression differs on
  v2312).
- `docs/superpowers/specs/2026-10-10-benchmark-verifier-builder-design.md`
- `docs/superpowers/specs/2026-10-09-agent-harness-design.md`
- `docs/superpowers/ROADMAP.md`
