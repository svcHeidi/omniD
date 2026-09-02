# omnidriver

Solver-agnostic scientific workflow orchestrator: DAG execution, parameter
sweep routing, JSON schema validation, and cryptographic provenance
tracking. Contains zero physics rules; it names an environment binding
(`Allrun`, `system/controlDict`, ...) only where a plugin can declare its own
in place of it — see `future/ENVIRONMENT_CONTRACT.md` in the source repository
for the exact rule and how it's enforced.

See the source repository's root `ARCHITECTURE.md` and `GITHUB_MIGRATION.md`
for the full package split (links to files in this repository do not resolve
from a standalone package install).
