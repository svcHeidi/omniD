# OpenFOAM mechanics lead: pre-Phase-2 audit

Date: 2026-09-22. Role: Maintainer. Scope: roadmap and review only; no production changes.

Read the router, maintainer manifest entries, actual OpenFOAM provider, its lexical/native readers and mutators, builder, source scanner, core override adapter/candidate path, and Phase 2 Tasks 1–3. Preserved pre-existing cardiacCore `run_config.py` and validation-test WIP.

## Decision

Keep a common case-write transaction, but do not execute the Phase 2 plan as written. First repair the existing effective-readback integration and native dependency provenance; then rewrite the write-provider contract to say exactly who interprets an OpenFOAM patch. A universal transaction is useful. A universal dictionary language or universal claim that a case will run is not justified.

The implementation already makes a valuable distinction between inert lexical reading and explicit native effective resolution. It also has real rollback, containment, and native conformance tests. Those foundations should be retained. The critical defects are at the composition/evidence seams, which successful helper-level tests do not cover.

## Ranked findings

### P1 / O1 — public override capability silently drops the execution environment

Evidence:

- `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py::_OverrideScopeAdapter.apply` accepts `execution_env`, but calls the real hook with only `overrides`, `case_root`, and `driver_context`.
- `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py::OpenFOAMEnvironmentPlugin.apply_overrides` neither accepts nor forwards that environment.
- `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py::apply_overrides` returns `()` immediately when its environment is `None`.
- `packages/omnidriver/src/omnidriver/core/runtime/step_candidate.py::execute_candidate` checks returned effective records for unresolved/mismatched values. An empty tuple produces no failures.

Reproduced with the real OpenFOAM provider and adapter against a temporary `system/controlDict`: supplying `execution_env={"PATH": "/deliberately/no/runtime"}` wrote `deltaT 0.0005` and returned `evidence=()`. Native runtime unavailability should have been visible, but the lower helper was never asked to check.

This is an existing reproduced orchestration defect, so a bounded core forwarding correction satisfies the repository's criterion for core changes. Do not treat it as a reason for a general redesign. Add an integration test through the composed provider/public capability, not another helper-only test. Decide explicitly which writes require effective verification; distinguish `not_requested`, `unavailable`, `unsupported`, and `verified` instead of treating an empty collection as success.

### P1 / O2 — `#includeEtc` inspects the wrong dependency closure

Evidence:

- `openfoam/effective_dictionary.py::_inspect_source_closure` maps `#includeEtc` to `Path(environment["FOAM_ETC"]) / include_name`.
- Installed native v2412 source `src/OpenFOAM/db/dictionary/functionEntries/includeEtcEntry/includeEtcEntry.C::resolveEtcFile` delegates to `Foam::findEtcFile`.
- Installed `src/OpenFOAM/global/etcFiles/etcFiles.C::{groupResourceDir,projectResourceDir,findEtcFile}` searches additional user/site/version locations. The inspected local source is under `/Volumes/OpenFOAM-v2412`.

Native reproduction used only temporary inert dictionary files. Load the v2412 environment, set `WM_PROJECT_SITE` to a temporary directory, put `siteProbe 123;` in `site/etc/caseDicts/profiling/parallel.cfg`, and request `siteProbe` from a dictionary containing `#includeEtc "caseDicts/profiling/parallel.cfg"`.

Observed:

```text
status='resolved', value='123'
inspected_files=(temporary dictionary,
  '/Volumes/OpenFOAM-v2412/etc/caseDicts/profiling/parallel.cfg')
environment_keys=('FOAM_ETC',)
actual site dependency recorded: False
```

The native value comes from the site file, while provenance and directive screening inspect the vendor file. This is a correctness and execution-policy boundary defect: even a nominally safe resolution may evaluate a dependency that was never inspected. No executable directive was used in this audit.

Fix by resolving the actual native search precedence under a pinned runtime/environment, or conservatively marking this include form unresolved until its exact closure can be established. Include negative lookup locations in dependency evidence where their later creation can change resolution. A vendor path alone is not a runtime identity.

### P1 / O3 — native readback compares spelling rather than typed value

`openfoam/apply_overrides.py::apply_overrides` compares `result.value == _effective_value_text(requested)`. The latter only formats and strips the request. Native readback normalizes scalar spellings and lists.

Native temporary-file reproduction:

```text
requested_value='1e-3'
status='resolved', value='0.001'
matches_requested=False
```

The write is numerically correct. Once O1 is fixed, `step_candidate` will reject and roll back this otherwise valid override. Correct both in the same integration tranche. Preserve raw spelling for provenance, compare canonical structured values only when their declared type and dimensions justify it, and report `comparison_unavailable` for unmodeled values. Do not introduce loose floating tolerances that could accept an incorrect requested configuration.

### P1 / O4 — Phase 2 leaves ownership of `patch` undefined

`docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md`:

- Task 1 says only `synthesize` needs provider vocabulary and only it is provider-supplied.
- Task 2 says to dispatch both `patch` and `synthesize` through `CaseWriterCapability`.
- Task 3's proposed capability exposes `plan(request)` and `synthesize(operation, case_root) -> bytes`; no patch realization method is defined.

An OpenFOAM key patch requires scoped-path interpretation, lexical preservation, value-kind handling, duplicate/pattern semantics, and foamlib or text mutation behavior. Core cannot own that logic while remaining format-neutral. The proposed operation has no explicit format backend or schema version and no structured scope; `provider_id` alone does not distinguish the domain authority from the syntax implementation.

Also, the proposed `CaseWriteOperation.to_json` omits `value`: the agent's supposedly inspectable plan cannot show what value will be written. `frozen=True` does not freeze mutable `Any` payloads. The plan needs complete canonical serialization, precondition hashes, and an evidence-bearing validation policy before approval or digesting is meaningful.

Recommended contract: domain provider resolves scientific intent and declares addressed edits; OpenFOAM provider renders/prepares OpenFOAM bytes from explicit source snapshots; core validates the declared target set and commits/restores prepared bytes. Use the existing provider/capability machinery to implement this; do not add a parallel dispatch registry without a demonstrated need. Provider attribution must represent both semantic ownership and rendering implementation where they differ.

### P2 / O5 — the OpenFOAM environment is not yet an inspectable numerical-defaults provider

`OpenFOAMEnvironmentPlugin.get_dict_entries`, `get_dictionary_catalog`, and `get_named_catalogs` return empty collections. Its profile declares `system/controlDict`, a `constant` directory, and `Allrun`; it does not describe a comprehensive `fvSchemes`/`fvSolution` numerical surface. Its standalone `inspect_effective_configuration` therefore inspects `controlDict` only, because directories are skipped.

This is an implementation gap relative to the user's intended platform role, not proof that the present minimal environment plugin is inherently wrong. Domain providers can contribute other files through composition. What is missing is a clearly published reusable contract for OpenFOAM numerical controls and runtime-selected components.

Keep four meanings separate:

1. Native compiled fallback, conditional on source/runtime/version.
2. Configured dictionary value, after native expansion.
3. Tutorial/example value, supported by that example only.
4. Domain-recommended value/range, requiring solver/domain evidence.

OpenFOAM can own addressing, dimensions syntax, runtime lookup machinery, and version-qualified mechanical defaults. Solver adapters own valid model combinations, physical units/meaning, recommended ranges and acceptance criteria. Generic C++ understanding is not the OpenFOAM provider's promise: it should expose versioned evidence with bounded coverage and let the agent reason from it.

### P2 / O6 — `typical_value` is silently promoted into an execution default

`openfoam/dict_builder.py::populate_values(..., typical_value_fallback=True)` populates missing values from `DictEntry.typical_value`. `cardiacfoam/dict_builder.py::build_electro_properties` uses that mode by default. It also enables dependent dynamic entries when a matching instance appears.

The helper is mechanically reusable, but `typical` is not equivalent to a native fallback or a scientifically justified default. The output is a plain mapping of values with no per-value origin. Existing domain catalogs may justify some values; this audit does not assume they are scientifically wrong. The defect in the contract is that the kinds of evidence are indistinguishable downstream.

Add explicit provenance and policy for defaults before normalizing catalogs: `explicit`, `native_default`, `template_value`, `domain_recommendation`, and unresolved/unset, plus source/version/applicability. Require an explicit selected policy to turn a typical example into a synthesized input. Do not move a domain default into OpenFOAM solely because the same helper writes it.

### P2 / O7 — source scanner remains heuristic; its coverage claim is not measured here

`openfoam/dict_keys_scanner.py` documents approximately 80% accuracy and human-review-only results. It uses regexes rather than C++ semantic analysis, retains only `(kind,name,source_file,line)`, does not capture the receiver's dictionary identity or default expression, and feeds allowlist-backed strict drift reports.

Temporary C++ fixture:

```cpp
const char* url="http://example"; dict.lookup("realKey");
auto x=readScalar(dict.lookup("doubleCount"));
```

Observed output: `doubleCount` twice; `realKey` absent. `_strip_comments` treats `//` within a string as a comment; the wrapper and key patterns duplicate the same callsite. Do not use scanner silence as proof of coverage, catalog completeness, or a runnable configuration. Strict drift can still be valuable as a bounded change detector, provided its limits are emitted with the result. Replace the undocumented accuracy percentage with a measured corpus metric or remove it. An optional compiler-aware extractor should be justified against that corpus and compile-command availability, not assumed necessary as a new framework layer.

### P2 / O8 — failure policy is conservative scheduling, not deterministic diagnosis

`core/runtime/failure_classification.py::classify_failure` returns retryable for timeout diagnostics and fatal otherwise. This is a bounded retry policy; it neither distinguishes invalid dictionary configuration from solver divergence nor determines a scientific root cause. Timeout is not proof of transient contention, and generic nonzero exit is not proof of a deterministic failure.

Preserve the conservative scheduler, but label its result accurately. OpenFOAM should provide version-qualified parsing of recognized native diagnostics with raw stderr/stdout offsets and an explicit unknown result. Solver-specific diagnostics and interpretation belong in the solver adapter. The agent can propose a hypothesis and inspect evidence; the framework should validate the proposed operation and preserve the observation that motivated it.

## Normalized responsibility contract

| Owner | Owns | Must not silently infer |
|---|---|---|
| Core | request/plan lifecycle, provider routing, byte transaction, dependency fingerprints, execution, generic outcome and evidence envelope | OpenFOAM grammar, solver validity, physical acceptance |
| OpenFOAM | inert lexical AST/text addressing; native effective resolution and actual include closure; runtime identity; syntax rendering; generic OpenFOAM diagnostics and controls | domain model selection; physiological values/ranges; scientific success |
| Solver adapter | domain selectors/catalogs, supported combinations, conditional requirements, template intent, domain operations, results and scientific criteria with evidence | universal defaults from one tutorial or a successful run |
| Agent | goals, hypothesis formation, source/tool inspection, experiment selection and explanation within published capabilities | treating unverified/unknown as compatible |

Normalize the contracts and evidence levels, not every solver's internal concepts. CardiacFOAM synthesis and cardiacCore preprocessing can produce a common write plan while having different domain requests. Distinct operations need not be squeezed into identical selector lists.

Recommended result envelope: status (`supported`, `unsupported`, `unknown`, `failed` as appropriate), evidence kind, inspected scope, provider identity, runtime/source/dependency fingerprints, typed value and raw representation, assumptions, and limitations. Names are illustrative; reuse suitable existing core records instead of adding an overlapping evidence abstraction.

## Acceptance gates before publishing a common writer

1. Public/composed override call forwards exact execution environment; unavailable native resolution cannot disappear as an empty tuple.
2. Scientific-notation scalars, booleans, dimensions, vectors/tensors, lists and quoted words compare correctly under explicitly declared types. Unsupported comparisons remain unknown.
3. Native include fixtures cover local, optional, substitution, user/site/version `includeEtc` precedence, absent-path invalidation, cycles, and execution-gated dependencies. Recorded files must match the files actually used.
4. Every OpenFOAM patch uses an OpenFOAM renderer; a neutral/non-OpenFOAM provider passes the same core transaction tests without importing OpenFOAM.
5. Plans serialize values, scopes/addresses, provider attribution, format version, source preconditions and expected outputs. Mutation of an input collection after planning cannot change the executable plan.
6. Rollback covers all declared files, file creation/deletion and metadata where relevant. Distinguish ordinary exception rollback from process-crash recovery and concurrent edits. Reject a stale plan rather than overwrite later user changes.
7. A provenance test traverses composed public API → prepared mutation → native readback → transaction record. Low-level tests are insufficient for this defect class.
8. Catalog defaults have explicit origin and applicability; run reports identify where each executed value came from.
9. Run known native failures through OpenFOAM diagnostics; unknown output remains unknown and is not converted to a false exact diagnosis.

## Roadmap and expert work packages

1. **Integration expert, bounded repair:** O1/O3 together; public-edge regression tests; preserve existing adapter signature compatibility deliberately. This is a prerequisite, not a full Phase 2 migration.
2. **Native semantics expert:** O2; audit native include-resolution paths for the selected runtime; construct inert differential fixtures and fix dependency fingerprints. Publish supported runtime/version scope.
3. **Transaction expert with OpenFOAM renderer expert:** rewrite Phase 2 Tasks 1–3 around domain planning, provider byte realization and core transactions; pilot one patch and one synthesis; prove readback and rollback through public composition before migrating every write path.
4. **Catalog provenance expert with domain reviewer:** inventory `typical_value` consumers, classify evidence, design explicit fallback policy, and build the initial OpenFOAM numerical-control inventory without inventing domain recommendations.
5. **Source/runtime inspection expert:** establish a C++ extractor corpus, deduplicate records and repair string/comment handling; expose limits and source identity. Explore compiler assistance only if measured coverage warrants it.
6. **Diagnostics expert:** define recognized mechanical outcomes and unknown handling, bind failures to raw evidence, and separate scheduler retry policy from diagnostic certainty.

Suggested team-lead rule: each work package closes with a reproduced failure, a contract change, an integration test, and explicit unresolved boundaries. Run the four repository verification shapes for implementation; do not claim publication readiness from the focused audit suite.

## Checks actually run and limits

Ran:

```text
.venv/bin/python -m pytest \
 packages/omnidriver-openfoam/tests/core/test_native_dictionary_conformance.py \
 packages/omnidriver-openfoam/tests/core/test_effective_dictionary.py \
 packages/omnidriver-openfoam/tests/core/test_apply_effective_resolution.py -q

25 passed in 10.77s; no skips reported.
```

Also ran four isolated temporary-file probes described above: public adapter environment loss, native includeEtc wrong-file attribution, native scientific-notation comparison, and C++ scanner false-negative/duplicate. Native dictionary resolution used the installed `/Volumes/OpenFOAM-v2412` runtime. This is real native dictionary validation, not a full cardiacFOAM/cardiacCore solve and not evidence for other OpenFOAM releases or distributions. No scientific correctness or physical-model validation was performed. No production files were edited, no solver cases were changed, and no executable dictionary payload was evaluated.

### Native oracle identity and reproduction details

Environment loaded by the existing adapter API:

```python
from omnidriver.openfoam.openfoam_environment import load_openfoam_environment
runtime = load_openfoam_environment(
    explicit_bashrc='/Volumes/OpenFOAM-v2412/etc/bashrc'
)
env = runtime.env
```

Measured environment identifiers (only relevant public runtime metadata recorded):

```text
WM_PROJECT=OpenFOAM
WM_PROJECT_VERSION=v2412
WM_PROJECT_DIR=/Volumes/OpenFOAM-v2412
WM_OPTIONS=darwin64ClangDPInt32Opt
FOAM_API=2412
FOAM_ETC=/Volumes/OpenFOAM-v2412/etc
```

`shutil.which('foamDictionary', path=env['PATH'])` resolved to:

```text
/Volumes/OpenFOAM-v2412/platforms/darwin64ClangDPInt32Opt/bin/foamDictionary
```

Running that exact binary with `-help` under `env` reported:

```text
Using: OpenFOAM-v2412 (2412)
Build: _8dbc61e11c-20241220
Arch: LSB;label=32;scalar=64
```

The effective queries execute `(resolved_binary, dictionary_path, '-entry', entry, '-value')` through `resolve_effective_foam_entry(..., bashrc=None, env=env)`. They do not depend on host PATH containing OpenFOAM.

Minimal inert includeEtc reproduction after loading `env` above:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from omnidriver.openfoam.effective_dictionary import resolve_effective_foam_entry
with TemporaryDirectory() as d:
    root = Path(d)
    site = root / 'site'
    include = site / 'etc/caseDicts/profiling/parallel.cfg'
    include.parent.mkdir(parents=True)
    include.write_text('siteProbe 123;\n')
    dictionary = root / 'd'
    dictionary.write_text(
        'FoamFile { version 2.0; format ascii; class dictionary; object d; }\n'
        '#includeEtc "caseDicts/profiling/parallel.cfg"\n'
    )
    result = resolve_effective_foam_entry(
        dictionary, 'siteProbe', bashrc=None,
        env={**env, 'WM_PROJECT_SITE': str(site)},
    )
    print(result)
    print(str(include.resolve()) in result.inspected_files)  # False
```

Resolution repair must use a bounded, source-equivalent mechanism for the selected runtime, verified against its native oracle. Replacing the present single-path guess with a larger guessed search list would repeat the defect. Native `foamDictionary -includes` appears in this runtime's help, but should not be assumed an inert safe-closure discovery mechanism without testing its directive behavior. Refusal is an acceptable temporary result until the safe closure is established.
