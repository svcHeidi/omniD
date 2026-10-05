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

`inspect_effective_foam_configuration(...)` reads the files a dictionary
depends on without running anything: it follows only quoted local includes it
can inspect, records environment variables used to resolve quoted include
paths, preserves OpenFOAM's missing-optional-include behavior, and returns an
explicit unresolved status for an executable directive, an unset variable or a
runtime-dependent include form.

Mutation is transactional within one case write (`commit_case_write`): a failed
edit restores the original bytes of every target dictionary; a kill
mid-write makes the next `step`/`run` refuse ("an edit of this case was
interrupted ...; plan again"), and planning again restages the case. Directive-shaped values are rejected. In particular,
`#calc` and `#codeStream` are never evaluated by inspection or mutation.
