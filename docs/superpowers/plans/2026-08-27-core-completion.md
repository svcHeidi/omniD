# Core Completion — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four claims `omnidriver` already advertises actually true —
that a plugin can be selected by name, that the declared role vocabulary means
something, that a case's entrypoint is plugin-declared rather than hardcoded,
and that core imports from a built wheel.

**Architecture:** No new abstractions. Every change either fixes a string, wires
an existing `CaseFileRule.role` to the code that should already have been
reading it, moves a module-scope filesystem walk behind a function call, or
ports a plugin method that the legacy `driverFoam` tree already has. Design
rationale and the ownership rule these changes serve:
[`future/ENVIRONMENT_CONTRACT.md`](../../../future/ENVIRONMENT_CONTRACT.md).

**Tech Stack:** Python ≥3.11 (verify on 3.13, not the repo's own 3.14 `.venv`),
pytest, `tomllib`, `importlib.metadata`, setuptools.

---

## The core goal — what "finished" means

> **`omnidriver` can be installed from a wheel, on its own, and used to plan and
> run a case through a plugin the user selects by name — with no cardiacFoam
> code present and no cardiacFoam semantics silently applied.**

Six properties, each a command with a pass condition. Phase 1 delivers the two
marked ✦; the rest are Phases 2–3.

| # | Property | Check | Phase |
|---|---|---|---|
| G1 ✦ | Core imports from a **non-editable wheel**, from a neutral cwd | build wheel, install, `pkgutil.walk_packages` every module | 1 |
| G2 ✦ | A plugin resolves by **entry-point name** | `load_plugin_context("cardiacfoam")` returns a context | 1 |
| G3 | Core's own suite **runs** alone with zero failures | `pytest packages/omnidriver/tests` in a core-only venv | 2 |
| G4 | Core's CLI is usable alone | `python -m omnidriver --help && … list && … plugins` exit 0 | 2 |
| G5 | No `"org.cardiacfoam"` anywhere in `packages/omnidriver/src` | `grep -c` → 0 | 2 |
| G6 | Declared deps are imported; licence declared; CI tests a wheel | dependency guard test + `LICENSE` + new CI legs | 3 |

Current state: G1 ✗, G2 ✗, G3 ✗ (161 failed), G4 ✗, G5 ✗ (20), G6 ✗.

### Phase roadmap

| Phase | Tasks | Delivers | Risk |
|---|---|---|---|
| **1 (this plan)** | 1–5 | G1, G2; role vocabulary enforced; entrypoint plugin-declared; 18 of 20 cardiac gates provably dead | Low — no behaviour changes |
| 2 | explicit `DriverContext` (21 sites), `get_phases()` + `phase_order`, delete the 20 gates, tighten the import gate, fix `tests/equivalence`, relocate `spatial_pacing` + the three C++ scanners | G3, G4, G5 | Medium — `get_phases` and the context conversion both have real behavioural surface |
| 3 | trust-boundary seam (`CASE_SCRIPT_COMMANDS`, `CORE_NEUTRAL_COMMANDS`, `$FOAM_APPBIN`), `GenericEnvironmentPlugin` rename, licence, deps, CI legs | G6 | Medium — §5b of the spec; needs its own threat model |

Phases 2 and 3 get their own plans once Phase 1 lands. They are listed here so
the endpoint is visible, not so they can be started from this document.

---

## Global Constraints

- **Verify in a clean 3.13 virtualenv, never `~/omnidriver/.venv`.** That venv
  runs 3.14 (which hides annotation-evaluation bugs via PEP 649) and holds a
  stale `omnidriver-cardiac` editable install alongside `omnidriver-cardiacfoam`.
  Both export the entry-point name `cardiacfoam`, which will corrupt Task 1's
  results.
  ```bash
  rm -rf /tmp/od_all && /opt/homebrew/bin/python3.13 -m venv /tmp/od_all
  /tmp/od_all/bin/pip install -q -e "packages/omnidriver[post]" \
      -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam pytest
  ```
  And a core-only venv for anything claiming core standalone:
  ```bash
  rm -rf /tmp/od_core && /opt/homebrew/bin/python3.13 -m venv /tmp/od_core
  /tmp/od_core/bin/pip install -q -e "packages/omnidriver[post]" pytest
  ```
- **Run commands from a neutral cwd (`cd /tmp`) when testing installed
  behaviour.** The repo root contains an untracked
  `cardiacfoam_tutorials_driver.egg-info` that injects a broken
  `driverfoam.plugins` entry point into any process started there.
- **No `git commit` steps appear in this plan.** Committing is the operator's
  call, at whatever granularity they choose.
- **Behaviour must not change in Phase 1.** Every task here is either a fix to
  something already broken, or a rewiring whose current and new answers are
  identical for both shipped plugins.

- **Execution order, and how to read the expected counts.** The per-task
  totals below are written for numeric order 1→5 from the pre-Phase-1 baseline
  of **1456 passed / 1 failed / 272 skipped** — the one failure being
  `test_sweep_plan_contract.py::test_a_factory_failure_fails_one_case_not_the_command`,
  which **Task 4 fixes**.

  **Recommended order is Task 4 first**, precisely so that every later task has
  an unambiguous bar of *zero* failures instead of "one, and it must be that
  one". If you re-order, the counts shift and the invariant to hold is:

  > **No new failures, and the passed count rises by exactly the number of
  > tests this task adds.**

  Two fixed anchors regardless of order: before Task 4 the suite has exactly one
  failure and it is that test; after Task 4 it has none.

- **Never weaken a test to make it pass.** If an existing test fails after your
  change, read it and decide which of two things it was asserting. If it pins
  the *behaviour you are preserving*, your change is wrong — fix the change. If
  it pins the *hardcoding you are removing* (e.g. a literal `"Allrun"` where the
  point is now a declared role), rewrite it against the new mechanism and say so
  in your report. If you cannot tell which, **stop and report** rather than
  editing the assertion. Task 3 Step 8 is where this is most likely to bite.

- **Stay inside your task's file list.** Each task names every file it may
  create or modify. A file not on that list is another task's territory or
  another phase's; touching it silently is how the last migration pass left
  three regressions behind.
- **Existing file conventions:** core source files carry a cardiacFoam GPLv3
  header block. Do not add or remove those headers in this phase — the licence
  question is Phase 3 and touching it piecemeal makes it harder.
- **Test style:** plain `def test_*` with pytest, `from __future__ import
  annotations` at the top. `unittest.TestCase` appears in older files; do not
  convert them.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `packages/omnidriver/src/omnidriver/core/plugin_discovery.py` | entry-point group name + its documentation | 1 |
| `packages/omnidriver/tests/core/test_plugin_discovery.py` | discovery unit tests (seam-based) | 1 |
| `packages/omnidriver/tests/core/test_entry_point_group_matches_packaging.py` | **new** — group constant vs every `pyproject.toml` | 1 |
| `packages/omnidriver-cardiacfoam/tests/test_plugin_is_discoverable.py` | **new** — real `importlib.metadata` resolution | 1 |
| `packages/omnidriver/src/omnidriver/core/plugin_profile.py` | role vocabulary + validation | 2 |
| `packages/omnidriver/tests/core/test_plugin_profile.py` | profile loader tests | 2 |
| `packages/omnidriver/src/omnidriver/core/runtime/registry.py` | case discovery / runnability, role-driven | 3 |
| `packages/omnidriver/src/omnidriver/core/generic-plugin.yaml` | declares its own entrypoint | 3 |
| `packages/omnidriver/tests/core/test_entrypoint_is_plugin_declared.py` | **new** | 3 |
| `packages/omnidriver/src/omnidriver/core/capability_seams.py` | lazy repo-root resolution | 4 |
| `scripts/export-capability-seams.py` | two call sites of `ARCHITECTURE` | 4 |
| `packages/omnidriver/tests/core/test_sweep_plan_contract.py` | add the missing monorepo skip | 4 |
| `packages/omnidriver/tests/core/test_wheel_install_imports.py` | **new** — G1 | 4 |
| `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py` | two ported hooks | 5 |
| `packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py` | **new** — instrumented gate census | 5 |

---

### Task 1: Fix entry-point plugin discovery

`core/plugin_discovery.py:59` reads group `"driverfoam.plugins"`. Both shipped
`pyproject.toml` files register under `"omnidriver.plugins"`. The rename landed
in packaging and never in the code, so `--plugin <name>` resolves nothing in any
install. Every existing discovery test monkeypatches the `_entry_points()` seam,
so the constant is never exercised against real metadata — which is why a
package rename passed CI.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_discovery.py:22,33,35,48,51,59`
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py:622`
- Modify: `packages/omnidriver/src/omnidriver/core/generic_plugin.py:10`
- Modify: `packages/omnidriver/src/omnidriver/cli.py:592`
- Modify: `AGENT_GUIDE.md:818,911,968,980`, `KEY_FILES.md:15,36,113`, `CONTRIBUTING.md:52`
- Create: `packages/omnidriver/tests/core/test_entry_point_group_matches_packaging.py`
- Create: `packages/omnidriver-cardiacfoam/tests/test_plugin_is_discoverable.py`
- Modify: `packages/omnidriver/tests/core/test_plugin_discovery.py:59` (test name only)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `plugin_discovery.ENTRY_POINT_GROUP == "omnidriver.plugins"`. No
  signature changes.

- [ ] **Step 1: Write the packaging-consistency guard (fails today)**

Create `packages/omnidriver/tests/core/test_entry_point_group_matches_packaging.py`:

```python
"""The group constant and the packaging metadata must name the same group.

They did not, from the monorepo rename until this test existed: packaging moved
to 'omnidriver.plugins' and plugin_discovery.py kept reading 'driverfoam.plugins',
so --plugin <name> resolved nothing in any install. Every other discovery test
monkeypatches the _entry_points() seam and therefore cannot catch this.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from omnidriver.core.plugin_discovery import ENTRY_POINT_GROUP

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _declared_plugin_groups() -> dict[str, list[str]]:
    """Map each packages/*/pyproject.toml to the entry-point groups it declares
    that look like a plugin group (contain '.plugins')."""
    found: dict[str, list[str]] = {}
    for pyproject in sorted((_REPO_ROOT / "packages").glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text())
        groups = data.get("project", {}).get("entry-points", {})
        plugin_groups = [name for name in groups if ".plugins" in name]
        if plugin_groups:
            found[pyproject.parent.name] = sorted(plugin_groups)
    return found


def test_every_package_registers_into_the_group_core_reads() -> None:
    declared = _declared_plugin_groups()
    assert declared, "no packages/*/pyproject.toml declares a *.plugins group"
    offenders = {
        package: groups
        for package, groups in declared.items()
        if groups != [ENTRY_POINT_GROUP]
    }
    assert offenders == {}, (
        f"plugin_discovery.ENTRY_POINT_GROUP is {ENTRY_POINT_GROUP!r} but these "
        f"packages register elsewhere: {offenders}. A plugin registered into a "
        "group core does not read is undiscoverable."
    )
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_entry_point_group_matches_packaging.py -v`

Expected: **FAIL** —
`AssertionError: plugin_discovery.ENTRY_POINT_GROUP is 'driverfoam.plugins' but these packages register elsewhere: {'omnidriver': ['omnidriver.plugins'], 'omnidriver-cardiacfoam': ['omnidriver.plugins']}`

- [ ] **Step 3: Change the constant**

In `packages/omnidriver/src/omnidriver/core/plugin_discovery.py`, line 59:

```python
ENTRY_POINT_GROUP = "omnidriver.plugins"
```

- [ ] **Step 4: Run it and confirm it passes**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_entry_point_group_matches_packaging.py -v`
Expected: **PASS**

- [ ] **Step 5: Update every mention of the old group name**

Six source/doc locations still say `driverfoam.plugins`. Replace each with
`omnidriver.plugins`:

- `plugin_discovery.py:22` (module header Description), `:33`, `:35` (the
  `[project.entry-points."…"]` example), `:48`, `:51` (the troubleshooting
  one-liner)
- `plugin_interface.py:622` — `load_plugin_context` docstring
- `generic_plugin.py:10` — the plugin-scaffold checklist, step 4
- `cli.py:592` — the `--plugin` help string
- `AGENT_GUIDE.md:818,911,968,980`, `KEY_FILES.md:15,36,113`, `CONTRIBUTING.md:52`

Also rename the now-misleading test at
`packages/omnidriver/tests/core/test_plugin_discovery.py:59`:

```python
def test_discovery_reads_the_omnidriver_plugins_group(monkeypatch) -> None:
```

`KEY_FILES.md:15` additionally names the pre-migration path
`openfoam_driver/core/plugin_discovery.py`; correct it to
`packages/omnidriver/src/omnidriver/core/plugin_discovery.py`.

- [ ] **Step 6: Write the real-metadata test in cardiacfoam's suite**

This one needs an installed plugin, so it belongs to the package that ships one
— not core, whose CI job installs nothing else.

Create `packages/omnidriver-cardiacfoam/tests/test_plugin_is_discoverable.py`:

```python
"""The shipped plugin resolves through real installed metadata.

Deliberately does NOT monkeypatch plugin_discovery._entry_points(). That seam
exists so unit tests need no pip install, and it is exactly why a group-name
mismatch survived a package rename: mocked discovery never reads
ENTRY_POINT_GROUP. This test does.
"""
from __future__ import annotations

from importlib.metadata import entry_points

from omnidriver.core.plugin_discovery import ENTRY_POINT_GROUP, discover_plugins
from omnidriver.core.plugin_interface import load_plugin_context


def test_cardiacfoam_is_registered_in_the_group_core_reads() -> None:
    names = {ep.name for ep in entry_points(group=ENTRY_POINT_GROUP)}
    assert "cardiacfoam" in names, (
        f"installed distributions register {sorted(names)} in group "
        f"{ENTRY_POINT_GROUP!r}; 'cardiacfoam' is missing"
    )


def test_cardiacfoam_loads_by_discovered_name() -> None:
    assert "cardiacfoam" in discover_plugins()
    context = load_plugin_context("cardiacfoam")
    assert context.identity.id == "org.cardiacfoam"
    assert context.identity.source.startswith("entry-point:omnidriver-cardiacfoam=")
```

- [ ] **Step 7: Verify G2 end to end from a neutral cwd**

```bash
cd /tmp && /tmp/od_all/bin/python -c "
from omnidriver.core.plugin_interface import load_plugin_context
ctx = load_plugin_context('cardiacfoam')
print('OK', ctx.identity.id, ctx.identity.source)"
```
Expected: `OK org.cardiacfoam entry-point:omnidriver-cardiacfoam=0.1.0`

If this prints `openfoam_driver.plugins.cardiacfoam_plugin` or raises
`ModuleNotFoundError`, the venv is contaminated — see Global Constraints.

Then: `/tmp/od_all/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_plugin_is_discoverable.py -v` → 2 passed.

---

### Task 2: Make the role vocabulary a validated enum

`plugin_profile.py:101` checks only that `role` is a non-empty string.
`plugin_capabilities.py:461` documents the consequence in prose — *"a rule
written as `control_dict` rather than `openfoam.control_dict` will be silently
classified as plugin-owned"* — and nothing enforces it. An unenforced namespace
is not a seam; Task 3 depends on this one being real.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_profile.py` (add
  `KNOWN_ROLES`, validate in the `case_profile.dictionaries` loop at :99–115)
- Modify: `packages/omnidriver/src/omnidriver/core/generic-plugin.yaml:16–33`
  (the role reference comment becomes the authoritative list)
- Modify: `packages/omnidriver/tests/core/test_plugin_profile.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `plugin_profile.KNOWN_ROLES: frozenset[str]` — the eleven role
  strings below. Task 3 imports `KNOWN_ROLES` is **not** required; Task 3 uses
  the literal `"openfoam.entrypoint"`, which this task guarantees is spelled
  consistently.

The eleven roles are exactly those documented in `generic-plugin.yaml:16–33` and
in use across the two shipped profiles (`openfoam.case_directory`,
`openfoam.control_dict` in the generic profile; the other nine in
`cardiacfoam/plugin.yaml`).

- [ ] **Step 1: Write the failing tests**

Append to `packages/omnidriver/tests/core/test_plugin_profile.py`:

```python
def test_an_unknown_role_is_rejected_at_load(tmp_path) -> None:
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.test\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: control_dict\n"           # missing the openfoam. namespace
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="unknown case-file role 'control_dict'"):
        load_plugin_profile(profile)


def test_a_known_role_loads(tmp_path) -> None:
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.test\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: openfoam.control_dict\n"
        "      required: always\n"
    )
    loaded = load_plugin_profile(profile)
    assert loaded.case_files[0].role == "openfoam.control_dict"


def test_the_generic_profile_uses_only_known_roles() -> None:
    from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin

    for rule in GenericOpenFOAMPlugin.get_profile().case_files:
        assert rule.role in KNOWN_ROLES, rule


def test_the_cardiac_profile_uses_only_known_roles() -> None:
    """Skipped in the core-only CI job, which installs no plugin package.

    Worth asserting anyway: cardiacFoam's profile declares nine of the eleven
    roles, so it is the real drift risk. Core's own declares two.
    """
    cardiacfoam_plugin = pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason="omnidriver-cardiacfoam is not installed",
    )

    rules = cardiacfoam_plugin.CardiacFoamPlugin().get_profile().case_files
    assert rules, "cardiacFoam declares case files; an empty profile is a defect"
    for rule in rules:
        assert rule.role in KNOWN_ROLES, rule
```

`GenericOpenFOAMPlugin.get_profile` is an `lru_cache`d `staticmethod`, so
calling it on the class (no instance) is correct; `CardiacFoamPlugin`'s is an
ordinary method and needs the instance. Do not "fix" either to match the other.

Add the imports that file needs at its top: `pytest`, and from
`omnidriver.core.plugin_profile` both `load_plugin_profile` and `KNOWN_ROLES`.

- [ ] **Step 2: Run and confirm two of the three fail**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_plugin_profile.py -v -k "role"`

Expected: `test_an_unknown_role_is_rejected_at_load` FAILS (no exception raised);
`test_both_shipped_profiles_use_only_known_roles` FAILS with
`ImportError: cannot import name 'KNOWN_ROLES'`; `test_a_known_role_loads` passes.

- [ ] **Step 3: Add the enum and the check**

In `packages/omnidriver/src/omnidriver/core/plugin_profile.py`, above
`load_plugin_profile`:

```python
#: Case-file roles core recognises. The prefix is load-bearing: ``openfoam.*``
#: marks a file the OpenFOAM runtime itself requires, ``plugin.*`` one the
#: solver plugin requires, ``case.*`` one that belongs to the case as a
#: document rather than to either. Consumers split on that prefix
#: (tutorial_contracts.py) and look up specific roles by exact string
#: (provenance_inputs.py, registry.py), so an unvalidated typo silently
#: reclassifies a file instead of failing. See future/ENVIRONMENT_CONTRACT.md.
#:
#: Adding a role here is a contract change: document it in
#: core/generic-plugin.yaml's role reference in the same edit.
KNOWN_ROLES: frozenset[str] = frozenset({
    "openfoam.control_dict",
    "openfoam.discretisation",
    "openfoam.solver_settings",
    "openfoam.decomposition",
    "openfoam.mesh_generation",
    "openfoam.case_directory",
    "openfoam.entrypoint",
    "openfoam.cleanup",
    "plugin.configuration",
    "case.documentation",
    "case.regression_test",
})
```

Then, inside the `case_profile.dictionaries` loop, immediately after the
existing `required` check (`plugin_profile.py:109–114`):

```python
        if values["role"] not in KNOWN_ROLES:
            raise _mapping_error(
                profile_path,
                f"unknown case-file role {values['role']!r}; known roles are "
                + ", ".join(sorted(KNOWN_ROLES))
                + " (see future/ENVIRONMENT_CONTRACT.md)",
            )
```

`_mapping_error` already returns a `ValueError` subclass, so the tests' `pytest.raises(ValueError, ...)` matches.

- [ ] **Step 4: Run and confirm all three pass**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_plugin_profile.py -v`
Expected: all PASS.

- [ ] **Step 5: Confirm both shipped profiles still load**

```bash
cd /tmp && /tmp/od_all/bin/python -c "
from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
for cls in (GenericOpenFOAMPlugin, CardiacFoamPlugin):
    roles = sorted({r.role for r in cls().get_profile().case_files})
    print(cls.__name__, roles)"
```
Expected: both print without raising. cardiacFoam prints nine roles, the
generic plugin two. A `ValueError` here means the enum is missing a role one
of them actually uses — add it rather than editing the profile.

- [ ] **Step 6: Make the YAML comment authoritative**

In `packages/omnidriver/src/omnidriver/core/generic-plugin.yaml`, change the
role reference block's opening line from

```
#   role      (required) - semantic role tag; common values:
```

to

```
#   role      (required) - semantic role tag. VALIDATED at load time against
#                          core.plugin_profile.KNOWN_ROLES -- an unlisted role
#                          is an error, not a warning. The full set:
```

The eleven roles the block lists are already exactly `KNOWN_ROLES` — no role is
missing and none is surplus, so this step changes the framing line only.
Verify that with:

```bash
diff <(grep -oE '^#               [a-z._]+' packages/omnidriver/src/omnidriver/core/generic-plugin.yaml \
        | awk '{print $2}' | sort) \
     <(cd /tmp && /tmp/od_core/bin/python -c \
        "from omnidriver.core.plugin_profile import KNOWN_ROLES; print('\n'.join(sorted(KNOWN_ROLES)))")
```
Expected: no output. Any difference means the comment and the enum have drifted
— fix whichever is wrong before moving on.

---

### Task 3: Make the case entrypoint plugin-declared

`openfoam.entrypoint` is declared in `cardiacfoam/plugin.yaml:64` and read by
nothing. `Allrun` is hardcoded four lines away at `registry.py:79`, and again at
`:88` and `:302`. This wires the declaration to the three consumers.

**Scope boundary — read `future/ENVIRONMENT_CONTRACT.md` §5b before starting.**
This task touches only read-only filesystem predicates (is this a case? is it
runnable? keep the placeholder DAG?). It must **not** touch
`workflow.py:74 CASE_SCRIPT_COMMANDS`, which is the trust boundary deciding
which bare names may resolve to a case-local executable
(`workflow_runner.py:127`). Widening that is Phase 3 and needs its own threat
model. `generic_case.py:137`'s hardcoded `"Allrun"` is also out of scope: that
module has no `driver_context` at all, and threading one in is Phase 2 work.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/registry.py:76–97`,
  `:283–305`
- Modify: `packages/omnidriver/src/omnidriver/core/generic-plugin.yaml`
- Create: `packages/omnidriver/tests/core/test_entrypoint_is_plugin_declared.py`

**Interfaces:**
- Consumes: `plugin_profile.KNOWN_ROLES` guarantees `"openfoam.entrypoint"` is
  spelled consistently (Task 2).
- Produces: `registry._entrypoint_relpaths(driver_context) -> tuple[str, ...]`.
  `_with_entry_metadata` gains a keyword-only `driver_context` parameter.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_entrypoint_is_plugin_declared.py`:

```python
"""A case's entrypoint script comes from the plugin's declared role.

'Allrun' is OpenFOAM's spelling of a concept every simulation environment has.
Core is entitled to the concept; the spelling belongs to the plugin, declared as
role 'openfoam.entrypoint'. See future/ENVIRONMENT_CONTRACT.md.

Scope: discovery and runnability only. Which bare command names may resolve to a
case-local executable is a trust decision and stays in CASE_SCRIPT_COMMANDS.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_interface import driver_context, generic_openfoam_context
from omnidriver.core.runtime import registry

import plugins.minimal_plugin as minimal_plugin


def test_generic_plugin_still_finds_an_allrun_case(tmp_path) -> None:
    """Behaviour preservation: the shipped profiles declare Allrun, so every
    answer this file changes must be identical to the hardcoded one."""
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")
    assert registry._is_case_directory(case, generic_openfoam_context()) is True
    assert registry._case_is_runnable(case, driver_context=generic_openfoam_context()) is True


def test_a_plugin_declaring_another_entrypoint_finds_it(tmp_path) -> None:
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "run.sh").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is True
    assert registry._case_is_runnable(case, driver_context=context) is True


def test_that_plugin_does_not_claim_an_allrun_case(tmp_path) -> None:
    """The point of declaring: a plugin whose entrypoint is run.sh must not
    claim a folder just because it happens to contain an OpenFOAM Allrun."""
    case = tmp_path / "aCase"
    case.mkdir()
    (case / "Allrun").write_text("#!/bin/sh\n")

    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint="run.sh"),
        source="test:entrypoint",
    )
    assert registry._is_case_directory(case, context) is False


def test_no_declaration_falls_back_to_allrun(tmp_path) -> None:
    """Documented default, not a hidden one: a plugin declaring no entrypoint
    keeps the historical Allrun answer rather than becoming un-runnable."""
    context = driver_context(
        minimal_plugin.MinimalOpenFOAMPlugin(entrypoint=None),
        source="test:no-entrypoint",
    )
    assert registry._entrypoint_relpaths(context) == ("Allrun",)
```

- [ ] **Step 2: Give the minimal test plugin a declarable entrypoint**

`packages/omnidriver/tests/plugins/minimal_plugin.py` builds its `PluginProfile`
inline with `case_files=()`. Add an optional constructor argument that injects
one `CaseFileRule`. Insert this `__init__` directly above the `plugin_name`
property:

```python
    def __init__(self, *, entrypoint: str | None = None) -> None:
        """`entrypoint` declares an ``openfoam.entrypoint`` case-file rule.

        Default `None` declares none, so every existing no-argument
        construction in the suite is unchanged.
        """
        self._entrypoint = entrypoint
```

Then replace the body of `get_profile` (currently `case_files=()`) with:

```python
    def get_profile(self) -> PluginProfile:
        case_files: tuple[CaseFileRule, ...] = ()
        dictionaries: list[dict[str, str]] = []
        if self._entrypoint is not None:
            case_files = (
                CaseFileRule(
                    path=self._entrypoint,
                    kind="case_script",
                    role="openfoam.entrypoint",
                    required="conditional",
                ),
            )
            dictionaries = [{
                "path": self._entrypoint,
                "kind": "case_script",
                "role": "openfoam.entrypoint",
                "required": "conditional",
            }]
        return PluginProfile(
            path=Path(__file__),
            plugin_id=self.plugin_id,
            api_version=self.plugin_api_version,
            case_files=case_files,
            cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {
                    "id": self.plugin_id,
                    "api_version": self.plugin_api_version,
                },
                "case_profile": {"dictionaries": dictionaries},
            },
        )
```

and extend the existing import at the top of the file:

```python
from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
```

`payload` is kept in sync with `case_files` because `PluginProfile.payload` is
the raw document some consumers re-read; leaving them disagreeing would be a
trap for the next reader.

**Do not edit `packages/omnidriver-cardiacfoam/tests/plugins/minimal_plugin.py`**
in this task. It is a byte-identical copy; deduplicating the two is tracked
separately and doing it here would widen a low-risk task.

- [ ] **Step 3: Run and confirm three of the four fail**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_entrypoint_is_plugin_declared.py -v`

Expected: `test_generic_plugin_still_finds_an_allrun_case` PASSES (hardcoded
`Allrun` happens to agree); the other three FAIL —
`AttributeError: module 'omnidriver.core.runtime.registry' has no attribute '_entrypoint_relpaths'`
and, for `test_that_plugin_does_not_claim_an_allrun_case`, `assert True is False`.

- [ ] **Step 4: Add the role lookup**

In `packages/omnidriver/src/omnidriver/core/runtime/registry.py`, above
`_is_case_directory`:

```python
#: Historical entrypoint name, used when the active plugin declares no
#: ``openfoam.entrypoint`` rule (and when no context is available at all).
#: Documented and overridable rather than hardcoded -- see
#: future/ENVIRONMENT_CONTRACT.md §4.
_DEFAULT_ENTRYPOINT_RELPATHS: tuple[str, ...] = ("Allrun",)


def _entrypoint_relpaths(driver_context: "DriverContext | None") -> tuple[str, ...]:
    """Case-relative entrypoint scripts the active plugin declares.

    Searches every declared rule, not just ``required_rules()``: an entrypoint
    is legitimately ``conditional`` (both shipped profiles declare it so), and
    ``required_rules()`` filters to ``required == "always"``.
    """
    if driver_context is None:
        return _DEFAULT_ENTRYPOINT_RELPATHS
    declared = tuple(
        rule.path
        for rule in driver_context.capabilities.case_files.all_rules()
        if rule.role == "openfoam.entrypoint"
    )
    return declared or _DEFAULT_ENTRYPOINT_RELPATHS


def _has_entrypoint(case_root: Path, driver_context: "DriverContext | None") -> bool:
    return any(
        (case_root / relpath).is_file()
        for relpath in _entrypoint_relpaths(driver_context)
    )
```

- [ ] **Step 5: Replace the three hardcoded checks**

`registry.py:79`, inside `_is_case_directory` — replace
`or (path / "Allrun").is_file()` with:

```python
        or _has_entrypoint(path, driver_context)
```

`registry.py:88`, inside `_case_is_runnable` — the early return currently runs
*before* the context is resolved, so move it after. Replace:

```python
    if (case_root / "Allrun").is_file():
        return True

    from ..compatibility import resolve_public_driver_context
    from ..plugin_capabilities import CaseCompatibilityRequest

    driver_context = resolve_public_driver_context(driver_context)
```

with:

```python
    from ..compatibility import resolve_public_driver_context
    from ..plugin_capabilities import CaseCompatibilityRequest

    driver_context = resolve_public_driver_context(driver_context)
    if _has_entrypoint(case_root, driver_context):
        return True
```

This reorder is behaviour-preserving for both shipped plugins (each declares
`Allrun`), and Phase 2 removes the `resolve_public_driver_context` call
entirely.

`registry.py:300–303`, inside `_with_entry_metadata` — replace:

```python
    if (
        resolution["resolution"] == "case_folder"
        and not (Path(spec.case_root) / "Allrun").is_file()
    ):
```

with:

```python
    if (
        resolution["resolution"] == "case_folder"
        and not _has_entrypoint(Path(spec.case_root), driver_context)
    ):
```

and add the parameter to its signature (`registry.py:283`):

```python
def _with_entry_metadata(
    spec: TutorialSpec,
    resolution: dict[str, object],
    *,
    driver_context: "DriverContext | None" = None,
) -> TutorialSpec:
```

Both call sites (`:263` and `:280`) already hold a `driver_context`; pass it:

```python
    return _with_entry_metadata(spec, resolution, driver_context=driver_context)
```

Update the comment above the check, which currently says *"Plain case folders
are owned by their on-disk Allrun"*, to *"owned by their on-disk entrypoint (the
plugin's declared `openfoam.entrypoint`, `Allrun` by default)"*.

- [ ] **Step 6: Run and confirm all four pass**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_entrypoint_is_plugin_declared.py -v`
Expected: 4 passed.

- [ ] **Step 7: Let the generic plugin declare its own entrypoint**

`generic-plugin.yaml` currently declares only `system/controlDict` and
`constant`, so `GenericOpenFOAMPlugin` reaches `Allrun` through the fallback.
Make it explicit — append to `case_profile.dictionaries`:

```yaml
    - path: Allrun
      kind: case_script
      role: openfoam.entrypoint
      required: conditional
```

Behaviour-preserving: `Allrun` was already the answer via
`_DEFAULT_ENTRYPOINT_RELPATHS`.

- [ ] **Step 8: Confirm no behaviour changed anywhere else**

Run: `/tmp/od_all/bin/python -m pytest packages/ -q`
Expected: **1456 passed, 1 failed, 272 skipped** — unchanged from the baseline
in Global Constraints. The one failure is Task 4's.

A new failure here almost certainly means a test asserted on `Allrun` as a
literal. Read it before changing it: if it is asserting the *default*, keep it;
if it is asserting *discovery*, rewrite it against the declared role.

---

### Task 4: Make core importable from a built wheel

`core/capability_seams.py:50` calls `repo_root_default()` at **module scope**,
and that function walks up the filesystem looking for a development checkout
(`tutorials/+src/`, `tutorials/`, or `packages/+ARCHITECTURE.md`) and raises
rather than guess. From site-packages, none matches. Editable installs hide this
completely, which is why CI has never seen it — and `release.yml` builds exactly
this wheel.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/capability_seams.py:48–50`
- Modify: `scripts/export-capability-seams.py:43,60,74,75`
- Modify: `packages/omnidriver/tests/core/test_sweep_plan_contract.py`
- Create: `packages/omnidriver/tests/core/test_wheel_install_imports.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–3.
- Produces: `capability_seams.architecture_path() -> Path`. The module constant
  `ARCHITECTURE` is removed; its only two consumers are in
  `scripts/export-capability-seams.py`.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_wheel_install_imports.py`:

```python
"""Every core module must import from a real wheel, not just an editable install.

core/specs/paths.py::repo_root_default() walks up looking for a development
checkout and raises when it finds none. capability_seams.py called it at module
scope, so `import omnidriver.core.capability_seams` raised RuntimeError from
site-packages -- invisible to every editable install and to all of CI, while
release.yml built and published exactly that wheel.

Slow (builds a wheel into a throwaway venv). Marked so it can be deselected
locally with -m 'not slow'; CI runs it.
"""
from __future__ import annotations

import subprocess
import sys
import venv
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]

_WALK = """
import importlib, pkgutil, sys
import omnidriver
bad = []
for module in pkgutil.walk_packages(omnidriver.__path__, "omnidriver."):
    if "conftest" in module.name:
        continue
    try:
        importlib.import_module(module.name)
    except Exception as exc:
        bad.append(f"{module.name}: {type(exc).__name__}: {exc}")
if bad:
    print("\\n".join(bad))
    sys.exit(1)
print("all modules imported")
"""


@pytest.mark.slow
def test_every_core_module_imports_from_a_wheel(tmp_path) -> None:
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    python = env_dir / "bin" / "python"

    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", "build"],
        check=True, capture_output=True,
    )
    subprocess.run(
        [str(python), "-m", "build", "--wheel",
         str(_REPO_ROOT / "packages" / "omnidriver"), "-o", str(tmp_path / "dist")],
        check=True, capture_output=True,
    )
    wheel = next((tmp_path / "dist").glob("*.whl"))
    subprocess.run(
        [str(python), "-m", "pip", "install", "-q", f"{wheel}[post]"],
        check=True, capture_output=True,
    )

    # cwd must not be the repo: it would put the source tree back on sys.path
    # and re-hide exactly what this test exists to catch.
    result = subprocess.run(
        [str(python), "-c", _WALK],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

Register the marker in **both** `pyproject.toml` files under
`[tool.pytest.ini_options]` — the root one and
`packages/omnidriver/pyproject.toml`:

```toml
    "slow: builds a wheel in a throwaway venv; minutes, not seconds",
```

Both, because pytest resolves one config per run and which one depends on how
it is invoked: a whole-repo `pytest packages/` (this task's Step 7) reads the
root file, while a per-package `pytest packages/omnidriver/tests` (CI's
`test-core` job) reads the package file. Registering in only one produces
`PytestUnknownMarkWarning` in the other — harmless for `-m "not slow"`, which
still deselects correctly, but an unregistered marker is one typo away from
silently selecting nothing.

The root file already has a `markers` list containing `integration`; append to
it rather than replacing it. The package file has no `markers` key yet; add one.

- [ ] **Step 2: Run and confirm it fails**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_wheel_install_imports.py -v`

Expected: **FAIL**, output naming
`omnidriver.core.capability_seams: RuntimeError: Could not locate the omnidriver repository root by walking up from …/site-packages/omnidriver/core/specs/paths.py`

`omnidriver.scripts._rtst_scanner` will also be named. That is a **separate**
leak — it imports `PHYSICS_PROPERTY_ENTRIES` from `omnidriver.dict_entries`,
whose PEP 562 `__getattr__` resolves it out of `omnidriver.cardiacfoam`, so the
AST import gate cannot see it — and relocating that module is Phase 2 work.
Do **not** fix it here.

Instead, add a named, shrink-only exclusion. Replace the `_WALK` script's final
block with:

```python
# Modules known to fail from a wheel for a reason tracked elsewhere. This set
# may only SHRINK: an entry that stops matching fails the test, so it cannot
# rot into a lie the way a silently-broad assertion would.
KNOWN_UNIMPORTABLE = {
    # Imports PHYSICS_PROPERTY_ENTRIES from omnidriver.dict_entries, whose PEP
    # 562 __getattr__ resolves it out of omnidriver.cardiacfoam. Phase 2 moves
    # this module to omnidriver-cardiacfoam and deletes this entry.
    "omnidriver.scripts._rtst_scanner",
}

unexpected = [line for line in bad if line.split(":")[0] not in KNOWN_UNIMPORTABLE]
stale = KNOWN_UNIMPORTABLE - {line.split(":")[0] for line in bad}
if stale:
    print("KNOWN_UNIMPORTABLE entries that now import fine -- delete them: "
          + ", ".join(sorted(stale)))
    sys.exit(1)
if unexpected:
    print("\\n".join(unexpected))
    sys.exit(1)
print("all modules imported")
```

(that replaces the `if bad: … sys.exit(1)` / `print("all modules imported")`
lines shown in Step 1).

- [ ] **Step 3: Make the repo-root resolution lazy**

In `packages/omnidriver/src/omnidriver/core/capability_seams.py`, replace line 50:

```python
ARCHITECTURE = repo_root_default() / "ARCHITECTURE.md"
```

with:

```python
def architecture_path() -> Path:
    """Path to ARCHITECTURE.md in a development checkout.

    A function, not a module constant: ``repo_root_default()`` raises when no
    checkout is found, and evaluating it at import time made this module
    unimportable from an installed wheel. Only the export script calls this,
    and that script only ever runs inside a checkout.
    """
    return repo_root_default() / "ARCHITECTURE.md"
```

- [ ] **Step 4: Update the two consumers**

In `scripts/export-capability-seams.py`, change the import at :43 from
`ARCHITECTURE` to `architecture_path`, and at :60/:74/:75 bind it once at the
top of `main()`:

```python
    architecture = architecture_path()
```

then use `architecture.read_text()`, `architecture.write_text(updated)`, and
`architecture.name`.

- [ ] **Step 5: Run and confirm the wheel test passes**

Run: `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests/core/test_wheel_install_imports.py -v`
Expected: PASS (with `_rtst_scanner` still excluded).

Then confirm the export script still works in the checkout:
`/tmp/od_all/bin/python scripts/export-capability-seams.py --check`
Expected: `ARCHITECTURE.md capability seam table is up to date.`

- [ ] **Step 6: Fix the mis-marked sweep test**

`packages/omnidriver/tests/core/test_sweep_plan_contract.py::test_a_factory_failure_fails_one_case_not_the_command`
fails because `tutorials_root_default()` resolves to a root with no
`tutorials/`, so the *valid* `Courtemanche` case fails alongside the intended
`TotallyFakeModel` one. Same root cause as this task: core assuming a checkout
layout. It is a missing skip marker, not a sweep defect — the same test passes
in the legacy `driverFoam` tree, where `tutorials/` exists.

Add the import and the marker:

```python
from conftest import skip_without_monorepo


@skip_without_monorepo
def test_a_factory_failure_fails_one_case_not_the_command(tmp_path):
```

Leave `test_a_malformed_spec_is_reported_structurally` unmarked — it never
touches the tutorials tree.

- [ ] **Step 7: Confirm the full suite is now clean**

Run: `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"`
Expected: **1456 passed, 0 failed, 273 skipped** — one more skip than baseline,
zero failures. This is the first time the repository's own suite is green.

---

### Task 5: Port the two missing plugin hooks

Instrumentation across the whole suite shows the *cardiac branch* of the twenty
`plugin_id == "org.cardiacfoam"` gates in `core/compatibility.py` is taken by
exactly one function — `legacy_describe_config_resolution`, 12 times. Every
other call arrives from a non-cardiac plugin and takes the neutral branch.

The reason is a hook gap: legacy's `CardiacFoamPlugin` implements
`get_config_resolution_description` (`:244`) and `get_report_catalog` (`:236`);
this repo's does not. Porting both removes the last reachable gate reached
during the suite and leaves `get_phases` (Phase 2) as the only remaining hook
gap. It does **not** delete any gate — that is Phase 2, after the census re-runs
clean.

**Files:**
- Modify: `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`
- Create: `packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–4.
- Produces: `CardiacFoamPlugin.get_config_resolution_description() -> str` and
  `CardiacFoamPlugin.get_report_catalog() -> tuple[ReportDefinition, ...]`.
  Phase 2's gate deletion depends on both existing.

- [ ] **Step 1: Write the failing census test**

Create `packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py`:

```python
"""No compatibility fallback may answer in cardiac terms for the cardiac plugin.

core/compatibility.py has twenty branches gated on
plugin_id == "org.cardiacfoam". Each exists only for plugins predating an
optional hook. Once CardiacFoamPlugin implements the hook, the adapter calls it
directly and the gate is dead code.

This asserts that directly: run an operation under an explicit cardiac context
and assert no gated fallback fired. Phase 2 deletes the branches; this is the
evidence that deleting them is safe.
"""
from __future__ import annotations

import inspect

from omnidriver.core import compatibility
from omnidriver.core.plugin_interface import driver_context
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin


def _gated_fallback_names() -> frozenset[str]:
    """Every legacy_* whose source branches on the cardiac plugin id."""
    names = set()
    for name in dir(compatibility):
        if not name.startswith("legacy_"):
            continue
        func = getattr(compatibility, name)
        if not callable(func):
            continue
        try:
            source = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        if "org.cardiacfoam" in source:
            names.add(name)
    return frozenset(names)


def test_the_gate_set_is_the_twenty_we_measured() -> None:
    """A twenty-first gate appearing is a regression worth noticing."""
    assert len(_gated_fallback_names()) == 20


def test_reading_every_capability_under_cardiac_fires_no_gated_fallback() -> None:
    gated = _gated_fallback_names()
    context = driver_context(CardiacFoamPlugin(), source="test:cardiac-census")

    with compatibility.track_fallback_calls() as calls:
        caps = context.capabilities
        caps.case_files.describe_config_resolution()
        caps.report_catalog.reports()
        caps.named_catalogs.catalogs()
        caps.override_scopes.scopes()
        caps.dict_regeneration.scopes()
        caps.command_authorization.solver_commands()
        caps.command_authorization.auxiliary_commands()
        caps.command_authorization.utility_manifests()
        caps.command_authorization.utility_roots()
        caps.case_introspection.samplable_fields({})
        caps.case_introspection.resolve_case_models(Path("/nonexistent"))
        fired = sorted({name for name in calls if name in gated})

    assert fired == [], (
        f"gated cardiac fallbacks fired under an explicit cardiac context: "
        f"{fired}. Each names a hook CardiacFoamPlugin should implement."
    )
```

Add `from pathlib import Path` to that file's imports.
`resolve_case_models` is contractually forbidden from raising — its
`SolverPlugin` docstring says *"Must never raise: agents call it against
partly-written cases"* — so a nonexistent path is a valid probe.

The accessor names above are verified against `PluginCapabilities`
(`plugin_capabilities.py:1268–1291`) and the adapters: note it is
`report_catalog.reports()`, **not** `.catalog()`.

- [ ] **Step 2: Run and confirm it fails**

Run: `/tmp/od_all/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py -v`

Expected: `test_the_gate_set_is_the_twenty_we_measured` PASSES;
`test_reading_every_capability_under_cardiac_fires_no_gated_fallback` FAILS with
`fired == ['legacy_describe_config_resolution', 'legacy_report_catalog']`.

- [ ] **Step 3: Port both hooks**

In `packages/omnidriver-cardiacfoam/src/omnidriver/cardiacfoam/cardiacfoam_plugin.py`,
add two methods. Both bodies are the exact values `compatibility.py` returns for
this plugin today — `compatibility.py:526` and `:558` — so this is a move, not a
change:

```python
    def get_config_resolution_description(self) -> str:
        """Which files resolve into a valid RunDocument config, in one sentence.

        Moved here from core's legacy_describe_config_resolution fallback, which
        hardcoded this string behind a plugin_id check. Core owning a sentence
        about electroProperties was the last reachable cardiac gate.
        """
        return (
            "physicsProperties and electroProperties resolve into a valid "
            "RunDocument config."
        )

    def get_report_catalog(self) -> tuple:
        """Post-run reports this plugin offers. Core owns the machinery; the
        catalog is plugin data."""
        from omnidriver.cardiacfoam.reports import CARDIAC_REPORTS

        return CARDIAC_REPORTS
```

Match the surrounding file's import convention — if `cardiacfoam_plugin.py`
imports its catalogs at module scope rather than inside methods, follow that.

- [ ] **Step 4: Run and confirm it passes**

Run: `/tmp/od_all/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_no_cardiac_gate_is_reached.py -v`
Expected: 2 passed.

- [ ] **Step 5: Confirm the strings are identical**

The whole point is behaviour preservation. Verify the hook and the fallback
return the same values:

```bash
cd /tmp && /tmp/od_all/bin/python -c "
from omnidriver.core import compatibility as c
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
p = CardiacFoamPlugin()
assert p.get_config_resolution_description() == c.legacy_describe_config_resolution(p)
assert p.get_report_catalog() == c.legacy_report_catalog(p)
print('hook and fallback agree')"
```
Expected: `hook and fallback agree`

- [ ] **Step 6: Full suite**

Run: `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"`
Expected: **1458 passed, 0 failed, 273 skipped** (Task 4's total plus this
task's two).

---

## Phase 1 exit criteria

All must hold before Phase 2 starts.

- [ ] `cd /tmp && /tmp/od_all/bin/python -c "from omnidriver.core.plugin_interface import load_plugin_context; print(load_plugin_context('cardiacfoam').identity.id)"` → `org.cardiacfoam` **(G2)**
- [ ] `pytest packages/omnidriver/tests/core/test_wheel_install_imports.py` → PASS **(G1, modulo the one Phase 2 exclusion)**
- [ ] `/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow"` → **0 failed**
- [ ] `/tmp/od_core/bin/python -m pytest packages/omnidriver/tests --collect-only -q` → **0 errors** (unchanged)
- [ ] `python3 scripts/check-import-boundaries.py` → exit 0, still exactly one waiver
- [ ] `/tmp/od_all/bin/python scripts/export-capability-seams.py --check` → up to date
- [ ] A profile with an unnamespaced role fails to load with a message naming the eleven known roles
- [ ] `GITHUB_MIGRATION.md` §3 reflects what Phase 1 closed

Explicitly **not** expected to change in Phase 1: the core-only failure count
(still ~161 — that is Phase 2's `DriverContext` work), the twenty gates (still
present, now provably unreachable), `CASE_SCRIPT_COMMANDS`,
`CORE_NEUTRAL_COMMANDS`, `$FOAM_APPBIN`, `ArtifactFormat`, and the `Phase` enum.

## Related

- [`future/ENVIRONMENT_CONTRACT.md`](../../../future/ENVIRONMENT_CONTRACT.md) — the ownership rule these tasks serve, and why §5b is out of scope
- `GITHUB_MIGRATION.md` §3 — round-2 scope, corrected 2026-08-27
- `docs/superpowers/plans/2026-08-27-test-core-decoupling.md` — the completed test-tree pass this follows
