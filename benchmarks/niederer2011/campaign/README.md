# Niederer 2011 campaign: openCARP against cardiacFOAM

Prepared 2026-09-27 for the owner to run on a cluster. This directory
holds the Cartesian benchmark over the paper's whole grid, for two
questions kept apart:

1. **Agreement.** The same problem on both solvers, compared per
   (Δx, Δt) level. The same reports also answer the owner's question
   about time steps: within one solver at a fixed Δx, are the Δt levels
   basically the same?
2. **Performance.** Equal MPI ranks, one thread per rank, each solver in
   its best accurate configuration. The solve's wall time is recorded
   apart from meshing, decomposition and post-processing. The protocol
   gives a scaling curve over a few rank counts, and time to accuracy.

The grid is Δx 0.5, 0.2, 0.1 mm × Δt 0.05, 0.01, 0.005 ms. The end
times are 200, 80 and 55 ms per Δx, which cardiacFOAM's native
`cartesianConvergence` study chose so every point activates.

Only the 0.5 mm level has run, on a workstation, as the proof ("The
proof", below). The finer levels are for the cluster.

## Layout

| path | what | written |
|---|---|---|
| `studies/opencarp_cartesianConvergence.json` | openCARP's study on the same 9-point grid: `dx` 500/200/100 µm, `nversion.par:dt` 50/10/5 µs, `nversion.par:tend` 200/80/55 ms, and `nversion.par:mass_lumping 0` | committed. It lives here because openCARP's tutorial tree is a read-only system install |
| cardiacFOAM's study | the native `NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json`, **not copied**. It runs `TNNPcompactBatched` with `rushLarsen`, the case's own setting (native `0489be3c`; `docs/solver-learning/cardiacfoam.md` T) | the native tree's |
| `requests/*.json`, `requests/SHA256SUMS` | the 21 pre-registered comparison requests and their digests | committed before any campaign run |
| `write_requests.py` | how the requests were typed: the tolerances, their rationale, the pairing and the offsets, in one place. `--check` confirms the committed files are what it writes | committed |
| `level_study.py` | writes one level's study from a zip study. It keeps the rows at one Δx (and optionally one Δt) and adds `base` keys such as the rank count. It never changes a value the study states | committed |
| `campaign.sh` | every command below | committed |
| `summarize.py` | tables from what the runs and reports record | committed |
| `runs/` | everything a run writes. **Make it a link to the cluster's scratch** (`ln -s $SCRATCH/niederer-campaign runs`). It is git-ignored | per machine |

Inside `runs/`:

```
runs/
  studies/<solver>_cartesianConvergence_dx<mm>[_dt<ms>]_np<N>.json   the level studies that ran
  <solver>/cartesianConvergence/dx<mm>/        one sweep per solver and Δx: the agreement runs
  perf/<solver>/dx<mm>_dt<ms>/np<N>/rep<r>/    one sweep per scaling point
  reports/<request name>.json                  one report per request, written once
  hosts/<time>-<solver>-<what>.txt             where each sweep ran (see "What is recorded")
  scratch/                                     omniD's staging (--scratch-dir)
```

**Why the requests need no fill-in step.** Every path in a request is
relative (`../../../niederer2011.json`, `../runs/opencarp/...`), and
`omnidriver compare` resolves relative paths against the request's own
directory (AGENT_GUIDE, "Comparing results as quantities"). So a request's
bytes, and therefore its digest, are the same on every machine and in every
run. That is why `runs` must sit here, as a link, rather than anywhere you
like.

## Levels and case ids

One sweep per solver and Δx. `level_study.py` keeps the study's rows in
order, so within each `dx<mm>` sweep the time steps are always these cases:

| case | Δt | cardiacFOAM `system/controlDict:deltaT` | openCARP `nversion.par:dt` |
|---|---|---|---|
| `case_0001` | 0.05 ms | `5e-05` s | `50.0` µs |
| `case_0002` | 0.01 ms | `1e-05` s | `10.0` µs |
| `case_0003` | 0.005 ms | `5e-06` s | `5.0` µs |

| Δx | cardiacFOAM `dx` | openCARP `dx` | end time | cardiacFOAM cells | openCARP nodes |
|---|---|---|---|---|---|
| 0.5 mm | `0.0005` m | `500.0` µm | 200 ms | 3,360 (40×6×14) | 4,305 (41×15×7) |
| 0.2 mm | `0.0002` m | `200.0` µm | 80 ms | 52,500 (100×15×35) | 58,176 (101×36×16) |
| 0.1 mm | `0.0001` m | `100.0` µm | 55 ms | 420,000 (200×30×70) | 442,401 (201×71×31) |

`summarize.py` prints each report's cases with the study values they
actually ran, so a case that is not the level its request names shows up.

## Pre-registration

The requests were written, committed and digested **before any campaign
value was read** (commit `82746b8`). One trial openCARP run at 0.5 mm had
already finished by then; only its step times and its log's timing table
had been looked at. **The owner may revise a tolerance
before the cluster run, and never after it.** To revise one:

1. edit `write_requests.py` (the tolerance, its rationale, or both);
2. run `python write_requests.py`, which rewrites `requests/` and
   `requests/SHA256SUMS`;
3. commit before any run, with a dated line under "Tolerances" below.

A request changed after a run has been read is a new request. It gets
its own report, and the first one stays. `omnidriver compare` refuses to
overwrite a report, and it records the request's digest in the report. The
tool cannot verify when a request was written, though; that part is
discipline (AGENT_GUIDE, "What pre-registration actually enforces").

`campaign.sh check` confirms three things before a run:
- the committed requests are what `write_requests.py` writes;
- `SHA256SUMS` verifies;
- the native case still has the probes and the grid the requests assume.

### Tolerances (proposed 2026-09-27; the owner may revise them before the run)

| requests | tolerance | rationale |
|---|---|---|
| `cross_dx<mm>_dt<ms>` (9): openCARP against cardiacFOAM at one level | **5 ms absolute**, every point, every level | The same bar everywhere, so the nine reports say at which level the two solvers agree to it. A coarse level outside it is a finding, not a reason to loosen it. 5 ms is about half the 10.9 ms spread of P8 across the paper's codes at its finest level (37.8–48.7 ms, section 6), so passing means agreeing more closely than two of the paper's codes may. It is the bar Task 8 fixed before its own runs, not one chosen from its numbers |
| `temporal_<solver>_dx<mm>_dt<a>_vs_dt<b>` (12): successive time steps of one solver at one Δx | **1 ms absolute** | The owner's belief, made testable. It is a fifth of the cross-solver bar, so a time-step effect inside it cannot decide a cross-solver verdict by itself. It is also 20 times the coarsest step, so the step's own quantisation of the 0 mV crossing cannot fail it |

In every request:
- **`both_not_reached: "fail"`.** Every end time was chosen so every
  point activates, so a point that does not is a failure.
- **Points in each solver's own frame, with no frame code.**
  - openCARP's frame is the reference frame. Its points are the
    reference's own coordinates, in mm.
  - cardiacFOAM's points are the `probeLocations` of
    `system/Niedererpoints`, in m, as the expected locations.
  - The pairing is cardiacFOAM probe k ↔ P(k+1). It is derived from the
    stimulus box in `constant/electroProperties` (cardiacfoam.md X), and
    stated in each pair's `note`.
- **`max_sampling_offset`:**
  - openCARP: how far any P1–P9 lies from its nearest node, rounded up at
    0.1 µm and at least 1 µm. That is 1 µm at 0.5 and 0.1 mm, where every
    point is a node, and 0.1415 mm at 0.2 mm, where P9 lies between four
    nodes.
  - cardiacFOAM: half a cell diagonal, rounded up at 0.1 µm: 0.4331,
    0.1733 and 0.0867 mm, because the native `system/Niedererpoints` set no
    `interpolationScheme` (OpenFOAM's `cell` default), so the reader
    reported the containing cell's centre.

**Sampling changed 2026-09-28 (owner decision).** From native `e9439c4f`,
`system/Niedererpoints` sets `interpolationScheme cellPoint`, and the reader
reports each probe at its own location (offset 0, inside the offsets above).
Every cardiacFOAM result below, and the 2026-09-27 local run of the whole
grid, used OpenFOAM's `cell` default: the containing cell's value. The
requests and tolerances are unchanged; the owner reruns the campaign.

Digests (`requests/SHA256SUMS`; verify with `shasum -a 256 -c SHA256SUMS`
in `requests/`):

| request | sha256 |
|---|---|
| `cross_dx0.5_dt0.05` | `0cfd212cf0d909d5dc0882762f86558e56ff2724d13076a90c94d8a79d74bdb1` |
| `cross_dx0.5_dt0.01` | `c6afde8f93177046b7502d57d988e7e46c9674eff6d59381fe0ba4731bdd31b2` |
| `cross_dx0.5_dt0.005` | `c807a42aa683372eb593d7bfd257e49794c11082861e9446d4fa56d0bca6b852` |
| `cross_dx0.2_dt0.05` | `abcbf739aacd13f8f41f2606398ed9492e9e591cb27883f607712ca3dbeec7e4` |
| `cross_dx0.2_dt0.01` | `524b193c74f85989633fcbed572ecfaab086655f96c89cda7120f82251b7c860` |
| `cross_dx0.2_dt0.005` | `6b983928bfe713e68f5599df06984bcb302860903f522d23869096f56a71010d` |
| `cross_dx0.1_dt0.05` | `211cdb42b31363449c354b87f23ec7e469960a59204398e75ad25ed283f24df8` |
| `cross_dx0.1_dt0.01` | `05abfe902a8a979dba67ee9dfaeae063c4574dfb81b18299691484b219560512` |
| `cross_dx0.1_dt0.005` | `84d0399d7d33776a002521add6c37401c1b6cca390e10f6b14e5923bc176cc20` |
| `temporal_opencarp_dx0.5_dt0.05_vs_dt0.01` | `5c1f21f6bd9d169020a7a1f7b30a785e8a65440c1c58145c356fe5b65bf2111d` |
| `temporal_opencarp_dx0.5_dt0.01_vs_dt0.005` | `a513b656cb787e4ef771476b4ce2535b4b64adb31b24b3228d7e65783cdf3b24` |
| `temporal_opencarp_dx0.2_dt0.05_vs_dt0.01` | `2df1ed4c0bc2c7944dac4bd82df661e02e17bbbd1ed54595ad71c5be77770826` |
| `temporal_opencarp_dx0.2_dt0.01_vs_dt0.005` | `00765a1850aec1e466891c81754fdc838e2cc3695eeea053d8080445da1b0ac2` |
| `temporal_opencarp_dx0.1_dt0.05_vs_dt0.01` | `9f3aa13081ec7a329fa834c36aa539b0ffe1193435c8e68de8f4ae70a6433449` |
| `temporal_opencarp_dx0.1_dt0.01_vs_dt0.005` | `67558f802ed0d115e26a62fdc34d39054fed3a646e65d2b1ea2fab99c0a0050c` |
| `temporal_cardiacfoam_dx0.5_dt0.05_vs_dt0.01` | `46aa1d78d479b527a420fdfdb1a7c2fb8b5187fa25e81a25c9c0cd82cf409eff` |
| `temporal_cardiacfoam_dx0.5_dt0.01_vs_dt0.005` | `4b8edf96c8598c79f23f05495307db20a485570985a349887175ee9d3d156172` |
| `temporal_cardiacfoam_dx0.2_dt0.05_vs_dt0.01` | `85680aa62185ec73ad682ad5851fabe7b46a0cd0165d1ef3a2e069f31f5ff3a5` |
| `temporal_cardiacfoam_dx0.2_dt0.01_vs_dt0.005` | `55895643da9a99a7390b00650703a379e045b431cf9d07d7e9d5ff1d80875427` |
| `temporal_cardiacfoam_dx0.1_dt0.05_vs_dt0.01` | `0a7954375d63faf228dff830b3c52c31f4f237f9c2f6cf3da2da911bc4d42388` |
| `temporal_cardiacfoam_dx0.1_dt0.01_vs_dt0.005` | `4e060d34b73843a038781edbacb1be665055a3866d11e9892f28e1876920b975` |

### Each solver's configuration, and why it is its best accurate one

- **openCARP: `nversion.par:mass_lumping 0`, the full mass matrix.**
  - openCARP's own benchmark driver (`03E_study_resolution/run.py`)
    passes `-mass_lumping 0` unless told otherwise. Its tutorial text says
    lumping gave the biggest inaccuracies among the paper's
    finite-element codes.
  - The binary's own default is 1, lumped (`openCARP +Help
    mass_lumping`). The `niedererNVersion` record passes nothing, so
    without this key a run is lumped. Every earlier omniD openCARP run
    was lumped, including Task 8.
  - At Δx 0.5 mm and Δt 0.01 ms, P8 is 126.27 ms lumped (Task 8) and
    58.14 ms with the full mass matrix (this campaign):
    `docs/solver-learning/opencarp.md` G10.
- **cardiacFOAM: the native case unchanged.** It runs
  `TNNPcompactBatched` with Rush–Larsen gating and the implicit
  monodomain algorithm. At the same wavefront this was 5.6× faster than
  RKF45 (cardiacfoam.md T).

## Environment, per solver

The two solvers need different MPIs, so each runs in its own shell.
`campaign.sh` builds each shell from variables you supply; it discovers
nothing:

| variable | for | value |
|---|---|---|
| `PYTHON` | both | a Python with `omnidriver`, `omnidriver-openfoam`, `omnidriver-cardiacfoam` and `omnidriver-opencarp` installed |
| `OMNIDRIVER_NATIVE_TUTORIALS` | cardiacFOAM | the native tutorials tree, a directory named `tutorials`. The runs start from its parent, because the native study's `cases_root` is `tutorials`. Use a clean `git worktree` or `git archive` of the native branch at `0489be3c` or later |
| `OPENFOAM_BASHRC` | cardiacFOAM | OpenFOAM's `etc/bashrc` (v2412 here). It is sourced for cardiacFOAM only, and it puts OpenFOAM's MPI (Open MPI here) first on `PATH` |
| `OMNIDRIVER_OPENCARP_TUTORIALS` | openCARP | openCARP's tutorials tree (`<prefix>/share/tutorials`). Its study's `cases_root` is `tutorials` too |
| `OPENCARP_MPI_BIN` | openCARP | **the bin directory of the MPI openCARP was built against, put first on `PATH`.** A bundled-MPICH install has `<prefix>/lib/petsc/bin`. Another MPI's `mpirun` (e.g. Open MPI's) silently starts N serial copies of the whole problem, racing on one output directory. omniD's preflight refuses that by name (`opencarp_mpi_launcher_mismatch`; opencarp.md I2, I5) |
| `CAMPAIGN_DYLD_LIBRARY_PATH` | both, **macOS only** | appended to `DYLD_LIBRARY_PATH` inside each solver's shell (here `/opt/homebrew/lib`, for openCARP's `libsundials_cvode`). macOS strips `DYLD_*` when it starts `bash`, so it cannot be exported from outside. Leave it unset on Linux |
| `HYDRA_IFACE` | openCARP, some hosts | only where the host name does not resolve, which MPICH's hydra needs (`lo0` on this workstation; opencarp.md I3) |

`omnidriver compare` and `summarize.py` need only `PYTHON`.

## Running it

### Ranks: `--parallel`, `SLURM_NTASKS` and `numberOfSubdomains`

`campaign.sh level <solver> <dx-mm> N` and `perf ... N` run serial for
N = 1. Otherwise they run the solve on N ranks (AGENT_GUIDE, "Running a
record in parallel"):

- **cardiacFOAM.** N is the case's `system/decomposeParDict:numberOfSubdomains`.
  The native value is 6, so `campaign.sh` writes N into the level study as
  a `base` value (`level_study.py --set
  system/decomposeParDict:numberOfSubdomains=N`) and adds `--parallel`
  with no count. The solve becomes `decomposePar -force`, then `mpirun -np
  N cardiacFoam -parallel`, then `reconstructPar`, each as its own step.
- **openCARP.** Its case states no count, so `campaign.sh` passes
  `--parallel N`. The solve becomes `mpirun -np N openCARP ...`.
- **Under Slurm.** omniD reads `SLURM_NTASKS`, and only when a run asks
  for parallel. If it disagrees with N, for either solver, the plan is
  refused before any solver starts, naming both numbers. So pass
  `"$SLURM_NTASKS"` as N, and request the ranks with `--ntasks`.
  `mpirun` inherits the allocation. omniD always launches with `mpirun`,
  never `srun`.
- **One thread per rank.** Neither solver threads (opencarp.md T5: MPI
  only; OpenFOAM is MPI only). Export `OMP_NUM_THREADS=1` anyway, since a
  threaded BLAS or PETSc build could otherwise oversubscribe.

### The agreement runs: one job per solver and Δx

```bash
cd <repo>/benchmarks/niederer2011/campaign
ln -s $SCRATCH/niederer-campaign runs      # once; the requests name ../runs
./campaign.sh check                        # before anything runs
./campaign.sh level opencarp    0.5 16
./campaign.sh level cardiacfoam 0.5 16
# ... 0.2 and 0.1 likewise
```

Each `level` call runs three cases, the level's three time steps, in
one sweep. It prints the sweep's JSON summary; every case should be
`completed`. It amounts to these commands (cardiacFOAM at 0.1 mm on
N = 16):

```bash
python level_study.py \
  --study $OMNIDRIVER_NATIVE_TUTORIALS/NiedererEtAl2011verification/setup/studies/cartesianConvergence/sweep_hex_convergence.json \
  --where dx=0.0001 --set system/decomposeParDict:numberOfSubdomains=16 \
  --out runs/studies/cardiacfoam_cartesianConvergence_dx0.1_np16.json
( source $OPENFOAM_BASHRC; cd $OMNIDRIVER_NATIVE_TUTORIALS/..
  python -m omnidriver sweep-run --plugin cardiacfoam \
    --spec <campaign>/runs/studies/cardiacfoam_cartesianConvergence_dx0.1_np16.json \
    --output-dir <campaign>/runs/cardiacfoam/cartesianConvergence/dx0.1 \
    --scratch-dir <campaign>/runs/scratch --parallel )
```

For openCARP at 0.1 mm on N = 16, `level_study.py` reads
`studies/opencarp_cartesianConvergence.json` with `--where dx=100.0`. The
run is `(export PATH=$OPENCARP_MPI_BIN:$PATH; cd
$OMNIDRIVER_OPENCARP_TUTORIALS/..; python -m omnidriver sweep-run --plugin
opencarp --spec ... --output-dir <campaign>/runs/opencarp/cartesianConvergence/dx0.1
--scratch-dir <campaign>/runs/scratch --parallel 16)`.

A sweep resumes: rerunning a `level` skips completed cases. To redo one
level from scratch, delete its `runs/<solver>/cartesianConvergence/dx<mm>`
first. Its reports are then stale, and a report is written once, so move
them aside rather than overwrite them.

**Rank count for the agreement runs.** Serial and parallel runs agree to
the precision each solver writes (cardiacfoam.md P3; opencarp.md I7), so
N does not change agreement. But these runs' solve times are also the
time-to-accuracy points. Use **one N for both solvers and every level**
(16 is proposed: one node on most clusters). Then each level's solve time
is measured on the same resources.

### A Slurm example

One job per solver and Δx. The same script serves every level:

```bash
#!/bin/bash
#SBATCH --job-name=niederer-%x
#SBATCH --ntasks=16
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --time=04:00:00
# usage: sbatch --export=ALL,SOLVER=cardiacfoam,DX=0.1 niederer.sbatch
set -euo pipefail
export OMP_NUM_THREADS=1
export PYTHON=$HOME/venvs/omnidriver/bin/python
export OMNIDRIVER_NATIVE_TUTORIALS=$HOME/cardiacFoam/tutorials         # clean, at 0489be3c or later
export OPENFOAM_BASHRC=/opt/OpenFOAM/OpenFOAM-v2412/etc/bashrc
export OMNIDRIVER_OPENCARP_TUTORIALS=/opt/opencarp/share/tutorials
export OPENCARP_MPI_BIN=/opt/opencarp/lib/petsc/bin                    # the MPI openCARP was built against
cd $HOME/omnidriver/benchmarks/niederer2011/campaign
./campaign.sh level "$SOLVER" "$DX" "$SLURM_NTASKS"
```

Submit six jobs, (opencarp, cardiacfoam) × (0.5, 0.2, 0.1), after
`campaign.sh check` has passed on the login node. `--time` is sized for
cardiacFOAM at 0.1 mm on 16 ranks ("Expected cost", below). A scheduler
other than Slurm needs only the rank count: omniD reads the allocation
from `SLURM_NTASKS` alone (`record_execution.SCHEDULER_ALLOCATION_VARIABLES`).
Elsewhere, N passed on the command line is the only source, and nothing
checks it against the allocation.

### Comparing

Run this when the runs are done, from any shell with `PYTHON`:

```bash
./campaign.sh compare              # every request whose cases have all completed
./campaign.sh compare cross_dx0.1_dt0.005     # or only those named
./campaign.sh summary > runs/summary.md
```

`compare` runs, for each request:

```bash
python -m omnidriver compare --comparison-request requests/<name>.json --report runs/reports/<name>.json
```

It skips a request whose cases have not all completed. It would otherwise
write an `unavailable` report, and a report is written once. It also skips
a request whose report already exists.

### Reading the reports

`runs/reports/<name>.json`:
- **`status` is the report's verdict, not the exit code.**
  - `passed`: every pair is `within_tolerance`.
  - `failed`: some pair is `outside_tolerance`, `reached_on_one_side`,
    `sampled_off_point` or `both_not_reached`.
  - `unavailable`: something could not be read (`status_reason` says
    what).
- **`metrics[]`**, one per point: both sides' `value` (in ms), their
  `sampled_at` and `requested_at` with units (µm for openCARP, m for
  cardiacFOAM), the `sampling_offset`, the `difference`, the `status` and
  the pair's `note`.
- **`request.digest`** must equal the request's line in `SHA256SUMS`.

`campaign.sh summary` prints the following, reading only:
- every run, with its study values, status, ranks and step times;
- every report's pair table, and core's association of the report with
  each case it names (it should be `run_verified`: the report matches
  each case's recorded digests);
- a time-to-accuracy table for P8. It gives each level's value, its
  difference from the solver's own finest level (Δx 0.1 mm, Δt
  0.005 ms), whether it lies in the paper's 37.8–48.7 ms, and the solve
  time. The range is read from `published_values` in
  `benchmarks/niederer2011.json`, not restated.

## Performance protocol

- **Fairness.** Equal ranks for both solvers, one thread per rank, one
  exclusive node (`--exclusive`, `--nodes=1`), the same node type for
  every job, and `OMP_NUM_THREADS=1`. Each solver runs its best
  accurate configuration, above.
- **Scaling curve.** At Δx 0.1 mm and Δt 0.05 ms (`campaign.sh perf
  <solver> 0.1 0.05 N r`):
  - N ∈ {1, 2, 4, 8, 16, 32, 64}, capped at one node's cores;
  - **3 repetitions** each, `r` = 1, 2, 3;
  - report the median and the minimum.

  This level has the finest mesh, which is what sets parallel
  efficiency, at the fewest steps (1,100). If the temporal reports
  pass, it is also the cheapest level that is as accurate as Δt
  0.005 ms. Each call is one sweep of one case, in
  `runs/perf/<solver>/dx0.1_dt0.05/np<N>/rep<r>/`.

  ```bash
  #SBATCH --ntasks=64 --nodes=1 --exclusive   # one job per solver; N below the allocation
  for n in 1 2 4 8 16 32 64; do for r in 1 2 3; do
    SLURM_NTASKS=$n ./campaign.sh perf "$SOLVER" 0.1 0.05 $n $r
  done; done
  ```

  Setting `SLURM_NTASKS=$n` tells omniD the ranks this step uses, inside
  a larger allocation. Otherwise it refuses N ≠ 64 by name. The other
  way is one job per N with `--ntasks=$n`.
- **Time to accuracy.**
  - Use the agreement runs, all on one N. For each solver, plot each
    level's solve time against |P8 − P8 at that solver's own finest
    level| (`summary`'s last table).
  - Also say whether each level's P8 lies in the paper's 37.8–48.7 ms,
    which is a statement about Δx 0.1 mm, Δt 0.005 ms.
  - "Time to reach accuracy X" is the cheapest level within X.

### What is recorded, and what is missing

What each run records:
- **`cases/<case>/workflow_state.json`: each step's `started_at` and
  `finished_at`** (UTC, µs), exit code, command and arguments. The step
  ids separate the phases:
  - `mesh` (or `gmsh`...) is meshing;
  - `solve` is the solve;
  - `solve.decompose` and `solve.reconstruct` are cardiacFOAM's
    decomposition and reconstruction;
  - `samplePoints`, `writeCellCentres`, `samplePointCentres` and
    `sampleLines` are post-processing.

  So **the solve's wall time is recorded apart from meshing,
  decomposition and post-processing**. `summarize.py` groups the steps
  this way.
- **The rank count:**
  - the solve step's own command, `mpirun -np N ...`;
  - the run document's `resolvedEntry.parallel`, `{"requested": ...,
    "allocation": {"variable": "SLURM_NTASKS", "ranks": N} | null}`;
  - for cardiacFOAM, the fingerprinted `decomposeParDict` in the
    provenance snapshot.

  A serial run has no `resolvedEntry.parallel`.
- **The solver's own timings** are in its kept solve log,
  `cases/<case>/workflow_logs/solve.attempt1.stdout.log`:
  - openCARP ends with "Timings of individual physics", which splits
    Electrics and Ionics into Init, Compute and Output;
  - OpenFOAM prints `ExecutionTime`/`ClockTime` every step.

What omniD does not record:
- **Where it ran.** No host name, CPU model, node list or job id.
- **The threading and binding environment.** `OMP_NUM_THREADS`, MPI
  binding and the `mpirun` version are not recorded.
- **The solve's own I/O.** The `solve` step's wall time includes the
  solver's field writes: cardiacFOAM writes every 5 ms of simulated
  time, openCARP `vm.igb` every 1 ms. Only openCARP's log separates it.

`campaign.sh` fills the first two for this campaign. Before each sweep it
writes `runs/hosts/<time>-<solver>-<what>.txt`, holding the host name,
`uname`, `lscpu` (or `sysctl` on macOS), every `SLURM_*`/`OMP_*`/`HYDRA_*`
variable, and `mpirun`'s path and version as the solver's shell sees
them. A neutral design for omniD itself is proposed in
`.superpowers/sdd/campaign-report.md`; it is not built.

## Expected cost

These are serial, on the owner's 14-core Apple-silicon workstation, while
other agents were running. Divide by N × parallel efficiency. cardiacFOAM
showed 1.9× on 2 ranks at 3,360 cells (cardiacfoam.md P3); expect about
0.6–0.8 at 16 ranks on the finer meshes. "measured" is this campaign's
proof; the rest scale per step with cells or nodes and are estimates.

| level | steps | cardiacFOAM solve | openCARP solve |
|---|---|---|---|
| 0.5 mm, 0.05 ms | 4,000 | 23 s measured | 3.5 s measured |
| 0.5 mm, 0.01 ms | 20,000 | 105 s measured | 16 s measured |
| 0.5 mm, 0.005 ms | 40,000 | 204 s measured | 31 s measured |
| 0.2 mm, 0.05 ms | 1,600 | ~2.5 min (93 s per 1,000 steps, cardiacfoam.md T) | ~20 s |
| 0.2 mm, 0.01 ms | 8,000 | ~12 min | ~1.5 min |
| 0.2 mm, 0.005 ms | 16,000 | ~25 min | ~3 min |
| 0.1 mm, 0.05 ms | 1,100 | ~14 min (8× the cells of 0.2 mm) | ~1.6 min |
| 0.1 mm, 0.01 ms | 5,500 | ~70 min | ~8 min |
| 0.1 mm, 0.005 ms | 11,000 | ~2.3 h | ~16 min |
| **whole grid** | | **~4.4 h serial** | **~30 min serial** |

- **cardiacFOAM** measured 5.1–5.8 ms per step at 3,360 cells, and 93 ms per
  step at 52,500 cells (section T). 0.1 mm assumes 8× that again.
- **openCARP** measured 0.8–0.9 ms per step at 4,305 nodes with the full mass
  matrix, and the table scales it with the node count. That is optimistic
  at 0.1 mm: its conjugate-gradient iterations per step may grow as Δt/Δx²
  grows, so allow 2×.
- **Wall time per job.** On 16 ranks, cardiacFOAM's 0.1 mm job should take
  about 20–30 min. Every openCARP job should take minutes. `--time=04:00:00`
  leaves room for the serial point of the scaling curve (~14 min per
  repetition at 0.1 mm, 0.05 ms for cardiacFOAM).
- **Disk.** cardiacFOAM writes about 190 bytes per cell per write. A
  0.1 mm case is about 1 GB, and about 2 GB in parallel, since the
  `processor*` directories stay. openCARP's `vm.igb` is nodes × frames ×
  4 bytes, about 100 MB at 0.1 mm. The whole campaign is about 10 GB,
  most of it cardiacFOAM at 0.1 mm.

## The proof (run here, 2026-09-27)

`campaign.sh proof` runs the 0.5 mm level exactly as above, with the
supplied environment of this workstation:

```bash
PYTHON=/tmp/odA-campaign/bin/python \
OMNIDRIVER_NATIVE_TUTORIALS=<native worktree>/tutorials OPENFOAM_BASHRC=/Volumes/OpenFOAM-v2412/etc/bashrc \
OMNIDRIVER_OPENCARP_TUTORIALS=/usr/local/lib/opencarp/share/tutorials \
OPENCARP_MPI_BIN=/usr/local/lib/opencarp/lib/petsc/bin CAMPAIGN_DYLD_LIBRARY_PATH=/opt/homebrew/lib HYDRA_IFACE=lo0 \
  ./campaign.sh proof
```

It does the following:
- `check`;
- both solvers' `level ... 0.5`, serial;
- `perf <solver> 0.5 0.05 N 1` for N = 1 and 2 (one parallel run per
  solver);
- the three cross-solver and four temporal requests at 0.5 mm;
- `summary`.

It took 473 s here (2026-09-27), nearly all of it cardiacFOAM. The tables
are in `docs/solver-learning/cardiacfoam.md` section Y and in
`.superpowers/sdd/campaign-report.md`. What it showed:
- every case `completed`, and every report `run_verified` against both
  cases it names;
- the three cross-solver reports `failed`: only P1 is within 5 ms, and P8
  is 58 ms (openCARP) against 143 ms (cardiacFOAM) at every Δt;
- all four temporal reports `passed`. The largest move is 0.87 ms
  (cardiacFOAM P8, Δt 0.05 against 0.01 ms) and 0.69 ms (openCARP P4);
- on 2 ranks, the values match serial to the precision written. For the
  solve times, see the report.

It is not a native test. It would need both MPIs in one test, which
means a third supplied variable for openCARP's launcher in the native
cardiacFOAM shape. It would also add another ~8 minutes to a shape that
already takes ~25.

## Later variations

Godunov splitting, SBDF2 and the like are extra studies on the same
records:
1. Put the study beside the native one (cardiacFOAM) or in `studies/`
   (openCARP).
2. Give it a name in place of `cartesianConvergence`. Its sweeps go to
   `runs/<solver>/<name>/dx<mm>`, next to these, and nothing here moves.
3. Add a block to `write_requests.py` naming that study's sweeps, run
   it, and commit the new requests and their digests before those runs.

The existing requests and their digests stay as they are.
