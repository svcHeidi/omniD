# TorchCor: what the runner and the library do that a reader would not guess

- **A case is `case.json`, run by the solver repository's `scripts/run_case.py`**
  in TorchCor's own venv. Every key is required; `run_case.py --describe` (or
  `omnidriver describe`) lists them. Select the stack with `--repo` naming the
  repository so omniD judges a study's keys, and the staged case by the
  runner's own `--check`, before anything runs; with `--plugin torchcor`
  alone, keys are written unvalidated.
- **`device`** is a case value. Only the devices this host can run are offered:
  `cpu` always, `cuda` where present, `mps` never with torch 2.14 (TorchCor's
  assembly needs a sparse CSR conversion MPS lacks; D12, G0c).
- **`mass_lumping` decides the answer.** At dx 0.5 mm, lumping moves P8 from
  about 40 to 68 ms (D14). Read the case's own value before comparing.
- **`theta`**: TorchCor's library default and the N-version case's value differ
  (B8); `describe` shows the default, and the case states its own.
- **`dtype`** sets the simulation precision; TorchCor's CG always runs in
  float64 (D9).
- **`conductivity_S_per_m.et`**: TorchCor's own `verification/benchmark.py`
  uses 0.2, not the N-version benchmark's value (F6); read the case's own.
- **Activation time** is stamped at the first step a node exceeds
  `activation_threshold_mV`; a node never activated reads `-1` (G1).
- **The first run on a machine compiles** the ionic model (`torch.compile`),
  cached outside the case in the system temp directory (D6): a cold run is
  slower, not different.
