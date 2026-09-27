# Adversarial review of the solver-descriptions design

Reviewed commit `1205dc8`, including the complete design, current implementation,
and the cited local solver-learning evidence. This is a design review, not an
implementation approval. No solver runs or full test suites were performed.
One isolated Python reproduction exercised the current argument-merging API.
Slurm's official documentation was checked for allocation/step semantics.

**Recommendation: revise before implementing the ten-step migration.** Keep
the record loader, existing execution objects, format codecs, unit-bearing
axes, and evidence-backed solver bindings. Separate the adapter migration,
resource policy, scientific comparison contract, and benchmark revision.
The current draft understates changes to existing contracts and overstates
what its quantity maps can establish.

## Findings, in priority order

### 1. [P1] The proposed openCARP axes conflict with the existing resolver

Spec §2.4, lines 533–555, introduces independent `tend`, `dt`, and
`massLumping` axes targeting `solve`. §4.1 treats the underlying record
machinery as essentially unchanged.

`core/tutorial_records.py:1096` explicitly refuses different argument
contributions from two axes to the same step. I reproduced this using a
`TutorialRecord`, two `DefaultArgument`s, and two `AxisContract`s:

```text
TutorialRecordError: step 'solve' receives conflicting command arguments
from axis 'dt' (['-dt', '10']) and axis 'tend' (['-tend', '100'])
```

Consequently a study varying timestep while setting duration cannot use the
proposed record. This is a contract change, not just TOML loading.

**Required revision:** give declarative argument replacements a structured
identity such as `(step, default-argument key)`. Merge disjoint replacements;
reject different values for the same key; preserve deterministic argv order.
Keep arbitrary Python argument lists conservative rather than guessing their
flag grammar. Test multiple axes together, including aliases targeting the
same setting and interaction with command-line ownership.

### 2. [P1] Quantity bindings have the wrong scope and no complete effective-value contract

Spec §3.4 puts `nversion.par`, `imp_region[0]`, `gregion[0]`, `stim[0]`, and
`lats[0]` in a solver-wide map. The cardiacFOAM map assumes
`constant/electroProperties` even though §5 documents region-local paths.
Both maps assume a record has `dx`, although records have different axes.

These are bindings for particular records and configurations, not universal
facts about the solver. A second openCARP record or an electromechanical case
will make this distinction unavoidable.

Moreover, §3.4 reads case keys, while openCARP's effective values also depend
on ordered command arguments and binary defaults. The existing config reader
in `opencarp/plugin.py` returns `None` for an absent assignment; it does not
resolve catalog defaults. The example relies on the default
`bidm_eqv_mono = 1`, without specifying that resolution. Reading a stale file
value overridden by argv is worse: the report can describe a different run.

**Required revision:** retain shared quantity definitions, but bind them per
record, with explicit applicability to model, region, stimulus, and output.
For the first release, explicitly support one region and one stimulus and
report other configurations as unsupported. Do not implement a general
selector language yet. Resolve values from the final plan through solver
Python where necessary. Report requested value, effective value, unit,
source, applicability, and unknown status. Bind compiled defaults to the
verified binary version. Missing or unverified is not equivalent to matching.

### 3. [P1] “Problem identity” promises more than the report verifies

Spec §3.4, lines 1211–1221, calls its mapped-value comparison an automation
of §S. But `docs/solver-learning/cardiacfoam.md` §S also records initial
state, numerical schemes, stimulus-volume discretization, stimulus endpoint
inclusion, and frame differences. Several are absent from the maps. The
initial-state reader is explicitly deferred. Equal conductivity components
also do not establish equal spatial tensors without the case frame.

A changed stimulus box can leave every mapped scalar unchanged. So can a
different activation-event convention. A table of matching scalar values
must not become evidence that the cases represent the same problem.

**Required revision:** call the initial feature a *mapped-parameter report*.
Let each benchmark declare its required comparison fields, tolerances, and
accepted differences. Distinguish physical model, numerical method, initial
and boundary conditions, stimulus protocol, and measurement definition.
Uncovered required fields must leave compatibility unresolved. The pairing
file may remain separate, but its frame and sampling assumptions must be
included in the comparison evidence.

The owner has already accepted TNNP 2004 and −84 mV; the latest request and
the solver-learning log settle D16. Preserve both and record the accepted
differences. Do not reopen the choice or relabel them as model equivalence.

There is also a numerical error in the claimed tolerance: 49,994 versus
50,000 differs by **0.012%**, exceeding the stated 0.01%. Correct the status
or explicitly decide a tolerance before treating it as a match.

### 4. [P1] Quantity plus format does not uniquely identify an output

Spec §3.4 replaces positional artifact ids with `activation_time` plus a
format; S8 then gives both point and diagonal outputs the `openfoam_probes`
format. The two artifacts will share quantity, format, and field. No unique
selection rule is specified.

The diagonal migration is also incomplete. The current
`ActivationProbeReader` requires sibling `Cx`, `Cy`, and `Cz` probe files
to report actual sample locations. `niederer_2011.py` produces these for
`samplePoints`, not `sampleLines`. Merely declaring the diagonal file's
format will make the moved reader attempt to open missing companions.

**Required revision:** give outputs stable semantic names scoped to the
record, such as `activation.points` and `activation.diagonal`, and bind each
to its producer, path, field, quantity, and sampling metadata. Quantity-only
selection is acceptable only when it resolves uniquely. Add diagonal centre
sampling or an independently validated reader with equivalent location
evidence. Verify the complete read and comparison, not only registration.

### 5. [P1] Scheduler allocation is not universally the solver rank count

Spec §2.3.1 requires equality between case decomposition, request, and
`SLURM_NTASKS`. Equality between decomposition and launched solver ranks is
appropriate. Equality with the enclosing allocation is a restrictive policy,
not a universal MPI invariant.

Slurm explicitly distinguishes allocation from job steps. Its
[sbatch documentation](https://slurm.schedmd.com/sbatch.html) describes
`--ntasks` as provisioning for a maximum task count in steps, while
[srun](https://slurm.schedmd.com/srun.html) supports task requests for individual
steps. A run using 8 ranks within a suitable 32-task allocation should not be
rejected solely because those numbers differ. The restriction also impedes
strong-scaling sweeps and the design's own two-rank launcher probe.

**Required revision:** distinguish requested ranks, case-required ranks,
actual launch ranks, and available resources. Keep the current full-allocation
policy if that is the supported first mode, but label it explicitly. Do not
merely replace equality with `<=`: threads, task placement, and concurrent
steps also affect resource use. Allow a supplied, recorded site launcher
configuration to own those details without adding a scheduler submission
framework. Bind launcher verification to the solver/MPI/site environment,
not a universal `srun` name.

### 6. [P1] The identity guarantee needs explicit hashes for description resources

Spec §2.2 says the stack digest stays untouched; §7.1 relies on identity
changes to prevent reuse. The current provider digest includes profile,
dictionary entries, and manifest. `provider_stack.py` hashes content for only
three capabilities. `provider_identity.py` explicitly documents that changes
inside other capabilities without a version bump can remain invisible.

A file glob such as `records/*.toml` is not the content of those files.
The specification mentions hashing the vocabulary, but does not establish
coverage for records, quantity maps, output semantics, or interpretation
rules. A workflow digest can detect argv changes; it cannot cover a changed
unit or model mapping that leaves argv unchanged.

**Required revision:** define an aggregate content identity for descriptions,
records, maps, vocabulary, and interpretation/schema version. State how
referenced Python implementations are versioned. Tests must mutate each
semantic resource without a package-version bump and show which plan/run/
compare/resume checks refuse reuse. Specify comment-only behavior separately.
This is a missing guarantee, not a claim that every present resume path fails.

### 7. [P2] Identity quantities cannot be requested as the example claims

Spec §3.4, lines 1204–1205, recognizes quantity study keys by a dot and no
colon, then lines 1230–1233 promises an `ionic_model` request. That identifier
contains no dot. Its mapping is also under `read`, with no input binding.
Further, two cardiacFOAM names map to the same published model identity,
so reversing a read mapping would not select a unique implementation.

**Required revision:** use explicit quantity registration or an explicit
quantity namespace, not punctuation as authority. Separate read and write
support. Require an unambiguous input binding and refuse unsupported writes
by name. Keep published model identity distinct from implementation/backend
selection. Test a valid identity write, an unsupported identity, and an
ambiguous reverse mapping. The first release may reasonably be read-only.

### 8. [P2] The anti-growth guards reward moving complexity, not removing it

Spec §0 counts the toy as a second implementer and exempts binary facts from
the two-implementer rule. Guard A then says a toy needing Python proves a
missing interpreter table. Guard B exempts entire modules labelled codec,
reader, rule, or derived, provided they are reachable.

This can justify a new generic feature by teaching it to a toy, or satisfy
the budget by moving more logic into an exempt module. Conversely it can
block a legitimate adapter fix because a counted hook gained a few lines.
It does not prove less complexity or easier solver onboarding.

**Required revision:** retain the toy as a portability/conformance fixture,
not evidence of real demand. Keep Python line counts as review information,
not a monotonic correctness gate. Judge core additions by real solver cases,
contract clarity, and total maintenance burden. A binary fact can remain in
adapter Python. Hooks should be explicit, typed, and tested; they need not
shrink every time the supported solver behavior grows.

### 9. [P2] Two logged runs cannot decide whether numerical options matter generally

D3 and §4.5 propose retaining carputils solver options only if two runs
differ beyond tolerance. One agreeing pair does not establish equivalent
convergence, performance, or failure behavior at other resolutions, rank
counts, or problem types.

**Required revision:** first decide what this record promises to reproduce.
If it reproduces the native `run.py` workflow, preserve its effective options
and supplied option-file contents, unless a departure is explicitly recorded.
If it intentionally uses binary defaults, name that execution policy. Use
logged comparisons to validate the chosen scope, recording convergence,
iterations and timing as well as final quantities. Do not infer universal
irrelevance from matching output on two examples.

### 10. [P2] Serial TL-EM requires a record contract extension

Spec §5 says `cwd` is one field in `record_description.py` and nothing in
core changes. The workflow DAG supports `cwd`, but `WorkflowStep` currently
has no such field, and `_workflow_dag_for_record` does not carry it through.
A loader that constructs the existing dataclass cannot express `cwd = 'src'`.

**Required revision:** add and validate `cwd` on the record object and preserve
it into the DAG. Define whether consumed and produced paths remain
case-relative, and test script resolution and output location from the build
directory. Keep native validation before claiming the serial TL-EM example
works. This is a small change, but it contradicts the reuse claim and must be
budgeted.

## What is worth building

1. **A record loader into the existing runtime.** TOML is a reasonable authoring
   format. Retain Python for codecs, derived values and conditional solver
   behavior. Do not force a new table for every Python callback.
2. **Inspectable effective plans.** A user needs to see selected route,
   effective parameter values, argv, working directory, environment identity,
   resources, and expected outputs before committing expensive compute.
3. **Units and explicit bindings.** Unit-bearing axes solve a demonstrated
   problem. Shared quantity names are valuable when their case scope and
   read/write contracts are honest.
4. **Stable output names and interpretation provenance.** A successful process
   exit, a readable artifact, a numerically acceptable result, and a scientifically
   comparable result are different claims. Keep them distinguishable.
5. **Representative adapter tests.** Existing conformance is valuable but cannot
   establish facts it never exercises. Retain native configuration-specific
   regressions when replacing common Python machinery with templates.

Do not make solver users wait for the entire science package to gain TOML
records. Do not make the cluster campaign depend on retiring factories,
moving every catalog, reorganizing prose, or meeting Python line budgets.

A shared electrophysiology package is a defensible home for shared semantics.
Start with evidence-backed identities, dimensions, and scoped read bindings.
Delay automatic cross-solver writes, relation inference beyond verified cases,
and moving S1–S2 arithmetic until their independent value is demonstrated.
Generic electrical units are not cardiac vocabulary: core's hard time/length
boundary is an architectural policy, not a scientific necessity. Extension
registries should at least reject conflicting unit definitions and remain
scoped to the active context.

## Decisions D1–D16

| Decision | Review recommendation |
|---|---|
| D1 | **Yes to TOML/JSON.** Correct the rationale: TOML has typed literals; quoted solver tokens preserve their spelling. The YAML issue describes the current YAML 1.1 loader, not every YAML implementation. Prefer consistency and the existing dependency footprint over a blanket YAML objection. |
| D2 | **Yes**, if the record promises native-driver defaults. Fix independent argument replacement first. Record this as a behavior change separate from format migration. |
| D3 | **Revise.** Preserve the declared execution policy; two agreeing runs are not grounds for dropping numerical options. |
| D4 | **Yes to retiring an unusable path**, after checking references and preserving a useful unsupported-entry diagnostic. Do not present retirement as restored TL-EM support. |
| D5 | **Defer arbitrary study DAG injection.** Keep a documented way to supply prepared cases/inputs. Revisit with a concrete workflow that current records cannot express. |
| D6 | **Yes to units now; conditional on quantity writes.** Resolve scope, effective values, alias conflicts, and read/write support first. |
| D7 | **Yes to a small shared package; no to making all of §3 a migration prerequisite.** |
| D8 | **Keep `variant_constraints`.** The bidomain counterexample defeats blanket rejection of contributions to inactive steps. Separately diagnose an axis whose entire contribution is inactive. |
| D9 | **Allow vocabulary extensions; reconsider the absolute core restriction.** Units are generic; quantities and model identities are domain-specific. |
| D10 | **Yes**, with named point/diagonal outputs, actual sampling locations, declared comparison method, and the missing centre-sampling step. |
| D11 | **No as an automatic dependency.** Freeze and pin the current campaign. Publish a separately versioned request/campaign revision after migration equivalence is demonstrated; retain existing results and their original interpretation. |
| D12 | **Accept for these records.** Declare the concrete copy operations in the record. The ownership of general-purpose `cp` is not the important design issue. Test restaging/retry behavior of region-mesh copies. |
| D13 | **Yes, with accessible evidence.** Facts required to operate a packaged adapter must remain available from the installed artifact or stable references, not only a checkout's history. |
| D14 | **Low priority; decide from actual consumers.** Moving a command declaration changes its authorization scope even if current cardiac records still work. Avoid claiming it has no behavior effect. |
| D15 | **Yes to hooks; no to the shrinking-line-count gate.** Require explicit ownership, signatures, deterministic planning behavior, and conformance tests. |
| D16 | **Closed by the owner: keep TNNP 2004 and −84 mV.** Preserve their provenance and accepted differences. |

## A smaller implementation sequence

1. Specify and fix independent argument replacement and record `cwd`.
2. Load one openCARP record from TOML without changing defaults or scientific
   interpretation. Compare resolved plans, staged files, and native outputs.
3. Migrate a genuinely different cardiacFOAM record with routes and derived
   axes. Let those two real integrations determine the needed interpreter.
4. Add axis units, stable output names, aggregate description identities, and
   effective-value reporting. Keep behavior corrections as separate changes.
5. Implement a scoped Niederer mapped-parameter report and benchmark-owned
   compatibility criteria. Only then generalize shared science rules.
6. Validate the intended cluster resource policy and launch environment.
   Revise the campaign independently, preserving prior requests and results.

Before approving the design, require examples covering simultaneous `dt` and
`tend`; two records with different bindings; command-line overrides and absent
defaults; two artifacts with the same quantity/format; changed semantic TOML
without a version bump; incomplete scientific comparison; a selected rank
count inside a larger allocation or an explicit restriction; and a case-local
build with `cwd`. These examples test the promises that the current toy and
line-count gates do not establish.
