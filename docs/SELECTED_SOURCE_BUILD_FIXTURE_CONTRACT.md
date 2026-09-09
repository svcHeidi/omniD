# Selected-source/build fixture contract

Native cardiac acceptance is opt-in. It must never locate a solver checkout,
OpenFOAM installation, or output directory by searching the host.

## Scope and fixture modes

Updated scope, 2026-09-09: the driver fixture proves configuration, execution and reporting contracts. Numerical acceptance is delegated to the selected solver's regression scripts/reference data. The fixture must not redefine their tolerances or freeze unrelated tutorial content.

- **Selected-source mode:** explicit source root and revision; reads source/catalog/tutorial contracts without requiring a compiled solver or OpenFOAM installation. Any materialization uses a temporary output root, never the source checkout.
- **Selected-runtime mode:** all inputs below, plus the named case/input manifest and requested regression scope. It executes isolated cases and records driver and solver outcomes separately.

The implementation must provide an explicit test selection/opt-in mechanism. Native checks not requested may skip with a reason. Once selected-source or native acceptance is explicitly requested, missing, partial or invalid prerequisites fail before staging. Setting any fixture input must not silently turn an invalid selection into a skip.

## Required explicit inputs (native mode)

| Input | Purpose | Required validation |
| --- | --- | --- |
| `OMNIDRIVER_CARDIACFOAM_SOURCE_ROOT` | Solver checkout containing `src/`, `tutorials/`, and its Git metadata | Absolute existing path; `git rev-parse HEAD` matches `OMNIDRIVER_CARDIACFOAM_SOURCE_REVISION`. |
| `OMNIDRIVER_CARDIACFOAM_SOURCE_REVISION` | Accepted solver commit | Full 40-character commit ID. The fixture requires a clean `src/` diff against this commit. Tutorial/characterization drift is permitted, but its complete status and diff digest are recorded. |
| `OPENFOAM_BASHRC` | OpenFOAM environment entrypoint | Existing absolute `etc/bashrc`; the child process reports `WM_PROJECT_DIR`, `WM_PROJECT_VERSION`, and `WM_OPTIONS`. |
| `DRIVERFOAM_CARDIACFOAM_BACKEND` | Chosen cardiac backend | Validated against the cardiac runtime profile and build manifest. |
| `DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST` | Solver-library evidence | Existing manifest accepted by `CardiacFoamPlugin.configure_execution_environment`. |
| `OMNIDRIVER_NATIVE_OUTPUT_ROOT` | Disposable output parent | Existing explicit directory outside both source and OmniDriver checkouts; each test creates a unique child. |

## Input selection policy

Default to named committed inputs read from the selected revision. Working-tree tutorial changes do not silently affect that baseline. If an explicitly selected working-tree candidate is needed, stage only its declared inputs, record their exact bytes/digests, changed and untracked paths, and diff from the selected revision; label it as a candidate rather than the committed reference. Do not auto-update reference results. A passing candidate does not establish unchanged paper reproduction.

Build identity must cover relevant solver applications, build scripts/configuration and submodules, not only a clean `src/` directory. Record or reject build-affecting drift according to the selected build contract. A source revision and runtime inspection manifest alone do not prove historical build provenance.

## Fixture behavior

1. Apply the mode-specific selection and fail/skip rules above.
2. Validate every required input and build/case identity before staging.
3. Copy only the declared input manifest using the selected committed or explicit-candidate policy into a unique output child. Exclude historical solver output and never write below the selected source root.
4. The fixture records source revision, `src/` diff status, permitted
   tutorial/characterization diff digest, submodule status, OpenFOAM identity,
   backend, manifest digest, staged input digest, command results, bounded
   diagnostics, and output artifact digests.
5. Solver success and OmniDriver success are separate assertions. A solver
   failure is solver evidence, not an adapter crash; a driver transaction or
   provenance failure is adapter evidence even if the solver itself succeeds.

## Previously inspected selection (revalidate before use)

The previously inspected gold-standard checkout is
`/Users/simaocastro/noFrontendCardiacFoam_minor_errors` at
`c3a852e957d23077ce1b2712331dfe45489c4386`. Its `src/` tree is clean. Its
permitted drift is confined to monodomain pseudo-ECG tutorial/characterization
inputs, plus `modules/solids4foam` at
`d28c6527fca934b39271ca61531110aeee0f80ed`. This records an earlier inspection, not permission to trust a moving checkout. Revalidate the identities, build-affecting drift and input-selection policy before use. T6 implementation and T7 reproducible acceptance remain pending.
