# Solver-onboarding builder: evidence contract

## Purpose

The builder turns a user's short description of a simulation tool and one or
more native workflows into a bounded OmniD adapter.  It makes the workflow
discoverable and executable without claiming that every option in a codebase
is understood or safe to vary.

The builder is **evidence-led**, not source-code-led.  C++ or other source is
an optional, valuable evidence channel when it is available; it is not a
precondition for onboarding a solver.

## Input from the user

The user supplies the tool's purpose and the workflow in scope.  For example:

> cardiacCore prepares conductivity, anatomy, and Purkinje fields used by a
> cardiacFoam run.  Start with `bivCase`.

This selects the semantic boundary.  It does not select a scientific hypothesis
or force a parameter sweep.

The builder asks for more direction only when the user has not identified a
tool/workflow, or when several native workflows imply materially different
interfaces.

## Evidence ladder

For every declared fact, retain its evidence origin and scope.  Prefer the
strongest applicable evidence; do not treat a weaker source as equivalent to a
stronger one.

| Evidence channel | What it can establish | Limit |
| --- | --- | --- |
| Native case files, scripts, and dictionaries | A concrete workflow, the files it names, and its authored values | An example does not make every value generally supported. |
| Documentation and command help | User-facing option names, formats, and stated outputs | Documentation may lag the installed runtime. |
| Public API, schema, or machine-readable metadata | Declared option shape and result interface | It may not establish a specific installed build's availability. |
| Source code | Candidate readers/writers, registrations, defaults, and conditions | Static inspection does not prove runtime branches, loaded libraries, or effective configuration. |
| Controlled execution | Availability of one runtime path and observed artifacts | A successful run is not a general compatibility or scientific-validity claim. |

Unavailable evidence is explicit: `unknown`, `unsupported`, or `unavailable`.
It must not silently become a default, a mutable parameter, or a supported
claim.

The same rule applies to physical units.  A familiar convention (for example,
SI conductivity) is not a verified unit claim.  Leave a unit empty and record
the limitation until native documentation, an inspected dimensional definition,
or domain review establishes it for the selected workflow.

## Builder outputs

The builder produces four linked, inspectable catalogs for the selected native
vertical slice:

1. **Workflow catalog** — ordered commands, case entrypoint, dependencies,
   runtime requirements, and staging behavior.
2. **Input catalog (x candidates)** — dictionary/API/file settings a user may
   configure.  Each entry records its path, value shape, applicable workflow,
   evidence, and whether mutation is supported, unavailable, or still only a
   discovered candidate.
3. **Output catalog (y values)** — fields, files, logs, or structured result
   records produced by each command.  Each records its producer, path/pattern,
   format, evidence, and whether it is a final result or an intermediate
   consumed by a later step.
4. **Support boundary** — supported workflows and explicit exclusions.  An
   adapter never advertises every command in a repository merely because it
   found them during discovery.

Here, **x** means a catalogued controllable input.  It does not yet mean a
sweep axis.  A sweep is a later user request that selects supported x entries
and concrete values.  **y** means the output of a utility or solver stage; it
may be an intermediate field rather than a scientific metric.

## Candidate versus supported facts

Discovery may collect candidates broadly.  The published catalog is narrower.

| State | Meaning | May plan/run? | May mutate? |
| --- | --- | --- | --- |
| `supported` | Evidence covers this exact workflow/build scope and an adapter contract exists | Yes | Only if its mutator and validation exist |
| `observed` | Seen in a native case or controlled run, but not generalized | Only in that declared case scope | No by default |
| `conditional` | Required by a named workflow mode whose role was confirmed by the owner | Only after that mode and its prerequisites are selected | Only with complete mode-specific validation |
| `candidate` | Found in documentation/source/static inspection | No | No |
| `unknown` | A relevant fact could not be resolved | No strict claim | No |
| `unsupported` | Explicitly outside the adapter slice | No | No |

The labels prevent a source scan or example dictionary from becoming an
unreviewed global catalog.

## When to ask the owner

Source and cases can often establish that a value is required, optional, or
conditional. They do not always establish the domain-level name of that
condition. Before publishing an ambiguous branch, the builder asks a concise
question such as: “Which workflow needs these paired tensor dictionaries?” or
“What does this manual groove branch represent?” The answer becomes a
declarative condition in the catalog, not hidden reasoning in the agent.

For cardiacCore, the owner established that paired intracellular/extracellular
tensors belong to bidomain preprocessing, manual groove inputs belong to
manual AHA segmentation, and `subendocardialWeight` belongs to the pig
Purkinje morphometry algorithm.

## Cross-solver closure

A preprocessing adapter can establish that it writes an artifact and which of
its own branches create it.  It cannot, from that repository alone, establish
every downstream solver or mode that requires the artifact.

Until a consuming solver is available, the builder records a conditional
relationship with its evidence and, where needed, a concise owner-supplied
meaning.  It does not invent a complete consumer matrix.  Once a downstream
solver/case is provided, the builder follows the chain:

`producer output → consuming solver input → selected solver/mode → staged
combined workflow`

It then upgrades the relationship only if the consumer's case, configuration,
documentation, source/API, or runtime evidence actually supports it.  This is
how a multi-solver workflow closes most otherwise ambiguous conditions.

For example, cardiacCore can establish that it can write paired bidomain
tensors.  Access to the bath-bidomain cardiacFoam workflow is needed to bind
those tensors to that solver mode and validate the combined path.

## Python adapter versus JSON experiment request

Python is the adapter's implementation language. It owns the evidence-backed
catalog, the mapping from a stable x path to a native file/scope, conditional
rules, validation, staging, and y interpretation. OmniD's `DictEntry` and
`DictionaryCatalog` are the reusable Python contract; do not invent a second
parser or schema engine for each solver.

JSON is normally the user's experiment request. It says either “run this
tutorial with these values” or “materialize one disposable case per listed
value set.” It must be validated by the adapter and applied only to a staged
case, never by changing the native tutorial defaults. For example, the first
cardiacCore slice accepts a normal-run request of the form:

```json
{
  "input_overrides": {
    "$PURKINJE_SLAB.thickness": 0.05
  }
}
```

Its one-axis sweep uses the same input object as the axis value:

```json
{
  "base": {"entry": "cardiaccore-human-purkinje-slab"},
  "sweep": {
    "mode": "cross_product",
    "independent": {
      "input_overrides": [
        {"$PURKINJE_SLAB.thickness": 0.05},
        {"$PURKINJE_SLAB.thickness": 0.10}
      ]
    }
  }
}
```

The JSON object is a user intent, not the adapter definition. Python remains
necessary for resolving a condition from a live case, expanding dynamic paths,
performing transactional mutation, invoking a native query, or interpreting
results. JSON/YAML may also store settled static facts such as a profile or an
exported catalog, but a small catalog need not be forced into JSON.

## Case assets are part of the contract

A runnable native case may depend on assets absent from Git: a mesh, initial
fields, imaging-derived data, a generated coordinate field, or a licensed
binary input. The builder must inventory each consumed asset and label its
origin as tracked, generated (with its generator), user-supplied, or unknown.
It must then either stage the asset, name the generator, or refuse the run.

A successful local run must not silently turn an untracked mesh or initial
field bundle into a tutorial default. The selected cardiacCore `bivCase`
demonstrated this boundary: its source snapshot contains the dictionaries and
wrapper, but not `constant/polyMesh` or the initial `0/` fibre/UVC fields.
Those are prerequisites for a clean-user execution, not outputs OmniD may
fabricate. A valid experiment may instead name a separately versioned asset
bundle and stage only its declared inputs. In CC-1, mesh plus raw
`fiber`, `sheet`, and `uvc_*` fields from
`cardiacCore-local-cases/bivCase_Pig_Morphometric_Tree` were staged into the
clean source tutorial; the source tutorial's dictionaries and four-stage
workflow remained unchanged, and the run completed. This validates the asset
interface, but does not make that local case an implicit default or close the
future distribution/generator requirement.

## OpenFOAM and source-available adapters

When the source is available, the builder may use it to strengthen a catalog:

- a utility's dictionary reader can corroborate an input key and its scope;
- a writer can corroborate a generated field name;
- registrations can identify candidate commands or models;
- build/runtime inspection binds a claim to the executable actually invoked.

Source inspection remains discovery/corroboration.  Effective OpenFOAM
dictionaries, conditional branches, dynamically loaded libraries, and runtime
selection require their own evidence.  Do not create a generic C++ reasoning
layer in Core.

### Existing OmniD route for OpenFOAM dictionaries

Do not add a solver-specific parser when the selected input is an ordinary
OpenFOAM dictionary entry.  Reuse the established layers:

- `core.contracts.dictionary.DictEntry` and `DictionaryCatalog` for reviewed
  input/x declarations;
- `openfoam.mutators.read_foam_entry` for lexical, read-only values at a
  concrete dictionary path and scope;
- `openfoam.effective_dictionary` when native include/substitution resolution
  is required;
- `openfoam.apply_overrides` and `update_foam_entry` only after the solver
  adapter has declared valid target scopes, transaction targets, and semantic
  constraints.

Discover and guard dictionary keys with the same layers before writing a
catalog by hand (added 2026-09-16, after the cardiacCore adapter re-typed keys
the scanner already finds):

- `openfoam.dict_keys_scanner.scan_dict_reads(src_root)` lists every
  `lookup`/`get`/`getOrDefault`/`found`/`readEntry`/`subDict` read with file and
  line. It is the inventory to start from, not an accepted catalog. Each read
  carries `scope` (enclosing sub-dictionaries recovered from local
  `dictionary&` bindings and chained `subDict` calls; a runtime name appears
  as `<var>`, and `()` through a function parameter means "not recovered") and
  `method`. `dict_read_default(read)` returns the source default expression
  of an `*OrDefault` read, unevaluated.
- `openfoam.dict_keys_scanner.strict_dict_key_report(src_root, allowlist_path=,
  entries=)` is the drift gate between that inventory and the adapter's
  `DictEntry`s; the allowlist holds reviewed non-catalog reads (graph-file
  keys, upstream OpenFOAM keys, false matches). Every source-available adapter
  should test it when a native source root is supplied.
- `DictEntry.dynamic_path` with `<name>` segments covers instance-named blocks
  such as `regions.<id>.<key>`; do not enumerate instances or skip them.
- `openfoam.case_dict_keys.case_dict_key_diagnostics` warns about keys written
  in a supplied case that the catalog does not know.
- `openfoam.dict_builder` (`select_applicable_entries`, `check_required`,
  `populate_values`) materializes dictionary text from catalog entries.
- `core.utility_catalog.UtilityManifest` / `ProducesEntry` declare a native
  command's inputs and produced artifacts.

`scripts/scan-dict-keys.py` is a cardiacFoam-specific front end to the scanner;
call the module functions directly for another adapter.

Use a solver-specific adapter only to map its vocabulary to those mechanisms:
which file and scope an x value belongs to, when it is applicable, and what
validation/refusal is required.  It must not duplicate OpenFOAM tokenization,
parsing, rollback, or effective-value resolution.

## Source-unavailable adapters

For a tool such as openCARP, source access may be absent.  The builder uses the
same contract with different evidence:

- examples and native input files establish a bounded workflow;
- manuals, schemas, and CLI help establish configurable inputs;
- documented/observed result files establish outputs;
- a controlled run establishes the installed runtime path.

The resulting adapter is not lesser; its claims are simply scoped to the
evidence available.  Missing source-derived detail remains unknown instead of
being guessed.

## Required execution discipline

Before declaring a native vertical slice complete:

1. Preserve the source case and stage a disposable copy.
2. Make the workflow's command and dependency graph explicit.
3. Declare consumed inputs and produced artifacts per step.
4. Strict-plan using the selected runtime.
5. Run the staged case, reconcile required artifacts, and record logs/state.
6. Ensure generated outputs are not later represented as authored source
   inputs; retain an intermediate output when a later step explicitly consumes
   it.
7. Add a focused regression test for each corrected adapter/core contract.

This validates orchestration and declared artifacts.  It does not establish
numerical convergence, physiological validity, or support beyond the stated
slice.

## cardiacCore example

For `bivCase`, the user-defined boundary is a preprocessing tool required
before a cardiacFoam simulation.  The initial catalog is therefore utility
based:

| Utility | x candidates | y outputs |
| --- | --- | --- |
| `setCardiacConductivity` | `df`, `ds`, `dn`, field-name selections | `Conductivity`, optional paired tensors |
| `setCardiacAnatomy` | anatomical dictionary settings | `AHA_Segment`, `aha_angle` |
| `setPurkinjeSlab` | thickness, multiplier | `PurkinjeLayer`, updated `Conductivity` |
| `setPurkinjeMorphometry` | its documented dictionary settings | region labels and terminal-weight fields |

The next implementation increment is to extract this input catalog with
per-entry evidence and mutation validation.  It must not automatically expose
every lexical dictionary key as an x value.

## Ownership

- **Core** owns generic staging, planning, execution, artifact reconciliation,
  provenance, and the generic evidence/result vocabulary.
- **Environment adapter** owns runtime conventions and format interpretation
  (for example OpenFOAM dictionaries, time directories, and environment
  loading).
- **Solver adapter** owns the selected workflow, catalogued inputs/outputs,
  semantic validation, and result interpretation.
- **The builder agent** assembles and tests those adapter declarations from
  available evidence; it does not infer scientific meaning beyond the user's
  stated tool purpose.
