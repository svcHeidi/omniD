# Verification and publication team audit

Audit date: 2026-09-05. Revision baseline: `d19ea1543f1c7be7ce10084f06a2434c0901a011`. Scope: source inspection of tests, CI, release, installation guidance and agent onboarding. No new build, package install, full test run, solver run or release was performed by this lead. The baseline records the program lead's completed regression/static checks; their pass counts are not evidence of native solver readiness.

Team composition: verification/publication lead plus the program lead as independent packaging reviewer. A requested additional packaging expert could not start because the agent tool rejected the spawn at its thread limit. Packaging conclusions below integrate the program lead's independent review; no unstarted expert is claimed as contributing.

## Findings grounded in implementation

### R1 — Release is not bound to comprehensive verification of the published artifacts (P1)

`.github/workflows/release.yml:43` builds the selected package, `:49` installs that wheel with dependency resolution, `:65` applies the dedicated artifact check only to core, and `:69` publishes the resulting distribution files. There is no dependency on package/static/native test results for the tagged revision. `.github/workflows/ci.yml:109` provides an installed-wheel job only for core; OpenFOAM and cardiac jobs install editable packages (`:53`, `:78`). These are meaningful import/install defenses, but adapter execution, bundled data and compatible local dependency artifacts are not covered equally.

The import loop currently reaches adapter packages: both contain `__init__.py`. The program lead's existing-environment probe discovered 151 modules, including 58 core, 16 OpenFOAM and 64 cardiac modules. This does **not** demonstrate a namespace discovery bug or a tested wheel. The loop still needs explicit expected-module/API assertions to make its intended coverage contractual. `scripts/check-wheel-artifact.py:45` has a zero-module defense; the release loop has no equivalent explicit assertion and is only an import smoke check.

Acceptance: build once from the approved revision into a release candidate artifact set; record hashes and exact dependency resolution; install the selected package with the tested sibling wheel versions into a clean environment outside the checkout; validate declared APIs, schemas/data and the supported workflow; publish the same hashed artifacts only after required gates pass. Preserve independently versioned packages, with a tested compatibility matrix. Include an sdist installation check where sdists are distributed; do not infer this from wheel importability.

### R2 — Native tests encode one maintainer installation, not a portable supported runtime contract (P0 support definition, P1 release)

`packages/omnidriver-cardiacfoam/tests/test_runtime_dependencies_live_verification.py:55` enables tests whenever `cardiacFoam` is on PATH, but `:69` requires `FOAM_MODULE_LIBBIN` to be unset, `:82` requires resolved libraries to have `.dylib` suffix, and `:98`–`:104` requires an electromechanical library to be absent. These are explicit observations of a particular lightweight macOS installation. Enabling the same file unchanged in a Linux/full-backend native CI job can reject valid environments.

Acceptance: distinguish installation-specific regression fixtures from portable resolver contracts. Name the first supported runtime profile, including OS, OpenFOAM family/version, solver build/backend, precision and MPI scope. Native checks compare actual evidence to that declared profile; lightweight/full and Linux/macOS differences have explicit applicability. Required profile tests fail if the runtime or fixture is unavailable. Optional unrelated profiles remain visibly untested.

### R3 — Required behavior is hidden by broad skips, and live regression entry needs repair (P0)

Core and cardiac conftests force `SKIP_ENV_DIAGNOSTICS=1` (`packages/omnidriver/tests/conftest.py:6`; cardiac `:33`). Cardiac tests define a monorepo-dependent skip at `:44`. Live catalog verification skips when its utility is absent (`test_ionic_catalog_live_verification.py:64`). Skipping optional native tests on ordinary developer machines is reasonable; it cannot satisfy a required release gate.

There is avoidable lost coverage: `tests/regression_equivalence/test_dual_run.py:1` calls itself solver-free unit tests but applies the monorepo skip to the whole module (`:7`–`:8`), including pure text parsing and tolerance helper tests. Move pure unit checks out of that dependency boundary.

A concrete live-path defect was reproduced by the program reviewer in the existing environment: `tests/regression_equivalence/dual_run.py:299` constructs `Path(omnidriver.__file__)`. The installed project intentionally uses a namespace root with `__file__` equal to `None`. Calling `_drive_agent(None, "strict", Path("/tmp/omnidriver-audit-unexecuted"))` immediately raised `TypeError` at that line, before any case access or subprocess. Correct this namespace-package assumption before claiming the live strict regression harness works. Generic execution may bypass it via a committed regression script (`:407`–`:408`); helper tests monkeypatch the function, so those tests cannot establish its health.

Acceptance: classify tests by contract, packaged installation, native/runtime and scientific benchmark; create a required-check manifest for each advertised support profile. Count and report skipped/deselected checks with reasons. Fail release when a required test is skipped or absent. Exercise actual strict CLI invocation from all-package wheels with no injected checkout PYTHONPATH. Keep pure parser/control-flow tests independent of solver source trees.

### R4 — Catalog-addressable tutorials do not yet prove a fresh usable case (P0 first case)

`test_registered_tutorials_need_no_repository.py:35` checks a spec's case-root placement. `:40`–`:59` calls factories and counts 18 successful catalog entries, including aliases; it does not materialize and execute 18 independent complete tutorials. The four named parallel tutorials intentionally fail without rank-count case content (`:62`–`:68`). The cardiac package data declaration (`packages/omnidriver-cardiacfoam/pyproject.toml:44`) includes template constant files and utility manifests, not a complete tutorial fixture tree.

Acceptance: choose a small first supported case whose exact template, mesh/input acquisition, runtime requirements and expected outputs ship or are fetched by a documented versioned route. From an empty case directory and clean package installation, discover the case, materialize, validate, plan, execute, resume and compare output. Report unique physical/tutorial cases separately from aliases and spec-factory coverage. Later tutorials receive their own complete-case gates.

### R5 — The current agent contract is mostly a Python/CLI guide; it lacks measured agent task acceptance (P0)

`AGENT_GUIDE.md:16` exposes many internal Python modules alongside commands, and `:40` recommends strict planning. Existing tests establish valuable structured-output behavior, such as `test_strict_plan_contract.py:75` checking JSON for a missing selector. That test itself requires a monorepo fixture. The function named `_drive_agent` in `regression_equivalence/dual_run.py:297` executes a fixed CLI subprocess; it does not test an agent discovering tools, interpreting uncertainty or selecting actions.

The package READMEs contain brief descriptions, and core explicitly redirects readers to repository files whose links do not work from an installed package. `VERSION_POLICY.md:30` says no package index exists, while the cardiac installation command resolves ordinary sibling dependencies (`packages/omnidriver-cardiacfoam/pyproject.toml:12`). A tested complete installation route is required; no package-index availability was verified here.

Acceptance: provide one stable application API and thin typed agent tools, then test a fresh agent given only the shipped guide and tool responses. Corpus: valid first case, invalid model combination, missing required parameter, wrong dimension, unresolved include, missing runtime, stale completed state, changed solver binary, interrupted run and unknown solver error. Measure task completion, false acceptance, unsupported claims and unstructured shell fallback. Require zero known false compatibility or stale-resume acceptances in the declared corpus; retain and publish corpus size and limitations. Reuse core lifecycle tests beneath these evaluations, rather than replacing them with variable agent outcomes.

## Integrated work order and release gates

| Work | Owner / reviewer | Deliverable and gate |
|---|---|---|
| P0 define first support profile and claim ledger | Program + simulation / verification | Every advertised property names evidence, runtime applicability and required checks; untested modes are explicit. |
| P0 repair and isolate test dependencies | Verification / core + simulation | Pure unit tests run without monorepo; strict regression helper works with namespace packages; negative environment cases are tested with diagnostics enabled. |
| P0 fresh-case and agent acceptance | Core + simulation / verification | Packaged case completes discover → materialize → validate → plan → execute → observe → resume; drift and incompatible cases refuse with stable reasons. |
| P1 all-package exact-artifact gates | Verification / program | Exact wheel/dependency hashes, explicit package/API/resource assertions, tested sdist route, tests bound to release revision and artifact set. |
| P1 native/scientific evidence | Simulation / verification | Mandatory live catalog and required runtime checks do not skip; case-specific reference/convergence criteria use domain-approved tolerances and build identity. |
| P1 standalone onboarding and publication evidence | Verification + owner / core | Tested install instructions, linked user guide/examples, compatibility/schema migration policy, documented limitations and distribution provenance/terms inventory. Owner settles distribution terms before publication; this audit makes no licensing decision. |

The roadmap should start wheel/fixture/onboarding preparation alongside core repairs, then make integrated evidence mandatory before advertising a ready-to-use supported slice. Test volume, passing imports and catalog size remain useful supporting evidence; they do not substitute for a complete attributable simulation attempt.
