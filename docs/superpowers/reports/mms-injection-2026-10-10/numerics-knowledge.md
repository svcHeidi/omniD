# Where numerics knowledge lives in omniD, and where it should

Read-only investigation, 2026-10-10. omniD at `integration/2026-10-09`
(worktree `.claude/worktrees/integration`, venv `/tmp/od-int`). Nothing in any
repository was changed. Raw outputs sit next to this file.

## 1. Today's state

| solver | knob | where | form |
|---|---|---|---|
| OpenFOAM family (cardiacFOAM, cardiacCore) | `system/fvSchemes` (grad, div, laplacian, snGrad, interpolation, ddt) | nowhere: `describe`/`catalog` list `{"document":"system/fvSchemes","key":"<any>","validated":false}` | **missing**. The guidance prose for both plugins says "omniD has no catalogue of OpenFOAM's keys" |
| same | `system/fvSolution` (linear solvers, `nOuterCorrectors`, `nNonOrthogonalCorrectors`) | same `<any>`, `validated:false` | **missing** |
| same | formal order of any scheme | nowhere | **missing** |
| same | ddt stability limit (`Euler` 2, `backward` 4 for `rate*dt`) | `omnidriver.cardiacfoam.validation._DDT_STABILITY_LIMIT` | **data, in the wrong package**: a property of OpenFOAM's ddt schemes, held by cardiacFOAM, so cardiacCore cannot reach it (breaks "one reality") |
| same | `ODESolver` (`solver` key: `RKF45`, `Euler`) | cardiacFOAM catalogue entry, menu curated to 2 names; `dict_key_allowlist.json` classifies it `not_runtime_selected: "OpenFOAM ODESolver"` | data (menu), but never compared with OpenFOAM's table (13 names); no order |
| cardiacFOAM | `timeCouplingScheme` godunov/sbdf2 | catalogue entry, menu + source_refs | menu is data; **orders are prose** in the description ("godunov is first-order Lie splitting; sbdf2 is second-order ...") |
| cardiacFOAM | `solutionAlgorithm` implicit/explicit | catalogue entry | menu data; "operator-split forward-Euler" is prose; no order |
| cardiacFOAM | `batchedIntegrator` euler/rushLarsen, `batchedSubsteps` | catalogue entries | menu/default data; no order |
| cardiacFOAM | `electrophysicsAdvanceScheme` (staggered only) | catalogue, RTST-checked | menu data; staggering order not stated |
| cardiacFOAM | how `ddt(Vm)` composes with `timeCouplingScheme` | nowhere | **missing** (also noted in `docs/solver-learning/cross-solver-variables.md` item 10) |
| cardiacCore | any numerics | nothing in its catalogues | missing (its solves are OpenFOAM `fvSchemes` too) |
| openCARP | `parab_solve`, `theta`, `mass_lumping`, `operator_splitting`, `ode_fac`, `dt` | `opencarp_parameters.json` (generated from `+Help`) | menu/bounds/default are data, **but menu labels are dropped**: `+Help parab_solve` prints `2 "2nd order dt"`, `1 "Crank-Nicolson"`, `0 "Explicit"`; the catalogue holds `["2","1","0"]`. `catalog_generation._MENU_ITEM` captures the label as group 3 and discards it |
| openCARP | element order (P1), ionic integration (per IMP, Rush–Larsen in limpet) | not keys; `docs/solver-learning/opencarp.md` J | prose / missing |
| TorchCor | `theta`, `mass_lumping`, `dtype`, `cg.*` | `torchcor-cases/scripts/run_case.py` `KEYS`, via `--describe` | data with descriptions; "1 implicit Euler, 0.5 Crank–Nicolson" is prose; element order (P1 tets) and ionic integrator absent |

### What the manufactured cases actually use (cardiacFOAM tree, all hex blockMesh by default)

| case | ddt(Vm) | grad | laplacian | snGrad | interp | solver keys |
|---|---|---|---|---|---|---|
| monodomain1D3D | backward | Gauss linear | Gauss linear corrected | corrected | linear | implicit, RKF45, godunov (default), nNonOrth 1 |
| bidomain | backward | leastSquares | Gauss linear corrected | corrected | linear | implicit, RKF45, **sbdf2**, nOuter 2, nNonOrth 0; div `Gauss linear` |
| bathBidomain | backward | leastSquares | Gauss linear corrected | corrected | linear | implicit, RKF45, godunov |
| monodomainPseudoECG | backward | leastSquares | Gauss linear corrected | corrected | linear | implicit, RKF45, godunov |
| eikonalECG | none (steady) | leastSquares | Gauss linear corrected | corrected | linear | div `Gauss linear` for `phiU,activationTime`; PBiCGStab |

The bidomain `fvSchemes` itself carries order in comments (`//default backward; // 2nd order`, `// default Euler; // 1st order`): prose in a native file.

Source evidence on composition (`monodomainSolver::solveDiffusionImplicit`):
the PDE is `chi*Cm*fvm::ddt(Vm) == fvm::laplacian(...) - chi*Cm*Iion*`, where
`Iion*` is the linear extrapolation `Iion_old + r(Iion_old - Iion_oldold)`
when the old-old current exists (sbdf2), else the current `Iion`. So the
effective time order is a composition of OpenFOAM's `ddt(Vm)` scheme and
cardiacFOAM's coupling: `backward` + godunov is limited to first order by the
split, `backward` + sbdf2 is the second-order pair. That composition is a
cardiacFOAM fact settled by its C++, not by OpenFOAM.

## 2. Scanner probe (OpenFOAM v2412 `src/` exists)

How C++ is supplied today: `cxx_mapping.source_root` in a plugin's
`plugin.yaml` (cardiacFOAM: `$OMNIDRIVER_NATIVE_TUTORIALS/../src`) — one root,
the solver's own. OpenFOAM's `src` is never scanned. Probe: the scanner's own
regex pass (`rtst_scanner.scan_rtst_registrations` over
`dict_keys_scanner.source_files`, comments stripped), no code changed
(`probe_rtst.py`, `probe_rtst.out`, `probe_ode.out`).

- `src/finiteVolume` (1257 files, 0.8 s): 8 bases found (`fvPatch`,
  `fvGeometryScheme`, `porosityModel`, ...), **0 scheme bases**.
- `src/ODE`: `ODESolver` with all 13 names (`Euler, EulerSI, RKCK45, RKDP45,
  RKF45, Rosenbrock12/23/34, SIBS, Trapezoid, rodas23, rodas34, seulex`). Works,
  because these use `addToRunTimeSelectionTable` directly and the class name
  equals the `TypeName`.

Why the schemes are missed (two gaps, both mechanical):
1. **Registration through macros.** Schemes register via `makeFvGradScheme(gaussGrad)`,
   `makeFvDdtScheme(backwardDdtScheme)`, `makeSnGradScheme`, `makeSurfaceInterpolationScheme`,
   `makeLimitedSurfaceInterpolationScheme`, ... (31 macro families found). The
   `addToRunTimeSelectionTable` is inside the `#define` in a `.H`, and the scan reads registrations only from `.C`.
2. **Registered name is `TypeName("...")`, not the class.** `gaussGrad` registers as
   `Gauss`, `leastSquaresGrad` as `leastSquares`, `correctedSnGrad` as `corrected`,
   `backwardDdtScheme` as `backward`. The scanner maps only `OverrideTypeName`.

A macro-aware pass (match `make\w*Scheme\s*\(\s*(\w+)` in `.C`, then the class's
`TypeName` in its `.H`) recovers per category: ddt 8 (`CoEuler, CrankNicolson,
Euler, SLTS, backward, bounded, localEuler, steadyState`), grad 7 + limited
(`Gauss, leastSquares, fourth, iterativeGauss, cellLimited, faceLimited, cellMDLimited, faceMDLimited`, plus `pointCellsLeastSquares`, `edgeCellsLeastSquares`),
laplacian 2 (`Gauss`, `relaxedNonOrthoGauss`), snGrad 7 (+2 fit), div 1 (`Gauss`),
interpolation about 80 (linear, upwind, linearUpwind, limited*, TVD/NVD ...).
Templated limiter schemes (`makeLLimitedSurfaceInterpolationTypeScheme(limitedVanLeer, ...)`)
register names built inside the macro; a few need the macro's own name argument.

**Formal orders are not in the code.** Some headers state them in their
`Description` comment (which the scanner strips): of typed headers, ddt 6/8,
grad 4/11, laplacian 2/2, div 1/1, snGrad 0/9, surfaceInterpolation 0/41
(e.g. `backwardDdtScheme.H`: "Second-order backward-differencing ddt",
`EulerDdtScheme.H`: "first-order Euler", `gaussGrad.H`: "Basic second-order
gradient scheme", `CrankNicolsonDdtScheme.H`: second-order only with
coefficient 1). The rest must come from literature (Jasak 1996 thesis;
Moukalled, Mangani & Darwish 2016) and be settled on our meshes by a run. They
are **curated data with a citation per value**, never scanned.

## 3. Proposal

Principle: the *names* come from the C++ (scanned, never typed); the *orders*
are curated facts, each with `settled_by` (a header line, a citation, or a
run id); combining them for a given case is the agent's reasoning, helped by
the composition rules the solver's own C++ settles.

### 3.1 No new core contract: `get_named_catalogs`

`get_named_catalogs` is already a `map` member; providers merge, and a duplicate
name is refused. Each layer contributes its own catalogue, named
`<owner>_numerics`; `omnidriver catalog --named openfoam_numerics --item ddt.backward`
already serves it. Core learns nothing. The verifier package reads every named
catalogue whose content says `"schema": "numerics/1"`; that small schema is
owned by `omnidriver-verifier` (documented there), and plugins depend on
nothing new. Rejected alternative: a `formal_order` field on core's
`DictEntry` — it would put a numerics concept in core, does not fit OpenFOAM's
scheme specs (a phrase like `Gauss linear corrected` is a grammar of three
tables, not one enum), and fvSchemes has no DictEntries anyway.

### 3.2 OpenFOAM schemes — `omnidriver-openfoam`, shared by cardiacFOAM and cardiacCore

`omnidriver/openfoam/numerics/openfoam_numerics.json`, served by the OpenFOAM
environment provider. Names validated against a scan of `$FOAM_SRC` (ambient
once the supplied `OPENFOAM_BASHRC` is sourced; declared where it is looked,
not searched), which needs the macro + `TypeName` pass of §2 added to
`rtst_scanner`. `_DDT_STABILITY_LIMIT` moves here (one source of truth), and
`ODESolver` too (it is OpenFOAM's table, not cardiacFOAM's).

```json
{"schema": "numerics/1", "owner": "openfoam", "foam_version": "v2412",
 "categories": {
  "ddtSchemes": {"base": "ddtScheme", "source": "src/finiteVolume/finiteVolume/ddtSchemes",
   "schemes": {
    "backward": {"class": "backwardDdtScheme", "arguments": [],
      "formal_order": {"time": 2},
      "conditions": ["constant deltaT; first step falls back to Euler"],
      "stability": {"linear_decay_rate_dt_max": 4},
      "settled_by": ["src: backwardDdtScheme.H Description 'Second-order backward-differencing'"]},
    "Euler": {"class": "EulerDdtScheme", "formal_order": {"time": 1},
      "stability": {"linear_decay_rate_dt_max": 2},
      "settled_by": ["src: EulerDdtScheme.H Description 'first-order Euler'"]}}},
  "snGradSchemes": {"schemes": {
    "corrected": {"formal_order": {"space": 2},
      "conditions": ["second order on non-orthogonal meshes with explicit correction; orthogonal hex: same as uncorrected"],
      "settled_by": ["citation: Jasak 1996, ch. 3 (to verify)", "run: <pending>"]}}}
 }}
```

A scheme phrase is parsed by the agent against the categories:
`laplacianSchemes: Gauss linear corrected` = laplacian `Gauss` + interpolation
`linear` + snGrad `corrected`; its spatial order is the minimum of the parts
under their `conditions`.

### 3.3 Solver-specific numerics — each plugin

**cardiacFOAM** contributes `cardiacfoam_numerics`, keyed by the catalogue's
`driver_path` and menu value (the entry still owns the menu; a test asserts
every keyed value is in the menu, so nothing is restated):

```json
{"schema": "numerics/1", "owner": "cardiacfoam",
 "keys": {"$ELECTRO_MODEL_COEFFS.timeCouplingScheme": {
   "godunov": {"formal_order": {"time": 1}, "role": "reaction-diffusion splitting",
     "composes": "time order = min(1, order of ddt(Vm))",
     "settled_by": ["src: monodomainSolver::solveDiffusionImplicit uses Iion at the current state"]},
   "sbdf2": {"formal_order": {"time": 2},
     "composes": "time order = min(2, order of ddt(Vm)); needs ddt(Vm) backward for 2",
     "settled_by": ["src: monodomainSolver::solveDiffusionImplicit extrapolates Iion linearly", "run: <pending>"]}}}}
```

The description prose ("godunov is first-order Lie splitting") then shortens
to what the key does, the order living only here.

**openCARP** contributes `opencarp_numerics` keyed by `.par` name. First fix
the generator so menu labels survive (`menu_labels` alongside `menu`, from
`+Help`), then:

```json
{"schema": "numerics/1", "owner": "opencarp",
 "keys": {"parab_solve": {
   "1": {"label_from_help": "Crank-Nicolson", "formal_order": {"time": 2},
     "conditions": ["theta = 0.5; otherwise 1"], "settled_by": ["+Help parab_solve", "run: <pending>"]},
   "0": {"label_from_help": "Explicit", "formal_order": {"time": 1}},
   "2": {"label_from_help": "2nd order dt", "formal_order": {"time": 2}}},
  "<element:P1>": {"formal_order": {"space": 2, "norm": "L2"}, "settled_by": ["citation: standard P1 FE theory", "run: <pending>"]}}}
```

**TorchCor** the same, keyed by the runner's `KEYS` (`theta` 1 → time 1,
0.5 → time 2; `mass_lumping`; element P1).

### 3.4 How an agent derives the expected order of a case

1. Read the case: `system/fvSchemes`, `fvSolution`, the solver keys (resolved
   values from `describe`/`plan`).
2. Look each value up: scheme phrases in `openfoam_numerics`, solver keys in
   `<plugin>_numerics`.
3. Apply the `composes` rules (data, from the solver's C++) and the
   `conditions` (data) to get the expected `{space, time}`.
4. **Agent reasoning, not data:** which norm and field the order applies to;
   mesh effects (non-orthogonality, skewness, tet versus hex, boundary
   treatment); interaction of corrector counts with order; ODE substepping
   tolerance floors; pre-asymptotic range; round-off at fine meshes (dtype).
   The verifier reports the expected order with the facts it used, the
   observed order, and the explanation.

Hex first fits this: on an orthogonal hex mesh most `conditions` drop out, so
the first entries needed are exactly what the manufactured cases use
(`backward`, `Euler`, `Gauss`, `leastSquares`, `linear`, `corrected`, laplacian
`Gauss`; `godunov`, `sbdf2`, `implicit`, `explicit`, `RKF45`).

## 4. Open questions for the owner

1. Is `$FOAM_SRC` (ambient after the supplied bashrc) an acceptable second C++
   root for the OpenFOAM layer, or must it be supplied explicitly as its own
   variable?
2. Extend `rtst_scanner` for the `make*Scheme` macros + `TypeName`? (§2; small,
   mechanical, needs fixtures from verbatim OpenFOAM snippets.)
3. Move `_DDT_STABILITY_LIMIT` and the `ODESolver` menu to the OpenFOAM layer?
4. Should fvSchemes/fvSolution ever become DictEntries (validated keys), or
   stay `<any>` with the numerics catalogue as the only knowledge?
5. What counts as `settled_by` for an order: a header comment, a citation, or
   only a run of ours? (The memory rule "fixtures can't settle external claims"
   suggests: header/citation = claimed, run = settled; record both.)
6. openCARP generator: keep `+Help` menu labels (`menu_labels`)? Today they are
   discarded.
7. Should cardiacFOAM's catalogue description prose lose its order statements
   once they live in `cardiacfoam_numerics`?

## Evidence (commands)

- `omnidriver describe --repo ~/omnid-runs/2026-10-09/cardiacfoam-tree --entry manufacturedMonodomain1D3D` → `describe_mono.json`: 165 keys; fvSchemes and fvSolution only as `<any>`, `validated:false`; numerics keys listed above.
- `omnidriver catalog ... --entry manufacturedMonodomain1D3D --document system/fvSchemes` → `catalog_fvschemes.json`: one `<any>` entry.
- `omnidriver catalog ... --named ionic_model_catalog --item TNNP` → named catalogues are served today.
- `probe_rtst.py` → `probe_rtst.out` (finiteVolume: 0 scheme bases; macro families listed); `probe_ode.out` (ODESolver 13 names).
- `grep TypeName / order` over `src/finiteVolume/{finiteVolume,interpolation}` (counts in §2).
- `openCARP +Help parab_solve|mass_lumping|operator_splitting|theta|ode_fac` → `opencarp_help.out` (labelled menus).
- `run_case.py --describe` (TorchCor) → `torchcor_describe.out`.
- `provider_stack._merge`: duplicate named-catalogue keys across providers are refused, hence `<owner>_numerics` names.
