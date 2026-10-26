# omnidriver-openfoam

The OpenFOAM layer for `omnidriver`, shared by every OpenFOAM-based solver
plugin: the solver's shell and MPI, case reading and writing, the
`controlDict` and `fvSchemes` catalogue, the case rules, parallel
decomposition, and the scanners that compare a plugin's catalogue and utility
manifests with its C++. Depends on `omnidriver`; names no solver and no
physics.

## Dictionary capability boundary

`dictionary_reader.read_foam_entry` is **lexical inspection**: it returns raw
source text, preserves quoted strings, ignores comments, and never follows
includes, expands substitutions, or evaluates directives.

`inspect_effective_foam_configuration(...)` reads the files a dictionary
depends on without running anything: it follows only quoted local includes it
can inspect, records environment variables used to resolve quoted include
paths, preserves OpenFOAM's missing-optional-include behavior, and returns an
explicit unresolved status for an executable directive, an unset variable or a
runtime-dependent include form.

Mutation is transactional within one case write (`commit_case_write`): a failed
edit restores the original bytes of every target dictionary; a kill
mid-write makes the next `step`/`run` refuse ("an edit of this case was
interrupted ...; plan again"), and planning again restages the case.
Directive-shaped values are rejected. `#calc` and `#codeStream` are never
evaluated by inspection or mutation.
