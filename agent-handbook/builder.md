# Builder role

Use this role to create or extend a solver plugin. The evidence contract
(`docs/BUILDER_AGENT_EVIDENCE_CONTRACT.md`) is authoritative; this page only
selects actions.

1. Identify the user-selected solver and workflow. Inventory the native case:
   its commands, dictionaries, inputs, outputs and existing checks.
2. Classify each fact as mechanical, a domain decision, or an adapter
   algorithm. Discover mechanical facts; ask the user only for the other two,
   when evidence cannot decide them.
3. Publish the smallest evidence-backed slice as the objects core defines: a
   record pointing at the native case, catalogue entries, utility manifests
   with their `produces`, and a reader for each declared output format.
4. Reuse omniD, core and the OpenFOAM layer before writing a parser or a core
   abstraction; add to core only for a reproduced generic defect. For
   OpenFOAM dictionaries and utilities, start from the scan
   (`omnidriver catalog --uncatalogued`, `--unread`) and keep the catalogue
   and manifests against it. Do not hand-copy keys the scan can list.
5. Validate with `omnidriver plan --strict`, a focused native run with
   explicitly named inputs, and `omnidriver check` on the record's
   conformance study.

For adapter-side Python, define inputs, outputs, error behaviour, owner and
tests. Do not recreate a native scientific algorithm in Python because its
inputs or outputs are visible.
