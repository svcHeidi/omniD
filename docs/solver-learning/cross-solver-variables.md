# What each variable means in cardiacFOAM and openCARP, and how they correspond

**Method:** [`method.md`](method.md). **Solver logs it draws on:**
[`cardiacfoam.md`](cardiacfoam.md) (S, Q, Y, Z, AA) and
[`opencarp.md`](opencarp.md) (F, G, J, M). **Date:** 2026-10-09.
**omniD:** the integration branch (`/tmp/od-int`, 23260845).

An agent used omniD, and only omniD's CLI, to find each solver's spelling of the
concepts the Niederer 2011 benchmark shares, then settled every physical mapping
by real runs through omniD: one perturbation per concept, run in both solvers
from their native Niederer configuration, judged by whether it moves the
activation times the same way in both. The agent wrote no omniD code. Where
omniD could not say something as data, the friction log records it, because
that is design input.

Runs, studies, requests and reports are under `<runs>/2026-10-09/varmap/`
(`studies/`, `runs/`, `requests/`, `reports/`, `discovery/` for every CLI
answer). Shells: `cf.sh` (sources OpenFOAM's bashrc, `DYLD_LIBRARY_PATH`,
`OMNIDRIVER_NATIVE_TUTORIALS`) and `oc.sh` (`DYLD_LIBRARY_PATH`,
`OPENCARP_MPI_BIN` first on `PATH`, `HYDRA_IFACE=lo0`); the two MPIs never
share a shell. cardiacFOAM: `--repo` the 2026-10-09 tree, record `niederer2011`
(hex), binary older than the source (`stale_build`, expected). openCARP:
`--plugin opencarp --cases-root /usr/local/lib/opencarp/share/tutorials`, record
`niedererNVersion`.

## Setting

Every run: dx 0.5 mm, Δt 0.05 ms, end 300 ms, serial, one-row study through
`sweep-run`. openCARP keeps the record's native mass matrix (`mass_lumping`
unset, so the binary's default 1, lumped), because cardiacFOAM's finite volumes
behave like a lumped mass ([`cardiacfoam.md`](cardiacfoam.md) S4); one run sets
`mass_lumping 0`. Activation times P1–P9 are read with `omnidriver compare`, one
request per perturbation pairing openCARP with cardiacFOAM (request shape and
frame mapping from the threeway campaign: cardiacFOAM x = a, y = c,
z = 7 mm − b). Every value in this file is a `compare` report value; no solver
output was read by hand for a time.

**Baselines (ms).** openCARP lumped / cardiacFOAM:
P1 1.355 / 1.217, P2 112.75 / 132.93, P3 49.69 / 46.14, P5 26.74 / 36.08,
P7 56.16 / 56.24, P8 126.45 / 143.91, P9 55.78 / 66.26. At this dx both are far
from converged across the fibre (P8 is about 40 ms converged), so a 2× change
in a diffusion parameter does not give the continuum √2.

**The verdict criterion, and why.** A mapping is verified when the same
perturbation changes each solver's own baseline the same way: the ratio (or
shift) at the points the perturbation should move agrees between solvers to
within 10 %, and the points it should not move stay within 2 % in both. Why
10 %: at dx 0.5 mm the two discretisations (finite volumes at cell centres, P1
elements with a lumped mass at nodes) are both under-resolved, and the numerical
velocity depends on dx over the space constant differently in each; a semantic
mismatch (a key ignored, a factor 10 or 1000 of units, another formula) shows as
a ratio of 1.0 against about 1.8, or a factor of 2 or more, far outside 10 %.

## The table

| concept | cardiacFOAM (document:key, unit) | openCARP (`nversion.par:` key, unit) | relation | verified by (prediction → observed) | how omniD told me |
|---|---|---|---|---|---|
| conductivity, along fibre | `constant/electroProperties:monodomainSolverCoeffs.conductivity` xx, S/m (tensor in the global frame; native 0.13342) | `gregion[0].g_il` 0.17, `g_el` 0.62, S/m | cardiacFOAM takes the monodomain value; openCARP forms it as σiσe/(σi+σe) per direction (`bidm_eqv_mono` 1): 0.17·0.62/0.79 = 0.13342 | `sigl` (σl halved; cardiacFOAM xx 0.066709, openCARP g_il 0.085, g_el 0.31): P3 ×1.714 oc, ×1.796 cf; P7 ×1.559 / ×1.507; P2, P5 move ≤ 2.3 % / 1.2 %. **Verified** (4.8 %, 3.4 %) | DATA key and unit for both. Formation: openCARP PROSE (`bidm_eqv_mono` "equivalent to the bidomain"; no formula); cardiacFOAM NOTHING (the description says "monodomain conductivity tensor", not that it is σiσe/(σi+σe), nor in which frame). The tensor's frame and component order: NOTHING (native file and `cardiacfoam.md` S) |
| conductivity, across fibre | same tensor, yy and zz (0.017606) | `g_it`, `g_in` 0.019; `g_et`, `g_en` 0.24 | as above; `n` = sheet normal, transversely isotropic here (`opencarp.md` M3) | `sigl` leaves them unchanged and the transverse points stay (above). No run of its own | as above |
| surface-to-volume ratio χ | `…chi`, 1/m, 140000 | `imp_region[0].cellSurfVolRatio`, µm⁻¹, 0.14 | χ[1/m] = 10⁶ · ratio[µm⁻¹] | `sigma2` (χ×2: 280000 / 0.28): P3 ×1.835 oc, ×1.800 cf (1.9 %); every transverse point not reached by 300 ms in both. **Verified** for the diffusion term. P1: oc unchanged (−0.001 ms), cf +0.881 ms: see the stimulus row | DATA (key, unit, both). That χ also scales cardiacFOAM's stimulus and not openCARP's: NOTHING |
| membrane capacitance Cm | `…cm`, F/m², 0.01 | none: fixed 1 µF/cm² in the binary (`opencarp.md` J2) | 0.01 F/m² = 1 µF/cm². In cardiacFOAM χ and Cm enter only as the product χ·Cm | `cm2` against `chi2` in cardiacFOAM: all nine values identical to the last printed digit (`cf_chi2_vs_cm2`). openCARP cannot be perturbed; χ×2 there is the same perturbation of χ·Cm, verified above | cardiacFOAM DATA. openCARP NOTHING: no key, and omniD does not say Cm is fixed. Not to be confused with the ionic models' cell capacitance (`Cm` in cardiacFOAM's TNNP constants, `CAPACITANCE 0.185` in openCARP's), which `catalog --named ionic_model_catalog` lists without saying what it is |
| ionic model | `…ionicModel` `TNNPcompactBatched` (menu, DATA) | `imp_region[0].im` `tenTusscherPanfilov` (free string, no menu) | **not the same model**: cardiacFOAM's TNNP is ten Tusscher 2004 (17 states incl. `g`, `fCa`; no `CaSS`); openCARP's is ten Tusscher–Panfilov 2006 (`bench --imp-info`: "Year: 2006", states incl. `CaSS`, `CaSR`). Owner decision 2026-09-28: 2004 is intended (`cardiacfoam.md` S) | Activation times cannot separate them (shared I_Na, I_K1; `cardiacfoam.md` S3). Not re-run | cardiacFOAM: `catalog --named ionic_model_catalog --item TNNP` gives the state list (DATA, 17 states) **and** the description "21-state … (ten Tusscher & Panfilov 2006)" with aliases TT04 and TT06 (PROSE that contradicts its own data). openCARP: NOTHING (no named catalog; the description sends you to `bench --list-imps`) |
| cell type | `…tissue` `epicardialCells` (menu) | `imp_region[0].im_param` `"flags=EPI"` | epicardial in each model | not perturbed: LATs do not separate cell types | cardiacFOAM DATA (menu). openCARP NOTHING: `im_param` is a free string whose description's example is not a flag; `flags` and its values `EPI|MCELL|ENDO` only from `bench --imp-info` |
| stimulus strength | `…externalStimulus.stimulusIntensity`, A/m³ (= µA/cm³), 50000 | `stim[0].pulse.strength`, µA/cm² of membrane, 35.71 | strength_oc[µA/cm²] = I_cf[A/m³] / (χ[1/m]/100) = 50000/1400. **The conversion depends on χ**: cardiacFOAM's stimulus is per tissue volume, openCARP's per membrane area | `stim2` (×2): P1 −0.515 oc, −0.485 cf; far points −0.7 to −5.3 ms in both. `sigma2`: P1 moves only in cardiacFOAM (+0.881). `beta2half` (openCARP β×2 with strength halved, the cardiacFOAM χ×2 equivalent): P1 +0.956 against cf +0.881 (8 %), P3 ×1.862 / ×1.800. **Verified, including the χ dependence** | cardiacFOAM DATA (A/m³). openCARP PROSE that misleads: the unit is "uA/cm^2(2D current), uA/cm^3(3D current), or mV"; in this 3D slab it behaves as per-area, which only the χ×2 run showed |
| stimulus duration | `…externalStimulus.stimulusDuration`, s, 2e-3 | `stim[0].ptcl.duration`, ms, 2 | seconds ↔ ms; cardiacFOAM includes the end step (`cardiacfoam.md` S) | not perturbed (start and strength cover the protocol units) | DATA both |
| stimulus start | `…externalStimulus.stimulusStartTime`, **no unit given** (s) | `stim[0].ptcl.start`, ms | s ↔ ms | `start5` (0.005 s / 5 ms): oc +5.000 at P1, +4.84…+4.95 elsewhere; cf +5.10 at P1, +5.26…+5.86 elsewhere. **Verified** units; cardiacFOAM's extra 0.1–0.9 ms is its −84 mV initial state relaxing for 5 ms before the stimulus (openCARP starts from `singlecell.sv`) | cardiacFOAM: unit empty (sibling `stimulusDuration` says s). openCARP DATA |
| stimulus region | `…stimulusLocationMin/Max`, **no unit** (m, mesh frame): (0, 0, 5.5) to (1.5, 1.5, 7) mm | `stim[0].elec.p0[i]/p1[i]`, µm: 0 to 1500 each | the same 1.5 mm cube at P1 in each frame; cardiacFOAM selects 27 cell centres, openCARP 64 nodes (`cardiacfoam.md` S) | the baseline P1 (1.355 / 1.217) | cardiacFOAM: unit empty. openCARP DATA. Frame: agent reasoning (by design) |
| time step | `system/controlDict:deltaT`, s | `dt`, µs | 5e-5 s = 50 µs | each baseline: cardiacFOAM 6000 steps to 0.3 s; openCARP 20 ODE calls per ms (`ODE_stats.dat`), 300 ms | DATA both |
| end time | `system/controlDict:endTime`, s | `tend`, ms | s ↔ ms | as above | DATA both |
| spatial resolution | axis `dx`, m | axis `dx`, µm | 0.0005 ↔ 500 | baseline meshes: 3360 cells (40×6×14); 4305 nodes (41×15×7) | NOTHING: `describe` gives each axis `name` and `value_kind` only; the unit is in openCARP's guidance prose and in cardiacFOAM's native study values |
| activation threshold / LAT | `…activationThreshold`, V (unit field empty; description says "(V)"), default 0; upward crossing, linear in the step, **last** crossing (`cardiacfoam.md` Q2) | `lats[0].threshold`, mV (unit empty; `actthresh` beside it has mV), method 1 = threshold crossing, `all 0` = first | V ↔ mV | `thr` (−0.04 V / −40 mV): every point earlier by 0.165–0.208 ms cf, 0.178–0.258 ms oc. **Verified** (same sign, size within the upstroke time from −40 to 0 mV) | cardiacFOAM PROSE (unit only in the description). openCARP PROSE (unit absent on this key) |
| mass matrix | none: finite volumes (diagonal) | `mass_lumping`, default 1 | cardiacFOAM FV ≈ openCARP lumped at this dx | `lump0`: openCARP full mass P8 58.83 vs lumped 126.45; cardiacFOAM 143.91 sits with lumped | openCARP DATA. cardiacFOAM NOTHING (no key; the correspondence is reasoning plus `cardiacfoam.md` S4) |
| PDE time scheme | `…solutionAlgorithm` implicit\|explicit; `system/fvSchemes:ddtSchemes` `backward`; `…timeCouplingScheme` godunov (default) | `parab_solve` 1 (Crank–Nicolson), `theta` 0.5 | same role, not equivalent | `explicit` (cf `explicit`, oc `parab_solve 0`): cf +0.2…+1.4 ms, oc −0.2…−0.75 ms. Both under 1.5 ms, **opposite signs**: each solver's own scheme, not a mapping | cardiacFOAM DATA (menu, description) for two keys; `fvSchemes` is not catalogued (NOTHING on how `ddtSchemes` interacts with `godunov`). openCARP PROSE (`parab_solve` "solution method" with integer codes in the description) |
| ionic integrator | `…batchedIntegrator` `rushLarsen`, `batchedSubsteps` | none (the IMP's own: Rush–Larsen gates, lookup tables, `opencarp.md` J) | same family | not run | cardiacFOAM DATA. openCARP NOTHING |
| initial state | none: −84 mV everywhere (domain default) | `-imp_region[0].im_sv_init singlecell.sv` on the record's command line | **differ** (`cardiacfoam.md` S5): visible in `start5` | `start5` above | NOTHING in either |
| output sampling | activation field probed by `system/Niedererpoints` (`interpolationScheme cellPoint`) | per-node LAT file, `compare` interpolates linearly in the containing tet | both evaluate a field at the point; the readers report `sampling_offset` 0 | every report | openCARP DATA (guidance prose plus the report's `sampling_rule`). cardiacFOAM: probes not catalogued |

## Mappings that failed verification

None of the physical mappings failed. Two correspondences are **not**
one-to-one and would mislead an agent that maps keys by name:

1. **Stimulus strength is not a unit conversion alone.** cardiacFOAM's
   `stimulusIntensity` is current per tissue volume; openCARP's `pulse.strength`
   is current per membrane area. The conversion divides by χ, so changing χ in
   both solvers changes the stimulus in cardiacFOAM only. Settled by
   `sigma2` (P1 moves in cardiacFOAM only) and `beta2half` (scaling openCARP's
   strength by 1/2 with β×2 reproduces cardiacFOAM's P1, 8 %).
2. **The ionic model differs** (TNNP 2004 against TT 2006), as already recorded
   in `cardiacfoam.md` S; the owner chose 2004. LATs cannot show it.

## Friction log

Each line: what I needed, what omniD gave (DATA / PROSE / NOTHING), where I went.

1. **The native case's current values: NOTHING.** `describe`, `catalog` and
   `plan --strict` list every key a case may take, with type, unit, default and
   `typical_value`, but never the value the record's case has now. The baseline
   conductivity, χ, stimulus box and model came from reading
   `constant/electroProperties` and `nversion.par` directly. A
   `plan --strict` `configuration_evidence` lists the files it inspected, not
   their values.
2. **How each solver forms the monodomain conductivity: NOTHING / PROSE.**
   cardiacFOAM's entry says "Monodomain conductivity tensor"; openCARP's
   `bidm_eqv_mono` says "Use monodomain conductivities that are equivalent to
   the bidomain". Neither says harmonic mean per direction, and cardiacFOAM
   does not say the tensor is (xx xy xz yy yz zz) in the mesh frame. Both from
   `cardiacfoam.md` S, which read the C++.
3. **What a stimulus strength is per: PROSE that misleads.** openCARP's unit is
   "uA/cm^2(2D current), uA/cm^3(3D current), or mV". In a 3D slab the value
   35.71 is per membrane area; only a run (χ×2) showed it.
4. **Units missing on keys that have one.** cardiacFOAM `activationThreshold`
   (V, said only in the description), `stimulusStartTime` (s),
   `stimulusLocationMin/Max` (m); openCARP `lats[0].threshold` (mV),
   `t_sentinel`. The `dx` axis of both records has no unit (cardiacFOAM m,
   openCARP µm): `describe` gives axes `name` and `value_kind` only.
5. **openCARP's ionic model: NOTHING.** No named catalog (`the stack has []`),
   `imp_region[].im` is a free string with no menu, and the cell type lives in
   the free string `im_param` (`flags=EPI`). Model year, states and flags came
   from `bench --imp-info`. Cm being fixed at 1 µF/cm² is said nowhere.
6. **cardiacFOAM's ionic catalog contradicts itself.** `TNNP`: description
   "21-state … ten Tusscher & Panfilov 2006", aliases `TT04` and `TT06`, and a
   17-state list with `g` and `fCa` (2004). The data is right, the prose wrong.
7. **Dimensioned values: the note says one form, the validator demands
   another.** The entries for `conductivity` and `stimulusIntensity` say "best
   overridden with a full OpenFOAM literal string"; `sweep-plan` refuses the
   literal ("must be a mapping with value and dimensions"). The mapping
   `{"value": [...], "dimensions": [...]}` is accepted; its member names were
   guessed. Meanwhile `chi`, dimensioned in the native file, is catalogued as a
   plain `scalar` and written as `chi 280000;` (dimensions dropped; the run was
   correct).
8. **Which keys are the same concept across solvers: NOTHING, by design?**
   Not frame alignment, which is agent reasoning; but a concept tag (say
   `surface_to_volume_ratio`) on each entry would have turned this whole
   discovery into a join. Without it, the join was by reading descriptions.
9. **openCARP `parab_solve`, `mass_lumping`: integer codes with meanings in
   prose.** No menu with labels.
10. Minor: `catalog --document --key` needs `--entry` even for a
    document-level question; `env` output is polluted by the OpenFOAM bashrc
    printing to stdout (redirect it in the shell); `cardiacFOAM` `fvSchemes`
    and the probe dictionaries are not catalogued, so the PDE time derivative
    and the probe interpolation are invisible.

## Probes

| # | command | observed | conclusion |
|---|---|---|---|
| V1 | `describe --repo <tree> --entry niederer2011`; `describe --plugin opencarp --cases-root … --entry niedererNVersion` (`discovery/*-describe.json`, `*-keys.txt`) | 167 cardiacFOAM keys (15 omitted by `applicable_when`), 2 axes; openCARP ~280 `nversion.par` keys from `+Help`, 2 axes | every key of the table found; units DATA on most, missing on the keys of friction 4 |
| V2 | `catalog --entry niederer2011 --document constant/electroProperties --key …conductivity`; `catalog --named ionic_model_catalog --item TNNP`, `--item TNNPcompactBatched` | entry as in V1; TNNP: 17 states, description "21-state … 2006"; compactBatched `same_model_as: TNNP` | friction 6 |
| V3 | `catalog --plugin opencarp --named x`; `catalog … --key 'imp_region[0].im'` | `the stack has []`; free string, default `LuoRudy91`, "Query … by calling 'bench'" | friction 5 |
| V4 | `plan --strict` on both records (`discovery/*-plan.json`) | both `ok`; cardiacFOAM 5 `stale_build` warnings, scanner notes (one catalogue disagreement on `purkinjeFibreRadius`, not this case); no case values anywhere | friction 1 |
| V5 | `bench --imp=tenTusscherPanfilov --imp-info` (outside omniD) | "Year: 2006", `CAPACITANCE 0.185`, `flags EPI|MCELL|ENDO`, states incl. `CaSR`, `CaSS` | openCARP runs TT 2006 |
| V6 | `sweep-plan` of `cf_sigl`, `cf_stim2` with literal strings | refused: "does not fit catalogued value_kind 'dimensioned_tensor': must be a mapping with value and dimensions" | friction 7; mapping form accepted, written as `[-1 -3 3 0 0 2 0] (0.06670886075 …)` |
| V7 | `sweep-run` of 8 openCARP and 8 cardiacFOAM one-row studies, plus `oc_beta2half`; `compare` per pair (`reports/oc_vs_cf_*.json`) | all `completed`; values in the table | each mapping's verdict above |
| V8 | `compare` `cf_chi2_vs_cm2` | identical at P1 and P3 (2.09761, 83.0716 ms), the rest not reached in both | χ and Cm enter cardiacFOAM only as χ·Cm, including the stimulus; the ionic term then cannot depend on `cm` alone (consistent with the catalogued `Iion_cm`, a current per capacitance; inferred, not read in the C++) |
| V9 | `compare` `oc_lumped_vs_full` | P8 126.45 lumped, 58.83 full; P3 49.69 / 33.32 | the native record runs lumped (`mass_lumping` default 1); cardiacFOAM's 143.9 sits with lumped |
| V10 | the `cf_start5` wall time (786 s against 42 s); its solve log | for the 101 steps before and at the stimulus onset (t ≤ 5.05 ms) every step runs all 1000 `nOuterCorrectors`: the `Vm` residual alternates between 1.15574e-3 and 1.15759e-3 and never reaches `tolerance 1e-6`. Base and `thr` (stimulus at 0) never hit 1000 | **cardiacFOAM native behaviour**: a quiescent tissue relaxing from −84 mV never meets PIMPLE's residual control, so pre-stimulus time costs about 7.5 s a step at this mesh. The results are unaffected (shift as predicted); the cost is not. For `docs/solver-learning/cardiacfoam.md`, and a reason a study should not delay its stimulus |
| V11 | openCARP `out/ODE_stats.dat`, `vm.igb` header; cardiacFOAM step count | 20 ODE calls per ms, `T size 300 ms`; 6000 steps to 0.3 s | `dt` µs, `tend` ms; `deltaT`, `endTime` s, as the units say |

**Run count and wall time.** 17 solver runs (openCARP 9, cardiacFOAM 8) and 9
`compare` reports. openCARP 3–6 s per run (51 s in all); cardiacFOAM 28–43 s
per run except `start5` (786 s, V10): 1068 s in all.
