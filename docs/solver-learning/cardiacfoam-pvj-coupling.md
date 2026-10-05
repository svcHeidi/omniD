# cardiacFOAM's Purkinje-myocardium (PVJ) coupling: what native main did, measured

**Method:** [`method.md`](method.md). **State described:** native main `0b1bf13c`
(the installed `cardiacFoam` and `libelectroModels` were built from this source),
before the fixes in progress on cardiacFOAM PR #53's branch. **Date:** 2026-10-05.
The catalogue describes the intended semantics; this file records the behaviour
the fixes remove and the numbers they are tested against. Keys and units are in
[`cardiacfoam-conduction-graph.md`](cardiacfoam-conduction-graph.md).

The probe case is `electrophysiologyProtocols/purkinjeRestitution2D`, `monodomain`
variant: a 150 x 150 x 1 slab (h = 0.333 mm, 0.1 mm thick), Bueno-Orovio tissue and
network with `chi*Cm` = 1400 F/m³ on both sides, `rPvj 10000`, `pvjRadius 0.6 mm`,
`pvjKernel linear`, `pvjCouplingScheme implicit`, tissue `solutionAlgorithm explicit`,
`ddtSchemes backward`, dt = 5e-5 s, shortened to one beat. Three junctions sit on
cell corners: 12 cells within the radius, largest kernel weight 0.607, kernel-weighted
volume V_s = 3.78e-11 m³.

## Conservation: the network does not feel the tissue

The tissue side of `reactionDiffusionPvjCoupler` takes the junction current as A:
`pvjMapper` divides it by the kernel-weighted volume and deposits it in
`externalStimulusCurrent` (A/m³), so the tissue gains exactly `I`. The network side
subtracts the same number from the node's applied current, which the cable update
divides by `chi*Cm` as A/m³, with no cross-section or control length: an implied node
volume of 1 m³.

| run | change | result |
|---|---|---|
| bidirectional | `couplingMode bidirectional` | every network node's Vm equals the unidirectional run's to the 9 digits of the output (largest difference 0.0) |
| retrograde | bidirectional, root intensity 0, a 4 x 4 mm tissue stimulus on one junction at 5 ms | junction current down to -1.06e-5 A; the network stays at -0.084 V, 0 of 377 nodes activate; the network moves about 1e-12 V, matching the code's own term to 0.05-0.5 % |
| small R | the same with `rPvj` 10 and 1e-6, implicit tissue | the junction sphere is clamped at rest; the network still does not move |
| scaled network | `cm`, `purkinjeConductivity` and root intensity multiplied by a node volume of 8.0e-14 m³, which gives the conservative term; equal to the stock run when unidirectional to 7e-18 V | with `rPvj` 3e5 and 1e6 Ω terminal 4 fires at 6.4 and 6.6 ms and 250 of 377 nodes activate; at 1e5 Ω the explicit network term diverges at 4.1 ms; at 1e7 Ω nothing activates |

The manufactured solution passes either way: `coupled1D3DMonodomainVerifier`
builds the network's source with the same expression as `assembleAppliedCurrent`
(`exactSecondaryAppliedCurrent_[terminalNodes[i]] -= exactCurrent[i]`), so it checks
that the code solves its own equations, not that they conserve charge. The graph
error is 7.0e-6 to 7.1e-6 unidirectional, bidirectional and bidirectional-implicit.

## Explicit and implicit

Tissue update per combination, with `n` the old and `n+1` the new level, `G = 1/R`,
`w` the kernel weight, `<V>` the weighted mean of the tissue Vm over the junction's
cells, `K` the finite-volume Laplacian and `D_t` the `ddtSchemes` operator:

| `solutionAlgorithm` | `pvjCouplingScheme` | tissue equation in a junction cell |
|---|---|---|
| explicit | explicit | `chi*Cm D_t V = K V^n - chi*Cm Iion + S + w G (Vn^{n+1} - <V^n>)/V_s` |
| explicit | implicit | the same with `<V^n>` replaced by the cell's own `V^n`: the coefficient multiplies the old Vm on the right-hand side |
| implicit | explicit | `K V^{n+1}` and an Iion at the extrapolated level; the junction term as in the first row |
| implicit | implicit | `chi*Cm D_t V + w G V^{n+1}/V_s = K V^{n+1} - chi*Cm Iion + S + w G Vn^{n+1}/V_s`: the coefficient is on the diagonal |

`solutionAlgorithm` is read as `explicit` or else implicit: `Explicit` or a typo ran
the implicit path without a message. `eikonalMonodomainPvjCoupler` never reads
`pvjCouplingScheme`. The network advances first with the tissue at level `n`, the
tissue second with the network at `n+1`; the tissue's ionic current is always lagged,
and the network's junction term is always lagged.

The explicit tissue path's time-step cap (`suggestExplicitDeltaT`) counts diffusion
only, not the junction term.

### Stability bound

An explicit junction term gives a decay rate `k` on the old level, stable for `a = k dt`
below 2 under `Euler` (`|1 - a| < 1`) and 4 under `backward` (`3z² + (2a - 4)z + 1 = 0`,
`|z| < 1`; `z = -1` at `a = 4`).

- The explicit scheme is a rank-one operator on the junction's cells; its one nonzero
  rate is `k = G * sum(w² V) / (chi*Cm * V_s²)`, so the resistance must exceed
  `R = dt * sum(w² V) / (chi*Cm * V_s² * A)`, `V_s = sum(w V)`, `A` = 2 or 4.
- The per-cell form (`implicit` with an explicit tissue) has at most
  `k = w_max G / (chi*Cm * V_s)`, so `R > dt * w_max / (chi*Cm * V_s * A)`.

On the probe slab, `dt/(chi*Cm*V_s*A)` is 236 Ω and `sum(w² V) / V_s` is 0.468 of the
cell-wise factor: the bounds are 110.6 Ω (explicit scheme) and 143.4 Ω (per-cell form).
Crash bracket (SIGFPE in the ionic model, the junction sphere's mean Vm alternating in
sign every step and growing about 1.1 per step against a predicted 1.09):

| form | crashes at | runs at | predicted bound |
|---|---|---|---|
| `implicit` scheme, explicit tissue | 120, 135, 140, 146 Ω | 150, 160, 200, 10000 Ω | 143.4 Ω (explicit diffusion adds at most 0.1 to `a`) |
| `explicit` scheme | 90, 105, 110 Ω | 115, 125, 150 Ω | 110.6 Ω |

Between 2 and 4 times the bound's rate the BDF2 step produces a decaying period-2
ripple without crashing. An implicit tissue with the implicit scheme ran stably at
`rPvj` 1 and 10; an implicit tissue with the explicit scheme crashed at 1.15 ms at
`rPvj` 10.

omniD's check (`validation._evaluate_pvj_stability`) judges the explicit scheme of
`reactionDiffusionPvjCoupler`. Its inputs are `deltaT` (`system/controlDict`),
`ddtSchemes` (`ddt(Vm)`, else `default`, in `system/fvSchemes`), the tissue's `chi` and
`cm`, each junction's resistance (the graph's `pvjResistances`, else `rPvj`), and the
weights and volumes of the cells `pvjMapper` gathers (`pvjLocations`, `pvjRadius`,
`pvjKernel`, the mesh's cell centres and volumes). Its refusals on the slab are 90, 105
and 110 Ω, and it passes 111 Ω and above, matching the bracket above. It is not
judged before the mesh exists; the mesh is read where `constant/polyMesh` exists when
the case is judged.

## Other measurements

- **A misplaced junction couples silently.** `pvjLocations` written in millimetres
  against a mesh in metres ran to the end with no message; all three junctions coupled
  to the corner cell (V_s = 1.11e-11 m³, one cell) and the tissue activated from the
  corner at 35.4 ms. `pvjMapper` falls back to the nearest cell with weight 1 and
  compares the distance with nothing.
- **A short `pvjResistances`** (two values for three junctions, explicit scheme) read
  past its end: SIGFPE in `couplingCurrentAtPvjs` on the first step. A
  `rootStimulus.node` of 100000 on a 377-node graph ran to the end with the network
  never activating.
- **Restart.** The base case run to 0.03 s and restarted to 0.06 s against the
  continuous run: the first leg matches exactly; after the restart node 1 is at 43.2 mV
  instead of 8.4 mV (35 mV at 30.5 ms) and terminal node 4 differs by up to 0.2 mV from
  35 to 60 ms. The network's ionic model is never asked for its restart state, the
  coupler's last observation is not saved, and the restart truncates
  `postProcessing/purkinjeNetwork.dat` to the second leg.
- **The capture delay depends on `pvjRadius` at fixed `rPvj`:** 0.39, 0.65, 0.99 and
  1.97 ms at 0.6, 0.9, 1.2 and 1.8 mm, because the current is fixed by `R` and spread
  over `V_s`, which grows with the cube (the square in a slab) of the radius. At fixed
  radius, refining the mesh from 0.333 to 0.167 mm moves it from 0.39 to 0.31 ms. The
  radius is a physical size of the junction, calibrated together with `rPvj`.
- **Parallel runs agree with serial** (scotch, and a `simple (1 2 1)` split through a
  junction's sphere): network Vm identical at every node and write, the same tissue
  activation times.
- **Bidirectional eikonal echo.** With `restitutionEikonalSolver1D` the tissue's own
  antegrade activation near a junction comes back one capture delay after the terminal
  fired and counts as a block: `blockCount` 3, 3, 3 at the terminals against 1, 1, 1
  unidirectional. Activation times are unaffected.
- **A never-activated terminal** in `eikonalMonodomainPvjCoupler` evaluates the
  voltage template at `t + 1 s`, past its end, and deposits 1.2e-8 A at `rPvj` 1000
  before activation.

## What the code at `0b1bf13c` supports soundly

- `unidirectional` coupling of `reactionDiffusionPvjCoupler` is a one-way, non-loading
  coupling: the network acts as an unloaded source of the voltage `Vn`, and `rPvj` is a
  tissue-side parameter. Every native case uses it. The tissue side conserves current
  exactly (`sum_c source_c V_c = I`), the signs are right, and a junction on a face or
  corner gets its partial sphere.
- `eikonalMonodomainPvjCoupler` and `eikonalPvjCoupler` do not use the network-side
  current, so the defect above does not touch them.
- A result of bidirectional cable coupling is not reliable until the fix: retrograde
  conduction into the network, electrotonic loading of the Purkinje system by the
  tissue and PVJ block cannot occur at any resistance.

## Target

The junction as Vergara and co-workers write it, a flux condition at the fibre end:
`-pi rho² sigma_p dVp/dl = gamma_j`, with `gamma_j = (Vp - <Vm>)/R` the junction
current, spread over a ball on the tissue side (Vergara, Lange, Palamara, Lassila,
Frangi and Quarteroni, J Comput Phys 308:218, 2016,
[doi:10.1016/j.jcp.2015.12.016](https://doi.org/10.1016/j.jcp.2015.12.016)). The
network node then sees the current over the fibre cross-section and its control
length, which needs the term on the Hines diagonal to stay stable at small `R`.

Tests that do not copy the code's own term:

- *Two capacitors.* A two-node graph with zero edge conductance, a passive membrane,
  uniform kernel and tissue conductivity 0: `C_n Vn + C_t <V>` is constant and
  `Vn - <V>` decays as `exp(-t/tau)`, `tau = R C_n C_t / (C_n + C_t)`. It needs a
  passive ionic model for the test only.
- *A manufactured solution with the flux condition* taken from the analytic fields,
  so the verifier holds no copy of `assembleAppliedCurrent`'s term.
- *A ledger:* per step, the tissue's `sum_c source_c V_c` against the network's
  capacitance times its Vm rate at the junction.
- *Restart equivalence:* 0 to 0.06 s against 0 to 0.03 to 0.06 s agrees to round-off
  and keeps both legs of `purkinjeNetwork.dat`.
- *Implicit coupling:* `rPvj` 10 with an explicit tissue runs, each junction cell
  staying between its old Vm and `Vn`; `pvjCouplingScheme explicit` with `rPvj` 100
  is refused by name before the first step.
