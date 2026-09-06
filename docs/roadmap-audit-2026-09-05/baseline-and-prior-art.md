# Audit baseline and comparison with existing practice

Audit date: 2026-09-05. Repository commit: `d19ea1543f1c7be7ce10084f06a2434c0901a011`. The working tree was clean at audit start. This is a planning audit; production code and scientific settings were not changed.

## What was actually checked

| Check | Observed result | Scope of evidence |
|---|---|---|
| `.venv/bin/python -m pytest packages/ -q -m 'not slow and not integration'` | 1,568 passed, 274 skipped, 3 deselected; 40 subtests passed; 48.98 seconds | Existing editable workspace, Python 3.14.3, foamlib 1.7.5, pytest 9.1.1; not the CI Python matrix |
| `.venv/bin/python scripts/check-import-boundaries.py` | Passed | Enforced static import boundaries, not complete semantic independence |
| `.venv/bin/python scripts/export-capability-seams.py --check` | Passed | Generated table matches protocol docstrings, not proof that runtime semantics satisfy those docstrings |
| Three package distributions | Each installed at 0.1.0 | Existing environment; clean wheel installations were not repeated in this planning audit |
| Native simulations | Not run | No conclusion about convergence, MPI/GPU behavior, scientific correctness, or installed solver equivalence |

Counts are an observation at this revision, not an enduring quality target. The full command above passed; critical gaps were independently found outside the behavior covered by those tests. Specialist reports distinguish code inspection from small reproductions.

Additional program-review probes after team review: namespace package discovery in the existing environment reached 151 modules, including all three package branches; this ruled out a suspected current namespace-walk coverage defect. Calling the native regression helper `_drive_agent` stopped immediately with `TypeError` because it constructs `Path(omnidriver.__file__)` while the namespace root has `__file__ = None`. No subprocess or solver launched. The release-team report records this concrete harness defect and the precise limits of the probe.

The CI file declares Python 3.11–3.13 package jobs and a core wheel job for 3.11/3.13 (`.github/workflows/ci.yml`, `test-core`, `test-openfoam`, `test-cardiac`, `test-wheel`). Its existence is not evidence of a successful remote run. Remote CI status was not inspected. Cardiac test setup sets `SKIP_ENV_DIAGNOSTICS=1` and skips monorepo-dependent tests if sibling tutorials/applications are absent (`packages/omnidriver-cardiacfoam/tests/conftest.py:33`, `:39`). Live ionic verification skips without its runtime utility (`tests/test_ionic_catalog_live_verification.py`, `requires_utility`). A sibling checkout is not automatically discovered by an ancestor-only search.

## Comparison with current practice

These are narrow comparisons to official documentation checked on the audit date. They are not an exhaustive literature review or a claim that any framework guarantees scientific validity.

| Existing approach | Relevant established practice | Implication for omniD |
|---|---|---|
| AiiDA | Process specifications declare input/output ports and exit codes; external calculations have parser and provenance contracts. | Adopt explicit process and parser contracts. Evaluate an execution/provenance adapter before independently building a persistent HPC service. An immediate engine migration is not justified by this audit. |
| CWL | Command tools declare typed inputs/outputs, runtime requirements, exit-code policy and file staging semantics; requirements differ from optional hints. | Treat missing mandatory capabilities as failures and optional evidence as explicitly unavailable. Use declarative command specifications; JSON schema validity alone cannot establish simulation validity. |
| signac | Jobs associate parameter state points with filesystem workspaces and distinguish identifying parameters from other metadata. | Separate experiment identity, execution attempt identity and observations. Include every result-affecting dependency in identity rather than relying on a case directory name. |
| foamlib | Provides OpenFOAM file manipulation; its documentation explicitly distinguishes syntax handling from evaluation. | Retain it as a parser/editor where supported. Add effective-configuration evidence from the selected OpenFOAM runtime; do not silently upgrade lexical reads to runtime truth. |
| OpenFOAM itself | Dictionary syntax includes substitution, inclusion, merge behavior and code-generated entries. | A dictionary can depend on other files and executable code. Resolve and fingerprint the transitive inputs, and label unresolved evaluation explicitly. |

AiiDA supports the process-specification comparison through its [process usage documentation](https://aiida.readthedocs.io/projects/aiida-core/en/stable/topics/processes/usage.html). Its [calculation usage documentation](https://aiida.readthedocs.io/projects/aiida-core/en/stable/topics/calculations/usage.html) describes parser exit codes, and its [process concepts](https://aiida.readthedocs.io/projects/aiida-core/en/stable/topics/processes/concepts.html) distinguish calculation and workflow provenance.

The [CWL v1.2 CommandLineTool specification](https://www.commonwl.org/v1.2/CommandLineTool.html) defines input/output validation, required capabilities, runtime requirements, file staging and success/failure codes. The [signac jobs documentation](https://signac.readthedocs.io/en/latest/jobs.html) explains state points and workspaces. These are design precedents, not dependencies selected for this repository.

The [foamlib file-manipulation documentation](https://foamlib.readthedocs.io/en/stable/files.html) states that regex and directives can be modified but are not evaluated or expanded, and that `#codeStream` is unsupported. The [OpenFOAM dictionary guide](https://www.openfoam.com/documentation/user-guide/2-openfoam-cases/2-2-basic-inputoutput-file-format) describes inclusion, substitution, merge directives and compiled code generation. That guide is background, not a conformance oracle for every OpenFOAM fork/version: the implementation must test the explicitly supported runtime.

## What is distinctive enough to invest in

The useful product is an agent-facing simulation contract: ask what a selected solver accepts, get evidence and applicability conditions, propose a configuration, receive a reviewable resolved plan, and execute exactly that plan with attributable outcomes. A DAG engine, Python package split, JSON output and a parameter catalog are useful ingredients already common elsewhere. They do not by themselves provide this product.

The recommended investment is therefore effective OpenFOAM semantics, source/build-bound solver capabilities, explicit uncertainty, and verification that the agent uses those contracts correctly. Reuse workflow conventions; avoid adding a scheduler, vector database, general C++ reasoning engine, or persistent multi-agent platform until a measured requirement demands it. This is a design recommendation derived from the comparison and repository audit.

## Publication observations

The release workflow builds one selected package and installs its wheel using dependency resolution (`.github/workflows/release.yml:43`, `:49`). It does not declare a dependency on tests for that exact tag, run the full suite, or provision a mutually compatible local wheel set before release. The only explicit artifact gate is core-specific (`:65`). This is a release-contract gap; this audit did not execute a release or test availability on a package index.

`VERSION_POLICY.md` explicitly says there is no package index yet, while sibling dependencies are ordinary package requirements. The release/install story needs a tested dependency source and clean installation of the complete wheel set. Preserve independent package versions, with a tested compatibility matrix.

No tracked root LICENSE file or package license metadata was present. Some cardiac files carry historical GPL notices. Inventory provenance and have the owner settle distribution licensing before publication; this report makes no license selection or legal determination. Package READMEs are too small to constitute standalone onboarding, and the root guidance contains historical migration material and contradictory old claims. Replace release-facing claims with generated, dated evidence and tested examples.
