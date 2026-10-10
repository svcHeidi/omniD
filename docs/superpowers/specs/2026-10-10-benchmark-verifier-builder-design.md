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

**Role:** verification, in two levels, independent of any one solver and of
how it discretises (FEM, FVM or anything else).

1. **Model parity, across solvers, with no run.** Do two solvers implement the
   same mathematical model, meaning the same equations, terms and definitions?
   The verdict is "same model", or the term or definition that differs. For
   example:
   - how the reaction term is scaled (χ·Cm);
   - how conductivity reduces to the monodomain;
   - what a stimulus strength is normalised by;
   - the boundary conditions;
   - the cell model and its version.

   For this, each solver declares its model as data an agent can act on, not
   prose. The variable-mapping evidence
   (`docs/solver-learning/cross-solver-variables.md`) shows what such a
   declaration must cover: it found a stimulus normalised differently and two
   versions of one cell model.
2. **Numerical verification, per solver.** A manufactured problem with an
   analytical solution, run over refinement levels. The check is whether the
   observed order of convergence matches the formal order the solver's
   discretisation claims, within a stated tolerance on the slope. That claim
   is data too: each scheme a solver offers declares its formal order.

Every verdict is JSON with a code, like every refusal. Frame and mesh alignment
stays the agent's reasoning (owner, 2026-10-09).

**What the plugins supply,** as data through the plugin contract:
- a declaration of the model each record solves;
- the formal order of each scheme;
- the manufactured cases and the reader for their error norms.

Their exact shape is written from the owner's verification code, not invented
ahead of it.

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
3. **Verifier,** from the owner's verification code. The model declaration,
   the formal orders and the manufactured-case readers are written from that
   code, not invented ahead of it. The numerical level can start from
   manufactured cases that solvers already ship.

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
