# Selected-source/build fixture contract

Native cardiac acceptance is opt-in. It must never locate a solver checkout,
OpenFOAM installation, or output directory by searching the host.

## Required explicit inputs

| Input | Purpose | Required validation |
| --- | --- | --- |
| `OMNIDRIVER_CARDIACFOAM_SOURCE_ROOT` | Solver checkout containing `src/`, `tutorials/`, and its Git metadata | Absolute existing path; `git rev-parse HEAD` matches `OMNIDRIVER_CARDIACFOAM_SOURCE_REVISION`. |
| `OMNIDRIVER_CARDIACFOAM_SOURCE_REVISION` | Accepted solver commit | Full 40-character commit ID. The fixture requires a clean `src/` diff against this commit. Tutorial/characterization drift is permitted, but its complete status and diff digest are recorded. |
| `OPENFOAM_BASHRC` | OpenFOAM environment entrypoint | Existing absolute `etc/bashrc`; the child process reports `WM_PROJECT_DIR`, `WM_PROJECT_VERSION`, and `WM_OPTIONS`. |
| `DRIVERFOAM_CARDIACFOAM_BACKEND` | Chosen cardiac backend | Validated against the cardiac runtime profile and build manifest. |
| `DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST` | Solver-library evidence | Existing manifest accepted by `CardiacFoamPlugin.configure_execution_environment`. |
| `OMNIDRIVER_NATIVE_OUTPUT_ROOT` | Disposable output parent | Existing explicit directory outside both source and OmniDriver checkouts; each test creates a unique child. |

## Fixture behavior

1. With no required inputs, native tests skip and name the missing variable.
2. With any supplied input that is invalid, native tests fail before staging.
3. The fixture copies only named committed tutorial inputs into its unique
   output child. It never writes below the selected source root.
4. The fixture records source revision, `src/` diff status, permitted
   tutorial/characterization diff digest, submodule status, OpenFOAM identity,
   backend, manifest digest, staged input digest, command results, bounded
   diagnostics, and output artifact digests.
5. Solver success and OmniDriver success are separate assertions. A solver
   failure is solver evidence, not an adapter crash; a driver transaction or
   provenance failure is adapter evidence even if the solver itself succeeds.

## Current selection status

The current gold-standard checkout is
`/Users/simaocastro/noFrontendCardiacFoam_minor_errors` at
`c3a852e957d23077ce1b2712331dfe45489c4386`. Its `src/` tree is clean. Its
permitted drift is confined to monodomain pseudo-ECG tutorial/characterization
inputs, plus `modules/solids4foam` at
`d28c6527fca934b39271ca61531110aeee0f80ed`. A native fixture may use this
state, provided it records those identities and stages only the named input
case into its disposable output root.
