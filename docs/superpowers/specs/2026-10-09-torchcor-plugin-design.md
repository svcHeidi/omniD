# TorchCor: a third solver of a different shape

**Status:** design, approved in conversation 2026-10-09. Covers sub-projects B
(the plugin) and C (the core changes B shows a need for).

## Why

openCARP proved that core is independent of OpenFOAM, but openCARP has
OpenFOAM's shape: a binary run in a case folder of text documents, parallel
through `mpirun -np`. TorchCor ([SoftwareX 33, 102521](https://doi.org/10.1016/j.softx.2026.102521),
`github.com/sagebei/torchcor`, MIT) has none of these. It is a
Python API on PyTorch, runs on one GPU (or the CPU), and has no input file:
its N-version benchmark (`verification/benchmark.py`) sets every value in
`__main__`. It is verified against the same Niederer N-version benchmark
omniD already holds as `benchmarks/niederer2011.json`, so it adds a third
solver to one shared reference.

## Decisions taken

- **A case is a folder holding `case.json`** (plus mesh files when a case
  supplies its mesh). A runner turns `case.json` into TorchCor API calls.
  Patching, sweeps and rules then work through omniD's existing document
  mechanism. This is `method.md` step 9: a script-built example becomes a
  candidate once its facts move into files.
- **The runner states the keys and the rules; omniD asks it.** `run_case.py
  --describe` prints every key a `case.json` takes, with its kind, unit,
  bounds and menu, and per ionic model its options and initial values with
  their kinds, read from the installed TorchCor with `inspect` (defaults,
  `torchcor.ionic.__all__`, the string literals a model compares an option
  to). `run_case.py --check <case.json>` prints the rules a case breaks as
  `{"refusals": [{"key", "rule", "message"}]}` and exits 0. The rules live in
  the runner only, which refuses the same case when asked to run it. This is
  the counterpart of the C++ key scan.
- **TorchCor runs in its own venv.** It is the solver's environment, not
  omniD's. The manifest declares `TORCHCOR_BIN` (supplied), the venv's `bin`,
  first on `PATH`, exactly as openCARP declares `OPENCARP_MPI_BIN`.

## Where the case and the runner live

omniD ships no case (tutorials are pointers), and TorchCor has none to point
at. The case and the runner therefore live in a **solver-side repository**,
`torchcor-cases`, laid out like cardiacCore:

```
torchcor-cases/
  omnidriver.toml        plugin = "torchcor", tutorials = "cases", scripts = "scripts", source = "torchcor"
  torchcor/              TorchCor, a git submodule at b02daee, installed editable into the venv
  scripts/run_case.py    the runner: run, --describe, --check; imports TorchCor, numpy, pygmsh and the standard library only
  cases/nversion/
    case.json            every value the run uses
    README.md            the line of TorchCor's verification/benchmark.py each value comes from
```

A record's solve step names `run_case.py` as a repository script, which core
already runs under the `python3` on the stack's `PATH`
(`core/scripts.py`), here the TorchCor venv's. No omniD code runs inside the
solver's interpreter, and the venv never needs omniD installed.

## The plugin: `packages/omnidriver-torchcor`

Depends on core only. `scripts/check-import-boundaries.py` gains the rule
that it imports no other adapter and no adapter imports it.

| member / file | content |
|---|---|
| `torchcor.yaml` | identity; environment: `TORCHCOR_BIN` (required), `path_prepend`; no `mpi_launcher` |
| records | `nversion`: one step (`run_case.py case.json`), `serial_only`, no axes: `dx_mm`, `dt_ms` and every other value are `case.json` keys a study names directly (`case.json:dx_mm`); a conformance study with a `QuantityTarget` of activation time at P1–P8 against `benchmarks/niederer2011.json` |
| key catalogue | the runner's `--describe`, cached under the scratch root by a digest of the runner, the TorchCor source, the `python3` that runs it (its path and the interpreter it resolves to), that interpreter's `torch/version.py`, and the host; the case's own model's options and initial values are listed |
| key validator | before staging, whether `--describe` lists a study's key, and its kind; a judged key may add a field of `ionic_options` or `ionic_init`, since the case rules re-judge the edit |
| case rules | the runner's `--check` on the staged case, each refusal an error; nothing judged in the plugin |
| reader | activation times from the runner's output file at the node nearest a point, in ms at points in mm (both already in core's unit table) |
| provenance | the installed TorchCor version and commit, torch's version, and the device the run used, recorded by the runner into `out/run_info.json` |

The key catalogue, the validator and the case rules find the runner in the
repository the stack was selected from (`driver_context.repository`). With
`--plugin torchcor` alone there is none: keys are written unvalidated, a key
only replaces one the case holds, and a strict plan says so once
(`torchcor_runner_not_supplied`).

Device: whether a GPU exists is ambient fact and is read; which device a case
uses is a `case.json` value (`device`), supplied. `--describe` offers only the
devices this host can run, so `--check` refuses a case asking for `cuda` where
none exists, by name, before it runs.

## How it is learned first

The plugin is written only after `method.md` phases A–F, logged in
`docs/solver-learning/torchcor.md`:

- A: install in a venv on this Mac (no CUDA), import, record version and commit.
- B: does TorchCor describe itself? (signatures, docstrings, ionic model list.)
- C: inventory `demo/`, `verification/`, `benchmark/`; classify each by where its physics lives.
- D: smallest real run: the N-version slab at the coarsest `dx`, on CPU; time it; take its outputs apart.
- E: map onto omniD nouns (case, document, key, step, axis, quantity).
- F: open questions, settled only by runs.

Phase D also settles whether the runner uses `torchcor.simulator.Monodomain`
or must follow `verification/benchmark.py`, which defines its own
`Monodomain` class with the benchmark's mesh and activation recording.

## Core changes (sub-project C), only where B needs them

1. **C13 is `not_applicable` for a `serial_only` record.** `check_parallel_agrees`
   does not consult `serial_only` today, so a record that declares a quantity and
   cannot run on MPI ranks always fails C13. TorchCor needs this.
2. **The key validator, the key catalogue and the case rules receive the
   `DriverContext`.** `get_record_key_validator`, `get_record_key_catalog` and
   `validate_run_semantics` take a keyword-only `driver_context`, as
   `get_plan_diagnostics` does, and every core call site passes the context
   it holds. Without it TorchCor could reach its runner only through a
   variable restating `--repo`. `plugin_api_version` stays `"3"`: nothing is
   released, and every implementer changed with the contract.
3. **Whatever else phases A–F or the plugin hit**, each recorded with its evidence
   before it is fixed, and fixed minimally.

Not done now, because TorchCor does not need them: extensible units (ms and mm
are in the table) and a declared launcher binding (TorchCor has no launcher; the
`srun` binding belongs with the cluster Niederer campaign).

## Owner decisions, 2026-10-09

1. `omnidriver.toml`'s `source` is a git submodule of TorchCor pinned at
   `b02daee`, from which the venv is installed editable, so the code that runs
   is the code recorded.
2. `torchcor-cases` starts as a local git repository under `~/torchcor-cases`;
   a remote is the owner's call.
3. The N-version case uses `et = 0.24` S/m, the benchmark's value; TorchCor's
   `verification/benchmark.py` uses 0.2, recorded as a likely upstream typo.
4. Licence: TorchCor's repository is MIT (the paper's CC BY-NC 4.0 does not
   apply to the code).

## Success

- `omnidriver check --repo ~/torchcor-cases --record nversion` on this Mac (CPU)
  reports C1–C12 and C14 passed, C13 `not_applicable`.
- `omnidriver compare` of TorchCor's and openCARP's N-version runs at the same
  `dx` reads both through their own readers against the shared reference.
- All three suite shapes and the static gates: 0 failed.
