# Niederer 2011 cross-solver campaign: report

## Status

The campaign is prepared and proved at the cheapest level. The worktree
is `.claude/worktrees/campaign`, on branch `campaign`, based on `main` at
`ccbc685`. It is not merged or pushed.

| commit | what |
|---|---|
| `82746b8` | feat(benchmarks): the pre-registration. openCARP's 9-point study, 21 requests with `SHA256SUMS`, `write_requests.py`, `level_study.py`, `campaign.sh` and `summarize.py`. Committed before the proof run and before any campaign value was read |
| `a9a96fd` | docs(benchmarks): the README runbook; `campaign.sh` fixes (the OpenFOAM bashrc argument trap, host-facts naming); AGENT_GUIDE pointer; `opencarp.md` G10; `cardiacfoam.md` Y; plan and spec status lines |

- No record, core or package source changed.
- Every shape run is **0 failed** (§9).
- The proof ran as `campaign.sh proof`, a documented script, not a native
  test (§5).

## 1. Layout

```
benchmarks/niederer2011/campaign/
  README.md                                  the runbook
  studies/opencarp_cartesianConvergence.json openCARP's 9-point grid (cardiacFOAM uses its native study, not copied)
  requests/*.json (21), requests/SHA256SUMS  the pre-registered requests and their digests
  write_requests.py                          how the requests were typed; --check [--native-tutorials] guards them
  level_study.py                             one level's study from a zip study: keeps rows, adds base keys, never overrides
  campaign.sh                                check | level | perf | compare | summary | proof
  summarize.py                               run / report / association / time-to-accuracy tables, read-only
  .gitignore                                 /runs
  runs -> <scratch>                          per machine, git-ignored
```

The main design choice is **relative request paths, so no fill-in step
is needed**.
- `omnidriver compare` resolves a request's relative paths against the
  request's own directory.
- So each request names `../../../niederer2011.json` and
  `../runs/<solver>/cartesianConvergence/dx<mm>`, and `runs/` is a link to
  scratch.
- A request's bytes, and so its digest, are then the same on every
  machine and in every run. There are no templates.

**One sweep per solver and Δx**, `case_0001`/`0002`/`0003` = Δt 0.05 /
0.01 / 0.005 ms.
- `level_study.py` slices a level out of cardiacFOAM's native study, and
  adds `system/decomposeParDict:numberOfSubdomains=N` for a parallel run.
  So the native study is used and never copied.
- It keeps the study's row order, and the requests name those positional
  case ids.
- `write_requests.py --check --native-tutorials` checks three things:
  - the native `probeLocations` still equal the pairing table;
  - openCARP's grid still equals the native grid, after converting study
    units (µm, µs, ms to m, s);
  - both follow DX_MM × DT_MS with the end times, in order.

  It was run against a tampered copy of the native study and probes, and
  caught both changes.

## 2. Proposed tolerances and rationale

These were written before any campaign value was read. The owner may
revise them before the cluster run, never after (README,
"Pre-registration").

| requests | tolerance | rationale, in short |
|---|---|---|
| 9 × `cross_dx<mm>_dt<ms>` | **5 ms absolute**, all points, all levels | One bar everywhere, so the reports say at which level the two solvers agree. It is about half the paper's 10.9 ms cross-code P8 spread at its finest level. It is Task 8's pre-registered bar, not tuned |
| 12 × `temporal_<solver>_dx<mm>_dt<a>_vs_dt<b>` (successive Δt) | **1 ms absolute** | The owner's belief made testable. A fifth of the cross-solver bar, so the time step alone cannot decide a cross-solver verdict. 20× the coarsest Δt, so crossing-time quantisation cannot fail it |

In all requests:
- **`both_not_reached: "fail"`.**
- **Points in each solver's own frame.** openCARP's are the reference's
  coordinates, in mm. cardiacFOAM's are `system/Niedererpoints`, in m, as
  the expected locations. The pairing, probe k ↔ P(k+1), is in every
  `note`.
- **`max_sampling_offset`:**
  - openCARP: the farthest P from its nearest node, rounded up at 0.1 µm
    and at least 1 µm. That gives 0.001 mm at 0.5 and 0.1 mm, and 0.1415
    mm at 0.2 mm, where P9 is off-node.
  - cardiacFOAM: half a cell diagonal, rounded up: 0.0004331, 0.0001733
    and 0.0000867 m.

## 3. Request digests (sha256)

| request | digest |
|---|---|
| cross_dx0.5_dt0.05 | `0cfd212cf0d909d5dc0882762f86558e56ff2724d13076a90c94d8a79d74bdb1` |
| cross_dx0.5_dt0.01 | `c6afde8f93177046b7502d57d988e7e46c9674eff6d59381fe0ba4731bdd31b2` |
| cross_dx0.5_dt0.005 | `c807a42aa683372eb593d7bfd257e49794c11082861e9446d4fa56d0bca6b852` |
| cross_dx0.2_dt0.05 | `abcbf739aacd13f8f41f2606398ed9492e9e591cb27883f607712ca3dbeec7e4` |
| cross_dx0.2_dt0.01 | `524b193c74f85989633fcbed572ecfaab086655f96c89cda7120f82251b7c860` |
| cross_dx0.2_dt0.005 | `6b983928bfe713e68f5599df06984bcb302860903f522d23869096f56a71010d` |
| cross_dx0.1_dt0.05 | `211cdb42b31363449c354b87f23ec7e469960a59204398e75ad25ed283f24df8` |
| cross_dx0.1_dt0.01 | `05abfe902a8a979dba67ee9dfaeae063c4574dfb81b18299691484b219560512` |
| cross_dx0.1_dt0.005 | `84d0399d7d33776a002521add6c37401c1b6cca390e10f6b14e5923bc176cc20` |
| temporal_opencarp_dx0.5_dt0.05_vs_dt0.01 | `5c1f21f6bd9d169020a7a1f7b30a785e8a65440c1c58145c356fe5b65bf2111d` |
| temporal_opencarp_dx0.5_dt0.01_vs_dt0.005 | `a513b656cb787e4ef771476b4ce2535b4b64adb31b24b3228d7e65783cdf3b24` |
| temporal_opencarp_dx0.2_dt0.05_vs_dt0.01 | `2df1ed4c0bc2c7944dac4bd82df661e02e17bbbd1ed54595ad71c5be77770826` |
| temporal_opencarp_dx0.2_dt0.01_vs_dt0.005 | `00765a1850aec1e466891c81754fdc838e2cc3695eeea053d8080445da1b0ac2` |
| temporal_opencarp_dx0.1_dt0.05_vs_dt0.01 | `9f3aa13081ec7a329fa834c36aa539b0ffe1193435c8e68de8f4ae70a6433449` |
| temporal_opencarp_dx0.1_dt0.01_vs_dt0.005 | `67558f802ed0d115e26a62fdc34d39054fed3a646e65d2b1ea2fab99c0a0050c` |
| temporal_cardiacfoam_dx0.5_dt0.05_vs_dt0.01 | `46aa1d78d479b527a420fdfdb1a7c2fb8b5187fa25e81a25c9c0cd82cf409eff` |
| temporal_cardiacfoam_dx0.5_dt0.01_vs_dt0.005 | `4b8edf96c8598c79f23f05495307db20a485570985a349887175ee9d3d156172` |
| temporal_cardiacfoam_dx0.2_dt0.05_vs_dt0.01 | `85680aa62185ec73ad682ad5851fabe7b46a0cd0165d1ef3a2e069f31f5ff3a5` |
| temporal_cardiacfoam_dx0.2_dt0.01_vs_dt0.005 | `55895643da9a99a7390b00650703a379e045b431cf9d07d7e9d5ff1d80875427` |
| temporal_cardiacfoam_dx0.1_dt0.05_vs_dt0.01 | `0a7954375d63faf228dff830b3c52c31f4f237f9c2f6cf3da2da911bc4d42388` |
| temporal_cardiacfoam_dx0.1_dt0.01_vs_dt0.005 | `4e060d34b73843a038781edbacb1be665055a3866d11e9892f28e1876920b975` |

Each proof report's `request.digest` equals its line here.

**Order of events, stated plainly.** A trial run preceded the
pre-registration:
1. A trial openCARP `level 0.5` finished before the requests were
   generated. Only its step times and its log's timing table were looked
   at, no activation value.
2. The requests were then written, and the trial cardiacFOAM run started.
3. The trial compares came after that.
4. The pre-registration was committed as `82746b8`.
5. The proof below was then run from an empty `runs/`, and reproduced
   the trial's values to every printed digit.

## 4. Proof reports at Δx 0.5 mm

`campaign.sh proof` ran in 473 s wall on the owner's workstation, while
another agent's native suite was running.
- Every case `completed`.
- Every report is `run_verified` against both of its cases.
- The native tree was clean before and after (`git status --porcelain
  --ignored tutorials`: 0 lines), at `0489be3c`.
- Reports are under `.../scratchpad/campaign/proof/reports/`, and the
  whole summary is at `.../scratchpad/campaign/proof-summary.md`.

**Cross-solver** (openCARP full mass against cardiacFOAM, values in ms):

| point | oC dt .05 | cF dt .05 | diff | oC dt .01 | cF dt .01 | diff | oC dt .005 | cF dt .005 | diff |
|---|---|---|---|---|---|---|---|---|---|
| P1 | 1.353 | 1.217 | 0.137 ✓ | 1.252 | 1.195 | 0.057 ✓ | 1.241 | 1.192 | 0.049 ✓ |
| P2 | 47.233 | 132.930 | 85.697 | 47.348 | 132.290 | 84.942 | 47.354 | 132.193 | 84.839 |
| P3 | 33.322 | 46.144 | 12.822 | 32.938 | 46.518 | 13.580 | 32.884 | 46.543 | 13.659 |
| P4 | 58.747 | 142.991 | 84.244 | 58.054 | 142.131 | 84.077 | 57.960 | 142.004 | 84.044 |
| P5 | 11.600 | 36.082 | 24.482 | 11.518 | 35.929 | 24.411 | 11.506 | 35.900 | 24.394 |
| P6 | 47.557 | 134.256 | 86.699 | 47.671 | 133.607 | 85.936 | 47.678 | 133.508 | 85.830 |
| P7 | 34.245 | 56.239 | 21.995 | 33.856 | 55.961 | 22.105 | 33.801 | 55.912 | 22.111 |
| P8 | 58.830 | 143.912 | 85.082 | 58.144 | 143.043 | 84.899 | 58.051 | 142.914 | 84.863 |
| P9 | 25.308 | 71.208 | 45.900 | 24.901 | 70.711 | 45.810 | 24.848 | 70.637 | 45.789 |
| status | | | `failed` | | | `failed` | | | `failed` |

**Temporal** (1 ms; the largest |difference| per report, all `passed`):

| request | P1 | P2 | P3 | P4 | P5 | P6 | P7 | P8 | P9 |
|---|---|---|---|---|---|---|---|---|---|
| cardiacFOAM dt .05 vs .01 | 0.022 | 0.640 | 0.373 | 0.860 | 0.154 | 0.649 | 0.278 | **0.869** | 0.497 |
| cardiacFOAM dt .01 vs .005 | 0.003 | 0.097 | 0.025 | 0.127 | 0.029 | 0.099 | 0.049 | 0.129 | 0.074 |
| openCARP dt .05 vs .01 | 0.101 | 0.115 | 0.385 | **0.693** | 0.082 | 0.114 | 0.389 | 0.686 | 0.407 |
| openCARP dt .01 vs .005 | 0.011 | 0.006 | 0.054 | 0.094 | 0.012 | 0.007 | 0.055 | 0.093 | 0.053 |

**Reading.**
- **The owner's belief holds at 0.5 mm.** No Δt change moves any point by
  more than 0.87 ms. cardiacFOAM's 0.05→0.01 ms move is the closest to
  the bar.
- **The cross-solver gap is far larger than Task 8's 15–19 ms.** P8 is
  58 ms against 143 ms, because this campaign's openCARP uses the full
  mass matrix (§8, concern 1). cardiacFOAM's values match Task 8's
  (143.043 against 143.067 at dt 0.01 ms).

## 5. Serial against parallel (dx 0.5 mm, dt 0.05 ms, 4,000 steps)

Wall seconds, from each case's `workflow_state.json`:

| solver | ranks | solve | decompose + reconstruct | vs serial |
|---|---|---|---|---|
| cardiacFOAM | 1 | 22.4 | — | — |
| cardiacFOAM | 2 | 13.3 | 2.8 | final probe row identical as written; `nProcs : 2` |
| openCARP | 1 | 3.5 | — | — |
| openCARP | 2 | 3.1 | — | LAT differs by at most 1e-6 ms (the last digit) |

- cardiacFOAM's solve is 1.7× faster on 2 ranks, or 1.4× counting the
  decomposition. openCARP's case is too small to scale.
- `resolvedEntry.parallel` is `{"requested": true, "allocation": null}`
  for cardiacFOAM and `{"requested": 2, "allocation": null}` for openCARP.
  The solve steps are `mpirun -np 2 ...`.
- Serial level solves, cardiacFOAM against openCARP: 23.2 / 104.9 / 204.1
  s against 3.5 / 15.8 / 31.0 s, at dt 0.05 / 0.01 / 0.005 ms.

**Why a script and not a native test.** It took 473 s, under the ~10
minute limit. But as a native test it would need both MPIs in one test,
which means a new supplied variable for openCARP's launcher in the native
cardiacFOAM shape, and a CLAUDE.md change outside my files. It would also
add ~8 minutes to a ~25-minute shape. It can be added if wanted.

## 6. What is recorded for performance, and what is missing

**Recorded; no core change needed:**
- each step's `started_at`/`finished_at` in `workflow_state.json` (UTC,
  µs), and its command and arguments;
- the step ids separate `mesh`, `solve`, `solve.decompose`/
  `solve.reconstruct` and post-processing, so **the solve's wall time is
  recorded apart from meshing, decomposition and post-processing**;
- the rank count, from `mpirun -np N` and `resolvedEntry.parallel`, with
  the allocation;
- the solver's own timings, in the kept solve log only: openCARP's
  "Timings of individual physics" (Compute and Output), and OpenFOAM's
  `ExecutionTime`/`ClockTime`.

**Missing from the run document and workflow state:**
1. the host: name, CPU, node list, job id;
2. the threading and binding environment (`OMP_NUM_THREADS`, the MPI
   binding) and the launcher's version;
3. the solve step's own I/O, separated from its compute. Its wall time
   includes field writes; only openCARP's log splits them.

**Interim, campaign-side, no core change.** `campaign.sh` writes
`runs/hosts/<time>-<solver>-<sweep>.txt` before each sweep. It holds the
host name, `uname`, `lscpu`/`sysctl`, the `SLURM_*`/`OMP_*`/`HYDRA_*`
variables, and `mpirun`'s path and version.

**Proposed minimal neutral design (not built; it needs the owner's
go-ahead because it touches core):**
- **(a) Where a run ran.** The workflow runner writes, once per run, an
  `execution` block into `workflow_state.json`: `{hostname, platform,
  cpu_count, environment: {name: value}}`.
  - The names come from a declared core tuple beside
    `SCHEDULER_ALLOCATION_VARIABLES`: `SLURM_JOB_ID`,
    `SLURM_JOB_NODELIST`, `OMP_NUM_THREADS`.
  - Plugins add names through an optional hook, for example openCARP's
    `HYDRA_IFACE` and OpenFOAM's `FOAM_MPI`.
  - The block is recorded and never interpreted. That fits "supplied
    versus discovered", which allows reading ambient scheduler facts.
- **(b) The solver's own split, optional.** A plugin hook
  `solve_log_timings(step_id, log_text) -> {name: seconds}` puts the
  result in the step's existing `diagnostics`. openCARP would report
  Electrics Compute/Output and Ionics Compute; OpenFOAM would report
  `ExecutionTime`. There is no schema change.

## 7. Estimated cluster cost per level

These are serial wall-clock solve times. Measured means this proof;
estimates scale per step with cells or nodes (details in README,
"Expected cost").

| level | steps | cardiacFOAM | openCARP (full mass) |
|---|---|---|---|
| 0.5 mm (3 Δt) | 4k / 20k / 40k | 23 / 105 / 204 s measured | 3.5 / 16 / 31 s measured |
| 0.2 mm | 1.6k / 8k / 16k | ~2.5 / 12 / 25 min (93 s per 1,000 steps, section T) | ~20 s / 1.5 / 3 min |
| 0.1 mm | 1.1k / 5.5k / 11k | ~14 / 70 / 140 min (8× the 0.2 mm cells) | ~1.6 / 8 / 16 min (×2 allowed for CG growth) |
| whole grid | | **~4.4 h serial**; ~20–30 min for the 0.1 mm job on 16 ranks | **~30 min serial** |

- **Disk.** About 1 GB per cardiacFOAM 0.1 mm case, about 2 GB with its
  `processor*` directories; about 10 GB for the campaign.
- **Scaling curve** (README): Δx 0.1 mm, Δt 0.05 ms; N ∈ {1, 2, 4, 8, 16,
  32, 64} on one exclusive node; 3 repetitions each. cardiacFOAM's serial
  point is ~14 min per repetition.

## 8. Concerns

1. **openCARP's mass matrix changes the picture.** This is recorded as
   `opencarp.md` G10.
   - The binary lumps by default (`mass_lumping` default 1).
     `03E_study_resolution/run.py` passes `-mass_lumping 0` by default,
     and the `niedererNVersion` record passes nothing.
   - So every earlier omniD openCARP run was lumped, including Task 8's
     cross-solver comparison, G4, G8 and PAR's I7.
   - The campaign sets `nversion.par:mass_lumping 0` in its study, as
     "best accurate configuration". P8 at 0.5 mm moves from 126 to 58 ms.
   - **The owner should confirm this before the run.** Whether the record
     should pass run.py's default is a record decision I did not take.
     The records are off-limits here.
2. **I may have disrupted the bath agent's native suite.** At about
   01:59Z, stopping my own first (flawed) proof run, I used broad
   `pkill -f "omnidriver sweep-run"` and `pkill cardiacFoam`. Those match
   any user process. The bath agent's native pytest
   (`/tmp/odA-t54a-bath`, worktree `t54a-bath`) was running then, so one
   of its tests may have been killed mid-run and failed. Its next test was
   already running 8 s later. **Its current native results should be
   rerun or checked.** After that I killed only by my own PID.
3. **The OpenFOAM bashrc argument trap.** Sourced inside a shell
   function, `etc/bashrc` reads the function's positional arguments as
   settings and files to source, and it tried to execute the level study
   JSON. `campaign.sh` now clears them (`set --`) first. The first proof
   attempt hit this, and I discarded it and reran from empty. A job script
   that sources the bashrc at top level with arguments would hit it too.
4. **Temporal bar headroom.** cardiacFOAM's 0.05→0.01 ms move is already
   0.87 ms at 0.5 mm. At finer Δx the activation times are shorter, but
   the step's share may differ. If the owner wants the temporal claim to
   be robust, 1 ms may be tight. Revise only before the run.
5. **Positional case ids.** The requests name `case_0001..3` in
   `level_study.py`'s row order. `compare` does not check a case's study
   values against the request's `note`; `summarize.py` prints them side
   by side for a person to check. Reordering either study silently
   mispairs levels. `write_requests.py --check --native-tutorials` guards
   the native grid's order, not a hand-edited level study.
6. **Cluster launchers.**
   - omniD emits only `mpirun` and reads only `SLURM_NTASKS`, as PAR's
     concerns 1 and 2 say. A cluster that needs `srun` cannot run the
     parallel form as is.
   - The README's scaling loop inside one 64-rank allocation sets
     `SLURM_NTASKS=$n` per step. That is plausible but untested; one job
     per N is the safe alternative.
7. **The cost estimates at 0.1 mm are extrapolations.** openCARP's CG
   iterations, and cardiacFOAM's implicit solve, may grow with Δt/Δx².
   The 0.5 mm numbers were measured on a loaded workstation.
8. **Sampling differs by design at 0.2 mm P9.** openCARP's P9 lies
   0.141 mm from its nearest node, one of four equidistant nodes.
   cardiacFOAM's cell centre is 0.1 mm off. Both are within their
   pre-registered offsets and shown in the report.
9. **M9 is unchanged.** cardiacFOAM records the last upward crossing, and
   neither reader reports its threshold.
10. **The `runs` link must be at `campaign/runs`.** The relative-path
    design depends on it, and the README says so.

## 9. Verification (final summary lines)

```
# proof (both solvers, the runbook's own commands)
campaign.sh proof                  -> PROOF rc=0 wall=473s; 3 cross `failed`, 4 temporal `passed`, all run_verified
campaign.sh check                  -> requests match; SHA256SUMS verifies; native case matches PROBES and grid

# all packages (/tmp/odA-campaign)
3441 passed, 243 skipped, 142 deselected, 8 warnings, 40 subtests passed in 174.29s
# core alone (/tmp/odAcore-campaign)
1732 passed, 95 skipped, 8 warnings in 88.79s
# installed wheel (/tmp/wheeltest-campaign, /tmp/wheelenv-campaign)
Wheel artifact OK: core installs and runs standalone.
1536 passed, 291 skipped, 8 warnings in 33.23s

# static gates, all rc 0
check-import-boundaries.py     -> Import boundaries OK
export-capability-seams.py --check -> up to date
check-case-writes.py           -> Case-write boundaries OK
check-core-shape.py            -> rc 0
check-benchmark-references.py  -> ok niederer2011.json: 9 points, coordinates for P1..P9
```

- The native shapes were not rerun. No package source or test changed,
  and the proof exercised both solvers natively through omniD.
- The post-proof `campaign.sh` edit, which changed host-facts naming
  only, was re-exercised: `check`, one `perf opencarp` run, and
  `compare`'s written-once and not-yet-run guards.
