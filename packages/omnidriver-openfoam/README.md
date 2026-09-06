# omnidriver-openfoam

OpenFOAM environment plugin for `omnidriver`. Translates the core
orchestrator's generic requests into OpenFOAM actions: `controlDict` parsing,
fallback `blockMeshDict` provisioning, and `foamlib`-based dictionary
mutation. Depends on `omnidriver`, knows nothing about specific physics.

## Dictionary capability boundary

The adapter deliberately exposes two different kinds of dictionary work.
`read_foam_entry` is **lexical inspection**: it returns raw source text,
preserves quoted strings, ignores comments, and never follows includes,
expands substitutions, or evaluates directives. It is suitable for inspecting
and applying known, catalogue-addressed edits without making a runtime claim.

Effective OpenFOAM resolution is a separate native operation. The conformance
fixtures use `foamDictionary` from `/Volumes/OpenFOAM-v2412` as the oracle for
includes, substitutions, duplicate-key precedence, nested dictionaries,
dimensions, lists, comments, quoted strings, and multiline values. That is
local v2412 evidence only; it does not claim support for other OpenFOAM
versions or distributions.

`resolve_effective_foam_entry(...)` exposes that native operation explicitly.
It reports the parser/runtime identity and inspected local files, follows only
quoted local includes it can inspect, records environment variables used to
resolve quoted include paths, preserves OpenFOAM's missing-optional-include
behavior, and returns explicit unresolved status for an unset variable or
runtime-dependent include form. Executable directives require
`allow_executable_directives=True`.

Mutation is transactional within one `apply_overrides` batch: a failed edit
restores the original bytes of every target dictionary. It is not a
crash-recovery or concurrent-writer lock. Directive-shaped override values are
rejected. In particular, `#calc` and `#codeStream` are never evaluated by
lexical inspection or mutation; executing a dictionary directive is an
explicit native execution capability, not a parsing side effect.
