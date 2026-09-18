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

**Resolution.** One vocabulary: `{case_id}` and `{time}`. cardiacCore's patterns
are rewritten. A guard rejects any `path_pattern` containing `<...>`, or a
`{...}` naming anything other than the two known placeholders, at manifest load
— so the next one fails loudly instead of silently. Note that a literal brace in
a pattern would make `.format()` raise, which is a second reason the guard
belongs at load time rather than at execution.

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
| a consumed artifact id was produced in this run | a test with two neutral plugins where the producing step is skipped, asserting the consumer is refused |
| every `path_pattern` uses only `{case_id}`/`{time}` | a manifest-load guard, run over both adapters' catalogs |
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

## Open questions

1. **Strict or evidential `produces`.** Should a step that did not produce what
   it declared fail, or should the discrepancy be recorded the way checker
   results are? `core/experiments`' boundary suggests recording; `LaunchReadiness`
   suggests failing. Likely answer: fail for a non-optional artifact, record for
   an optional one — but this should be decided against the coverage-as-evidence
   amendments, which cover the same question for checks.
2. **Where the merged `driver_contexts` mapping is built.** The CLI is the
   obvious place, since it already resolves `--plugin`. A DAG spanning two
   adapters implies something like repeated `--plugin`, and that surface needs
   designing.
3. **Whether `depends_on` should be derivable.** If B consumes an id that A
   produces, the edge is implied. Deriving it removes a second hand-maintained
   truth; keeping it and *checking* it against the artifact graph is the more
   conservative option and probably the right first step.

## Sequence

1 and 2 are prerequisites for anything cross-adapter and land together with
neutral tests. 3 is what makes the seam verifiable rather than merely
expressible. The placeholder repair is independent of all three and can land
first — it fixes a live defect in cardiacCore's artifact attribution regardless
of whether cross-adapter execution is ever built.
