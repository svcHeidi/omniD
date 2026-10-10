# Publication plan: two papers from omniD

**Status:** plan for the owner's review, 2026-10-10. Nothing runs until it is
approved. Four literature searches (2026-10-10) back it, kept in
`docs/superpowers/reports/literature-2026-10-10/`. Their citations are below; claims marked "not found" rest on one search pass and are rechecked
before submission.

## The two papers

| | Paper 1 (first) | Paper 2 (second) |
|---|---|---|
| question | Do independent cardiac EP solvers solve the same model correctly, and how do finite-element and finite-volume discretisations differ? | Does omniD make LLM agents better at setting up, running and comparing cardiac simulations? |
| contribution | an automated verification layer applied across discretisations | a controlled with/without evaluation of that layer |
| omniD's role | the instrument (the verifier package) | the treatment |
| answer key | the manufactured solutions' exact answers, and the published benchmark | paper 1's verified results |
| venue | IJNMBE or Frontiers in Physiology; optionally a Computing in Cardiology abstract first | arXiv, then NeurIPS Evaluations & Datasets (2027 cycle), TMLR or Digital Discovery |

The two answer distinct questions and are disclosed to each editor, so neither
is redundant. A preprint is not prior publication at Elsevier or PLOS. Every
venue needs the code public under an OSI licence at review, and the licence is
the owner's decision, to be made later.

## Paper 1: automated cross-discretisation verification of cardiac EP solvers

**Claim, as narrow as the evidence allows:**

> To our knowledge, the first framework that generates the same
> manufactured-solution problem, injects it into independent finite-element
> and finite-volume solvers through per-solver plugins, runs them, and
> compares observed orders of convergence, preceded by a model-parity check,
> applied to cardiac electrophysiology.

It does not claim that automating manufactured solutions is new: MASA, MOOSE
and Ramoa et al. 2022 for OpenFOAM all exist, each within one code.

**Problem set:** the nine cardiac manufactured-solution problems of Pathmanathan
& Gray 2014, republished by the FDA as RST24CV03.01. They are published and
citable, and so far only implemented by hand, one code at a time. The gap is
the automation across codes.

**Solvers:**

| solver | discretisation | published | role |
|---|---|---|---|
| openCARP | FE, structured tets | yes | reference FE code |
| TorchCor | FE on GPU | yes (SoftwareX 2026) | the same FE formulation re-implemented on GPU: a consistency check, not an independent discretisation |
| cardiacFOAM | FV, hex and tet, OpenFOAM-based | no; its first verification is part of the contribution | the FV code this work develops |
| MonoAlg3D | FV, structured, GPU | yes | a published FV code, so the FV side does not rest on cardiacFOAM alone (owner, 2026-10-10) |

**Layers, in the verifier's order:**
1. **Model parity:** do the solvers implement the same equations, terms and
   definitions? This draws on the verified variable mappings
   (`docs/solver-learning/cross-solver-variables.md`), for example a stimulus
   normalised per tissue volume in one solver and per membrane area in another.
2. **Code verification:** the observed order against each solver's own claimed
   order, and error levels at common nodes, for FE and FV alike. This includes a
   rotated-tensor case that exercises the wall condition.
3. **Physical benchmark:** Niederer 2011 at dx 0.5, 0.2 and 0.1 mm, aligned and
   oblique fibres, on each solver's own mesh and on shared meshes.
4. **Findings already in hand:**
   - FV accuracy depends on hex vs tet;
   - with oblique fibres, a `zeroGradient` wall gives P3 = P7 exactly, while
     sealed/conormal walls match FE no-flux behaviour;
   - at coarse dx, mesh type dominates FE results (Wülfers 2016 is the
     precedent).

**What reviewers will raise, and the answers to prepare:**
- **"The nine problems already exist."** Yes: they are the foundation, cited.
  The contribution is running them automatically across discretisations.
- **"What does comparing orders across FE and FV show?"** Each code against its
  own formal order, plus error levels on common nodes.
- **Wülfers 2016** (grid regularity shifts activation times as much as mass
  lumping) must be checked against the hex-vs-tet result before it is a claim.
- **Limits of manufactured solutions with nonlinear ionic models and operator
  splitting** (Pathmanathan & Gray discuss this).
- **cardiacFOAM is unpublished:** MonoAlg3D covers the published FV side.

## Paper 2: agents with vs without omniD

**Claim:** a controlled evaluation of a solver-agnostic validation layer built
from each solver's own source. It focuses on the failure class prior work
reports as worst: runs that silently inherit wrong defaults, or that run and
solve the wrong physics (JutulGPT, MooseBench, Judge Agent). It does not claim
to be the first solver tool layer for agents (Foam-Agent, ChatCFD) or the first
validator for generated input (Judge Agent).

**Design (to be fixed in a pre-registration before any trial):**
- **arms:** bare solver; solver plus good documentation; omniD;
- **models:** at least two model families;
- **trials:** at least 5 per task per arm, with confidence intervals and
  pass^k;
- **tasks:** perturbed or held-out, against contamination;
- **oracles:** independent of omniD's catalogues, from paper 1's verified
  results;
- **failure taxonomy:** loud error, silent inherited default, wrong physics,
  and which of them omniD turned into refusals;
- **cost:** tokens, dollars, wall time and solver launches, reported with
  accuracy;
- **isolation:** each trial has its own home, with no memory, plugins or
  `CLAUDE.md`; verified by a probe first.

## Prerequisites, in order

1. **The verifier package** (spec `2026-10-10-benchmark-verifier-builder-design.md`),
   now paper 1's method. It holds the problem set, the per-solver injection
   through plugins, and the order analysis. Its contract is written from the
   owner's verification code.
2. **MonoAlg3D,** learned and onboarded as a plugin through the method in
   `docs/solver-learning/method.md`. Check first that it builds on this machine
   without CUDA.
3. **The Wülfers check** against the hex-vs-tet result.
4. **Niederer at dx 0.1 mm** on all solvers (cluster).
5. **For paper 2,** the harness additions:
   - a docs-only arm;
   - an adapter for a second model family;
   - a failure-taxonomy field in the task record;
   - perturbed tasks;
   - independent oracles.

   Then the pre-registration.
6. **The licence and a public repository** (the owner's decision, later). This
   is needed before either paper goes to review.

## Citations gathered

- Niederer et al. 2011, Phil Trans R Soc A 369:4331, doi 10.1098/rsta.2011.0139
- Pathmanathan et al. 2012, IJNMBE 28:890, doi 10.1002/cnm.2467
- Pathmanathan & Gray 2014, IJNMBE 30:525, doi 10.1002/cnm.2615
- FDA RST24CV03.01, cardiac EP code verification problems, https://cdrh-rst.fda.gov/node/1576
- Wülfers, Dössel & Seemann, Computing in Cardiology 2016, https://cinc.org/archives/2016/pdf/054-405.pdf
- de Lima et al., Computing in Cardiology 2025, doi 10.22489/CinC.2025.376. MonoAlg3D vs openCARP on the Niederer slab and a ventricle: mostly timing, accuracy compared visually, no manufactured solutions, not automated.
- MonoAlg3D, https://www.biorxiv.org/content/10.1101/2025.04.09.647733
- TorchCor, arXiv 2510.12011; SoftwareX 2026, doi 10.1016/j.softx.2026.102521
- Land et al. 2015, cardiac mechanics verification benchmark, https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4707707/
- Roy 2005, J Comput Phys, https://doi.org/10.1016/j.jcp.2004.10.036; Oberkampf & Roy 2010; Salari & Knupp 2000
- Malaya et al. 2013, MASA, doi 10.1007/s00366-012-0267-9
- Ramoa et al. 2022, MMS for OpenFOAM, https://journal.openfoam.com/index.php/ofj/article/view/75
- NASA Turbulence Modeling Resource, https://ntrs.nasa.gov/citations/20160000768
- Agents: JutulGPT (arXiv 2603.00214), MooseBench (2605.09360), Judge Agent (2603.25780), Foam-Agent (2509.18178), ChatCFD (2506.02019), CFDLLMBench (2509.20374), ChemToolAgent (2411.07228), AI Agents That Matter (2407.01502), τ-bench (2406.12045)
