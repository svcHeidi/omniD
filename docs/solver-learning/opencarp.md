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
| A8 | `openCARP -buildinfo` | `GIT tag: v18.1`, `GIT hash: 6eaa147d…`; also a CI repository URL with an embedded token (**redacted**) | version identity from the binary; build output can carry credentials |

## B. Self-description

| # | command | observed | conclusion |
|---|---|---|---|
| B1 | `openCARP +Help` | usage `openCARP [+Default \| +F file \| +Help topic \| +Doc] [+Save file]`, then about 265 parameter lines, e.g. `'-lats[Int].threshold' Float`, `-num_LATs Int` (272 lines in total) | full parameter list with types; indexed names appear as `[Int]` templates |
| B2 | `openCARP +Help bidomain` | description; `type: Short`; `default: (Short)(0)`; menu `0 Monodomain / 1 Bidomain / 2 Pseudo-bidomain` | per-parameter description, default and allowed values: **the catalog source** |
| B3 | `openCARP +Help 'lats[Int].threshold'` | prints the general list again, no detail | the template form is not accepted |
| B4 | `openCARP +Help 'stim[0].pulse.strength'` | description ("amplitude… uA/volume… mV"), `type: Float` | **a concrete index is required** for detail on indexed names |
| B5 | `openCARP +Help num_stim` | `type: Int`, `default: (Int)(2)`, `min: (Int)(0)`, `Changes the allocation of: {…}` | **surprising default: 2 stimuli.** Count keys allocate their indexed arrays |
| B6 | `openCARP +Default +Save defaults.par` | nothing written, exit 1 | no defaults export by this route |

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

| id | question | settling run | state |
|---|---|---|---|
| F1 | How is a `Flag` parameter written in a `.par`? | set a Flag in a `.par`, then read `parameters.par` and the behaviour | open |
| F2 | What does openCARP do with an indexed key beyond its count (`stim[1].*` with `num_stim = 1`)? Given B5, is it an allocation error or silently ignored? | a two-line `.par` experiment | open |
| F3 | Which `mesher` arguments reproduce carputils' `Block(size, resolution, centre)`? | compare point extents from `block.pts` with the tutorial's geometry | open |
| F4 | Are `run.py`'s `gen_physics_opts` region options needed for a one-tag slab, or do defaults suffice? | run with and without; compare `vm.igb` | open |
| F5 | How does `imp_region[0].im_sv_init` resolve when given case-relative in a staged clone? | run from a different working directory | open |
| F6 | What is column 1 of `*-thresh.dat`: a node index, sorted by time? | cross-check against `block.pts` order and a known activation order | open (added from D7) |
| F7 | Does a `.par` that omits `num_stim` really get two stimuli (B5), and what is the second one? | minimal `.par` without `num_stim`; inspect `parameters.par`/traces | open (added from B5) |
