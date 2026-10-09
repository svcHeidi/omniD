# Learning TorchCor: the evidence log

**Method:** [`method.md`](method.md). **Design it feeds:**
`docs/superpowers/specs/2026-10-09-torchcor-plugin-design.md`.
**Machine:** Apple M4 Pro, 24 GB, macOS, no CUDA. **Started:** 2026-10-09.

TorchCor is a Python API on PyTorch, not a binary. "The solver" below is the
installed `torchcor` package run in its own venv; every claim carries the
command (or script) that settled it. Run outputs live under
`/Users/simaocastro/omnid-runs/2026-10-09/torchcor/<probe>/` (each holds the
script that ran, `run.log` and `run.err`). Line numbers cite TorchCor at commit
`b02daee`, which pins them.

## A. Locate, install, run

| # | command | observed | conclusion |
|---|---|---|---|
| A1 | `git clone https://github.com/sagebei/torchcor ~/torchcor`; `git log -1` | `b02daee87d4283888981cbfc3a6b00f57789a820`, 2026-09-14, "fixed precision"; no tags (`git describe` prints the hash) | identity is a commit hash; the dist version is `1.0.6` (`pyproject.toml`) |
| A2 | `head -1 LICENSE`; README badge | `MIT License`, `Copyright (c) 2024 Bei Zhou`; badge "License-MIT" | **the repository says MIT, not CC BY-NC 4.0** as the design's open question 3 states. Which licence governs (the repo, or the paper's) is for the owner |
| A3 | `uv venv --python 3.11 ~/torchcor-venv`; `VIRTUAL_ENV=~/torchcor-venv uv pip install -e ~/torchcor` | success in 12.9 s; resolved `torch 2.14.1`, `gmsh 4.15.2` (wheel, ships the binary and `gmsh.py`), `pygmsh 7.1.17`, `meshio 5.3.5`, `nvidia-ml-py 13.615.71`, `vtk 9.7.1`, `pyvista 0.49.0`, `wfdb 4.3.1`, `scikit-learn`, `seaborn`, `pandas 2.3.3` | **the recipe works on a Mac with no CUDA.** `nvidia-ml-py` installs, and is imported only `if torch.cuda.is_available()` (`simulator/monodomain.py` l. 9-10), so it is inert here. `pygmsh` needs no system gmsh: the `gmsh` wheel provides it. `requirements.txt` pins different versions (`torch==2.7.1`, two conflicting `nvidia-ml-py` pins, plus `petsc4py`, `torch_geometric` not in `pyproject.toml`); it was not used |
| A4 | `python -c "import torchcor, torch; ..."` | first import 8.9 s, then 1.9 s; `torchcor.__version__` absent (`None`); `importlib.metadata.version("torchcor")` = `1.0.6`; `dir(torchcor)` = `device float32 float64 get_device set_device torch` | version from package metadata, not the module. Provenance must also record the commit, since `1.0.6` is all an editable install reports |
| A5 | the same, `torch.backends.mps.is_available()`, `torch.cuda.is_available()` | `True`, `False` | MPS exists on this machine; see D9 for whether TorchCor can use it |
| A6 | imports with `warnings.simplefilter("always")` | 12 × `FutureWarning: torch.jit.script is deprecated` (one per ionic model and the CG class); a `DeprecationWarning` for an invalid escape in `signalanalysis/.../general.py` | noise on stderr at every run; harmless today, a future torch may remove `torch.jit.script` |
| A7 | `pyproject.toml` `[tool.setuptools] packages` | lists `torchcor.core`, `.ionic`, `.simulator`, `.ecg`, `.tools`, ...; not `torchcor.mechanics` or `torchcor.utils` (neither has an `__init__.py`) | a non-editable install would omit those two directories; the N-version path does not use them |

## B. Self-description

| # | command | observed | conclusion |
|---|---|---|---|
| B1 | `inspect.signature` over `torchcor.simulator.Monodomain` public methods | `__init__(ionic_models, T, dt, device=None, dtype=None, mass_lumping=False)`; `load_mesh(path='Data/ventricle/Case_1', unit_conversion=1000)`; `add_conductivity(region_ids, il, it, el=None, et=None)`; `add_stimulus(vtx_filepath, start, duration, intensity, period=None, count=1)`; `solve(a_tol, r_tol, max_iter, linear_guess=True, snapshot_interval=5, verbose=True, result_path=None)`; `step(u, t, a_tol, r_tol, max_iter, verbose=False)`; `compute_activation_map(Vm, snapshot_interval=1.0, threshold=0, interpolate=False, save=False)`; also `assemble`, `compute_activation_map_dvdt`, `compute_repolarization_map`, `save_vm`, `vm_to_vtk`, `vm_to_igb`, `igb_to_vtk`, `phie_recovery`, `simulated_ECG` | **signatures and defaults are readable with `inspect`.** Only `phie_recovery` has a docstring; the class has none. Units are not in the code; the tutorial (`docs/tutorials/monodomain.rst`) states `T`, `dt` in ms, conductivities in S/m, `unit_conversion` dividing µm to mm |
| B2 | the same for `ReactionEikonal` | as Monodomain plus `diffusion=False, v_th=-50.0, t_foot=5.0, tau_foot=0.7`, `add_velocity`, `eikonal_activation_times`, `set_diffusion_current`; `solve` has defaults `a_tol=1e-05, r_tol=1e-05, max_iter=100` that Monodomain's lacks | sibling simulator, same shape |
| B3 | `torchcor.ionic.__all__` and `inspect.signature(cls.__init__)` | 10 models: `AlievPanfilov, BuenoOrovio, CourtemancheRamirezNattel, MitchellSchaeffer, ModifiedMS2v, OHaraRudy, TenTusscherPanfilov, Tomek19, Tomek20, TWorld`. All take `dt`, `device=cpu`, `dtype=float64`; all but `AlievPanfilov` take `region_ids=None`; string options: TTP `cell_type='EPI'`, OHaraRudy `cell_type='ENDO', ina='ORdINa', formulation='ORIGINAL'`, BuenoOrovio `formulation='TRANSFORM'`, Tomek19/20 `cell_type='ENDO'`, TWorld `cell_type='ENDO', sex='MIX'` | the model menu is `__all__`. Under `@torch.jit.script` outside scripting the classes are plain Python `type`s, so `inspect` works |
| B4 | `grep cell_type torchcor/ionic/TenTusscherPanfilov.py` | l. 100-101: `GKs_init = 0.392 if cell_type == "EPI" else 0.098 if cell_type == "MCELL" else 0.392`, `Gto_init = 0.294 if "EPI" else 0.294 if "MCELL" else 0.073`; l. 274 `if self.cell_type=="ENDO"` | **string menus are not in signatures**; they are the literals the code compares (`EPI`, `MCELL`, `ENDO`). Any other spelling (`"epi"`) is accepted silently and gets a mixture (ENDO's `Gto`, non-ENDO `tau_S`). A validator must refuse it from the compared literals, the counterpart of the C++ compared-literal scan |
| B5 | `m = TenTusscherPanfilov(dt=0.005)`; `[a for a in dir(m) if a.endswith('_init')]` | 24 attributes (`V_init=-86.2`, `Cai_init=7e-05`, `CaSR_init=1.3`, `Nai_init=7.67`, `Ki_init=138.3`, ...) | **the initial state is instance attributes set in `__init__`, not parameters.** A catalogue can read them by instantiating the model; `inspect.signature` cannot |
| B6 | `m.V_init = -85.23`; `m.not_an_attr = 1` | both succeed silently | **a misspelt attribute is silently ignored.** The runner must refuse a `case.json` init key that is not an existing `*_init` attribute |
| B7 | `TenTusscherPanfilov(..., mass_lumping=True)` (an accidental probe, `d8_library_lumped/run_badsed.err`) | `TypeError: TenTusscherPanfilov.__init__() got an unexpected keyword argument 'mass_lumping'` | unknown constructor keywords are refused, unlike attributes |
| B8 | read `Monodomain.__init__` (l. 22-56) | `dtype` default `float64`; `device` default `tc.get_device()` = CUDA else CPU (never MPS); `Chi = 140`, `Cm = 0.01`, `theta = 0.5` are attributes, not parameters | **defaults a reader would not assume:** `theta` (0.5, Crank-Nicolson) differs from the N-version benchmark's 1 (C/`__main__`); `Chi`, `Cm`, `theta` are invisible to a signature scan; the CG solver is built with `dtype=torch.float64` regardless of the simulation dtype (l. 146) |
| B9 | read `Conductivity.add`, `Stimuli.add/apply` | `el`/`et` given: monodomain sigma is the harmonic mean `il*el/(il+el)`; no `add_conductivity` call leaves sigma zero (no error); stimulus active while `start <= t mod period <= start+duration` and `t/period <= count`; `add_stimulus` reads a `.vtx` file (count, a header line, node indices) and has no geometric form | a stimulus must be a file. A case that forgets conductivities runs and never propagates; preflight must require it |
| B10 | `python -c "print(int(0.3/0.1))"` (Python, against `solve`'s `ts_per_frame = int(snapshot_interval / self.dt)`, l. 201) | `2` | a `snapshot_interval` that is not an exact float multiple of `dt` silently samples at the wrong interval; the runner should not depend on `snapshot_interval` (see D10) |

## C. Native examples

Every example is a script. None ships a mesh: all read from
`~/Data/...`, `/home/bzhou6/...` or `/app/...`, absent here. No example is
file-native, so the case must be built from a script's facts (method step 9).

| file | simulates | physics lives in | mesh source | outputs |
|---|---|---|---|---|
| `verification/benchmark.py` | Niederer N-version slab, TTP EPI, dx 0.5/0.2/0.1 | `__main__` plus its **own** `Monodomain` class and its own `verification/TenTusscherPanfilov.py` | generated in `load_mesh` with `pygmsh` (20×7×3 mm, `mesh_size=dx`) | `activation_time.pdf` (plot of the diagonal); activation held in memory only |
| `verification/benchmark_quant.py` | the same | the same; differs only in `dtype=float64`, `dx in [0.1]`, labels | as above | as above |
| `verification/TenTusscherPanfilov.py` | TTP copy used by the benchmark | module | — | `V.png` when run |
| `verification/manufactured_2d.py`, `_copy.py`, `laplance_2d.py` | 2-D manufactured-solution and Laplace convergence | script | `scipy.spatial.Delaunay` in code | plots, VTK/GIF |
| `verification/conjugate_gradient.py` | CG versus PETSc | script | reads `A.pt`, `b.pt` (absent) | residuals; needs `petsc4py` (not installed) |
| `verification/plot.py` | plots a hard-coded manufactured-solution error table | script | — | `convergence.pdf` |
| `demo/monodomain_ventricle.py`, `eikonal_ventricle.py` | BiV, TTP ENDO, 5 pacing sites | script | `~/Data/ventricle/Case_1` (CARP files) | `solve(result_path=...)`, AT/RT maps |
| `demo/monodomain_atrium.py`, `eikonal_atrium.py`, `docker/main.py` | atrium, CRN / ModifiedMS2v | script | `/home/bzhou6/Data/atrium/...`, `/app/...` | as above |
| `demo/linear.py` | atrium, 5 CRN regions, 16+ pacing beats | script | `/home/bzhou6/Data/Mesh_12928433` | as above |
| `demo/ecg_12lead.py` | BiV + torso lead field | script | `~/Data/torso/HC2` | `ecg_12lead.png` |
| `benchmark/torchcor/mesh_volume.py`, `mesh_surface.py` | write the slab (volume) / a surface as CARP files at 11 sizes | script | `pygmsh` → `~/Data/volume/<n_nodes>/0.{pts,elem,lon,vtx}` in µm | mesh files |
| `benchmark/torchcor/volume.py`, `surface.py` | performance runs on those meshes | script | the files above | none. **Stale against the current API:** `add_condutivity` (typo), `solve(plot_interval=..., format=...)` (not parameters), a bare model instead of a list for `ionic_models` |
| `benchmark/opencarp/*` | openCARP counterparts (`.par`, Slurm scripts, an `mMS` ionic model) | `.par` files | external | — |
| `notebooks/*.ipynb` (12) | heat-equation FEM/FDM/PCG teaching notebooks; `Monodomain.ipynb` imports a pre-package layout (`ionic`, `mesh.materialproperties`); `IGB.ipynb` reads `/home/bzhou6/Downloads/...` | notebook | in-notebook or absent | — |
| `docs/tutorials/*.rst`, `docs/quickstart.rst` | API walk-throughs (monodomain, reaction-eikonal, ECG) | prose + snippets | `/path/to/...` | — |

- **C1, read end to end: `verification/benchmark.py`.** Its `__main__`
  (l. 201-278) sets `dt = 0.005`, `dtype = float32`, TTP EPI with 19 initial
  values (l. 208-226), `il 0.17, it 0.019, el 0.62, et 0.2` (l. 228-231),
  `T = 150` (l. 236), and per dx `Chi = 140`, `Cm = 0.01`, **`theta = 1`**
  (l. 243-245). Its `Monodomain` stimulates nodes with x, y, z ≤ 1.5 mm at 50
  (divided by 100) while `ctime <= 2.0` (l. 80-84, 158, 179-180), records
  activation at the first step with `u > 0` only on nodes near the P1-P8
  diagonal (l. 96-116, 188), and stops when P8 exceeds 0 mV (l. 198).
- **C2, defects found:**
  - `et = 0.2`, where Niederer 2011 Table 1 and openCARP's `nversion.par`
    (`opencarp.md` C4) use 0.24;
  - the diagonal tolerance is defined only for dx ∈ {0.1, 0.2, 0.5}, and any
    other dx raises `NameError` (l. 100-105);
  - P2-P7 are never recorded;
  - its TTP copy lacks the library's 2026-09-11 fix `a517084` "fixed CaSS_tab"
    (`CaSS_tab[:, CaSS2_idx] = CaSS*CaSS`), and differs in the `Cai` ×1e3/×1e-3
    scaling and in `torch.compile`;
  - its CG runs in the simulation dtype (float32), while the library's always
    runs in float64.

## D. Smallest real run, and its outputs

| # | command | observed | conclusion |
|---|---|---|---|
| D1 | `d1_benchmark_dx05/`: `benchmark.py` copied with `TenTusscherPanfilov.py`; diff (`benchmark.diff`): `dx in [0.5]`, a wall-time print, a dump of P1/P8 and the diagonal to `activation_dx0.5.npz`, the PDF renamed. `/usr/bin/time -p python benchmark.py` | exit 0; mesh 3675 nodes, 16062 tets; 34 diagonal nodes; 8062 steps (stopped at t = 40.31 ms); **solve 11.6 s, process 17.2 s** (user 13.7, sys 15.0) | real runs are affordable on CPU at dx 0.5 |
| D2 | the same, P1/P8 | **P1 0.955 ms, P8 40.31 ms** (float32, θ = 1, et 0.2, consistent mass) | first numbers; see the comparison below |
| D3 | `d1_.../rerun/`: the same script again; `np.array_equal` on every array; `diff run.log` | activation, distance, node and vertex arrays identical; logs differ only in the wall-time line | **CPU runs are deterministic run to run**, mesh generation included |
| D4 | the npz vertices | extents (0,0,0)-(20,7,3); each of the 8 corners is exactly one node; the nearest node to P9 (10, 3.5, 1.5) is (9.75, 3.39, 1.5) | **the frame matches `niederer2011.json`** (origin P1, axis 1 = 20 mm fibre edge, axis 2 = 7 mm, axis 3 = 3 mm); P1-P8 are exact nodes, P9 is not one at dx 0.5 |
| D5 | `d2_library_dx05/run_library.py 45 float32 cpu`: the slab written as CARP files exactly as `mesh_volume.py` does (µm; `Tt ... 0`; `.lon` header `1`, rows `1 0 0`; `stim.vtx` of the 40 nodes with x, y, z ≤ 1500 µm), then `Monodomain([TTP EPI + the 19 init values], T=45, dt=0.005, float32)`, `theta = 1`, `load_mesh(unit_conversion=1000)`, `add_conductivity(None, 0.17, 0.019, 0.62, 0.2)`, `add_stimulus(stim.vtx, 0, 2, 50)`, `solve(1e-5, 1e-5, 1000, snapshot_interval=dt)`, `compute_activation_map(threshold=0, save=True)` | exit 0; P1 0.950, P2 21.465, P3 33.100, P4 38.075, P5 6.475, P6 22.270, P7 33.665, **P8 40.380** ms; solve 22.0 s, of which the first step took 15.6 s | **the library API runs the N-version case** from files; the first step pays a `torch.compile` of the TTP `differentiate` |
| D6 | `d5_library_dx05_rerun/`: D5 again | solve 9.4 s (ionic 5.6 s vs 18.2 s); `ATs` array identical; `.pts` and `.elem` byte-identical | **the compile is cached across processes** in `/var/folders/.../T/torchinductor_simaocastro` (from `torch._inductor.runtime.cache_dir_utils.cache_dir()`): ambient state outside the case. Results did not change with it |
| D7 | `find out -type f` after D5 (with `vm_to_vtk(step=2000)`) | `solve()` wrote nothing; `compute_activation_map(save=True)` wrote `out/ATs.pt` (a float32 tensor of 3675, `torch.load`able, NaN = never activated); `vm_to_vtk` wrote `out/Vm_vtk/ms_<i*snapshot_interval>.vtk` and `out/ATs.vtk` (legacy VTK 5.1, BINARY, UNSTRUCTURED_GRID, float points in mm) | **nothing is written unless asked**; `result_path` is only remembered. No file records the configuration that ran: unlike openCARP's `parameters.par`, provenance must come from the runner |
| D8 | compare D2 with D5 | P1 0.955 vs 0.950; P8 40.31 vs 40.38 | two separate differences, settled in D9-D11 |
| D9 | `d3_benchmark_dx05_f64/` (benchmark.py, `dtype = float64` only); `d4_library_dx05_f64/` (D5 in float64) | benchmark f64: P1 0.955, **P8 40.385**; library f64: P1 0.950, P8 40.375 | the 0.075 ms P8 gap is **benchmark.py's float32 CG**; in float64 the two agree to the recording convention and 0.005 ms |
| D10 | `d11_library_step_loop/`: D5 with `solve()` replaced by `assemble()`, `im.initialize`, `cg.initialize`, then a loop over the public `step()` that stamps `t` at the first step with `u > 0` | every node's time is **exactly +0.005 ms** (one dt) from D5's `compute_activation_map`; P8 40.385; solve 8.6 s; memory one state vector | **convention:** `compute_activation_map` returns the last frame at or below threshold (`crossing * snapshot_interval`); benchmark.py returns the first step above it. The step loop matches benchmark.py's convention and needs no `(nt+1) × N` history (D5's `Vm` was 9001 × 3675; at dx 0.1 that history is infeasible) |
| D11 | `d10_library_verifTTP_f64/`: D9's library run with `verification/TenTusscherPanfilov.py` swapped in (`region_ids = None`, `construct_tables()` called) | P8 40.380, P1 0.950; all P1-P8 equal benchmark f64 minus one dt | **the library `Monodomain` reproduces benchmark.py's class exactly** given the same ionic model; the residual 0.005 ms is the library TTP (the CaSS fix and/or compiled vs eager), not the simulator |
| D12 | `d6_library_mps/`: D5 with `device=mps`, T = 1 | exit 1 in `Monodomain.assemble`: `NotImplementedError: Could not run 'aten::_to_sparse_csr' with arguments from the 'SparseMPS' backend` | **MPS cannot run TorchCor** (torch 2.14.1). Devices here: `cpu` only. Not forced further |
| D13 | `d7_library_theta_default/`: D5 without `sim.theta = 1` | P8 40.400 (P2-P7 within 0.025 ms of D5) | the θ default moves P8 by 0.02 ms at dx 0.5; a case must still state it |
| D14 | `d8_library_lumped/`: D5 with `mass_lumping=True`, T = 60 then 120 | T = 60: P4, P8 and 170 other nodes not activated; T = 120: P3 47.635, P4 64.110, **P8 68.120** ms | **mass lumping (which the tutorial recommends as "correct") changes P8 at dx 0.5 by 28 ms.** benchmark.py does not lump; `mass_lumping` is a first-class case key |
| D15 | `d9_benchmark_dx02/`: benchmark.py with `dx in [0.2]` only | 44 861 nodes, 239 328 tets, 21 diagonal nodes; **P1 0.955, P8 37.65 ms**; solve 108.6 s, process 116.3 s | dx 0.2 is about 2 minutes on CPU: 12.2× the nodes cost 9.4× the time |

**Against `benchmarks/niederer2011.json`, informally.** The reference publishes
only one value: P8's range across codes at dx 0.1, dt 0.005, which is
[37.8, 48.7] ms. TorchCor's benchmark settings (float32, et 0.2, θ 1, consistent
mass) give P8 = 40.31 ms at dx 0.5 and 37.65 ms at dx 0.2. Neither run is at the
reference's resolution, so neither is a comparison. P8 falling as dx is refined
is the opposite of the benchmark paper's usual trend (coarse meshes conduct too
slowly). That is consistent with the tutorial's note that the consistent mass
matrix "conducts ~35% too fast", but no run here settles it. P1 is 0.955 ms
(0.950 by the library's convention) at both resolutions.

## E. Mapping onto omniD

| omniD noun | TorchCor | evidence |
|---|---|---|
| native case | none ships (C). A `case.json` plus the mesh, either as CARP files (`.pts` µm, `.elem`, `.lon`, `.vtx`) or generated by the runner from `dx` with `pygmsh` | C, D5 |
| study key | `case.json:<key>` (keys below) | — |
| axis | `dx` (mm, `pygmsh` `mesh_size`; the mesh must then be generated, not supplied); `dt` (ms) | D1, D15 |
| key validator | `inspect.signature` of the callables the runner uses (B1, B3) **plus** what a signature cannot show: the `*_init` attributes read from an instance (B5), the literal menus from the source (B4), and the `Chi`/`Cm`/`theta` attributes (B8) | B1-B8 |
| reader | the runner's activation output: ms at node coordinates in mm, frame as `niederer2011.json` | D4, D10 |
| workflow steps | one: `python3 run_case.py case.json` in the TorchCor venv | D5, D10 |
| artifacts | whatever the runner writes. TorchCor writes only on request (`ATs.pt`, VTK) | D7 |
| environment | `TORCHCOR_VENV`; the device; and an ambient compile cache (`torchinductor_<user>` under the system temp dir) | A3, D6, D12 |
| parallelism | none: one process, no MPI. `device` is the only placement choice; `cpu` is the only one that works here. The record is `serial_only` | D12 |

**Proposed `case.json` keys** for the N-version run. Each value is traced to
`verification/benchmark.py` at `b02daee` unless marked otherwise:

| key | value | source |
|---|---|---|
| `device` | `"cpu"` | `__main__` l. 204 (`cuda:0` if available else `cpu`) |
| `dtype` | `"float32"` | l. 205 (`benchmark_quant.py`: float64) |
| `dt_ms` | `0.005` | l. 202 |
| `t_end_ms` | `150` | l. 236; the class also stops once P8 > 0 mV (l. 198) |
| `dx_mm` | `0.5` (axis: 0.5, 0.2, 0.1) | l. 242 |
| `slab_mm` | `[20, 7, 3]` | `Monodomain.load_mesh` l. 61-63 |
| `ionic_model` | `"TenTusscherPanfilov"` | l. 207; menu = `torchcor.ionic.__all__` |
| `ionic_options` | `{"cell_type": "EPI"}` | l. 207; menu from the compared literals (B4) |
| `ionic_init` | the 19 values `V_init: -85.23` ... `Ki_init: 136.89` | l. 208-226; keys must be existing `*_init` attributes (B5, B6) |
| `conductivity_S_per_m` | `{"il": 0.17, "it": 0.019, "el": 0.62, "et": 0.2}` | l. 228-231 (Niederer: `et` 0.24, C2) |
| `chi_per_mm`, `cm_uF_per_mm2` | `140`, `0.01` | l. 243-244 (also the library defaults, `Monodomain.__init__` l. 54-55) |
| `theta` | `1` | l. 245 (library default 0.5, B8) |
| `mass_lumping` | `false` | absent from benchmark.py (equals the library default); D14 shows it decides P8 |
| `stimulus` | `{"box_mm": [[0,0,0],[1.5,1.5,1.5]], "start_ms": 0, "duration_ms": 2.0, "intensity": 50}` | l. 80-84, 158, 179; the library form is a `.vtx` the runner writes from the box (D5) |
| `cg` | `{"a_tol": 1e-5, "r_tol": 1e-5, "max_iter": 1000}` | l. 249-251 |
| `activation_threshold_mV` | `0` | l. 188 (and the reference's definition) |
| `probe_points` | P1-P8 from `benchmarks/niederer2011.json` | the benchmark records only the diagonal (C2); D4 shows the corners are exact nodes |

**Verdict: the runner uses the library `torchcor.simulator.Monodomain`, not
benchmark.py's class.**

- With the same ionic model, the library class reproduces benchmark.py's class
  exactly, up to a one-dt recording convention (D11).
- It carries the library's fixed TTP (C2).
- Its CG is float64 whatever the simulation dtype (D9).
- It is the public, versioned API, so a signature scan can catalogue it.
- The runner must still own three things:
  - the mesh, as CARP files or generated from `dx`;
  - the stimulus `.vtx`;
  - the activation recording, a loop over `assemble()` / `step()` (D10).
    `solve()` would hold the full `Vm` history, and `compute_activation_map`
    stamps one dt earlier than the benchmark.
- `theta` is set as an attribute before `assemble()`.

## F. Open questions: each with the run that would settle it

| id | question | run that settles it |
|---|---|---|
| F1 | `omnidriver.toml` requires `source` (core reads it only to cross-check a provider's `cxx_mapping`, `cli.py`; `read_repository` refuses a manifest without it and accepts a path that does not exist, probed in the session scratchpad). What is TorchCor's honest source? | owner decision. Evidence: the code that runs is the installed package, identified by commit `b02daee` (A1, A4). A submodule `torchcor-cases/torchcor` at that commit, installed editable from there, would make `source` both true and the install origin; the catalogue digest would then hash that tree. Settle by installing from the submodule and checking `torchcor.__file__` points inside it |
| F2 | float32 versus float64: which does the record use, and what does it cost? | at dx 0.5, P8 moves 0.075 ms between benchmark.py's float32 and float64 CG (D9). The library's CG is always float64, so its dtype choice moves P8 by 0.005 ms (D5 vs D4). Settle at dx 0.1 with both dtypes through the runner, comparing P1-P8 and wall time |
| F3 | is a CPU run deterministic across processes, thread counts and the compile cache? | settled for one machine at dx 0.5: identical arrays, warm or cold cache (D3, D6). Still open: a different `OMP_NUM_THREADS` / `torch.set_num_threads`, and a cleared `torchinductor` cache. Settle by rerunning D10 under `OMP_NUM_THREADS=1` and `=4` and after deleting the cache, then `np.array_equal` |
| F4 | wall time at dx 0.1 on CPU | measured: dx 0.5 at 11.6 s, dx 0.2 at 108.6 s. dx 0.1 is not run. A rough guess from node count alone (about 8× the nodes) is 15-20 min; the CG iteration count also grows, so this is unverified. Settle with one dx 0.1 run of the step-loop runner, in the background |
| F5 | why does P8 fall from 40.31 (dx 0.5) to 37.65 ms (dx 0.2), and is the consistent mass matrix the cause? | run dx 0.5 and 0.2 with `mass_lumping` true and false, both at float64, and compare against openCARP's `03E` runs at the same dx (the cross-solver `compare` the design targets) |
| F6 | is `et = 0.2` a deliberate choice or a typo against Niederer's 0.24? | the case should cite benchmark.py's value and record the discrepancy. A run with `et = 0.24` shows the size of the effect; whether it is intended is a question for TorchCor's author |
| F7 | does the library TTP's residual 0.005 ms (D11) come from the CaSS fix or from `torch.compile`? | run D11's verification TTP with the one-line CaSS fix applied; then the library TTP with `TORCHDYNAMO_DISABLE=1` |
| F8 | does `gmsh` produce the same mesh on another machine or gmsh version? | byte-identical here across runs (D6). Settle by generating at dx 0.5 on a second machine or gmsh version and `cmp` the `.pts`. If it differs, the case must ship the mesh files rather than `dx` |
| F9 | licence | MIT in the repository (A2) versus CC BY-NC 4.0 in the design; owner |

## G. The runner, and omniD driving it

Runs below use `~/torchcor-cases` (the case, the runner
`scripts/run_case.py`, and TorchCor as the submodule `torchcor` at `b02daee`)
and the venv `~/torchcor-venv` rebuilt from that submodule. Outputs under
`/Users/simaocastro/omnid-runs/2026-10-09/torchcor/g<n>_*/`.

| # | command | observed | conclusion |
|---|---|---|---|
| G0 | `uv venv ~/torchcor-venv`; `uv pip install -e ~/torchcor-cases/torchcor`; `python -c "import torchcor; print(torchcor.__file__)"` | `/Users/simaocastro/torchcor-cases/torchcor/torchcor/__init__.py`, torch 2.14.1 | **F1 settled:** the submodule is both `omnidriver.toml`'s `source` and the code that runs |
| G0b | `g0_describe_probe/probe.py`: each `torchcor.ionic` model built with `dt` only; its `_init` attributes; its constructor | all ten build; `_init` attributes: AlievPanfilov 0, BuenoOrovio 4, CRN 20, MitchellSchaeffer 2, ModifiedMS2v 0, OHaraRudy 45, TTP 24, Tomek19 43, Tomek20 56, TWorld 93. `grep` of the compared literals: OHaraRudy `cell_type` compares `EPI`, `MCELL` (default `ENDO` is the else branch), Tomek19 `MCELL`, Tomek20 `M`, TWorld `MID` and `sex` `MALE`, `FEMALE` (default `MIX`) | **a string option's menu is its compared literals plus its default**, which no comparison names. The mid-myocardial spelling differs per model (`MCELL`, `M`, `MID`), so a menu must be read per model, never shared. TTP's `GKs_init` and `Gto_init` are conductances set from `cell_type`, yet end in `_init` |
| G0c | `torch.sparse_coo_tensor(..., device="mps").to_sparse_csr()` | `NotImplementedError` for `aten::_to_sparse_csr` on `SparseMPS` | the conversion `Monodomain.assemble` needs (D12) is a one-line probe; the runner offers `mps` only when it succeeds |
| G1 | `g1_runner_dx05/`: `run_case.py nversion/case.json` on a copy of `cases/nversion` (et 0.24, float32, θ 1, consistent mass, to 150 ms) | exit 0; 3675 nodes, 30 000 steps; setup 0.46 s, **solve 19.1 s**, process 29.2 s. P1 0.955, P2 21.375, P3 33.105, P4 38.050, P5 6.455, P6 22.175, P7 33.660, **P8 40.325** ms; no node unactivated (latest 40.35 ms). Rerun (`rerun/`): `activation_times.dat` and `--describe` byte-identical | the runner reproduces D10's convention (P1 0.955). `et` 0.24 instead of 0.2 moves P8 by -0.06 ms at dx 0.5 (D10: 40.385 ms in float64 at et 0.2). The run is deterministic run to run (D3 again, through the runner) |
| G2 | `g2_refusals/`: the case with `chi_per_m` added; `ionic_init.V_int`; `cell_type: "EPIC"`; `device: "mps"` | each exits 2 before writing anything, naming the key: `chi_per_m: not a key this runner takes`; `ionic_init.V_int: not an initial value of TenTusscherPanfilov`; `ionic_options.cell_type: 'EPIC' is not one of ['ENDO', 'EPI', 'MCELL']`; `device: 'mps' is not one of ['cpu']` | the runner refuses what TorchCor would accept silently (B4, B6) or fail on late (D12) |
