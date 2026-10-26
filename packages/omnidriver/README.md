# omnidriver

Solver-agnostic workflow orchestrator: tutorial records, strict planning,
DAG execution, parameter sweeps, JSON schema validation and provenance. It
contains no physics; it names an environment binding (`Allrun`,
`system/controlDict`, ...) only where a plugin can declare its own in its
place, and `scripts/check-core-shape.py` in the source repository fails on
any other.

See the source repository's `AGENTS.md` for where to start,
`ARCHITECTURE.md` for the package split and `docs/superpowers/ROADMAP.md` for
the current state (links to files in this repository do not resolve from a
standalone package install).
