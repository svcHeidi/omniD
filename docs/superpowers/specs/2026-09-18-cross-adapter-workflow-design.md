# One workflow, two adapters

**Date:** 2026-09-18
**Status:** design, not yet implemented
**Owner of the mechanism:** `omnidriver` (core). **Owner of the declarations:** each adapter.

## The problem, in one example

A patient ECG and a simulated ECG disagree. The simulation is cardiacFOAM's;
two of the things that could be wrong are not. The Purkinje tree comes from
cardiacCore, and the ionic heterogeneity is cardiacFOAM's own. Answering "why
do these disagree" therefore means running steps from two adapters, in one
ordered whole, and being able to say afterwards which input moved between
attempt three and attempt four.

Today that whole cannot be expressed. Not because the DAG is too weak — it is
almost sufficient — but because a run binds exactly one adapter.

## What already works

Core's step vocabulary is already `id`, `command`, `args`, `cwd`,
`depends_on`, `consumes`, `produces`, `retry_policy`, `timeout_s`. Producer and
consumer relationships between steps are first-class, and
`provenance_inputs._collect_consumed_relpaths` already fingerprints what a step
consumes.

An artifact is already declared **once**, by whoever writes it, as a
`ProducesEntry` in a utility manifest, and surfaces to core as a
`DataArtifact` carrying `artifact_id`, `path_pattern`, `format`, `variables`,
`produced_by` and `optional`. Both adapters do this: cardiacFOAM in twelve
`utility.manifest.toml` files, cardiacCore in `catalogs/utilities.py`, which
builds thirty-five `ProducesEntry` values in Python. **Corrected 2026-09-18**:
an earlier reading of this design claimed cardiacCore declared no `produces`.
It declares them at the utility level; what it does not do is restate them on
workflow steps, which is correct — see below.

Core already resolves that single truth on the producing side. In
`runtime/workflow.normalize_workflow_dag`:

```python
if not produces and command in utility_produces:
    produces = utility_produces[command]
if produces:
    claimed_artifacts.update(produces)
```

A step that says nothing about what it produces is given the manifest's answer,
and every declared artifact must be claimed by some step. Artifacts nobody
claims are credited to the **last step whose command is a producer** —
`entrypoint_relpaths(driver_context)` plus
`command_authorization.solver_commands()`, deliberately excluding auxiliary and
cleanup commands. So the intended model is already visible in the code: **the
artifact declaration is the one truth, and a step refers to it by id.**

`run_workflow_step` takes `driver_context` as a per-call argument. The executor
is therefore already capable of running different steps under different
adapters. Nothing in the step model or the artifact model needs replacing.

## What blocks it

**1. Execution binds one context.** `runtime/workflow_orchestrator`'s step loop
captures a single context and passes it to every step:

```python
context_kwargs = {} if driver_context is None else {"driver_context": driver_context}
result = runner(workflow_dag, workflow_state, step_id, ..., **context_kwargs)
```

**2. Planning binds one context too — in two places.** This is the half that is
easy to miss: fixing execution alone is not enough.

`strict_planning._utility_produces_by_command` takes a `driver_context` and
returns the command→artifact-id map for *that* adapter's utilities. A DAG mixing
`setPurkinjeSlab` with cardiacFOAM's solver resolves only half its commands, so
the `produces` fill-in above — the mechanism that makes the single truth work —
silently covers one adapter.

`normalize_workflow_dag`'s unclaimed-artifact credit resolves its producer set
from one context too. cardiacCore's commands are not in cardiacFOAM's
`solver_commands()`, so in a mixed DAG the last *cardiacFOAM* producer absorbs
artifacts a cardiacCore step actually wrote. That misattribution is worse than a
failure, because the run still succeeds and the provenance is quietly wrong.

**3. `consumes` speaks a different language from `produces`.** Both are parsed
identically, by `_string_list`, but they are read differently:

| key | holds | read by |
|---|---|---|
| `produces` | artifact **ids** | `workflow_runner`: `artifact.artifact_id in step.get("produces", ())` |
| `consumes` | case-relative **paths** | `provenance_inputs._collect_consumed_relpaths` |

So a consumer naming `constant/purkinjeGraph` restates a location that
`1DgraphToFoam`'s manifest already owns as `purkinje_graph_dict`. That is a
second truth about one fact, and it is the one that can drift. Worse, it is
unverifiable: a path that exists satisfies `consumes` whether or not any step
in this run produced it. A stale file from a previous attempt passes.

## The design

### Core change 1 — a step names its adapter

A step may carry an `adapter` key. The orchestrator resolves a context per step
from a mapping the caller supplies:

```python
step = _step_by_id(workflow_dag, step_id)
context = _context_for_step(step, driver_contexts, driver_context)
context_kwargs = {} if context is None else {"driver_context": context}
```

`driver_contexts` is `Mapping[str, DriverContext]`, **supplied by the caller,
never discovered by core**. Core learns one relation — *a step names a context
by key* — and never learns that cardiacCore exists. This is
`future/ENVIRONMENT_CONTRACT.md` §12, and the same rule that made
`own_driver_context` necessary on 2026-09-18: an identity has no ambient truth,
so discovering it invents an answer.

A step naming a key that was not supplied is a **planning** failure, reported
through `LaunchReadiness` before anything executes — not a crash partway
through a DAG that has already written files.

Each step's command is then authorised by its own adapter's
`command_authorization` capability, which is the behaviour you want: cardiacCore's
utilities are authorised by cardiacCore and by nothing else.

### Core change 2 — the normalizer resolves per adapter

Both single-context bindings in normalization get the same treatment.
`_utility_produces_by_command` builds its map per adapter and merges by command
name, so a mixed DAG resolves every step's `produces` from the manifest that
actually declares it. A command claimed by two adapters is an error, not a
silent last-wins — the same shape as `plugin_discovery`'s refusal to guess
between contested names.

Unclaimed-artifact credit resolves a step's producer status against **that
step's** adapter, so a cardiacCore step is judged by cardiacCore's
`solver_commands()`. An artifact left unclaimed across a mixed DAG has no
single defensible owner, so it is a planning error rather than a guess — the
existing last-producer-wins rule is only safe within one adapter.

### Core change 3 — `consumes` refers to artifacts by id

A `consumes` entry resolves as an artifact id first, through the declared
artifacts, and is fingerprinted at the path the declaration gives.

This must preserve a distinction that is two different facts, not two versions
of one. cardiacCore's real steps consume `system/setCardiacConductivityDict`,
`0/fiber`, `0/sheet` — none of which any step produces. They were in the case
before the run began. So a `consumes` entry is either:

- **a produced artifact** — an id some step in this run claims via `produces`.
  Core can verify the producing step ran and succeeded, making the edge real.
- **a case input** — a path that simply exists, fingerprinted as today, and
  modelled by `provenance_inputs.ResolvedInput`, which already distinguishes
  `required` from optional and already emits an explicit `unavailable`
  component when a required input does not resolve.

The payoff is the verification that motivates the whole design: when cardiacFOAM
consumes `purkinje_graph_dict`, core can establish that the cardiacCore step
declaring it ran **in this run**, rather than finding a file and calling the
contract satisfied.

An entry that is neither a known artifact id nor an existing path is a planning
error. Ambiguity between an id and a path that happen to coincide is resolved in
favour of the id, and the collision is reported.

### Core change 4 — a path component may name the config entry that determines it

The Purkinje graph is the worked example, and it is also the artifact that
crosses the seam, so the problem lands exactly where the two adapters meet.
Three places state where that file lives:

| statement | says |
|---|---|
| `1DgraphToFoam`'s `-name` flag | "Name of the graph object written under `constant/` (default: `purkinjeGraph`)" |
| its manifest's `[[produces]]` | `path_pattern = "constant/purkinjeGraph"` |
| `…purkinjeGraphModelCoeffs.graphFile` | `required=True`, "Basename of the solver-facing graph dictionary in `constant/`. The value may name any graph dictionary produced by upstream preprocessing and may vary between study cases." |

The dict entry is the authority: it is what `conductionSystemDomain.C` reads.
The manifest restates its *default*, and is wrong as soon as anyone uses the
freedom the entry's own description grants. The flag is the writer's side of the
same fact.

A `path_pattern` may therefore reference a configured value instead of copying
it:

```toml
path_pattern = "constant/{config:$ELECTRO_MODEL_COEFFS.conductionNetworkDomains.<name>.purkinjeGraphModelCoeffs.graphFile}"
```

Core resolves it through the adapter's existing `get_config_value_reader`
capability, so core reads a value without learning what `graphFile` means. The
dict entry becomes the single truth; the artifact is found wherever the case
actually puts it; and the step's `-name` argument can be built from the same
value rather than being a fourth statement of it.

Unresolvable references are the missing-artifact case, not a crash: if the entry
is absent the artifact's location is unknown, and that is reported with the
reason, per the decision below.

## Adapter uniformity

The two adapters reach the same core types by different routes. Some of that is
harmless; some of it is a defect. The generic shape is core's, and both adapters
should present the same face to it.

### Divergence 1 — placeholder vocabulary (a live defect)

`DataArtifact.path_pattern` documents exactly two placeholders, `{case_id}` and
`{time}`, and says "anything else is a literal path component". Core expands and
matches them in `workflow_runner._artifact_snapshot`:

```python
expanded = artifact.path_pattern.format(case_id=case_root.name, time="*")
patterns = [str(case_root / expanded)]
... glob.glob(pattern)
```

Three conventions are in use for this one field:

| source | example | behaviour |
|---|---|---|
| core's model | `{time}/Scar` | substituted, then globbed — works |
| cardiacFOAM | `0/*` | no placeholder; works because core globs |
| cardiacCore | `<current-time>/Scar`, `<output-vtk>`, `<current-time>/<vtk-cell-data-name>` | `.format()` leaves it alone; `<` and `>` are not glob metacharacters, so it matches only a directory literally named `<current-time>` — **never matches** |

cardiacCore's angle-bracket patterns are prose where core expects a placeholder.
They do not raise; they silently match nothing, so `_artifact_snapshot` returns
an empty snapshot and step attribution for those artifacts is vacuous. This
affects precisely the artifacts whose location varies, which are the ones worth
attributing.

**Corrected 2026-09-18.** An earlier draft of this section called every
angle-bracket pattern the same defect and prescribed rewriting them all to
`{time}`. That was wrong, and the distinction matters:

- `<current-time>/Scar` means `{time}` written as prose. A genuine defect —
  rewrite it.
- `<output-vtk>`, described as "the caller-selected output path", is not that
  kind of thing at all. Its value is determined by an argument, and no
  substitution of `{time}` or `{case_id}` could ever produce it.

Note also that `<name>` inside a `DictEntry.driver_path` is a legitimate,
established convention — `dynamic_path=True`, marking a block name the user
chooses. Angle brackets are not inherently wrong in this repository; they are
wrong in a `path_pattern`, where core substitutes braces and then globs.

**Resolution.** `{case_id}` and `{time}` stay as the only *substitution*
placeholders and cardiacCore's `<current-time>` uses are rewritten. Patterns
whose value comes from configuration are handled by core change 4 below, not by
rewriting. A guard at manifest load rejects any `path_pattern` containing a
`<...>` group or a `{...}` naming anything other than a known placeholder or a
`config:` reference, so the next one fails loudly instead of silently. A literal
brace would make `.format()` raise, which is a second reason the guard belongs at
load rather than at execution.

### Divergence 2 — authoring medium

cardiacFOAM declares utilities as TOML data (`utilities/<name>/utility.manifest.toml`);
cardiacCore declares them as Python building `UtilityManifest` objects. Both
produce the same type, so core is indifferent, and this is **not** a defect.

It is worth recording why they differ before anyone "fixes" it: cardiacFOAM's
manifests sit beside the utility sources they describe and are checked against
them, whereas cardiacCore's are declared from a native wrapper and its
documentation, which is a different provenance with a different drift risk.
Unifying the medium without preserving that difference would lose information.
What should be unified is the *shape* — every field core reads, populated by
both — not the file format.

### Divergence 3 — module naming

cardiacCore has `workflows/`, cardiacFOAM has `tutorials/`; both return core's
`TutorialSpec`. cardiacCore has `operations/` and `catalogs/` packages where
cardiacFOAM has flat modules. This is cosmetic today and becomes real when a
single DAG spans both and a reader has to find "the thing that declares the
steps" twice, in two places, under two names. Renaming is out of scope here and
should be its own change; this spec only records that the names differ and that
`TutorialSpec` is the shared type underneath.

### What uniformity means, concretely

Not "identical code". Both adapters must:

1. declare every artifact they write, once, as a `ProducesEntry` with a
   `path_pattern` in core's placeholder vocabulary;
2. leave step-level `produces` to the manifest fill-in rather than restating it;
3. name consumed *artifacts* by id and consumed *case inputs* by path;
4. answer the same core capability surface, so a step is servable by either.

## Invariants and their guards

| invariant | guarded by |
|---|---|
| core never maps an adapter key to a package | a test that a DAG naming an unsupplied adapter fails readiness, with no import attempted |
| a step naming an unknown adapter never executes | `LaunchReadiness` test: `structural_ok` false, nothing written |
| one command is claimed by at most one adapter | a test over the merged utility map, mirroring `plugin_discovery`'s contested-name refusal |
| an artifact is credited to a step of the adapter that wrote it | a two-plugin test where an unclaimed artifact must not be absorbed by the other adapter's terminal producer |
| a consumer transitively depends on its producer | a planning test: a DAG consuming an id produced by a step it does not depend on is a diagnostic, not a run |
| a missing non-optional artifact reports why | a test asserting the failure names the declaring step, its adapter, the pattern, and whether the producer ran |
| a consumed artifact id was produced in this run | a test with two neutral plugins where the producing step is skipped, asserting the consumer is refused |
| every `path_pattern` uses only known placeholders or a `config:` reference | a manifest-load guard, run over both adapters' catalogs |
| a configured path is read from the entry, not a copied default | a test that changing `graphFile` moves where the artifact is looked for |
| core declares no cardiac vocabulary | existing `test_core_declares_no_phase_vocabulary`, unchanged |

Tests use two throwaway plugins from `packages/omnidriver/tests/plugins/`, not
the cardiac adapters — the generic semantics must be demonstrated without either
of them, per the responsibility split. The cardiac case is then a declaration
that uses the mechanism, tested in its own package.

## Non-goals

- **Who decides what to change next.** Whether the outer loop is driven by an
  optimizer, an agent or a person is deliberately out of scope. This spec makes
  the loop's *body* expressible and verifiable; `runtime/repair_loop` already
  exists for binding a hypothesis to the evidence that motivated it, and
  `core/experiments` already states the boundary — core records a checker's
  status and metrics and never decides scientific acceptability.
- **Direct communication between adapters.** They do not talk. They are steps in
  one DAG that exchange declared artifacts. `scripts/check-import-boundaries.py`
  forbids the import, and nothing here needs it.
- **Renaming `workflows/` and `tutorials/`.** Recorded above, not done here.

## Decisions

**A missing artifact must say why it is missing.** Decided 2026-09-18. The
question was whether a step that did not produce what it declared should fail or
merely record the discrepancy. Both, and neither alone: knowing an artifact is
absent is worthless without knowing *why*, because the reason is the whole point
of running the comparison. A non-optional declared artifact that does not appear
fails the step, and the failure carries the attributable facts — which step and
which adapter declared it, the `path_pattern` the declaration gave, what was
found at that location, and whether the producing step ran at all. An absence
reported as a bare boolean throws away the evidence that was the reason to look.

This is the same principle as the coverage-as-evidence amendments: a check that
did not run must say so, and say why, rather than being scored as though it had.
An artifact that did not appear is that principle applied to outputs.

**The DAG is the CLI surface.** Decided 2026-09-18. No new syntax. The steps
already name their adapters, so the DAG *is* the request; the CLI resolves each
adapter named in it through the same installed-plugin mechanism `--plugin`
already uses, and refuses with the missing name if one is not installed.

This keeps §12 intact. Resolution happens at the CLI — a public edge, where "no
plugin supplied" legitimately means "find the installed one" — and core still
receives a mapping it was handed. Core does not gain a lookup; the CLI already
has one.

**`depends_on` is checked against the artifact graph, not replaced by it.**
Decided 2026-09-18. See below.

## What `depends_on` does, and why `consumes` is not a substitute

`depends_on` is the only thing that sequences execution.
`workflow_runner._next_runnable_step_id` scans steps in declaration order and
returns the first `pending` step whose every dependency is in
`completed_steps`; `initial_workflow_state` starts the run at the first step
with no dependencies. `normalize_workflow_dag` rejects a dependency on an
unknown step and rejects cycles. Execution is serial: one `current_step_id` at a
time, so the DAG is declared as a graph and executed as a topological sequence.

`consumes` and `produces` affect **none** of that. They drive provenance and
artifact attribution only. So the two keys are not redundant today — they are
disconnected, which is worse. In cardiacCore's real preprocessing DAG,
`purkinje_slab` consumes `0/Conductivity`, which the `conductivity` step writes,
and the ordering happens to hold only through the chain
`purkinje_slab → anatomy → conductivity`. Nothing checks that those two facts
agree. Drop or reorder a `depends_on` and the `consumes` list stays perfectly
truthful while the step now runs before its input exists.

Once `consumes` refers to artifacts by id (core change 3), the artifact graph
states the real dependency: a step consuming an id that another step produces
must run after it. The choice is to derive `depends_on` from that graph or to
keep it and check it. **Check it.** Deriving would make ordering implicit and
silently change existing DAGs, and it cannot express the orderings that are not
artifact-mediated — a step that must follow another for a reason no file records.
Checking adds no key, removes no expressiveness, and turns a silent
misordering into a planning error: if a step consumes an artifact another step
produces and does not transitively depend on it, that is a diagnostic, reported
before execution.

That is the relation between existing keys, modelled — rather than a third key
restating what two already imply.

## Remaining open question

**Parallel execution.** Derived or checked, the artifact graph would make safe
fan-out computable: independent branches could run concurrently. Execution is
serial today and this spec does not change that. Worth noting only so that the
checking rule above is not written in a way that assumes a single running step.

## Sequence

Changes 1 and 2 are prerequisites for anything cross-adapter and land together
with neutral tests. Change 3 is what makes the seam verifiable rather than
merely expressible.

Change 4 is independent of all three and should land **first**. It is the
smallest, it fixes a live defect in cardiacCore's artifact attribution whether
or not cross-adapter execution is ever built, and it is the one that removes a
duplicated truth about the seam artifact itself — so every later change is built
on a `path_pattern` that is right rather than one that happens to match the
default. The `<current-time>` rewrite rides along with it.
