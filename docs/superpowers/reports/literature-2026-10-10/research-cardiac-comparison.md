# Cross-solver cardiac EP comparison: literature check (2026-10-10)

Method: web search plus reading of several PDFs. Items marked [V] I read at source; [S] come from search snippets only; [J] are my judgement. Not found is stated explicitly. Search coverage was one pass, so absence of a paper is not proof.

## 1. Follow-ups to Niederer 2011

Verified [V]/[S]:
- Original: 11 solvers, 20x7x3 mm slab, ten Tusscher-Panfilov, fibres along x. Mass lumping combined with operator splitting was identified as the main cause of CV error. https://pmc.ncbi.nlm.nih.gov/articles/3263775 [S]
- Pathmanathan et al., IJNMBE 28(8):890-903 (2012), doi 10.1002/cnm.2467, explains the solver variability (title confirmed; abstract not read). https://www.cs.ox.ac.uk/publications/publication5482-abstract.html [V title]
- Pathmanathan & Gray, IJNMBE 30(5):525-544 (2014), doi 10.1002/cnm.2615. Nine manufactured-solution test problems; Chaste converges at the theoretical rate for linear FE; the metric is activation time. https://www.cs.ox.ac.uk/publications/publication5482.bib (bibliographic entry via search) [S]
- Wulfers, Dossel, Seemann, Computing in Cardiology 43 (2016): node-arrangement regularity changes CV about as much as mass lumping. At 0.7 mm a regular grid gives AT 80.01 ms, a triangulated grid 47.52 ms, reference 42.82 ms; CV rises monotonically with node perturbation. https://cinc.org/archives/2016/pdf/054-405.pdf [V]. This is the closest precedent to your structured-vs-unstructured-tet 25 ms finding.
- Arthurs, Bishop, Kay (2012), high-order FE; cites the benchmark only as future work. https://pmc.ncbi.nlm.nih.gov/articles/PMC4067136 [V]
- Jilberto & Hurtado, Front Physiol 9:1513 (2018): non-conforming Q1NC elements run the Niederer benchmark on meshes up to 8x coarser. https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2018.01513/full [V]
- Lindner et al., IJNMBE 39(2):e3666 (2023): splitting schemes, reference solution on an LV ellipsoid (Beeler-Reuter). Not the Niederer slab. https://www.waves.kit.edu/downloads/CRC1173_Preprint_2022-35.pdf [V title, rest S]
- de Lima et al., CinC 2025 (52): MonoAlg3D (finite volume, structured, GPU) vs openCARP on the Niederer slab at 250/100/50 um, plus O'Hara-Rudy and a human ventricle. Reports "numerically congruent" activation times. Compares performance mainly. https://www.cinc.org/archives/2025/pdf/CinC2025-376.pdf [V]. This is the only FV-vs-FE Niederer comparison I found; it uses structured grids and aligned fibres only.
- TorchCor (Zhou, ..., Niederer): arXiv 2510.12011; SoftwareX. Verified with a manufactured decaying-wave solution on a 100x100 grid (error plotted, no formal convergence orders reported) and the N-version benchmark at dx 0.5/0.2/0.1 mm, compared with Chaste and FEniCS references. https://arxiv.org/html/2510.12011v1 [V]. Implication: dx 0.1 mm on the benchmark is already done by TorchCor.
- CEPS (Inria/Liryc), JOSS 2025, doi 10.21105/joss.08910, an exploratory solver; I did not confirm whether it runs the benchmark. https://www.theoj.org/joss-papers/joss.08910/10.21105.joss.08910.pdf [V title only]
- Not found: a post-2011 multi-solver re-run covering FV and FE with oblique fibres, bidomain, or more than two solvers. None found for openCARP-vs-Chaste-vs-CARPentry either. The openCARP documentation has a Niederer resolution example, not a paper: https://opencarp.org/documentation/examples/02_ep_tissue/03g_study_resolution [S]

## 2. Finite-volume cardiac EP
- Harrild & Henriquez, Ann Biomed Eng 1997, FV model of cardiac propagation, arbitrary fibre orientation. https://link.springer.com/article/10.1114/1.1567283 [S]
- Coudiere & Pierre, FV bidomain on unstructured meshes with stability and convergence proofs; DDFV convergence paper, https://arxiv.org/pdf/1010.2718 : first-order-ish rates, proved for diagonal tensors in one scheme. https://cpierre1.perso.univ-pau.fr/fvca4paper.pdf [S]
- MonoAlg3D (FV, structured, GPU): https://www.biorxiv.org/content/10.1101/2025.04.09.647733.full.pdf [S]
- Not found: any published OpenFOAM-based cardiac EP solver, or any FV-vs-FE study of mesh type or orientation effects on CV (hex vs tet), beyond Wulfers for FE. Your hex-vs-tet result in an FV code looks unpublished.

## 3. Wall boundary conditions with anisotropy
- Standard formulation: zero flux in the conormal sense, D grad v . n = 0, not dv/dn = 0 [S, e.g. arXiv 1805.00757]. With D rotated relative to the wall, a zeroGradient (dv/dn = 0) condition imposes a different flux. That is consistent with your P3=P7 symmetry, but I found no paper that discusses this error for FV solvers. DDFV papers treat the conormal flux properly (Coudiere/Pierre above).
- Treat this as a judgement gap: the explicit demonstration (zeroGradient vs conormal, rotated fibres, activation time) appears novel, but only one search pass supports that.

## 4. Venues [J unless cited]
- Phil Trans A: the original venue; novelty bar high, expects consensus across several independent codes.
- IJNMBE: hosted Pathmanathan 2012/2014 and Lindner 2023; the natural home for MMS plus benchmark work.
- Front Physiol: hosted Jilberto 2018; lower bar, tolerates tool-oriented papers.
- CinC: de Lima 2025, Wulfers 2016 precedent; a short first output with low risk.
- J Comput Phys: needs new numerics (e.g. a proven FV conormal treatment), not a comparison.
- PLOS Comp Biol: needs a biological or methodological reach; weak fit.

## 5. Reproducibility and automation
- AutoVARP (openCARP/carputils, automated reproducible inducibility testing), https://arxiv.org/pdf/2510.18635 [S]. Single-solver.
- Functional Curation / Cardiac Web Lab (Cooper et al., Front Physiol 2014, tech report), https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2014.00511/pdf [S]. Cell-level, not tissue-level cross-solver.
- Land et al. verification of cardiac mechanics software (https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4707707/ [S]) is the model for a benchmark with specified problems and cross-code results, for mechanics.
- Not found: tooling that automates cross-solver tissue EP comparison with verified variable mappings.

## Judgement [J]

Publishable as a first paper: yes, provided it is framed as a verification and methodology paper, not "three more solvers on the benchmark". The benchmark alone is incremental: TorchCor already covers 0.1/0.2/0.5 mm and de Lima covers FV-vs-FE aligned.

What would be novel, in order of strength:
1. The FV result: hex-vs-tet mesh dependence in an FV code, plus the zeroGradient vs conormal wall finding on an oblique-fibre benchmark variant. No published precedent found.
2. MMS observed convergence orders (TorchCor reports none) for FV and FE on the same manufactured problem, including a rotated-tensor case that exercises the wall condition.
3. Mapping-verification by perturbation runs (stimulus per tissue volume vs per membrane area): a concrete reproducibility contribution and a likely source of the "variability" the field keeps rediscovering.
4. The automated pipeline, as a methods claim.
Resolution 0.1 mm and a third solver are supporting, not novel.

Suggested target: IJNMBE (or Front Physiol), with a CinC abstract as an early outlet. Check one thing before committing: whether the Wulfers-type structured-tet artefact and your hex result are explained by the same mechanism (grid-induced anisotropy), since a reviewer will ask.

Must-cite:
1. Niederer et al. 2011, doi 10.1098/rsta.2011.0139.
2. Pathmanathan & Gray 2014, doi 10.1002/cnm.2615.
3. Pathmanathan et al. 2012, doi 10.1002/cnm.2467.
4. Wulfers, Dossel, Seemann 2016, CinC 43 (link above).
5. Zhou et al., TorchCor, arXiv 2510.12011 / SoftwareX doi 10.1016/j.softx.2026.102521 (the DOI is the researcher's; I could not confirm it). Add de Lima 2025 as the FV-vs-FE precedent.
