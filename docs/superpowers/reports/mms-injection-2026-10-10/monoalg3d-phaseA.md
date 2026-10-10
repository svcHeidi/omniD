# MonoAlg3D phase A: build and run without CUDA (evidence log)

**Method:** `docs/solver-learning/method.md` phase A. **Machine:** Apple M4 Pro (14 cores), macOS Darwin 24.6, arm64, Homebrew `/opt/homebrew`, no NVIDIA/CUDA. **Date:** 2026-10-10.
**Tree:** `~/MonoAlg3D_C`, commit `cb7727ff0800340397861bba523a83ce1605595f` (2026-09-17, "Fix visualizer file dialogs, view reset and crash on unreadable meshes"). No source file was modified. No secrets appeared in any output.

| # | command | observed | conclusion |
|---|---|---|---|
| A1 | `git clone https://github.com/rsachetto/MonoAlg3D_C ~/MonoAlg3D_C`; `git log -1` | commit above; top level has `build.sh`, `bsbash/`, `Makefile`, `example_configs/`, `src/`, Linux guides only (ubuntu/fedora/windows) | no macOS guide; build is a bash script (`bsbash/`), not CMake |
| A2 | read `README.md`, `build.sh`, `bsbash/find_functions.sh` | README: "Linux-based operating system, Nvidia Driver, CUDA library". `build.sh` takes modules `all gui simulator batch converter` and a **documented-in-code `disable_cuda` module**; `FIND_CUDA` only warns ("CUDA code will not be compiled") and clears `CUDA_FOUND` when nvcc/libcudart are absent. CUDA is therefore not a hard requirement. Compiler is hardcoded `gcc`/`g++` (`C_COMPILER` in `bsbash/build_functions.sh`) | CPU-only path: `./build.sh simulator disable_cuda` |
| A3 | `brew list --versions` | already present: `cmake 4.2.1`, `gcc 15.2.0_1`, `libomp`, `pkgconf`; `/usr/bin/gcc` is Apple clang 17 (no `-fopenmp` support), `/bin/bash` is 3.2.57 | the script needs `-fopenmp` (flag in `DEFAULT_C_FLAGS`) and bash 4 |
| A4 | `./build.sh -q simulator disable_cuda` | `./bsbash/build_functions.sh: line 29: declare: -A: invalid option` | **FAIL.** the script uses `declare -A` (bash 4+). Fix: `brew install bash` (5.3.20), run as `/opt/homebrew/bin/bash ./build.sh ...` |
| A5 | `brew install bash` | bash 5.3.20 at `/opt/homebrew/bin/bash` | the only package installed in this whole probe |
| A6 | `PATH=<shim>:$PATH /opt/homebrew/bin/bash ./build.sh -q simulator disable_cuda`, first with plain `gcc`->`gcc-15` and `g++`->`g++-15` symlinks (`build1.log`) | all objects compile (only `-Wformat` warnings); link of the first model `.so` fails: `Undefined symbols for architecture arm64: "_log_to_stderr_and_file" ... ld: symbol(s) not found` | **FAIL.** Apple `ld` rejects undefined symbols in a shared library, GNU ld allows them (the model libs call logger functions provided by the executable/liblogger at load time). Needs `-undefined dynamic_lookup` on `-shared` links |
| A7 | same with a wrapper `gcc`/`g++` that appends `-undefined dynamic_lookup` when `-shared` is present (`build2.log`) | all 46 `shared_libs/lib*.so` build; executable link fails: `ld: unknown options: -rpath=~/MonoAlg3D_C/shared_libs` | **FAIL.** `build_functions.sh` emits GNU `-Wl,-rpath=DIR`; Apple ld wants `-rpath DIR`. (The executable link line also hardcodes `gcc`, which resolves through `PATH`, so the wrapper sees it) |
| A8 | wrapper additionally rewrites `-Wl,-rpath=DIR` to `-Wl,-rpath,DIR` (`build3.log`) | `bin/MonoAlg3D` (255 KB) built, 8 s; `otool -L`: `liblogger.so`, Homebrew `libgomp.1.dylib`, `libSystem`. Build log also prints harmless noise: `ls: unrecognized option --time-style=full-iso` and `date: illegal time format` (the script's incremental-build timestamp check uses GNU `ls`/`date`; so staleness detection does not work on macOS, rebuild with `-f` or `clean`) | **BUILDS.** Whole simulator, 46 shared modules, ~65 s cold build (A6-A8 together, `time`) |
| A9 | `bin/MonoAlg3D --help` | options include `-c config`, `-f final time`, `-n num_threads` (OpenMP, default 1), `--domain "k=v, ..."` and `--ode_solver "..."` per-section overrides, `-g` GPU, `--visualize` | CLI overrides ini keys; sections can be patched from the command line |
| A10 | `bin/MonoAlg3D -c example_configs/cable_mesh_with_fhn.ini` (FHN, 10 ms, 200 cells, ensight output; `build`-relative paths, so run from repo root) | exit 0, **1.3 s wall**; log: `Using modified FHN 1961 CPU model`, `[main] Using OpenMP with 6 threads`, `Resolution Time: 284763 us`, CG total iterations 3631; outputs `outputs/FHN_cable/`: `simulation_result.case`, `geometry.geo`, `geometry.geo.vis`, `Vm.Esca0000..0010` (ASCII ensight-gold per-element Vm, 11 time steps), `original_configuration.ini` (copy of config), `outputlog.txt` | runs on CPU, no GPU code touched. Thread count comes from `[main] num_threads` (ini), overridable by `-n` |
| A11 | `bin/MonoAlg3D -c example_configs/activation_time_and_apd_example.ini -f 100 -n 4` (ToRORd dynCl, 100 cells cable, 100 ms instead of 5000 ms) | exit 0, **7.5 s wall** (7.26 s "Resolution", 4.6 s of it writing); `Using OpenMP with 4 threads`; outputs in `outputs/cable_save_activation_time_and_apd_example/`: 107 `Vm.Esca*` ensight steps, `simulation_result.case`, `geometry.geo`, `outputlog.txt`, `original_configuration.ini`, and **`activation_info_it_0.acm`** | **activation times**: text file, first line `1` (number of beats), then one line per cell `cx,cy,cz,dx,dy,dz <n_activations> [ t1 ... ] [ apd1 ... ]`, e.g. `9950,50,50,50,50,50 1 [ 56.200001 ] [ ]` (cell centre and half side in um, activation times in ms, APD list empty as the cell had not repolarised within 100 ms) |
| A12 | read `build.sh` GUI branch | `COMPILE_GUI` adds raylib (`src/3dparty/raylib`) and links `OpenGL GLX GLU pthread X11 rt` | **not attempted**: Linux-only link libs; irrelevant to a CPU/batch use. The `simulator` module needs none of it |
| A13 | `ls src/` and `src/config/*.h` | see plug-in module list below | |

## Environment contract (what must be supplied)

- bash >= 4 (`brew install bash`); invoke the script as `/opt/homebrew/bin/bash ./build.sh -q simulator disable_cuda`.
- A `gcc`/`g++` on `PATH` that is real GCC with OpenMP (Homebrew `gcc-15`; Apple clang does not work: no `-fopenmp`), wrapped to (1) add `-undefined dynamic_lookup` to `-shared` links and (2) turn `-Wl,-rpath=DIR` into `-Wl,-rpath,DIR`. The wrapper is `~/omnid-runs/2026-10-10/monoalg3d/shim/{gcc,g++}` (not in any repo).
- No CUDA, no pkg-config library beyond the compiler. MPI (`batch` module, `MonoAlg3D_batch`), GUI and criterion tests were not built.
- Run from the repository root (configs use relative `shared_libs/...so` paths and `./outputs`).
- Runtime library lookup: `bin/MonoAlg3D` records `build_release/liblogger/liblogger.so` and `shared_libs/` as an rpath. Moving the tree breaks it.
- Default precision is `-DCELL_MODEL_REAL_DOUBLE`.

## Plug-in module types (all C shared libraries named by `library_file=` in an ini section, entry points `main_function`, `init_function`, `end_function`)

Interfaces are macros in `src/config/*.h`; implementations in `src/<x>_library/`. Models live in `src/models_library/<name>/<name>.c` (+ `.cu` GPU, ignored here).

| ini section | contract (header) | sources |
|---|---|---|
| `[ode_solver]` | cell model: `set_model_initial_conditions_cpu`, `solve_model_odes_cpu` (`src/models_library/model_common.h`, `default_solvers.c`) | `src/models_library/*/` (fhn, ToROrd, ToROrd_Land, Ohara_Rudy, ten_Tusscher, CRN, Maleckar, Trovato, Tworld, ... ) each with its own `build.sh` |
| `[domain]` | `SET_SPATIAL_DOMAIN` (+ `SET_CUSTOM_DATA_FOR_MESH`) | `src/domains_library/` |
| `[stim_*]` (any number) | `SET_SPATIAL_STIM` | `src/stimuli_library/stimuli.c` |
| `[extra_data]` / `[purkinje_extra_data]` | `SET_EXTRA_DATA`, `FREE_EXTRA_DATA` (per-cell parameters, e.g. celltype/gk scaling, fibrosis) | `src/extra_data_library/` |
| `[assembly_matrix]` | `INIT_ASSEMBLY_MATRIX`, `ASSEMBLY_MATRIX` (conductivity/sigma, fibres) | `src/matrix_assembly_library/` |
| `[linear_system_solver]` | `INIT_/SOLVE_/END_LINEAR_SYSTEM` (CG default; cublas variants are CUDA only) | `src/linear_system_solver_library/` |
| `[update_monodomain]` | `UPDATE_MONODOMAIN` | `src/update_monodomain_library/` |
| `[save_result]` | `INIT_/SAVE_MESH/END_SAVE_MESH` (e.g. `save_as_ensight`, `save_with_activation_times`, `save_as_text_or_binary`, vtk) | `src/save_mesh_library/` |
| `[modify_domain]` | `MODIFY_DOMAIN` (time-dependent changes) | `src/modify_domain/` |
| `[calc_ecg]` | `INIT_/CALC_/END_CALC_ECG` | `src/ecg_library/` |
| `[purkinje]`, `[purkinje_*]` | `SET_SPATIAL_PURKINJE`; coupling assembly | `src/purkinje_library/`, `src/matrix_assembly_library/purkinje*.c` |
| `[save_state]`, `[restore_state]` | `SAVE_STATE`, `RESTORE_STATE` | `src/save_state_library/`, `src/restore_state_library/` |

Modules are compiled by `build.sh` (`ADD_SUBDIRECTORY "src/<x>_library"` and each directory's `build.sh`), so a new module means a new `.c` plus a `build.sh` entry in the tree; the `.ini` then names the resulting `shared_libs/lib<x>.so`. The ini accepts `;` and `#` comments and `key=value`; stimulus parameters are read by the module through `GET_PARAMETER_*` from its own section.

## Findings and oddities

- Building without source changes needs a compiler wrapper (A6-A8). It is a pure toolchain workaround (two GNU-ld-isms in the build scripts), not a patch to MonoAlg3D, and is cheap to reproduce; but it is an environment fact that omniD preflight must declare.
- First mesh log line prints nonsense cell counts (`Refined 1 of 1 (4294967332 cells)`, a 32-bit overflow in a progress print); the run itself reports correct `Number of Cells:200`/`100`.
- FHN example uses 6 threads for a 200-cell cable (ini default); small problems get no benefit from threads.
- `[WARN] The gpu_id option is being moved to the [main] section` is printed by the shipped example.
- Not tried: GUI/visualizer, MPI batch, tests (criterion), `ddm`, Purkinje examples, anything GPU.
