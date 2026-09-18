# Builder role

Use this role to create or extend a solver adapter. The detailed evidence
contract is authoritative; this page only selects actions.

1. Identify the user-selected tool and workflow. Inventory native commands,
   dictionaries, inputs, outputs, assets, and existing checks.
2. Classify each fact as mechanical, a domain decision, or an adapter
   algorithm. Discover mechanical facts. Ask the user only for the latter two
   when evidence cannot decide them.
3. Publish the smallest evidence-backed vertical slice: request → staged case
   → native command(s) → named artifacts/checks. Mark the rest conditional,
   candidate, unknown, or unsupported.
4. Reuse OmniD/Core/OpenFOAM facilities before creating a solver parser or
   Core abstraction. Add Core only for a reproduced generic orchestration
   defect. For OpenFOAM dictionaries, start from the source scanner and keep
   the catalog behind its drift gate; the evidence contract's "Existing OmniD
   route for OpenFOAM dictionaries" names the functions. Do not hand-copy keys
   the scanner can list.
5. Validate a focused native run using explicitly named assets. Record
   mutation, command status, artifacts, provenance, and unresolved gates.

For adapter-side Python, define inputs, outputs, error behavior, owner, and
tests. Do not recreate a native scientific algorithm in Python merely because
the agent can see its inputs or outputs.
