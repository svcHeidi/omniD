# Niederer 2011 with the fibre at 45°: openCARP and TorchCor

cardiacFOAM's native `obliqueWall` study rotates the slab's conductivity 45° in
its x–y plane. These two files pose the same physical problem to openCARP and
TorchCor, on the campaign's grid (Δx 0.5, 0.2, 0.1 mm × Δt 0.05, 0.01,
0.005 ms; end times 200, 80 and 75 ms, the oblique study's).

| file | solver | what it changes in the native case |
|---|---|---|
| `opencarp_obliqueWall.json` | openCARP `niedererNVersion` | `fibers.imbrication 90` (mesher), `mass_lumping 0` as the campaign |
| `torchcor_obliqueWall.json` | TorchCor `nversion` (`--repo` the TorchCor cases repository) | `case.json:fibre` (1, 0, 1)/√2 |
| cardiacFOAM's like-for-like study | `godunov_AB`: `godunov_0` with `sealedHeartBoundary true`, `sealedWallTrace conormal`, so its walls carry no flux as the FE walls do | |
| cardiacFOAM's native-wall study | the native `NiedererEtAl2011verification/setup/studies/obliqueWall/sweep_hex_oblique_godunov_0.json`, **not copied** | |

## The same fibre in each frame

cardiacFOAM's slab is 20 (x) × 3 (y) × 7 (z) mm with P1 at (0, 0, 7) mm;
openCARP's and TorchCor's is 20 × 7 × 3 mm with P1 at the origin, the frame of
`benchmarks/niederer2011.json`. A point maps as x_f = x_c, y_f = z_c,
z_f = 7 mm − y_c (f cardiacFOAM, c openCARP/TorchCor; determinant +1), so a
direction (a, b, c) in the reference frame is (a, c, −b) in cardiacFOAM's.

The native tensor is R(45°) diag(σl, σt, σt) Rᵀ with σxy = (σl − σt)/2 > 0:
the fibre is (1, 1, 0)/√2 in cardiacFOAM's frame, rising from the stimulus
corner into the 3 mm. In the reference frame that is **(1, 0, 1)/√2**: +45°
from +x towards +z, in the 20 × 3 mm x–z face that holds P1, P3, P5 and P7. The
sign matters: (1, 0, −1)/√2 is another problem (`docs/solver-learning/opencarp.md` M).

- **openCARP** takes the fibre from the `.lon` file `mesher` writes. mesher tilts
  the fibre out of its x–y plane by atan(sin(imbrication)), so `-fibers.imbrication 90`
  writes exactly (0.707107, 0, 0.707107), with a sheet (−0.707107, 0, 0.707107).
  `nversion.par` sets `g_in` = `g_it` and `g_en` = `g_et`, so the sheet changes nothing.
  The record's `fibers.imbrication` axis passes it; no file is rewritten.
- **TorchCor**'s runner writes the `case.json` key `fibre` as every `.lon` row and
  forms σt I + (σl − σt) f fᵀ from the harmonic means, as openCARP does.
- **cardiacFOAM** takes the full tensor. Compare openCARP and TorchCor against
  **`godunov_AB`**, the like-for-like study: sealed walls with the `conormal`
  trace, its counterpart of the FE natural condition. `godunov_0` is the
  native-wall variant (`sealedHeartBoundary false`, `zeroGradient`, the C++
  default coupling `godunov`); both change one other thing from the native
  case, `ddtSchemes Euler` against the native `backward`, which at Δx 0.5 mm,
  Δt 0.01 ms moves the aligned corners by at most 0.48 ms
  (`docs/solver-learning/cardiacfoam.md` AA).

**The wall is not the same problem in `godunov_0`.** openCARP and TorchCor apply
the finite-element natural condition, no flux n·σ∇V = 0. `zeroGradient`
(n·∇V = 0) admits a front uniform across cardiacFOAM's 3 mm, so under oblique
conductivity `godunov_0` gives P3 = P7 and P4 = P8 exactly (AA3), where
openCARP and TorchCor keep P7 3.6-5.2 ms ahead of P3. Its agreement at those
corners is therefore not evidence of anything; read `godunov_AB`, which
restores the ordering (AA4).

## Running one level

As the campaign: slice a level with `../campaign/level_study.py`, then run it
from the solver's own shell (`omnidriver env --plugin <p>`).

```bash
python3 ../campaign/level_study.py --study opencarp_obliqueWall.json \
  --cases-root <openCARP>/share/tutorials --where dx=200.0 --where nversion.par:dt=10.0 --out oc.json
omnidriver sweep-run --plugin opencarp --spec oc.json --output-dir <out> --scratch-dir <scratch>

python3 ../campaign/level_study.py --study torchcor_obliqueWall.json \
  --cases-root <torchcor-cases>/cases --where case.json:dx_mm=0.2 --where case.json:dt_ms=0.01 --out tc.json
omnidriver sweep-run --plugin torchcor --repo <torchcor-cases> --spec tc.json --output-dir <out> --scratch-dir <scratch>
```

Read P1–P9 with `omnidriver compare`, a request per pair shaped as the
campaign's `cross_*.json`; the points stay those of `niederer2011.json`, each
in its solver's frame. The rotation moves no point.
