# Simulation foundation and solver semantics audit

Date: 2026-09-05. Scope: OpenFOAM foundation, dictionary semantics, C++ evidence, runtime identity, and cardiacFOAM integration. This is a roadmap audit; no production code or simulations were changed or run by this team. Evidence comes from inspected implementation/tests, tiny temporary-file probes, installed OpenFOAM v2412 source, and primary documentation. Line references are to the audited working tree. Cardiac specialist findings are incorporated below when complete.

## Assessment

The intended split is sound: omniD owns decisions and execution policy; the OpenFOAM package owns the semantics of that runtime; cardiacFOAM owns its physics and solver-specific constraints. The current implementation provides useful pieces, but it does not yet supply authoritative effective configuration to the agent. Deterministic string processing can consistently return the wrong solver value. A publishable contract must expose what was actually established, by which evidence, for which build, and what remains unknown.

“Will run” must be scoped. Configuration conformance, runtime availability, model registration, artifact readiness, numerical convergence, and scientific validity are different claims. The first four can receive bounded evidence before execution. Convergence and scientific validity require numerical checks and cannot be guaranteed for arbitrary cases merely by expanding a catalogue.

## Verified foundation findings

| ID | Priority | Finding and effect | Evidence |
|---|---|---|---|
| OF-01 | P0 | The fast dictionary reader/writer treats entries inside C-style block comments as live entries. A requested override can report success while the solver's active value remains unchanged. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/mutators.py:35`, `:277`, `:284`, `:357`, `:373`, `:395`; temporary-file reproduction below. |
| OF-02 | P0 | Read results conflate absence and inability to determine a value. Includes and legal multiline entries return `None`; macros remain literal `$base`. Readers offer no provenance or resolution status. A later default cannot safely distinguish a missing value from an unevaluated value. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/mutators.py:251`, `:274`, `:281`, `:291`; `config_values.py:8`. |
| OF-03 | P1 | OpenFOAM environment sourcing can fail and still return `error=None`: the source script disables errexit, then exports the environment, overwriting the source command's status. A partially initialized runtime can be accepted. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam_environment.py:163`, `:202`, `:217`; temporary bashrc reproduction below. |
| OF-04 | P1 | C++ scanning is discovery evidence, not a default or compatibility oracle. It stores only kind/name/file/line; it does not recover the dictionary path, conditional control flow, default expression, C++ type, preprocessor selection, or binary registration. Multiline comment removal shifts reported source line numbers. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_keys_scanner.py:29`, `:54`, `:63`, `:116`, `:155`; reproduced incorrect line below. |
| OF-05 | P1 | Unknown-key checks disappear entirely on parse/IO exceptions; individual failed node reads also disappear. A clean diagnostic list cannot mean full dictionary coverage. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/case_dict_keys.py:102`, `:116`, `:121`, `:154`. |
| OF-06 | P1 | A solver-neutral package assigns physical units from cardiac-sized bounding boxes and raises errors based on the inference. Extent 20 is classified as mm, although a legitimate generic OpenFOAM domain can be 20 m. Coupling can also be assumed from all regions. Coordinate magnitudes do not establish units. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/mesh_geometry.py:26`, `:52`, `:165`, `:199`, `:220`. |
| OF-07 | P1 | Catalogue examples can become written configuration through default-on `typical_value_fallback`; the shared catalogue shape has no explicit distinction between documented example, recommended profile, source default, runtime default, and user choice. This can change the simulation rather than merely describe it. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_builder.py:132`, `:187`, `:195`; `packages/omnidriver/src/omnidriver/core/contracts/dictionary.py:15`. |
| OF-08 | P2 | Generic environment checks verify variable presence and command resolution, with optional source/binary mtime warnings. They do not establish the full OpenFOAM runtime identity. Discovery sorts filesystem paths in reverse lexical order; that is convenience discovery, not version compatibility selection. | `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment_preflight.py:107`, `:196`, `:214`; `openfoam_environment.py:50`, `:99`. The cardiac plugin has additional manifest machinery; its strength is assessed separately. |
| OF-09 | P2 | Standing dictionary differential conformance to OpenFOAM is missing from the inspected test harness: it explicitly says prior comparisons were one-time and removed, leaving an inert-directive test. Numerous regression tests exist, but mostly compare Python paths or self-consistent results. Source-dependent drift checks can skip in standalone installs. | `packages/omnidriver-openfoam/tests/core/test_mutators_differential.py:1`; `tests/conftest.py:6`, `:17`, `:58`; `tests/drift_guards/test_mesh_geometry_contract.py:15`. |

P0 means the current public contract can misrepresent or apply the wrong configuration, so it should be repaired before making stronger readiness claims. These priorities are local to this audit, not claims of exploitation or scientific harm in an observed production run.

### Temporary-file reproductions

Executed with the existing `.venv/bin/python`, importing production functions. Temporary directories were cleaned by Python. No permanent regression tests were added.

Input to `read_foam_entry(path, "deltaT")` and `update_foam_entry(path, "deltaT", "0.02")`:

```text
/*
deltaT 99;
*/
deltaT 0.01;
```

The reader returned `"99"`. The writer changed the commented entry to `deltaT    0.02;` and preserved the active `deltaT 0.01;`. This is stronger evidence than simply saying the parser is heuristic: the documented override intent and the actual active case diverge.

Additional reads:

| Input | Observed result |
|---|---|
| `base 0.01;` followed by `deltaT $base;` | `"$base"` |
| `#include "baseDict"`, with an existing sibling file containing `deltaT 0.01;` | `None` |
| `deltaT` followed on a new line by `0.01;` | `None` |

A synthetic bashrc containing `export WM_PROJECT_DIR=/tmp/nonexistent-openfoam` followed by `return 7` produced `OpenFOAMEnvironment(error=None)` and retained the exported variable. This verifies a masked source error; it does not establish that every downstream runtime check would pass.

A synthetic C++ file with a three-line block comment followed by `dict.lookupOrDefault<scalar>("alpha", 2)` at line 4 was reported by `scan_dict_reads` as line 2. The scanner's `_strip_comments` deletes newlines before `_line_of` runs.

### What OpenFOAM actually evaluates

The installed v2412 implementation invokes function entries and expands variables: `/Volumes/OpenFOAM-v2412/src/OpenFOAM/db/dictionary/entry/entryIO.C:212`, `:228`, and `primitiveEntry/primitiveEntryIO.C:91`, `:106`. Duplicate-entry treatment depends on input mode (`entry/entryIO.C:112`, `:317`, `:339`, `:348`). Pattern lookup is implemented by the runtime (`dictionarySearch.C:39`, `:280`), with insertion order maintained by `:685`. These behaviors belong to the selected OpenFOAM distribution/version; Python matching should not implicitly claim equivalence across distributions.

foamlib is useful for inert file manipulation, but its own documentation explicitly says regex and directives are not evaluated/expanded and that `#codeStream` files are unsupported. That is an important capability boundary, not a failure of foamlib. [foamlib file manipulation documentation](https://foamlib.readthedocs.io/en/stable/files.html).

## Retain, refactor, and remove

**Retain:** the package boundary; inert parsing as a distinct operation; foamlib's structured mutation support; rejection of directive-shaped scalar overrides (`foam_backend.py:122`); scoped override APIs; source scanners as discovery tools; typed diagnostic codes; tutorial fixtures and existing regression cases; runtime manifests where backed by actual build evidence.

**Refactor:** replace the line scanner as semantic authority with a single parser service that reports coverage and ambiguity. A fast path may remain only if it is proven equivalent on its declared subset. Separate parse, resolve, validate, patch, and probe operations. Preserve original spans and duplicate occurrences. Move cardiac physical-size assumptions out of generic OpenFOAM policy; require declared coordinate units and explicit conversions. Replace unstructured `source_refs` with verified references tied to a source revision and runtime identity. Make typical/example values opt-in profile inputs with visible provenance.

**Remove from correctness paths:** silent exception-to-empty-diagnostic behavior; `None` as the sole representation of absent/unresolved/invalid values; auto-selection of a runtime as evidence of compatibility; source regex scans as proof of C++ defaults; formatting equivalence as a substitute for runtime semantics; explanatory examples that automatically become scientific defaults. Remove obsolete comments about a foamDictionary-first writer once implementation migration is complete.

Do not respond by rebuilding all of OpenFOAM in Python or adding a broad generic “C++ understanding” layer. A bounded query bridge around selected compiled runtime operations is more falsifiable than a growing collection of regex approximations. Compiler-assisted extraction can add declaration/call-site evidence, but it does not by itself prove dynamic dictionary behavior or loaded plugin registrations.

## Proposed foundation contracts

1. **Runtime identity.** Distribution, version, source revision, executable and loaded library hashes, architecture, scalar/label width, compiler/build flags, MPI implementation, GPU backend where relevant, selected environment configuration, and the manifest producer/version. Source provenance and binary provenance are separate fields. A copied manifest never proves that its source revision built its artifacts unless produced by the build process and verified.
2. **Dictionary inspection.** Return an AST or typed entries with source spans, duplicate occurrences, includes/dependencies, raw tokens, and `resolution_status` such as `literal`, `resolved`, `requires_runtime`, `invalid`, or `unsupported`. Missing file, missing key, parse failure, and unresolved macro are distinct outcomes. Inert inspection never executes code.
3. **Effective configuration.** Resolve only a documented safe subset locally; use the selected OpenFOAM runtime in a controlled scratch process for the rest. Return include provenance, environmental substitutions, input mode, chosen pattern, runtime identity, and the effective typed value. Code directives require an explicit execution-capable operation; ordinary inspection reports them.
4. **Patch transaction.** Plan target source locations and effect first; apply to a scratch case, parse/resolve again, assert the intended effective diff and no unintended changes, then commit atomically. For an entry originating in an include or matching regex, report which source entry is affected and whether other fields share it. No partial multi-file edits on failure.
5. **C++ facts.** Source fact kind (`read`, `default_expression`, `registration`, `equation`, `constraint`), exact revision/path/line/symbol, declared context, extractor version, confidence/coverage, and runtime verification where available. Dynamic expressions and preprocessor alternatives remain explicitly unresolved until evaluated for a build.
6. **Compatibility result.** `supported`, `incompatible`, `unknown`, and `unavailable` are distinct. Each rule includes scope, structured inputs, evidence, and remedy. Separately report software acceptance, declared plugin support, runtime availability, and scientific validation status. An uncatalogued numerical option should be queryable and labeled unknown until inspected; it must not automatically be called impossible.
7. **Numerical freedom.** OpenFOAM owns runtime-selected discretization, linear solvers, preconditioners, time control, boundary/field primitives, dimensions, and general mesh representations. cardiacFOAM constrains these only where its equations/implementation require it. Presets record explicit choices; original runtime defaults remain separately visible. Agent exploration is a typed patch proposal with preconditions and effective configuration evidence.

## Work packages and acceptance gates

| Phase | Owner | Bounded work | Acceptance gate |
|---|---|---|---|
| 0: Establish truth | Foundation lead + test expert | Register supported OpenFOAM/runtime tuples; preserve current behavior fixtures; reproduce OF-01/02/03/04; inventory silent fallback paths; publish coverage statuses. | Every failure above is represented by a regression fixture; unsupported syntax is explicit; environment failure cannot masquerade as successful sourcing. |
| 1: Dictionary semantics | Parser expert + OpenFOAM C++ expert | Implement inspection and effective-value contracts; preserve comments/quoted strings/multiline entries; handle includes/macros/patterns/duplicates according to declared support. | A maintained corpus compares effective values against pinned native OpenFOAM for each supported tuple. The corpus includes include graphs, recursion/cycles, environment substitutions, quoted regex precedence, duplicate modes, missing inputs, and code directives. Inert operations never execute directive code. |
| 2: Transactional edits | Mutation expert | Consolidate read/write semantics; scratch staging, intended diff, post-resolution checks, atomic commit; provenance per override. | Failed edits leave the entire case unchanged. Each accepted edit changes exactly the declared effective values. Included/shared pattern entries receive explicit handling. |
| 3: Runtime/source binding | Build/runtime expert | Publish build-generated manifests and native introspection; preserve source positions; extract selected defaults, dimensions, registrations, and conditions; expose unknowns. | Changing source, build flags, artifact/library, or runtime version invalidates corresponding facts. Missing evidence produces unknown/unavailable. Available registrations match the selected loaded libraries. |
| 4: Solver contracts | Cardiac physics lead + model experts | Reconcile solver catalogues, units, model compatibility, conditional fields, and preset values with source and runtime; attach tutorials to claims. | Every enforced rule has executable evidence; examples cannot silently become defaults; supported selector combinations have positive/negative preflight fixtures and bounded smoke runs in dedicated CI. |
| 5: Scientific and release evidence | Verification lead | Maintain minimal numerical benchmarks and release support matrix; package standalone artifacts; document limits and controlled extension workflow. | Tests distinguish dictionary conformance, executable readiness, convergence, and scientific benchmark outcomes. Fresh installed packages can reproduce representative cases on every advertised tuple without a developer checkout. |

Each phase can begin with one deliberately narrow vertical slice (for example a supported single-cell case on the configured v2412 CPU runtime). Expand after the slice demonstrates the full evidence chain. Do not claim all OpenFOAM configurations are covered merely because a finite tutorial suite passes.

## Specialist integration

The independent [cardiacFOAM expert report](cardiac-expert.md) is complete. Its C++ observations use `/Users/simaocastro/noFrontendCardiacFoam_minor_errors` at `b39b65a25ccb8f62c861e3f6b5636274a77d44b3` with local changes; this is explicitly not proof of the installed binary's source identity.

The expert reproduced three additional contract failures using temporary-function probes: a manifest with no artifact list passes its validator; an unlisted solver pair yields no coupling diagnostic; and two independently allowed named networks can be rejected because every coupler is checked against the first network's solver. The source implementation resolves each coupling's named network. These findings reinforce the need for runtime-bound evidence and correctly scoped rules, not simply larger catalogs.

The expert also found that runtime-generated manifests infer historical build information from the current environment/source tree; a catalog recommendation described as dimensionless occupies fields documented as SI PDE stimulus; live catalog verification misses models absent from the catalog; and adding a catalog entry can automatically expand tutorial declarations without new validation evidence. The expert report carefully separates metadata inconsistency from demonstrated numerical failure. No scientific settings were changed.

Add manifest completeness/executable binding and named-network compatibility fixtures to the first repair batch. Subsequent gates must verify model inventory in both directions, distinguish generated runtime facts from curated scientific guidance, and bind validated tutorials to a specific support profile. Full evidence, uncertainties and acceptance cases are in CF-01 through CF-05 of the expert report.
