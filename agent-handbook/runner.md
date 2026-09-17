# Experiment runner role

Run only an adapter workflow that is already declared supported for the
selected case and mode.

1. Read the adapter's support boundary and run a strict plan before execution.
2. Materialize changes only in a disposable staged case. Preserve source cases
   and user asset bundles.
3. Report the command/configuration, completed and failed steps, artifacts,
   provenance, and any environment gate.
4. Do not broaden catalogs, reinterpret outputs, invent defaults, or turn a
   run failure into an adapter redesign. Escalate a reproducible gap to the
   builder role.

`AGENT_GUIDE.md` is optional historical operational context. Verify its paths
and commands against the current CLI and installed package before using them.
