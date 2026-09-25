# Release and agent-interface audit — 2026-09-22

Scope: maintainer review at `db93cc436883a09346658e6113870c6c9f421a6d`, including the explicitly identified pre-existing working-tree changes. This is an implementation audit, not a certification of solver correctness. Production files were not changed.

## Findings

| ID | Finding and evidence | Consequence / required work |
|---|---|---|
| R1 | `.github/workflows/ci.yml` already has `test-all-package-wheels`; `packages/omnidriver-cardiacfoam/tests/test_all_packages_wheel_install.py::test_all_package_wheels_discover_and_invoke_cardiacfoam` builds and installs all four distributions outside the checkout and invokes both adapters' `describe`. It explicitly excludes native runtime execution. | Preserve this useful gate. Extend it with materialization, plan inspection, and recovery conformance as those APIs stabilize. Do not describe wheel coverage as absent or native runtime coverage as present. |
| R2 | `.github/workflows/release.yml` triggers on tags for core, OpenFOAM, and cardiacFoam, but has no cardiacCore tag trigger. It builds and smoke-imports the tagged artifact; there is no job dependency on the full CI result or native acceptance for that exact revision. | Add cardiacCore routing and bind release eligibility to the exact tested revision/artifacts. Current evidence supports installability checks, not release assurance of supported simulations. This review does not publish anything. |
| R3 | CI defines package-specific Python 3.11/3.12/3.13 jobs and artifact/static gates, but no configured OpenFOAM/cardiacFoam native runtime job. Selected native integration tests exist under the cardiacFoam tests. | Define a pinned supported runtime profile and required native checks. Report unavailable infrastructure as unavailable; it must not satisfy release acceptance through skips. Do not replace solver-owned scientific regressions with newly invented tolerances. |
| R4 | `agent-handbook/provider-integration.md` defines exact guidance delivery and hash recording. A scoped search of production packages and scripts found no implementation referencing its guidance manifest. `core/experiments.py` does provide a substantial solver-neutral read model for attempts and supplied scientific comparison reports. | Treat guidance injection as a documented external integration responsibility until a concrete launcher is verified. Build a thin agent tool adapter over existing application paths; do not add a resident agent platform without a measured need. Reuse the experiment read model. |
| R5 | `core/runtime/launch_readiness.py::is_launchable` can refuse an `unavailable` audit item, but the CLI call sites omit `simulation_audit`; `StepExecutionContext` has no audit field. `_refuse_environment_errors` only examines `environment_ok`. | Audit visibility is not enforcement. Carry required-check evidence through dispatch and test the public execution edge. Do not make every optional check mandatory; define applicability and requiredness per operation/profile. |
| R6 | The older `docs/OMNIDRIVER_ROADMAP.md` contains dated baseline findings and still says to preserve three distributions, while the current implementation contains four. Its deterministic-versus-scientific-validity distinction remains useful. | Publish a dated current decision with links from the old roadmap and Phase 2. Historical findings need explicit revalidation, not wholesale recopying. |

## Verification limits

The host default Python is 3.14.3 and cannot import the workspace packages. Audit tests instead use the existing `/tmp/od311/bin/python` environment, Python 3.11.15, with all four packages installed editable. Core/OpenFOAM/cardiac import boundaries and generated capability-seam freshness both passed. The full non-slow suite result is recorded in the consolidated roadmap after completion. Its input includes a pre-existing untracked validator regression test and uncommitted validator helper; results must be attributed accordingly.

`foamDictionary` was not found on the host PATH. The OpenFOAM lead subsequently loaded `/Volumes/OpenFOAM-v2412/etc/bashrc` and performed native dictionary probes; see its report for the binary/build identity and results. No full native solver acceptance execution was performed. Wheel/native release gates listed above were inspected, not all rerun. No production source change was made, so a source-change artifact close-out is not being claimed.

## Agent acceptance work package

An agent should be able to use the same normalized tools to: discover providers; inspect a parameter's authority and applicability; propose an edit; inspect the complete diff; materialize; validate; dispatch; observe; and investigate an unknown failure. Test those behaviors on both real adapter contracts and a minimal non-OpenFOAM fixture.

The negative cases are as valuable as the successful one: unsupported parameter, missing native evaluator, ambiguous dictionary address, stale reviewed inputs, interrupted transaction, unsupported adapter operation, and unknown runtime failure. Count false acceptance and unsupported claims, and retain raw evidence with stable reason codes. Successful preflight and an exit code cannot prove scientific suitability.

## External references consulted

- [foamlib file API](https://foamlib.readthedocs.io/en/stable/files.html) documents a file parser/editor supporting directives. That interface alone does not establish equivalence with a selected native runtime's effective values.
- [OpenFOAM Foundation v13 dictionary API](https://cpp.openfoam.org/v13/classFoam_1_1dictionary.html) exposes caller-supplied defaults through `lookupOrDefault`. A missing dictionary key therefore cannot, on its own, reveal the default consumed by every solver.

These references explain why parser, source-call-site, and runtime evidence need distinct labels. They do not establish the distribution/version used by this user's solver; the implementation roadmap must bind evidence to the selected build.
