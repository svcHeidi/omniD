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
with omniD knowledge. A trial therefore runs in a folder outside every
repository (refused when `git rev-parse --is-inside-work-tree` succeeds there)
with `HOME` set to a dedicated `--agent-home`, also outside every repository:
Claude Code reads its config and login from `<agent-home>/.claude` and
`<agent-home>/.claude.json`, logged in once by hand, holding no memory, plugins,
hooks or `CLAUDE.md`. `SHELL` is `/bin/bash`.

Both conditions get the same tools. `--agent-python` is a Python that cannot
import `omnidriver` (a trial refuses one that can); `<trial>/tools/python3` and
`python` link to it, `tools` is on PATH in both conditions, and the solver shims
use it as their interpreter. Only the `omnid` condition adds
`<trial>/omnid-bin`, which holds two symlinks, `omnidriver` and
`omnidriver-verify`, never their venv. A `bare` trial is refused when its PATH
resolves any `omnidriver*` command.

Claude Code's Bash tool runs commands in a login shell that can rebuild PATH, so
the adapter writes `<trial>/claude-env.sh` (`export PATH=...`) and sets
`CLAUDE_ENV_FILE` to it; Claude Code sources it before each Bash command. The
oracle runs with `omnid-bin` on PATH and with `--oracle-env-file` variables the
agent never sees. The first implementation task proves isolation by a probe
trial that asks the agent to list what it was told, and records the answer.

## The task record

`<output>/<uuid>/task_record.json` (the folder name says nothing of the condition or model; the record carries both):
model and CLI version, condition, omniD commit and dirty flag, guidance paths
and SHA-256s, task file digest, wall time, turns, input and output tokens, cost,
solver launches (from the shims), omniD refusals (tool results carrying
`"status": "failed"` and a `code`), the real path and installed version of the
`omnidriver` that ran, how many transcript events name the omniD repository's
path, the oracle's verdict JSON, and the native tree's digest before and
after. Beside it, `transcript.jsonl` and `launches.jsonl`.

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
