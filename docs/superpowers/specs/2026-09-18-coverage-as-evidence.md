# Coverage is evidence

**Status:** specification. Supersedes `2026-09-18-coverage-as-evidence-design.md`
and incorporates `2026-09-18-coverage-as-evidence-review.md`.
**Consolidated:** 2026-09-18, against main at the post-integration baseline.

Both source documents stay in the tree. The design carries reasoning this
document compresses; the review carries the probes that justify the amendments.
Where they disagreed the review wins, and §11 records each change with its
reason, because the superseded position is usually the one someone will
rediscover.

---

## 1. The finding

This repository is **honest per item and dishonest in aggregate.**

Per item the evidence discipline is real. `ProvenanceComponent` carries
`strength` and says it "is honest about how much the fingerprint actually
proves". `ComparisonOutcome` bounds itself: "Core exposes a bounded summary
only". `BUILDER_AGENT_EVIDENCE_CONTRACT.md` states that "Unavailable evidence is
explicit ... It must not silently become a default."

In aggregate, three mechanisms treat *absence of data* as *evidence of success*:

| Aggregate | Computation | What a check that did not run contributes |
|---|---|---|
| `readiness_score` | `sum(item.points)` over seven weighted stages | **full points, status `passed`** |
| `ProvenanceSnapshot.is_complete` | `all(strength in {"content","absence"})` | nothing — a root never walked cannot lower it |
| catalogue `source_refs` | one drift guard, `skipif(monorepo_root is None)` | a green CI line |

These are one defect. Each aggregates over what it examined and records nothing
about what it declined to examine, so an empty result set is indistinguishable
from a clean one.

`_score_from_diagnostics` branches on error and on warning, then falls through
unguarded to `status="passed", points=max_points`. Every skip path returns an
empty diagnostic tuple and lands there. Four of seven stages have a vacuous-pass
trigger — `case_preparation_files` (15), `dictionary_resolution` (20),
`environment_preflight` (10), `mesh_geometry` (5) — so **fifty of one hundred
weighted points are earnable by checks that never executed**, each with an
affirmative summary. `mesh_geometry` reports "Mesh-scale checks did not find
run-preparation issues". `is_launchable` inherits it: `environment_ok = not
environment_errors`, and `not ()` is `True`.

Confirmed by direct probe during review:
`_score_from_diagnostics(..., diagnostics=(), evidence={"skipped": True})` awards
10/10 and `passed`; `is_launchable(plan_status="ok", environment_diagnostics=())`
returns `launchable=True`; `regenerate-ionic-catalog.py --check` prints that it
has no usable source root and returns zero; `strict_dict_key_report` with a
missing root, empty entries and empty allowlist returns `ok`.

`docs/OMNIDRIVER_ROADMAP.md` already forbids this: "Missing or skipped checks
must never increase a readiness score or appear as proven compatibility." The
rule is stated and not implemented.

**The guard that ratified.** `test_strict_planning.py` asserts
`readiness_score["score"] == 100` and `status == "ready"` for a plan built with a
nonexistent OpenFOAM bashrc, under a conftest setting `SKIP_ENV_DIAGNOSTICS`
suite-wide. Per CLAUDE.md's rule about never weakening a guard: this guard did
not fail, it **ratified**. Changing its expectation is the intended direction,
not a weakening.

## 2. The invariant

> **An aggregate may not report success over checks it did not perform.
> Every aggregate carries its own coverage, and a check that could not run
> is a distinct outcome from a check that passed.**

**Launch corollary.** A *required* check that cannot run prevents the claim that
depends on it. Explicit verification gates return non-zero on unavailable
required evidence.

This replaces the design's blanket "a check that cannot run fails", which
contradicted the design's own §4.1 policy and would have made offline planning
impossible. Planning may produce a structurally valid plan with launch blocked.
An explicit permitted override may authorise a run; it can never turn unavailable
evidence into a pass, and the check ids, policy and override are recorded in the
plan and attempt evidence.

## 3. Two axes, and a third that is not an outcome

**Coverage** answers *did this check run?* It is a property of an act of
verification, computed at plan time, and it decays — a stage covered yesterday is
uncovered today if its tool disappeared.

**Evidence status** answers *how strong is this claim?* It is a property of a
declared fact, authored by a builder, stable until the fact is re-derived.

These are orthogonal and must not be merged. An entry with
`evidence_status="supported"` can sit in a stage whose coverage is `unavailable`
— a well-evidenced fact that nothing checked on this run. Collapsing them makes
that state unrepresentable.

**Ownership is a third axis, and it is not a coverage outcome.** The design made
`native_owned` a seventh `COVERAGE_OUTCOME` that left the denominator. That
conflates *who defines a check* with *what happened to it*. A native-owned
regression can pass, fail, be unrequested, or be unavailable, and a real native
failure must not be recorded as the same permanent non-blocking label as a check
nobody asked for.

So: every check carries an **owner** (`orchestration` | `native`) and,
separately, an **outcome**. Native scientific verification is reported beside
orchestration readiness and never summed into it. A declared acceptance workflow
**fails acceptance when its required native checker fails**, and that needs no
extra synthetic readiness stage.

Coverage outcomes, one vocabulary, already two-thirds present in
`core/experiments._COMPARISON_STATUSES`:

```
passed | failed | unavailable | not_requested | not_applicable | unknown
```

The distinctions that matter, all three of which are `passed` today: a generic
case has no plugin configuration to parse — `not_applicable`;
`SKIP_ENV_DIAGNOSTICS` — `not_requested`; a missing C++ source root —
`unavailable`.

Applicability, selection and obligation are declared **separately from the
result**. No installed hook does not by itself prove `not_applicable`;
`not_applicable` stays visible with a reason even when it does not block launch.
Stage results come from the actual checker and are never reconstructed afterwards
from diagnostic counts or environment flags.

## 4. Scoring

The design proposed `earned / eligible` plus a coverage ratio, arguing the
percentage "can no longer be inflated by suppression". It can: suppress a failing
check and it leaves `eligible`, so `earned / eligible` rises to 100% while
coverage falls beside it. A reader who sees one number sees the wrong one.

Per declared support profile and audience, enumerate expected checks **before**
running them, then define:

| term | meaning |
|---|---|
| `applicable_weight` | expected checks, excluding only explicitly justified `not_applicable` |
| `executed_weight` | checks returning passed, warning or failed |
| `earned_weight` | passed weights, plus the warning policy of §10 |
| `coverage` | `executed_weight / applicable_weight` |
| `success_among_executed` | `earned_weight / executed_weight`, where useful |
| `readiness` | `earned_weight / applicable_weight`, if a single figure is retained |

Rules:

- An unavailable **or suppressed** applicable check stays in the denominator and
  earns nothing. This is the whole difference from the superseded model.
- A failed check counts as executed.
- An empty denominator is `null` with an explanatory state — never 100%.
- A partially covered plan is not `ready` merely because everything executed
  passed.
- Uncovered stages are named, each with its outcome and reason.
- Neither percentages nor stage weights authorise execution. Launch policy is §5.

`StrictDiagnostic.level` gains no new values: coverage is a property of a stage,
and a stage that did not run has no diagnostics to level.

## 5. Launch policy

`is_launchable` takes coverage as an input, and the policy is explicit:

| outcome | effect on launch |
|---|---|
| `unavailable` on a required check | blocks |
| `not_requested` | does not block; reported in `launch` |
| `not_applicable` | does not block; reported with its reason |
| `failed` | blocks |
| required native checker failed | fails acceptance, independent of driver exit code |

Applied at the **shared execution boundary** — run, step, sweep children and
resume alike — with execution-relevant identities revalidated before dispatch.
There must be a test that the gate cannot be bypassed through another CLI route.
Existing skip variables (`SKIP_ENV_DIAGNOSTICS`, `SKIP_MESH_DIAGNOSTICS`) need a
documented migration onto this policy rather than silent removal.

## 6. Provenance

The enumeration boundary is sound and is **not** widened. `enumerate_case_inputs`
stays exhaustive within declared walk roots, keeping the safety property that an
unrecognised file inside a root becomes a `required_input`. A whole-case-tree
digest stays rejected: `CLEAN_INSTALL_ACCEPTANCE_2026-09-08.md` rules that
integration must not content-hash the historical tutorial tree against a ~204 GiB
checkout. Coverage is declared and recorded, not bought by walking everything.

What is missing is that the snapshot has no notion of what it declined to walk.
`_walk_files` returns `[]` for a non-directory, and four of cardiacFoam's eleven
declared rules are files: `Allrun` and `Allclean` reach the snapshot only through
step-executable resolution, while `README.md` and `runRegressionTest.sh` are
declared and never fingerprinted.

**Repair it; do not merely record the omission.** Declared *consumed* files are
fingerprinted directly rather than added to an unwalked list. Each coverage
record carries a rule/input identity, a classification, an outcome and a reason,
distinguishing:

- a directory root walked,
- a declared file consumed directly,
- an optional absence,
- a generated output,
- declared-but-irrelevant documentation.

Required unenumerated or unreadable inputs make the snapshot incomplete. An
unconsumed `README.md` must **not** prevent resume merely because a `CaseFileRule`
lists it — that would trade a false pass for a false block.

The enumeration policy and coverage identity join the aggregate digest and its
comparison, and completeness is enforced in resume decisions. `SCHEMA_VERSION`
changes, by the existing convention that it encodes policy rather than layout;
old snapshots stay inspectable, with explicit incompatible-policy refusal for
reuse.

## 7. Catalogue facts and evidence

Two flat fields on `DictEntry`, both defaulting to the weakest value so silence
claims nothing:

```python
evidence_channel: str = "unknown"   # case_files | documentation | api_schema | source | execution | unknown
evidence_status:  str = "candidate" # supported | observed | conditional | candidate | unknown | unsupported
```

Flat, not nested: `DictEntry` already carries five predicate fields inline, and a
nested type would need its own serializer among ninety-six hand-written `to_json`
pairs.

**But two strings are presentation metadata, not authorization.** An entry's
*name* may come from source, its *unit* from documentation, and its *example
value* from a case. One channel must not upgrade all three claims. Claims may
therefore reference versioned evidence records carrying workflow and build scope,
checker identity and version, source or document locator, and content digest —
starting as a small companion record keyed by entry and claim, not a new schema
framework. **A support status is invalidated when its supporting identity
changes**, and its consumer is defined at the mutation/planning boundary,
including how legacy entries migrate.

Every reference asserted as supporting evidence is checked. Path existence alone
does not prove the statement attached to it.

Source stays **optional** for solver onboarding, as the builder contract already
requires. Units or enums may be established by an authoritative API/schema or by
documentation; a C++ file cannot be mandatory for every solver.

The gate, modelled on `export-capability-seams.py` — the one generate-and-verify
loop in this repository that closes:

1. `evidence_channel="source"` requires at least one resolving `source_refs` path.
2. A required check that cannot run reports `unavailable` and exits non-zero.
3. `unit` may be declared only with channel `source` or `documentation` and a
   resolving reference. Coordinate magnitudes do not establish units.
4. `enum_values` require a `source_refs` and are never derived from arbitrary
   lexical discovery. Mechanical extraction of an *explicit* enumeration is
   acceptable once its binding to the user input has been reviewed; anything
   else stays `candidate`.

It is a builder-audience gate (§9): it runs when a native source root is
supplied, reports `unavailable` when one is not, and never contributes to a run's
readiness.

## 8. What may be mechanised from C++

A scanner reliably yields `{key, C++ type, required|optional, literal default,
file:line}` for roughly 80–85% of lookup sites across both native trees.

**Only required-versus-optional is adopted** — the one fact with a clean
syntactic discriminator, since `get<T>` throws and `getOrDefault<T>` carries its
default inline, with no intermediate form in either tree.

**With a qualification the design omitted:** `get` versus `getOrDefault`
establishes required/defaulted behaviour *at one read site*, not unconditional
case-level requiredness. The read-site context is retained and unresolved
activation conditions stay explicit.

Not mechanised, by decision:

- **Dotted-path attribution** — receivers are opaque. In `generatePurkinjeTree.C`
  sixteen lookups hang off a receiver bound to `subDict(ventKey)`, a runtime
  parameter called twice; no textual analysis recovers that a key lives under
  both `lv` and `rv`.
- **Enumerations** — of three `Enum<>` tables in cardiacCoreStandalone and five
  in noFrontendCardiacFoam, zero and one respectively describe a user dictionary
  key. Real ones take four shapes, none self-labelling.
- **Units** — sometimes bound at the lookup, usually absent.
- **Conditional requirements** — control flow. In `generatePurkinjeTree.C` the
  `extension` block is required only when `terminalModel == "transmural"`; a
  scanner sees five optional keys with defaults and is wrong in the direction
  that lets an invalid case plan.

The 15% a scanner cannot see is exactly the scientific content, and rules 3–4 of
§7 stop it being guessed.

**Baseline to reconcile first:** the current scanner does not expose the `scope`,
`method` or `dict_read_default` API the builder guide describes, and cardiacFoam's
profile resolves its scanner root to `/Users/simaocastro/src` rather than the
native checkout, while cardiacCore has no `cxx_mapping` at all. The gate needs an
explicit native checkout root and explicit scan subdirectories; a static relative
profile path with ancestor-based discovery is not sufficient. Reconcile this
before assigning implementation work.

## 9. Test policy: two audiences, three kinds

Two owner rulings stand: scientific logic is native-owned, and builder
verification is a different product from case verification.

**Builder and runner are report *audiences*, not test kinds.** The design treated
them as a partition of the suite; that forces every unit test into an audience
and adds no evidence. Three kinds of test exist and stay distinct:

| kind | subject |
|---|---|
| software unit tests | arithmetic, transforms, parsing, rejection paths |
| source/declaration checks | does a declaration still point at something real |
| native integration checks | does the tool come out green on real data |

Coverage is **reported per audience**: a runner's readiness may not be inflated
or deflated by builder gates, and a builder's onboarding report may not be
reassured by runner greens. A single blended percentage is uninterpretable, which
is what `readiness_score` is today. The roles already exist —
`agent_guidance/manifest.yaml` binds `builder` and `runner` to different
`required_catalogs` and refuses an unknown role rather than defaulting.

Expected checks are recorded **independently of which tests collect or run**.
Ordinary developer jobs may exclude unselected integrations; a
release/native-acceptance job must require its named checks, reject missing
prerequisites and zero selection, and publish the evidence report.

### 9.1 What may be asserted

The design's numeric-literal lint is **rejected as written**. Unit tests need
small constructed arrays for arithmetic and rejection paths; a zero distance to a
supplied point is a mathematical expectation, not a physiological threshold. And
writing an invented threshold into a file so a test can read it back supplies no
independent authority — the lint would have been satisfied by the very move it
was meant to prevent.

The boundary instead:

> **Synthetic fixtures may establish adapter behaviour under declared
> assumptions. Scientific acceptance criteria must have an independently
> identified, native- or study-owned oracle and an explicit scope.**

> Python may verify a correspondence. It may not originate a quantity.

— survives as the rule for the *scientific* half only, not as a lint over every
numeric literal.

**Targeted C++ and metadata regression guards are not blanket-deleted.** The
dictionary scanner matches sets of names — not species, semantic scope, units,
conditional branches or compiled availability — so a generic key gate cannot
replace those guards. Each is replaced only after an equivalent assertion with at
least the same failure sensitivity is identified. A working cardiacCore
regression does not cover cardiacFoam model metadata.

### 9.2 Measured state

610 Python test functions across the domain packages at the time of the design:

| | cardiaccore | cardiacfoam |
|---|---|---|
| structural / agnostic | 49 | ~482 |
| correspondence | 7 | ~63 |
| **originated quantity** | **6** | **3** |
| skipped in that checkout | 0 | ~83 |

Two distribution findings matter more than the nine originations.

**Every cardiacfoam test anchored on an actual C++ file, native binary, tutorial
case or committed reference is skipped in a bare checkout.** Under the audience
split most are builder-audience checks correctly reporting `unavailable`; today
they report nothing, and silence is indistinguishable from success.

**cardiaccore inverts it.** No `conftest.py`, and not one test opens a C++ file,
though its docstrings cite `coordinatesConvention.H`, `generatePurkinjeTree.C`
and commit `1ea6d23`. It has the appearance of correspondence with none of the
substance.

**Updated 2026-09-18 (post-integration):** the census is stale in two ways the
review predicted. cardiaccore now runs 69 tests with one skip — the optional
`pyvista` bridge in `test_electrode_normalization.py` — not 62 with none. And it
is now installed in the documented environment with its own CI job, so the
review's `PYTHONPATH` workaround is no longer needed. Re-measure before citing
these numbers; do not quote them as current.

The tests that could verify correspondence do not run. The tests that run cannot
verify correspondence. That finding survives re-measurement.

## 10. The warning policy

The review requires `earned_weight` to be "passed weights plus an explicitly
defined warning policy" and does not define it. **This is the one open decision
in this document.**

**Corrected 2026-09-18, before implementation.** A first draft of this section
proposed that a warning earn *full* weight. That was written without reading the
code: `_score_from_diagnostics` already awards `max_points // 2` on
`has_warning`. A policy therefore already exists — half weight — it is simply
implicit and undocumented rather than absent.

So the default is to **preserve half weight and state it**, not to change it. A
warning counts as `executed`, contributes half its weight to `earned`, and is
reported. Changing scoring semantics while fixing a different defect would make
any score movement ambiguous between the two causes, and the ratifying test
would no longer isolate what it is meant to prove.

The owner decision that remains is narrower than the draft implied: whether half
weight is right, and whether it should be per-profile configurable. Neither
blocks the work below — implement against current behaviour and revisit with the
scores in front of you.

## 11. What changed from the design, and why

| § | Superseded position | Reason |
|---|---|---|
| 2 | "a check that cannot run **fails**" | contradicted the design's own §4.1, and would forbid offline planning. Replaced by the required-claim formulation. |
| 4 | `earned / eligible`, claimed uninflatable | suppression removes a failing check from `eligible`, raising it to 100%. `applicable_weight` keeps it in the denominator. |
| 3 | `native_owned` as a seventh coverage outcome | conflates ownership with outcome; a real native failure would carry the same label as a check nobody requested. Ownership became a separate axis. |
| 6 | record `declared_unwalked` | recording an omission is not repairing it. Declared consumed files are fingerprinted; an unconsumed README must not block resume. |
| 7 | two strings as evidence | one channel would upgrade name, unit and example together. Scoped per-claim records added. |
| 8 | `get`/`getOrDefault` ⇒ requiredness | it is read-site behaviour, not case-level requiredness. |
| 9 | builder/runner as a partition of the suite | they are report audiences; test kinds are orthogonal. |
| 9.1 | numeric-literal lint | would forbid legitimate unit tests and would be satisfied by writing an invented threshold to a file. Replaced by the oracle-and-scope rule. |
| 9.2 | cardiaccore census | stale: 69 tests, one skip, now installed with a CI job. |
| — | dirty-tree rule | see §12: dirty source does not establish what a binary was built from. |

## 12. Pinning and dirty trees

Neither native tree has a `VERSION` file or reachable tag; `git describe` fails on
both, both working trees are dirty, and one is on a feature branch. So
`verified_at` records the source SHA, a digest of the files actually read, and a
`dirty` flag. A SHA alone would not identify what was checked. The gate does not
refuse to run on a dirty tree — refusing would mean never running.

**Scope, added by the review:** builder inspection may accept dirty source and
record exactly the bytes read. That does **not** establish that an existing binary
was compiled from those bytes. The selected cardiacFoam runtime fixture currently
rejects build-affecting `src/` drift; preserve that guarantee unless a build
attestation binds the dirty source to the executable.

## 13. Out of scope

- **Directory restructuring** (`sim_engine` / `agent_layer` / `schemas`).
  Rejected for four independent reasons: there is no non-deterministic code here,
  so `agent_layer/` would contain markdown; the proposal cuts horizontally by
  determinism while the existing split is vertical by domain; the horizontal seam
  it wants already exists as the capability seam, with 24 Protocols and a
  CI `--check`; and every defect found was in a *relation* or an *aggregate*, not
  a package boundary, so rearranging packages would move all of them untouched.
- **A regenerated `dict_entries.json`.** It existed, churned six times in thirty
  commits, and was deleted deliberately. Rebuilding it is the idea that drifted.
- **Context hydration and bounded agent output.** `StrictPlanReport.to_json()`
  serializes all 22 fields unconditionally with no projection and no `--brief`.
  A different invariant with a different mechanism; its own design.
- **Pydantic.** Four parallel contract mechanisms exist; the question is whether
  they converge, not whether to add a fifth.
- **Widening provenance enumeration.** §6.
- **Any change to scientific method.** §15.

## 14. Sequence

Two orderings, at different granularities, and they do not compete. The
programme order is the owner's; the mechanism order sits inside its step 1.

**Programme** (owner's ordering; step 1 completed 2026-09-18):

1. ~~Integrate the three branches into one tested baseline.~~ **Done** — merged
   to main, 1968 passing, four CI shapes green.
2. **Consolidate the amendments** (this document) **then fix coverage accounting
   and launch policy.** Completion: skipped checks cannot earn success; required
   unavailable checks block execution; neutral tests demonstrate both.
3. Extract reusable acceptance machinery from cardiacFoam.
4. Complete one installed cardiacCore preprocessing workflow.
5. Exercise cardiacFoam's short workflows through the same contract.
6. Connect cardiacCore outputs to one cardiacFoam workflow.

**Mechanism**, inside programme step 2 and after:

1. A required check that cannot run reports `unavailable` and returns non-zero.
   One branch, several call sites; kills the silent-pass class at its cheapest
   point.
2. Coverage in the readiness path: the outcome vocabulary, the required `outcome`
   argument to `_score_from_diagnostics`, the five scoring terms, coverage into
   `is_launchable`. Update the ratifying test to assert the honest number.
3. Coverage fields on `ProvenanceSnapshot`, with the `SCHEMA_VERSION` bump and
   direct fingerprinting of declared consumed files.
4. `evidence_channel` / `evidence_status` on `DictEntry`, defaulting weak, no gate
   yet. Purely additive.
5. The catalogue gate with its four rules, wired into CI — after the scanner
   baseline of §8 is reconciled.
6. `cxx_mapping` for cardiaccore, so `strict_dict_key_report` can run there at
   all. It cannot today.
7. Report coverage per audience. The cheapest single change that would have
   surfaced the ~83 dark tests, and it depends on nothing else.
8. The cardiacCore regression: the idealized case across two workflows, static
   and native-owned, with a runner-audience test asserting the adapter's declared
   operations against its output.
9. Retire hand-written C++ ties **only** after step 8 runs, and only where an
   equivalent assertion of at least equal sensitivity exists (§9.1).

Steps 1 and 2 are worth doing even if nothing else is. Step 9 must not precede
step 8: doing so would move this repository from dark verification to none.

## 15. Open questions, for the owner

Scientific decisions surfaced by the evidence pass. A mechanism built over an
unresolved contradiction mechanises the contradiction.

1. **Slab/tree mutual exclusion.** One document appeals to it as an existing
   preflight rule; a newer one records that preflight being retired with its
   replacements returning empty tuples. A stated domain constraint is enforced by
   nothing.
2. **The nine originated quantities.** Each needs a ruling — delete, re-anchor to
   a case-supplied value, or move native. The six in `test_tree_validation.py` are
   sharpest: an invented labelled surface with hand-assigned AHA segments is the
   sole evidence for five assertions about septal identity, and the `1e-9` His-root
   tolerance cites a measurement that exists nowhere in the repository. Now
   governed by §9.1's oracle rule rather than by a lint.
3. **The ionic export floors.** `TestRecommendedExportsExpanded` asserts `>= 4`
   and `TestRecommendedExportsExpansion` asserts `>= 5`, both live in one file.
   **Corrected 2026-09-18:** these are not contradictory — `>= 5` implies `>= 4`,
   so they cannot disagree and the weaker one is unfalsifiable while the stronger
   holds. They are two unanchored answers to "what is the floor". Independently
   noted by the review.
4. **Catalogue entry counts.** `test_generic_contract.py` asserts exactly 87
   dictionary entries; `test_dict_entries_catalog.py` asserts `> 80`. Structural,
   not scientific, but still two answers.
5. **Unresolved catalogue references**, measured by the review against local
   native roots: cardiacCore 6 of 18 unique references, cardiacFoam 3 of 73.
   cardiacCore's are `cases/bivCase/system/generatePurkinjeTreeDict`, three under
   `src/setCardiacScar/` and two under `src/setPurkinjeScar/`; cardiacFoam's are
   the bath, eikonal and pseudo-ECG verifier sources. These are resolution
   failures against those checkouts, not proof the features are unsupported.
   Reconcile by reviewed migration or by explicitly historical catalogue scope;
   do not waive wholesale.

**Withdrawn.** The design's UVC seed-rule question (C4) is superseded: current
cardiacCore documentation already distinguishes the removed standalone
UVC-threshold implementation from the retained native-surface/AHA proposal, and
`catalogs/purkinje.py` scopes its assumptions rather than claiming universal
acceptance. No further ruling needed on the question as the design posed it.

**Note on ledger entries.** Historical study-ledger entries are dated
observations. Do not treat an older entry as a competing current instruction;
verify against current code and preserve owner decisions.
