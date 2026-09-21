# Vendored singleCell fixture

`constant/electroProperties` and `constant/physicsProperties` are copied
verbatim from the cardiacFoam monorepo's
`tutorials/electrophysiologyProtocols/singleCell/constant/` (source commit
`6515739bd1b1c6cf7ef21fe1d4e25830352ed4d2`, see
`docs/PROGRESS_LEDGER.md`). Both are plain OpenFOAM dictionaries with no
patient or case-specific content -- only the `singleCellSolver` benchmark
configuration.

This fixture exists so tests that only need a runnable minimal case (not the
full monorepo) can build one without depending on
`cardiacfoam_monorepo_root()`, which resolves to `None` in CI and on any
machine without a real cardiacFoam checkout. Before this fixture existed,
every test built this way was gated `skip_without_monorepo` and never ran in
CI -- see `packages/omnidriver/tests/core/test_trust_boundary_end_to_end.py`
and `test_cli_run_document.py`.

If the monorepo's singleCell tutorial changes in a way that matters to these
tests, update this copy deliberately rather than assuming drift is harmless.
