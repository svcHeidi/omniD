# TorchCor: what the runner and the library do that a reader would not guess

- **A case is `case.json`, run by the solver repository's `scripts/run_case.py`**
  in TorchCor's own venv. Every key is required; `run_case.py --describe` (or
  `omnidriver describe`) lists them. Select the stack with `--repo` naming the
  repository so omniD judges a study's keys before anything runs; with
  `--plugin torchcor` alone, keys are written unvalidated.
- **`device`** is a case value. Only the devices this host can run are offered:
  `cpu` always, `cuda` where present, `mps` never with torch 2.14 (TorchCor's
  assembly needs a sparse CSR conversion MPS lacks; D12, G0c).
- **`mass_lumping` decides the answer.** At dx 0.5 mm, lumping moves P8 from
  about 40 to 68 ms (D14). The N-version case does not lump, as TorchCor's own
  benchmark does not.
- **`theta`** defaults to 0.5 (Crank-Nicolson) in TorchCor; the benchmark uses
  1 (B8). The case states it.
- **`dtype`** sets the simulation precision; TorchCor's CG always runs in
  float64 (D9).
- **`conductivity_S_per_m.et`** is 0.24, the benchmark's value; TorchCor's own
  `verification/benchmark.py` uses 0.2 (F6).
- **Activation time** is stamped at the first step a node exceeds
  `activation_threshold_mV`; a node never activated reads `-1` (G1).
- **The first run on a machine compiles** the ionic model (`torch.compile`),
  cached outside the case in the system temp directory (D6): a cold run is
  slower, not different.
