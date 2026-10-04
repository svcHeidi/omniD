# openCARP through omniD

Study keys are `<file>.par:<parameter>`, e.g. `nversion.par:gregion[0].g_il`.
A study goes in a sweep spec (`sweep-plan`/`sweep-run --spec`, whose `base`
names `entry` and `cases_root`; a one-case study is a one-value axis). A
single `plan`/`run` takes the native case as it is, plus `--parallel`.

`plan`/`run` stage the record's case under a scratch root you supply:
`--scratch-dir <dir>` (or `OMNIDRIVER_SCRATCH_DIR`), a writable directory
outside the tutorials tree. There is no default -- without one the plan is
refused by name, and one inside the tutorials tree is refused too; the native
tree is only ever read. `describe` needs none.

`describe` lists every parameter you may set, with its type, default and
bounds: only keys of a `.par` the record passes with `+F`, and none the record's
command line sets.

- The record owns its command-line keys. openCARP reads its arguments in
  order and the last assignment wins silently, so a `-<key>` after `+F` (for
  this record `meshname`, `simID`, `imp_region[0].im_sv_init`) overrides the
  `.par` with no warning (F14). omniD refuses a study key the record sets on
  its command line, and a `.par` no step passes with `+F`, by name.

- Flags: write `true`/`false` in a study; omniD writes `1`/`0`. openCARP reads
  `no`, `off`, `yes`, `2` all as ON (F1).
- Counts size arrays: `stim[1].*` needs `num_stim >= 2`, or openCARP exits (F2).
  `num_stim` defaults to 2, so a case that omits it gets two stimuli (F7).
- Units: `dt` is in microseconds, `tend` in milliseconds (G2); `describe` lists
  each parameter's unit as `+Help` prints it. The mesh axis `dx` is in
  micrometres (F3).
- Bounds: a bound written as a number is checked when a study sets the key. A
  bound that names parameters, or does `+ - * /` on them and numbers
  (`spacedt` <= `tend`, G1; `tend` >= `dt/1000.`), is evaluated at their
  values in the case, their defaults where the case omits them, and
  `[PrMelem1]` stands for the key's own index. Any other bound is not judged:
  the plan notes `opencarp_bound_not_checked` and leaves it to openCARP.
- A key assigned twice in a .par takes its last value (F8); omniD refuses to
  patch such a key.
- Strings: omniD always writes a `.par` string quoted (F13). An unquoted
  value containing `=` is silently truncated at the `=` (F10), so omniD
  refuses to write or read one unquoted; `""` is the empty string, not an
  absent value (F11); a string cannot contain `#`, because openCARP starts a
  comment there even inside quotes (F12).
- Relative paths resolve against the case directory, which is every step's
  working directory (F5).
- Defaults that make a run slow: mesher resolution 100 µm, tend 100 ms, dt 5 µs
  (G7). Pin `dx`, `nversion.par:tend` and `nversion.par:dt` for quick studies.
- Outputs: `out/vm.igb` holds every time step; `out/init_acts_vm_act-thresh.dat`
  holds one activation time per mesh point in point order, -1 if never
  activated (F6).

## Reading activation times as quantities

`out/init_acts_vm_act-thresh.dat` has format `opencarp_lat_per_node`. `omnidriver
compare` reads it at points you supply in the request (`runs.<name>.points`, any
length unit; omniD converts to µm). The reader takes the value of the nearest mesh
node and reports that node's coordinates as `sampled_at`, with rule `node`, unit
`ms`, and `-1` as `not_reached`. It refuses a point equidistant from two nodes: at
dx 1000 the slab centre is one. Pick a dx whose nodes include your points (dx 500
and 250 contain the Niederer corners and centre). The mesh is the one openCARP
records in `out/parameters.par` (F16). `lats[0].all` must stay `0`: with `1`
there is no per-node file (F17). openCARP's slab is 0–20000 × 0–7000 × 0–3000 µm
with the stimulus cube at the origin and fibres along x (F3). That is the frame
of `benchmarks/niederer2011.json`, so its coordinates are written unchanged.

## Running in parallel

Ask with the study value `parallel` (or `--parallel` on the CLI); serial is the
default. openCARP has no decomposition file, so its process count is either the
scheduler's allocation (`SLURM_NTASKS`, used by `parallel: true`) or a count you
supply (`parallel: 4`, `--parallel 4`); outside a scheduler `true` is refused, and
a count that disagrees with the allocation is refused. The solve runs as `mpirun
-np N openCARP ...`; the outputs keep their serial names, node order and location,
and differ from a serial run only in the LAT file's last printed digit (I7). The
`mpirun` first on PATH must be the launcher of the MPI openCARP was built
against (an install that bundles MPICH ships it next to its PETSc). Another MPI's
launcher runs N separate one-process copies into one output directory; preflight
refuses it by name (`opencarp_mpi_launcher_mismatch`, I2, I5).
