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
