# Coverage is evidence: one vocabulary for what a check actually proves

> **SUPERSEDED 2026-09-18 by `2026-09-18-coverage-as-evidence.md`.**
> Read this for its reasoning, not as the specification. Nine of its positions
> were amended by `2026-09-18-coverage-as-evidence-review.md` and the
> consolidation records each change with its reason. In particular: §2's
> corollary, §4.1's scoring formula, §4.5.3's `native_owned` outcome and
> §4.5.4's numeric-literal lint are **not** the current design. Its cardiaccore
> census in §4.5.2 is stale. Do not implement from this file.

Design, 2026-09-18. Status: superseded; retained for reasoning.

Supersedes nothing. Amends no contract. It names an invariant this repository
already states in prose fifteen times, implements correctly in two subsystems,
and violates in the three places that decide whether a run may start.

## 1. The finding

This repository is **honest per item and dishonest in aggregate.**

Per item, the evidence discipline is real and unusual. `ProvenanceComponent`
carries `strength` and its docstring says why: it "is honest about how much the
fingerprint actually proves". `ComparisonOutcome` bounds itself and says so:
"Core exposes a bounded summary only". `BUILDER_AGENT_EVIDENCE_CONTRACT.md`
gives a five-rung evidence ladder with a per-channel limit, and the rule that
"Unavailable evidence is explicit ... It must not silently become a default."

In aggregate, three separate mechanisms treat *absence of data* as *evidence of
success*:

| Aggregate | Computation | What a check that did not run contributes |
|---|---|---|
| `readiness_score` | `sum(item.points)` over seven weighted stages | **full points, status `passed`** |
| `ProvenanceSnapshot.is_complete` | `all(strength in {"content","absence"})` | nothing — a root never walked cannot lower it |
| catalogue `source_refs` | one drift guard, `skipif(monorepo_root is None)` | a green CI line |

These are the same defect. Each aggregates only over what it *did* examine, and
none records what it *declined* to examine. An empty result set is
indistinguishable from a clean one.

### 1.1 The readiness score, specifically

`_score_from_diagnostics` branches on error and on warning, then falls through
unguarded to `status="passed", points=max_points`. Every skip path in the
codebase returns an empty diagnostic tuple, which lands on that fallthrough.
Four of the seven stages have a vacuous-pass trigger:

| Stage | Weight | Trigger |
|---|---|---|
| `case_preparation_files` | 15 | a generic case returns before any file is stat'd; `required_files=()` also earns full points |
| `dictionary_resolution` | 20 | both validators bypassed for a generic case |
| `environment_preflight` | 10 | `SKIP_ENV_DIAGNOSTICS` in the environment |
| `mesh_geometry` | 5 | `SKIP_MESH_DIAGNOSTICS`, a nondimensional entry, a generic case, or a plugin with no hook |

Fifty of one hundred weighted points are earnable by checks that never
executed, each reported with an affirmative summary. `mesh_geometry`'s reads
"Mesh-scale checks did not find run-preparation issues"; `environment_preflight`'s
asserts "The current environment satisfies the commands declared by the
workflow."

`is_launchable` inherits it: `environment_ok = not environment_errors`, and
`not ()` is `True`.

`docs/OMNIDRIVER_ROADMAP.md` already forbids this — "Missing or skipped checks
must never increase a readiness score or appear as proven compatibility." The
rule is stated and not implemented.

### 1.2 The guard that ratified

`test_strict_planning.py` asserts `readiness_score["score"] == 100` and
`status == "ready"` for a plan built with a nonexistent OpenFOAM bashrc, under
a conftest that sets `SKIP_ENV_DIAGNOSTICS` suite-wide. Per CLAUDE.md's rule
about never weakening a guard: this guard did not fail, it **ratified**. Fixing
the cause requires changing this expectation, and that is the intended
direction, not a weakening.

## 2. The invariant

> **An aggregate may not report success over checks it did not perform.
> Every aggregate carries its own coverage, and a check that could not run
> is a distinct outcome from a check that passed.**

Corollary, already true one layer down and to be made true everywhere:
*a check that cannot run fails.* A `--check` that returns 0 because its source
of truth is absent is worse than no gate, because a CI log reads it as
verification.

## 3. The vocabulary

It is not invented here. It exists twice, in two subsystems, and is absent from
the layer that gates launch.

```python
# core/experiments.py -- post-run comparison. Already correct.
_COMPARISON_STATUSES = frozenset(
    {"passed", "failed", "unavailable", "not_requested", "unknown"}
)
```

`experiments.py` is the model for this whole design: it is honest per item
*and* in aggregate, because `Experiment.to_json`'s summary block is
`_status_counts` over that vocabulary. It is the only place in the repository
where both levels are honest. Copy it.

Proposed shared vocabulary, in `core/planning_types.py`:

```python
COVERAGE_OUTCOMES = frozenset(
    {"passed", "failed", "warning", "unavailable", "not_applicable", "not_requested"}
)
```

- `unavailable` -- the check applies and could not run (tool missing, source
  root absent, capability not installed). **Never scores points.**
- `not_applicable` -- the check does not apply to this case, by a declared
  reason. Leaves the denominator, does not enter the numerator.
- `not_requested` -- deliberately suppressed by an operator flag.

### 3.1 Two axes, not two competing vocabularies

`COVERAGE_OUTCOMES` and the `evidence_status` of section 4.3 are orthogonal and
must not be merged.

- **Coverage** answers *did this check run?* It is a property of an act of
  verification, computed at plan time, and it decays: a stage covered yesterday
  is uncovered today if its tool disappeared.
- **Evidence status** answers *how strong is this claim?* It is a property of a
  declared fact, authored by a builder, and it is stable until the fact is
  re-derived.

A `DictEntry` with `evidence_status="supported"` can still sit in a stage whose
coverage is `unavailable` -- a well-evidenced fact that nothing checked on this
run. Collapsing the two would make that state unrepresentable, which is the
error this design exists to remove.

The distinction between `unavailable` and `not_applicable` is the one that
matters within coverage: a generic case genuinely has no plugin configuration to parse, and
that is `not_applicable`; `SKIP_ENV_DIAGNOSTICS` is `not_requested`; a missing
C++ source root is `unavailable`. Today all three are `passed`.

## 4. Adoption, layer by layer

### 4.1 Readiness (`SimulationAuditItem`, `strict_audit`)

`status` becomes a member of `COVERAGE_OUTCOMES`. `_score_from_diagnostics`
gains a required `outcome` argument -- it may no longer infer success from an
empty tuple, which is the entire defect.

`readiness_score` stops being a bare sum. It reports three numbers:

```
earned / eligible          points over stages that actually ran
eligible / total           coverage
uncovered: [stage, ...]    named, with each one's outcome and reason
```

A plan with fifty uncovered points reports 50% coverage, not 100% ready. The
percentage that exists today is retained but computed over `eligible`, so it
can no longer be inflated by suppression.

`is_launchable` gains coverage as an input. Policy (deliberate, and the one
place an operator can override): `unavailable` on a stage blocks launch;
`not_requested` does not block but is reported in `launch`; `not_applicable`
is silent. This preserves today's ability to run with diagnostics suppressed
while making the suppression visible in the record.

`StrictDiagnostic.level` gains no new values. Coverage is a property of the
*stage*, not of a diagnostic; a stage that did not run has no diagnostics to
level.

### 4.2 Provenance (`ProvenanceSnapshot`)

The enumeration boundary is sound and is **not** widened. `enumerate_case_inputs`
is exhaustive within declared walk roots, with the correct safety property that
an unrecognised file inside a root becomes a `required_input` -- "This is the
safety property, not laziness."

What is missing is that the snapshot has no notion of what it declined to walk.
`is_complete` aggregates per-component read success only. Add:

```python
enumerated_roots: tuple[str, ...]      # what was walked
declared_unwalked: tuple[str, ...]     # CaseFileRule paths that yielded no root
```

`declared_unwalked` is not hypothetical: `_walk_files` returns `[]` for a
non-directory, and four of cardiacFoam's eleven declared rules are files.
`Allrun` and `Allclean` reach the snapshot only through step-executable
resolution; `README.md` and `runRegressionTest.sh` are declared and never
fingerprinted. Today that is invisible. It should be a recorded field, not a
discovery.

This changes `SCHEMA_VERSION`, which by existing convention encodes policy
rather than layout. Old snapshots remain readable for inspection and cannot
resume -- the established rule.

**Explicitly rejected: a whole-case-tree digest.** `CLEAN_INSTALL_ACCEPTANCE_2026-09-08.md`
rules that integration "must not copy or content-hash the whole historical
tutorial tree on every attempt" against a ~204 GiB checkout. Coverage is
declared and recorded, not bought by walking everything.

### 4.3 Catalogue facts (`DictEntry`)

Two fields, both defaulting to the weakest value so silence claims nothing:

```python
evidence_channel: str = "unknown"
# case_files | documentation | api_schema | source | execution | unknown
# The ladder of BUILDER_AGENT_EVIDENCE_CONTRACT.md, as a field.

evidence_status: str = "candidate"
# supported | observed | conditional | candidate | unknown | unsupported
# Governs what an agent may do with the entry, per that contract's own table.
```

Flat fields, not a nested object: `DictEntry` already carries five predicate
fields inline, the house style is flat frozen dataclasses, and a nested type
would need its own serializer in a codebase with ninety-six hand-written
`to_json` pairs.

One gate, modelled on `export-capability-seams.py` -- the only generate-and-verify
loop in this repository that closes. It is a **builder-suite** gate in the sense
of section 4.5: it runs when a native source root is supplied, reports
`unavailable` to a builder when one is not, and never contributes to a run's
readiness.

1. `evidence_channel="source"` requires at least one `source_refs` path that resolves.
2. **A check that cannot run fails.** Absent source root reports `unavailable`
   and exits non-zero.
3. `unit` may be declared only with channel `source` or `documentation` and a
   resolving `source_refs`. "Coordinate magnitudes do not establish units."
4. `enum_values` require a `source_refs` and are never machine-derived.

### 4.4 What may be mechanised from C++, and what may not

Measured over both native trees: a scanner reliably yields
`{key, C++ type, required|optional, literal default, file:line}` for roughly
80-85% of lookup sites. **Only required-versus-optional is adopted**, because
it is the one fact with a clean syntactic discriminator -- `get<T>` throws,
`getOrDefault<T>` carries its default inline, and no intermediate form exists
in either tree.

Not mechanised, by decision:

- **Dotted-path attribution.** Receivers are opaque. In `generatePurkinjeTree.C`
  sixteen lookups hang off a receiver bound to `subDict(ventKey)` where
  `ventKey` is a runtime parameter called twice. No textual analysis recovers
  that a key lives under both `lv` and `rv`.
- **Enumerations.** Of three `Enum<>` tables in cardiacCoreStandalone and five
  in noFrontendCardiacFoam, zero and one respectively describe a user
  dictionary key. Real enumerations take four shapes -- `if`/`else` chains
  ending in `FatalErrorInFunction`, chained ternaries, `List<word>` from a
  virtual override, and a registry across ~40 `defineTypeNameAndDebug` sites.
  None is self-labelling.
- **Units.** Sometimes bound at the lookup, usually not present at all.
- **Conditional requirements.** These are control flow. In
  `generatePurkinjeTree.C` the `extension` block is required only when
  `terminalModel == "transmural"`; a scanner sees five optional keys with
  defaults and is wrong in the direction that lets an invalid case plan.

This boundary is the point of the design. The 15% a scanner cannot see is
exactly the scientific content, and rules 3 and 4 stop it being guessed.

### 4.5 Two suites, two audiences

Added 2026-09-18, after two owner rulings: scientific logic is native-owned, and
developer/builder verification is a different product from case verification.

The second ruling is the load-bearing one. This repository has been treating one
test suite as if it had one audience. It has two, they anchor on different
things, and the same check is a gap for one and irrelevant to the other.

| | **builder suite** | **runner suite** |
|---|---|---|
| audience | someone onboarding a solver or editing a catalogue | someone running a case |
| anchors on | the native source tree | a real case and its regression reference |
| asks | does the declaration still match the tool? | does the helper come out green on real data? |
| native tree absent | `unavailable` -- a real gap | `not_applicable` -- not this audience's concern |
| runs | when a native source root is supplied | whenever a case exists |

The roles are already declared. `agent_guidance/manifest.yaml` binds `builder`
and `runner` to different `required_catalogs`, and `read_guidance` refuses an
unknown role rather than defaulting. The guidance layer has the split; the test
layer does not.

**Coverage is therefore reported per role.** A runner's readiness may not be
inflated or deflated by builder-suite gates, and a builder's onboarding report
may not be reassured by runner-suite greens. A single blended percentage is
uninterpretable, which is what the current `readiness_score` is.

#### 4.5.1 What each suite may assert

**Runner suite.** Its subject is the adapter's own operations, which are checks
and helpers. It runs them against a real case and asserts:

- the helper's own verdict -- a status, an empty or non-empty diagnostic set;
- a numeric value **only when the expected value is read at test time** from the
  case or its regression reference.

Forbidden: a numeric literal written into the test file as an expected physical
value. The quantity's origin stays native; Python may compare, never originate.

> **Python may verify a correspondence. It may not originate a quantity.**

**Builder suite.** Generic mechanisms over a supplied source root --
`strict_dict_key_report`, `source_refs` resolution, catalogue-versus-inventory
coverage. These assert nothing about physics; they assert that a declaration
still points at something real. They are development tooling, not case
verification, and must never contribute to a run's readiness.

**Removed from both.** Hand-written ties to a specific C++ symbol or file --
a test asserting the catalogue says "pig" because `Gaur_2021.H` says so, or
pinning one `addToRunTimeSelectionTable` registration. The generic builder-suite
mechanisms already cover that ground without hard-coding one symbol per test.

#### 4.5.2 Measured state, 2026-09-18

610 Python test functions across the two domain packages.

| | cardiaccore | cardiacfoam |
|---|---|---|
| structural / agnostic | 49 | ~482 |
| correspondence | 7 | ~63 |
| **originated quantity** | **6** | **3** |
| skipped in this checkout | 0 | ~83 |

Nine originated quantities is a fence to build, not a fire. Two distribution
findings matter more.

**Every cardiacfoam test whose anchor is an actual C++ file, native binary,
tutorial case, or committed reference is skipped here.** Nothing in CI verifies
any of it. Under the two-suite split most of these are builder-suite tests that
correctly report `unavailable` in a checkout with no native tree -- but today
they report nothing at all, and their silence is indistinguishable from success.

**cardiaccore inverts it.** No `conftest.py`, no `skipif` anywhere, all 62 tests
run -- and not one opens a C++ file. Its docstrings cite
`coordinatesConvention.H`, `generatePurkinjeTree.C`, and the commit `1ea6d23`;
none is read at test time. It has the appearance of correspondence with none of
the substance.

The tests that could verify correspondence do not run. The tests that run cannot
verify correspondence.

#### 4.5.3 Three states, one green

`pytest.skip` is the test-suite spelling of a `--check` that returns zero.

| State | Example | Outcome |
|---|---|---|
| Not answerable in Python, ever | numerical convergence, physiological validity | `native_owned` |
| Answerable, anchor absent, audience cares | builder gate with no source tree | `unavailable` |
| Answerable, anchor absent, audience does not care | same gate, runner asking | `not_applicable` |
| No anchor exists anywhere | an invented array asserted as anatomy | not a result at all |

`COVERAGE_OUTCOMES` gains a seventh member:

- `native_owned` -- real, load-bearing, not answerable in this process. It
  **leaves the denominator entirely** and prints on its own line, never summed
  with orchestration coverage. This inherits the evidence ladder's existing
  ceiling: its top rung is controlled execution, limited to "A successful run is
  not a general compatibility or scientific-validity claim." There is no sixth
  rung, deliberately, and no Python aggregate may imply one.

The report prints lines that are never added together:

```
runner coverage:    eligible / total
builder coverage:   eligible / total     (only when a source root is supplied)
native-owned:       [stage, ...]         named, never scored
```

`native_owned` does not block launch -- it is a permanent property, and blocking
on it would make every run unlaunchable. It prints every time, so that full
runner coverage cannot be read as scientific readiness.

#### 4.5.4 The origination lint

Mechanically checkable: **a numeric literal in a test assertion is a violation
unless its expected operand was read from a file during that test.**

Counts of catalogue entries are structural, not scientific, and are exempt --
though two disagree today and should be reconciled separately:
`test_generic_contract.py` asserts exactly 87 dictionary entries while
`test_dict_entries_catalog.py` asserts "> 80 # sanity: we have 87+ today", in
different packages.

The lint stops new originations. Existing ones are per-test scientific
judgements -- delete, re-anchor to a case-supplied value, or move native -- and
are listed in section 8 for the owner, not automated.

#### 4.5.5 Sequencing, which matters more than the rule

Removing the hand-written C++ ties before the cardiacCore regression exists and
runs would move this repository from dark verification to none. The regression
comes first; the deletions follow it. The practical loss is small either way --
`regenerate-ionic-catalog --check` is in no CI job and returns zero without its
source anyway -- but the order is not optional.

## 5. Pinning, and dirty trees

Neither native tree has a `VERSION` file or a reachable tag; `git describe`
fails on both. Both working trees are dirty, and one is on a feature branch.
A dirty tree here normally means work in flight, not noise -- so the content
verified against may be ahead of any commit and reproducible by no one else.

Therefore `verified_at` records the source SHA **and** a digest of the files
actually read, and a `dirty: bool`. A SHA alone would not identify what was
checked, and the gate's own record would become the next thing to drift.

The gate does not refuse to run on a dirty tree. Refusing would mean never
running.

## 6. Out of scope

- **Directory restructuring.** A `sim_engine` / `agent_layer` / `schemas` split
  was evaluated against the evidence of nine read-only surveys and rejected for
  four independent reasons, which is the strongest signal in that analysis.
  (1) There is no non-deterministic code in this repository -- no model call, no
  agent loop, no MCP server -- so `agent_layer/` would contain markdown. The
  agent boundary is already the JSON surface of the CLI, the narrowest part of
  the system. (2) The proposal is a horizontal cut by determinism; the existing
  split is vertical by domain, with the determinism boundary inside each
  package. They are different axes, so it was never A-or-B. (3) The horizontal
  seam the proposal wants already exists as the capability seam -- 24 Protocols,
  a generated table, a CI `--check` -- and is the healthiest part of the
  codebase. (4) Every defect found was in a *relation* or an *aggregate*, not in
  a package boundary; rearranging packages would have moved all of them
  untouched.

  `docs/OMNIDRIVER_ROADMAP.md` independently reaches the same conclusion from
  the other direction, describing "two logical layers with three ownership
  boundaries" and declining a "wholesale rewrite".
- **A regenerated `dict_entries.json`.** It existed at
  `cardiacCoreStandalone/agent/dict_entries.json` with very nearly the schema
  such a proposal would reach for, churned six times in thirty commits -- nearly
  as often as the source it described -- and was deleted deliberately when the
  agent-facing interface was handed to this repository. Rebuilding it is not a
  new idea; it is the idea that drifted.
- **Context hydration and bounded agent output.** `StrictPlanReport.to_json()`
  serializes all 22 fields unconditionally -- the full workflow DAG, the full
  workflow state including every step's args and diagnostics, the full nested
  run document, the full capability manifest -- and `AGENT_GUIDE.md` directs an
  agent to run `plan --strict` before every launch. There is no projection and
  no `--brief`. The principle is already stated twice in the codebase
  (`ComparisonOutcome`: "Core exposes a bounded summary only";
  `build_failure_context`: bounded "so a diverged run that produced a huge log
  cannot exhaust memory or context") and the one role-scoped hydration
  mechanism, `agent_guidance/` with its `required_catalogs` per role, exists in
  a single package and is used by nothing else. This is a different invariant
  -- bounded output -- with a different mechanism -- projection -- and belongs
  in its own design. Out of scope here, not out of mind.
- **Pydantic.** There are four parallel contract mechanisms already (frozen
  dataclasses with hand-written serializers, one JSON Schema, the `DictEntry`
  predicate engine, and YAML plugin profiles). The question worth asking is
  whether they converge, not whether to add a fifth.
- **Widening provenance enumeration.** See 4.2.
- **Any change to scientific method.** See 8.

## 7. Migration order

Each step is independently valuable and independently revertible.

1. **Make a check that cannot run fail.** One branch, several call sites. Kills
   the whole silent-pass class at its cheapest point.
2. **Coverage in the readiness path.** `COVERAGE_OUTCOMES`, the required
   `outcome` argument, the three-number score, coverage into `is_launchable`.
   Update the ratifying test to assert the new, honest number.
3. **Coverage fields on `ProvenanceSnapshot`**, with the `SCHEMA_VERSION` bump.
4. **`evidence_channel` / `evidence_status` on `DictEntry`**, defaulting weak,
   with no gate yet. Purely additive; nothing changes behaviour.
5. **The catalogue gate**, with its four rules, wired into CI.
6. **`cxx_mapping` for cardiaccore** so `strict_dict_key_report` can run there
   at all. It cannot today: no `cxx_mapping` block, no allowlist file.

7. **Split the suites by role.** Mark every test builder or runner, and report
   their coverage separately. A skipped builder gate becomes `unavailable` to a
   builder and `not_applicable` to a runner instead of vanishing. This is step
   1's rule applied to the test suite, and it depends on nothing else.
8. **The cardiacCore regression** -- the idealized case across two workflows,
   static and native-owned -- with a runner-suite test that runs the adapter's
   declared operations against its output and asserts their verdicts.
9. **Delete the hand-written C++ ties**, once step 8 runs. Not before: see
   4.5.5.
10. **The origination lint**, advisory first, enforcing once the nine existing
    violations have owner rulings.

Steps 1 and 2 are worth doing even if the rest is never done. Step 7 is the
cheapest single change that would have surfaced the ~83 dark tests. Step 8 is
the only one that establishes the adapter actually works, and step 9 must not
precede it.

## 8. Open questions, for the owner and not for an agent

These are scientific decisions surfaced by the evidence pass. They are recorded
here because a mechanism built over an unresolved contradiction will mechanise
the contradiction.

1. **The UVC seed rule (contradiction C4).** The 2026-09-16 retirement review
   records that the owner retired the standalone UVC-threshold seed method. The
   study protocol states the adapter contract encodes "the recovered-RV-septum
   UVC rule". Both documents are current. Either the rule survives inside the
   tree-validation contract and only the standalone script was deleted, or it
   was genuinely retired and two documents still advertise it. No document says
   which.
2. **Slab/tree mutual exclusion (C5).** One document appeals to it as an
   existing preflight rule; the newer one records that this preflight is being
   retired and its replacements return empty tuples. A stated domain constraint
   is currently enforced by nothing.
3. **Three incompatible next steps (C7)** for the cardiaccore package, written
   on three consecutive days.
4. **The nine originated quantities.** Each needs a ruling: delete, demote to a
   correspondence test, or move native. The six in
   `test_tree_validation.py` are the sharpest -- an invented labelled surface
   (`_surface_points()`, with hand-assigned AHA segments) is the sole evidence
   for five assertions about septal identity and the LV-to-RV septal remap. The
   `1e-9` His-root tolerance cites a measurement ("9.4e-10 m on the idealized
   biventricular ellipsoid") that exists nowhere in the repository.
5. **Two contradictory physiological floors in one file.**
   `test_ionic_catalog_contract.py` asserts `recommended_exports >= 5` in one
   class ("5 = voltage + calcium + 3 currents minimum") and `>= 4` in another.
   Both run. Neither is anchored.

## 9. Observations recorded in passing

Not part of this design; recorded because they are the same class and will
otherwise be rediscovered.

- `ProvenanceComponent`'s docstring says `strength` is `"verified_absence"`.
  The code assigns `strength="absence"` and puts `"verified_absence"` in
  `method`. `is_complete` checks `{"content", "absence"}`. The docstring names
  a value that field never holds. Observed 2026-09-18.
- `scan-dict-keys.py` is invoked nowhere -- not CI, not a test, not a caller --
  though it is the front end to the scanner the cardiaccore input catalogue
  cites as its provenance.
- `equivalence_protocol.yaml` has no executed reader. Its consumer computes
  `Path(omnidriver.__file__)` against a PEP 420 namespace package, so it raises
  before doing anything, and both tests that touch it monkeypatch it out.
- `check-import-boundaries.py` has no rule naming `cardiaccore` in either
  direction, and there is no `test-cardiaccore` CI job, while CLAUDE.md
  presents that gate as the enforcement behind core's cardiac-freedom.
- **Declared-to-exists is gated; exists-to-declared is not.**
  `test_advertised_operations_have_resolvable_interfaces` proves every declared
  operation resolves and that its declared `inputs` match the real signature.
  Nothing proves the reverse. `discover_coordinate_ring_candidates_from_vtk` is
  public, documented, and in no operation record. A one-directional gate on a
  two-directional relation is the same shape as every other finding here.
- **The workflow DAG's types evaporate at the boundary.** `WorkflowStep` is a
  frozen dataclass with `depends_on`, `produces` and `consumes`, used during
  normalization and then discarded: `workflow_runner`, `workflow_orchestrator`,
  `run_document_exec` and `sweep_runner` all take `workflow_dag: dict[str, Any]`
  and re-scan `workflow_dag["steps"]` by hand. The declaration exists and is not
  load-bearing.
- **`--dry-run` is dead surface.** Defined as a flag, rejected by `describe`,
  `plan`, `step` and `run`, accepted silently by the three sweep actions, and
  read by no code anywhere. Its help text still promises "Plan and print
  simulation cases without running OpenFOAM." The real dry run is
  `plan --strict`.
- **The README of `omnidriver-cardiaccore` documents an operation and a module
  that do not exist** (`cardiaccore.cobiveco.normalize.v1`,
  `omnidriver.cardiaccore.operations.cobiveco`). Nothing checks a README against
  `OPERATIONS`.
- CLAUDE.md documents three packages; there are four. Its "Where authority
  lives" section names only documents that stop at 2026-09-04, and none of the
  four that steer current work.
