# Benchmarker, verifier and builder: one role per package

**Status:** design for the owner's review, 2026-10-10. No code moves until it
is approved.

## Why

Core is solver-agnostic. No line names a solver, and the gates enforce it. But
core is not single-purpose: next to planning and running, it compares results
against references (`core/quantities/comparison.py`, `reference.py`, the
`compare` command, conformance C14), and it builds cases (`core/case_build.py`
with its own entry-point group, outside the plugin contract).

The owner wants each of these jobs to be a package with one role an agent can
name:

- **benchmark:** a physical problem, judged against references.
- **verify:** are the models the same, and is each code numerically correct?
- **build:** extend omniD to a new solver.

The benchmarker and the verifier use similar tools (quantities, sweeps,
comparisons), but they answer different questions and reason differently.
Neither depends on the other:

| | benchmark | verify |
|---|---|---|
| question | how do the answers to a real physical problem compare? | do the solvers implement the same model, and does each solve it correctly? |
| judged against | references: published values (online or not), other solvers | first the declared models of other solvers (parity), then an analytical solution |
| what "pass" means | within a band; a spread between solvers is expected and is itself a result | parity: the same equations, terms and definitions, or which one differs. Numerics: the error converges at the order the solver's discretisation claims |
| independent of the discretisation? | no: the mesh and method shape the answer | parity yes (FEM or FVM alike); numerics per solver |
| example | Niederer 2011: no solver is expected to give exactly the same answer | a manufactured solution: a second-order scheme must show slope ≈ 2 under refinement |

The reasoning for agents is focus. An agent loads the package for its task,
the import gate keeps the roles from leaking into each other, and each
package has its own acceptance test.

## The shape: a hub, not a mesh

```
                         omnidriver (core)
   contracts: plugin MEMBERS · records, axes, catalogue entries ·
   reader contract and Quantity types · refusal codes
   execution: plan · run · sweep · run document · provenance
   single-case rules (bounds, menus, cross-field) · conformance C1–C13
        ▲               ▲                ▲               ▲             ▲
   benchmark       verifier          builder         agents      solver plugins
```

- **Everything depends on core, and core imports none of these.**
- **Benchmarker, verifier and builder each depend on core only,** and none
  imports another. Where they share a need (reading quantities, sweeping
  refinement levels), it is core's.
- **No new package imports a solver plugin.** Each reaches a solver only
  through the plugin contract.
- **`scripts/check-import-boundaries.py` enforces each rule.**

## omnidriver-benchmark

**Role:** judge results against a stated reference, either a published one
(`benchmarks/niederer2011.json`) or another run.

**Moves out of core:**

| from | to |
|---|---|
| `core/quantities/comparison.py` (`run_quantity_comparison`, `compare_pair`, `Tolerance`, `overall_status`, `experiment_comparisons`) | `omnidriver.benchmark.comparison` |
| `core/quantities/reference.py`, `schemas/point-reference.schema.json`, `schemas/quantity-comparison.schema.json` | `omnidriver.benchmark` |
| the `compare` action in `cli.py` | `omnidriver-bench compare` (its own console script, as `omnidriver-agents` has) |
| conformance C14 (`check_quantity_across_sweep`) | `omnidriver-bench check`, run against the same record |
| `benchmarks/` and `scripts/check-benchmark-references.py` | stay at the repo root as data; the gate imports `omnidriver.benchmark` |

**Stays in core,** because plugins implement it and C12/C13 use it:
`core/quantities/model.py` (`Quantity`, `RawSample`, `ReadRequest`, the
reader declaration), `reading.py`, `units.py` and `errors.py`.

## omnidriver-verifier

**Role:** the verifier is an agent plus capabilities (owner, 2026-10-10). Given
a solver it knows through omniD and a set of manufactured problems that should
pass, the agent writes the verification code for that solver from scratch,
runs refinement studies, and reports what the solver's numerics deliver.
Convergence is rarely checked on real problems; the verifier makes checking it
routine for any solver.

**What the agent is given (data and tools, not generated per solver by hand):**
1. **A problem library (data),** for example monodomain in 1D, 2D and 3D, and
   pseudo-ECG. Each problem gives its equation, exact fields, cell model as
   expressions, parameters, domain, boundary conditions, refinement path and
   provenance. The library is transcribed from the owner's cardiacFOAM
   manufactured models and Pathmanathan & Gray / FDA.
2. **Solver knowledge, per plugin, as data.** How to inject a cell model, set a
   per-node state, apply a source f(x,t), read results, whether a full
   conductivity tensor is supported, whether a pseudo-ECG is output, and the
   numerics: spatial discretisation, time scheme, mass lumping, operator
   splitting.
3. **Deterministic tools, as code.**
   - A symbolic residual check of the generated cell model. It must be zero
     before any run, so a bug in the agent's own code is never reported as a
     solver defect.
   - The refinement sweep through omniD.
   - One error norm.
   - An order fit.
   - A cross-solver table.
4. **A record of each run:** the generated code and its digest go into the
   run's provenance.

**Progression (owner):** verification starts from hexahedral elements, the
configuration with the fewest possible error sources, and builds up from there
(more dimensions, then other element types). That is why cardiacFOAM ships
three manufactured problems.

**Solver knowledge grows with the tests.** What is built now is the
architecture: a declared place for each kind of knowledge, filled solver by
solver as verification runs. For the OpenFOAM family, most numerics options
(`fvSchemes`: gradient, divergence, laplacian, snGrad, interpolation, ddt) ship
with OpenFOAM itself. Their knowledge belongs to the shared OpenFOAM layer, one
reality for cardiacFOAM and cardiacCore. Each solver's own numerics stay in its
plugin, for example cardiacFOAM's time coupling, solution algorithm and
batched ionic integrator.

**What the verifier reports, per solver and problem:**
- the observed order;
- the order this solver's own numerics should give;
- the agent's explanation of any difference. Different numerical methods can
  legitimately give different orders, and that is a result, not a failure.

When most solvers behave as their numerics predict and one does not, the
evidence localises a defect in that solver.

**cardiacFOAM runs its native manufactured models as they are.** The agent
generates for the other solvers.

**Frame and mesh alignment** stays the agent's reasoning (owner, 2026-10-09).

## omnidriver-builder

**Role:** how omniD builds on top of itself, by turning a new solver into a
plugin.

**Exists today, moves here:**
- `core/case_build.py` and the `omnidriver.builders` entry-point group
  (`omnidriver build`, which sits outside the plugin contract today), as
  `omnidriver-build`;
- `scripts/generate-opencarp-catalog.py`, `export-dict-catalog.py`,
  `export-utility-catalog.py` and `regenerate-ionic-catalog.py`;
- `docs/solver-learning/method.md` and `agent-handbook/builder.md`, as the
  builder's guidance.

**Missing, and the main part:** the procedure, made executable step by step:

1. Read the solver's self-description into a catalogue: a C++ scan, `+Help`,
   or a runner's `--describe`.
2. Turn native cases into records.
3. Write the readers.
4. Accept the plugin when conformance C1–C13 passes, plus the benchmarker's
   C14.

**Stays with each solver family:** scanners and catalogues. For example the
OpenFOAM C++ key scanner stays in `omnidriver-openfoam`, shared by cardiacFOAM
and cardiacCore ("one reality").

## Decoupling core, point by point

Four places in core reach into comparison today. Each is resolved as follows.

| place | today | after |
|---|---|---|
| conformance C14 | uses `experiment_comparisons` | moves to the benchmarker |
| `QuantityTarget.resolved` (`core/conformance_study.py`) | loads a benchmark reference to fill in `at` and `pairs` (openCARP declares none) | core no longer reads references. A record whose C13 needs points declares `at` itself, so openCARP's P1–P9 become explicit data in its plugin, as cardiacFOAM's already are. Filling from a reference becomes the benchmarker's job, for C14 |
| `core/experiments.py` `_quantities_status` | recomputes a comparison report's status with `overall_status` | the read model keeps the status the report states. Recomputing it moves to `omnidriver-bench inspect` |
| `cli.py` | imports `PointReferenceError` (for `describe --benchmarks`) and the comparison engine (`compare`) | `compare` moves out. `describe` stops resolving references: its `conformance_quantity` shows the declared points, and `points_from: reference` with the reference's path when none are declared |

## Phases (each reviewed adversarially before merging, as before)

1. **Benchmarker by relocation, with no behaviour change.**
   - Move the modules, schemas, `compare` and C14.
   - Make openCARP's points explicit.
   - Add the import rules.
   - Update `AGENT_GUIDE.md` and the guidance manifest: the evaluator role reads
     the benchmarker.
   - Every verification shape must show 0 failed, and a real `compare` of
     existing reports must give byte-identical reports.
2. **Builder by relocation.** Move the build command, the generators and the
   guidance, with no behaviour change. Then write the procedure, one solver
   (openCARP) at a time.
3. **Verifier,** as an agent plus capabilities: the problem library (from the
   owner's cardiacFOAM manufactured models), per-plugin solver knowledge
   (injection points and numerics), and the deterministic tools. The agent
   generates each solver's verification code.

## Open questions for the owner

1. **Model declaration:** what vocabulary describes a model so that two
   solvers' declarations can be compared (equation form, terms, parameter
   meanings and units, boundary conditions), and where it lives. Each plugin
   owns its declaration. The shared vocabulary cannot be in core (no physics
   there); a natural home is the verifier, as data.
2. **Console scripts:** `omnidriver-bench`, `omnidriver-verify` and
   `omnidriver-build`, each with its own console script, as `omnidriver-agents`
   has. The alternative is to keep one `omnidriver` command that discovers
   subcommands. That would need a new core mechanism, and this spec avoids it.
3. **C14:** in the benchmarker's own `check`, or dropped? It checks the
   sweep-compare-attach mechanism, not agreement.
4. **Package names:** `omnidriver-benchmark`, `omnidriver-verifier`,
   `omnidriver-builder`.
