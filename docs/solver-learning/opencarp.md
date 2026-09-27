# Learning openCARP: the evidence log

**Method:** [`method.md`](method.md). **Design it feeds:**
`docs/superpowers/specs/2026-09-25-solver-conformance-and-opencarp-design.md` §7, §9.
**Machine:** macOS arm64, the owner's workstation. **Started:** 2026-09-25.

Every entry records the command and what it printed (abridged). Secrets that
appear in output are redacted.

## A. Locate and run

| # | command | observed | conclusion |
|---|---|---|---|
| A1 | `which openCARP` | `/usr/local/bin/openCARP` → `/usr/local/lib/opencarp/bin/openCARP` (Mach-O arm64) | installed system-wide |
| A2 | `ls /usr/local/bin \| grep -iE 'carp\|igb\|mesher\|bench'` | `bench igbapd igbdft igbextract igbhead igbops install_carputils.sh mesher openCARP` | solver + mesher + IGB tools; carputils only as an installer |
| A3 | `python3 -c "import carputils"` | `ModuleNotFoundError` | carputils absent; the design does not use it |
| A4 | `openCARP -revision` | `dyld: Library not loaded: /usr/local/lib/libsundials_cvode.7.dylib` | the binary cannot start as installed |
| A5 | `ls /opt/homebrew/lib \| grep sundials`; `brew list --versions sundials` | `libsundials_cvode.7.dylib` present; `sundials 7.3.0` | the library exists, in Homebrew's prefix |
| A6 | `DYLD_LIBRARY_PATH=/opt/homebrew/lib bench --help` | usage text | **environment contract: one library path.** No shell profile. The path is supplied, never discovered |
| A7 | `openCARP -revision` (with A6's path) | `*** Unrecognized keyword -revision` | not a valid flag |
| A8 | `openCARP -buildinfo` | `GIT tag: v18.1`, `GIT hash: 6eaa147d…`; also a CI repository URL with an embedded token (**redacted**) | version identity from the binary; build output can carry credentials. Used since 2026-09-25 (final review S-M3): preflight parses the `GIT tag` line and warns (`opencarp_version_mismatch`), naming both tags, when it differs from the committed catalogue's `identity.tag`; v18.1 matches (`test_environment_native.py`) |

## B. Self-description

| # | command | observed | conclusion |
|---|---|---|---|
| B1 | `openCARP +Help` | usage `openCARP [+Default \| +F file \| +Help topic \| +Doc] [+Save file]`, then about 265 parameter lines, e.g. `'-lats[Int].threshold' Float`, `-num_LATs Int` (272 lines in total) | full parameter list with types; indexed names appear as `[Int]` templates |
| B2 | `openCARP +Help bidomain` | description; `type: Short`; `default: (Short)(0)`; menu `0 Monodomain / 1 Bidomain / 2 Pseudo-bidomain` | per-parameter description, default and allowed values: **the catalog source** |
| B3 | `openCARP +Help 'lats[Int].threshold'` | prints the general list again, no detail | the template form is not accepted |
| B4 | `openCARP +Help 'stim[0].pulse.strength'` | description ("amplitude… uA/volume… mV"), `type: Float` | **a concrete index is required** for detail on indexed names |
| B5 | `openCARP +Help num_stim` | `type: Int`, `default: (Int)(2)`, `min: (Int)(0)`, `Changes the allocation of: {…}` | **surprising default: 2 stimuli.** Count keys allocate their indexed arrays |
| B6 | `openCARP +Default +Save defaults.par` | nothing written, exit 1 | no defaults export by this route |
| B8 | `openCARP +Help 'phys_region[0].ID'`, `'phys_region[Int].ID'`; then `'phys_region[0].ID[0]'` | the first two print the general list; the element prints a full detail block (`type: Int`, `default: (Int)(0)`) | **a whole-array shorthand (type `{ N x T }`) has no detail block under any spelling; only its elements do.** The catalog records a shorthand from its list line alone |
| B9 | the planned `catalog_generation.build_catalog()`, run against the binary (plan Task 9 dry run) | 266 parameters in about 35 s; identity `v18.1` + hash, no URL; 16 shorthands; 11 count keys (e.g. `num_stim → stim, stimulus`, `num_LATs → lats`); `compute_APD` default `PrMFALSE`; `spacedt` max `tend` | the generator's parse matches every value Task 9's tests expect |
| B7 | `DYLD_LIBRARY_PATH=/opt/homebrew/lib /tmp/odconf-trackB/bin/python scripts/generate-opencarp-catalog.py` (Task 9, 2026-09-25) | 266 parameters in 36.3 s (`time`, user+sys); identity `{tag: v18.1, hash: 6eaa147d...}`, no URL; type histogram 53 Float, 52 Int, 40 Short, 35 Double, 30 String, 18 RFile, 14 WFile, 7 Flag, 1 Long, plus 16 whole-array shorthand forms (266 total); 11 count keys | matches B9's dry run exactly; `grep -i "gitlab\|token"` on the committed JSON finds nothing (G3 held); committed and drift-gated by `test_catalog_native.py` |

## C. Native examples

- **C1:** tutorials live in `/usr/local/lib/opencarp/share/tutorials/` (also the
  `experiments` repository, Apache-2.0). Groups: `01_EP_single_cell`,
  `02_EP_tissue`, `03_Eikonal`, `05_pre_post_processing`, `06_visualization`,
  plus onboarding notebooks.
- **C2:** every example is a carputils `run.py`. Some also ship native files:
  - `00_simple`: `simple.par`;
  - `01_basic_usage`: `basic.par`;
  - `03C_tuning_wavelength`: `.par` files plus a full `Mesh_1.5cm_Cable/`
    (`mesh.pts/.elem/.lon/.surf`, `stim.vtx`);
  - `03E_study_resolution`: `nversion.par`, `singlecell.sv`;
  - `05A`–`05E`: heterogeneity `.par` files and `.vtx` files;
  - `16_bidm_dogbone`: `pt_shock.par`, `run.sh`;
  - `21_reentry_induction`: `parameters.par` plus a mesh directory.
  
  The single-cell examples are all script-only.
- **C3, read end to end: `02_EP_tissue/00_simple`.**
  - `simple.par` holds the ionic model, the stimulus pulse and the solver
    settings.
  - `run.py` builds the rest in Python:
    - the mesh (`mesh.Block(size=(2,0.5,0.5))`);
    - fibres;
    - conductivities (`gregion[0].*`);
    - an ionic model override;
    - LAT settings;
    - the stimulus geometry.
  - Only `--tend` is exposed.
  - **Defect:** `'imp_region[0].im', 'Courtemanche'` lacks a trailing comma, so
    Python fuses `'Courtemanche'` with the next string.
- **C4, first case: `02_EP_tissue/03E_study_resolution`**, the Niederer 2011
  N-version benchmark.
  - `nversion.par` holds the physics:
    - `tenTusscherPanfilov`, `im_param = "flags=EPI"`;
    - `g_il/it/in = 0.17/0.019/0.019`, `g_el/et/en = 0.62/0.24/0.24`;
    - a stimulus cube from (0,0,0) to (1500,1500,1500) µm at 35.71 for 2 ms;
    - LATs.
  - `run.py` adds:
    - the slab, `mesh.Block(size=(20,7,3), resolution=dx/1000, centre=(10,3.5,1.5))`;
    - `im_sv_init = os.getcwd()+'/singlecell.sv'`;
    - `tend`, `dt`, `mass_lumping`;
    - physics tags.

## D. Smallest real run

| # | command | observed | conclusion |
|---|---|---|---|
| D1 | `mesher -size[0] 0.2 …` (unquoted, zsh) | `no matches found: -size[0]` | zsh globs bracketed arguments; quote them |
| D2 | `mesher '-size[0]' 0.2 '-size[1]' 0.05 '-size[2]' 0.05 '-resolution[0]' 250 … -mesh block` | 81 points, 160 tetrahedra; `block.pts/.elem/.lon/.vec/.vpts` | `size` is in cm and `resolution` in µm (0.2 cm / 250 µm = 8 cells) |
| D3 | `openCARP +F simple.par -meshname block -simID run1 -tend 20` plus stimulus box `stim[0].elec.p0/p1[i]` plus `-num_LATs 1 -lats[0].ID act -lats[0].threshold -10` | exit 0, **0.25 s** | real-binary tests are affordable |
| D4 | `ls run1` | `IO_stats.dat ODE_stats.dat S1.trc act-thresh.dat electrics.log par_stats.dat parameters.par petsc_err_log.txt vm.igb` | the output directory is `-simID`, a command argument; no time directories |
| D5 | `cat run1/parameters.par` | git hash; the full command line; `simple.par` verbatim between markers; every command-line override resolved as `key = value` | **the solver records the configuration it was given** (not its defaults) |
| D6 | `igbhead run1/vm.igb` | `x 81, y 1, z 1, t 21`, `float`, units `mv`, `um` | one file holds all 21 output times (`spacedt = 1` over 20 ms) |
| D7 | `wc -l run1/act-thresh.dat`; `head -3` | 81 lines; `9 0.382323`, `27 0.382323`, … | one line per mesh point, two columns; the meaning of column 1 is open (F6) |
| D8 | the planned `par_format.patch_par` on the real `nversion.par` (`tend` 10.0, `dt` 50.0 appended), then `openCARP +F patched.par -meshname slab -simID out_patched -imp_region[0].im_sv_init singlecell.sv` | exit 0; `parameters.par` echoes the marked block and both keys; `vm.igb` has `t dimension: 11` | openCARP accepts the appended omniD block, and the appended `tend` takes effect. The planned parser also round-trips all 26 shipped `.par` files byte for byte (832 assignments) |

## E. Mapping onto omniD

| omniD noun | openCARP | evidence |
|---|---|---|
| native case | a tutorial directory's `.par` (+ `.sv`), plus mesh files | C2, C4 |
| study key | `nversion.par:gregion[0].g_il` | B1 key form |
| axis | `dx` (µm) → `mesher -resolution[i]` | C4, D2 |
| key validator | a catalog generated from `+Help` / `+Help <concrete name>` | B1, B2, B4 |
| reader and comparator | a `.par` line parser; numeric-aware comparison | C3, D5 |
| workflow steps | `mesher …` → `openCARP +F <par> -meshname <m> -simID <out>` | D2, D3 |
| artifacts | `<simID>/vm.igb`, `<simID>/<lat-id>-thresh.dat` | D4 |
| environment | `DYLD_LIBRARY_PATH` supplied; preflight runs `openCARP -buildinfo` | A4–A8 |

## F. Open questions: each settled only by a run

All settled 2026-09-25 against openCARP v18.1. Scratch cases live in the
session scratchpad, never in the native tree.

| id | question | run | observed | conclusion |
|---|---|---|---|---|
| F1 | How is a `Flag` written in a `.par`? | `compute_APD = <v>` for v in `1 0 yes true no false 2 off`, on the 160-tet block | APD outputs (`vm_activation.dat`, `vm_repolarisation.dat`) appear for `1 yes true no 2 off`; absent for `0 false`; every value exits 0 | **Only `0` and `false` mean off. `no` and `off` silently mean on.** omniD's value kind for a Flag is `boolean`; the writer emits `1`/`0`; the validator refuses any other spelling in a study, and the reader refuses one in a native file |
| F2 | An indexed key beyond its count (`stim[1].*` with `num_stim = 1`)? | a `.par` with `num_stim = 1` and `stim[1].pulse.strength = 999.0` | exit 5: `*** Index #1 (1) in stim[1].pulse.strength  is out of bounds [0-0]` | the binary refuses. The validator also refuses it by name at plan time, from the count key's value in the staged case after patching, so the refusal comes before a run rather than from one |
| F3 | Which `mesher` arguments reproduce the benchmark slab? | `mesher -size 2.0 0.7 0.3 -center 1.0 0.35 0.15 -resolution 500 500 500 -mesh slab` (indexed forms, quoted) | 4305 points (41×15×7), 16800 tets; extents x 0–20000, y 0–7000, z 0–3000 µm; `.lon` first row `1 0 0` | `size` and `center` in **cm**, `resolution` in **µm**. This gives the Niederer 20×7×3 mm slab with its corner at the origin, matching the stimulus cube (0–1500 µm) in `nversion.par`. Default fibres run along x, as the benchmark requires. Checked against the benchmark geometry, not against carputils (not installed) |
| F4 | Are `gen_physics_opts` region options needed? | the full case at dx 500, tend 150, with and without `-num_phys_regions 2` (ptype 0 and 1, both on tag 1) | both exit 0; `vm.igb` and the LAT file **byte-identical**; only the no-region warning differs | not needed for this case; the record omits them. Caveat: the region options were hand-written, because carputils' generator is not installed |
| F5 | How does `im_sv_init` resolve? | the same case, run from the case directory, then from its parent with `+F stage/nversion.par` | from the case directory: `read_sv(): Initialization using file: singlecell.sv`; from the parent: exit 255, `Unable to access file singlecell.sv` | **relative paths resolve against the process working directory**, not the `.par` location. The solve step runs with the staged case root as its working directory and passes `singlecell.sv` case-relative |
| F6 | The LAT file's layout? | `wc`, `awk` on `init_acts_vm_act-thresh.dat` (nversion) and `act-thresh.dat` (block run) | nversion (`lats[0].all = 0`): 4305 lines, one column, in point order, `-1` for never activated. Block run (default `all = 1`): two columns | layout depends on `lats[].all`. With `all = 0` it is one value per mesh point in point order, `-1` = not activated; with `all = 1` (the default) it is one line per activation event. File name: `init_acts_<lats[].ID>-thresh.dat`; nversion's ID defaults to `vm_act` |
| F7 | Does omitting `num_stim` give two stimuli? | a `.par` without `num_stim` | exit 0; `Stimulus_0.trc` and `Stimulus_1.trc`; `Warning: No potential or current stimuli found!` | **yes: two default, zero-strength stimuli.** A study that intends one stimulus must state `num_stim` |
| F8 | What does openCARP do with a key assigned twice in one `.par`? (raised while designing the parser) | `spacedt = 1` then `spacedt = 2`, tend 5 | exit 0; `igbhead` shows `t dimension: 3` (frames at 0, 2, 4 ms) | **the last assignment wins, silently.** openCARP's own saved `21_reentry_induction/.../parameters.par` repeats `dt`, `spacedt`, `timedt`, `mass_lumping` and `tend`. The reader returns the last assignment; the patcher refuses to patch a repeated key by name rather than guess which occurrence was meant |
| F9 | Is `key value` (no `=`) valid `.par` syntax? (found by testing the plan's parser on all 832 shipped assignments: `onboarding_notebooks/tissue/0[1-3]_basic_openCARP/ring.par` use it) | `spacedt 2` without `=`, tend 5 | exit 0; `t dimension: 3`; `parameters.par` echoes `spacedt 2` | **the separator is `=` or whitespace.** The parser accepts both; a patch keeps the line's own separator |
| F10 | Does an unquoted value containing `=` survive? (review B-I6: the tests asserted `im_param = flags=EPI`; the only native occurrence, C4, is quoted) | on the 160-tet block (D2), `simple.par` with `tenTusscherPanfilov`, tend 20, `openCARP +F p.par -meshname ../block`, one line varied: `simID = x=y` vs `simID = "x=y"`; then `imp_region[0].im_param = flags=ENDO` vs `= "flags=ENDO"`, vs no `im_param`, `"flags=EPI"`, `flags=EPI`, `"flags=MCELL"`; `md5` of `vm.igb` | `simID = x=y` makes directory `x`, `"x=y"` makes `x=y`; unquoted `flags=ENDO` gives the **same `vm.igb` as no `im_param`** (EPI, the default), quoted `"flags=ENDO"` differs, as does `"flags=MCELL"`; every run exits 0 and warns nothing | **unquoted, everything from an `=` on is silently dropped.** `format_value` always quotes a string (F13). The reader returns an unquoted native `a=b` whole, which is not what openCARP reads; no shipped `.par` has one (review B-I6), and Task 11's config reader must refuse one rather than report it |
| F11 | Is `""` the empty string? | as F10: `simID = ""`; and `imp_region[0].im_param = ""` vs no `im_param` | `simID = ""`: exit 255, `Unable to make output directory` (a literal `""` name would have been creatable); `im_param = ""` gives a `vm.igb` byte-identical to omitting it (its default is empty for this model) | **`""` spells the empty string**; the quotes are removed, not kept |
| F12 | Does quoting protect a `#`? | as F10: `simID = "a#b"` vs `simID = a#b` | exit 0 both; the quoted one makes directory `"a` (quote included), the unquoted one `a`; `parameters.par` echoes `simID = "a#b"` | **`#` starts a comment even inside quotes**, leaving an unbalanced quote in the value. No spelling carries a `#`, so `format_value` refuses one by name |
| F13 | Is quoting transparent for the String/RFile values omniD writes? | as F10: `imp_region[0].im = tenTusscherPanfilov` vs `"tenTusscherPanfilov"`; `imp_region[0].im_sv_init = singlecell.sv` vs `"singlecell.sv"` (the Niederer `.sv`, copied into the run directory); `simID = "two words"`; also F10's `"x=y"` and `simID = "quoted"` | model: `vm.igb` byte-identical; `.sv`: both log `read_sv(): Initialization using file: singlecell.sv` and give byte-identical `vm.igb` (different from no `.sv`); `"two words"` makes directory `two words`; `"quoted"` makes `quoted` | **a balanced pair of quotes is removed and nothing else changes.** `format_value` quotes every string, which F10 shows is the only safe spelling for `=` |
| F14 | Which wins when a key is set both in the `+F` `.par` and on the command line? (wave-2 review I1; re-run by the fixer 2026-09-25) | the staged `03E_study_resolution` case, `mesher` slab at dx 1000 (F3); `probe.par` = `nversion.par` plus `tend = 10.0`, `dt = 50.0`, `simID = "fromPar"`, `imp_region[0].im_sv_init = "nonexistent.sv"`. Run 1, the record's order: `openCARP +F probe.par -meshname slab -simID fromCLI -imp_region[0].im_sv_init singlecell.sv`. Run 2, the flags moved before `+F`: `openCARP -simID fromCLI2 -imp_region[0].im_sv_init singlecell.sv +F probe.par -meshname slab` | run 1: exit 0, output in `fromCLI/`, `read_sv(): Initialization using file: singlecell.sv`, and no warning but the usual no-physics-region one; its `parameters.par` echoes both `.par` lines, then resolves `simID = fromCLI`, `imp_region[0].im_sv_init = singlecell.sv`. Run 2: exit 255, output directory `fromPar/`, `*** imp_region[0].im_sv_init: Unable to access file nonexistent.sv`; its `parameters.par` lists the flags first, then the `.par` lines | **openCARP reads its arguments in order and the last assignment wins, silently** (F8's rule, across `+F` and flags). The record passes `+F nversion.par` first, so every `-<key>` after it overrides the `.par` with no warning. The validator refuses, by name, a study key a record step assigns after `+F <document>`, and a document no record step passes with `+F`; `get_record_key_catalog` lists neither. Both facts are read from the records' own steps (`validation.read_documents`) |
| F15 | What does one record run leave in the case beyond its declared outputs? (spec 2026-09-26 A5, conformance C11) | C6's run of `niedererNVersion` (dx 1000, tend 10, dt 50) on the staged `03E_study_resolution`, then a listing of the staged case | `mesher` wrote `slab.pts`, `slab.elem`, `slab.lon`, **`slab.vec`, `slab.vpts`**; `openCARP ... -simID out` wrote `out/` holding `vm.igb`, `init_acts_vm_act-thresh.dat`, **`IO_stats.dat`, `ODE_stats.dat`, `Stimulus_0.trc`, `electrics.log`, `par_stats.dat`, `parameters.par`, `petsc_err_log.txt`** | **the `-simID` directory is wholly generated, and `mesher` writes five files, not three.** The record declares `out` and all five mesh files in `produces`, so record staging never carries them into a new stage (C11) |
| F16 | Does openCARP record which mesh a solve used? | the dx-1000 slab (`mesher '-size[0]' 2.0 '-size[1]' 0.7 '-size[2]' 0.3 '-center[0]' 1.0 '-center[1]' 0.35 '-center[2]' 0.15 '-resolution[0]' 1000 '-resolution[1]' 1000 '-resolution[2]' 1000 -mesh slab`), `openCARP +F nversion.par -meshname slab -simID out '-imp_region[0].im_sv_init' singlecell.sv -tend 10 -dt 50`; `grep meshname out/parameters.par`; `par_format.read_raw(text, "meshname")` and `par_format.parse_par(text)` on the real `out/parameters.par` (2026-09-26, scratchpad, redone against `03E_study_resolution` per this task) | `slab.pts`: 672 points, then integer µm coordinates (`0 0 0`, `1000 0 0`, …), 673 lines; `out/parameters.par` line 70: `meshname                                = slab` (padded before `=`); `read_raw(text, "meshname")` returns `'slab'`, `unquote` leaves it `'slab'`; `parse_par(text)` returns 40 assignments; `out/init_acts_vm_act-thresh.dat` has 672 lines, one column, 658 of them `-1.000000` | **yes: `<simID>/parameters.par` states `meshname`**, relative to the working directory (F5). The LAT reader reads the mesh from there, the solver's own record of the run, rather than from an argument |
| F17 | What does `lats[0].all = 1` write for nversion? | as F16 plus `-lats[0].all 1`, `-simID outall` (same slab and case) | `ls outall`: `IO_stats.dat ODE_stats.dat Stimulus_0.trc electrics.log par_stats.dat parameters.par petsc_err_log.txt vm.igb vm_act-thresh.dat` -- **no `init_acts_vm_act-thresh.dat`**; `head -3 outall/vm_act-thresh.dat`: `0\t1.360763`, `1\t1.391853`, `21\t1.363779` (two tab-separated columns, node index then time, out of point order) | the per-node file the record declares exists only with `all = 0`. With `all = 1` the declared artifact is missing (reconciliation says so), and the reader refuses a two-column file by name |

## G. Further findings made while settling F

- **G1:** `spacedt` defaults to 3 ms and is bounded by `[dt/1000, tend]`. With
  `tend = 2` the run fails: `*** spacedt = 3 is above the 2 maximum`. openCARP
  checks cross-parameter bounds when it reads parameters, and `+Help` shows
  them as `min:`/`max:` expressions. The catalog keeps those expressions
  verbatim; the validator evaluates only numeric bounds.
- **G2:** `dt` is in **µs** and `tend` in ms (`run.py`: `--dt` in µs, and the
  run header). A study value for `dt` is in µs.
- **G3:** **every run log starts with the build header, including a CI token**
  (A8). omniD keeps solver stdout in `workflow_logs/`, so the token would be
  copied into every run record. The adapter redacts it before logs are written
  (plan Task 7). **Corrected 2026-09-25 (wave-2 review M1):** core redacts it
  (`workflow_runner.redact_step_logs`, K9, Task 12), after the step's process
  ends and before anything reads the kept log, using the pattern the plugin
  declares (`environment.REDACTION_PATTERNS`); every match is replaced whole
  (review I3). `test_no_token_survives_in_workflow_logs` proves it on a real
  run.
- **G4, a first benchmark number:** at dx 500 µm and dt 50 µs, with tend 150
  (as `run.py` uses for dx 500), P1 (the origin, point 0) activates at
  1.355 ms and P8 (the far corner, point 4304) at **126.45 ms**. All 4305
  points activate. The run takes 1.7 s. This is evidence for the later
  benchmarker topic, not a reference value.
- **G6, the allocation block:** `+Help num_stim` lists, under `Changes the allocation of: {`, the arrays that count sizes: `stim` and `stimulus` (lines without `[`), then their members. This is how a count key maps to its arrays, taken from the binary.
- **G7, defaults that make an unpinned run slow:** `mesher` resolution defaults to 100 µm (the slab would be about 420k points); `tend` defaults to 100 ms and `dt` to 5 µs. A conformance or test run pins `dx`, `tend` and `dt`.
- **G5:** `run.py`'s example flow passes `-dt`, `-tend` and `-mass_lumping` on
  the command line. They are ordinary `.par` parameters, so omniD writes them
  into the staged `nversion.par`, keeping one source of values: the case.
- **G8, the benchmarker's step-2 proof (2026-09-26, spec `2026-09-26-results-as-quantities-design.md`
  Task 6):** `test_an_agent_compares_dx_500_with_dx_250_at_the_paper_points`
  runs `niedererNVersion` at dx 500 and dx 250 (dt 50 µs, tend 150 ms) through
  `sweep-run`, reads all nine of `benchmarks/niederer2011.json`'s resolved
  points (P1-P9) through the LAT reader (artifact `record.solve.2`, format
  `opencarp_lat_per_node`), and compares them with a pre-registered
  `omnidriver compare` request (absolute tolerance 5 ms). Evidence for the
  benchmarker, not a reference value, like G4: P1 (nearest the stimulus)
  agrees closely (dx 500 1.355495 ms vs dx 250 1.355191 ms,
  `within_tolerance`); P8 (the far corner) is dx 500 **126.454889 ms**
  (matching G4) vs dx 250 61.989965 ms; P9 (the centre) is dx 500 55.776783 ms
  vs dx 250 27.536149 ms. Every point but P1 comes back `outside_tolerance` —
  the coarse mesh's diagonal conduction disagrees substantially with the
  finer one, which is what a spatial-refinement comparison is expected to
  show, not a defect in the pipeline. The report's overall `status` is
  `failed`, exactly as it should be reported; each case's
  `ExperimentCase.comparison.association_status` (via
  `experiment_comparisons`) reads `run_verified` for both. The proof is that
  the pipeline reports correctly, not that the two resolutions agree.
- **G9, against cardiacFOAM (2026-09-26, topic B Task 8):**
  `niedererNVersion` at dx 500 µm, **dt 10 µs** and tend 200 ms, to match
  cardiacFOAM's step. It was compared with cardiacFOAM's `niederer2011` at
  the same dx and step by a pre-registered request. The table and setup are
  in `cardiacfoam.md` section X.
  - **The time step barely moves openCARP.** Its own values at dt 10 µs are
    P1 1.253986 ms, P8 126.268283 ms and P9 55.556030 ms. P8 is within
    0.2 ms of G4's dt 50 µs value, and P1 is 0.1 ms earlier.
  - The `solve` step took 9.6 s. Every P1-P9 is a slab node (offset 0).
- **G10, the mass matrix (2026-09-27, the Niederer campaign,
  `benchmarks/niederer2011/campaign/`).**
  - **What the binary does by default.** `openCARP +Help mass_lumping`
    reports `default:(Short)(1)`, "Lump mass matrix"; 0 means "Use full
    mass matrix".
  - **What the native driver does.** `03E_study_resolution/run.py` has
    `--massLumping` with default 0, and always passes `-mass_lumping`. Its
    tutorial text says lumping gave the biggest inaccuracies among the
    paper's finite-element codes.
  - **What the record does.** `niedererNVersion` passes nothing, and
    `nversion.par` has no `mass_lumping` line. So every omniD run before
    the campaign was lumped: G4, G8, G9, Task 8 and PAR's I7.
  - **The campaign states it.** Its study sets `nversion.par:mass_lumping
    0`, and the staged `out/parameters.par` echoes `mass_lumping = 0`.
  - **The effect** at dx 500 µm, dt 10 µs, tend 200 ms: P8 is
    **58.144 ms** with the full mass matrix (campaign, case_0002),
    against **126.268 ms** lumped (G9). P9 is 24.901 ms against
    55.556 ms. The full-mass P8 at dx 500 is already closer to the
    paper's finest-level range (37.8-48.7 ms) than the lumped P8 at dx
    250 (61.99 ms, G8).
  - **The cost.** The dt 10 µs solve took 16.3 s with the full mass matrix,
    against 9.6 s lumped (G9).
  - **Conclusion.** A study that wants run.py's benchmark configuration
    names `nversion.par:mass_lumping 0`; the record does not supply it.
    Whether the record should is a record question, not settled here.

## H. omniD drives openCARP

Task 11: `OpenCARPPlugin` (`packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py`)
and the `niedererNVersion` record (`.../records/niederer_n_version.py`), run
against the real `openCARP` v18.1 binary and its own
`02_EP_tissue/03E_study_resolution` tutorial. All ten conformance checks
(`omnidriver.conformance.CHECKS`) pass, with `base_study = {dx: 1000.0,
nversion.par:tend: 10.0, nversion.par:dt: 50.0}` (G7: pinned for a short run).
No core file changed (`packages/omnidriver/src` untouched by this task); see
the generality log's 2026-09-25 "no core change needed" row. **Corrected 2026-09-25
(wave-2 review M1, I4):** true of Task 11 alone, not of the wave: Task 10a
(the record surface, C10) and Task 12 (K9 log redaction) changed core, and
the review's fixes changed it three more times (I2, I3, I4); each has its own
generality-log row.

| check | verdict detail |
|---|---|
| C1 | stack `['org.omnidriver.opencarp']`, root `org.omnidriver.opencarp` |
| C2 | no changes proposed |
| C3 | refused: validating `nversion.par:gregion[0].g_ill` raised `TutorialRecordError`: `nversion.par:gregion[0].g_ill` is not an openCARP v18.1 parameter |
| C4 | patched one key; its sibling is unchanged |
| C5 | ok; launch `['.../bin/python', '-m', 'omnidriver', 'run', '--plugin', 'opencarp', '--run-document', '.../scratch/records/niedererNVersion/run_document.json']` |
| C6 | 5 declared artifact(s) present |
| C7 | 2 cases completed and reconciled; native tree unchanged |
| C8 | 2 consumed file(s) fingerprinted |
| C9 | clean; names the missing solver |
| C10 | 1 axes, 250 keys, 1 guidance item(s) (a dated run record: since wave-2 review I1 the catalogue omits the command-owned keys, and C10 now reports 247; note added 2026-09-25, final review S-M5) |

Each check's own suite run (fresh scratch dirs under `/tmp`, sequential):
6.40 s total for all ten. The full native `pytest -m native` (since 2026-09-25, final review S-I1: `-m native_opencarp`) suite for this
package (the ten checks plus `test_committed_catalog_matches_the_binary` and
`test_every_shipped_par_round_trips`) took 39.57 s wall time.

**C6/C7 needed one addition the brief flagged as conditional:** without
`is_case_runnable_without_workflow`, `run_document_exec` refused every staged
case with `case_root_not_a_runnable_case` before it reached the solver
(`legacy_case_runnable_without_workflow`'s default is `False`, and this
plugin declares no `case_compatibility` capability member otherwise). Added
`is_case_runnable_without_workflow(self, case_root)` returning whether
`nversion.par` is present in the staged case -- the same shape as the
`E2ERecordPlugin` example the brief names. This is a plugin-side addition,
not a core change.

**Corrected 2026-09-25 (wave-2 review I4):** the addition was a workaround,
not a fit. The hook's contract is whether a case *without* driver-owned
workflow metadata is runnable, and a record run's document carries its steps,
so core should not have asked. Core now exempts such a run from that gate
(`run_document_exec._is_record_run_with_steps`), and the hook is deleted from
`OpenCARPPlugin`; all ten checks still pass on the real binary without it.

## I. Parallel runs (PAR, owner Q6, 2026-09-26)

**Question:** does `mpirun -np N openCARP ...` keep the serial outputs (the
LAT file and `vm.igb`) in the same layout and location, and where does N come
from? openCARP v18.1, macOS arm64, 14 cores; the `03E_study_resolution` case
copied into the session scratchpad, meshed with F3's `mesher` line. Every log
was read with `grep -v "://"`, so the build header's token (G3) was never
printed or copied.

| # | command | observed | conclusion |
|---|---|---|---|
| I1 | `otool -L /usr/local/lib/opencarp/bin/openCARP \| grep -i mpi`; `ls /usr/local/lib/opencarp/lib/petsc/bin`; then that directory's `mpirun --version`; `/opt/homebrew/bin/mpirun --version` | links `/usr/local/lib/opencarp/lib/petsc/lib/libmpi.12.dylib` (MPICH's ABI name); the bundle ships `mpirun`/`mpiexec` → `mpiexec.hydra`, "HYDRA build details: Version 4.0.1"; Homebrew's is "mpirun (Open MPI) 5.0.9", the one OpenFOAM uses (`WM_MPLIB=SYSTEMOPENMPI`) | **openCARP is built against its own bundled MPICH, not the machine's Open MPI.** Two MPIs on one machine: each solver needs its own launcher |
| I2 | `/opt/homebrew/bin/mpirun -np 2 openCARP +F nversion.par -meshname slab -simID ompi2 -imp_region[0].im_sv_init singlecell.sv -tend 20 -dt 50` (dx 1000); again with `PETSC_OPTIONS=-log_view` | exit 0; the log holds **two** build headers, every stage twice, and `L2 : Output directory exists: ompi2`; `vm.igb` and the LAT file are **byte-identical to the serial run**; `-log_view` prints `openCARP on a  named macbook with 1 processor` **twice** | **another MPI's launcher starts N separate one-process runs of the whole problem, racing on one output directory, and nothing fails.** Its outputs equal the serial run's, so a serial-against-parallel comparison would pass without any parallel run. This has to be checked, not assumed |
| I3 | the bundle's `mpirun -np 2 openCARP ...` (as I2) | exit 15: `MPID_nem_tcp_get_business_card ... GetSockInterfaceAddr: gethostbyname failed, macbook`. `python3 -c "socket.gethostbyname('macbook')"` fails; `macbook.local` resolves to 127.0.0.1. `MPIR_CVAR_CH3_INTERFACE_HOSTNAME=127.0.0.1` (or `macbook.local`) still fails with the same message; `HYDRA_USE_LOCALHOST=1` fails; `mpirun -hosts 127.0.0.1 -np 2 ...` and `HYDRA_IFACE=lo0 mpirun -np 2 ...` both **exit 0** | **this machine's host name does not resolve, which MPICH's TCP channel needs.** Hydra sets the interface host name for each process itself, so the MPICH variable is overridden; hydra's own `HYDRA_IFACE=lo0` is the ambient fix. A machine fact, supplied in the environment, not by omniD. (Also: `/usr/bin/env VAR=... mpirun` loses `DYLD_LIBRARY_PATH`, since macOS strips `DYLD_*` when it starts a protected binary; export it instead) |
| I4 | `PETSC_OPTIONS=-log_view HYDRA_IFACE=lo0 <bundle>/mpirun -np 2 openCARP ... -tend 5`, vs I2's Open MPI line | bundle: `openCARP on a  named macbook with 2 processors`, once; Open MPI: `with 1 processor`, twice | PETSc's own report of the world size: the bundle's launcher gives one 2-process run |
| I5 | the header, counted, for `<launcher> -np <n> openCARP +Default` in an empty directory (it initialises MPI, prints the header, then fails for want of `project.elem`), and for `-buildinfo` | `+Default`: bundle n=2 → **1**, n=3 → **1**; Open MPI n=2 → **2**, n=3 → **3**; serial → 1. `-buildinfo`: 2 under both launchers (it prints before MPI is initialised) | **the build header is printed once per MPI world**, so `+Default`'s header count tells one N-process run from N one-process runs, in well under a second and with no case. This is the preflight check `parallel.launcher_diagnostics` makes (`opencarp_mpi_launcher_mismatch`); `-buildinfo` cannot tell them apart |
| I6 | dx 1000, tend 20, dt 50: serial vs `HYDRA_IFACE=lo0 <bundle>/mpirun -np 2` | exit 0; the same nine files in the `-simID` directory; `vm.igb` and `init_acts_vm_act-thresh.dat` **byte-identical** (md5); `parameters.par` differs only in the `simID` line and the echoed command | at this size the parallel run reproduces the serial one exactly |
| I7 | dx 500, tend 150, dt 50 (G4's case): serial, then the bundle's `-np 2` and `-np 4` | all exit 0, about 2 s each (too small to speed up); the same nine files in each `-simID` directory; LAT file 4305 lines each, in the serial node order (line 1 `1.355495` = P1, line 4305 `126.454889` = P8, as G4), max \|difference\| **1e-6 ms** against serial for both, i.e. the last printed digit, with no `-1` mismatch; `vm.igb` header identical (`x:4305 ... t:151`), size identical (2601244 bytes), max \|ΔVm\| 5.3e-5 mV (np 2) and 6.3e-5 mV (np 4), about 3% of values differ | **the outputs keep their layout, node order and location in parallel**: PETSc partitions internally and rank 0 writes the canonical order into the same `-simID` directory; there are no per-rank files. The values differ only by the parallel solve's reduction order, below the LAT file's printed precision. The record's `produces` and the LAT reader need nothing new |
| I8 | omniD, `plan --strict --plugin opencarp --entry niedererNVersion --parallel 2` (dx 1000), three environments | Homebrew's Open MPI first on PATH: `opencarp_mpi_launcher_mismatch`, "'mpirun' (/opt/homebrew/bin/mpirun) started 2 separate one-process openCARP runs"; the bundle first, no `HYDRA_IFACE`: the same code, "could not start 2 openCARP processes: ... gethostbyname failed, macbook"; the bundle first with `HYDRA_IFACE=lo0`: no error. A `sweep-run` of the first environment fails the case before openCARP runs (no `out/`) | preflight refuses both wrong environments by name, before a run |

**Where N comes from.** openCARP has no decomposition dictionary: nothing in
its case states a process count, so N is not a case fact. It is either the
scheduler's allocation, which is ambient (`SLURM_NTASKS`, read by core only
when a run asks for parallel), or a count the agent supplies with the request
(`parallel: N`, `--parallel N`). `parallel: true` uses the allocation and is
refused by name outside a scheduler; a supplied N that disagrees with an
ambient allocation is refused by name. Neither is ever restated or
overridden (`parallel.parallel_steps`).

**The proof on the real binary** is `test_parallel_native.py`: `niedererNVersion`
at dx 500, tend 150, serial and `parallel: 2` through `sweep-run`, P1-P9 read
through the LAT reader at `benchmarks/niederer2011.json`'s points, equal within
1e-5 ms (ten units of the printed last digit); the parallel solve log states
`with 2 processors` and one header; the file set, LAT length and `vm.igb` header
match. It needs the bundle's launcher first on PATH and, on this machine,
`HYDRA_IFACE=lo0` (I3), and fails, naming the diagnostic, without them.

## J. The Niederer cell and the mass matrix (2026-09-27)

The openCARP half of [`cardiacfoam.md`](cardiacfoam.md) S, which holds the
parameter table and the verdict. `bench` and `openCARP` need
`DYLD_LIBRARY_PATH=/opt/homebrew/lib`.

| # | probe | observed | conclusion |
|---|---|---|---|
| J1 | `bench -I tenTusscherPanfilov -p "flags=EPI" -R niederer.sv --stim-curr 35.7142857 -T 2 --stim-start 10 --numstim 1 --duration 510 --dt 0.005 --dt-out 0.005 --fout=sv` (`niederer.sv` = the tutorial's `singlecell.sv`); again without `-R` | with `.sv`: Vrest −85.25 mV, peak 55.0 mV, max dV/dt 360 mV/ms, 0 mV at 1.223 ms, APD90 289.8 ms. Without: −86.04, 57.3, 390, 1.228, 300.3 | the Niederer cell. `--fout=` needs the `=`: `-O name` is ignored and output goes to `BENCH_REG.txt` |
| J2 | read `openCARP.prm`, `electric_integrators.cc`, `electrics.cc` | `bidm_eqv_mono` defaults to 1 (harmonic mean per direction); Cm fixed at 1.0 µF/cm²; a transmembrane stimulus is applied unscaled in µA/cm² | σ, Cm and stimulus match the paper |
| J3 | 15 mm cables, Δt 0.01 ms, full / lumped mass, dx 10, 50, 500 µm | along fibres 0.6073/0.6070, 0.6095/0.6018, 0.5772/0.4057 m/s; across 0.2217/0.2208, 0.2277/0.2097, 0.1139/blocked | at 0.5 mm, lumping costs about 30 % along the fibres and blocks conduction across them; the full mass matrix keeps 95 % and 51 % |
| J4 | dx 0.5 mm slab: full mass with `.sv`, full without, lumped | P8 58.14, 57.22, 126.27 ms | the initial state moves P8 by 0.9 ms; the mass matrix by 68 ms |
| J5 | `LatPerNodeReader` at dx 0.2 mm: P9 (10000, 3500, 1500) um is exactly equidistant from four nodes (a 200 um grid, y and z both landing on a half-step). The old nearest-node reader raised on every P1-P9 read for that mesh (one `read()` call answers all nine names, so one name's refusal failed the rest); the campaign's `cross_dx0.2_*` and `temporal_opencarp_dx0.2_*` reports (`runs/reports/`) are `unavailable` for exactly this reason. Fixed by reading `slab.elem` and returning the barycentric interpolation of the containing tet, re-read into `runs/reports-2026-09-28-interpolated/` | ms, dt 0.05/0.01/0.005: P1 1.354977/1.253536/1.242009, P2 28.546249/28.345679/28.318395, P3 31.985257/30.977199/30.84069, P4 41.343641/40.291864/40.154248, P5 8.855868/8.711875/8.694228, P6 29.06731/28.864362/28.836669, P7 33.028645/31.992794/31.852735, P8 41.659734/40.59073/40.450567, P9 19.4276045/18.8277115/18.7491775. Every value at dx 0.5 and 0.1 mm (every point a node there) is byte-identical to the old reports; `sampling_rule` there reads `linear` instead of `node`, `sampling_offset` 0 | the tie needed no rule once the reader returns the FE solution itself. Interpolation changes only the dx 0.2 mm openCARP side, and only by making it evaluable |

`run.py` (`03E_study_resolution`) passes `+F nversion.par`,
`-imp_region[0].im_sv_init singlecell.sv`, `-tend`, `-dt` (default 20 µs) and
`-mass_lumping` (default 0), and no linear-solver options. The
`niedererNVersion` record passes none of these; the campaign study supplies
`mass_lumping 0`.
