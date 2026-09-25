# Where omniD stands: generality, the research handoff, and the landscape

**Date:** 2026-09-25 · **Baseline:** `main` at `ff64ba3`, plus the in-flight
`tutorials-are-pointers` branch (`claude/festive-cray-9d30ca`, `19d826a`) where
noted.
**Input:** `omniD_research_architecture_handoff.md` (repo root, untracked; written
2026-09-23 without access to the code), which asks for every architectural
statement to be classified as implemented / partial / easy extension / major
missing / research experiment, and lists 45 code questions and 13 claims not to
publish until proven.
**Method:** four read-only code surveys (core generality, the three plugin
packages, execution/models/verification, a record traced through core on the
branch), one external-landscape survey of about 30 tools, and a real openCARP
v18.1 run. Findings that were re-checked by hand are marked *(verified)*.

This document is the reasoning behind
`docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md`.

## 1. The handoff's architecture against the code

```
handoff layer           what the repository has
───────────────         ───────────────────────────────────────────────────────
omniD reasoning      →  not in the repo, by design. The agent is an external
                        coding agent routed by AGENTS.md roles. No LLM provider
                        code, no MCP server, no typed tool API. The guidance
                        launcher in agent-handbook/provider-integration.md is
                        documented, not built.
application iface    →  real and enforced: 27 capability seams, an empty import
                        waiver list, a transactional case-write channel
                        (CaseMutationRequest → resolve_case_mutation →
                        render_case_files → commit_case_write). OpenFOAM-shaped;
                        see §2.
executor iface       →  absent. Local subprocess only (run_workflow_step,
                        sweep_runner._run_case_process); no resource object; no
                        Slurm/PBS/LSF/SSH. The seam is clear, but step success
                        (leases, before/after artifact snapshots, orphan
                        detection) assumes a synchronous local process.
deterministic solver →  yes.
validation           →  test-only. equivalence_protocol.yaml (87 rows) and the
                        tolerance harness live in tests/. In the product,
                        run_postprocess_phase always returns not_configured,
                        RuntimeEvidenceCapability.artifact_value_reader is never
                        consumed, and experiments.ComparisonRequest only passes
                        through a checker's report.
```

| handoff statement | class |
|---|---|
| application interface separate from reasoning | implemented |
| executor interface | major missing (seam: easy extension) |
| tutorial-grounded clone-and-patch adaptation | implemented; strongest part of the repo |
| structured mutation instead of raw text | implemented; G3 not closed (nine bypasses, Phase 3 Task 11) |
| READMEs as agent grounding | missing. All 19 native case READMEs exist in the external cardiacFoam tree; no code reads them |
| per-tutorial machine-readable metadata | partial (`TutorialDisplay` tags; `export-tutorials-catalog.py` on demand); becoming data under tutorials-are-pointers |
| unsupported-request recognition | partial: strict planning refuses by name; cardiacCore has `support_boundary` |
| task levels (interpolate / adapt / compose / OOD) | research experiment |
| replaceable and specialist models | research experiment; nothing blocks it, nothing exercises it |
| deterministic numerical validation | partial, test-only |
| FSI | major missing; nearest is solids4foam electromechanics (`backend: full`) |

### The 13 claims

| claim | verdict |
|---|---|
| solver-agnostic | partial: no cardiac vocabulary (enforced); OpenFOAM shape throughout (not enforced) |
| application-independent | untested: one application family, OpenFOAM, through two plugins |
| HPC-independent; portable across schedulers | no |
| model-independent; supports local models | vacuously true (no model code); never exercised; no typed tool surface a small model could drive |
| supports arbitrary OpenFOAM cases | no: `case_folder` entries exist, uncatalogued keys are unvalidated |
| autonomous; self-correcting | no: `run_repair_loop` and `experiments.py` have no production caller |
| physically validated | partial, test-only |
| generalizes across solvers | no evidence |
| privacy-preserving; works with patient data | omnidriver makes no network calls (no requests/urllib/httpx/socket); the agent host is unaudited. Scope any claim to the tool |

## 2. Three layers of agnosticism; only the first is guarded

1. **Vocabulary**: core names nothing cardiac. Achieved and gated by
   `scripts/check-import-boundaries.py`. Two leaks the gate does not see,
   because they are names, not imports: `omnidriver/dict_entries.py` exports
   `get_heterogeneity_models` and `get_electro_property_entry_groups`, and
   openfoam's `function_object_fields` defaults the region to `"electro"`.
2. **Shape**: core does not assume the world looks like an OpenFOAM case. Not
   achieved and not gated.
   - A run is a case directory: `TutorialSpec.case_root`, case-relative
     `WorkflowStep.cwd`, sweeps copy trees.
   - A step is a CLI subprocess: authorization by command name;
     `CORE_NEUTRAL_COMMANDS` holds `mpirun`/`mpiexec`/`orterun`.
   - Outputs are time directories: `DataArtifact`'s `{time}`,
     `CaseRuntimeConventions.time_directory_name_pattern`,
     `get_selected_start_time` mirroring `Time::findInstance`.
   - Configuration is dictionaries: `DictEntry`, `VALUE_KINDS` with
     `dimensioned_*`, `$TOKEN` scopes, `cxx_mapping` and C++ key scanning.
   - The environment is a sourced shell profile: `--environment-bashrc`,
     `get_loaded_environment`.
   - Core's default run script is `scripts/run_case.sh` (Allrun, blockMesh,
     `case.foam`).
   - Core's own records (`workflow_state.json`, `run_document.json`,
     `sweep_manifest.json`, `workflow_logs`) are declared only by
     `openfoam_case_runtime_conventions()`.
3. **Paradigm**: in-process Python, surrogates, GPU jobs. Not achieved. The
   only way to run a Python callable is to wrap it as an executable.

The empty waiver list proves core is not *cardiac*. It does not prove core is
*general*. What each candidate solver would hit today:

| candidate | hits |
|---|---|
| openCARP, LAMMPS, SU2 (file + CLI + MPI) | fits the shape; needs a non-FOAM format adapter, and `openfoam-environment` is the only one that exists |
| FEniCS/dolfinx | no dictionaries; XDMF, not time directories; ten required members to stub |
| PyTorch surrogate, in-process ODE | blocked by "step = subprocess" and "run = directory" |

## 3. What a second plugin gets for free, and what it rebuilds

**Free:** DAG execution (state, resume, recover, leases, retry, backoff);
command gating; failure classification; RunDocument and strict-planning
diagnostics; SHA-256 provenance; provider-stack composition; the transactional
case-write channel; sweep expansion and staging; report and utility catalogs;
plot and table helpers.

**Rebuilt from scratch:** the whole environment/format tier (environment
loading, installed-command check, runtime conventions, config reader, override
application, renderer, effective-config inspection); the domain tier (catalog,
case mutation, tutorials, artifact prediction, telemetry, post-processing, sweep
routing). No artifact-value reader exists anywhere to copy.

**Code that sits a layer too high** (candidates to push down, not scoped here):
- In cardiacfoam, but generic to any OpenFOAM app: `CONTROL_DICT_ENTRIES`;
  `rtst_scanner`; `runtime_evidence`'s `controlDict libs` resolution and
  `log.*` globs; `runtime_profile`'s binary-build checks;
  `commit_case_overrides`/`merge_assignments`; the repeated FoamFile header;
  the meshless 1-cell polyMesh trick.
- In openfoam, but generic to any mesh workflow: `classify_scale` unit
  sniffing, `cell_counts_from_dx`, the decompose → mpirun → reconstruct
  DAG pattern.

## 4. The external landscape

| tool | core mechanism | use for omniD |
|---|---|---|
| Foam-Agent (MIT) | LangGraph Architect/Writer/Runner/Reviewer; FAISS over tutorials; repair loop stops on a repeated error fingerprint; MCP server | compare; borrow the fingerprint stop and the read-only-import + writable-copy pattern |
| FoamBench / CFDLLMBench | success = runs and NMSE ≤ 10% against a reference OpenFOAM run | external eval point; weak reference (same solver, loose bar) |
| sim-cli (Apache-2.0) | solver-agnostic core; per-solver driver + skill; CAE files → JSON inventories; bounded steps | nearest architectural sibling; commercial CAE, no verification layer |
| ChatCFD (CC BY-NC-SA) | structured knowledge bases (BCs, dimensions, templates); reports execution (82.1%) separately from physical fidelity (68.1%) | adopt the metric split; do not copy code |
| "Beyond a generic harness" (arXiv 2609.03718) | a single generic agent with tutorials and execution-feedback repair: 96.4% on FoamBench against Foam-Agent's 88.2%; the ablation credits tutorials and repair, not roles | evidence for keeping reasoning in an external host with no role machinery |
| ALL-FEM (CMAME 2026) | LoRA-tuned open models on about 1,000 FEniCS scripts; 7-role pipeline; graded visually and by LLM judge | compare; do not follow the fine-tuning route |
| Constrained FEniCS NL interface (arXiv 2606.10928) | the LLM emits validated JSON only; dispatched to verified templates | adopt: this is the right agent/knowledge split |
| JutulGPT (SINTEF, MIT) | interpret–act–validate loop; lint before run; key lesson: silently inherited solver defaults were the worst failure | adopt the lesson; it restates supplied-vs-discovered at the solver boundary |
| AiiDA (MIT) | provenance DAG; `CalcJob` + `Parser` returning **named exit codes**; hash caching with explicit invalidation; Transport/Scheduler plugins | adopt exit codes and cache design; do not rebuild the engine |
| signac (BSD-3) | job directory named by the hash of its statepoint | adopt for sweep addressing |
| PSI/J (MIT) | portable scheduler API: JobSpec, ResourceSpec, JobExecutor, Launcher, normalized states | integrate as the executor backend; do not write a Slurm layer |
| Snakemake 8 | executor plugins built against separately versioned interface packages | adopt the packaging pattern for the plugin contract |
| Workflow Run RO-Crate | JSON-LD provenance (`CreateAction`: instrument, object, result) | export only |
| EasyVVUQ / Dakota | Encoder (write inputs) / Decoder (read outputs) drive any black box | expose Encoder/Decoder; implement no UQ |
| preCICE (LGPL-3) | coupling library; each solver keeps its own loop | treat a coupled run as one opaque node |
| openCARP + carputils (APL / Apache-2.0) | experiments are Python `run.py` scripts; test = fixed run + check (`max_error`) against references kept in a separate repo | adopt the example → test → check ladder; first solver outside OpenFOAM (see the spec) |
| Chaste (BSD-3) | continuous / nightly / weekly test packs; passes Pathmanathan & Gray | adopt tiered packs |
| Cardiac-Digital-Twin (MIT) | modular pipeline with separate Discrepancy and Evaluation | compare |

Sources: github.com/csml-rpi/Foam-Agent · arxiv.org/abs/2509.20374 ·
github.com/svd-ai-lab/sim-cli · arxiv.org/abs/2506.02019 ·
arxiv.org/abs/2609.03718 · doi.org/10.1016/j.cma.2026.118985 ·
arxiv.org/abs/2606.10928 · github.com/SINTEF-agentlab/JutulGPT ·
aiida.readthedocs.io · github.com/glotzerlab/signac ·
github.com/ExaWorks/psij-python · snakemake.github.io/snakemake-plugin-catalog ·
researchobject.org/workflow-run-crate · github.com/UCL-CCS/EasyVVUQ ·
precice.org · opencarp.org · github.com/Chaste/Chaste ·
github.com/juliacamps/Cardiac-Digital-Twin.

### Where omniD is differentiated

- **Verification attached to the knowledge the agent retrieves.** Every agentic
  simulation system surveyed grades itself on execution. None attaches
  deterministic checks (MMS, exact solutions, N-version consensus) to its
  reference cases. omniD already owns the material: manufactured tutorials,
  `niederer_2012`, the 87-row protocol. It sits in `tests/`.
- **A core with no solver vocabulary, enforced by a gate.** The OpenFOAM agents
  are OpenFOAM-shaped throughout; sim-cli has no orchestration, provenance or
  post-processing.
- **Cardiac EP under an agent-operated orchestrator.** Nothing comparable was
  found for openCARP, Chaste, lifex or cardiacFoam.
- **Effective-configuration provenance.** No surveyed tool records which values
  a run inherited from solver defaults. openCARP's own `parameters.par` records
  what was supplied (verified); `+Help` holds the defaults.

### Where omniD would be re-inventing

A general DAG engine (AiiDA, Snakemake); a scheduler layer (PSI/J); a
provenance database (export RO-Crate instead); a parameter-study data space
(signac); samplers or PCE (Encoder/Decoder); multi-agent role pipelines (the
2609.03718 ablation); fine-tuned domain models.

## 5. Where this audit disagrees with the handoff

- **"omniD owns reasoning" (§1, §10).** Inverted: omniD owns no reasoning. It
  owns the contract that makes reasoning checkable. Model routing belongs to
  the agent host. omniD is model-independent by exposing a typed surface small
  models can drive, not by routing between models.
- **Per-tutorial `manifest.yaml` (§5).** As proposed, it restates facts other
  layers own: `modifiable` is the key catalog plus axes, and `relevant_files` is
  the case profile. Under one-source-of-truth, a manifest holds only what
  nothing else owns: checks, and the unsupported envelope.
- **openCARP (§7, §17).** The handoff frames it as the cross-solver *paper*
  experiment. Owner decision 2026-09-25: it is first the proving case for "any
  solver can plug in". It is file + CLI + MPI, so it will not exercise the
  paradigm layer, but it does exercise the format, environment and output
  parts of the shape layer.
- **Executor (§8).** Agreed, but the hard part is not scheduler syntax (PSI/J
  handles that). It is that `run_workflow_step`'s success logic assumes a
  synchronous local process.

## 6. Benchmarks with deterministic correctness (for later topics)

Rule: the reference is never "the same solver's tutorial output", and the pass
criterion is a convergence rate or a tolerance against independent data, never
"it ran".

- **Niederer 2011 N-version** (doi 10.1098/rsta.2011.0139). A 20×7×3 mm slab,
  tenTusscherPanfilov EPI, activation times at P1–P9, Δx ∈ {0.5, 0.2, 0.1} mm ×
  Δt ∈ {0.05, 0.01, 0.005} ms, against an 11-code consensus. openCARP ships it
  as `02_EP_tissue/03E_study_resolution` (verified); cardiacFoam has
  `niederer_2012`. This is the natural cross-solver benchmark.
- **Pathmanathan & Gray 2014** (FDA regulatory science tool): nine EP problems
  with exact solutions; pass = observed order of convergence.
- **Land et al. 2015**: cardiac mechanics benchmark, for electromechanics.
- **CFD**: MMS via `fvOptions`; lid-driven cavity against Ghia 1982 as a
  tolerance band; Kovasznay, Taylor–Green, Poiseuille/Couette (exact to
  round-off, so failures point at BC or dictionary errors); Schäfer & Turek
  1996 cylinder.
- **Agent-level reporting**: three numbers per task. *Executed*;
  *specification-faithful* (the resolved configuration equals the intended
  one, a diff of effective configurations); *verified* (the check passes).

## 7. Defects found during this audit

- `packages/omnidriver-cardiacfoam/tests/regression_equivalence/dual_run.py::check_protocol`
  uses `omnidriver.__file__`, but the module never imports `omnidriver`
  *(verified)*. Tests monkeypatch the function, so the real path is never
  exercised. Filed as a separate task.
- Two findings on the in-flight branch: records cannot reach `plan --strict` /
  `run --strict`, and render snapshots are seeded empty. Both are carried into
  the spec as prerequisites P1 and P2.
- The `dual_run.verify_reproduction` "generic" driver reports `"reproduced"`
  when the committed `regressionTest.sh` passes; it does not exercise the agent
  path.
- Stale docstring: `strict_planning` says core "classifies every polyMesh
  region".
