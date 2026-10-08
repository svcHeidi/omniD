# The agent harness: measuring agents with and without omniD

**Status:** design, approved in conversation 2026-10-09 (sub-project D).

## Why

omniD's goal is easy, deterministic agent access to solvers. Nothing measures
that today. `AGENTS.md`, `agent-handbook/guidance-manifest.yaml` and
`provider-integration.md` describe a launcher that injects guidance and records
its hashes, and `evaluator.md` describes held-out comparisons, but no code
implements any of it. There is no task set, no baseline without omniD, and no
model comparison.

## Decisions taken

- **A sixth package, `packages/omnidriver-agents`.** It drives omniD only
  through the `omnidriver` CLI and its JSON, and imports nothing from
  `omnidriver.*`. `scripts/check-import-boundaries.py` gains the rule that no
  package imports it and it imports no omniD package. LLM tooling is optional
  extras; the core wheel is unaffected.
- **Models are driven through their agent CLIs**, headless, each in a fresh
  folder per trial. The first adapter is Claude Code
  (`claude -p --model <m> --output-format stream-json`), which yields the
  transcript, tokens, cost and turns. Codex and local models via ollama come
  later, one adapter each, when an experiment needs them.
- **No pytest test calls a model.** Tests use a scripted fake adapter, by the
  same rule as "no pytest test runs a solver".

## Units

| unit | one job |
|---|---|
| `task` | load a task file: `id`, `role`, `brief`, `inputs` (repo, plugin, cases root, input bundles), `budget` (turns, wall time), `oracle` (an argv whose JSON verdict decides success) |
| `guidance` | the launcher of `provider-integration.md`: read the manifest, concatenate `common` and the role's `required` files, fail on a missing path, return the text and each file's SHA-256 |
| `trial` | make the trial folder, export the native tree (`git archive`), digest it, write the launch shims, run the adapter, run the oracle, digest the tree again, write the record |
| `adapters/claude_code` | build the `claude -p` command, parse `stream-json` into transcript, usage, cost and turns |
| `shims` | small wrappers put first on `PATH` for each solver program and `mpirun`, logging argv, exit code and duration, then running the real program |
| `cli` | `omnidriver-agents run --task <file> --model <m> --condition omnid|bare --repeats N --output <dir>`, and `summarize <dir>` (one table, no plots) |

## Conditions

- `omnid`: the guidance is injected (`--append-system-prompt`), `omnidriver` is
  on `PATH`, and the scratch root is supplied in the brief.
- `bare`: no guidance, no `omnidriver` on `PATH`; the agent has the native tree,
  its docs and the solver.

Both conditions get the same brief, budget, shims and oracle.

## Isolation (must be verified before any trial counts)

Without `--bare`, `claude -p` loads the user's `~/.claude` memory, plugins, hooks
and any `CLAUDE.md` above the working folder, which would contaminate a trial
with omniD knowledge. Trials therefore run in a folder outside every repository,
with either a dedicated `CLAUDE_CONFIG_DIR` logged in once, or an API key with
`--bare`. The first implementation task proves which works by a probe trial that
asks the agent to list what it was told, and records the answer.

## The task record

`<output>/<task>/<model>/<condition>/<n>/task_record.json`:
model and CLI version, condition, omniD commit and dirty flag, guidance paths
and SHA-256s, task file digest, wall time, turns, input and output tokens, cost,
solver launches (from the shims), omniD refusals (`"status": "failed"` in the
transcript's tool results), the oracle's verdict JSON, and the native tree's
digest before and after. Beside it, `transcript.jsonl` and `launches.jsonl`.

## First experiment

- Role: runner. Task: run the N-version benchmark on openCARP at the coarsest
  resolution and report activation times. Oracle: `omnidriver compare` of the
  agent's output against a frozen reference run.
- For `bare`, the agent's output is not an omniD run document, so the oracle reads
  the LAT file by path; whether `compare` can do that, or the oracle needs a small
  reader, is settled when the task is written (ROADMAP §5 lists "artifacts chosen
  by format or path" for `compare`).
- Models: Opus, Sonnet, Haiku. Conditions: `omnid`, `bare`. Three trials each.

## Success

- A fake-adapter trial produces a complete task record in a test.
- The isolation probe shows a trial sees no user memory, plugin or `CLAUDE.md`.
- The first experiment produces 18 task records and one summary table.
