# cardiacFOAM's Purkinje-myocardium (PVJ) coupling: what native main did, and what the fixes do

**Method:** [`method.md`](method.md). **Before the fixes:** native main `0b1bf13c`.
The binary those runs used was built from the owner's working tree at `31c5dbea`,
whose PVJ sources (`pvjMapper`, `pvjCoupler`, `reactionDiffusionPvjCoupler`,
`eikonalMonodomainPvjCoupler`, `conductionSystemDomain`, `monodomain1DSolver`,
`monodomainSolver`) are byte-identical to `0b1bf13c`. **Date:** 2026-10-05.
**After the fixes:** cardiacFOAM PR #53's branch at `a6f0361d` (1D-3D PVJ coupling
fixes on top of `18f25c9d`); the evidence is in "After the fixes" below. Every
section before it, the tables and measurements included, describes native main
`0b1bf13c`. The catalogue describes the intended semantics. Keys and units are in
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

At native main `0b1bf13c`, the tissue update per combination, with `n` the old and `n+1` the new level, `G = 1/R`,
`w` the kernel weight, `<V>` the weighted mean of the tissue Vm over the junction's
cells, `K` the finite-volume Laplacian and `D_t` the `ddtSchemes` operator:

| `solutionAlgorithm` | `pvjCouplingScheme` | tissue equation in a junction cell |
|---|---|---|
| explicit | explicit | `chi*Cm D_t V = K V^n - chi*Cm Iion + S + w G (Vn^{n+1} - <V^n>)/V_s` |
| explicit | implicit | the same with `<V^n>` replaced by the cell's own `V^n`: the coefficient multiplies the old Vm on the right-hand side |
| implicit | explicit | `K V^{n+1}` and an Iion at the extrapolated level; the junction term as in the first row |
| implicit | implicit | `chi*Cm D_t V + w G V^{n+1}/V_s = K V^{n+1} - chi*Cm Iion + S + w G Vn^{n+1}/V_s`: the coefficient is on the diagonal |

`solutionAlgorithm` is read as `explicit` or else implicit: `Explicit` or a typo ran
the implicit path without a message (unchanged by the fixes). At `0b1bf13c`,
`eikonalMonodomainPvjCoupler` never read `pvjCouplingScheme`, and the two rows with
the implicit scheme put the coefficient on the old level or the diagonal as the table
says, for the implicit tissue only. The network advances first with the tissue at level `n`, the
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
`reactionDiffusionPvjCoupler` and of `eikonalMonodomainPvjCoupler`, which adds the same
explicit term every step (at `0b1bf13c` it has no other; omniD judges it when its
`pvjCouplingScheme` is explicit or absent, as the fixed C++ reads it). Its inputs are
`deltaT` (`system/controlDict`), `ddtSchemes` (`ddt(Vm)`, else `default`, in
`system/fvSchemes`), the tissue's `chi` and `cm`, each junction's resistance (the
graph's `pvjResistances`, else `rPvj`), and the labels, weights and volumes of the
cells `pvjMapper` gathers (`pvjLocations`, `pvjRadius`, `pvjKernel`, the mesh's cell
centres and volumes). The explicit solver may cap `deltaT` below the written value
(`myocardiumDomain::applyModelTimeControls`, `maxCo*min(dx^2/D)`), which lowers the
bound; omniD uses the value as written and says so.

**Junctions that share cells.** The bound above treats a junction alone. Junctions whose
cell sets overlap add their terms on the shared cells, so the operator is a sum of
rank-one terms `a_k b_k^T` with `a_k[c] = w_ck / (R_k V_k chi*Cm)` and
`b_k[j] = w_jk V_j / V_k`, and its non-zero eigenvalues are those of the K x K matrix
`N_lk = sum_j w_lj w_kj V_j / (V_l V_k R_k chi*Cm)`. omniD groups the junctions that
overlap and takes the largest eigenvalue of each group (a power iteration on the
similar symmetric matrix `D^(1/2) P P^T D^(1/2)`). Human idealizedHeart's 1142
junctions (`rPvj` 1000, `pvjRadius` 1.65 mm, linear kernel, `dt` 2e-5, backward) need
`rPvj` above 2.47 ohm as a group, against 1.09 ohm for a junction alone; at 2.0 ohm the
check refuses, at 3.0 ohm it passes with a note that the rate times `dt`, 3.29, is within
a factor 2 of the limit 4. Between half the limit and the limit the tissue is stable but
carries the alternating ripple, and omniD says so. It is not judged before the mesh
exists; the mesh is read where `constant/polyMesh` exists when the case is judged, only
for the cells with a point within 2.5 `pvjRadius` of a junction, and a mesh whose such
cells have more than 600000 faces is reported as unreadable, not read for minutes.

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

## After the fixes

**Build and probes.** `a6f0361d` built into a scratch install, every library loaded
from it and none from the owner's tree. Probe case as above unless stated; evidence
from the fixes log. The unidirectional runs with the explicit scheme (R 115) and the
eikonal coupler's explicit scheme are byte-identical (time directories and
`purkinjeNetwork.dat`) to a pristine build of `18f25c9d`.

**What the C++ now does.**

- `pvjCouplingScheme implicit` puts the junction term on the tissue's diagonal
  (`fvm::Sp`) for both tissue algorithms, in `unidirectional` mode;
  `eikonalMonodomainPvjCoupler` reads the key and does the same with its template
  voltage.
- In `bidirectional` mode `reactionDiffusionPvjCoupler` gives the tissue exactly the
  current the network solved (an explicit deposit) whatever the scheme. The network
  loses each junction current from the terminal node's volume `pi rho^2 L`, `rho`
  the new key `purkinjeFibreRadius` (m, required, read with a plain `get<scalar>`) and
  `L` half of each incident edge, with `Vn'` on the Hines diagonal and `<V>` the tissue
  Vm from before the tissue solve. A cell-wise implicit term in this mode saw the
  network a step late, a spurious capacitance `dt/R` that was 94 times the tissue's
  `chi*Cm*V_s` at R 10 and froze the junction.
- The restart writes and reads the network's ionic state, the coupler's last
  observed tissue activation (`lastObservedTissueActivation.<coupling>`), the
  restitution network's pending events and the time series.
- `coupled1D3DMonodomainVerifier` computes `pi rho^2 L` from `purkinjeFibreRadius`
  and the edge lengths itself.

**Charge ledger** (per step, the network's residual of its own cable equation at the
terminals times `pi rho^2` against the tissue's `sum_c source_c V_c`, from the written
binary fields), R 3e5, 7.10 to 9.00 ms, 39 steps: `|I_net - I_tis|` at most 1.4e-22 A
(relative 4.6e-13), window charge 8.703664e-13 C on both sides. With
`pvjCouplingScheme implicit` in bidirectional mode: 1.9e-17, 2.7e-18 and 1.4e-22 A per
step at R 1, 10 and 3e5, window charge equal. Bidirectional implicit runs are
byte-identical to bidirectional explicit at R 1, 10, 1e4, 3e5, 1e6 and 1e7 (720 files
each, `.dat` the same).

**Retrograde conduction** (root off, a tissue box on junction 4 at 5 ms, the
probe slab's 377-node cable network, `rho` 14.29 um):

| `rPvj` | 1, 10, 1e4 | 3e5 | 1e6 | 1e7 |
|---|---|---|---|---|
| terminal 4 fires at | 6.35 ms | 6.45 ms | 6.65 ms | never |

The first fixed build, at R 1e4, 1e5 and 3e5, had 253, 253 and 247 of 377 nodes
active by 30 ms; the unidirectional control at 3e5 activates none. Antegrade
bidirectional (R 1e4, 3e5): the root fires, the terminals are blocked by the
source-sink mismatch, 368 and 371 of 377 nodes activate and the tissue is not captured
by the network. Before the fixes, retrograde activation never occurred (0 of 377 nodes).

**Manufactured solution, which now tells a conservative coupling from a
non-conservative one** (`monodomain1D3D`, bidirectional, `purkinjeFibreRadius`
`1/sqrt(pi)` m, L2 errors; rates in brackets):

| N | 10 | 20 | 40 | 80 |
|---|---|---|---|---|
| fixed, 3D Vm | 3.9052e-3 | 1.0169e-3 (1.94) | 2.5698e-4 (1.98) | 6.4459e-5 (2.00) |
| fixed, graph Vm1D | 3.7572e-4 | 9.3378e-5 (2.01) | 2.2877e-5 (2.03) | 5.5901e-6 (2.03) |
| old coupling, new verifier, 3D | 4.41e-2 | 5.43e-2 | 5.78e-2 | 5.8889e-2 |
| solver volume halved, 3D | 4.39e-2 | 5.13e-2 | 5.35e-2 | 5.3936e-2 |

At N = 80 the graph error is 2.6061e-1 with the old coupling and 2.3908e-1 with the
halved volume, against 5.5901e-6 fixed. The implicit scheme gives the fixed numbers;
unidirectional is unchanged. At native main the same case passed with the code's own
term (graph error 7.0e-6 to 7.1e-6), which is why the verifier now builds the
volume from the radius and the edge lengths.

**Unidirectional implicit.** With an explicit tissue and `pvjCouplingScheme implicit`,
`rPvj` 10, 100, 150 and 1e4 run for 60 ms; the junction sphere's Vm flips sign between
steps (above 0.1 mV) once at R 10 and R 100, against 131 flips at R 150 at native main.
Retrograde bidirectional at R 10, which crashed at 1 ms at native main, runs.
`pvjCouplingScheme explicit` is unchanged and keeps the bracket measured above (R 110
crashes at 34.9 ms, R 115 runs; byte-identical to the pristine build at R 115).
The implicit scheme writes, at output times, the current the tissue received,
`G (Vn' - <V'>)` over `V_s`, which agrees with the deposit reconstructed from the
fields to 3e-9 relative. `eikonalMonodomainPvjCoupler` with `implicit` activates 7218
tissue cells, the earliest at 17.95 ms against 17.84 ms explicit.

**Restart** (0 to 0.06 s against 0 to 0.03 to 0.06 s):

- cable (monodomain variant): `purkinjeNetwork.dat` byte-identical to the continuous
  run, both legs (12 rows). Time-directory fields: the first leg identical, after the
  restart at most 5e-11 V from the continuous run in the tissue and 1.3e-13 V in the
  network (the adaptive ODE step sizes are not state). Native main was 11 to 13 mV off
  from 35 to 45 ms, and the `.dat` held only the second leg.
- restitution network (`eikonalMonodomainPvjCoupler`, bidirectional), split at 0.015
  s: the network has 367, 377 and 377 nodes active at 0.0175, 0.02 and 0.03 s and 704
  tissue cells are activated at 0.03 s, as in the continuous run; `.dat` identical and
  activation fields byte-identical. The `.vtk.series` has all 12 entries (6 at native
  main).

**Regressions.** The native regression scripts pass: `purkinjeRestitution2D` 32 of 32
over its three variants, `electroHeart` 24 of 24 (three variants, two trees),
`conductionBlock` 4 of 4. The
only reference that moved is `purkinjeRestitution2D`'s monodomain `IcouplingSource`
rows, now -6041.88396, -6191.65009, -1028.87739 and -1507.08188 against -6061.67,
-6218.72, -1030.33 and -1506.77 (-0.33, -0.44, -0.14 and +0.02 %), from the diagonal
junction term.

**Left in the C++.** A parallel restart of a Purkinje network fails on rank 1, as it
did before the fixes. `pvjRadius` is still a numerical sphere, not a physical size of
the junction (the capture delay above still depends on it at fixed `rPvj`). The
stimulus window is still half-open. The input checks (`pvjResistances` length and
sign, `rPvj` range, `rootStimulus.node`) and a stability guard in the C++ were taken
out by the owner's decision; omniD judges the resistance bound before the run.
