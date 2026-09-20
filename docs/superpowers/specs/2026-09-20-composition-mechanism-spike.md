# Phase 1 mechanism spike: own it, or adopt pluggy

**Status:** spike complete. Both prototypes were built, measured, and
deleted. This document is the only artifact that survives.
**Written:** 2026-09-20, against `docs/provider-composition-spec` at
`71897f9` (Phase 0 Tasks 1-14 landed).
**Executes:** Task 15 of
`docs/superpowers/plans/2026-09-20-phase0-contract-coherence.md`.
**Answers:** `docs/superpowers/specs/2026-09-20-provider-composition-design.md`
§4.6.

---

## Success criterion (written before either prototype was built)

> `omnidriver step --strict --apply` succeeds on a cardiacCore case with
> **zero new code in `omnidriver-cardiaccore`**. Today it is refused:
> `CardiacCorePlugin` implements none of `apply_overrides`,
> `get_override_target_paths`, `inspect_effective_configuration`,
> `get_override_scopes`, so `legacy_apply_overrides` raises. Under a working
> provider stack the OpenFOAM provider supplies all four.

Both prototypes were graded against this criterion and nothing else, decided
before any code was written.

**Correction to the criterion's own premise, 2026-09-20.** The criterion text
says "`legacy_apply_overrides` raises." Reproducing the refusal (below) shows
the *first* fallback hit is `legacy_override_target_paths`, not
`legacy_apply_overrides` — `step --apply`'s call order resolves mutation
target paths before applying anything
(`core/runtime/step_candidate.execute_step_candidate_owned`), and
`CardiacCorePlugin` implements neither hook, so the target-paths probe fails
first. The underlying finding is unaffected: both fallbacks raise for the
same reason (no adapter-side hook), and both disappear under composition.
Recorded per house style rather than silently fixed in the plan.

---

## Reproducing the current refusal

A **real** cardiacCore case was required and one was available at
`/Users/simaocastro/cardiacCore-local-cases/bivCase_Pig_Morphometric_Tree` —
a previously-executed native cardiacCore case (real anatomy, UVC, fibre and
Purkinje-tree fields under `0/`, real `Allrun`/dict files, `postProcessing/`
output from an actual run). No case was invented. It was copied into the
session scratchpad before any `--apply` run, so a mutating override never
touches the user's original directory; the copy is discarded with everything
else this spike produced.

Built environments (per `CLAUDE.md`'s recipe, already present this session):
`/tmp/od311` (all four packages, editable).

```bash
$ /tmp/od311/bin/python -m omnidriver step --plugin cardiaccore \
    --entry-kind case_folder --entry <the copied case> \
    --step run --strict --apply /tmp/overrides.json
```

```json
{
  "status": "failed",
  "entry": "<the copied case>",
  "step": "run",
  "error": "candidate rejected: the selected adapter does not implement override target declaration"
}
```

That exact message — `"the selected adapter does not implement override
target declaration"`, raised by
`omnidriver.core.compatibility.legacy_override_target_paths` — disappearing
under composition is the test. (`--plugin cardiaccore --entry-kind
case_folder --entry <path>` was needed because `CardiacCorePlugin` declares
no `has_case_marker`; the resolver falls back to `_has_entrypoint`, which
looks for the case's declared entrypoint relpath — `Allrun` for this plugin's
`CaseRuntimeConventions` — so only case folders that actually carry an
`Allrun` resolve as runnable. Two of the eight local cases do; the other six
lack a run script and were not used.)

---

## What could and could not be measured end-to-end, and why

The criterion's literal wording — `step --strict --apply` **succeeds** — was
only partially reachable in this environment, for a reason unrelated to
composition: `Allrun` on this case shells out to a native cardiacCore build
(`run_cardiac_core_case.sh`) that does not exist in this sandbox. No
prototype, however correct, can make an uncompiled native solver execute.
This is the blocker the task anticipated; the honest substitute it names —
"driving the four capability calls directly through a composed context" —
was used *in addition to*, not instead of, the CLI reproduction, because a
real case was in fact available:

1. **Full CLI**, both prototypes: the specific refusal
   (`"the selected adapter does not implement override target
   declaration"`) is gone under composition. The command instead reaches
   real execution and fails there, with a *different, unrelated* error:
   `Allrun: line 6: .../run_cardiac_core_case.sh: No such file or directory`.
   This is evidence the composition layer resolved cleanly and handed off to
   the real `Allrun` step — the thing Task 15 is measuring — and that the
   remaining failure is an execution-environment gap, not a mechanism defect.
2. **Direct capability calls**, both prototypes, against the same real case
   copy: `context.capabilities.override_scopes.{target_paths, apply,
   inspect, scopes}()` were called directly (no native binary on this path;
   `apply_overrides`/`get_override_target_paths` never invoke the solver,
   only OpenFOAM's own dictionary mutator). This is the cleanest measurement
   of the actual thing under test, and it is unambiguous:
   - Against the **uncomposed** context (`CardiacCorePlugin` alone):
     `target_paths()` raises the same `"the selected adapter does not
     implement override target declaration"`.
   - Against the **composed** context (`CardiacCorePlugin` +
     `OpenFOAMEnvironmentPlugin`): `target_paths()` resolves a real path,
     `apply()` writes a real value into `system/setCardiacAnatomyDict` on
     disk (verified by re-reading the file), `inspect()` returns real
     `foamDictionary`-backed evidence, `scopes()` returns OpenFOAM's
     declared scopes. **Zero new code in `omnidriver-cardiaccore`** in
     either prototype (confirmed by `git diff --stat -- packages/omnidriver-cardiaccore`
     showing no changes on either branch).

Verdict: **both prototypes meet the criterion** as far as this environment
can exercise it. Neither can be driven to a literal process exit 0 without a
compiled native cardiacCore, which no mechanism choice changes.

---

## Prototype A — own it (`spike/composition-own`, deleted)

Built in an isolated `git worktree` at `/tmp/od_spike/composition-own`
(branch `spike/composition-own`, based on `71897f9`), with its own venv
(`/tmp/od_spike/venv-own`), so the session's pre-existing uncommitted changes
in the main working tree were never touched or carried across.

**Changes** (`git diff --numstat` against `71897f9`):

| file | + | - |
|---|---|---|
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | 30 | 1 |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | 118 | 2 |
| `packages/omnidriver/src/omnidriver/cli.py` | 21 | 0 |
| **`packages/omnidriver-cardiaccore/`** | **0** | **0** |

**What was built**, only as far as the criterion needs (not all 24
capabilities, not all six §4.3 rules):

- `DriverContext.providers: tuple[SolverPlugin, ...] = ()` — additive field,
  default-empty so every existing single-plugin context is unaffected.
- `plugin_interface.composed_driver_context(plugin, *, providers, source)` —
  builds a context the existing way, then reattaches `providers`. Identity
  (the capability digest) is **not** extended to cover the stack — spec
  §4.4's stack digest was explicitly out of scope for this spike, and this
  is recorded as a known gap, not a silent omission.
- `plugin_capabilities.adapt_plugin_capabilities(plugin, *, providers=())` —
  when `providers` is non-empty, only `override_scopes` is composed; every
  other capability still reads `plugin` alone. This is the "implement only
  as much as the criterion needs" instruction taken literally.
- `_ComposedOverrideScopeAdapter(stack)` implementing the four
  `OverrideScopeCapability` members by hand over `stack = (plugin,) +
  providers`:
  - `apply_overrides` / `get_override_target_paths` (tier
    `optional-refusing`): the **refusing-hook rule** — exactly one provider
    in the stack may implement the member; two raises a composition-conflict
    `ValueError` naming both provider ids (verified directly: registering a
    second fake provider that also implements `apply_overrides` raises
    correctly); zero falls through to the existing `legacy_*` refusal.
  - `get_override_scopes` (tier `optional-neutral`): unioned across every
    provider that implements it (closest of the six rows is "set", though
    this member does not cleanly match any row — see Findings below).
  - `inspect_effective_configuration` (tier `optional-neutral`): treated as
    the **diagnostics rule** — concatenate every implementing provider's
    results, in stack order.
- A hardcoded, clearly-marked prototype hack in `cli.py`'s plugin-loading
  block: when the selected plugin's id is `org.omnidriver.cardiaccore`, look
  up the installed `openfoam-environment` plugin and compose it in. This is
  **not** spec §4.1/§4.2's declared mechanism (`plugin.yaml`'s
  `requires:`/`provides:` and a topological sort) — building that was out of
  scope for a mechanism spike focused on §4.3's composition semantics, not
  on ordering/discovery. See Findings for what this hack exposed.

**Rules from spec §4.3 actually exercised:** 2 of 6 — "refusing hooks"
(the one the criterion is about) and "diagnostics" (for `inspect`). "set",
"map", "single value", and "case-file rules" were not exercised; nothing in
this capability's four members calls for them.

**What broke** (`pytest packages/omnidriver/tests -q`, `842 passed` `2
failed` `83 skipped`, ignoring one wheel-shape failure explained below):

1. `test_plugin_capabilities.py::test_context_exposes_focused_adapters_without_replacing_public_plugin`
   — asserts `DriverContext` has exactly the fields `["plugin",
   "identity"]`. Adding `providers` is precisely the shape change this guard
   exists to catch. A real Phase 1 change updates this guard's expected
   field list deliberately; a spike does not get to do that quietly, so it
   is reported as broken rather than patched.
2. `test_plugin_dependency_boundary.py::test_production_consumers_do_not_bypass_capability_bundle`
   — the guard `CLAUDE.md` names ("no production module in core may touch
   `driver_context.plugin` directly"). The prototype hack in `cli.py` reads
   `driver_context.plugin.plugin_id` to decide whether to compose, and trips
   it. **This was not weakened or skipped** (Global Constraints forbid
   that); it is left failing and reported as a genuine design finding below.

(A third failure, `test_wheel_install_imports.py::test_every_core_module_imports_from_a_wheel`,
is a sandbox artifact — it shells out to build a nested venv via `ensurepip`
and that subprocess `SIGABRT`s in this environment on both prototype
branches and was not investigated further; it is not a consequence of either
mechanism.)

`scripts/check-import-boundaries.py` and `scripts/export-capability-seams.py
--check` both exit 0 on this branch.

---

## Prototype B — pluggy (`spike/composition-pluggy`, deleted)

Same worktree isolation (`/tmp/od_spike/composition-pluggy`, venv
`/tmp/od_spike/venv-pluggy`), same base commit, same case, same measurement
procedure — everything held constant except the mechanism.

**pluggy's current API was verified from its own documentation**
(`https://pluggy.readthedocs.io/en/stable/`, pluggy `1.6.0`, the version `uv`
resolved), not from memory or from spec §4.6's summary of it:

- `@hookspec(firstresult=True)` makes a hook call return only the first
  non-`None` result; without it, `PluginManager.hook.<name>(**kwargs)`
  returns a **list** of every non-`None` result, in **LIFO registration
  order** (last-registered plugin's implementation runs, and appears in the
  result, first).
- Hooks are called with keyword arguments only.
- `@hookimpl(tryfirst=True|trylast=True)` order within that list;
  `@hookimpl(wrapper=True)` (pluggy ≥1.1) is a generator-based wrapper around
  every non-wrapper implementation. None of these were needed for this
  spike's one composed capability.
- `PluginManager.register(namespace)` registers a plugin object or module;
  its methods must carry `@hookimpl` to be picked up.

**The load-bearing finding: pluggy has no "exactly one implementation, else
error" arity.** `firstresult=True` returns the first non-`None` result and
silently discards how many providers answered — the opposite of what spec
§4.3's refusing-hook row requires (two implementations is an *error*, not a
silent pick). Not setting `firstresult` gets the full list back, but then
**this module counts non-`None` results itself** and raises the same
`ValueError` Prototype A raises by hand (see `_exactly_one` in
`pluggy_composition.py`). Adopting pluggy did not remove this logic; it
relocated it next to a second problem pluggy introduces on its own: to know
*which* provider produced *which* result for the composition-conflict error
message, the plain result list has to be correlated back to the provider
stack by re-probing with `getattr` — exactly the duplication a mechanism
adoption should have removed, not introduced.

**Changes** (`git diff --numstat` against `71897f9`):

| file | + | - |
|---|---|---|
| `packages/omnidriver/pyproject.toml` | 4 | 0 |
| `packages/omnidriver/src/omnidriver/cli.py` | 19 | 0 |
| `packages/omnidriver/src/omnidriver/core/pluggy_composition.py` (new) | 227 | 0 |
| `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` | 17 | 2 |
| `packages/omnidriver/src/omnidriver/core/plugin_interface.py` | 24 | 1 |
| **`packages/omnidriver-cardiaccore/`** | **0** | **0** |

291 insertions / 3 deletions across 5 files, versus Prototype A's 169 / 3
across 3 files — **72% more code for the same subset of the same
capability**, almost all of it in the new `pluggy_composition.py`
(hookspecs, a per-provider `_ProviderShim` because neither
`CardiacCorePlugin` nor `OpenFOAMEnvironmentPlugin` carries `@hookimpl` and
neither package may be touched, and the hand-rolled arity check above). Zero
changes in `omnidriver-cardiaccore`, same as Prototype A. A runtime
dependency (`pluggy>=1.6`) was added to a core package that `CLAUDE.md`
states "has nearly none" — the same cost the spec named in advance.

**The same "exactly one" conflict check was verified to raise identically**
to Prototype A, word for word (registering a duplicate fake provider).

**`capability_seams.parse_fields` and the generated seam table.** This
prototype did **not** delete or rewrite `OverrideScopeCapability` — the
`Protocol` class and its `:adapts:`/`:consumed-by:`/`:fallback:`/`:status:`
docstring fields are untouched; only the private adapter behind it changed
(swapped for `PluggyOverrideScopeAdapter`, built on pluggy, when a stack is
present). `capability_seams.collect_seams()` reads
`PluginCapabilities.__annotations__` and the named `Protocol` classes' own
docstrings — it never inspects the adapters at all. Consequently
`scripts/export-capability-seams.py --check` **exits 0 unchanged** on this
branch, and `ARCHITECTURE.md`'s table is untouched.

This is a **narrower and more precise finding than spec §4.6's stated cost**
("rewriting 24 Protocols as hookspecs, and losing the seam table in its
present form"). The seam table survives pluggy adoption *as long as the
Protocols stay the documented contract* and pluggy is used only to
*implement* the adapters behind them — exactly what this prototype did. The
spec's cost is real only under the more aggressive version of "adopt
pluggy" — deleting the Protocols and making `hookspec`-decorated functions
the sole declared contract — which was not necessary to satisfy this
criterion and was not built. If Phase 1 chooses pluggy, keeping the
Protocols as the documented seam and pluggy as a private dispatch detail
avoids this cost entirely; that option was not visible before this spike
measured it.

Same two tests broke, for the same reasons, as Prototype A (`git diff` on
`cli.py`'s hack is byte-for-byte identical between branches).
`scripts/check-import-boundaries.py` exits 0.

---

## Comparison

| | A: own it | B: pluggy |
|---|---|---|
| Criterion met (capability-level, real case) | yes | yes |
| Criterion met (full CLI, same real case) | refusal gone; blocked on missing native binary (environment, not mechanism) | identical |
| Lines changed | 169 / 3, 3 files | 291 / 3, 5 files |
| Changes in `omnidriver-cardiaccore` | 0 | 0 |
| New runtime dependency | none | `pluggy>=1.6` |
| §4.3 rules exercised | 2 of 6 (refusing, diagnostics) | same 2 of 6 |
| "Exactly one" arity | hand-written, ~15 lines | hand-written, ~20 lines (pluggy does not provide it) |
| Seam table (`export-capability-seams.py --check`) | unaffected | unaffected, **if** Protocols are kept as documentation |
| Existing guards broken | 2 (same 2) | 2 (same 2) |
| Import boundaries | clean | clean |

---

## Recommendation

**Own it.** Prototype A satisfies the criterion with less code, no new
runtime dependency, and no loss of the generated seam table, and it
exercises spec §4.3's rules exactly as directly as Prototype B does — pluggy
added a dependency and 122 more lines without buying a single rule this
capability needed for free. The one rule where a mature plugin manager could
plausibly have paid for itself — "exactly one implementation, else error"
for a refusing hook — is not a rule pluggy expresses; both prototypes
implement it by hand, so the deciding advantage the spec's §4.6 imagined
(pluggy having "already resolved this arity question") did not materialize
for the specific rule this codebase actually needs. `firstresult=True`
resolves a *different* arity question (silently pick one), which is not the
same as ("error if more than one").

This recommendation is scoped to what was measured: one capability, four
members, two of six composition rules. It should be revisited if Phase 1's
full 24-capability rollout exercises the "map merge with explicit override"
or "case-file exactly-one-declarer" rules in ways this spike did not probe —
those are the rows most likely to reward a library's conflict-tracking
machinery, and neither prototype touched them.

---

## Findings for spec §4.3 (and adjacent) that the prototyping surfaced

1. **`get_override_scopes` does not fit any of the six rows.** It is tagged
   `optional-neutral` (not "refusing"), but it is not a "single value"
   either (a capability may sensibly declare zero, one, or several scopes),
   not a "map" (scopes are not keyed by a shared name a duplicate could
   collide on), and not quite "diagnostics" (diagnostics are inherently
   order-independent facts; scopes are addressable contract surface a
   caller resolves by token). Both prototypes treated it as an ad hoc
   set-union. Phase 1 should either add a seventh row for
   "declare-only, union, name collision is only an error if two providers
   claim the *same token*" (not implemented or tested here), or fold it
   explicitly into the "set" row and say so.
2. **The crash-safety check ("plugin implements `apply_overrides` but not
   `get_override_target_paths`") needs restating for a stack.** Spec §4.3
   describes the refusing-hook rule per member, independently. But the
   existing single-plugin crash-safety check ("a plugin that writes without
   declaring what it touched is a data-loss risk") is a **cross-member**
   invariant, not a per-member rule, and composition does not automatically
   preserve it — a stack could plausibly have provider X supply
   `apply_overrides` and provider Y supply `get_override_target_paths`,
   satisfying "exactly one" for each member individually while nothing
   guarantees the *same* provider's mutator is what the declared targets
   describe. Both prototypes reimplemented the original single-plugin check
   (raise if the `apply_overrides` winner has no `target_paths` winner) but
   did not verify the more general N-provider case, because the criterion's
   stack has depth two. This should be named explicitly in §4.3 as a
   cross-member constraint, not left implicit in each mechanism's
   implementation.
3. **pluggy's `firstresult` is not a substitute for "exactly one, else
   error."** Recorded in detail above; stated here because spec §4.6's
   framing ("pluggy... has already resolved this arity question") reads as
   settling the refusing-hook row in pluggy's favor, and prototyping showed
   it does not.
4. **The declared-vs-discovered provider-selection wiring belongs inside
   `plugin_interface.py`/`plugin_discovery.py`, not in `cli.py`.** Both
   prototypes' CLI glue hack trips `test_plugin_dependency_boundary`
   because it reads `driver_context.plugin.plugin_id` from `cli.py`, which
   that guard exempts only for `plugin_interface.py` and
   `plugin_capabilities.py`. This is a real constraint Phase 1's actual
   `plugin.yaml` `requires:`/`provides:` reader (spec §4.1/§4.2) must
   satisfy by living inside the exempted modules — a fact this spike's
   deliberately-crude hack surfaced by violating it, which a from-scratch
   design might not have noticed until integration.
5. **Spec §4.4's stack digest is untested by this spike.** Both prototypes
   compute identity from the primary plugin alone, as stated up front. This
   spike answers the mechanism question only; it does not validate §4.4.

---

## Cleanup

- Both worktrees (`/tmp/od_spike/composition-own`,
  `/tmp/od_spike/composition-pluggy`) and their venvs
  (`/tmp/od_spike/venv-own`, `/tmp/od_spike/venv-pluggy`) were removed via
  `git worktree remove`, after which both branches
  (`spike/composition-own`, `spike/composition-pluggy`) were deleted with
  `git branch -D`. Neither branch was pushed or merged.
- The copied case directories used for real-file mutation testing
  (`spike-case`, `spike-case-b`, `spike-case-b-cli`) live only under this
  session's scratchpad, never under the original
  `/Users/simaocastro/cardiacCore-local-cases/`, which was never written to.
- This spike touched only files inside the two throwaway worktrees plus this
  document in the main working tree. The pre-existing uncommitted changes
  present in the main working tree before this task started (`.github/workflows/ci.yml`,
  `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py`,
  `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/run_config.py`,
  `packages/omnidriver-cardiacfoam/tests/test_all_packages_wheel_install.py`,
  `packages/omnidriver/tests/core/test_trust_boundary_end_to_end.py`, and the
  untracked `packages/omnidriver-cardiaccore/tests/test_validate_configuration.py`
  and `packages/omnidriver/tests/fixtures/`) were never staged, committed, or
  otherwise touched by this task, and remain exactly as they were.
