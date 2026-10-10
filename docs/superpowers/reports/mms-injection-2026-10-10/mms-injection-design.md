# One manufactured problem, many cardiac EP solvers: an injection design

**Status:** proposal for the owner, 2026-10-10. No omniD code and no repository
was changed. Probes ran in `~/omnid-runs/2026-10-10/mms-injection/`.
Feeds the
verifier package (`2026-10-10-benchmark-verifier-builder-design.md`).

**cardiacFOAM source read:** git objects only. `HEAD` = `origin/main` =
`277dfeb1` in `~/noFrontendCardiacFoam_minor_errors`. `origin/omnid/tutorials-are-pointers`
(`a7b8e845`, the exported tree) differs from it under `src/verificationModels`
and `src/ionicModels/verificationModels` only in `coupled1D3DMonodomainVerifier.C`
(+17/-1), so every statement below holds on both.

## 1. What the owner built in cardiacFOAM

### 1.1 Mechanism: three layers, all runtime-selected

1. **A manufactured cell model** (`src/ionicModels/verificationModels/*FDAManufactured`).
   It is an ordinary `ionicModel`. Its states are `V, u1, u2, u3`, and it has
   the constants `Cm = 2`, `Chi = 3` and `Beta`. `u3` has a zero rate, so it is a
   spatially varying constant that the verifier sets per cell.
2. **A verifier** (`src/verificationModels/*`, base classes in
   `src/electroModels/core/verificationModels`). It has two hooks:
   - `preProcess`: writes the exact `Vm`, `u1`, `u2` and `u3` (and `phiE`) at
     the cell centres at the start time. These are the spatially varying initial
     conditions.
   - `postProcess`: at `endTime` (half-step tolerance), compares the solution
     with the exact fields. It reports L1, L2 and Linf to
     `postProcessing/<dim>_<N>_cells.dat`. L1 and L2 are volume-weighted and
     normalised by the total volume (`verificationUtils::computeNorms`), so L2 is an RMS.
3. **An optional volumetric source** for problems whose cell model does not
   balance the diffusion term. `myocardiumDomain` calls
   `verificationModel->addManufacturedPdeSource(sourceField_, conductivity, t0 + dt)`,
   adding the source to the same `sourceField_` that carries the external
   stimulus. The ionic model can also take the source through
   `setManufacturedSourceTerm` (`Im += source/(chi*Cm)`).

**The Pathmanathan & Gray (P&G) problems need no source term.** The cell model
is built so that the exact solution satisfies the coupled nonlinear system with
the stimulus at zero. `Beta*(V - u3)/Chi` cancels the diffusion of `V`, and the
`u1`/`u2` ODEs hold exactly. I confirmed this symbolically for 1D/2D/3D,
monodomain and bidomain (§6, E9).

### 1.2 Inventory

| problem (record) | PDE | exact solution | injection | BCs / domain | refinement study |
|---|---|---|---|---|---|
| **P&G monodomain** 1D/2D/3D. Verifier `manufacturedFDAMonodomainVerifier`, ionic `monodomainFDAManufactured` (record `manufacturedMonodomainPseudoECG`) | monodomain `chi(Cm dV/dt + Iion) = div(sigma grad V)` | `V = sqrt(1+t) F`, `F = cos(pi x)[cos(2 pi y)[cos(3 pi z)]]`; `u1 = (1+t)G + sqrt(1+t)F`, `u2 = 1/((1+t) sqrt G)`, `u3 = 0`; `G = 1 + x[y^2[z^3]]` | cell model only; exact ICs for V, u1, u2 | unit box, zero flux (F' = 0 on the faces); `t` in [0, 0.2] | `cartesianConvergence/sweep_hex_convergence.json`: 1D/2D/3D, N = 10/20/40/80, dt = 0.00892857/0.00224215/0.000560538/0.000140174 (dt proportional to h^2); plus tet and temporal studies |
| **P&G bidomain** 1D/2D/3D. `manufacturedFDABidomainVerifier`, `bidomainFDAManufactured` (`manufacturedBidomain`) | bidomain | same V and u; `phiE = -k sqrt(1+t) F + shift`, `k = 1/sqrt2`; `sigma_e = sigma_i (1-k)/k` | same cell model, `Beta_bi = (1-k) Beta_mono`; phiE gauge fixed at `phiERefPoint` | unit box | 1D/2D/3D x N = 10..80, same dt ladder; tet, corrector |
| **P&G bidomain with bath** 1D/2D/3D. `manufacturedFDABathBidomainVerifier`, `bathBidomainFDAManufactured` (`manufacturedBathBidomain`) | bidomain + bath | `V = sqrt(1+t)cos(pi x) - alpha x/s_e`, `u3 = -alpha x/s_e` (a spatial constant state), piecewise phiE in bath [-1,0] and [1,2]; `sigma_bath = s_e/2`; `alpha = 0.01` | cell model + **boundary current** (`fdaBathVariant electrodePair`: flux on xMin/xMax) or a **ground** Dirichlet patch (`groundElectrode`) | [-1,2] with tissue in [0,1]; the solution varies in x only, while u1 and u2 depend on y and z through G | 1D/2D/3D x N = 10..80; electrodePair and groundElectrode sweeps; tet, coupling, gradient-scheme, temporal studies |
| owner's: anisotropic monodomain (`manufacturedAnisotropicMonodomainVerifier`) | monodomain, full SPD tensor with off-diagonal terms | `V = sqrt(1+t) sin^2(pi x) sin^2(pi y) sin^2(pi z)` | **volumetric source** `sqrt(1+t)(Beta F - div(K grad F))` at `t0 + dt` | unit cube (checked), zero flux | the 3D rows of the monodomain sweep |
| owner's: conormal monodomain / unequal-conormal bidomain (`insulatedWall`) | mono/bido, `sealedWallTrace conormal` | `F = Re[v(x) e^{i(wy y + wz z)}]`, quadratic `v` chosen so `n.G.grad F = 0` at x = 0 and 1 | volumetric source | conormal-insulated x-walls, periodic in y and z | tet studies |
| owner's: pseudo-ECG, eikonal, eikonal-ECG, 1D-3D Purkinje coupling, graph, electromechanics | not covered | Gauss-Legendre reference integrals, etc. | in-solver verifiers | | various |

**Against the nine:** all nine P&G/FDA problems (monodomain, bidomain and bath,
each in 1D, 2D and 3D) are implemented and swept in cardiacFOAM. None is
missing. The owner added four kinds beyond them:
- the full-tensor anisotropic monodomain;
- conormal walls;
- unequal-anisotropy conormal bidomain;
- non-EP problems (ECG, eikonal, coupling, electromechanics).

The rotated-tensor case that exercises the wall condition is one of the
owner's problems, not P&G's. It needs a source term, which the nine do not.

**Finding: a literal restates a relation.** `Beta` is hard-coded as
`-1.1/-5.9/-8.6`. It equals `-pi^2(sigma_xx + 4 sigma_yy + 9 sigma_zz)` truncated
to the dimension. With the 9-digit conductivities of the monodomain sweep, the
mismatch is about 2e-8. The bidomain tutorial's `electroProperties` gives sigma
to 6 digits (`0.111453 ...`) and its sweep does not override it, which leaves an
inconsistent source of about 1.6e-5·V in 3D (E10). That is an error floor that a
fine enough mesh will hit. The data model below states one value and derives the
other (owner rule: "one source of truth").

## 2. Injection points per solver

| need | cardiacFOAM | openCARP v18.1 | TorchCor | MonoAlg3D |
|---|---|---|---|---|
| custom cell model (states, rates, Iion) | native C++ ionic model | **EasyML `.model` → `make_dynamic_model.sh` → `.so`**, loaded with `-num_external_imp 1 -external_imp[0] <abs path>`. Built in 2.4 s here (E1) | **any Python object** with `initialize(n)` and `differentiate(V)` returning dV/dt; `region_ids`, `node_indices`. Passed in `ionic_models=[...]` (E5) | C model library (`GET_CELL_MODEL_DATA`, `SET_ODE_INITIAL_CONDITIONS_CPU`, `SOLVE_MODEL_ODES`), a directory with `build.sh` under `models_library`, loaded by `[ode_solver] library_file` (E7) |
| model sees **time** | yes | **yes**: EasyML has `t` (E3) | no `t` in `differentiate`; `Stimuli.apply(t)` has it | yes: `SOLVE_MODEL_ODES(..., real current_t, ...)` |
| model sees **space** | verifier sets fields from cell centres | **no x**. Per-node states and external variables are set by `adjustment[i]` files (`MULTI_IF::adjust_MIIF_variables`). A state with `diff_s = 0` is a nodal parameter, the same device as cardiacFOAM's `u3`. Coordinates can be such states, so any `f(x,t)` can be written in EasyML | the model can hold the node coordinates (`sim.nodes[im.node_indices]`) | `SET_EXTRA_DATA(...)` gets the grid (cell centres) and returns per-cell arrays, read by the model's ICs and RHS (`solver->ode_extra_data`) |
| exact **initial conditions** per DOF | `preProcess` | `adjustment` of `Vm` and of `<Model>.<state>`. **Probed: t=0 error 1.2e-8** (E2) | `initialize` returns V at the nodes and sets the states (E5) | `init_function = set_initial_conditions_from_odes` takes V from `sv[0]`, which is set from extra data (E7) |
| volumetric source `f(x,t)` | `addManufacturedPdeSource` | in EasyML (coordinate states + `t`), or separable `stim[].elec.vtx_fcn = 1` (nodal scaling) x `stim[].pulse.file` (time trace) | replace `sim.stimuli` with an object exposing `apply(t)` (the only use in `Monodomain.step`) | inside the model RHS (extra data + `current_t`); the built-in stimulus is `f(x)` on/off only (`solve_all_volumes_odes`) |
| bidomain | yes | yes (`-bidomain 1`); **probed** (E4) | **no**: only `Monodomain` and `ReactionEikonal` | **no**: monodomain only |
| bath / electrode BCs | yes | `gregion[].g_bath`, extracellular current (`crct.type 1`) and ground (`3`) stimuli. Not probed | no | no |
| output to read | `*_cells.dat` errors and Vm fields | `vm.igb`, `phie.igb` at nodes | Vm tensor at nodes (returned / `Vm.pt`) | `save_as_text_or_binary`: cell centres + V |
| fixed conventions the injection must map | Cm and chi free | **Cm = 1 hard-coded** (`electrics.cc`); beta in 1/µm, sigma in S/m, dt in µs, x in µm | `Cm = 0.01`, `Chi = 140`, `/100` scalings fixed in `Monodomain`; x in mm | beta, cm and sigma configurable; µm |

## 3. Options

- **(c) Hand ports per solver** (the baseline). Each port restates the problem,
  so it drifts and it does not automate. Rejected.
- **(b) Extract from cardiacFOAM's C++.** cardiacFOAM stays the only definition,
  but:
  - the formulas sit in imperative `forAll` loops spread over three files per
    problem (reference header, ionic header, verifier);
  - the relations (Beta from sigma, sigma_e from k) are hard-coded literals;
  - a scanner that turns C++ arithmetic into symbolic expressions is a large
    and fragile tool.

  As the definition: rejected. As the provenance and a drift gate: kept.
- **(a) A solver-neutral problem definition as data, with symbolic expressions,
  from which each plugin generates its injection.** Recommended. It is "(a)
  transcribed from (b)":
  - every field of the data cites the cardiacFOAM file and commit it comes
    from, and P&G/FDA;
  - cardiacFOAM keeps running its native implementation, unchanged;
  - two gates tie the data to the C++ (§4.4), so the owner's code stays the
    origin and the data cannot drift from it silently.

## 4. Recommended design

### 4.1 Ownership

- **Core:** unchanged. It names no physics. At most, an optional plugin
  contract member names "stage a manufactured problem" and "read DOF field". It
  passes the problem as opaque data, and its absent answer is a refusal by name.
- **`omnidriver-verifier`:** owns the problem vocabulary (equation family,
  exact fields, cell-model block, relations, BC kinds) as data files, plus
  three pieces of code:
  1. a sympy layer that parses, checks residuals and derives any source;
  2. the shared norm;
  3. the order fit.
- **Each plugin:** owns its generator. It turns the verifier's resolved problem
  (plain expressions and numbers) into native input, and its reader returns
  `(points, weights, values)` at the end time.

### 4.2 Data shape (one file per problem family; the dimension is an axis)

```toml
# omnidriver-verifier/problems/pathmanathan-gray-2014/monodomain.toml
id = "pathmanathan-gray-2014/monodomain"
cites = ["doi:10.1002/cnm.2615", "FDA RST24CV03.01"]
native = { cardiacfoam = { commit = "277dfeb1",
  cell_model = "src/ionicModels/verificationModels/monodomainFDAManufactured/monodomainFDAManufactured_2014.H",
  reference  = "src/verificationModels/monodomainVerification/manufacturedFDAReference.H",
  record = "manufacturedMonodomainPseudoECG",
  verifier = "manufacturedFDAMonodomainVerifier" } }
equation = "monodomain"            # chi*(Cm*dV/dt + Iion) = div(sigma*grad(V)) + chi*Cm*f
dimensions = [1, 2, 3]
domain = { box = [[0, 1], [0, 1], [0, 1]] }     # first d axes
time = { start = 0, end = 0.2 }
boundary = { all = "zero_conormal_flux" }

[parameters]
Cm = 2
chi = 3
sigma = { xx = 0.111453302, yy = 0.121585420, zz = 0.030396355 }

[derived]                          # relations, never restated literals
Beta = "-pi**2*(sigma_xx + 4*sigma_yy*(d>=2) + 9*sigma_zz*(d>=3))"

[fields]
F = { 1 = "cos(pi*x)", 2 = "cos(pi*x)*cos(2*pi*y)", 3 = "cos(pi*x)*cos(2*pi*y)*cos(3*pi*z)" }
G = { 1 = "1 + x", 2 = "1 + x*y**2", 3 = "1 + x*y**2*z**3" }

[exact]                            # also the initial conditions at t = start
V  = "sqrt(1 + t)*F"
u1 = "(1 + t)*G + sqrt(1 + t)*F"
u2 = "1/((1 + t)*sqrt(G))"
u3 = "0"

[cell_model]                       # in V and the states only: no x, no t
states = ["u1", "u2", "u3"]
rates = { u1 = "(u1+u3-V)**2*u2**2 + (u1+u3-V)*u2**2*(V-u3)/2",
          u2 = "-(u1+u3-V)*u2**3", u3 = "0" }
Iion = "-(Cm/2)*(u1+u3-V)*u2**2*(V-u3) + Beta*(V-u3)/chi"

[source]
f = "derive"     # the verifier computes the residual; it must be 0 for P&G

[check]
fields = ["V", "u1", "u2"]
at = "end"
refinement = { cells = [10, 20, 40, 80], dt = "0.2/(25*4**level)" }  # dt ∝ h^2; dt divides end
```

The bidomain file adds `phi_e = "-k*sqrt(1+t)*F"`, `k = "1/sqrt(2)"` and
`sigma_e = "sigma_i*(1-k)/k"`, sets `Beta = "(1-k)*Beta_mono"`, and states a
gauge rule (`mean_zero`). The bath file adds sub-domains, `sigma_bath = "sigma_e_xx/2"`,
and `u3 = "-alpha*x/sigma_e_xx"` as a nodal parameter. Its boundary kinds are
`current(alpha)` and `ground`.

### 4.3 What each plugin generates

| plugin | generated | from |
|---|---|---|
| cardiacFOAM | **nothing new**. It maps the problem and dimension to the existing record, the `verificationModel` type and its keys (`k`, `alpha`, `fdaBathVariant`), the `dimension` axis and the `numberCells` axis | `native.cardiacfoam` |
| openCARP | (1) EasyML `.model` from `[cell_model]`, with `Iion/Cm` because openCARP fixes Cm = 1, and Beta as `.param()`; then `make_dynamic_model.sh`; (2) one `adjustment` file per non-zero exact IC and nodal parameter; (3) conductivities scaled so that `D/L^2 = sigma/(chi Cm)` (the probe used `sigma_carp = 0.233333 sigma_nd` at beta 0.14/µm and L = 1000 µm); (4) `-bidomain 1` for bidomain; (5) a non-zero `f`: coordinate states plus `t` in EasyML; (6) bath: g_bath regions + extracellular current/ground stimuli. sympy `ccode` output compiles in EasyML (`pow` probed, E3) | `[cell_model]`, `[exact]`, `[parameters]`, `[source]` |
| TorchCor | no files: one generic class in the plugin turns the expressions into torch with `sympy.lambdify(modules="torch")`; `initialize` evaluates `[exact]` at `sim.nodes`; a non-zero `f` goes through a `Stimuli`-shaped `apply(t)`; mesh in mm | same |
| MonoAlg3D | a C model directory (`build.sh` + `.c` from `ccode`) and an extra-data function storing cell centres (or F, G per cell); `init_function = set_initial_conditions_from_odes`; `[main] beta/cm` set directly; `save_as_text_or_binary` | same |

### 4.4 Gates that keep the data honest

1. **Residual gate (pytest, no solver).** sympy substitutes `[exact]` into the
   PDE(s) and the `[cell_model]` ODEs. The residual must equal `[source].f`,
   which is zero for P&G. A transcription error fails here. Probed: zero for
   mono/bido x 1D/2D/3D in 0.8 s (E9).
2. **Native drift gate.** The cardiacFOAM plugin's C++ scanner already reads
   constants. It asserts that `Cm`, `Chi` and the `Beta` table in the `native`
   files equal the data's values and derivations. It fails when the owner
   changes the C++.
3. **Norm agreement (`omnidriver check`, reports only).** The verifier's shared
   norm, computed from cardiacFOAM's written Vm, must reproduce the solver's own
   `*_cells.dat` L2 to round-off. That confirms that the shared norm and the
   owner's norm are the same quantity.

### 4.5 Comparing errors: FE (nodal) against FV (cell-centred)

- **The verdict is per solver: observed order against its declared formal
  order.**
  - Each scheme declares `p_space` and `p_time`.
  - On the path dt ∝ h², the expected order is `min(p_space, 2 p_time)`, which
    is 2 for all four codes here (Godunov splitting and explicit ionics are
    first order in time).
  - A temporal ladder at fixed fine h measures `p_time` separately
    (cardiacFOAM already has `temporalConvergence`).
- **One shared norm, at each solver's own DOFs and weights.** The reader
  returns `(x_i, w_i, u_i)`, with `w_i` = the cell volume (FV) or the
  lumped-mass row sum, i.e. the nodal control volume (FE). The verifier then
  computes:
  - `L2 = sqrt(sum w_i e_i^2 / sum w_i)` (cardiacFOAM's definition);
  - `Linf = max |e_i|`.

  On uniform meshes this is the nodal RMS used in the probes. No solver-specific
  quadrature enters the verdict.
- **Error levels at common points are reported, not judged.**
  - Use nested families. An FE mesh with 2N cells per side has nodes at every
    centre of the FV mesh with N cells.
  - Otherwise, evaluate the FE P1 interpolant at the FV centres. The FE
    solution is a function and the FV one is not, so never reconstruct FV at
    nodes.
  - Report the paired errors and their ratio. Differences between
    discretisations are a result, not a failure.

### 4.6 Nonlinear ionic terms and operator splitting

- **The P&G design avoids the usual MMS trap.**
  - The exact solution satisfies the full nonlinear coupled system with no
    added source, so there is no question of when to evaluate the source in time.
  - Splitting and ODE-integrator errors appear as an O(dt^p) temporal error,
    measured rather than hidden.
  - dt ∝ h² keeps them from masking the spatial order.
- **The owner's source-bearing problems carry a time-level choice.**
  cardiacFOAM evaluates the source at `t0 + dt`. A generator must evaluate it
  where its scheme expects it; a mismatch costs O(dt).
- **Limits:**
  - the manufactured cell model is not excitable, so there are no fronts;
  - Rush-Larsen gate integrators and lookup tables are not exercised (EasyML
    chose `rk4` here);
  - the ICs of all states must be exact;
  - in 1D, FE nodal values can superconverge, so an order above 2 at nodes is
    not a defect.

## 5. Feasibility

| solver | monodomain | bidomain | bath | blocker / work |
|---|---|---|---|---|
| cardiacFOAM | easy (exists) | easy (exists) | easy (exists) | none; fix the 6-digit sigma (§1.2) |
| openCARP | **easy: probed, L2 orders 1.60/1.88/1.97** | **easy: probed, Vm 1.53/1.88/1.97, phiE 1.61/1.90/1.98** | needs work | bath: map flux/ground BCs onto openCARP's extracellular stimuli (total-current distribution over surface nodes not yet verified) and handle the phiE gauge; 2D/3D need only the box mesh and F, G in y and z |
| TorchCor | **easy: probed, orders 1.04/1.61/1.89** (through the real `Monodomain` class) | **blocked**: no bidomain solver | **blocked** | none for monodomain; TorchCor's own `verification/manufactured_2d.py` reimplements the time loop and so does not verify `Monodomain.step` |
| MonoAlg3D | needs work (not run) | **blocked**: monodomain only | **blocked** | generating a C model + extra data and building a model library (another agent owns the build); per-cell extra-data index mapping to verify; structured hex only; full-tensor sigma needs a different assembly function |

The probe errors of openCARP and TorchCor on the same meshes agree to within 3%
at N = 80 (1.72e-4 and 1.76e-4).

## 6. Evidence

| id | claim | evidence |
|---|---|---|
| E0 | refs read | `git -C ~/noFrontendCardiacFoam_minor_errors rev-parse HEAD origin/main origin/omnid/tutorials-are-pointers` → `277dfeb1…`, `277dfeb1…`, `a7b8e845…`; `git diff --stat origin/main origin/omnid/tutorials-are-pointers -- src/verificationModels src/ionicModels/verificationModels` → only `coupled1D3DMonodomainVerifier.C` |
| C1 | cell models, constants, Beta table | `git show HEAD:src/ionicModels/verificationModels/{monodomain,bidomain,bathBidomain}FDAManufactured/*_2014.H` (`Cm = 2`, `Chi = 3`, `Beta = -1.1/-5.9/-8.6`; bidomain `betaBase*(1-k)`; bath `-1.1*(1-k)`) |
| C2 | exact solutions | `manufacturedFDAReference.H` (`computeF`, `computeG`, `computeManufacturedV`, `computeManufacturedU`); `manufacturedFDABidomainReference.H`; `manufacturedFDABathBidomainReference.H` |
| C3 | source injection path | `myocardiumDomain.C` (`bindSourceField`, `addManufacturedPdeSource(sourceField_, *conductivityPtr, t0 + dt)`); `monodomainFDAManufactured.C` (`manufacturedSourceCorrection`, `setManufacturedSourceTerm`); `manufacturedAnisotropicMonodomainReference.H` (`computeAnisotropicManufacturedPdeSource`) |
| C4 | norms and timing | `verificationUtils.H` (`shouldReportManufacturedErrors`, volume-weighted `computeNorms`); `manufacturedFDAMonodomainVerifier.C` writes `postProcessing/<dim>_<N>_cells.dat` |
| C5 | sweeps | `tutorials/manufacturedSolutions/{monodomainPseudoECG,bidomain,bathBidomain}/setup/studies/cartesianConvergence/*.json`: dimensions 1D/2D/3D, cells 10–80, dt ladder ∝ h²; the bath sweeps `electrodePair` and `groundElectrode` |
| C6 | case parameters | `constant/electroProperties` of each case (sigma, `k 0.707107`, `alpha 0.01`, `fdaBathVariant`, `phiERefPoint`); `system/controlDict` `endTime 0.2`; bath `blockMeshDict.1D` spans [-1,2] |
| C7 | the nine = mono/bido/bath × 1D/2D/3D, stimulus zero | FDA page https://cdrh-rst.fda.gov/node/1576 (WebFetch, 2026-10-10); `docs/superpowers/reports/literature-2026-10-10/research-verifier-novelty.md`; bath README "Origin: … (Pathmanathan & Gray 2014)". **The P&G paper itself was not read**: the formulas trace to the owner's code |
| C8 | omniD records | `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/records/manufactured_{monodomain_pseudo_ecg,bidomain,bath_bidomain,eikonal_ecg,monodomain_1d3d}.py` |
| E1 | EasyML builds | `make_dynamic_model.sh FDAMono` → `FDAMono.so` in 2.4 s (`opencarp/FDAMono.model`) |
| E1b | single cell exact, first order in dt | `bench --load-module ./FDAMono.so --imp FDAMono --imp-par "Beta=0" --duration 1 --dt {0.002,0.001,0.0005}` → V(1) error 1.50e-4, 7.50e-5, 3.75e-5 (`opencarp/bench_dt_convergence.txt`) |
| E2 | openCARP monodomain 1D tissue | `opencarp/tissue/run.sh N dt` (mesher slab 1000 µm, `adjustment` of Vm, `FDAMono.u1`, `FDAMono.u2`; `Beta=-1.1`; g = 0.0520114 for i and e) and `err.py`: t=0 L2 1.18e-8; t=0.2 L2 1.92e-3, 6.35e-4, 1.72e-4, 4.39e-5 for N = 20/40/80/160, dt = 2/0.5/0.125/0.03125 µs → orders 1.60, 1.88, 1.97 (`tissue/convergence_N.txt`) |
| E3 | EasyML sees `t`; `pow` accepted | `opencarp/TimeSrc.model` (`Iion = -A*s/sqrt(1+t)`), bench V(1) error -7.3e-5 at dt 1e-3, halving with dt (`bench_time_source.txt`); `FDAPow.model` with `pow(u2, 3.0)` builds |
| E4 | openCARP bidomain 1D | `tissue/run_bi.sh` (`-bidomain 1 -floating_ground 1`, `g_i = 0.0260057`, `g_e = 0.0107719`, `Beta=-0.322182`), `err_bi.py` (phiE mean-removed): orders Vm 1.53/1.88/1.97, phiE 1.61/1.90/1.98 (`tissue/convergence_bidomain.txt`) |
| E4b | openCARP quirks | `make_dynamic_model.sh` exits 0 when the compile fails (`timesrc_build.log`, first attempt); `external_imp` needs an absolute path (`run_10.log`: "absolute paths must be used"); when tend is not reached exactly, the last frame is dropped (N=10, dt=8 µs: igb `t:2`); the build banner prints a CI token (not copied anywhere) |
| E4c | openCARP mechanisms in source | `/usr/local/lib/opencarp/share/openCARP/`: `physics/electrics.cc` (`SF_real Cm = 1.0`), `simulator/sim_utils.cc` (`load_ionic_module(external_imp[ii])`), `physics/ionics.cc` (`setup_MIIF` → `adjust_MIIF_variables`), `physics/limpet/src/MULTI_ION_IF.cc` ("state variables are the only variables … that vary on a nodal basis"); `openCARP +Help stim[0].crct.type`, `stim[0].elec.vtx_fcn`, `adjustment[0].variable` |
| E5 | TorchCor API and probe | `~/torchcor-cases/torchcor/torchcor/simulator/monodomain.py` (`step`: `du = im.differentiate(u[idx]) / 100`, `b = u*Cm + dt*du`, `Istim = self.stimuli.apply(t)/100`; `Cm = 0.01`, `Chi = 140`, `theta = 0.5`); `torchcor/probe.py` on the openCARP meshes: L2 4.08e-3, 1.98e-3, 6.51e-4, 1.76e-4 → orders 1.04, 1.61, 1.89 (`torchcor/convergence_N.txt`) |
| E6 | TorchCor's own MMS | `torchcor/verification/manufactured_2d.py` defines its own `Monodomain` loop with Dirichlet BCs |
| E7 | MonoAlg3D plugin points | `~/MonoAlg3D_C` at `cb7727ff` (clone by another agent; read only): `src/config/stim_config.h` (`SET_SPATIAL_STIM`), `src/ode_solver/ode_solver.c` (`solve_all_volumes_odes`: stim is on/off in time), `src/ode_solver/ode_solver.h` (`SOLVE_MODEL_ODES(..., real current_t, ...)`), `src/config/extra_data_config.h` (`SET_EXTRA_DATA(..., struct grid*, ...)`), `src/monodomain/monodomain_solver.c` (extra data set before `set_ode_initial_conditions_for_all_volumes`), `src/matrix_assembly_library/matrix_assembly.c` (`set_initial_conditions_from_odes`), `src/models_library/build.sh` (auto-adds any dir with `build.sh`); no "manufactured" anywhere in `src/` |
| E9 | residual gate works | `sympy/residual.py` (torchcor venv, sympy 1.14): all residuals 0 for 1D/2D/3D mono, bidomain parabolic and elliptic; `Beta` from sigma = -1.100000/-5.900000/-8.600000 (`residual_output.txt`) |
| E10 | 6-digit sigma floor | `python3 -c` on `pi^2*(0.111453+4*0.121585+9*0.0303964) - 8.6` = -1.56e-5; 9-digit -2.3e-8; `sweep_hex_convergence.json` of bidomain sets no conductivity |

## 7. Open questions for the owner

1. **Authority.** Do you accept the data file as the single definition, with
   cardiacFOAM as its native implementation, checked by the drift gate and the
   norm-agreement check? Or must the C++ remain primary? If it must, (b) needs
   an expression extractor; the gates would stay the same.
2. **Beta or sigma primary?** Beta reads as the round number. Should sigma be
   derived from it, and should the bidomain tutorial's sigma move to 9 digits?
3. **Your extensions** (anisotropic, conormal): are they in scope? The
   rotated-tensor case needs a source and, for conormal, periodic y and z. I
   have not checked periodic BCs in openCARP and MonoAlg3D.
4. **Bath on openCARP:** for the FE side, should it use the
   groundElectrode variant (a Dirichlet ground stimulus, simpler) or
   electrodePair?
5. **Scope:** bidomain and bath can be cross-discretisation only between
   openCARP (FE) and cardiacFOAM (FV), and monodomain across all four. Is that
   acceptable?
6. **The P&G PDF** should be read once against the data. Here
   the formulas trace through your code only.
