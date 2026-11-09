# Niederer 2011 N-version benchmark

`../niederer2011.json` is the reference: the paper's activation times at P1-P9
(milliseconds; 20 x 7 x 3 mm slab, P1 at the stimulated corner). Studies are
JSON; a zip study's lists are rows, so one level is the row at one index.

| solver | study or record | Δx | Δt | end time |
|---|---|---|---|---|
| cardiacFOAM | native `benchmarks/NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json`, entry `niederer2011` | `dx`, m | `system/controlDict:deltaT`, s | `system/controlDict:endTime`, s |
| openCARP | `studies/opencarp_cartesianConvergence.json`, entry `niedererNVersion` (here because openCARP's tutorials are a read-only install) | `dx`, µm | `nversion.par:dt`, µs | `nversion.par:tend`, ms |
| TorchCor | its cases repository's `nversion` (`oblique/torchcor_obliqueWall.json` shows the keys) | `case.json:dx_mm`, mm | `case.json:dt_ms`, ms | `case.json:t_end_ms`, ms |

The grid is Δx 0.5, 0.2, 0.1 mm by Δt 0.05, 0.01, 0.005 ms, with end times of
200, 80 and 55 ms per Δx so every point activates. The openCARP study sets
`nversion.par:mass_lumping 0`; the binary's default is lumped.

## Probes

cardiacFOAM reads `probeLocations` in `system/Niedererpoints` (m): probe k is
P(k+1), with x = a, y = c, z = 7 mm - b of the reference frame. openCARP and
TorchCor use the reference's own coordinates. The requests state each side's
points and `max_sampling_offset`.

## Pre-registered comparison requests

`preregistered/requests/` holds 21 comparison requests, fixed before any
campaign run: 9 `cross_*` (openCARP against cardiacFOAM per level, 5 ms) and
12 `temporal_*` (successive Δt of one solver, 1 ms). Tolerances and their
rationale are in each file. **Do not edit them:** `SHA256SUMS` beside them
records what was fixed, and a changed request is a new request. They sit three
folders below `benchmarks/` so their `reference` (`../../../niederer2011.json`)
resolves. Each names its runs by relative `sweep_output`
(`../runs/<solver>/cartesianConvergence/dx<mm>`), resolved against the request's
folder. Run one after both sweeps are done:

```bash
omnidriver compare --comparison-request preregistered/requests/cross_dx0.5_dt0.01.json --report <report.json>
```

A report is written once. `scripts/check-benchmark-references.py` checks the
digests and that each `reference` resolves.
