# Experiment runner role

Run a record a solver's stack already declares. Every fact you act on comes
from one of these commands, in this order; each prints JSON, and a refusal is
`{"status": "failed", "code": ..., "error": ...}` with exit 1. Select the stack
with `--repo <solver repository>` or, for a solver with no repository,
`--plugin <id>`.

1. `omnidriver env`: the variables the solver's shell needs, the
   `shell_prefix` to run every later command behind, the MPI launcher, the
   `host` (laptop or scheduler allocation) and a serial and 2-rank preflight.
2. `omnidriver describe`: the stack's `records` (with `serial_only` and their
   `inputs`), the repository's `scripts` and the utilities a step may run
   (`utility_manifests`).
3. `omnidriver describe --entry <record>`: the keys a study may set, each axis
   with its unit and bounds, the readers of the record's outputs, its
   conformance quantity and the solver's guidance. `omnidriver catalog --entry
   <record>` lists every key.
4. `omnidriver plan --strict --entry <record> --scratch-dir <dir>`: stages a
   copy and says, before anything runs, whether the run is valid and its
   environment ready (`ok`, `blocked` or `failed`, each failure with a `code`).
5. `omnidriver run --run-document <plan's run_document.json>`, or for a study
   `omnidriver sweep-plan`/`sweep-run --spec <sweep.json>`.
6. `omnidriver compare --comparison-request <request.json> --report <path>`:
   quantities from two runs, against the request you wrote before reading them.
7. `omnidriver-verify`, for a verification task: a manufactured problem's
   definition, a solver's field against its exact solution as error norms, and
   observed against stated convergence orders.

Rules:
- Stage only. The native case and supplied inputs are never written; the
  scratch root is supplied, never invented.
- Report the commands, the steps completed and failed, the artifacts, the run
  document's provenance and every refusal's `code`.
- Do not broaden a catalogue, reinterpret an output or invent a default. A
  reproducible gap goes to the builder role.

`AGENT_GUIDE.md` explains each command's fields; `omnidriver --help` is the
authority on a flag.
