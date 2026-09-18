# cardiacCore runner guide

Use the selected OmniD workflow, then inspect the plugin named catalogs:
`cardiaccore_field_conventions`, `cardiaccore_python_utilities`, and
`cardiaccore_support_boundary`. Select and invoke a transformation through
`cardiaccore_operations`; its operation record is the canonical callable
contract and example, while this guide provides workflow context.

1. Select a supported workflow or an explicit operation ID. Read its
   applicability, status, preconditions, and failure conditions.
2. Resolve required case conventions and assets. The field catalog explains
   the context; the selected case supplies the actual values. Do not hardcode
   matching values merely to satisfy a validator.
3. Use the operation's exact `entrypoints` references. Preparation/read,
   calculation, and write calls have separate inputs and side effects.
4. Report what was computed and any missing capability. An array method is
   not a native-file reader; a proposal is not permission to change a case.
5. On failure, address the declared prerequisite. Do not search old standalone
   scripts for a different algorithm or infer scientific acceptance from an
   operation returning successfully.

Numerical conventions, formulas and method-specific criteria live in the
catalogs rather than being duplicated here. Coverage categories are a named
baseline, and electrode transfer requires explicit comparative-study
selection. Neither establishes general scientific acceptance.
