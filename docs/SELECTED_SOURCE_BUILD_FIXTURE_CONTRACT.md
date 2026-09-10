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
| `DRIVERFOAM_CARDIACFOAM_BACKEND` | Declared compiled capability | Validated against the cardiac runtime profile and the selected solver/build evidence. |
| `DRIVERFOAM_CARDIACFOAM_BUILD_MANIFEST` | Solver-library evidence | Existing manifest accepted by `CardiacFoamPlugin.configure_execution_environment`. |
| `OMNIDRIVER_NATIVE_OUTPUT_ROOT` | Disposable output parent | Existing explicit directory outside both source and OmniDriver checkouts; each test creates a unique child. |

## Input selection policy

Default to named committed inputs read from the selected revision. Working-tree tutorial changes do not silently affect that baseline. If an explicitly selected working-tree candidate is needed, stage only its declared inputs, record their exact bytes/digests, changed and untracked paths, and diff from the selected revision; label it as a candidate rather than the committed reference. Do not auto-update reference results. A passing candidate does not establish unchanged paper reproduction.

Build identity must cover relevant solver applications, build scripts/configuration and submodules, not only a clean `src/` directory. Record or reject build-affecting drift according to the selected build contract. A source revision and runtime inspection manifest alone do not prove historical build provenance.

## Compile-time optional components

cardiacFOAM has two compiled capabilities: **electro-only** and
**electromechanics-enabled**. The latter is built when solids4foam is
available; the former is a valid cardiacFOAM build when it is not. This is a
compile-time property of the selected solver binary, not a requirement of each
case and not something OmniD infers from a checkout's `modules/` directory.

The adapter records a semantic capability and verifies it from the selected
binary/build-manifest libraries. A source root or submodule revision may be
recorded as additional build provenance when available, but a packaged solver
must remain usable without that source tree. The mechanism that supplies the
evidence is environment-specific: a macOS installation, Linux module, HPC
container, or CI package may expose different paths and inspection tools.
Those conventions belong to the environment/OpenFOAM adapter contract; Core
consumes only the declared capability and evidence.

## Fixture behavior

1. Apply the mode-specific selection and fail/skip rules above.
2. Validate every required input and build/case identity before staging.
3. Copy only the declared input manifest using the selected committed or explicit-candidate policy into a unique output child. Exclude historical solver output and never write below the selected source root.
4. The fixture records source revision, `src/` diff status, permitted
   tutorial/characterization diff digest, optional submodule provenance,
   OpenFOAM identity, compiled capability, manifest digest, staged input
   digest, command results, bounded diagnostics, and output artifact digests.
5. Solver success and OmniDriver success are separate assertions. A solver
   failure is solver evidence, not an adapter crash; a driver transaction or
   provenance failure is adapter evidence even if the solver itself succeeds.

## Previously inspected selection and recorded acceptance (revalidate before use)

The previously inspected gold-standard checkout is
`/Users/simaocastro/noFrontendCardiacFoam_minor_errors` at
`c3a852e957d23077ce1b2712331dfe45489c4386`. Its `src/` tree is clean. Its
permitted drift is confined to monodomain pseudo-ECG tutorial/characterization
inputs, plus `modules/solids4foam` at
`d28c6527fca934b39271ca61531110aeee0f80ed`. This records an earlier inspection, not permission to trust a moving checkout.

T6 and T7 were subsequently accepted against source revision
`3aa4b48fa5fd896933b3758f5a084e265f9ba9de`: the selected source/runtime
fixture, single-cell and Niederer reference runs with solver-owned check-only
reports, and a catalog-derived single-cell sweep all recorded their evidence.
Those records do not make a moving checkout trustworthy. Revalidate the source
identity, build-affecting drift, input-selection policy, and declared runtime
before each native run.
