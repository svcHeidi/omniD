# Extracellular potential from a monodomain run: notes for a later session

Status: notes, not a design. Nothing here is implemented or run. Items marked
**to check** are unverified.

## The three ways to get an ECG from cardiac tissue

All three compute the extracellular potential φe at electrodes from the
transmembrane potential Vm. They differ in what they assume about the medium
around the heart.

| | medium | what is solved | feeds back into Vm? |
|---|---|---|---|
| **pseudo-ECG** | infinite, uniform conductivity σb | nothing: a direct integral φe(xe) = 1/(4πσb) ∫ σi∇Vm·∇(1/r) dV | no |
| **φe recovery / lead field** (augmented monodomain, Bishop & Plank 2011) | a bounded heart + bath/torso, with a surface and a ground | one elliptic solve per output time, or one per electrode (lead field) | no |
| **bath bidomain** | the same bounded heart + bath | the coupled bidomain system at every step | yes |

**Pseudo-ECG and lead field are the same formula.** Both are ∫ σi∇Vm·∇Z dV.
- For the pseudo-ECG, Z = 1/(4πσb r), the free-space Green's function, known in closed form.
- For the lead field, Z is the potential from a unit current injected at the electrode into the actual bounded torso, solved numerically once per electrode (reciprocity).
- Recovery solves for φe everywhere and samples it at the electrodes. By reciprocity it gives the lead field's values at the electrodes, up to discretisation.

**Defining a surface is what turns the pseudo-ECG into a recovery problem.** The surface needs:
1. an outer surface with σ∇φe·n = 0 (insulated body);
2. a reference, either a ground electrode (Dirichlet) or zero mean, because with only Neumann conditions φe is fixed only up to a constant;
3. a bath or torso conductivity on a mesh between the heart and that surface;
4. heart–bath interface conditions: continuity of φe and of normal current.

The pseudo-ECG is the limit where the surface goes to infinity and the medium is
uniform, including σe inside the heart equal to σb.

## What exists today

**cardiacFOAM** (native main, read 2026-10-10):
- `pseudoECG` (`pseudoECGSolver`): free-space form, verified by `manufacturedPseudoECGVerifier` against a Gauss–Legendre quadrature reference.
- `torsoECG`: samples the global `phiE` of a heart+bath solve at electrodes. It needs the full bath-bidomain run.
- A bath-bidomain solver with a manufactured case: `tutorials/manufacturedSolutions/bathBidomain`, `manufacturedFDABathBidomainVerifier`, Pathmanathan & Gray 2014 bath problem, variant `groundElectrode`. Mesh [-1,2] with the myocardium at [0,1]; hex and tet variants.
- **Missing:** recovery of φe from a *monodomain* Vm, i.e. one elliptic solve over heart+bath with no feedback. That is what openCARP (pseudo-bidomain `phie` recovery) and TorchCor (`Monodomain.phie_recovery`, `ecg/leadfield.py` `LeadField`) do.

**openCARP**: `phie_rec_ptf` is the free-space form, not recovery (`recover_phie_std`). Pseudo-bidomain is a separate mode (**to check**: its parameter name and whether its φe is a recovery solve).

**TorchCor**: tissue is monodomain only. φe comes from K_ie φe = −K_i Vm (`phie_recovery`) or from torso lead fields (`LeadField`, ground = right-leg node). Bidomain conductivities enter only this post-processing step.

## Implementing recovery in cardiacFOAM

Recovery is the bidomain's elliptic equation with Vm given:

- heart: ∇·((σi+σe)∇φe) = −∇·(σi∇Vm)
- bath: ∇·(σb∇φe) = 0
- interface: φe continuous, normal current continuous
- outer surface: σb∇φe·n = 0, plus a ground

cardiacFOAM already assembles this equation inside its bath-bidomain solver (the `bathPotentialDomain` block in `bidomainSolverCoeffs`). The likely shape:
- a new `ecgModels` entry, e.g. `recoveredECG`, that takes the monodomain Vm;
- it reuses the bath-bidomain elliptic assembly once per output time;
- it samples like `torsoECG`.

**To check:**
- whether that assembly can be called without the parabolic half;
- how Vm on the heart mesh maps onto the heart cellZone of the heart+bath mesh (same mesh with zones, as in the bath tutorial, avoids interpolation).

Per the owner's rule that the C++ holds physics only, the C++ gets the solve and nothing else; checks live in omniD.

**Integration in omniD:**
- a catalogue entry for the new ECG model's keys, from the C++ key scanner;
- a verifier problem file like `fda_monodomain.toml`.

**Cost compared with the pseudo-ECG:**
- one linear solve over heart+bath per output, against an integral;
- for a few electrodes and many outputs, the lead field is cheaper: one solve per electrode, then a dot product per output.

## A manufactured solution for recovery

**Preferred: reuse the FDA bath-bidomain solution.**
- The bath-bidomain manufactured (Vm, φe) satisfies the elliptic equation at every instant.
- So, given Vm = exact Vm at time t, recovery must return φe = exact φe. No new mathematics is needed.

**To check:** does the FDA bath problem add a source to the elliptic equation? If it does, the recovery test needs the same source injected.
- The reference header (`manufacturedFDABathBidomainReference.H`) gives φe piecewise: linear in each bath, which satisfies Laplace there with no source, and −k√(1+t)cos(πx) + αx/σe + C in the heart.
- The heart part must be checked against the heart equation with the matching V = √(1+t)F − αx/σe.

The test can be run in two steps:
1. **Exact Vm in, recovery alone.** Spatial order of the elliptic solve; isolates recovery from the tissue solver.
2. **Solver's own monodomain Vm in.** Order of the whole chain.

The same exact φe sampled at electrodes on the outer bath surface verifies:
- `torsoECG` (bidomain);
- recovery (monodomain);
- the lead field (reciprocity).

**Simpler first test, with no bath and no source:**
- Take equal anisotropy ratios (σe = λσi) and a heart-only domain with insulated walls.
- Then φe = −Vm/(1+λ) + const solves the recovery equation exactly.
- A ground, or zero mean, fixes the constant.
- This is a one-line check that recovery's discretisation and gauge are right before the bath is added.

**Cross-solver:**
- TorchCor's `phie_recovery` and `LeadField`, and openCARP's pseudo-bidomain (**to check**), could all be verified on the FDA bath geometry with the same exact φe.
- Requirement: each solver must accept the [-1,2] three-zone mesh and its ground.
- TorchCor's ground is a node (Dirichlet), so the ground location must match the `groundElectrode` variant's.

## How much harder than the pseudo-ECG

- **Mesh:** the bath must be meshed, with conforming heart–bath interfaces. The pseudo-ECG needs only the heart.
- **Solver:** a linear solve per output, or per electrode, with a pure-Neumann gauge to handle. The pseudo-ECG is a sum.
- **Reference:**
  - pseudo-ECG: a quadrature integral, for any geometry;
  - recovery: an exact solution only for chosen geometries (the FDA slab, concentric spheres); otherwise a fine-mesh reference solution.
- **Physical meaning:** recovery sees the torso shape and the conductivity jumps. The pseudo-ECG does not. Recovery is closer to a measured ECG.
