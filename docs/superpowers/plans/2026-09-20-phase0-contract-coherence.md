# Phase 0: Contract Coherence — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the omnidriver plugin contract state each fact exactly once, so that the provider stack in Phase 1 can be built on a contract where "required" is not decided twice.

**Architecture:** The 24 capability Protocols in `core/plugin_capabilities.py` already carry a `:status:` docstring field that `core/capability_seams.py` parses and renders into `ARCHITECTURE.md`. Phase 0 makes that field the single declaration of a member's enforcement tier — `required`, `optional-neutral`, `optional-refusing` — and adds a guard that the three sources which currently disagree (`_REQUIRED_PLUGIN_MEMBERS`, the Protocol bodies, `compatibility.py`) agree with it. Everything else in this plan is either a duplicate intake collapsed, or a defect the audits found in passing.

**Tech Stack:** Python 3.11+ (floor; CI matrixes 3.11/3.12/3.13), pytest, `uv` for environments, `yaml`, `jsonschema`. No new runtime dependency is added by this plan.

**Source spec:** `docs/superpowers/specs/2026-09-20-provider-composition-design.md` §3 and §3.4.

## Global Constraints

- Python floor is **3.11**. Annotations must stay lazy (`from __future__ import annotations`) in `plugin_interface.py` — several annotations there name types imported only under `TYPE_CHECKING`, and evaluating them eagerly raises `NameError` on 3.11/3.12.
- `omnidriver.core` MUST NOT import from `omnidriver.openfoam`, `omnidriver.cardiacfoam`, or `omnidriver.cardiaccore`. `scripts/check-import-boundaries.py` enforces this and **its waiver list must stay empty**.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- No production module in core may touch `driver_context.plugin` directly; go through `driver_context.capabilities`. Guarded by `test_plugin_dependency_boundary.py`.
- Do not weaken or skip an existing guard to make a change pass. If a guard fails, fix the cause.
- **The `Files:` block is authoritative for what to commit, not the per-step `git add` list.** Those lists were written before the tasks ran and have been stale three times (Phase 0 Tasks 1, 4 and 6). Commit every file the task actually changed; if that differs from the `Files:` block, say so in the report.
- Do not quote test-suite totals in any code comment, docstring or document. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number in comments and docstrings.
- When correcting a claim in a document, record the correction with a date rather than silently overwriting.
- There is no `LICENSE` file and no `license` field in any `pyproject.toml`. Do not add one.
- After every source change, rebuild the wheel before running the wheel-shape suite, or it tests stale code.

## Status

| task | state | commit |
|---|---|---|
| 1 · `:status:` becomes the tier vocabulary | done | `078e125` |
| 2 · tier coherence guard | done | `7761f68` |
| 3 · split the `dictionaries` tier | done (rewritten mid-flight) | `5ce023f` |
| 4 · derive `_REQUIRED_PLUGIN_MEMBERS` (27 → 14) | done | `1f4359c` |
| 5 · correct the contract's docstrings | done | `f321940` |
| 6 · `get_dict_entries` + controlDict reader | done (amended mid-flight) | `9d2c7f0` |
| 7 · close the MPI authorization hole | done | `c7f0c7e` |
| 8 · stop discarding records and contexts | done | `5c1eb68` |
| 9 · `ConfigValueCapability` | done | `c8c5581` |
| 10 · one diagnostic shape | done | `d3f0d9d` |
| 11 · cardiacCore declaration hygiene | done | `07a71b2` |
| 12 · caching (prerequisite for Phase 1's digest) | done | `41056a4` |
| 13 · the three remaining §3.3 defects | done | `43bd487` |
| 14 · all four shapes, close-out | done | no commit needed |
| 15 · the composition-mechanism spike | done | `57d4d3a` |

**Phase 0 is COMPLETE.** Every task passes `0 failed` in all four
verification shapes; Task 14 re-verified the whole phase from a rebuilt wheel.

**Deliverables produced so far that later phases consume:**
- Task 4's Step 4b stub census → recorded in Phase 1 Task 9.
- Task 9's `config_value` divergence report → recorded in Phase 1 Task 9.

## How to execute a task in this plan

Learned from Phase 0 Tasks 1–10, each of which found something the plan had
wrong. Read this before starting any task.

**Protect the working tree.** Never `git add` a file that already had
uncommitted changes before your task started. Run `git status` first and treat
every pre-existing modification as someone else's work in progress. If your
change genuinely requires touching such a file, make the edit, leave it
**unstaged**, and say so in your report. This rule exists because a task
committed a pre-existing WIP file along with its own work, and the two could
not be separated afterwards.

**Verify every factual claim before acting on it.** The claims in these tasks
come from audits, not from measurement at execution time. Several have been
wrong. The contract's own docstrings have been wrong six times — two hook
counts, a constant defined in no module, a member count, a `-> None`
annotation on a function that always returned records, and a heading naming a
Protocol that was never written. Verify, then act.

**"Expected: PASS" has been wrong twice.** A correct fix can expose a real gap
downstream. When that happens, do not narrow the fix and do not weaken a test.
Investigate the gap, decide the remedy on evidence, and report. Task 6 is the
worked example: fixing `get_dict_entries` revealed that `config["solver"]`
never recorded what the run used, and the remedy was to add the missing reader,
not to relax the requirement.

**Fixture and helper names in these snippets are illustrative.** Check what
already exists in the target test file and its conftest before adding one.
Duplicating a fixture is the defect class this work exists to remove. Known
trap: `plugin_discovery.discover_plugins()` returns `EntryPoint` objects, not
plugin classes — use `load_discovered_plugin(name)`, which loads and builds a
context correctly. Two tasks hit this.

**A test may encode a defect as intended behaviour.** One did, in a file named
`test_workflow_command_security.py`, complete with a comment explaining the
hole as a design choice. When you find one: correct it with a dated note **and
add a test for the corrected behaviour**, so coverage grows rather than moves.

**The `Files:` block is authoritative for what to commit, not the per-step
`git add` list.** Those lists were written before the tasks ran and have been
stale three times. Commit what you actually changed, and report any divergence
from the `Files:` block.

**Report being wrong as a finding.** A plan that turns out to mis-describe the
codebase is information, not a failure. Say so plainly rather than working
around it silently.

---

## Verification shapes

Every task's "run the tests" step means at minimum the targeted test. Before each **commit** step, also run:

```bash
python -m pytest packages/ -q -m "not slow"
```

Before the final commit of each task group, run all four shapes per `CLAUDE.md`:

```bash
python -m pytest packages/ -q -m "not slow"
python -m pytest packages/omnidriver/tests -q
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
```

The environments `/tmp/od311` and `/tmp/odcore` are built once per `CLAUDE.md`'s recipe; they are not in the repo.

---

## File Structure

**Core — modified:**
- `packages/omnidriver/src/omnidriver/core/capability_seams.py` — gains tier vocabulary validation; `:status:` becomes the single tier declaration.
- `packages/omnidriver/src/omnidriver/core/plugin_interface.py` — `_REQUIRED_PLUGIN_MEMBERS` derived from tiers rather than hand-maintained; docstring corrections.
- `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` — nine dead probes replaced by unconditional calls; `_OverrideScopeAdapter.apply` return value; `extra_provenance_paths` annotation; new `ConfigValueCapability`.
- `packages/omnidriver/src/omnidriver/core/compatibility.py` — nine unreachable `legacy_*` deleted.
- `packages/omnidriver/src/omnidriver/core/runtime/workflow.py` — `validate_workflow_commands` unwraps MPI payloads.
- `packages/omnidriver/src/omnidriver/core/tutorial_contracts.py` — five always-empty reception slots removed.
- `packages/omnidriver/src/omnidriver/core/specs/validation.py`, `specs/validation_types.py`, `runtime/run_document_exec.py`, `runtime/run_document_adapter.py`, `cli.py` — one diagnostic shape.
- `scripts/export-capability-seams.py` — enforces the tier vocabulary, not only the table's freshness.

**Core — created:**
- `packages/omnidriver/tests/core/test_contract_tier_coherence.py` — the tier guard.
- `packages/omnidriver/tests/core/test_capability_calls_are_cheap.py` — the caching guard Phase 1's digest depends on.
- `packages/omnidriver-cardiaccore/tests/test_profile_matches_catalog.py` — profile and catalogue agree.

**Adapters — modified:**
- `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` — `get_dict_entries` completeness.
- `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py` — stop self-re-contexting.
- `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml` — missing dictionary rules.
- `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/inputs.py` — orphan constants deleted.

**Docs — modified:**
- `ARCHITECTURE.md` — regenerated seam table (never edited by hand).

---

## Task 1: Make `:status:` the tier vocabulary

The `:status:` field already exists on every capability Protocol docstring and is parsed by `capability_seams.parse_fields`. Today its values are free text — `mandatory`, `optional`, `mixed`. This task closes the vocabulary to three tiers and makes an unknown value a hard failure.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/capability_seams.py`
- Test: `packages/omnidriver/tests/core/test_capability_seam_documentation.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `capability_seams.TIERS: frozenset[str]` with members `{"required", "optional-neutral", "optional-refusing"}`; `capability_seams.validate_tiers(seams) -> list[str]` returning human-readable problems, empty when clean.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_capability_seam_documentation.py`:

```python
def test_every_seam_declares_a_known_tier():
    """:status: is the single declaration of a member's enforcement tier.

    Free text here is how the contract came to say `mandatory` in one place
    and probe with getattr in another.
    """
    from omnidriver.core import capability_seams

    seams = capability_seams.collect_seams()
    unknown = [
        (seam.field, seam.status)
        for seam in seams
        if seam.status not in capability_seams.TIERS
    ]
    assert unknown == [], (
        "capability seams declare a :status: outside the tier vocabulary "
        f"{sorted(capability_seams.TIERS)}: {unknown}"
    )


def test_validate_tiers_rejects_an_unknown_status():
    from omnidriver.core import capability_seams

    class _Seam:
        field = "made_up"
        status = "sort-of-optional"

    problems = capability_seams.validate_tiers([_Seam()])
    assert len(problems) == 1
    assert "made_up" in problems[0]
    assert "sort-of-optional" in problems[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -k tier -v
```

Expected: FAIL — `AttributeError: module 'omnidriver.core.capability_seams' has no attribute 'TIERS'`.

- [ ] **Step 3: Add the vocabulary and validator**

In `capability_seams.py`, below the existing `Seam` dataclass:

```python
#: The enforcement tier a capability member sits in. Exactly one per member.
#:
#: ``required``          -- ``validate_plugin`` rejects absence; NO fallback
#:                          may exist; the adapter calls unconditionally.
#: ``optional-neutral``  -- probed; the named fallback returns a documented
#:                          neutral value (``False``, ``{}``, ``()``).
#: ``optional-refusing`` -- probed; the named fallback RAISES, naming the hook.
#:                          Correct where a neutral answer would silently
#:                          produce the wrong result rather than no result.
#:
#: Added 2026-09-20. Before this, ``:status:`` was free text and carried
#: ``mandatory``/``optional``/``mixed``, while ``_REQUIRED_PLUGIN_MEMBERS``
#: separately decided enforcement -- so fifteen members were both enforced and
#: probed, and nine ``legacy_*`` fallbacks were unreachable in production.
TIERS: frozenset[str] = frozenset({
    "required",
    "optional-neutral",
    "optional-refusing",
})


def validate_tiers(seams) -> list[str]:
    """Return one problem string per seam whose ``:status:`` is not a tier."""
    return [
        f"capability {seam.field!r} declares :status: {seam.status!r}, "
        f"which is not one of {sorted(TIERS)}"
        for seam in seams
        if seam.status not in TIERS
    ]
```

- [ ] **Step 4: Run the test to verify `validate_tiers` passes and the vocabulary test still fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -k tier -v
```

Expected: `test_validate_tiers_rejects_an_unknown_status` PASSES; `test_every_seam_declares_a_known_tier` still FAILS, listing every seam whose `:status:` is `mandatory`, `optional` or `mixed`.

- [ ] **Step 5: Retag every capability Protocol's `:status:`**

Read each Protocol docstring in `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py` and rewrite its `:status:` line using this mapping. Do **not** guess — for each capability, check whether its adapter probes with `getattr` and whether `compatibility.py` has a `legacy_*` for it.

| current `:status:` | adapter behaviour | new tier |
|---|---|---|
| `mandatory` | calls unconditionally, no `legacy_*` | `required` |
| `mandatory` | probes with `getattr`, has a `legacy_*` | `required` — the probe is dead; Task 3 removes it |
| `optional` | probes, `legacy_*` returns a neutral value | `optional-neutral` |
| `optional` | probes, `legacy_*` raises | `optional-refusing` |
| `mixed` | split the capability's members; if members genuinely differ, the `:status:` line lists each member and its tier | as determined |

`case_files` is the one currently marked `mixed`: `get_profile` is required, `get_config_resolution_description` is `optional-neutral`. Write that as two entries on the `:status:` line.

The two capabilities whose fallbacks raise are `sweep_materializer` (`legacy_route_sweep_case`, `legacy_materialize_sweep_case`) and the applying half of `override_scopes` (`legacy_apply_overrides`, `legacy_override_target_paths`). Those are `optional-refusing`.

- [ ] **Step 6: Run the test to verify it passes**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -k tier -v
```

Expected: both PASS.

- [ ] **Step 7: Regenerate the seam table**

```bash
python3 scripts/export-capability-seams.py
python3 scripts/export-capability-seams.py --check
```

Expected: the second command exits 0. `ARCHITECTURE.md`'s generated block now shows tier values in its `status` column. Never hand-edit that block.

Then wire `validate_tiers` into that script so the vocabulary is enforced outside the test suite too. In `scripts/export-capability-seams.py`, before rendering:

```python
    problems = capability_seams.validate_tiers(seams)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        raise SystemExit(1)
```

Re-run both commands; `--check` must still exit 0.

- [ ] **Step 8: Run the full suite and commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/capability_seams.py \
        packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/tests/core/test_capability_seam_documentation.py \
        ARCHITECTURE.md
git commit -m "feat(core): :status: becomes the single enforcement-tier declaration"
```

---

## Task 2: The tier coherence guard

**Files:**
- Create: `packages/omnidriver/tests/core/test_contract_tier_coherence.py`
- Modify: `packages/omnidriver/src/omnidriver/core/capability_seams.py`

**Interfaces:**
- Consumes: `capability_seams.TIERS`, `capability_seams.collect_seams()` (Task 1).
- Produces: `capability_seams.members_by_tier() -> dict[str, frozenset[str]]`, mapping each tier to the contract member names declared at it. Task 3 and Task 4 both consume this.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_contract_tier_coherence.py`:

```python
"""The contract must state each member's enforcement tier exactly once.

Before 2026-09-20 three sources disagreed: `_REQUIRED_PLUGIN_MEMBERS` named
27 members, the `SolverPlugin` Protocol body declared 29, and the capability
adapters probed 15 of the required ones with `getattr` anyway -- which made
nine `legacy_*` fallbacks unreachable while the generated seam table still
advertised them.
"""

from omnidriver.core import capability_seams
from omnidriver.core import plugin_interface


def test_every_member_sits_in_exactly_one_tier():
    by_tier = capability_seams.members_by_tier()
    seen: dict[str, list[str]] = {}
    for tier, members in by_tier.items():
        for member in members:
            seen.setdefault(member, []).append(tier)
    duplicated = {m: t for m, t in seen.items() if len(t) > 1}
    assert duplicated == {}, f"members declared at more than one tier: {duplicated}"


def test_no_required_member_has_a_fallback():
    """A `required` member cannot be absent, so a fallback for it is dead code.

    This is the assertion that keeps `test_fallback_census` honest: a census
    of fallbacks that can never fire measures nothing.
    """
    from omnidriver.core import compatibility

    required = capability_seams.members_by_tier()["required"]
    offenders = sorted(
        name for name in required
        if hasattr(compatibility, f"legacy_{name.removeprefix('get_')}")
    )
    assert offenders == [], (
        "these members are required, so their fallbacks are unreachable: "
        f"{offenders}"
    )


def test_required_tier_matches_the_validator():
    """`_REQUIRED_PLUGIN_MEMBERS` must be derived from the tiers, not parallel."""
    required = capability_seams.members_by_tier()["required"]
    declared = set(plugin_interface._REQUIRED_PLUGIN_MEMBERS)
    identity_members = {
        "plugin_name", "plugin_id", "plugin_version", "plugin_api_version",
    }
    assert declared - identity_members == set(required), (
        "the validator's required set and the seam tiers disagree; "
        f"validator-only={sorted(declared - identity_members - set(required))} "
        f"tier-only={sorted(set(required) - declared)}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
```

Expected: FAIL — `AttributeError: module 'omnidriver.core.capability_seams' has no attribute 'members_by_tier'`.

- [ ] **Step 3: Implement `members_by_tier`**

**Amended 2026-09-20, after Task 1 landed.** Task 1 added
`capability_seams.status_tiers(status)`, which parses a composite
`member=tier, member=tier` line but **discards the member name**, returning
tiers only. `members_by_tier` needs the member. Do NOT add a second parser
alongside it — that is the duplication this whole phase exists to remove.

Instead refactor to one parser with two views. Replace `status_tiers`'s body
so it derives from a new `status_map`, and add both to `capability_seams.py`:

```python
def status_map(status: str) -> dict[str, str]:
    """Parse a seam's raw ``:status:`` text into a member -> tier mapping.

    A single-tier line applies to every member the seam adapts, and is
    returned under the key ``"*"``. A capability whose members genuinely
    differ (``case_files``, ``override_scopes``) declares one ``member=tier``
    entry per member instead.

    The single parser behind both :func:`status_tiers`, which needs the tiers
    alone, and :func:`members_by_tier`, which needs the member each belongs
    to. Added 2026-09-20 when the second consumer appeared; ``status_tiers``
    previously parsed the text itself.
    """
    if "=" not in status:
        return {"*": status.strip()}
    parsed: dict[str, str] = {}
    for clause in status.split(","):
        member, _, tier = clause.partition("=")
        if member.strip():
            parsed[member.strip()] = tier.strip()
    return parsed


def status_tiers(status: str) -> tuple[str, ...]:
    """Extract the tier(s) a seam's raw ``:status:`` text declares.

    See :func:`status_map`, which does the parsing; this drops the member
    names so :func:`validate_tiers` can check both shapes the same way.
    """
    return tuple(status_map(status).values())


def members_by_tier() -> dict[str, frozenset[str]]:
    """Map each tier to the contract member names declared at it.

    Derived from the ``:adapts:`` and ``:status:`` fields of every capability
    Protocol, so the tiers and the seam table cannot drift: they are the same
    parse.
    """
    buckets: dict[str, set[str]] = {tier: set() for tier in TIERS}
    for seam in collect_seams():
        adapted = [name.strip() for name in seam.adapts.split(",") if name.strip()]
        per_member = status_map(seam.status)
        for member in adapted:
            tier = per_member.get(member, per_member.get("*"))
            if tier is None:
                raise ValueError(
                    f"capability {seam.field!r} adapts {member!r} but its "
                    f":status: names neither that member nor a single tier"
                )
            buckets[tier].add(member)
    return {tier: frozenset(members) for tier, members in buckets.items()}
```

Verify `status_tiers`'s existing behaviour is unchanged:

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -q
```

Expected: `0 failed`. If Task 1's tests break, `status_map` is not a faithful
refactor of what `status_tiers` did — fix `status_map`, not the tests.

- [ ] **Step 4: Run the test**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
```

Expected: `test_every_member_sits_in_exactly_one_tier` PASSES. The other two FAIL — that is correct, they are the defects Tasks 3 and 4 fix. Record the failure output; it is the worklist.

- [ ] **Step 5: Mark the two known-failing tests**

Add to the two failing tests, above each:

```python
import pytest

@pytest.mark.xfail(
    reason="fixed by Task 3 (delete unreachable fallbacks) and Task 4 "
           "(derive _REQUIRED_PLUGIN_MEMBERS from tiers); see "
           "docs/superpowers/plans/2026-09-20-phase0-contract-coherence.md",
    strict=True,
)
```

`strict=True` matters: when Task 3 and Task 4 land, an xfail that starts passing becomes a failure, which is what forces the marker to be removed rather than left behind.

- [ ] **Step 6: Run the test to verify all three pass or xfail**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
```

Expected: 1 passed, 2 xfailed.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/tests/core/test_contract_tier_coherence.py \
        packages/omnidriver/src/omnidriver/core/capability_seams.py
git commit -m "test(core): guard that each contract member has exactly one tier"
```

---

## Task 3: Split the `dictionaries` tier

**Rewritten 2026-09-20, after Task 2's guard ran.** This task previously said
"delete the nine unreachable fallbacks". That was the wrong remedy and is
recorded as such in the spec's §3.1. The nine fallbacks are unreachable, but
the fix is to demote their members (Task 4), not to make them mandatory for
every provider -- an environment provider has no solver commands, and
`OpenFOAMEnvironmentPlugin` carries hollow stubs for all nine purely to satisfy
`validate_plugin`.

Task 2's guard reported exactly one real offender: `get_phases` is tagged
`required` and has a `legacy_phases` fallback. It is tagged required only
because `dictionaries` was tagged wholesale, and `get_phases` is genuinely
optional -- `SolverPluginOptionalHooks` documents it as an optional hook and
`validate_plugin` does not require it.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Test: `packages/omnidriver/tests/core/test_contract_tier_coherence.py`

**Interfaces:**
- Consumes: `capability_seams.members_by_tier()` (Task 2).
- Produces: nothing new. `DictionaryCatalogCapability`'s `:status:` becomes per-member. No fallback is deleted by this task.

- [ ] **Step 1: Confirm `get_phases` is the only offender**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py::test_no_required_member_has_a_fallback -v --runxfail
```

Expected: FAIL reporting `['get_phases']` and nothing else. If it reports more,
stop and report -- the tier assignment moved since Task 2 and this task's
premise needs rechecking.

- [ ] **Step 2: Verify `get_phases` is genuinely optional**

```bash
python3 -c "
import re, pathlib
s = pathlib.Path('packages/omnidriver/src/omnidriver/core/plugin_interface.py').read_text()
names = re.findall(r'\"([a-z_]+)\"', re.search(r'_REQUIRED_PLUGIN_MEMBERS = \(([^)]*)\)', s, re.S).group(1))
print('get_phases required by validator:', 'get_phases' in names)
print('declared in SolverPluginOptionalHooks:', 'def get_phases' in s)
"
```

Expected: `False` then `True` — the validator does not require it and the
optional-hooks class documents it. Its `legacy_phases` fallback derives phases
from the plugin's own `DictEntry` values, so a plugin without it still works.

- [ ] **Step 3: Split the `:status:` line**

In `plugin_capabilities.py`, `DictionaryCatalogCapability`'s `:adapts:` names
`get_dict_entries, get_dict_groups, get_dictionary_catalog, get_phases`.
Replace its single `:status: required` with a per-member line, in the same
shape `case_files` and `override_scopes` already use:

```
    :status: get_dict_entries=required, get_dict_groups=required,
        get_dictionary_catalog=required, get_phases=optional-neutral
```

Check whether `capability_seams.parse_fields` handles a wrapped field — its
docstring notes the `:consumed-by:` list may wrap. If `:status:` may not wrap,
keep the line unwrapped rather than changing the parser in this task.

- [ ] **Step 4: Remove the xfail from the fallback test**

Delete the `@pytest.mark.xfail` decorator above
`test_no_required_member_has_a_fallback` in `test_contract_tier_coherence.py`.
Leave the one above `test_required_tier_matches_the_validator` — Task 4 removes
that.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -q
```

Expected: `test_no_required_member_has_a_fallback` PASSES, one xfail remains,
and Task 1's seam tests still pass.

- [ ] **Step 6: Regenerate the seam table and run everything**

```bash
python3 scripts/export-capability-seams.py
python3 scripts/export-capability-seams.py --check
python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
```

Expected: `0 failed`, both gates exit 0.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/tests/core/test_contract_tier_coherence.py \
        ARCHITECTURE.md
git commit -m "fix(core): get_phases is optional, and the dictionaries tier now says so"
```

---

## Task 4: Derive `_REQUIRED_PLUGIN_MEMBERS` from the tiers

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py`
- Test: `packages/omnidriver/tests/core/test_contract_tier_coherence.py`

**Interfaces:**
- Consumes: `capability_seams.members_by_tier()` (Task 2).
- Produces: `_REQUIRED_PLUGIN_MEMBERS` computed rather than literal; its value is unchanged for the four identity properties.

- [ ] **Step 1: Remove the xfail**

Delete the `@pytest.mark.xfail` decorator above `test_required_tier_matches_the_validator` in `test_contract_tier_coherence.py`.

- [ ] **Step 2: Run to confirm it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py::test_required_tier_matches_the_validator -v
```

Expected: FAIL, listing whichever names differ between the hand-maintained tuple and the tiers.

- [ ] **Step 3: Replace the literal tuple with a derivation**

In `plugin_interface.py`, replace the `_REQUIRED_PLUGIN_MEMBERS = (...)` literal with:

```python
#: Identity properties, which are strings rather than capability members and
#: therefore appear in no capability's ``:adapts:`` list.
_IDENTITY_MEMBERS = (
    "plugin_name",
    "plugin_id",
    "plugin_version",
    "plugin_api_version",
)


def _required_plugin_members() -> tuple[str, ...]:
    """The contract members ``validate_plugin`` rejects a plugin for lacking.

    Derived from the capability seams' ``:status:`` tiers rather than
    hand-maintained beside them. Before 2026-09-20 these were two independent
    lists and they disagreed: the tuple named 27 members while the
    ``SolverPlugin`` Protocol declared 29, and the two it omitted were exactly
    the environment ones.
    """
    from .capability_seams import members_by_tier

    return _IDENTITY_MEMBERS + tuple(sorted(members_by_tier()["required"]))


_REQUIRED_PLUGIN_MEMBERS = _required_plugin_members()
```

The import is function-local deliberately: `capability_seams` reads
`PluginCapabilities.__annotations__`, and importing it at module scope in
`plugin_interface` would create a cycle.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
python -m pytest packages/omnidriver/tests -q
```

Expected: all three tier tests PASS, no xfail remains, core suite `0 failed`.

- [ ] **Step 4b: Confirm demotion is behaviour-preserving**

Deriving the set **shrinks** it: thirteen members the validator currently
demands are tagged `optional-neutral`, so `validate_plugin` will stop rejecting
a provider that lacks them. That is the intended change -- it is what lets an
environment provider stop carrying hollow stubs -- but it must not alter what
any *installed* plugin does today.

For each demoted member, verify the shipped implementation returns what its
fallback would:

```bash
python3 - <<'CHECK'
from omnidriver.core import plugin_discovery
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core import compatibility

for name, cls in plugin_discovery.discover_plugins().items():
    plugin = cls()
    for member, fallback in [
        ("get_solver_commands", compatibility.legacy_solver_commands),
        ("get_auxiliary_commands", compatibility.legacy_auxiliary_commands),
        ("get_utility_manifests", compatibility.legacy_utility_manifests),
        ("get_utility_roots", compatibility.legacy_utility_roots),
        ("resolve_case_models", None),
        ("get_samplable_fields", None),
    ]:
        if fallback is None:
            continue
        own = getattr(plugin, member)()
        print(f"{name}.{member}: own={own!r} fallback={fallback(plugin)!r}")
CHECK
```

Record the output. Where a plugin's own value differs from the fallback, that
plugin genuinely implements the member and keeps doing so -- demotion changes
nothing for it. Where they are equal, the implementation was a stub and can be
deleted in Phase 1 Task 9.

- [ ] **Step 5: Run the whole matrix**

```bash
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`. If a plugin now fails `validate_plugin` for a member it did not implement, that is a **real finding** — the member was declared required by its seam and the plugin never implemented it. Implement it on that plugin; do not lower the tier to make the failure go away.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_interface.py \
        packages/omnidriver/tests/core/test_contract_tier_coherence.py
git commit -m "refactor(core): derive the required-member set from the seam tiers"
```

---

## Task 5: Correct the contract's own docstrings

Three claims in `plugin_interface.py` are false. Per house style, correct with a date rather than silently overwriting.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Verify each claim is false**

```bash
grep -c 'def ' <(sed -n '/class SolverPluginOptionalHooks/,/^class \|^_REQUIRED/p' \
  packages/omnidriver/src/omnidriver/core/plugin_interface.py)
grep -n '_REQUIRED_V2_MEMBERS' packages/omnidriver/src/omnidriver/core/plugin_interface.py
```

Expected: the hook count is 27, not 14 and not 15. `_REQUIRED_V2_MEMBERS` appears only inside a docstring — there is no definition.

- [ ] **Step 2: Fix the module docstring**

Replace `- :class:`SolverPluginOptionalHooks` — 14 probe-based optional hooks that` with:

```
- :class:`SolverPluginOptionalHooks` — the probe-based optional hooks that
```

Counting hooks in prose rots; the number was wrong in two places at once.

- [ ] **Step 3: Fix the class docstring**

In `SolverPluginOptionalHooks`, replace `**Why this class exists.** Until it did, these fifteen hooks appeared` with `**Why this class exists.** Until it did, these hooks appeared`.

- [ ] **Step 4: Fix the `_REQUIRED_V2_MEMBERS` reference**

Replace `` ``_REQUIRED_PLUGIN_MEMBERS`` or ``_REQUIRED_V2_MEMBERS``, so this class is `` with:

```
``_REQUIRED_PLUGIN_MEMBERS``, so this class is
```

Then add, at the end of that paragraph:

```
    **Corrected 2026-09-20:** this previously also named
    ``_REQUIRED_V2_MEMBERS``, a constant that exists in no module -- it was
    referenced only here. It named two hook counts, 14 and fifteen, where the
    class declares neither.
```

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver/tests -q
python -m pytest packages/omnidriver/tests/core/test_documentation_inventory_contracts.py -v
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_interface.py
git commit -m "docs(core): correct three false claims in the plugin contract"
```

---

## Task 6: `get_dict_entries()` must return the whole catalog

`CardiacFoamPlugin.get_dict_entries()` yields 162 entries; `get_dictionary_catalog().entries` yields 171. The nine missing are `CONTROL_DICT_ENTRIES` — `deltaT`, `endTime`, `startTime`, `startFrom`, `stopAt`, `writeControl`, `writeInterval`, `writeFormat`, `purgeWrite`. Consumers reaching through `capabilities.dictionaries.entries()` cannot see them; consumers reaching through `.catalog()` can.

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/run_document_config.py`
- Test: `packages/omnidriver/tests/core/test_dict_entries.py`
- Test: `packages/omnidriver/tests/conftest.py` (fixture)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new; `get_dict_entries()` and `get_dictionary_catalog().entries` agree.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_dict_entries.py`:

```python
def test_entries_and_catalog_agree(driver_context_for_installed_plugins):
    """One capability must not give two answers.

    `get_dict_entries()` and `get_dictionary_catalog().entries` are both
    `DictionaryCatalogCapability`. A consumer should not have to know which
    accessor sees the whole catalogue.
    """
    for context in driver_context_for_installed_plugins:
        dictionaries = context.capabilities.dictionaries
        flat = {entry.driver_path for entry in dictionaries.entries()}
        catalogued = {entry.driver_path for entry in dictionaries.catalog().entries}
        assert flat == catalogued, (
            f"{context.identity.id}: entries() and catalog() disagree; "
            f"missing from entries()={sorted(catalogued - flat)} "
            f"missing from catalog()={sorted(flat - catalogued)}"
        )
```

If `driver_context_for_installed_plugins` does not exist in `packages/omnidriver/tests/conftest.py`, add it there:

```python
@pytest.fixture
def driver_context_for_installed_plugins():
    """A DriverContext per discoverable plugin, skipping when none is installed."""
    from omnidriver.core import plugin_discovery
    from omnidriver.core.plugin_interface import driver_context

    discovered = plugin_discovery.discover_plugins()
    if not discovered:
        pytest.skip("no omnidriver.plugins entry points installed")
    return [
        driver_context(plugin_class(), source=f"test:{name}")
        for name, plugin_class in discovered.items()
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_dict_entries.py -k agree -v
```

Expected: FAIL for `org.cardiacfoam`, naming the nine `controlDict` paths as missing from `entries()`.

- [ ] **Step 3: Include `CONTROL_DICT_ENTRIES`**

In `cardiacfoam_plugin.py`, find `get_dict_entries` and add `CONTROL_DICT_ENTRIES` to the tuple it concatenates, importing it from `.common_dict_entries` the same way `PHYSICS_PROPERTY_ENTRIES` is imported in that method.

- [ ] **Step 3b: Make `build_config` read the controlDict**

**Added 2026-09-20, after Step 4 was measured.** Step 4 previously expected
`0 failed`. It is not, and the reason is a real gap rather than a test-data
problem.

Once `get_dict_entries()` returns the nine `CONTROL_DICT_ENTRIES`,
`specs/validation.validate_run` correctly sees them — `phases={"solver"}`,
`required=True`, no `applicable_when`. But
`cardiacfoam/run_document_config.build_config` initialises
`config["solver"] = {}` and then reads only `constant/electroProperties` and
`constant/physicsProperties`. It never reads `system/controlDict`, so those
nine keys can never be populated and every cardiacFoam RunDocument fails
validation with nine "is required" errors.

Narrowing their `required` flag would be the wrong cure. `build_control_dict`
takes `delta_t`, `end_time` and `write_interval` as parameters — the values
originate upstream in the spec and are written into the case. A RunDocument
whose `config["solver"]` omits them does not record what the run actually used,
which is the thing `config` exists to record.

This cannot be a separate task: a reviewer cannot accept Step 3 while rejecting
this, because Step 3 is broken without it.

Add a controlDict reader to `run_document_config.py`, mirroring the existing
`_read_physics_type` pattern:

```python
def _read_control_dict_values(case_root: Path, driver_context) -> dict[str, Any]:
    """Read the solver-phase values the case's controlDict actually carries.

    Resolved BY ROLE, never by literal path: the adapter declares
    ``openfoam.control_dict`` in its profile, and `get_selected_start_time`
    already resolves it the same way. Spelling ``system/controlDict`` here
    would be a second declaration of a fact the profile already owns.
    """
```

Resolve the file through `driver_context.capabilities.case_files`, matching on
`rule.role == "openfoam.control_dict"`. Read each of the nine keys with the
adapter's own config-value reader rather than a new parser — Task 9 of this
plan makes `get_config_value_reader` a real capability, and `mutators.read_foam_entry`
is what it returns. If Task 9 has not landed yet, call
`openfoam.mutators.read_foam_entry` directly and leave a comment naming Task 9
as the follow-up that routes it through the seam.

A key absent from the file must produce a diagnostic, not a silent default —
`build_config` already does this for `physicsProperties` via
`missing_physics_properties`, so follow that shape with a distinct code.

- [ ] **Step 3c: Verify the three sweep-runner tests pass again**

```bash
python -m pytest packages/omnidriver-cardiacfoam/tests/test_sweep_runner.py -v
```

Expected: PASS. These three — `test_sweep_plan_materializes_and_audits_each_case_for_real`,
`test_sweep_plan_records_materialization_failure_and_continues`,
`test_sweep_run_writes_run_documents_and_continues_past_failure` — fail with
Step 3 alone and pass once the reader exists. **Do not edit them.** If they
still fail, the reader is not populating what validation demands; fix the
reader.

- [ ] **Step 4: Run the test**

```bash
python -m pytest packages/omnidriver/tests/core/test_dict_entries.py -k agree -v
python -m pytest packages/ -q -m "not slow"
```

Expected: PASS, `0 failed`. Note that `driver_context()` rejects duplicate `driver_path` values — if it now raises, `CONTROL_DICT_ENTRIES` is already reachable by another route and that route is the duplicate to remove.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py \
        packages/omnidriver/tests/core/test_dict_entries.py \
        packages/omnidriver/tests/conftest.py
git commit -m "fix(cardiacfoam): get_dict_entries omitted the controlDict entries"
```

---

## Task 7: Close the MPI authorization hole

`validate_workflow_commands` inspects only `step["command"]`. For a parallel solve step the command is `mpirun`, which is in `CORE_NEUTRAL_COMMANDS`, so the step is accepted unconditionally and the wrapped solver binary is never checked. `workflow._unwrap_mpi_program` already exists and is imported into `strict_planning` **unused**.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/workflow.py`
- Test: `packages/omnidriver/tests/core/test_command_authorization.py`

**Interfaces:**
- Consumes: `workflow._unwrap_mpi_program(step) -> str | None` — already exists.
- Produces: `validate_workflow_commands` additionally rejects an unauthorized MPI payload, with a distinct diagnostic code `unauthorized_mpi_payload`.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_command_authorization.py`:

```python
def test_mpi_wrapped_payload_is_authorized(neutral_driver_context):
    """An mpirun wrapper must not launder an unauthorized binary.

    `mpirun` is in CORE_NEUTRAL_COMMANDS, so before 2026-09-20 the wrapped
    program was never checked against solver_commands(). It was fingerprinted
    for provenance but invisible to the allowlist.
    """
    from omnidriver.core.runtime import workflow

    dag = {"steps": [{
        "id": "solve",
        "command": "mpirun",
        "args": ["-np", "4", "definitelyNotAuthorized", "-parallel"],
    }]}
    problems = workflow.validate_workflow_commands(
        dag, driver_context=neutral_driver_context,
    )
    assert any(
        getattr(p, "code", None) == "unauthorized_mpi_payload"
        for p in problems
    ), f"expected an unauthorized_mpi_payload diagnostic, got {problems}"


def test_mpi_wrapped_authorized_solver_is_accepted(solver_driver_context):
    from omnidriver.core.runtime import workflow

    solver = next(iter(
        solver_driver_context.capabilities.command_authorization.solver_commands()
    ))
    dag = {"steps": [{
        "id": "solve",
        "command": "mpirun",
        "args": ["-np", "4", solver, "-parallel"],
    }]}
    problems = workflow.validate_workflow_commands(
        dag, driver_context=solver_driver_context,
    )
    assert not any(
        getattr(p, "code", None) == "unauthorized_mpi_payload"
        for p in problems
    )
```

Reuse whatever context fixtures `test_command_authorization.py` already defines; if it names them differently, use those names rather than adding new fixtures.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_command_authorization.py -k mpi -v
```

Expected: `test_mpi_wrapped_payload_is_authorized` FAILS — no diagnostic is produced.

- [ ] **Step 3: Check the payload in `validate_workflow_commands`**

In `workflow.py`, inside `validate_workflow_commands`, after the existing per-step command check, add:

```python
        payload = _unwrap_mpi_program(step)
        if payload is not None and not _is_authorized(payload, driver_context):
            problems.append(diagnostic(
                level="error",
                code="unauthorized_mpi_payload",
                message=(
                    f"step {step.get('id')!r} runs {payload!r} under an MPI "
                    "launcher, and that program is not in this plugin's "
                    "authorized command set"
                ),
                source="workflow",
                field=f"steps.{step.get('id')}.args",
            ))
```

Factor the existing accept-surface check into `_is_authorized(command, driver_context) -> bool` so the wrapper and the payload share one definition of "authorized" — two definitions is how this gap opened.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_command_authorization.py -k mpi -v
python -m pytest packages/ -q -m "not slow"
```

Expected: both PASS, `0 failed`. If a cardiacFoam tutorial that builds `mpirun` steps via `openfoam.parallel_execution.solve_steps` now fails, its solve command is genuinely outside the authorized set — fix the declaration, not the check.

- [ ] **Step 5: Remove the dead import**

```bash
grep -n '_unwrap_mpi_program' packages/omnidriver/src/omnidriver/core/strict_planning.py
```

If it is still imported and unused there, delete the import.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/runtime/workflow.py \
        packages/omnidriver/src/omnidriver/core/strict_planning.py \
        packages/omnidriver/tests/core/test_command_authorization.py
git commit -m "fix(core): an MPI launcher no longer launders an unauthorized binary"
```

---

## Task 8: Stop discarding override records and contexts

Two defects in one area.

`_OverrideScopeAdapter.apply` calls the plugin hook and then `return ()`, discarding what it returned. `openfoam.apply_overrides.apply_overrides` really does return records, and `legacy_apply_overrides` is typed to return them.

`openfoam.apply_overrides` and `get_override_target_paths` each build `make_driver_context(self, source="adapter:openfoam-environment")`, **discarding the caller's context**. A cardiacFoam-contexted `--apply` reaching these silently loses cardiac semantics.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py`
- Test: `packages/omnidriver/tests/core/test_case_file_contract.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_OverrideScopeAdapter.apply(...) -> tuple[dict, ...]` — the plugin's records, not `()`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/omnidriver/tests/core/test_case_file_contract.py`:

```python
def test_apply_returns_the_plugins_records():
    """The adapter must not swallow what the plugin reports it changed."""
    from omnidriver.core import plugin_capabilities

    sentinel = ({"path": "constant/x", "key": "a", "old": "1", "new": "2"},)

    class _Plugin:
        def apply_overrides(self, overrides, *, case_root):
            return sentinel

        def get_override_target_paths(self, overrides, *, case_root):
            return ()

    adapter = plugin_capabilities._OverrideScopeAdapter(plugin=_Plugin())
    assert adapter.apply({}, case_root=None) == sentinel


def test_openfoam_apply_overrides_uses_the_caller_context(tmp_path):
    """An adapter must not substitute a context built from itself.

    Doing so drops the caller's solver semantics silently, which is the
    failure mode `DriverContext` exists to prevent.
    """
    import inspect
    from omnidriver.openfoam import apply_overrides

    for name in ("apply_overrides", "get_override_target_paths"):
        source = inspect.getsource(getattr(apply_overrides, name))
        assert "make_driver_context(" not in source, (
            f"{name} builds its own context, discarding the caller's"
        )
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_file_contract.py -k "records or caller_context" -v
```

Expected: both FAIL.

- [ ] **Step 3: Return the records**

In `plugin_capabilities.py`, in `_OverrideScopeAdapter.apply`, change the hook branch from calling the hook and returning `()` to returning the hook's result. Update the method's return annotation to `tuple[dict, ...]` so it matches `legacy_apply_overrides`.

- [ ] **Step 4: Thread the caller's context**

In `openfoam/apply_overrides.py`, give `apply_overrides` and `get_override_target_paths` a keyword-only `driver_context` parameter and delete the `make_driver_context(self, ...)` calls. Update `OpenFOAMEnvironmentPlugin.apply_overrides` and `.get_override_target_paths` in `openfoam/environment.py` to pass the context they were given.

If a caller has no context to pass, that caller is the defect — find it rather than restoring the self-built context.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_file_contract.py -k "records or caller_context" -v
python -m pytest packages/ -q -m "not slow"
python -m pytest packages/omnidriver/tests/core/test_core_context_is_explicit.py -v
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver-openfoam/src/omnidriver/openfoam/apply_overrides.py \
        packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py \
        packages/omnidriver/tests/core/test_case_file_contract.py
git commit -m "fix(core,openfoam): keep override records and the caller's context"
```

---

## Task 9: Give `get_config_value_reader` a capability, or delete it

`plugin_interface.py` declares `get_config_value_reader` under a `# -- ConfigValueCapability --` heading naming a Protocol that **does not exist**. No adapter, no field on `PluginCapabilities`. Both `OpenFOAMEnvironmentPlugin` and `CardiacFoamPlugin` implement it, and they return **different callables**. The only caller is `CardiacFoamPlugin.get_selected_start_time` calling it on `self`.

Phase 1 needs this as a composed seam, so build the capability rather than deleting the hook.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Test: `packages/omnidriver/tests/core/test_capability_seam_documentation.py`

**Interfaces:**
- Consumes: `capability_seams.TIERS` (Task 1).
- Produces: `plugin_capabilities.ConfigValueCapability` with one member `reader()`, adapted by `_ConfigValueAdapter`, reachable as `driver_context.capabilities.config_value`.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_capability_seam_documentation.py`:

```python
def test_config_value_is_a_real_capability():
    """`plugin_interface` documents ConfigValueCapability; it must exist.

    Before 2026-09-20 the heading named a Protocol no module defined, so two
    adapters implemented the hook and returned different callables while core
    read neither.
    """
    from omnidriver.core import plugin_capabilities

    assert hasattr(plugin_capabilities, "ConfigValueCapability")
    assert "config_value" in plugin_capabilities.PluginCapabilities.__annotations__
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -k config_value -v
```

Expected: FAIL on the first assertion.

- [ ] **Step 3: Add the Protocol, the adapter, and the field**

In `plugin_capabilities.py`, following the file's existing shape exactly:

```python
class ConfigValueCapability(Protocol):
    """Read one configuration value from an adapter's own file format.

    :adapts: get_config_value_reader
    :consumed-by: omnidriver/core/runtime/provenance_inputs.py
    :fallback: none
    :status: optional-neutral
    """

    def reader(self): ...
```

```python
@dataclass(frozen=True)
class _ConfigValueAdapter:
    plugin: "SolverPlugin"

    def reader(self):
        hook = getattr(self.plugin, "get_config_value_reader", None)
        if hook is None:
            return None
        return hook()
```

Add `config_value: ConfigValueCapability` to `PluginCapabilities` in the declaration position matching the seam order you want in the table, and wire `_ConfigValueAdapter(plugin=plugin)` into `adapt_plugin_capabilities`.

`:fallback: none` with `:status: optional-neutral` is correct here: the neutral value is `None`, returned inline, with no named `legacy_*`. Several adapters already do this.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_seam_documentation.py -v
python -m pytest packages/omnidriver/tests/core/test_contract_tier_coherence.py -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`.

- [ ] **Step 5: Regenerate the seam table**

```bash
python3 scripts/export-capability-seams.py
python3 scripts/export-capability-seams.py --check
```

Expected: the table gains a `config_value` row and `--check` exits 0.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/tests/core/test_capability_seam_documentation.py \
        ARCHITECTURE.md
git commit -m "feat(core): ConfigValueCapability exists, as the contract already claimed"
```

---

## Task 10: One diagnostic shape

Four distinct shapes reach an agent where the repair loop needs one. The worst is `run_document_exec._diag`, which drops `source` even when re-serializing a `StrictDiagnostic` that has one.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/specs/validation_types.py`
- Modify: `packages/omnidriver/src/omnidriver/core/specs/validation.py`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/run_document_exec.py`
- Test: `packages/omnidriver/tests/core/test_cli_run_document.py`

**Interfaces:**
- Consumes: `core.planning_types.StrictDiagnostic` with fields `level, code, message, source, field`, built by `planning_types.diagnostic(...)`.
- Produces: `validate_run(...)` returns `tuple[StrictDiagnostic, ...]`. `ValidationError` is removed. `run_document_exec._diag` is removed.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_cli_run_document.py`:

```python
def test_every_diagnostic_carries_the_same_five_fields(invalid_run_document_report):
    """An agent repairs against one shape or it repairs against none.

    `run_document_exec._diag` used to drop `source` even when the diagnostic
    it re-serialized had one, so the same logical error reached an agent with
    four fields from one path and five from another.
    """
    expected = {"level", "code", "message", "source", "field"}
    for key in (
        "validation_diagnostics",
        "workflow_diagnostics",
        "configuration_diagnostics",
    ):
        for item in invalid_run_document_report.get(key, ()):
            assert set(item) == expected, (
                f"{key} emitted a diagnostic with fields {sorted(item)}"
            )
```

Build `invalid_run_document_report` as a fixture in the same file that runs the run-document path against a document with a known-bad `config`, returning the parsed JSON report. Reuse whatever helper that file already uses to invoke the CLI.

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_cli_run_document.py -k five_fields -v
```

Expected: FAIL, showing a diagnostic missing `source`.

- [ ] **Step 3: Make `validate_run` return `StrictDiagnostic`**

In `validation.py`, replace every `ValidationError(phase=..., field=..., message=..., level=...)` construction with:

```python
diagnostic(level=..., code="run_validation", message=..., source=<the phase>, field=...)
```

`phase` becomes `source`; `code` becomes `"run_validation"` unless a more specific code already exists at that site. Update the `RunSemanticValidatorCapability` Protocol's return annotation from `tuple[Any, ...]` to `tuple[StrictDiagnostic, ...]` — the weakened annotation is why the divergence was invisible.

- [ ] **Step 4: Delete `_diag` and `ValidationError`**

In `run_document_exec.py`, delete `_diag` and pass diagnostics through unchanged. In `validation_types.py`, delete `ValidationError`. Update `run_document_adapter.py`, which currently re-wraps `ValidationError` into `StrictDiagnostic` — that re-wrap is now a no-op and should go.

- [ ] **Step 5: Replace the blanket exception envelope**

In `cli.py`, `_context_from_run_document` catches `Exception` and emits `{"status": "failed", "error": str(exc), "run_document": path}`. Keep the envelope — a load failure genuinely is not a diagnostic — but add a `diagnostics` key holding one `StrictDiagnostic` with `code="run_document_unreadable"`, `source="cli"`, so an agent parsing `diagnostics` finds it there too.

- [ ] **Step 6: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_cli_run_document.py -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/specs/validation.py \
        packages/omnidriver/src/omnidriver/core/specs/validation_types.py \
        packages/omnidriver/src/omnidriver/core/runtime/run_document_exec.py \
        packages/omnidriver/src/omnidriver/core/runtime/run_document_adapter.py \
        packages/omnidriver/src/omnidriver/cli.py \
        packages/omnidriver/tests/core/test_cli_run_document.py
git commit -m "refactor(core): one diagnostic shape reaches an agent"
```

---

## Task 11: cardiacCore declaration hygiene

Three independent findings in one package.

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/inputs.py`
- Test: `packages/omnidriver-cardiaccore/tests/` (place beside that package's existing catalog tests)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new; removes `catalogs.inputs.GRAPH_FILE_KEYS` and `catalogs.inputs.UTILITY_CLI_OPTIONS`.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver-cardiaccore/tests/test_profile_matches_catalog.py`:

```python
"""The profile and the dict catalogue must agree on which files a case has."""

from pathlib import Path

from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.cardiaccore.catalogs.inputs import DOCUMENTS


def test_every_catalogued_document_has_a_profile_rule():
    profile = load_plugin_profile(
        Path(__file__).resolve().parents[1]
        / "src/omnidriver/cardiaccore/plugin.yaml"
    )
    declared = {rule.path for rule in profile.case_files}
    catalogued = {f"system/{name}" for name in DOCUMENTS}
    missing = sorted(catalogued - declared)
    assert missing == [], (
        "these documents are in the dict catalogue but have no plugin.yaml "
        f"rule: {missing}"
    )
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/test_profile_matches_catalog.py -v
```

Expected: FAIL naming `setCardiacScarDict`, `setPurkinjeScarDict`, `coordinatesConventionDict`, `generatePurkinjeTreeDict`.

- [ ] **Step 3: Add the four rules**

In `plugin.yaml`, under `case_profile.dictionaries`, add four entries following the existing pattern exactly:

```yaml
    - path: system/setCardiacScarDict
      kind: openfoam_dictionary
      role: cardiaccore.scar_dictionary
      required: conditional
    - path: system/setPurkinjeScarDict
      kind: openfoam_dictionary
      role: cardiaccore.purkinje_scar_dictionary
      required: conditional
    - path: system/coordinatesConventionDict
      kind: openfoam_dictionary
      role: cardiaccore.coordinates_convention_dictionary
      required: conditional
    - path: system/generatePurkinjeTreeDict
      kind: openfoam_dictionary
      role: cardiaccore.purkinje_tree_dictionary
      required: conditional
```

The `cardiaccore.` namespace already validates through `plugin_profile._is_valid_environment_role`; no change to `KNOWN_ROLES` is needed.

- [ ] **Step 4: Delete the two orphan constants**

```bash
grep -rn 'GRAPH_FILE_KEYS\|UTILITY_CLI_OPTIONS' packages/ scripts/
```

Expected: matches only inside `catalogs/inputs.py` itself. If anything else matches, stop — the audit's "zero references" finding has drifted and the constant is live.

Delete both `GRAPH_FILE_KEYS` and `UTILITY_CLI_OPTIONS`. `UTILITY_CLI_OPTIONS` additionally contradicted `catalogs/utilities.UTILITY_MANIFESTS` on `-internalRole`'s default — `catalogs/utilities.py` is the single source and keeps its value.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/ -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml \
        packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/catalogs/inputs.py \
        packages/omnidriver-cardiaccore/tests/test_profile_matches_catalog.py
git commit -m "fix(cardiaccore): profile now declares every catalogued document"
```

---

## Task 12: Cache what Phase 1's digest will call

§4.4 of the spec makes this load-bearing: the stack digest materializes capabilities at context construction, and three of them currently re-parse from disk on every call.

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/agent_guidance/__init__.py`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/runtime_profile.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Test: `packages/omnidriver/tests/core/test_capability_seam_documentation.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing new; `describe_guidance`, `_profile_contract` and `_CapabilityManifestAdapter.manifest` become cached.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_capability_calls_are_cheap.py`:

```python
"""Capability accessors must be cheap enough to call at context construction.

Phase 1's stack digest materializes capabilities when a DriverContext is
built. An accessor that re-parses YAML from package resources on every call
makes that too slow to do.
"""

import pytest


def test_named_catalogs_does_not_reparse_on_every_call():
    pytest.importorskip("omnidriver.cardiaccore")
    from omnidriver.cardiaccore import agent_guidance

    first = agent_guidance.describe_guidance()
    second = agent_guidance.describe_guidance()
    assert first == second
    assert agent_guidance._load_manifest.cache_info().hits >= 1
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_calls_are_cheap.py -v
```

Expected: FAIL — `_load_manifest` does not exist.

- [ ] **Step 3: Cache the manifest parse**

In `cardiaccore/agent_guidance/__init__.py`, extract the `yaml.safe_load` of `manifest.yaml` into:

```python
@lru_cache(maxsize=1)
def _load_manifest() -> dict:
    """Parse the guidance manifest once per process.

    `describe_guidance` is reached through `get_named_catalogs()`, which
    `describe` calls and which Phase 1's stack digest will call at context
    construction. Re-reading package resources per call is affordable at the
    first and not at the second.
    """
    ...
```

Have `describe_guidance` call it. Keep the existing deep-copy on the way out — the cache holds the parsed document and callers must not mutate it.

- [ ] **Step 4: Run the test**

```bash
python -m pytest packages/omnidriver/tests/core/test_capability_calls_are_cheap.py -v
```

Expected: PASS.

- [ ] **Step 5: Cache the two remaining re-parses**

`cardiacfoam/runtime_profile._profile_contract()` re-reads `plugin.yaml` from disk on every call rather than reusing `PluginProfile.payload`, which already holds the same parsed document. Change it to read `get_profile().payload`. This also brings `runtime.backend` inside the profile digest, which it is currently outside.

`_CapabilityManifestAdapter.manifest()` in `plugin_capabilities.py` is a bare pass-through with no cache, and `CardiacFoamPlugin.get_named_catalogs()` calls `get_capabilities()` which rebuilds the whole manifest. Add an `@cached_property`-style memo on the adapter — the adapter is a frozen dataclass holding one plugin, so caching on it is per-context and cannot leak between contexts.

- [ ] **Step 6: Run everything**

```bash
python -m pytest packages/ -q -m "not slow"
python -m pytest packages/omnidriver/tests -q
```

Expected: `0 failed`. If a test depended on `_profile_contract` re-reading a file it had just rewritten, that test is asserting the defect — rewrite it to build a fresh context instead.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/agent_guidance/__init__.py \
        packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/runtime_profile.py \
        packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/tests/core/test_capability_calls_are_cheap.py
git commit -m "perf(core,adapters): cache the capability reads Phase 1's digest will make"
```

---

## Task 13: The three remaining §3.3 defects

Three items from spec §3.3 that fit no earlier task. Each is small and independent; a reviewer could accept any one and reject another.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver/src/omnidriver/core/tutorial_contracts.py`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
- Test: `packages/omnidriver/tests/core/test_case_provenance_capability.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `_RuntimeEvidenceAdapter.extra_provenance_paths(...) -> tuple[RuntimeDependency, ...]` (annotation corrected to match the contract); `tutorial_contracts.describe_tutorial_contract` no longer emits five always-empty keys.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_case_provenance_capability.py`:

```python
def test_extra_provenance_paths_is_annotated_as_dependencies():
    """A bare Path can only omit, and omission reads as nothing-to-check.

    That is the gap `RuntimeDependency` was introduced to close, so the
    adapter must not narrow the contract back to `tuple[Path, ...]`.
    """
    import typing
    from omnidriver.core import plugin_capabilities

    hints = typing.get_type_hints(
        plugin_capabilities._RuntimeEvidenceAdapter.extra_provenance_paths,
        include_extras=True,
    )
    assert "RuntimeDependency" in str(hints["return"]), (
        f"annotation is {hints['return']!r}, not a RuntimeDependency tuple"
    )


def test_capability_manifest_does_not_hand_out_a_live_catalog():
    """`get_utility_manifests` was hardened against this; the model
    catalogues were not, and one of them is mutated at import."""
    import pytest
    pytest.importorskip("omnidriver.cardiacfoam")
    from omnidriver.cardiacfoam import ionic_model_catalog
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    manifest = CardiacFoamPlugin().get_capabilities()
    assert manifest["ionic_models"] is not ionic_model_catalog.IONIC_MODEL_CATALOG
```

- [ ] **Step 2: Run to verify both fail**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_provenance_capability.py -k "annotated or live_catalog" -v
```

Expected: both FAIL.

- [ ] **Step 3: Correct the annotation**

In `plugin_capabilities.py`, change `_RuntimeEvidenceAdapter.extra_provenance_paths`'s return annotation from `tuple[Path, ...]` to `tuple["RuntimeDependency", ...]`, matching `RuntimeEvidenceCapability` and `SolverPlugin`. This is annotation-only — the runtime value was already `RuntimeDependency`; only the declared type was wrong, which is why no test caught it.

- [ ] **Step 4: Stop handing out the live catalogues**

In `cardiacfoam_plugin.get_capabilities`, wrap both model catalogues on the way out exactly as `get_utility_manifests` already does:

```python
        manifest["ionic_models"] = dict(IONIC_MODEL_CATALOG)
        manifest["active_tension_models"] = dict(ACTIVE_TENSION_MODEL_CATALOG)
```

A shallow copy is enough: the values are frozen dataclasses. The hazard is the mutable *dict*, which `IONIC_MODEL_CATALOG` additionally has written into at import by the `BATCHED_MODELS` loop.

- [ ] **Step 5: Delete the five dead reception slots**

In `tutorial_contracts.py`, five fields are hardcoded `[]` — `mesh_files`, `constant_files`, `system_files`, `reference_cases`, `postprocess_modules` — retained after OpenFOAM discovery was retired. Delete them from the emitted contract.

Before deleting, confirm nothing consumes them:

```bash
grep -rn 'mesh_files\|constant_files\|system_files\|reference_cases\|postprocess_modules' packages/ scripts/ --include=*.py
```

If a consumer reads one, it is reading a constant empty list — update that consumer in the same commit rather than keeping the slot.

- [ ] **Step 6: Note the one acceptable duplicate**

`get_profile` legitimately feeds two capabilities, `CxxMappingCapability` and `CaseFileContractCapability`. That is fine and must stay, but it currently looks like an oversight. Add to `CaseFileContractCapability`'s docstring:

```
    ``get_profile`` deliberately backs this capability AND
    ``CxxMappingCapability``: one declaration, two consumers with different
    concerns. Recorded 2026-09-20 because it reads as a duplicate intake and
    is not one.
```

- [ ] **Step 7: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_case_provenance_capability.py -v
python3 scripts/export-capability-seams.py && python3 scripts/export-capability-seams.py --check
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_capabilities.py \
        packages/omnidriver/src/omnidriver/core/tutorial_contracts.py \
        packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py \
        packages/omnidriver/tests/core/test_case_provenance_capability.py \
        ARCHITECTURE.md
git commit -m "fix(core,cardiacfoam): annotation, live catalogues, and five dead slots"
```

---

## Task 14: The wheel shape, and the Phase 0 close-out

Phase 0 is not done until it passes from a wheel. Editable installs leave the repository on `sys.path`, so a module reading repo-relative state at import time still works — that class of defect is only visible here.

**Files:**
- None modified unless the wheel shape fails.

- [ ] **Step 1: Rebuild the wheel**

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
```

- [ ] **Step 2: Run the artifact gate**

```bash
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
```

Expected: exits 0.

- [ ] **Step 3: Run the core suite from the wheel**

```bash
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: `0 failed`.

Two Phase 0 changes are wheel-sensitive and this is where they fail if they are wrong: `_required_plugin_members()` (Task 4) imports `capability_seams`, which calls `architecture_path()` — a *function*, not a constant, precisely because `repo_root_default()` raises from a wheel. If Task 4 made it a module-level constant, it fails here.

- [ ] **Step 4: Run the core-only shape**

```bash
VIRTUAL_ENV=/tmp/odcore uv pip install -q -e "packages/omnidriver[post]" pytest
/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: `0 failed`. This catches core reaching into a sibling package.

- [ ] **Step 5: Run the static gates**

```bash
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
```

Expected: both exit 0, and the import-boundary waiver list is still empty.

- [ ] **Step 6: Commit any fixes, then tag the phase**

```bash
git add -A
git commit -m "chore: Phase 0 passes in all four verification shapes"
```

---

## Task 15: The Phase 1 mechanism spike

Not a refactor — a **decision with evidence**. Its deliverable is a written recommendation plus a throwaway prototype, not merged production code.

**Files:**
- Create: `docs/superpowers/specs/2026-09-20-composition-mechanism-spike.md`
- Prototype on a throwaway branch; do not merge the prototype.

**Interfaces:**
- Consumes: everything Phase 0 produced, particularly `capability_seams.members_by_tier()`.
- Produces: a recommendation that Phase 1's plan consumes — either "own it" or "adopt pluggy", with the composition rules from spec §4.3 expressed in the chosen mechanism.

- [ ] **Step 1: Write down the success criterion before building anything**

Create the spike document with this at the top, so the prototype cannot be graded after the fact:

> **Success criterion.** `omnidriver step --strict --apply` succeeds on a
> cardiacCore case with **zero new code in `omnidriver-cardiaccore`**. Today it
> is refused: `CardiacCorePlugin` implements none of `apply_overrides`,
> `get_override_target_paths`, `inspect_effective_configuration`,
> `get_override_scopes`, so `legacy_apply_overrides` raises. Under a working
> provider stack the OpenFOAM provider supplies all four.

- [ ] **Step 2: Reproduce the current refusal**

```bash
python -m omnidriver step --plugin cardiaccore --strict --apply <a cardiaccore case> 2>&1 | tail -5
```

Expected: a `ValueError` naming `apply_overrides`. Paste the exact message into the spike document — that message disappearing is the test.

- [ ] **Step 3: Prototype A — own it**

On branch `spike/composition-own`, change `DriverContext` to hold `providers: tuple[SolverPlugin, ...]` and implement the five rules from spec §4.3 in `adapt_plugin_capabilities`. Implement only as much as the success criterion needs — `override_scopes` composition plus whatever `step --apply` traverses. Do not implement all 24.

Record: lines changed, which of the five rules the criterion actually exercised, and what broke.

- [ ] **Step 4: Prototype B — pluggy**

On branch `spike/composition-pluggy`, add `pluggy` and express the same subset as hookspecs and hookimpls. Verify its current API from its own documentation rather than from memory or from the spec's summary of it.

Record the same three things, plus: what happens to `capability_seams.parse_fields`, which reads Protocol docstrings that would no longer exist in that form.

- [ ] **Step 5: Measure both against the criterion**

```bash
python -m omnidriver step --plugin cardiaccore --strict --apply <the same case>
```

Expected on both branches: succeeds, with `git diff --stat main -- packages/omnidriver-cardiaccore` showing **no changes**. A prototype that needs cardiacCore edits has not met the criterion.

- [ ] **Step 6: Write the recommendation**

Complete the spike document with: the criterion and whether each prototype met it; lines changed in each; what each does to the generated seam table; the runtime-dependency cost; and a recommendation with its reason. If neither met the criterion, say so — that is a finding, and it means spec §4.3's rules are wrong somewhere.

- [ ] **Step 7: Commit the document, delete the branches**

```bash
git add docs/superpowers/specs/2026-09-20-composition-mechanism-spike.md
git commit -m "docs(spike): composition mechanism recommendation with evidence"
git branch -D spike/composition-own spike/composition-pluggy
```

The prototypes are deliberately not merged. Their value is the measurement.

---

## What this plan does not cover

Phase 1 (the provider stack) and Phase 2 (one case-write channel) get their own plans, written **after** Task 15 resolves the mechanism. They cannot be written now without placeholder steps, which this skill forbids: every "write the minimal implementation" step in Phase 1 depends on which mechanism Task 15 selects.

Four Phase 0 items from spec §3.2 are also deferred to Phase 1 for a reason the spec states — they cannot be resolved plugin-globally:

| item | why it waits |
|---|---|
| `config_schema` answered by two capabilities | which capability survives depends on which one composes correctly across providers |
| entrypoint declared twice | closed by spec §2.1's single-declarer rule, which needs providers to exist |
| case marker answered three ways | same |
| `get_capabilities()` round trip | core can only build the manifest itself once it holds every provider's seams |

`legacy_dict_key_scanner` — a permanently-active "fallback" with no hook, no capability and no probe, called unconditionally by `strict_planning._catalog_diagnostics` — is also deferred. It needs a capability designed for it, and that design belongs with Phase 1's per-capability work rather than before it.
