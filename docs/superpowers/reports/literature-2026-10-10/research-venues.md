# Publication venues for omniD (research, 2026-10-10)

Facts below come from the cited pages (via search/fetch summaries). Judgement is marked as such. Gaps: I could not retrieve SoftwareX's guide (403), PLOS Comp Biol's Software word limit, review times, or Frontiers/J Comput Sci/Nature Comp Sci/Patterns/Digital Discovery details beyond scope lines; check these before submitting.

## 1. Tool / software venues (verified facts)

**JOSS** (https://joss.readthedocs.io/en/latest/submitting.html, https://joss.readthedocs.io/en/latest/review_criteria.html)
- Needs an OSI-approved licence with an actual LICENSE file in the repo (a README mention is not enough).
- Repository must have been public more than six months, with evidence of sustained development, releases, issues and PRs; short bursts of commits near submission get desk-rejected.
- "Substantial scholarly effort" is judged on design decisions and sustained work. The paper must have a "Research impact statement" with concrete evidence (publications using the software, adoption, or benchmark results/reproducible materials for credible near-term significance).
- Papers must not focus on new research results obtained with the software. Short `paper.md`; review is iterative and conversational (authors respond within two weeks, changes in 4-6 weeks). A preprint is not prior publication. AI use must be disclosed and humans must assert they made core design decisions.
- Co-publication is explicitly allowed: disclose related papers (published, in review, forthcoming).

**SoftwareX** (https://www.sciencedirect.com/journal/softwarex/publish/guide-for-authors; terms via search summary): short paper (3000 words) plus software distribution. OSI licence from an approved list (Apache-2.0, BSD-3, GPL, LGPL, MIT, MPL-2.0, etc.); GitHub repo only, with README and Licence.txt, otherwise returned.

**PLOS Computational Biology** (https://journals.plos.org/ploscompbiol/s/materials-software-and-code-sharing): Software articles must conform to the Open Source Definition, be deposited in an open archive and linked from the manuscript. Articles should describe software of "exceptional importance" giving biological insight. PLOS welcomes preprints (https://plos.org/?p=4168).

**Computer Physics Communications** (https://www.elsevier.com/journals/computer-physics-communications/0010-4655/guide-for-authors): Computer Programs in Physics papers need an approved open licence (MIT, Apache-2.0, BSD, GPL, LGPL, MPL-2.0, CeCILL, CC0, etc.), with the code archived in the Mendeley Data program library.

**Journal of Computational Science**: scope explicitly includes "software developed to solve" science and medicine problems and multi-scale simulation (https://peeref.com/journals/9509). I found no software-specific licence rule.

**Frontiers (Physiology, Computational Physiology & Medicine)**: "Technology and Code" article type, up to 12,000 words, fee-bearing; software must be novel, documented, and in a repository with a DOI/URI (https://www.frontiersin.org/for-authors/where-to-publish/article-types; section scope: https://www.frontiersin.org/journals/physiology/sections/computational-physiology-and-medicine/about).

**Computing in Cardiology**: 4-page papers, must be presented at the meeting; preprint collection available (https://cinc.org/?p=1736). Precedent for cross-solver benchmarking there: "Benchmarking Open Cardiac Electrophysiology Simulators: MonoAlg3D and OpenCARP" (https://cinc.org/2025/Program/accepted/376.html).

## 2. Agent-evaluation venues

- **NeurIPS Evaluations & Datasets track** (formerly Datasets & Benchmarks; https://neurips.cc/Conferences/2026/CallForEvaluationsDatasets): evaluation is itself an object of study; proposals of new evaluation protocols are in scope. Code and data must be hosted and accessible to reviewers at submission; default double-blind (so a private repo cannot be submitted). 2026 deadlines were in May, so the next cycle is a 2027 call (not yet checked).
- **TMLR** (https://www.jmlr.org/tmlr/editorial-policies.html): accepts applications of existing techniques and empirical studies; rolling submission.
- **Digital Discovery (RSC)** (https://www.rsc.org/publishing/journals/digital-discovery): AI/automation tools for science, chemistry/materials-focused; **Patterns** publishes software and data-science papers (secondary source, https://ou-publier.cirad.fr/en/api/notice-revue/docx?nids=5962). I did not verify that domain-science agent evaluations in cardiac simulation fit; Nature Computational Science was not checked.
- Neighbouring prior art, all arXiv preprints: Foam-Agent/CFDLLMBench (https://arxiv.org/pdf/2505.04997), OpenFOAMGPT (https://arxiv.org/pdf/2501.06327), FermiLink (https://arxiv.org/pdf/2604.03460), SciAgentGym (https://arxiv.org/html/2602.12984v1). So CFD/simulation agent evaluation is an established, crowded niche; novelty must come from the with/without-tool contrast and the deterministic-interface claim.

## 3. Ordering and dual publication (verified)
- Elsevier does not treat a preprint as prior publication (https://www.elsevier.com/connect/clarification-of-our-policy-on-prior-publication); JOSS and PLOS likewise.
- Two papers from one project are legitimate when each answers a distinct question, adds a new contribution, and is disclosed to editors (COPE-style guidance summarised at https://casrai.org/guides/salami-slicing-redundant-publication).
- JOSS explicitly accepts disclosed companion papers. NeurIPS E&D requires public code at submission, so an evaluation paper there cannot precede open-sourcing.

## 4. Licence
Every software venue above wants an OSI licence, and JOSS and NeurIPS E&D additionally want the repo public (JOSS: six months of history). omniD has no LICENSE and a private repo, so all software-paper routes need a licence decision first. CLAUDE.md says do not add one without asking; this is the owner's decision. Dependencies matter: cardiacFOAM and OpenFOAM are GPL, which constrains choices (judgement).

## 5. Comparable splits
- svZeroDSolver: JOSS software paper (https://joss.theoj.org/papers/10.21105/joss.07595) alongside the method paper on automated 0D/1D model generation (https://arxiv.org/pdf/2111.04878). I did not verify that the second paper is the designated companion.
- openCARP: environment paper in Computer Methods and Programs in Biomedicine (https://pubmed.ncbi.nlm.nih.gov/34171774/), CDE/sustainability paper separately (https://arxiv.org/pdf/2201.04434), CinC conference paper (https://www.cinc.org/2020/Program/accepted/111.html).
- TorchCor: arXiv paper verified against the N-version benchmark (https://arxiv.org/pdf/2510.12011).
- I found no verified case of an agent-tool paper split into software plus with/without evaluation in computational physiology.

## Answers (judgement)
(a) Yes, two papers is defensible: the contributions differ in kind (a software/verification contribution vs a measurement of agent behaviour).
(c) Publishing the evaluation first as an arXiv preprint is fine by every policy above. A journal or NeurIPS paper of the evaluation first is awkward: the tool must be public and licensed for reviewers to inspect, and the results would be about an unreleased artefact.
(d) Yes, both can be journal/conference papers, but the evaluation is the riskier one; the novelty bar is higher in a crowded area.

## Recommended split (judgement)
**Order:** decide licence, open the repo; post the evaluation as an arXiv preprint when ready; write the tool paper first and submit it while the repo accumulates history.

**Paper 1, the tool paper (Computer Physics Communications or SoftwareX; JOSS only after six months of public history and with an impact statement).** Content: architecture and the plugin contract, the conformance suite C1-C14 as the generality argument, provenance and pre-run validation, and the Niederer cross-solver comparison across cardiacFOAM, openCARP and TorchCor as a verification demonstration. Add reproducible instructions and a licence. JOSS excludes new research results, so keep the benchmark as a demonstration of the tool, not a finding; for Frontiers Technology & Code or CPC the comparison can be fuller. The cross-solver result may also stand alone as a CinC paper, since solver comparisons are normal there.

**Paper 2, the agent evaluation (arXiv first; then NeurIPS E&D 2027 cycle, TMLR or Digital Discovery).** Minimum content: pre-registered task set, with-vs-without-omniD arms, several models, repeated runs with variance, outcome metrics (task success, correct physics, provenance completeness, cost), failure taxonomy, harness and tasks released. Position against Foam-Agent and CFDLLMBench. It must cite paper 1 and disclose it to editors.

**What keeps them distinct:** paper 1 reports what the tool is and that it is correct; paper 2 reports how agent behaviour changes with it. Do not repeat the Niederer comparison as a result in paper 2.
