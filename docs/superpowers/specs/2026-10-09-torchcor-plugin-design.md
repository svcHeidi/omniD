# TorchCor: a third solver of a different shape

**Status:** design, approved in conversation 2026-10-09. Covers sub-projects B
(the plugin) and C (the core changes B shows a need for).

## Why

openCARP proved that core is independent of OpenFOAM, but openCARP has
OpenFOAM's shape: a binary run in a case folder of text documents, parallel
through `mpirun -np`. TorchCor ([SoftwareX 33, 102521](https://doi.org/10.1016/j.softx.2026.102521),
`github.com/sagebei/torchcor`, CC BY-NC 4.0) has none of these. It is a
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
- **The catalogue is read from TorchCor**, not written by hand: the
  signatures and defaults of the callables the runner uses, read with
  `inspect` in the solver's interpreter, cached under the scratch root by a
  digest of the installed TorchCor source. This is the counterpart of the C++
  key scan.
- **TorchCor runs in its own venv.** It is the solver's environment, not
  omniD's. The manifest declares `TORCHCOR_VENV` (supplied), whose `bin` goes
  first on `PATH`, exactly as openCARP declares `OPENCARP_MPI_BIN`.

## Where the case and the runner live

omniD ships no case (tutorials are pointers), and TorchCor has none to point
at. The case and the runner therefore live in a **solver-side repository**,
`torchcor-cases`, laid out like cardiacCore:

```
torchcor-cases/
  omnidriver.toml        plugin = "torchcor", tutorials = "cases", scripts = "scripts", source = <see open question 1>
  scripts/run_case.py    the runner: reads case.json, calls TorchCor, writes outputs; imports TorchCor and the standard library only
  cases/nversion/
    case.json            every value cites the line of TorchCor's verification/benchmark.py it comes from
    README.md
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
| `torchcor.yaml` | identity; environment: `TORCHCOR_VENV` (required), `path_prepend`; no `mpi_launcher` |
| records | `nversion`: one step (`run_case.py case.json`), axes `dx` and `dt`, `serial_only`, a `QuantityTarget` of activation time at P1–P8 against `benchmarks/niederer2011.json` |
| catalogue | built from the signature scan; menus (ionic model names) from what TorchCor's `torchcor.ionic` exports |
| reader | activation times from the runner's output file, in ms at points in mm (both already in core's unit table) |
| validation | numeric bounds and menus from the catalogue; nothing invented beyond what the scan or a real run establishes |
| provenance | the installed TorchCor and torch versions, and the device the run used, recorded by the runner into its output |

Device: whether a GPU exists is ambient fact and is read; which device a case
uses is a `case.json` value (`device`), supplied. A case asking for `cuda`
where none exists fails in preflight by name.

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
2. **Whatever else phases A–F or the plugin hit**, each recorded with its evidence
   before it is fixed, and fixed minimally.

Not done now, because TorchCor does not need them: extensible units (ms and mm
are in the table) and a declared launcher binding (TorchCor has no launcher; the
`srun` binding belongs with the cluster Niederer campaign).

## Open questions for the owner

1. `omnidriver.toml` requires `source`, which core describes as C++ source. For
   TorchCor, the honest source is the installed package that runs. Options: a
   git submodule of TorchCor pinned to the installed version, or relaxing
   `source` so a repository may omit it. Decided after phase A.
2. Where `torchcor-cases` is hosted. It starts as a local git repository under
   `~/torchcor-cases`; a remote is the owner's call.
3. Licence: TorchCor is CC BY-NC 4.0. omniD only drives it and ships none of its
   code; the case values cite its benchmark.

## Success

- `omnidriver check --repo ~/torchcor-cases --record nversion` on this Mac (CPU)
  reports C1–C12 and C14 passed, C13 `not_applicable`.
- `omnidriver compare` of TorchCor's and openCARP's N-version runs at the same
  `dx` reads both through their own readers against the shared reference.
- All three suite shapes and the static gates: 0 failed.
