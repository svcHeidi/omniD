# Novelty check: automated cross-solver MMS verification (cardiac EP)

[V] = read in full or substantially; [S] = search snippet/abstract/summary only. Not every search was exhaustive; absence of evidence is not proof of absence.

## 1. General MMS tooling (single-code unless stated)
| Tool | Source injection | Observed order | Cross-code |
|---|---|---|---|
| MASA (Sandia/UT Austin) [S] https://sourceforge.net/p/masa/ ; Malaya et al., Eng. Comput. 2013, doi:10.1007/s00366-012-0267-9 | Library of manufactured solutions plus forcing terms (CAS/automatic differentiation), with C/C++/Fortran/Python APIs. The host code calls MASA to get its source. | No | No. One library serves many codes, but nothing orchestrates or compares them. |
| MOOSE MMS tooling [S] https://mooseframework.inl.gov/ | Symbolic source terms (SymPy) in the input. Its python tools include convergence-data utilities and CI "verification" tests. | Yes, inside MOOSE tests | No, MOOSE only |
| OpenFOAM semi-automatic MMS, Ramoa/Costa/Chinesta/Nóbrega, OpenFOAM Journal 2022 [S] https://journal.openfoam.com/index.php/ofj/article/view/75 | SymPy source terms, generated BCs and error-norm code | Yes (error norms plus convergence order) | No, OpenFOAM only. **Nearest FV prior art.** |
| Firedrake/FEniCS [S] | UFL symbolic differentiation makes MMS easy. I found no dedicated automated-MMS package. | Per user script | No |
| ExactPack (LANL) [S] https://arxiv.org/pdf/1701.07342 | Exact solutions behind one API, not MMS sources | Analysis tools included | Compares one code to exact solutions |
| Tri-Lab Verification Test Suite, LA-UR-05-6865 [S] https://cococubed.com/papers/la-ur-05-6865.pdf | Automated analysis of suite problems on uniform and adaptive grids | Yes | Multi-lab, on exact solutions rather than MMS, and no source injection |
| EasyVVUQ / VECMA [S] https://easyvvuq.readthedocs.io | None. It is a forward-UQ campaign tool wrapping any code. | No | Runs any code, but does no code verification |
| Roy 2005 [S] J. Comput. Phys. 205:131, https://doi.org/10.1016/j.jcp.2004.10.036 | Methodology, not a tool | Defines observed order | Single code |
| Chalmers OpenFOAM V&V test suite [S] https://odr.chalmers.se/handle/20.500.12380/250253 | Not checked | Not checked | OpenFOAM only |

## 2. Cross-code verification
- NASA Turbulence Modeling Resource (FUN3D, USM3D, CFL3D grid-convergence studies) [S] https://ntrs.nasa.gov/citations/20160000768. It is explicitly code-to-code agreement under grid refinement, with FV codes and benchmark problems. It is run by hand per paper, uses no MMS, and has no source-injection framework. A reviewer will cite it as the CFD analogue.
- I found no framework that auto-generates one MMS problem and injects it into several codes across FE and FV families. [S] The searches returned only single-code MMS papers.
- Caveat: one solver family being FE and another FV is normally studied by hand; PyLith and others have in-code MMS suites [S] https://pylith.readthedocs.io/en/stable/developer/testing/mmstests.html.

## 3. Cardiac EP
- Pathmanathan & Gray 2014, IJNMBE 30:525, doi:10.1002/cnm.2615 [S]. Nine analytic MMS problems (monodomain, bidomain and bidomain-with-bath in 1D, 2D, 3D), verified in Chaste (linear FE). Manual, single-code.
- FDA CDRH tool RST24CV03.01 [V, intro read] https://cdrh-rst.fda.gov/node/1576. It republishes the nine problems. The user "should specify each ... in their software, solve ... and compare". It is a manual document, and the tool page says Chaste and one commercial vendor tested it. **This is the most important prior art: the problems exist, and nothing is automated or cross-code.**
- Niederer et al. 2011, Phil. Trans. R. Soc. A 369:4331, https://pmc.ncbi.nlm.nih.gov/articles/PMC3263775/ [S]. 11 codes, manual, community submission, on a physical benchmark rather than MMS.
- Pathmanathan et al. 2012 (IJNMBE, doi:10.1002/cnm.2467) [S], on explaining solver variability.
- Land et al. 2015, Proc. R. Soc. A 471:20150641, https://eprints.whiterose.ac.uk/93701/ [S]. 11 groups, cardiac mechanics benchmark, manual.
- lifex-ep, https://arxiv.org/pdf/2308.01651 [S]; TorchCor, https://arxiv.org/pdf/2510.12011 [S]. Both verify against the Niederer benchmark. I could not confirm whether either does an MMS convergence study.
- I did not locate published openCARP or Chaste regression suites in detail. openCARP has benchmark examples [S] https://opencarp.org/documentation/examples.

## 4. de Lima et al., CinC 2025 [V, full text read]
"Benchmarking Open Cardiac Electrophysiology Simulators: MonoAlg3D and OpenCARP", doi:10.22489/CinC.2025.376 (https://www.cinc.org/archives/2025/pdf/CinC2025-376.pdf). MonoAlg3D is FV (GPU/OpenMP) and openCARP is FE (MPI).
- Three cases. (1) Niederer slab, 20x7x3 mm, ten Tusscher 2006, fibres along x, 80 ms, dt=0.02 ms. (2) Same geometry with O'Hara-Rudy, dt=0.005 ms. (3) A ventricular mesh from the Rodero virtual cohort. It was re-meshed to ~500 um for MonoAlg3D (1,306,274 volumes) and kept at 1 mm for openCARP (1,340,386 elements), so the meshes were NOT matched.
- Resolutions for Cases 1-2: 250, 100 and 50 um. Each setting ran 10 times.
- Metrics: wall-clock time (mean and SD), the PDE/ODE time split, scaling, and (Case 1 only) activation times along the slab diagonal, compared qualitatively in a figure. "Congruent" is a visual claim, with no error norm.
- No MMS, no observed convergence order, no manufactured source. Convergence is shown only as curves approaching each other. Nothing is described as automated; it reads as a hand-run performance benchmark.
- It shows the FE/FV cross-code comparison has been done in cardiac, but as performance plus a physical benchmark.

## 5. Other multi-solver cardiac comparisons
I found none beyond the above, including 2025-26 commercial plus open-source preprints [S: several searches]. This is a negative from search snippets only. Recheck bioRxiv/arXiv close to submission.

## Judgement
Facts vs. my reading:
- The strong claim as stated ("no published tool ... SEVERAL solvers ... FE and FV ... runs ... compares orders; nothing like it for cardiac EP") is not defensible without hedging. Absence claims are hard to prove, and parts are weakly supported: MASA supports multi-code source injection, and EasyVVUQ-like harnesses orchestrate many codes. The decomposed capabilities (source generation, injection, order computation) each exist.
- A claim I would defend, subject to a final search: "to our knowledge, the first framework that automatically generates the same MMS problem, injects it into independent FE and FV solvers through per-solver plugins, executes them and compares observed orders (and model-parity checks) across solvers, applied to cardiac EP."
- Drop "nothing like it exists"; say "we found none". Don't assert novelty of MMS or per-code automation (MASA, MOOSE, Ramoa 2022 own that). The novelty is the orchestration across solvers plus model-parity gating before verification.
- Reviewer attacks: (a) FDA/Pathmanathan nine problems already exist, so reuse them as the problem set and cite as foundation; (b) "observed orders differ across FE and FV, so what does comparison show?" Have an answer (orders against each code's own formal order, plus error levels on common nodes); (c) cardiacFOAM is unpublished, so the FV claim rests on MonoAlg3D or another published FV code; (d) MMS with nonlinear ionic models and tolerances (Pathmanathan notes sources and splitting-error limits).
- Must cite: Roy 2005; Oberkampf & Roy 2010 (book); Salari & Knupp 2000 (SAND2000-1444); Malaya 2013 (MASA); Pathmanathan & Gray 2014; FDA RST24CV03.01; Niederer 2011; Pathmanathan 2012; Land 2015; Ramoa 2022 (OpenFOAM MMS); de Lima 2025; NASA TMR (Rumsey et al.); EasyVVUQ (Richardson 2020); MOOSE verification.
