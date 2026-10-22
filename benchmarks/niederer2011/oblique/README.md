# Niederer 2011 with the fibre at 45°: openCARP and TorchCor

These two files pose the Niederer slab with its fibre rotated 45° to openCARP
and TorchCor, on the campaign's grid (Δx 0.5, 0.2, 0.1 mm × Δt 0.05, 0.01,
0.005 ms; end times 200, 80 and 75 ms).

| file | solver | what it changes in the native case |
|---|---|---|
| `opencarp_obliqueWall.json` | openCARP `niedererNVersion` | `fibers.imbrication 90` (mesher), `mass_lumping 0` as the campaign |
| `torchcor_obliqueWall.json` | TorchCor `nversion` (`--repo` the TorchCor cases repository) | `case.json:fibre` (1, 0, 1)/√2 |

**cardiacFOAM has no counterpart.** Its native `obliqueWall` study was removed
pending its redesign (the owner's decision D1): every arm of it set a wall
trace the sealed-wall design no longer reads. When a study under
`sealedHeartBoundary` and `sealedWallLeastSquares` returns, it is compared
here; until then these two files compare openCARP with TorchCor only.

## The fibre

The fibre is **(1, 0, 1)/√2** in the frame of `benchmarks/niederer2011.json`
(20 × 7 × 3 mm, P1 at the origin): +45° from +x towards +z, in the 20 × 3 mm
x–z face that holds P1, P3, P5 and P7. The sign matters: (1, 0, −1)/√2 is
another problem, and it orders P3 and P7 the other way
(`docs/solver-learning/opencarp.md` M7, M9).

- **openCARP** takes the fibre from the `.lon` file `mesher` writes. mesher tilts
  the fibre out of its x–y plane by atan(sin(imbrication)), so `-fibers.imbrication 90`
  writes exactly (0.707107, 0, 0.707107), with a sheet (−0.707107, 0, 0.707107).
  `nversion.par` sets `g_in` = `g_it` and `g_en` = `g_et`, so the sheet changes nothing.
  The record's `fibers.imbrication` axis passes it; no file is rewritten.
- **TorchCor**'s runner writes the `case.json` key `fibre` as every `.lon` row and
  forms σt I + (σl − σt) f fᵀ from the harmonic means, as openCARP does.

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
campaign's `cross_*.json`; the points stay those of `niederer2011.json`. The
rotation moves no point.
