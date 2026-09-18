# Review: build OmniDriver around a demonstrated workflow

2026-09-18. Review of `2026-09-18-coverage-as-evidence-design.md` against
OmniDriver `78dc3aee35f6f9b97d2a58ba5b432fa39749a53d` and selected local native
source. Recommendations, not implemented behavior or new scientific policy.

## Recommendation

Accept the central invariant and the existing Core / OpenFOAM / solver-adapter
boundaries. Amend the scoring, test policy, evidence model, and rollout before
implementation. This is a valuable assurance design, but is not by itself a
complete plan for building the agent-facing product.

The next deliverable should be an installed cardiacCore workflow that an agent
can inspect, modify in a disposable case, plan, execute, and reconcile. Use
cardiacFoam immediately as the more demanding second adapter and source of
existing integration machinery. Do not finish a universal source scanner or
classify every historical test before closing that first loop.

## What the diagnosis gets right

- Empty diagnostics do not prove execution of a check. In a direct probe,
  `_score_from_diagnostics(..., diagnostics=(), evidence={"skipped": True})`
  awarded environment preflight 10/10 and `passed`.
- `is_launchable(plan_status="ok", environment_diagnostics=())` returned
  `launchable=True`. The execution gate needs explicit coverage evidence.
- `regenerate-ionic-catalog.py --check` printed that it had no usable source
  root and returned zero. A requested verification should report unavailable
  and return nonzero when it cannot establish its advertised claim.
- A direct `strict_dict_key_report` probe with a missing root, empty entries,
  and empty allowlist returned `ok`. Expected verification scope must exist
  before aggregation; output-derived scope admits vacuous success.
- Native scientific acceptance belongs to the native workflow. OmniDriver
  must report the native checker's result and identity faithfully.
- Declared inputs, bounded staging, content identities, and existing package
  seams are preferable to restructuring the repository or hashing entire
  historical tutorial trees.

Evidence: `core/runtime/strict_audit.py`, `core/runtime/launch_readiness.py`,
`openfoam/dict_keys_scanner.py`, and `scripts/regenerate-ionic-catalog.py`.

## Amendments required before implementation

### 1. Define coverage and success separately, including zero coverage

The proposed `earned / eligible` can still increase when an operator suppresses
a failing check. With equal weights, pass + fail gives 50%; suppress the failure
and the score over executed checks becomes 100%. Showing coverage alongside it
helps, but this cannot remain an unqualified readiness percentage.

For each declared support profile and audience, enumerate expected checks before
running them. Define:

- `applicable_weight`: expected checks excluding explicitly justified
  `not_applicable` checks;
- `executed_weight`: checks returning passed, warning, or failed;
- `earned_weight`: passed weights plus an explicitly defined warning policy;
- `coverage = executed_weight / applicable_weight`;
- `success_among_executed = earned_weight / executed_weight`, if useful;
- if a legacy readiness score is retained,
  `readiness = earned_weight / applicable_weight`.

An unavailable or suppressed applicable check stays in the applicable
denominator and earns nothing. A failed check counts as executed. An empty
denominator is `null` with an explanatory state, never 100%. Do not call a
partially covered plan `ready` merely because all executed checks passed.
Neither percentages nor arbitrary stage weights authorize execution.

Applicability, selection, and obligation must be declared separately from the
result. No installed hook does not by itself prove `not_applicable`.
`not_applicable` should remain visible with a reason, even when it does not
block launch. Stage results should come from the actual checker, not be
reconstructed afterward from diagnostic counts or environment flags.

### 2. Make launch policy explicit and preserve offline planning

Replace the blanket corollary with:

> A required check that cannot run prevents the claim that depends on it.
> Explicit verification gates return nonzero on unavailable required evidence.

Offline planning may produce a structurally valid plan with launch blocked.
Optional observations need not block all executions. An explicit permitted
override may authorize a run, but it cannot turn unavailable evidence into a
pass. Record the check IDs, policy, and override in the plan/attempt evidence.
Existing skip variables need a documented migration to that behavior.

Apply the policy through the shared execution boundary, including run, step,
sweep children, and resume. Revalidate execution-relevant identities before
dispatch. Test that failure cannot be bypassed through another CLI route.

### 3. Treat native ownership as ownership, not a check outcome

`native_owned` describes who defines a check, whereas passed/unavailable
describe what happened. A native-owned regression can pass, fail, be unrequested,
or be unavailable. Preserve both dimensions and report native scientific
verification separately from orchestration readiness.

Otherwise a real native regression failure risks becoming the same permanent,
nonblocking `native_owned` label as a check that was never requested. A declared
acceptance workflow must fail acceptance when its required native checker fails.
There is no need for an eighth synthetic readiness stage to achieve this.

### 4. Retain legitimate synthetic and targeted contract tests

Reject the numeric-literal lint in section 4.5.4 as written. Unit tests need
small, constructed arrays to test arithmetic, transforms, parsing, and rejection
paths. A zero distance to a supplied point can be a mathematical expectation;
it is not necessarily a physiological threshold. Conversely, saving an invented
threshold in a file and reading it during a test supplies no independent
scientific authority.

Use this boundary instead:

> Synthetic fixtures may establish adapter behavior under declared assumptions.
> Scientific acceptance criteria must have an independently identified,
> native- or study-owned oracle and an explicit scope.

Keep software unit tests, source/declaration checks, and selected native
integration checks as distinct test kinds. Builder and runner are report
audiences; forcing every unit test into one audience does not add evidence.
Record expected checks independently of which tests collect or run. Ordinary
developer jobs may exclude unselected integrations; a release/native-acceptance
job must require its named checks, reject missing prerequisites and zero
selection, and publish the evidence report.

Do not blanket-delete targeted C++ or metadata regression guards. The current
dictionary scanner matches sets of names, not species, semantic scope, units,
conditional branches, or compiled availability. A generic key gate therefore
cannot replace all of those guards. Replace each only after identifying an
equivalent assertion with at least the same failure sensitivity. A working
cardiacCore regression alone does not cover cardiacFoam model metadata.

### 5. Record evidence for a scoped claim, not just an entire entry

Weak defaults for new fields are sensible. Two strings on a `DictEntry` are
useful presentation metadata, but insufficient authorization evidence: an
entry's name may come from source, unit from documentation, and example value
from a case. One channel must not upgrade all three claims.

Allow claims to reference versioned evidence records, including their workflow
and build scope, checker identity/version, source or document locator, and
content digest. This can start as a small companion record keyed by entry and
claim; it does not require a new general schema framework. A support status
must be invalidated when its supporting identity changes. Define its consumer
at the mutation/planning boundary, including how legacy entries migrate.

Check all references asserted as supporting evidence. At least one existing
path is weaker than the current cardiacFoam test that checks every reference,
and path existence alone does not prove the statement attached to it.

Keep source optional for solver onboarding, as the builder contract already
requires. Units or enums may be established by an authoritative API/schema or
documentation; a C++ file cannot be mandatory for every solver. Mechanical
extraction of an explicit enumeration is reasonable once its binding to the
user input is reviewed. Arbitrary lexical discoveries must remain candidates.

Similarly, `get` versus `getOrDefault` establishes required/defaulted behavior
at a particular read site, not unconditional case-level requiredness. Retain
the read-site context and leave unresolved activation conditions explicit.
The current scanner does not expose the `scope`, `method`, or
`dict_read_default` API described in the builder guide; reconcile that baseline
before assigning implementation work.

### 6. Repair provenance coverage, rather than only recording omissions

Keep the bounded enumeration policy, but distinguish directories, direct files,
optional absence, generated outputs, and irrelevant documentation. Fingerprint
declared consumed files directly; do not merely add them to an unwalked list.
An unconsumed README should not prevent resume solely because it is listed in
`CaseFileRule`.

Coverage records need a rule/input identity, classification, outcome, and
reason. Required unenumerated or unreadable inputs make the snapshot incomplete.
Include the enumeration policy and coverage identity in the aggregate digest
and comparison; enforce completeness in resume decisions. Keep old snapshots
inspectable, with explicit incompatible-policy refusal for reuse.

The dirty-tree rule also needs scope. Builder inspection can accept dirty
source and record exactly the bytes read. That does not establish that an
existing binary was compiled from those bytes. The selected cardiacFoam runtime
fixture currently rejects build-affecting `src/` drift. Preserve that guarantee
unless a replacement build attestation binds the dirty source to the executable.

## Delivery sequence

1. **Close the demonstrated false successes.** Add core tests for explicit
   skipped/unavailable/failed/applicable outcomes and a separate OpenFOAM test
   for missing scanner roots. Stop source-check CLIs returning success without
   evidence. Make the shared launch predicate consume the result.
2. **Make cardiacCore installed and repeatable.** Add its package to CI and
   wheel/discovery checks. Select a bounded workflow, runtime/build identity,
   native input asset manifest, disposable output, and native checker. Start
   with the existing declared preprocessing path; bring the intended human/pig
   tree regressions under the same explicit fixture contract as their inputs
   and oracle become available. Retain existing unit tests during this work.
3. **Exercise cardiacFoam in the same increment.** Reuse its selected-source,
   selected-runtime, manifest staging, and driver/checker evidence pattern.
   Use the short single-cell and small tissue paths already described by T7.
   Keep exact-input/command correspondence separate from numerical acceptance.
4. **Bind provenance and catalog claims.** Add consumed-file enumeration
   coverage and scoped evidence for the selected workflows. Add cardiacCore
   source mapping and reviewed exclusions when source verification is selected.
   Extend the catalog only as supported workflows need it.
5. **Close the agent loop over these existing operations.** Expose bounded
   inspect/describe, staged edit/diff, plan, execute, and result queries through
   the existing deterministic application functions. Return check IDs, reasons,
   artifact handles, and plan identity; fetch full catalogs/logs on demand.
   Evaluate whether an agent can complete the supported task and stop truthfully
   on unavailable evidence. A resident agent service is not a prerequisite.
6. **Then verify the producer-to-consumer workflow.** Bind cardiacCore outputs
   to one selected cardiacFoam mode: field names, dimensions, mesh identity,
   tissue/scope, and declared dependencies. Successful runs of each tool alone
   do not establish their compatibility. Generalize after this succeeds.

## First acceptance tests

| Layer | Required behavior |
| --- | --- |
| Core | Skipping or losing a checker cannot increase the headline readiness; zero checks cannot yield ready; failed checks remain covered failures. |
| Core | Plan may exist offline; required unavailable execution checks prevent dispatch through run/step/sweep; permitted overrides remain explicit. |
| Core provenance | Consumed direct file included; required missing root prevents complete/resume; optional absence and unconsumed documentation do not; policy changes invalidate reuse. |
| OpenFOAM | Missing/empty scanner scope cannot masquerade as verified coverage; scope ambiguities remain candidates. |
| cardiacCore | Installed discovery and child-process use work; effective overrides reach the disposable case; source assets stay unchanged; required artifacts and native checker results are recorded. |
| cardiacFoam | The same coverage contract handles nondimensional, tissue, unavailable-runtime, missing-hook, and intentionally suppressed paths without all collapsing to passed. |
| Native acceptance | A failing native checker fails the acceptance claim even when driver exit is zero; unrequested and missing required checker are distinct. |

## Verification performed for this review

The initial focused pytest command could not collect cardiacCore: the local
`.venv` does not have `omnidriver.cardiaccore` installed. With all four package
source directories explicitly placed on `PYTHONPATH`, the following selection
returned **76 passed, 16 skipped**:

```text
packages/omnidriver-cardiaccore/tests
packages/omnidriver-cardiacfoam/tests/test_strict_planning.py
packages/omnidriver-cardiacfoam/tests/test_selected_cardiacfoam_fixture.py
packages/omnidriver-cardiacfoam/tests/test_selected_cardiacfoam_fixture_acceptance.py
```

The skips were one optional PyVista bridge, thirteen module-gated cardiacFoam
strict-planning tests, and two unselected native fixture acceptance tests.
This is source-level test evidence, not installed-package or live-solver
validation. Native source trees exist locally; no native runtime/fixture was
selected for execution in this review. No native scientific run was performed.

The proposed spec's no-skips cardiacCore census is therefore stale. Its cited
ionic export floors also need rewording: `>= 5` and `>= 4` are inconsistent
policies, but not logically incompatible assertions. Historical study-ledger
entries are dated observations; do not treat every older entry as a competing
current instruction. Verify current code and preserve owner decisions.

Three Luna agents independently reviewed Core coverage/provenance, cardiacFoam
integration/testing, and cardiacCore/native-contract scope. The original
proposal is left intact so these amendments can be assessed separately.

### Additional source-drift checks

Directly resolving the current catalogs' references against the supplied local
native roots produced these results:

| Catalog | Local native HEAD | Entries / unique references | Unresolved references |
| --- | --- | --- | --- |
| cardiacCore | `d1afc3e47a78b92c87288f73aef818b23bbdc9e3` | 87 / 18 | 6 |
| cardiacFoam | `e34024e000d99ca1fcf8acb092b8fa56c547d911` | 173 / 73 | 3 |

cardiacCore's unresolved paths are
`cases/bivCase/system/generatePurkinjeTreeDict`, three files under
`src/setCardiacScar/`, and two under `src/setPurkinjeScar/`. cardiacFoam's are
the bath, eikonal, and pseudo ECG manufactured verifier `.C` files under
`src/verificationModels/ecgVerification/`. These are reference-resolution
failures against these particular checkouts, not proof that their scientific
features are unsupported everywhere. Reconcile them through reviewed migration
or explicitly historical/unsupported catalog scope; do not waive them wholesale.

cardiacFoam's current profile resolves its scanner root to
`/Users/simaocastro/src`, not the native checkout. cardiacCore has no mapping.
The builder gate needs an explicit native checkout root for references and
explicit scan subdirectories; a static relative profile path and ancestor-based
test discovery are not sufficient. The existing selected-source fixture is a
useful starting point, but does not currently supply these older gates.

Current cardiacCore documentation already distinguishes the removed standalone
UVC-threshold implementation from the retained native-surface/AHA proposal;
`catalogs/purkinje.py` explicitly scopes its assumptions rather than claiming
universal scientific acceptance. Update the spec's seed question to that
current baseline before asking for another owner ruling. The slab/tree policy
still needs reconciliation; this review does not select a scientific policy.

Useful implementation starting points:

- [Core audit](../../../packages/omnidriver/src/omnidriver/core/runtime/strict_audit.py)
  and [launch gate](../../../packages/omnidriver/src/omnidriver/core/runtime/launch_readiness.py).
- [Provenance enumeration](../../../packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py)
  and [snapshot model](../../../packages/omnidriver/src/omnidriver/core/runtime/provenance.py).
- [Dictionary scanner](../../../packages/omnidriver-openfoam/src/omnidriver/openfoam/dict_keys_scanner.py).
- [cardiacFoam selected fixture](../../../packages/omnidriver-cardiacfoam/tests/selected_cardiacfoam_fixture.py),
  [driver/checker harness](../../../packages/omnidriver-cardiacfoam/tests/selected_cardiacfoam_integration.py),
  and [native acceptance test](../../../packages/omnidriver-cardiacfoam/tests/test_selected_cardiacfoam_native_integration.py).
- [cardiacCore support boundary](../../../packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/support_boundary.py)
  and [input catalog](../../../packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/inputs.py).
