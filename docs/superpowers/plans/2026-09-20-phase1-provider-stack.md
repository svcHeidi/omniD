# Phase 1: The Provider Stack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let core compose an ordered stack of providers per capability, so that an environment adapter layers under a solver plugin instead of being embedded by hand in each one.

**Architecture:** `DriverContext.plugin: SolverPlugin` becomes `DriverContext.providers: tuple[SolverPlugin, ...]`, ordered least-specific to most-specific. A provider declares in its `plugin.yaml` which capabilities it provides and which providers it requires; core topologically sorts and composes per capability using six written rules. Identity becomes plural — `ProviderIdentity` per provider, `StackIdentity` over the stack — so a provenance record can say which adapter answered which capability.

**Tech Stack:** Python 3.11+, pytest, `yaml`. Whether a runtime dependency (`pluggy`) is added is decided by Phase 0's Task 15 spike; every other task here is mechanism-independent.

**Source spec:** `docs/superpowers/specs/2026-09-20-provider-composition-design.md` §4, plus §2.1 and the four items §3.2 deferred here.

**Prerequisite:** Phase 0 complete, including Task 15's spike recommendation.

## Global Constraints

- Python floor is **3.11**. Keep `from __future__ import annotations` in `plugin_interface.py`; several annotations there name `TYPE_CHECKING`-only types and eager evaluation raises `NameError` on 3.11/3.12.
- `omnidriver.core` MUST NOT import from any adapter package. `scripts/check-import-boundaries.py` enforces this and **its waiver list must stay empty**.
- `omnidriver.cardiaccore` MUST NOT import `omnidriver.cardiacfoam`, nor the reverse.
- No production module — in core **or in an adapter**, which is new in this phase — may touch `driver_context.plugin`/`.providers` directly. Go through `.capabilities`.
- Do not weaken or skip a guard to make a change pass.
- **The `Files:` block is authoritative for what to commit, not the per-step `git add` list.** Those lists were written before the tasks ran and have been stale three times (Phase 0 Tasks 1, 4 and 6). Commit every file the task actually changed; if that differs from the `Files:` block, say so in the report.
- Do not quote suite totals. The durable claim is `0 failed`.
- Prefer naming a **symbol** over a `file.py:123` line number.
- Record document corrections with a date.
- Do not add a `LICENSE` file or a `license` field.
- Rebuild the wheel after every source change before running the wheel shape.

## Status

| task | state | commit |
|---|---|---|
| 1 · `provides:`/`requires:` in the profile | done | `d901ea9` |
| 2 · declared-vs-implemented guard | done | `0326899` |
| 3 · topological ordering | done | `3b451fa` |
| 4 · the composition rules, as failing tests | done (red by design) | `10fea49` |
| 5 · `ProviderIdentity` / `StackIdentity` | done | `f408dc6` |
| 6 · the composition mechanism (spike resolved: **own it**) | done, one test blocked | `e7dc7b5` |
| 7 · `DriverContext.providers` | done | `b0df7ad` (+ `5b2d4b2`, `66d59ab` — review fix round) |
| 8 · extend the dependency boundary to adapters | done | `678af56` |
| 9 · delete the hand-embedding | done | `4a25c3d` (+ `18da0ac`, `73d122a`, `fb4287b`, `e732c26` — see note below) |
| 10 · the four deferred duplicate intakes | done | `cd47102` |
| 11 · `legacy_dict_key_scanner` gets a capability | done | `ce6996f` |
| 12 · document the composition contract | done | `edb0921` (+ `d0fa3ec` — review fix round) |
| 13 · all four shapes | done, no commit (pure verification) | — |
| final whole-branch review | done | `3998a85`, `c93f860`, `61c7e7e`, `55a8060`, `bc5a33c`, `02fde13` |

**Merged to `main` 2026-09-22** (fast-forward, `02fde13`). Branch `docs/provider-composition-spec` deleted after merge.

**The suite is intentionally red from Task 4 until Task 6.** 13 tests in
`test_provider_composition_rules.py` fail on `provider_stack.compose` not
existing. That is the design: they are the specification Task 6 implements
against, and Task 6 must turn them green WITHOUT editing them. Any other
failure in the meantime is a real regression.

**Corrected 2026-09-21, by Task 6.** Twelve of the thirteen are green and the
thirteenth cannot be made green by any implementation.
`test_a_case_file_path_declared_twice_is_an_error` writes
`env.get_profile().case_files = (rule,)`, but that file's `_Provider.get_profile`
builds a **fresh** `type("_P", (), {})()` on every call, so the attribute is
set on a throwaway and no `case_files` is ever observable from the provider.
The rule it names is implemented and is tested — `test_provider_ordering.py`'s
`test_a_case_file_path_declared_by_two_providers_is_an_error` uses a provider
whose profile persists and the duplicate path is refused by name. Making the
committed test exercise its own rule needs one line in its `_Provider`
(memoize the profile); Task 6 did not take it, because the task's terms
forbade editing that file. Whoever lands that edit should delete this note.

A second, milder slip in the same file: it calls the composed
`sweep_materializer.materialize` with the *contract member's* argument names
(`case_dir=`, `routed=`) rather than the Protocol's
`SweepMaterializationRequest`. Task 6 honoured the test — `_SweepMaterializerAdapter.materialize`
now accepts either, which is additive and breaks no caller — rather than
declaring a second slip.

Re-audited against post-Phase-0 code on 2026-09-20; five corrections applied
(Tasks 6, 7 and 9). Tasks 1-5, 8 and 10-13 were confirmed still correct as
written. No task was made redundant by Phase 0.

**Tasks 7-13, landed 2026-09-22.** Three things surfaced mid-execution that
the plan text did not anticipate, each resolved with a human decision before
continuing rather than guessed:

- **Task 7** found `DriverContext.identity` changing from `PluginIdentity`
  (flat `id`/`version`/`api_version`) to `StackIdentity` broke five
  core-internal call sites and `RunDocument.plugin`'s own JSON Schema — not
  just adapter code, which is all the task anticipated. Per spec §4.4's own
  stated rationale ("a provenance record can state which adapter answered
  which capability"), the fix gave `RunDocument.plugin` the full
  `StackIdentity` shape rather than a single-provider shim.
- **Task 9** (the payoff task) found two further things once its own
  case-file-duplication fix let real adapters compose for the first time:
  cardiacCore and cardiacFoam each independently declared two identical
  utilities (`newVtkUnstructuredToFoam`, `1DgraphToFoam`) with diverging
  documentation — resolved by deleting cardiacCore's copies, since
  cardiacFoam's were more complete and neither utility had any consumer
  inside cardiacCore itself. And `default_driver_context()` (Task 7's own
  change) was found to silently compose *any* two mutually-independent
  solver-tier plugins together with no way to pick a winner beyond
  alphabetical accident — fixed by making it refuse (name the candidates,
  point at `--plugin`) when 2+ solver-tier roots are ambiguous, while still
  auto-composing one root with its full `requires:` closure.
- **Task 12** found the plan's own "six rules" framing was stale — the
  actual implementation needed nine composition shapes, not six (three added
  by Task 6, a tenth-in-name-but-really-ninth added later by Task 9's own
  `get_tutorial_catalog` collision). Documented in `ARCHITECTURE.md`'s new
  "Provider composition" section rather than perpetuated here.

**The final whole-branch review** (after Task 13, covering all of the above)
found one Critical regression invisible to any single task's own review:
Task 8 turned `openfoam_environment.py`'s environment-configuration
back-channel into a no-op (correctly, per its own scope), and Task 9 deleted
cardiacFoam's redundant diagnostics passthrough (also correctly) — but
together, cardiacFoam's real backend/build-manifest configuration
(`configure_runtime_environment`, wired as a `chain`-shape
`get_configured_environment`) stopped being reachable from the CLI's actual
run/step path, which only ever called `.load()` (the `single`-shape
`get_loaded_environment`), never `.configure()`. Fixed by making `.load()`
thread its result through `.configure()`, restoring "load = source +
configure" as one contract. Three further Important findings (a
RunDocument identity gate in `cli.py` comparing dead keys; a
`@pytest.mark.slow` wheel test broken by the identity-shape change and never
run because every verification shape excludes slow tests; the `provides:`
realness standard from Task 9 having no actual effect on `resolutions()`'s
provenance, corrected in documentation rather than by changing the digest)
were fixed in the same round. Full detail in each task's own report under
`.superpowers/sdd/` in the branch history (not preserved after merge; see
commit messages `3998a85`..`02fde13` for the final fix round).

---

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

## Verification

Each task's test step runs at minimum its own test. Before each commit also run `python -m pytest packages/ -q -m "not slow"`. At Task 13, all four shapes per `CLAUDE.md`.

---

## File Structure

**Core — created:**
- `core/provider_stack.py` — ordering, composition rules, and the composed-capability builder. One responsibility: turning N providers into one `PluginCapabilities`.
- `core/provider_identity.py` — `ProviderIdentity`, `StackIdentity`, and the two-level digest.
- `tests/core/test_provider_composition_rules.py` — the six rules, mechanism-independent.
- `tests/core/test_provider_ordering.py` — `requires:` and the topological sort.
- `tests/core/test_stack_identity.py` — digest properties.

**Core — modified:**
- `core/plugin_profile.py` — `provides:` and `requires:` keys; single-declarer rule for case-file paths.
- `core/plugin_interface.py` — `DriverContext.providers`; `driver_context()` builds a stack.
- `core/plugin_capabilities.py` — adapters take a provider tuple.
- `core/plugin_discovery.py` — `_default_selection` composes rather than refusing.

**Adapters — modified:**
- `omnidriver-openfoam/.../openfoam-environment.yaml`, `omnidriver-cardiacfoam/.../plugin.yaml`, `omnidriver-cardiaccore/.../plugin.yaml` — gain `provides:`/`requires:`, lose duplicated case-file rules.
- `omnidriver-cardiaccore/.../plugin.py` — `_openfoam` and nine delegations deleted.
- `omnidriver-cardiacfoam/.../cardiacfoam_plugin.py` — function-local OpenFOAM imports for composed concerns deleted.
- `omnidriver-openfoam/.../openfoam_environment.py` — two `getattr` back-channels deleted.

---

## Task 1: `provides:` and `requires:` in the profile

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_profile.py`
- Test: `packages/omnidriver/tests/core/test_provider_ordering.py`

**Interfaces:**
- Consumes: `capability_seams.collect_seams()` (Phase 0 Task 1) for the valid capability-name vocabulary.
- Produces: `PluginProfile.provides: frozenset[str]` and `PluginProfile.requires: tuple[str, ...]`. Every later task reads these.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_provider_ordering.py`:

```python
"""A provider declares what it provides and what it layers on."""

import pytest
import yaml

from omnidriver.core import plugin_profile


def _profile(tmp_path, payload):
    path = tmp_path / "plugin.yaml"
    path.write_text(yaml.safe_dump(payload))
    return plugin_profile.load_plugin_profile(path)


BASE = {
    "schema_version": 1,
    "plugin": {"id": "org.example.thing", "api_version": "2"},
    "case_profile": {"dictionaries": []},
}


def test_provides_and_requires_default_to_empty(tmp_path):
    profile = _profile(tmp_path, dict(BASE))
    assert profile.provides == frozenset()
    assert profile.requires == ()


def test_provides_is_read(tmp_path):
    payload = dict(BASE, provides=["command_authorization", "case_files"])
    profile = _profile(tmp_path, payload)
    assert profile.provides == frozenset({"command_authorization", "case_files"})


def test_requires_preserves_order(tmp_path):
    payload = dict(BASE, requires=["org.omnidriver.openfoam", "org.example.mid"])
    profile = _profile(tmp_path, payload)
    assert profile.requires == ("org.omnidriver.openfoam", "org.example.mid")


def test_provides_rejects_an_unknown_capability(tmp_path):
    payload = dict(BASE, provides=["not_a_capability"])
    with pytest.raises(ValueError, match="not_a_capability"):
        _profile(tmp_path, payload)
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -v
```

Expected: FAIL — `PluginProfile` has no attribute `provides`.

- [ ] **Step 3: Implement the two keys**

In `plugin_profile.py`, add two frozen fields to `PluginProfile`:

```python
    #: Capability names this provider supplies, validated against the seam
    #: vocabulary at load. Intent, not observation: what the provider MEANS to
    #: supply. Core separately discovers what it actually implements, and
    #: `test_provides_matches_implementation` errors when they disagree --
    #: which is how a misspelled hook name becomes visible. Before this,
    #: a typo'd hook silently routed to a fallback and nothing reported it.
    provides: frozenset[str] = frozenset()

    #: Provider ids this one layers on top of, least-specific first. Ordering
    #: is declared, never inferred from install order or entry-point name.
    requires: tuple[str, ...] = ()
```

In `load_plugin_profile`, parse both. Validate each `provides` entry against the capability vocabulary:

```python
    from .capability_seams import collect_seams

    known = {seam.field for seam in collect_seams()}
    provides = frozenset(payload.get("provides", ()) or ())
    unknown = sorted(provides - known)
    if unknown:
        raise ValueError(
            f"plugin.yaml declares provides entries that name no capability: "
            f"{unknown}; known capabilities are {sorted(known)}"
        )
    requires = tuple(payload.get("requires", ()) or ())
```

Include both in the digest snapshot computed in `__post_init__` — a provider that changes what it provides has changed its semantics.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`. Existing profiles declare neither key and default to empty, so nothing breaks yet.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_profile.py \
        packages/omnidriver/tests/core/test_provider_ordering.py
git commit -m "feat(core): a profile declares what it provides and what it requires"
```

---

## Task 2: Declared-vs-implemented guard

Intent is supplied; the method set is discovered. `ENVIRONMENT_CONTRACT.md` §12 is the rule; this is its application.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py` (created here)
- Test: `packages/omnidriver/tests/core/test_provider_ordering.py`

**Interfaces:**
- Consumes: `PluginProfile.provides` (Task 1), `capability_seams.members_by_tier()` (Phase 0 Task 2).
- Produces: `provider_stack.implemented_capabilities(provider) -> frozenset[str]` and `provider_stack.check_provides(provider) -> list[str]` returning problems, empty when clean.

- [ ] **Step 1: Write the failing test**

Append to `test_provider_ordering.py`:

```python
def test_declared_provides_must_match_implementation():
    """A misspelled hook name must be an error, not a silent fallback."""
    from omnidriver.core import provider_stack

    class _Claims:
        """Declares command_authorization but misspells one of its members."""
        def get_solver_commands(self): return frozenset()
        def get_auxiliary_commands(self): return frozenset()
        def get_utility_manifest(self): return {}          # typo: no trailing s
        def get_utility_roots(self): return ()

        class _Profile:
            provides = frozenset({"command_authorization"})
        def get_profile(self): return self._Profile()

    problems = provider_stack.check_provides(_Claims())
    assert problems, "a misspelled member must be reported"
    assert any("get_utility_manifests" in p for p in problems)


def test_matching_declaration_reports_nothing():
    from omnidriver.core import provider_stack

    class _Honest:
        def get_solver_commands(self): return frozenset()
        def get_auxiliary_commands(self): return frozenset()
        def get_utility_manifests(self): return {}
        def get_utility_roots(self): return ()
        def get_environment_commands(self): return frozenset()
        def is_installed_environment_command(self, command): return False

        class _Profile:
            provides = frozenset({"command_authorization"})
        def get_profile(self): return self._Profile()

    assert provider_stack.check_provides(_Honest()) == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -k provides -v
```

Expected: FAIL — no module `omnidriver.core.provider_stack`.

- [ ] **Step 3: Create `provider_stack.py` with the guard**

```python
"""Compose N providers into one capability view.

Core owns composition; a provider never embeds another provider. Before this
module, each solver plugin embedded the environment adapter by hand -- and the
two did it differently, so `get_config_value_reader` returned a different
callable from each and `get_selected_start_time` was copy-pasted into both.
"""

from __future__ import annotations

from .capability_seams import collect_seams


def capability_members() -> dict[str, frozenset[str]]:
    """Map each capability name to the contract members it adapts."""
    return {
        seam.field: frozenset(
            name.strip() for name in seam.adapts.split(",") if name.strip()
        )
        for seam in collect_seams()
    }


def implemented_capabilities(provider) -> frozenset[str]:
    """Capabilities whose every member this provider actually implements."""
    return frozenset(
        capability
        for capability, members in capability_members().items()
        if all(callable(getattr(provider, member, None)) for member in members)
    )


def check_provides(provider) -> list[str]:
    """Return one problem per capability declared but not fully implemented.

    Declared-but-absent is the error this catches. Implemented-but-undeclared
    is NOT an error: a provider may implement a member for its own use without
    offering it to the stack.
    """
    declared = provider.get_profile().provides
    problems: list[str] = []
    members = capability_members()
    for capability in sorted(declared):
        missing = sorted(
            member for member in members.get(capability, ())
            if not callable(getattr(provider, member, None))
        )
        if missing:
            problems.append(
                f"provider declares provides: {capability!r} but does not "
                f"implement {missing}"
            )
    return problems
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -k provides -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/provider_stack.py \
        packages/omnidriver/tests/core/test_provider_ordering.py
git commit -m "feat(core): error when a provider declares a capability it does not implement"
```

---

## Task 3: Topological ordering

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py`
- Test: `packages/omnidriver/tests/core/test_provider_ordering.py`

**Interfaces:**
- Consumes: `PluginProfile.requires` (Task 1).
- Produces: `provider_stack.order_providers(providers) -> tuple[provider, ...]`, least-specific first. Raises `ValueError` on a cycle or a missing requirement.

- [ ] **Step 1: Write the failing test**

Append to `test_provider_ordering.py`:

```python
def _fake(plugin_id, requires=(), provides=frozenset()):
    class _P:
        class _Profile:
            pass
        def get_profile(self):
            profile = self._Profile()
            profile.requires = requires
            profile.provides = provides
            return profile
    p = _P()
    p.plugin_id = plugin_id
    return p


def test_ordering_puts_requirements_first():
    from omnidriver.core import provider_stack

    env = _fake("org.env")
    solver = _fake("org.solver", requires=("org.env",))
    ordered = provider_stack.order_providers([solver, env])
    assert [p.plugin_id for p in ordered] == ["org.env", "org.solver"]


def test_ordering_is_stable_for_independent_providers():
    from omnidriver.core import provider_stack

    a, b = _fake("org.a"), _fake("org.b")
    assert [p.plugin_id for p in provider_stack.order_providers([a, b])] == [
        "org.a", "org.b",
    ]
    assert [p.plugin_id for p in provider_stack.order_providers([b, a])] == [
        "org.a", "org.b",
    ]


def test_a_cycle_is_refused_by_name():
    from omnidriver.core import provider_stack

    a = _fake("org.a", requires=("org.b",))
    b = _fake("org.b", requires=("org.a",))
    with pytest.raises(ValueError, match="org.a"):
        provider_stack.order_providers([a, b])


def test_a_missing_requirement_is_refused_by_name():
    from omnidriver.core import provider_stack

    solver = _fake("org.solver", requires=("org.absent",))
    with pytest.raises(ValueError, match="org.absent"):
        provider_stack.order_providers([solver])
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -k ordering -v
```

Expected: FAIL — `order_providers` does not exist.

- [ ] **Step 3: Implement the sort**

Append to `provider_stack.py`:

```python
from graphlib import TopologicalSorter


def order_providers(providers) -> tuple:
    """Order providers least-specific first, by declared `requires:`.

    Stable: independent providers keep sorted-by-id order, so the same
    installation always composes identically. That matters because the stack
    digest hashes this order.
    """
    by_id = {provider.plugin_id: provider for provider in providers}
    graph: dict[str, set[str]] = {}
    for plugin_id, provider in sorted(by_id.items()):
        requires = tuple(provider.get_profile().requires)
        missing = sorted(set(requires) - set(by_id))
        if missing:
            raise ValueError(
                f"provider {plugin_id!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not installed"
            )
        graph[plugin_id] = set(requires)
    try:
        ordered = tuple(TopologicalSorter(graph).static_order())
    except Exception as exc:  # graphlib.CycleError
        raise ValueError(
            f"provider requirements form a cycle: {exc}"
        ) from exc
    return tuple(by_id[plugin_id] for plugin_id in ordered)
```

`graphlib.TopologicalSorter` is standard library from 3.9, so this adds no dependency. Sorting `by_id.items()` before building the graph is what makes independent order stable.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_ordering.py -v
```

Expected: all PASS. The cycle test must match on a provider id — `graphlib`'s `CycleError` names the cycle members, so wrapping its message preserves that.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/provider_stack.py \
        packages/omnidriver/tests/core/test_provider_ordering.py
git commit -m "feat(core): order providers by declared requirements, stably"
```

---

## Task 4: The six composition rules, as behaviour

These tests are **mechanism-independent** — spec §4.3 says any mechanism must satisfy them. Writing them before Task 6 means the spike's winner is graded against a fixed target.

**Files:**
- Create: `packages/omnidriver/tests/core/test_provider_composition_rules.py`

**Interfaces:**
- Consumes: `provider_stack.order_providers` (Task 3).
- Produces: nothing. This task is tests only; Task 6 makes them pass.

- [ ] **Step 1: Write the failing tests**

Create `packages/omnidriver/tests/core/test_provider_composition_rules.py`:

```python
"""The six composition rules from spec §4.3, as behaviour.

Deliberately mechanism-independent: whichever dispatch mechanism Phase 0's
spike selected, these must pass unchanged.
"""

import pytest

from omnidriver.core import provider_stack


class _Provider:
    """Minimal provider; attributes are set per test."""
    def __init__(self, plugin_id, provides=frozenset(), requires=(), **members):
        self.plugin_id = plugin_id
        self._provides = frozenset(provides)
        self._requires = tuple(requires)
        for name, value in members.items():
            setattr(self, name, value)

    def get_profile(self):
        profile = type("_P", (), {})()
        profile.provides = self._provides
        profile.requires = self._requires
        return profile


def _compose(*providers):
    return provider_stack.compose(provider_stack.order_providers(providers))


def test_sets_are_unioned():
    env = _Provider("org.env", get_environment_commands=lambda: frozenset({"blockMesh"}))
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_solver_commands=lambda: frozenset({"theSolver"}),
    )
    composed = _compose(env, solver)
    assert composed.command_authorization.environment_commands() == frozenset({"blockMesh"})
    assert composed.command_authorization.solver_commands() == frozenset({"theSolver"})


def test_maps_merge_and_an_unmarked_duplicate_is_an_error():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {"shared": {"from": "solver"}},
    )
    with pytest.raises(ValueError, match="shared"):
        _compose(env, solver).named_catalogs.catalogs()


def test_a_marked_override_wins():
    env = _Provider("org.env", get_named_catalogs=lambda: {"shared": {"from": "env"}})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {
            "shared": {"from": "solver", "overrides": "org.env"},
        },
    )
    assert _compose(env, solver).named_catalogs.catalogs()["shared"]["from"] == "solver"


def test_an_override_naming_a_provider_that_did_not_declare_it_is_an_error():
    """A stale override must surface when what it shadowed is removed."""
    env = _Provider("org.env", get_named_catalogs=lambda: {})
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_named_catalogs=lambda: {
            "gone": {"from": "solver", "overrides": "org.env"},
        },
    )
    with pytest.raises(ValueError, match="gone"):
        _compose(env, solver).named_catalogs.catalogs()


def test_single_values_take_the_most_specific_non_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: "solver-reader",
    )
    assert _compose(env, solver).config_value.reader() == "solver-reader"


def test_single_values_fall_through_a_none():
    env = _Provider("org.env", get_config_value_reader=lambda: "env-reader")
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_config_value_reader=lambda: None,
    )
    assert _compose(env, solver).config_value.reader() == "env-reader"


def test_diagnostics_concatenate_in_stack_order():
    env = _Provider(
        "org.env",
        get_base_mesh_geometry_diagnostics=lambda case_root: ("env-diag",),
    )
    solver = _Provider(
        "org.solver", requires=("org.env",),
        get_base_mesh_geometry_diagnostics=lambda case_root: ("solver-diag",),
    )
    composed = _compose(env, solver)
    assert composed.mesh_diagnostic_policy.base_geometry_diagnostics(None) == (
        "env-diag", "solver-diag",
    )


def test_two_providers_implementing_a_refusing_hook_is_an_error():
    a = _Provider("org.a", materialize_sweep_case=lambda **kw: None,
                  route_sweep_case_values=lambda **kw: {})
    b = _Provider("org.b", requires=("org.a",),
                  materialize_sweep_case=lambda **kw: None,
                  route_sweep_case_values=lambda **kw: {})
    with pytest.raises(ValueError, match="materialize_sweep_case"):
        _compose(a, b)


def test_zero_providers_implementing_a_refusing_hook_still_refuses_by_name():
    from omnidriver.core.sweep.sweep_expansion import SweepValidationError

    only = _Provider("org.only")
    with pytest.raises(SweepValidationError, match="materialize_sweep_case"):
        _compose(only).sweep_materializer.materialize(
            case_dir=None, routed={},
        )


def test_apply_and_target_paths_must_come_from_one_provider():
    """The refusing-hook rule is CROSS-member, not per-member.

    Added 2026-09-20 after the spike. Split across two providers, before-images
    are computed by a different provider than the one mutating, and rollback
    breaks silently. `_OverrideScopeAdapter.target_paths` already enforces this
    for a single plugin; composition must generalise it, not lose it.
    """
    a = _Provider("org.a", apply_overrides=lambda *a, **k: ())
    b = _Provider("org.b", requires=("org.a",),
                  get_override_target_paths=lambda *a, **k: ())
    with pytest.raises(ValueError, match="get_override_target_paths"):
        _compose(a, b)


def test_one_provider_supplying_both_is_accepted():
    both = _Provider(
        "org.both",
        apply_overrides=lambda *a, **k: (),
        get_override_target_paths=lambda *a, **k: (),
    )
    _compose(both)   # must not raise


def test_override_scopes_concatenate_across_providers():
    """`get_override_scopes` fits none of the original six shapes.

    Spike finding #1, 2026-09-20. Classified here as a concatenating sequence:
    scopes an environment provider offers and scopes a solver provider offers
    should BOTH be available, since they address different files. If Task 6
    concludes another shape is right, change this test and record why in the
    spec -- do not leave it unclassified.
    """
    env = _Provider("org.env", get_override_scopes=lambda: ("env-scope",))
    solver = _Provider("org.solver", requires=("org.env",),
                       get_override_scopes=lambda: ("solver-scope",))
    assert _compose(env, solver).override_scopes.scopes() == (
        "env-scope", "solver-scope",
    )


def test_a_case_file_path_declared_twice_is_an_error():
    """Spec §2.1: one fact, one declarer. Tolerance is how two sources of
    truth are born."""
    rule = type("_R", (), {"path": "system/controlDict", "role": "openfoam.control_dict"})()
    env = _Provider("org.env")
    env.get_profile().case_files = (rule,)
    solver = _Provider("org.solver", requires=("org.env",))
    solver.get_profile().case_files = (rule,)
    with pytest.raises(ValueError, match="system/controlDict"):
        _compose(env, solver)
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_composition_rules.py -v
```

Expected: every test FAILS — `provider_stack.compose` does not exist. Record the count; Task 6 turns it to zero.

- [ ] **Step 3: Commit the tests alone**

Committing failing tests deliberately: they are the specification Task 6 implements against, and committing them first means the spike's winner cannot be graded on a moving target.

```bash
git add packages/omnidriver/tests/core/test_provider_composition_rules.py
git commit -m "test(core): the six composition rules, before any mechanism exists"
```

---

## Task 5: `ProviderIdentity` and `StackIdentity`

Mechanism-independent: hashing does not depend on how dispatch works.

**Files:**
- Create: `packages/omnidriver/src/omnidriver/core/provider_identity.py`
- Create: `packages/omnidriver/tests/core/test_stack_identity.py`

**Interfaces:**
- Consumes: `provider_stack.order_providers` (Task 3), `PluginProfile.digest`.
- Produces: `ProviderIdentity(id, version, api_version, source, provider_digest)`; `StackIdentity(providers, composition_rule_version, capability_digest)` with `to_json()`. `DriverContext.identity` becomes a `StackIdentity` in Task 7.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_stack_identity.py`:

```python
"""The digest must distinguish stacks, not just plugins.

Two different stacks producing the same provenance record would make a run
irreproducible in exactly the way the digest exists to prevent.
"""

from omnidriver.core import provider_identity


def _pid(plugin_id, version="1.0", digest="d"):
    return provider_identity.ProviderIdentity(
        id=plugin_id, version=version, api_version="2",
        source="test", provider_digest=digest,
    )


def test_order_changes_the_digest():
    a, b = _pid("org.a"), _pid("org.b")
    first = provider_identity.build_stack_identity(
        providers=(a, b), resolutions={"x": ("org.b", "v")},
    )
    second = provider_identity.build_stack_identity(
        providers=(b, a), resolutions={"x": ("org.a", "v")},
    )
    assert first.capability_digest != second.capability_digest


def test_a_provider_that_wins_nothing_still_changes_the_digest():
    a = _pid("org.a")
    lone = provider_identity.build_stack_identity(
        providers=(a,), resolutions={"x": ("org.a", "v")},
    )
    with_loser = provider_identity.build_stack_identity(
        providers=(a, _pid("org.loser")), resolutions={"x": ("org.a", "v")},
    )
    assert lone.capability_digest != with_loser.capability_digest


def test_the_rule_version_changes_the_digest():
    a = _pid("org.a")
    args = dict(providers=(a,), resolutions={"x": ("org.a", "v")})
    assert (
        provider_identity.build_stack_identity(**args, composition_rule_version="1")
        .capability_digest
        != provider_identity.build_stack_identity(**args, composition_rule_version="2")
        .capability_digest
    )


def test_the_same_stack_is_stable():
    a, b = _pid("org.a"), _pid("org.b")
    args = dict(providers=(a, b), resolutions={"x": ("org.b", "v")})
    assert (
        provider_identity.build_stack_identity(**args).capability_digest
        == provider_identity.build_stack_identity(**args).capability_digest
    )


def test_to_json_names_who_answered_each_capability():
    a = _pid("org.a")
    identity = provider_identity.build_stack_identity(
        providers=(a,), resolutions={"dictionaries": ("org.a", "v")},
    )
    payload = identity.to_json()
    assert payload["resolutions"]["dictionaries"] == "org.a"
    assert [p["id"] for p in payload["providers"]] == ["org.a"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_stack_identity.py -v
```

Expected: FAIL — no module `provider_identity`.

- [ ] **Step 3: Implement**

Create `provider_identity.py`:

```python
"""Identity over a composed stack, not a single plugin.

`PluginIdentity` covered one plugin, because `DriverContext` held one. Under
composition two different stacks could otherwise produce the same provenance
record, and the digest is what makes a run reproducible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

#: Bumped whenever a composition rule in `provider_stack` changes meaning.
#: Without it, the same providers at the same versions would digest
#: identically across a semantic change core made -- the one case no other
#: element of the digest covers.
COMPOSITION_RULE_VERSION = "1"


@dataclass(frozen=True)
class ProviderIdentity:
    """What `PluginIdentity` was, now one per provider."""

    id: str
    version: str
    api_version: str
    source: str
    provider_digest: str

    def to_json(self) -> dict[str, str]:
        return {
            "id": self.id,
            "version": self.version,
            "api_version": self.api_version,
            "source": self.source,
            "provider_digest": self.provider_digest,
        }


@dataclass(frozen=True)
class StackIdentity:
    """Identity of a composed stack.

    `resolutions` maps each capability to the provider that answered it. It is
    what lets a provenance record say WHICH adapter answered -- which the
    single-plugin identity could not.
    """

    providers: tuple[ProviderIdentity, ...]
    composition_rule_version: str
    capability_digest: str
    resolutions: dict[str, str]

    def to_json(self) -> dict:
        return {
            "providers": [p.to_json() for p in self.providers],
            "composition_rule_version": self.composition_rule_version,
            "capability_digest": self.capability_digest,
            "resolutions": dict(sorted(self.resolutions.items())),
        }


def build_stack_identity(
    *,
    providers: tuple[ProviderIdentity, ...],
    resolutions: dict[str, tuple[str, str]],
    composition_rule_version: str = COMPOSITION_RULE_VERSION,
) -> StackIdentity:
    """Hash the composition RESULT, not merely its inputs.

    `resolutions` is capability -> (winning provider id, that capability's
    resolved-content digest). Only the three capabilities the single-plugin
    digest already covered carry a real content digest; the rest carry a
    placeholder and contribute only their winner.

    Known limit: a content change inside a non-digested capability, in an
    editable install with no version bump, is invisible here. Recorded
    2026-09-20 rather than discovered later; see spec §4.4.
    """
    payload = {
        "composition_rule_version": composition_rule_version,
        "providers": [
            [p.id, p.version, p.provider_digest] for p in providers
        ],
        "resolutions": [
            [capability, winner, content]
            for capability, (winner, content) in sorted(resolutions.items())
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return StackIdentity(
        providers=providers,
        composition_rule_version=composition_rule_version,
        capability_digest=digest,
        resolutions={
            capability: winner for capability, (winner, _) in resolutions.items()
        },
    )
```

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_stack_identity.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/provider_identity.py \
        packages/omnidriver/tests/core/test_stack_identity.py
git commit -m "feat(core): identity over a composed stack, naming who answered what"
```

---

## Task 6: The composition mechanism — **gated on Phase 0 Task 15**

The only task in this plan whose implementation the spike decides. Its target is fixed: make Task 4's committed tests pass without editing them.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Test: `packages/omnidriver/tests/core/test_provider_composition_rules.py` (unchanged)

**Interfaces:**
- Consumes: `order_providers` (Task 3), `capability_members()` (Task 2).
- Produces: `provider_stack.compose(ordered_providers) -> PluginCapabilities`, and `provider_stack.resolutions(ordered_providers) -> dict[str, tuple[str, str]]` for Task 5's digest.

- [ ] **Step 1: Read the spike's recommendation**

```bash
cat docs/superpowers/specs/2026-09-20-composition-mechanism-spike.md
```

Do not start until that document names a winner and gives its reason. If it says neither prototype met the success criterion, **stop**: spec §4.3's rules are wrong somewhere, and this plan needs revising before implementation.

- [ ] **Step 2: Run Task 4's tests to see the target**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_composition_rules.py -v
```

Expected: every test fails on `provider_stack.compose`. That count is the target.

- [ ] **Step 3A: If the spike chose "own it"**

Implement `compose` in `provider_stack.py`. Classify each capability member by shape using a table keyed on the capability's `:adapts:` members, and build a composed adapter per capability:

```python
#: Composition rule per declaration shape (spec §4.3). A member absent here
#: is an error at import, not a silent default -- an unclassified member is
#: how a rule gets chosen by accident.
_SHAPE = {
    "set": ("solver_commands", "auxiliary_commands", "environment_commands"),
    "map": ("utility_manifests", "dict_groups", "named_catalogs", "catalog"),
    "single": ("reader", "selected_start_time", "conventions"),
    "sequence": ("base_geometry_diagnostics", "diagnostics"),
    "exclusive": ("materialize", "route", "apply", "target_paths"),
}
```

Then one combinator per shape: `_union`, `_merge_with_override`, `_first_non_none`, `_concat`, `_exactly_one`. Each takes the ordered providers and the member name.

`_merge_with_override` implements the override marker: a value carrying `overrides: <provider id>` replaces that provider's key; an unmarked duplicate raises; a marker naming a provider that did not declare the key raises.

**Two rules the `_SHAPE` table above does not cover. Added 2026-09-20 after the
spike and the Phase 1 re-audit.**

**(a) The refusing-hook rule is cross-member, not per-member.** `apply_overrides`
and `get_override_target_paths` must come from the **same** provider. Split
across two, before-images are computed by a different provider than the one
mutating, and rollback silently breaks.

You are not inventing this check — `_OverrideScopeAdapter.target_paths` already
enforces it for the single-plugin case:

```python
if callable(getattr(self.plugin, "apply_overrides", None)):
    raise ValueError(
        f"plugin {self.plugin.plugin_id!r} implements apply_overrides() but "
        "does not declare get_override_target_paths(); crash-safe --apply is "
        "unavailable"
    )
```

Generalise it to N providers: whichever provider wins `apply_overrides` must
also win `get_override_target_paths`. Two providers each supplying one is an
error naming both.

**(b) `get_override_scopes` fits none of the six shapes.** The spike found this
by building. It is not a set, map, single value, diagnostic sequence, refusing
hook, or case-file rule. Classify it explicitly — do not let it fall through a
default. Its natural shape is a concatenating sequence, since scopes from an
environment provider and a solver provider should both be offered, but decide
that deliberately and record the reason.

- [ ] **Step 3B: If the spike chose pluggy**

Add `pluggy` to `packages/omnidriver/pyproject.toml` dependencies. Express each capability member as a hookspec, using `firstresult=True` for the `single` shape and the default collect-all for `sequence`. Implement `set`, `map` and `exclusive` as post-processing over the collected results, since pluggy has no built-in for them.

`capability_seams.parse_fields` reads Protocol docstrings. Preserve it by keeping the Protocols as documentation even where hookspecs carry the dispatch, or port the `:adapts:`/`:status:` block onto the hookspecs and update `collect_seams` to read them there. **Do not delete the seam table** — `scripts/export-capability-seams.py --check` is a required gate.

- [ ] **Step 4: Run Task 4's tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_provider_composition_rules.py -v
```

Expected: all PASS, with **no edits to that file**. If a test needs changing to pass, either the rule in spec §4.3 is wrong — amend the spec first, with a dated correction — or the implementation is.

- [ ] **Step 5: Implement `resolutions` for the digest**

```python
def resolutions(ordered_providers) -> dict[str, tuple[str, str]]:
    """capability -> (winning provider id, resolved-content digest).

    Content digests only for the three capabilities the single-plugin digest
    already covered -- profile, dictionaries, manifest. The rest carry the
    placeholder "-" and contribute only their winner, per spec §4.4's cost
    trade-off.
    """
```

- [ ] **Step 6: Run everything and commit**

```bash
python -m pytest packages/ -q -m "not slow"
python3 scripts/export-capability-seams.py --check
git add packages/omnidriver/src/omnidriver/core/provider_stack.py \
        packages/omnidriver/src/omnidriver/core/plugin_capabilities.py
git commit -m "feat(core): compose N providers per capability"
```

---

## Task 7: `DriverContext.providers`

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_discovery.py`
- Test: `packages/omnidriver/tests/core/test_core_context_is_explicit.py`
- Test: `packages/omnidriver/tests/core/test_plugin_capabilities.py` — **this guard WILL break; see below**

**A guard that breaks, identified in advance.** `test_plugin_capabilities.py::test_context_exposes_focused_adapters_without_replacing_public_plugin`
asserts `context.plugin is plugin`, reconstructs `DriverContext(plugin, context.identity)`
**positionally**, and asserts `[f.name for f in fields(reconstructed)] == ["plugin", "identity"]`.
All three break when the field becomes `providers`. The spike hit exactly this.
Update the test to the new arity — do not let it fail as a surprise, and do not
weaken what it checks: it exists to prove the context does not hide the
provider behind the adapters, and that property survives the change.

**Interfaces:**
- Consumes: `provider_stack.compose`, `provider_stack.resolutions` (Task 6); `provider_identity.build_stack_identity` (Task 5).
- Produces: `DriverContext(providers: tuple[SolverPlugin, ...], identity: StackIdentity)`; `driver_context(*providers, source)`.

- [ ] **Step 1: Write the failing test**

Append to `test_core_context_is_explicit.py`:

```python
def test_a_context_holds_an_ordered_stack():
    from omnidriver.core.plugin_interface import DriverContext
    import dataclasses

    fields = {f.name for f in dataclasses.fields(DriverContext)}
    assert "providers" in fields
    assert "plugin" not in fields, (
        "a single `plugin` field is the arity assumption this phase removes"
    )


def test_identity_names_every_provider(two_provider_context):
    payload = two_provider_context.identity.to_json()
    assert len(payload["providers"]) == 2
    assert payload["resolutions"], "the identity must record who answered what"
```

Add a `two_provider_context` fixture beside it, composing the OpenFOAM
environment adapter with whichever solver adapter is installed, skipping when
fewer than two are.

**Build raw plugin instances, not contexts.** Do NOT wrap the existing
`driver_context_for_installed_plugins` fixture in `conftest.py` — it returns
built single-plugin `DriverContext` objects, and you need the plugin instances
themselves to pass into `driver_context(*providers, ...)`. Mirror
`plugin_discovery.load_discovered_plugin`'s `entry_point.load()()` pattern
rather than writing new discovery: `discover_plugins()` returns `EntryPoint`
objects, not classes, and that trap has already caught two tasks.

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_core_context_is_explicit.py -k stack -v
```

Expected: FAIL — `providers` is not a field.

- [ ] **Step 3: Change the dataclass**

In `plugin_interface.py`:

```python
@dataclass(frozen=True)
class DriverContext:
    """Per-operation provider stack for solver-specific behaviour.

    Immutable and threaded through planning, discovery and execution, as
    before. What changed 2026-09-20 is arity: this held a single `plugin`
    because the migration it came from replaced a process-global active
    plugin, and that migration was about isolation, not about how many
    providers there are. Composition was consequently done by hand inside each
    solver plugin, differently in each.
    """

    providers: tuple[SolverPlugin, ...]
    identity: "StackIdentity"

    @cached_property
    def capabilities(self) -> "PluginCapabilities":
        from .provider_stack import compose

        return compose(self.providers)
```

Change `driver_context` to accept `*providers`, validate each with `validate_plugin`, run `check_provides` on each, `order_providers` them, enforce the single-declarer rule over their combined `case_files`, and build a `StackIdentity`.

- [ ] **Step 4: Make discovery compose instead of refusing**

In `plugin_discovery._default_selection`, replace the `LookupError` raised when more than one adapter resolves with composition: order them and return the stack. Keep an explicit `--plugin` able to narrow the stack. The old error existed only because two adapters could not coexist.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_core_context_is_explicit.py -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`. Call sites reading `context.plugin` will fail — that is the point. Every core module already goes through `.capabilities`, so the failures should be tests and adapters only.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_interface.py \
        packages/omnidriver/src/omnidriver/core/plugin_discovery.py \
        packages/omnidriver/tests/core/test_core_context_is_explicit.py
git commit -m "feat(core): DriverContext holds an ordered provider stack"
```

---

## Task 8: Extend the dependency boundary to adapters

The guard that kept core clean does not cover `omnidriver.openfoam`, which is exactly why two `getattr` back-channels grew there.

**Files:**
- Modify: `packages/omnidriver/tests/core/test_plugin_dependency_boundary.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing.

- [ ] **Step 1: Extend the guard**

Add to that file:

```python
ADAPTER_PACKAGES = (
    "packages/omnidriver-openfoam/src",
    "packages/omnidriver-cardiacfoam/src",
    "packages/omnidriver-cardiaccore/src",
)


def test_no_adapter_reaches_into_the_context_providers():
    """Adapters go through `.capabilities` too.

    Core has been clean since Phase 2 Task 7, but this guard never covered the
    adapters -- so `openfoam_environment` grew a private, unversioned plugin
    ABI (`get_openfoam_bashrc`, `configure_execution_environment`) that no
    Protocol declared and nothing validated.
    """
    offenders = []
    for package in ADAPTER_PACKAGES:
        for path in Path(package).rglob("*.py"):
            text = path.read_text()
            for needle in ("driver_context.plugin", "driver_context.providers"):
                if needle in text and "test" not in path.parts:
                    offenders.append(f"{path}: {needle}")
    assert offenders == [], offenders
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver/tests/core/test_plugin_dependency_boundary.py -v
```

Expected: FAIL naming `openfoam_environment.py` twice.

- [ ] **Step 3: Delete the back-channels**

In `openfoam/openfoam_environment.py`, remove `getattr(driver_context.plugin, "get_openfoam_bashrc", None)` from `load_openfoam_environment` and `getattr(driver_context.plugin, "configure_execution_environment", None)` from `_configure_plugin_environment`.

Both concerns now compose: cardiacFoam declares `provides: [environment_preflight]` and implements `get_configured_environment` / `get_loaded_environment`, and the stack's `first non-None` rule gives cardiacFoam's answer precedence over OpenFOAM's. Delete `configure_execution_environment` and `get_openfoam_bashrc` from `CardiacFoamPlugin`, folding their bodies into the two declared hooks.

- [ ] **Step 4: Run the tests**

```bash
python -m pytest packages/omnidriver/tests/core/test_plugin_dependency_boundary.py -v
python -m pytest packages/ -q -m "not slow"
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add packages/omnidriver/tests/core/test_plugin_dependency_boundary.py \
        packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam_environment.py \
        packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py
git commit -m "fix(openfoam,cardiacfoam): delete the private plugin ABI, compose instead"
```

---

## Task 9: Delete the hand-embedding

The payoff task. `CardiacCorePlugin._openfoam` and its nine delegations go, and `step --strict --apply` starts working.

**Files:**
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.py`
- Modify: `packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/plugin.yaml`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/plugin.yaml`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/openfoam-environment.yaml`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing new; deletes `CardiacCorePlugin._openfoam` and nine methods.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver-cardiaccore/tests/test_apply_works_through_the_stack.py`:

```python
"""cardiacCore gains --apply by composition, not by writing an implementation.

Six one-line delegations were never written, so `legacy_apply_overrides`
raised and strict applying was refused for this adapter entirely -- while the
package maintained parallel override machinery reachable only through
`TutorialSpec.apply_case`.
"""

import inspect

from omnidriver.cardiaccore.plugin import CardiacCorePlugin


def test_the_plugin_no_longer_embeds_an_environment_adapter():
    source = inspect.getsource(CardiacCorePlugin)
    assert "OpenFOAMEnvironmentPlugin()" not in source, (
        "a provider must not embed another provider"
    )
    assert "_openfoam" not in source


def test_applying_overrides_is_supported(cardiaccore_stack_context, tmp_case):
    scopes = cardiaccore_stack_context.capabilities.override_scopes
    scopes.apply({}, case_root=tmp_case)   # must not raise
```

Build `cardiaccore_stack_context` as a fixture composing the OpenFOAM environment adapter with `CardiacCorePlugin`, and `tmp_case` as a minimal case directory.

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/test_apply_works_through_the_stack.py -v
```

Expected: both FAIL.

- [ ] **Step 3: Declare the stack in each manifest**

`openfoam-environment.yaml` gains:

```yaml
provides:
  - command_authorization
  - case_runtime_conventions
  - environment_preflight
  - case_introspection
  - dict_diagnostics
  - override_scopes
  - dict_regeneration
  - mesh_diagnostic_policy
  - config_value
  - case_files
```

**Do NOT generate `provides:` from `implemented_capabilities()`.** Measured
2026-09-20 by Phase 1 Task 2: that function reports capabilities by **presence**
of their members, which is right for catching a misspelled hook but wrong for
declaring intent. It reports 17 capabilities for `openfoam-environment` — while
Phase 0 Task 4 measured nine of that adapter's members as **hollow stubs**
returning `frozenset()` and `{}`.

A `provides:` entry means "this provider genuinely answers this capability". A
stub declared there lands in the stack digest's `resolutions` record as the
provider that answered — which is a false provenance claim, and the digest is
what makes a run reproducible.

**Correction, 2026-09-22 (final whole-branch review, Finding 4).** The
premise above is false, discovered too late to change this task's scope
(the re-audit it justifies was already done and reviewed). `resolutions()`
(`provider_stack.py`) never reads `provides:` — it picks each capability's
winner purely by which provider has a callable member, independent of
whether that provider declared the capability. So a stub withheld from
`provides:` by this task's own re-audit can still win `resolutions()`, and
the stack digest, if it is the most-specific implementer: the exact false
provenance claim this paragraph describes still happens, just silently. The
re-audit itself was not wasted work — `provides:`/`check_provides()` still
needed it, for the reason gate 1/gate 2 give in each manifest's own comment
block — it just does not protect the digest the way this paragraph claims.
Not fixed (here or in `resolutions()` itself, which would change every
`capability_digest` this codebase has ever computed); see
`ARCHITECTURE.md`'s "Provider composition" > "provides: / requires:" section
for the full explanation.

So: cross-reference the stub census below against `implemented_capabilities()`,
and declare only capabilities the provider really answers. Where the two
disagree, the census wins and the stub gets deleted.

Verify that list against `provider_stack.implemented_capabilities(OpenFOAMEnvironmentPlugin())` rather than trusting it — Task 2's guard errors on any it does not fully implement.

`cardiaccore/plugin.yaml` and `cardiacfoam/plugin.yaml` each gain:

```yaml
requires:
  - org.omnidriver.openfoam.environment
provides:
  - dictionaries
  - tutorials
  - named_catalogs
  # plus whatever implemented_capabilities() reports for that plugin
```

Per spec §2.1, remove every `case_profile.dictionaries` entry the environment
profile already declares. **Verified 2026-09-20 against all three manifests —
this is not uniform, and the earlier "all three" instruction was wrong:**

| manifest | remove | keep, and why |
|---|---|---|
| `cardiacfoam/plugin.yaml` | `system/controlDict` (exact duplicate, same role), `Allrun` (exact duplicate, same role `openfoam.entrypoint`) | `constant/electroProperties` and `constant/physicsProperties` — these are **not** duplicates of the environment's bare `constant` entry. Different path, different role (`plugin.configuration`), finer granularity. cardiacfoam declares no bare `constant` rule at all. |
| `cardiaccore/plugin.yaml` | `system/controlDict` and `constant` (exact duplicates), plus `Allrun` | — |
| `openfoam-environment.yaml` | nothing — it is the declarer | all three |

cardiaccore's `Allrun` is a **role-mismatched** duplicate: same path, but role
`cardiaccore.entrypoint` against the environment's `openfoam.entrypoint`. Still
a single-declarer violation, so it still goes — but before deleting, grep for
any consumer keying off the literal string `cardiaccore.entrypoint`. Case
entrypoint resolution reads `CaseRuntimeConventions.case_entrypoints`, not this
role, so that consumer is safe; confirm no other is.

**Resolve `config_value`'s divergence here (reported by Phase 0 Task 9,
2026-09-20).** The two adapters return different callables for this one seam:

| adapter | returns | `scope` support |
|---|---|---|
| `OpenFOAMEnvironmentPlugin` | `mutators.read_foam_entry(path, key, *, scope=None)` | yes |
| `CardiacFoamPlugin` | `config_values.openfoam_config_value_reader()`, a closure `_read(path, key)` | **no — silently dropped** |

The composed seam must return the **wider** one, or an equivalent that forwards
`scope`. The narrow closure exists only because `ConfigValueCapability.reader()`
had no fixed signature to conform to; nothing about its callers requires
dropping `scope`. A composed seam that silently discards a capability one
provider offers is the same defect class as two declarations of one fact.

Delete `config_values.openfoam_config_value_reader` once cardiacFoam stops
returning it, unless something else consumes it — check before deleting.

**Measured stub census, from Phase 0 Task 4's Step 4b (2026-09-20).** Do not
re-derive this; it was produced by comparing each plugin's shipped
implementation against what its fallback returns.

| provider | real implementations | hollow stubs, equal to the fallback |
|---|---|---|
| `openfoam-environment` | none of the nine | **all nine** — `get_auxiliary_commands`, `get_dict_entry_catalog`, `get_override_schema`, `get_run_document_config_schema`, `get_samplable_fields`, `get_solver_commands`, `get_utility_manifests`, `get_utility_roots`, `resolve_case_models` |
| `cardiaccore` | `get_auxiliary_commands`, `get_dict_entry_catalog`, `get_run_document_config_schema`, `get_utility_manifests` | `get_override_schema`, `get_samplable_fields`, `get_solver_commands`, `get_utility_roots`, `resolve_case_models` |
| `cardiacfoam` | **all nine** | none |

Every stub in that table exists only because the pre-Task-4 validator demanded
the member. Task 4 demoted all thirteen, so the stubs are now deletable — and
deleting `openfoam-environment`'s nine is the concrete evidence that the
environment adapter was being forced to impersonate a solver plugin.

Delete the stubs in this table alongside the delegations below. Leave every
"real implementation" untouched.

- [ ] **Step 4: Delete the delegations**

From `CardiacCorePlugin`, delete `_openfoam` and these nine methods, which now compose from the environment provider: `get_environment_commands`, `is_installed_environment_command`, `get_case_runtime_conventions`, `get_selected_start_time`, `get_environment_diagnostics`, `get_loaded_environment`, `get_configured_environment`, `get_function_object_field_diagnostics`, `get_case_dict_key_diagnostics`.

From `CardiacFoamPlugin`, delete the function-local `omnidriver.openfoam` imports for the same composed concerns — `command_authorization`, `profile`, `config_values`, `time_selection`, `case_runtime_conventions`. Keep imports for concerns cardiacFoam genuinely extends rather than delegates, such as `mesh_geometry`.

- [ ] **Step 5: Run the tests**

```bash
python -m pytest packages/omnidriver-cardiaccore/tests/ -v
python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
```

Expected: `0 failed`.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-cardiaccore/ packages/omnidriver-cardiacfoam/ \
        packages/omnidriver-openfoam/
git commit -m "refactor(adapters): compose the environment provider, stop embedding it"
```

---

## Task 10: The four items Phase 0 deferred

Each needs providers to exist, which they now do.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver/src/omnidriver/core/capability_manifest.py`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/registry.py`

**Interfaces:**
- Consumes: the composed capabilities.
- Produces: `build_capability_manifest` moves from plugin-called to core-called.

- [ ] **Step 1: Write the failing tests**

Create `packages/omnidriver/tests/core/test_deferred_duplicate_intakes.py`:

```python
def test_config_schema_has_one_source(stack_context):
    """Two capabilities answered "what may config contain"."""
    caps = stack_context.capabilities
    assert (
        caps.override_schema.config_schema("any", {})
        == caps.run_document_configuration.schema()
    ), "the two config schemas must no longer be independently authored"


def test_core_builds_the_capability_manifest(stack_context):
    """The plugin must not assemble what core can compose.

    The round trip delivered six declarations to core twice, and the manifest
    copy was what landed in the identity digest.
    """
    import inspect
    from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

    source = inspect.getsource(CardiacFoamPlugin.get_capabilities)
    assert "build_capability_manifest" not in source


def test_a_case_is_recognised_by_one_predicate(stack_context):
    caps = stack_context.capabilities
    assert hasattr(caps.case_compatibility, "is_case")
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest packages/omnidriver/tests/core/test_deferred_duplicate_intakes.py -v
```

- [ ] **Step 3: Derive one config schema from the other**

`RunDocumentConfigurationCapability.schema()` is what core validates against; `OverrideSchemaCapability.config_schema()` is agent-facing documentation. Make the documentation derive from the validated schema rather than be authored separately, so they cannot diverge.

**Resolve this isolation narrowing while you are here (found by the Phase 0
review, 2026-09-20).** Phase 0 Task 12 made `_CapabilityManifestAdapter.manifest`
a `cached_property`; Task 13 added `dict(...)` copies inside
`CardiacFoamPlugin.get_capabilities`. Together they protect the module-level
`IONIC_MODEL_CATALOG` — the copy happens before caching, so the real catalogue
is never the cached object — but they narrow a second property: within one
`DriverContext`, every `.manifest()` caller now shares one copy, where each
previously got a fresh one. Three consumers call it per context
(`dict_entries`, `strict_planning`, `introspection`), and the `dict()` wrapping
at two of those copies only the top level, not `manifest["ionic_models"]`.

No code mutates it today, so nothing breaks — but `DriverContext` exists to stop
one operation affecting another's, and this weakens that within a context.
Moving assembly into core removes the shared-mutable entirely: core builds the
manifest from capability reads it already holds, so there is no plugin-owned
dict to share. Verify that outcome rather than re-adding a defensive copy.

- [ ] **Step 4: Move manifest assembly into core**

`build_capability_manifest` currently takes arguments the plugin gathers. Change it to take the composed `PluginCapabilities` and read each declaration once. `CardiacFoamPlugin.get_capabilities` and `CardiacCorePlugin.get_capabilities` then return only what core cannot compose — the domain model catalogues — and core merges.

- [ ] **Step 5: Collapse the case predicate**

`registry._is_case_directory` is `has_case_marker(...) or _has_entrypoint(...)`. Add one composed `case_compatibility.is_case(case_root)` that consults marker, entrypoint and `generated_case_markers` in one place, and have `registry` call only that.

- [ ] **Step 6: Run everything and commit**

```bash
python -m pytest packages/ -q -m "not slow"
git add packages/omnidriver/src/omnidriver/core/ \
        packages/omnidriver-cardiacfoam/ packages/omnidriver-cardiaccore/ \
        packages/omnidriver/tests/core/test_deferred_duplicate_intakes.py
git commit -m "refactor(core): collapse the four duplicate intakes providers unblocked"
```

---

## Task 11: `legacy_dict_key_scanner` gets a capability

A permanently-active "fallback" with no hook, no capability and no probe, called unconditionally by `strict_planning._catalog_diagnostics`. No adapter can override it.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_capabilities.py`
- Modify: `packages/omnidriver/src/omnidriver/core/strict_planning.py`
- Modify: `packages/omnidriver/src/omnidriver/core/compatibility.py`

**Interfaces:**
- Consumes: `capability_seams.TIERS`.
- Produces: `DictKeyScannerCapability` with member `scan(...)`, adapting `get_dict_key_scanner`, `:status: optional-neutral`, fallback `legacy_dict_key_scanner` returning the existing `_EmptyReport`.

- [ ] **Step 1: Write the failing test**

```python
def test_dict_key_scanning_is_overridable():
    """A fallback no adapter can replace is not a seam."""
    from omnidriver.core import plugin_capabilities

    assert hasattr(plugin_capabilities, "DictKeyScannerCapability")
    assert "dict_key_scanner" in plugin_capabilities.PluginCapabilities.__annotations__
```

- [ ] **Step 2: Run to verify it fails, then implement**

Add the Protocol with its four docstring fields, the adapter, and the `PluginCapabilities` field, following the shape Phase 0 Task 9 established for `ConfigValueCapability`. Change `strict_planning._catalog_diagnostics` to call `driver_context.capabilities.dict_key_scanner.scan(...)` instead of importing `compatibility.legacy_dict_key_scanner` at module scope. Have the OpenFOAM provider implement `get_dict_key_scanner` returning `openfoam.dict_keys_scanner`'s real scanner — which currently has **no runtime importer at all**.

- [ ] **Step 3: Run, regenerate the table, commit**

```bash
python -m pytest packages/ -q -m "not slow"
python3 scripts/export-capability-seams.py && python3 scripts/export-capability-seams.py --check
git add packages/omnidriver/src/omnidriver/core/ packages/omnidriver-openfoam/ ARCHITECTURE.md
git commit -m "feat(core): dict-key scanning becomes a real, overridable seam"
```

---

## Task 12: Document the composition contract

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `future/ENVIRONMENT_CONTRACT.md`

- [ ] **Step 1: Add a composition section to `ARCHITECTURE.md`**

Above the generated seam table, add a hand-written section stating the six rules, the `provides:`/`requires:` keys, and the single-declarer rule. Mark clearly that it is outside the generated block.

- [ ] **Step 2: Record the correction in the environment contract**

`ENVIRONMENT_CONTRACT.md` §6 says the `GenericEnvironmentPlugin` rename is blocked on §5b's trust boundary. Under composition the environment adapter is no longer a competing plugin, which changes that assessment. Append, dated:

```
**Amended 2026-09-20:** Phase 1 of the provider-composition spec makes the
environment adapter a composed provider rather than a competing entry in the
same discovery group. The rename's original blocker -- that the generic
plugin's value was supplying `allowed_commands` from a hardcoded set -- is
unchanged, but "substitution, not composition" no longer describes the
architecture. Re-evaluate §6 against the stack before acting on it.
```

- [ ] **Step 3: Run the documentation guards and commit**

```bash
python -m pytest packages/omnidriver/tests/core/test_documentation_inventory_contracts.py -v
python3 scripts/export-capability-seams.py --check
git add ARCHITECTURE.md future/ENVIRONMENT_CONTRACT.md
git commit -m "docs: the composition contract, and a dated amendment to §6"
```

---

## Task 13: All four shapes

- [ ] **Step 1: Rebuild the wheel**

```bash
rm -rf /tmp/wheeltest /tmp/wheelenv
python -m build --outdir /tmp/wheeltest packages/omnidriver
uv venv --python 3.11 /tmp/wheelenv
VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-*.whl[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: `0 failed`. `provider_stack` calls `collect_seams()`, which reads Protocol annotations rather than repo files, so it is wheel-safe — but verify rather than assume.

- [ ] **Step 2: Core alone**

```bash
/tmp/odcore/bin/python -m pytest packages/omnidriver/tests -q
```

Expected: `0 failed`. With no adapter installed, `discover_plugins()` returns nothing and every stack test must skip rather than fail.

- [ ] **Step 3: All four packages, and the static gates**

```bash
python -m pytest packages/ -q -m "not slow"
python3 scripts/check-import-boundaries.py
python3 scripts/export-capability-seams.py --check
```

Expected: all clean, waiver list still empty.

- [ ] **Step 4: Confirm the payoff**

```bash
python -m omnidriver step --plugin cardiaccore --strict --apply <a cardiaccore case>
git diff --stat main -- packages/omnidriver-cardiaccore/src/omnidriver/cardiaccore/workflows/
```

Expected: the command succeeds, and the second shows no change to cardiacCore's override machinery. Phase 1's thesis was that the missing capability was a composition gap, not missing cardiacCore code.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: Phase 1 passes in all four verification shapes"
```
