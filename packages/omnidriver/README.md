# omnidriver

Solver-agnostic scientific workflow orchestrator: DAG execution, parameter
sweep routing, JSON schema validation, and cryptographic provenance
tracking. Contains zero physics rules; it names an environment binding
(`Allrun`, `system/controlDict`, ...) only where a plugin can declare its own
in place of it; `scripts/check-core-shape.py` in the source repository holds
what is left.

See the source repository's root `ARCHITECTURE.md` for the full package split,
and `docs/superpowers/plans/` for what's done and what's open (links to files
in this repository do not resolve from a standalone package install).
