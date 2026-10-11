# Bidirectional PVJ coupling: is "both sides implicit" simply an outer loop?

**Date:** 2026-10-06. **Scope:** I only read the source. Nothing was edited or built.
`$S/native-pvj` is at a6f0361d (PR #53 head). I did not touch the owner's tree or
`/Volumes/OpenFOAM-v2412`; I only read `pimpleControl::loop` there.
`S=<scratch>`.
The one numerical check is a lumped toy model of a single step's linear algebra, in
`$S/pvj-outer/toy.py`. It uses no cardiacFOAM code. Its numbers are estimates until the real
solver reproduces them.

**Short answer:** in numerical terms, yes. In code terms, it is more than a loop. The loop
converges in 2 to 3 passes at every R, but only if it iterates today's pass. It does not
converge fast if it iterates the cell-wise "implicit" form; that form is where the review's
1000 re-solves come from. The loop body is about 40 lines. Making the two voltage solves and
the coupler deposit re-entrant adds about 200 more. Section 6 has the owner summary.

---

## 1. The time step today, exactly

Call chain: `electroModel::evolve` → `electrophysicsSystem::advance` →
`staggeredElectrophysicsAdvanceScheme::advance`. With t0 the step start and dt the step:

| # | call | what it does |
|---|---|---|
| 1 | `myocardiumDomain::prepareTimeStep` | Resets `sourceField_` to the external box stimulus at t0 and adds the PDE manufactured source (MMS). Zeroes `implicitSourceCoeff_`. Rotates `IionOldOld_ ← IionOld_ ← Iion_`. Under SBDF2, sets `VmRate_ = (Vm − VmPrev_)/dt0` and `VmPrev_ = Vm`. Runs **once per step**. |
| 2 | `prepareConductionCouplings` → `reactionDiffusionPvjCoupler::prepareSecondaryCoupling` | The base class runs `preProcessCoupling()` when t0 == 0. `evaluateCoupling` gathers the tissue sphere average ⟨V⟩ⁿ (`pvjMapper::gatherVm3DPvjs`, one `reduce` per terminal) and the terminal voltages Vnⁿ. The verifier sets the network MMS source (levels t0, t0+dt). In bidirectional mode it calls `setTerminalTissueVm(⟨V⟩ⁿ)`. (`eikonalMonodomainPvjCoupler` here: `observeTerminalActivations`, which advances `lastObservedTissueActivation_`.) |
| 3 | `advanceConductionDomains` → `conductionSystemDomain::advance` → `monodomain1DSolver::advance` | **Reaction:** `ionicModel::solveODE(t0, dt, Vmⁿ, Iion)` advances the gating state with Vm frozen and returns Iion (reduced across ranks). **Applied current:** the root stimulus at t0. **Diffusion:** one backward-Euler Hines tree solve, written in place over `Vm`, with rhs = Vmⁿ − dt·Iion + dt·Iapp/χCm. At each terminal, diag += dt·g/χCm and rhs += dt·g/χCm·⟨V⟩ⁿ, with g = G/(πρ²L). **Then:** a node's first threshold crossing sets `activationTime` = t0+dt, and `terminalActivationObservations_` is set to −1. |
| 4 | `prepareMyocardiumCouplings` → `preparePrimaryCoupling` | `evaluateCoupling` again. The tissue is unsolved, so I = G(Vn′ − ⟨V⟩ⁿ), which is exactly the network's solved current. The verifier sets the tissue MMS source. `depositPrimaryCoupling`: in bidirectional mode the constructor forces `couplingScheme_ = "explicit"`, so the deposit is `+= w_c·I/V_s` into `sourceField_`. In unidirectional implicit mode it is an `fvm::Sp` coefficient plus a Vn′ source. Finally `setTerminalCoupling` (output buffers). |
| 5a | no bath: `myocardiumDomain::advance` | `setVmRate` (SBDF2) → `solveIonicCurrent` (`solveODE(t0, dt, Vmⁿ, Iion)`) → `clearVmRate` → `updateGradVm` → diffusion → (SBDF2) `refreshIonicCurrent(t0+dt)` → `updateActivationTime`. **Explicit diffusion** (`monodomainSolver::solveDiffusionExplicit`): χCm·ddt(Vm) [+ Sp] = `fvc::laplacian(G, domain.Vm())` − χCm·Iion + source. **Implicit diffusion:** `myocardiumSolver::solveDiffusionImplicit` runs `pimple.loop()` × non-orthogonal correctors × one `fvm::laplacian` assembly. Under SBDF2 (timeIndex ≥ 3) Iion is extrapolated from `IionOld_` and `IionOldOld_`. |
| 5b | bath | `solveReactionStep` (ODE only) → `preparePotentialDomain` → predictor `solveDiffusionStepOnce` → `advancePotentialDomain` (φE) → corrector `solveDiffusionStepOnce` → `finalizeDiffusionStep` (activation only). |
| 6 | ECG | `prepareECGCouplings`, `advanceECGDomains`. |
| 7 | `evolve` after the advance | `postProcess`/`exportStates`; `writeConductionCouplings`, `writeConductionDomains` and `writeECGDomains` (each acts only at output times). Fields and restart state are written in `writeFields`. **Every write is outside the advance.** |

**Operator splitting.** Both sides use Godunov (Lie) splitting with the reaction first.
`solveODE` takes `const scalarField& Vm`: the ionic state advances once, with Vmⁿ frozen,
and the solve that follows treats Iion as a fixed source. The tissue's SBDF2 variant uses an
extrapolated Iion and a VmRate supplied to the ODE, and both are fixed before the solve. The
network has no SBDF2. **Consequence:** after the two reaction steps, the problem for
(Vn′, V′) within the step is **linear**. Everything in sections 4 and 5 relies on this.

**The partitioning today.** The network (the light side) gets a Robin condition: it is
implicit in Vn′ against the given ⟨V⟩ⁿ. The tissue (the heavy side) gets a Neumann condition:
it receives the network's current. This is one Gauss–Seidel pass, network first.

## 2. Existing outer loops, and whether PVJ can join one

| loop | where | what it iterates | can PVJ run inside it? |
|---|---|---|---|
| `bathPredictorCorrector` | `staggeredElectrophysicsAdvanceScheme::advance` | A **fixed two-pass** Vm(φEⁿ) → φE → Vm(φEⁿ⁺¹), with no count and no tolerance. Tissue only. Implicit algorithm only: `solveDiffusionStepOnce` refuses the explicit algorithm. | No. The network has already advanced, and the PVJ deposit stays fixed in `sourceField_` for both passes. It is, though, the precedent for re-solving the tissue diffusion within a step. |
| PIMPLE `nOuterCorrectors` (`pimple.loop()`) | `myocardiumSolver::solveDiffusionImplicit` | For bidomain, the Vm↔φE iteration. For monodomain it re-solves the same linear system. | No. It sits inside the tissue diffusion solver, which holds no reference to couplers or the network. The explicit algorithm never enters it. `pimpleControl::loop` resets `corr_` when it finishes, so calling it again in a later pass is safe. |
| non-orthogonal correctors | `nonOrthogonalCorrectorLoop.H` | Reassembly of one solve | No. |
| `couplingIterations`, any other `nOuterCorrectors` | — | **none exist** (grep of `src/` and `applications/`) | — |

**How is a coupler told it is in a corrector pass?** It is not. `electroDomainCoupler`
exposes only the phase hooks `prepareSecondaryCoupling`, `preparePrimaryCoupling` and
`preparePostPrimaryCoupling(t0, dt)`. They carry no pass index and no `pimpleControl`.
Calling `prepareSecondaryCoupling` again is not neutral: at t0 == 0 it runs
`preProcessCoupling()`, and the eikonal couplers advance their observation state in it. A
loop needs new hooks.

## 3. What must become re-entrant

The loop below iterates the voltage solves only. Both reaction steps stay at one per step.

| state | where it lives | re-entrant today? | change needed |
|---|---|---|---|
| Network ionic state and Iion | `monodomain1DSolver::advance` step 1; `ionicModel::step()` (adaptive ODE step sizes) | No. A second call advances the gating a second time. | Split `advance` into reaction (once), diffusion (per pass) and finish (once). |
| Network tree solve | `monodomain1DSolver::advance` step 3 | No. It overwrites `Vm` in place, and the rhs reads `Vm`. | Keep a copy of Vmⁿ (N scalars) and build the rhs from it. The Hines solve itself is O(N) and cheap. |
| Network activation time | end of `monodomain1DSolver::advance` | No. A crossing seen in a pass that the final pass reverses would stay recorded. | Record it once, after the last pass (it is the "finish" part of the split). |
| Tissue ionic state, Iion, SBDF2 VmRate | `myocardiumDomain::advance` (`setVmRate`, `solveIonicCurrent`, `clearVmRate`) | No (same as the network). | Run once, before the loop. |
| Tissue explicit diffusion | `monodomainSolver::solveDiffusionExplicit`, `bidomainSolver::solveDiffusionExplicit` | **No.** `fvc::laplacian(G, domain.Vm())` reads the current Vm, which is V′ after pass 1. The bidomain explicit φE solve also reads the current Vm. | Use `domain.Vm().oldTime()` in the explicit terms, about 4 lines. Pass 1 should then be bit-identical, because oldTime equals Vm at that point. This needs a byte check. |
| Tissue implicit diffusion | `myocardiumSolver::solveDiffusionImplicit` | Yes. `fvm::ddt` reads `oldTime()` (and `oldOldTime()` for backward), and `pimple.loop()` restarts. | None. Each pass prints another "PIMPLE: iteration" line in the log. |
| SBDF2 refresh | `myocardiumDomain::advance` → `refreshIonicCurrent(t0+dt)` | No. It overwrites `Iion_`, and the diffusion reads that before timeIndex 3. | Run it once, after the last pass. |
| SBDF2 history (`IionOld_`, `IionOldOld_`, `VmPrev_`, `VmRate_`) | `myocardiumDomain::prepareTimeStep` | Yes (it rotates once per step, outside the loop). | None. |
| Tissue activation time, `gradVm_` | `updateActivationTime`, `updateGradVm` | Same problem as the network activation time. | Once, after the last pass. |
| Coupler's deposited source | `pvjMapper::depositCoupling` (`+=` into `sourceField_`) | No. It accumulates, and `prepareTimeStep` resets the field only once per step. | Keep the last deposited current and deposit −I_prev + I_new each pass. Do not snapshot and restore the field: two couplers depositing into overlapping spheres would erase each other. |
| Coupler buffers and output | `terminalCurrentBuffer_`, `setTerminalCoupling` | Yes (the last pass wins). | None. The `write()` override that recomputes the received current becomes unnecessary in iterated mode. |
| MMS sources | the verifier's `updateManufacturedSource` → `ionicModel::setManufacturedSourceTerm`, consumed inside `solveODE` | Idempotent, and consumed in the reaction step, which runs once. | Set it before the reaction steps, at the converged levels (both t0+dt, sphere-average form). About 5 lines in the coupler's arguments. |
| Restitution and eikonal 1D networks | `restitutionEikonalSolver1D::advance` (`nextTact_`, `lastActTime_`, `blockCount_`, imported observations) | **No.** It commits events and counters. | **Leave them out of the loop.** They have no algebraic junction: `eikonalMonodomainPvjCoupler` prescribes a template voltage, so its implicit form is already exact on both sides, and its bidirectional mode is event-based. The loop must iterate only the cable domains behind an iterated coupler, which needs a flag on the coupler. |
| Writes, VTK, .dat rows, restart fields | `evolve` after the advance | Yes (outside the advance). | None. |
| Parallel | `gatherVm3DPvjs` does one `reduce` per terminal per gather | Yes, but every pass adds nT allreduces (about 900 or more on electroHeart). | Batch the reduction into one list reduce, about 10 lines, independent of the loop. The residual needs one `gMax`. |
| Bath branch (5b) | the advance scheme | — | Smallest version: iterate around the corrector `solveDiffusionStepOnce` only, about 10 lines. Alternatively, leave it out. |

**Latent finding, separate from the loop:** the split API that the bath path uses
(`solveReactionStep`, `finalizeDiffusionStep`) leaves out `setVmRate`/`clearVmRate` and
`refreshIonicCurrent`. So bath with SBDF2 silently loses both. No shipped tutorial combines
them. The PVJ loop must not reuse that API as it stands, or it inherits the gap.

## 4. The scheme at convergence, the criterion, and the cost

### Two ways to iterate, with different fixed points and different speeds

Lumped junction notation, as in the review: C_n = χCm·πρ²L (the network node);
C_t,eff = χCm·V_s²/Σw²V (the sphere mode); a = dt/(R·C_n); b = dt/(R·C_t,eff);
d = dt·G_edge/C_n (the tree's one-step stiffness at the terminal); x̂ is the junction tissue
voltage the network is given.

| iteration | per pass | fixed point | contraction per pass |
|---|---|---|---|
| **(N) Iterate today's pass:** Robin network, Neumann tissue | network implicit against x̂; tissue receives G(Vn′ − x̂)·w_c/V_s; then x̂ ← ⟨V′⟩ | network implicit against ⟨V′⟩; tissue receives G(Vn′ − ⟨V′⟩), spread by the kernel. This is Vergara's γ_j/A_r at the new level. | λ ≈ b(1+d)/(1+a+d) ≤ min(b, (C_n + dt·G_edge)/C_t,eff) |
| (C) The cell-wise "implicit" pairing (the review's option C) | network against x̂; tissue `fvm::Sp` against Vn′ cell by cell | as (N) in total current, but each cell takes G·w_c(Vn′ − V_c′)/V_s, which adds an intra-sphere smoothing term | ab/((1+a)(1+b)) → b/(1+b) as R → 0 |

The toy model (`$S/pvj-outer/toy.py`) measures the contraction by power iteration on the
homogeneous error equation. It uses a 60-cell tissue chain, a sphere of 8 cells and a 30-node
cable network. ρ = 14.3 µm, dt = 5e-5 s, χCm = 1400 F/m³, σ_p = 1 S/m, and the terminal is a
leaf. C_t,eff/C_n = 2122 and d = 4.6.

| R [Ω] | (N), explicit tissue | (N), implicit tissue | (C) cell-wise |
|---|---|---|---|
| 1 | 1.5e-3 | 1.5e-3 | **0.998** |
| 10 | 1.5e-3 | 1.5e-3 | **0.977** |
| 100 | 1.5e-3 | 1.5e-3 | 0.81 |
| 1e4 | 1.4e-3 | 1.4e-3 | 0.039 |
| 3e5 | 7.2e-4 | 7.2e-4 | 6.7e-4 |
| 1e7 | 4.1e-5 | 4.1e-5 | 1.1e-6 |

Column (C) reproduces the review's 0.998 and 0.978. Those are its "≈10 000 and ≈1 000
iterations", and they belong to the cell-wise ordering. **Iterating the pass the code already
makes contracts about a thousand times per pass at every R.** The reason is physical: through
the junction, the tissue sees only the capacitance the network can supply in one step,
C_n + dt·G_edge, which is about 1/400 of the sphere.

Properties of (N):

- **Pass 1 is today's scheme.** With the loop switched off or converged after one pass,
  results stay byte-identical.
- **Charge is conserved at every pass,** not only at convergence: the tissue always receives
  exactly the current the network solved. Stopping early, including at an iteration cap,
  leaves part of the one-step lag but never breaks conservation.
- **It converges to the literature model.** At the fixed point both sides are implicit in the
  same junction current, so the junction mode is A-stable with no bound in R.
- **Where it fails.** (N) diverges when (C_n + dt·G_edge) is comparable to C_t,eff at strong
  coupling. On the slab that means thick fibres: λ = 0.29 at ρ = 0.2 mm, 3.1 at ρ = 0.65 mm
  and 27 at ρ = 2 mm (R = 1 Ω). This is the same region where today's single pass is unstable
  (the review's b < 2 + a). It does not occur at physiological ρ.
- **The MMS case.** The `monodomain1D3D` bidirectional MMS (unit cross-section, χCm = 6)
  sits in the weak-coupling regime, where λ ≤ b and b falls as dt ∝ h². Measure it before
  relying on that.

### The convergence criterion

The residual is the mismatch between the current the tissue received and the current at the
new level: G_j·|⟨V′⟩_j − x̂_j|. Expressed as a voltage, the criterion is
r = max_j |⟨V′⟩_j − x̂_j| ≤ tol, which is one `gMax`.

- The network terminal's error is about r. The tissue's error is about λ·r.
- Passes ≈ 1 + ⌈log(r₁/tol)/log(1/λ)⌉, where r₁ is the junction's voltage change over one
  step.
- During a junction upstroke (r₁ around 10 mV, tol = 1 µV), that is 3 passes. On a plateau
  it is 2. At rest, where r₁ < tol, it is 1, and the residual check after pass 1 ends the
  loop.

### The cost

The ionic ODEs are not repeated, and with RKF45 they are the dominant cost. One extra pass
costs:

- one tissue diffusion solve: one explicit assembly, or one linear solve with its PIMPLE and
  non-orthogonal correctors;
- one O(N) Hines solve;
- one gather, which costs nT reductions until it is batched.

Expected overhead: zero at rest, and one or two extra diffusion solves per step while any
junction is active. For an explicit tissue this is small next to the ODE. For an implicit
tissue it is up to about 2× the diffusion cost. I have not measured this.

### Under-relaxation, Aitken, Schur or monolithic

- **Under-relaxation or global Aitken** is not needed for (N) at physiological ρ, where λ is
  about 1e-3. A single global Aitken ω (Küttler–Wall) is also a poor fit, because junctions
  differ in R and in sphere.
- **A per-junction secant** is about 10 lines in the coupler and makes the loop
  unconditional, covering thick fibres. After two passes, λ̂_j = −Δx_j/Δx̂_j, then
  x̂_j ← x̂_j + (x_j − x̂_j)/(1 + λ̂_j). The map within a step is linear and each junction is
  nearly decoupled, so this is exact for an isolated junction. It is the data-driven form of
  the 1×1 per-junction Schur correction, and it needs nothing from the tissue's
  discretisation. Recommended as part of the loop, or as the first addition if the owner
  wants thick fibres covered.
- **A 1×1 Schur from model quantities, or a monolithic diagonal block** at the junction
  cells: with an explicit tissue and spheres that do not overlap, eliminating the sphere
  cells into the network's terminal row is exact in one pass, and the matrix stays a tree.
  The cost of that:
  - It needs the tissue's explicit predictor and its ddt diagonal at the junction cells before
    the network solve. That means reordering the scheme (tissue reaction before network
    diffusion) and letting the coupler read the tissue's discretisation (ddt scheme
    coefficient, explicit flux).
  - Overlapping spheres (electroHeart) couple terminals, so the matrix is no longer a tree.
  - With an implicit tissue the Laplacian makes the elimination non-local, so it has to
    iterate anyway.

  Not simpler than (N).

## 5. Verdict

**Is it almost an outer loop?** Numerically, yes, with one condition: the loop must iterate
today's pass, (N). Iterating the cell-wise form, (C), is what produces the 1000 re-solves. In
code it is not "almost": the loop is the smallest part. Both voltage solves overwrite their
start-of-step state, the coupler accumulates into the tissue source, and the reaction,
activation and SBDF2 updates sit inside the `advance()` calls that the loop would repeat.

**What it buys.** Not stability, and not conservation: today's pass already conserves charge
and is stable from 1 Ω to 1e7 Ω at physiological ρ. It removes the one-step lag in the
network's view of the tissue. At physiological R (a ≈ 1.5) that lag is not negligible for the
network terminal. The coupled scheme still stays first order in time, because of Godunov
splitting and backward Euler on the network. Landajuela 2018 found one pass and the iterated
scheme indistinguishable. Converging the loop makes "both sides implicit, same current" true;
it should not be expected to move results much.

**Files and lines** (estimates; the loop body is about 40 lines and the rest is re-entrance):

| file | change | lines |
|---|---|---|
| `core/advanceSchemes/staggered/staggeredElectrophysicsAdvanceScheme.C` | the loop in branch 5a (plus about 10 for branch 5b's corrector) | +35–45 |
| `core/system/electrophysicsSystem.{H,C}` | `hasIteratedCouplings`, per-pass correct calls for couplers and domains, residual, finish | +40 |
| `electroCouplers/electroDomainCoupler.H` | `iteratesWithPrimary()`, `correctSecondaryCoupling()` (sets x̂, returns r), `correctPrimaryCoupling()` (re-deposit) | +20 |
| `electroCouplers/pvjCoupler/reactionDiffusion/reactionDiffusionPvjCoupler.{H,C}` | keys; undo/redo deposit; residual; secant; MMS levels; remove the forced `"explicit"` line | +50–60 |
| `electroCouplers/pvjCoupler/pvjMapper.C` | batch the per-terminal reduce (optional) | +10 |
| `electroDomains/conductionSystemDomain/{conductionSystemDomain,conductionSystemSolver}.{H,C}`, `core/electroDomainInterface.H` | reaction / diffusion / finish interface for the network | +30 |
| `conductionSystemModels/monodomain1DSolver/monodomain1DSolver.{H,C}` | the split, and the Vmⁿ copy (mostly moved code) | ~60 moved, +20 |
| `electroDomains/myocardiumDomain/{myocardiumDomain,myocardiumDomainInterface}.{H,C}` | reaction (with VmRate) / re-solve / finish (refresh, activation), without touching the bath split API | +30 |
| `myocardiumModels/{monodomainSolver,bidomainSolver}/*.C` | `Vm().oldTime()` in the explicit terms | ~4 |
| `verificationModels/coupledVerification/coupled1D3DMonodomainVerifier.C` | probably none (levels come from the coupler); check the implicit branch | 0–10 |
| docs: `electroModels/ARCHITECTURE.md`, `electroCouplers/README.md` | the new meaning of `pvjCouplingScheme` under bidirectional | +20 |

That is about 250 to 300 lines across about 15 files. One key, `pvjCouplingTolerance`, plus
an iteration cap if the owner wants one.

**Risk to existing regressions.** It is low if pass 1 stays byte-identical and the loop runs
only for `bidirectional` with `pvjCouplingScheme implicit`. Default `explicit` behaves as
today.

- No shipped regression runs the bidirectional cable. The `antegrade` and `retrograde`
  variants of `purkinjeRestitution2D` are eikonalMonodomain on a restitution network, which
  the loop does not touch. Its `monodomain` variant, `electroHeart` and `conductionBlock` are
  unidirectional.
- Three refactors could break byte identity and must each pass a byte-identity probe like the
  ones in Phases 1–5: the explicit Laplacian on `oldTime()`, the `monodomain1DSolver` split,
  and the `myocardiumDomain` split (operation order: VmRate, ODE, clear, gradVm, diffusion,
  refresh, activation).
- Only the `monodomain1D3D` bidirectional MMS with `implicit` changes, through the new levels.
  No native reference file holds those numbers. Expect the order of convergence to stay at 2.

**The smallest correct version:**

1. `pvjCouplingScheme implicit` together with `couplingMode bidirectional` means: iterate (N)
   to `pvjCouplingTolerance` (in V). Delete the constructor line that forces `"explicit"`.
   `explicit` stays one pass. This restores the key's meaning, which answers review question 1
   in the owner's terms.
2. Advance-scheme branch 5a:
   1. `prepareTimeStep` and the secondary phase.
   2. The reaction step of every iterated cable network; every other domain advances as today.
   3. The network diffusion pass, the primary deposit, the tissue reaction step, and the
      tissue diffusion pass.
   4. Loop while r > tol: set x̂ = ⟨V′⟩, re-solve the network from Vmⁿ, re-deposit
      (−I_prev + I_new), re-solve the tissue diffusion.
   5. Finish: network activation; SBDF2 refresh and tissue activation.
3. Make the re-entrance changes in the table in section 3, and nothing else.
4. Per-junction secant from the third pass on: about 10 lines, which makes thick fibres
   converge too. Leave the bath branch at one pass, or loop its corrector only.

**Evidence the implementation should show:**

1. With `explicit`, and with `implicit` stopped at one pass, outputs are byte-identical to
   a6f0361d. This covers the unidirectional runs, the eikonal coupler and the bidirectional
   cable.
2. Passes per step against R (1, 10, 1e4, 3e5, 1e6 Ω): 1 to 3, flat in R. Plain (N) at
   ρ = 0.65 mm against (N) with the secant: the plain version diverges and the secant version
   converges.
3. The ledger: round-off agreement at every pass, the first included.
4. The converged residual G·|⟨V′⟩ − x̂| ≤ G·tol.
5. Retrograde node-4 and antegrade activation times, one pass against converged, and against
   halving dt. Expect at most about one step of difference.
6. MMS rates of 2 for the bidirectional implicit sweep.
7. Wall time per step for the explicit and the implicit tissue.

## 6. For the owner (half a page)

Within one time step the problem is linear: both ionic models are advanced once, before the
voltage solves (Godunov splitting). So an outer loop around the two voltage solves is an
ordinary fixed-point iteration. Whether it is cheap depends on what you iterate.

- **Iterate today's pass and it converges fast.** Today's pass solves the network implicitly
  against the tissue's junction average, then gives the tissue exactly that current. Iterating
  it converges to the scheme you want: both sides implicit in the same junction current
  (Vergara's model at the new time level).
  - Each pass reduces the error about a thousandfold at every resistance, because through the
    junction the tissue sees only the capacitance the network can supply in one step.
  - Pass 1 is today's scheme.
  - Every pass conserves charge, so even a capped loop stays conservative.
  - Expect 1 pass at rest and 2 to 3 while a junction is depolarising.
- **Iterate the cell-wise "implicit" form and it is slow.** That form puts the tissue on the
  matrix diagonal, cell by cell, and it is what the review measured at about 1000 re-solves at
  10 Ω.

In code it is more than a loop. There is no existing outer loop the junction can join. The
bath predictor–corrector is a fixed two passes, and PIMPLE's outer correctors live inside the
tissue's implicit diffusion solve and know nothing about the network. Couplers are never told
they are in a corrector pass.

- The loop itself is about 40 lines in `staggeredElectrophysicsAdvanceScheme`.
- To make it correct, about 200 more lines across about 15 files:
  - Split the cable network's and the tissue's `advance()` into reaction (once), voltage solve
    (repeatable) and finish (activation times and the SBDF2 refresh, once).
  - The network re-solves from a saved start-of-step voltage.
  - The explicit tissue's Laplacian reads `Vm.oldTime()`.
  - The coupler replaces its deposit rather than adding to it.
- The restitution and eikonal networks stay outside the loop. They exchange events, not a
  current, and their state is not repeatable.
- A per-junction secant (about 10 lines) makes the loop converge for thick fibres too. That is
  the one regime where the plain loop, and today's single pass, both go unstable.

**Recommendation.** It is worth doing as the meaning of `pvjCouplingScheme implicit` under
`bidirectional`, with `explicit` staying one pass.

- If pass 1 is kept byte-identical and the loop runs only in that mode, the risk to existing
  regressions is low: none of them runs the bidirectional cable.
- It should not be expected to change results much. Today's pass is already conservative and
  stable. Its remaining error is a one-step lag in what the network sees of the tissue, and
  the scheme stays first order in time either way (Landajuela 2018 found one pass and the
  iterated scheme indistinguishable).
- These are estimates from reading the code and a lumped model. The convergence rate and
  the cost need measuring on the real solver.

**Separate finding:** the reaction/diffusion split that the bath path uses drops the SBDF2
VmRate and the Iion refresh, so bath with SBDF2 silently differs from `advance()`.
