# A Case Is A Path — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pytest packages/omnidriver/tests` pass against an installed
wheel, by letting a case be identified by its path and removing core's ambient
root resolution.

**Architecture:** Four commits. Task 1 teaches `resolve_entry` to accept a
path, which alone fixes most of the wheel failures. Task 2 removes core's
ambient defaults and moves resolution to the public edge
(explicit → `OMNIDRIVER_CASES_ROOT` → cwd). Task 3 relocates scratch out of the
repository. Task 4 adds the static guard and upgrades the CI wheel job to run
the suite.

**Tech Stack:** Python 3.11+ (floor), pytest, plain `pathlib`. No new
dependencies.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-09-04-a-case-is-a-path-design.md`.
  Principle recorded in `future/ENVIRONMENT_CONTRACT.md` §12.
- **Verification interpreters:** `/tmp/od_all/bin/python` (3.13, all three
  packages), `/tmp/od311b/bin/python` (3.11, all three),
  `/tmp/od_core/bin/python` (core only), `/tmp/wheelenv/bin/python` (core
  installed **from a wheel**). Never the repo's own `.venv`.
- **Baselines that must not regress:** full suite **1551 passed, 276 skipped,
  1 deselected, 40 subtests** on 3.11 and 3.13; core-only **679 passed, 93
  skipped**.
- **Gates that must stay green:** `scripts/check-import-boundaries.py` exits 0
  with an EMPTY `KNOWN_VIOLATIONS`; `scripts/export-capability-seams.py --check`
  reports up to date.
- **Today's date is 2026-09-04.** Use it for new dated markers; never rewrite
  the date on a historical measurement.
- **Rebuild the wheel venv after any source change**, or it tests stale code:
  ```bash
  rm -rf /tmp/wheeltest /tmp/wheelenv
  /tmp/od_all/bin/python -m build --outdir /tmp/wheeltest packages/omnidriver
  uv venv --python 3.11 /tmp/wheelenv -q
  VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "/tmp/wheeltest/omnidriver-0.1.0-py3-none-any.whl[post]" pytest
  ```
- **No alias for renamed public names.** Pre-publication; the repo removed
  `--openfoam-bashrc` and the cardiac `make_spec` aliases outright.

## File Structure

| file | task | responsibility |
|---|---|---|
| `packages/omnidriver/src/omnidriver/core/runtime/registry.py` | 1 | accept a path as an entry |
| `packages/omnidriver/tests/core/test_case_is_a_path.py` | 1 | new: the path-entry contract |
| `packages/omnidriver/src/omnidriver/core/specs/paths.py` | 2, 3 | drop the ambient defaults |
| `packages/omnidriver/src/omnidriver/cli.py` | 2, 3 | resolve the base at the public edge |
| `packages/omnidriver/src/omnidriver/core/capability_seams.py` | 2 | keep repo lookup for dev tooling only |
| `packages/omnidriver/tests/core/test_core_context_is_explicit.py` | 4 | extend the static guard |
| `.github/workflows/ci.yml` | 4 | wheel job runs the suite |

---

## Task 1: `resolve_entry` accepts a path

The single change that removes most wheel failures. `_is_case_directory()`
already recognises a case anywhere on disk; only the entry API refuses one.

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/registry.py` (in
  `resolve_entry`, before the `_match_entry` call at line ~371)
- Create: `packages/omnidriver/tests/core/test_case_is_a_path.py`

**Interfaces:**
- Consumes: `registry._is_case_directory(path, driver_context) -> bool`;
  `core.runtime.generic_case.make_generic_case_spec(**kwargs) -> TutorialSpec`.
- Produces: `resolve_entry` returns its existing dict shape with
  `resolution="case_path"`. `load_entry_spec` calls
  `resolution["factory"](**resolution["factory_overrides"])`, so
  `factory_overrides` MUST carry `tutorials_root` (the case's parent) and
  `case_dir_name` (its leaf name). Task 2 relies on this working without any
  ambient default.

- [ ] **Step 1: Write the failing test**

Create `packages/omnidriver/tests/core/test_case_is_a_path.py`:

```python
"""A case is identified by its path, not by a name under a root.

registry._is_case_directory() already answers "is this a runnable case?" from
a directory's own contents, through the plugin's declared marker or entrypoint
contract -- and it takes a path. Before this, resolve_entry() rejected that
same path and only resolved once the caller split it into a root and a name.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.registry import resolve_entry

from plugins.neutral_environment_plugin import NeutralEnvironmentPlugin


def _case(tmp_path: Path, name: str = "mycase") -> Path:
    """A directory the NeutralEnvironmentPlugin's profile calls a case."""
    case = tmp_path / name
    (case / "system").mkdir(parents=True)
    (case / "constant").mkdir()
    (case / "system" / "controlDict").write_text("")
    (case / "Allrun").write_text("#!/bin/sh\nexit 0\n")
    return case


def test_an_absolute_path_resolves_as_a_case(tmp_path: Path) -> None:
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    case = _case(tmp_path)

    resolution = resolve_entry(str(case), entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"
    assert Path(resolution["factory_overrides"]["tutorials_root"]) == tmp_path
    assert resolution["factory_overrides"]["case_dir_name"] == "mycase"


def test_a_relative_path_resolves_against_the_working_directory(
    tmp_path: Path, monkeypatch
) -> None:
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    _case(tmp_path)
    monkeypatch.chdir(tmp_path)

    resolution = resolve_entry("mycase", entry_kind="case_folder", driver_context=ctx)

    assert resolution["resolution"] == "case_path"
    assert resolution["entry_name"] == "mycase"


def test_a_directory_that_is_not_a_case_is_still_refused(tmp_path: Path) -> None:
    """The contrast is the point: if any path resolved, the assertions above
    would pass for a directory with nothing in it."""
    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    empty = tmp_path / "notacase"
    empty.mkdir()

    with pytest.raises(KeyError):
        resolve_entry(str(empty), entry_kind="case_folder", driver_context=ctx)
```

- [ ] **Step 2: Run and confirm all three fail**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver/tests/core/test_case_is_a_path.py -q -p no:cacheprovider
```
Expected: the first two FAIL with `KeyError: "Unknown entry ..."`; the third
passes already (an unknown name is refused today for the wrong reason). Two
failures is the correct starting state.

- [ ] **Step 3: Implement**

In `registry.py`'s `resolve_entry`, insert immediately **before** the
`matched_entry = _match_entry(...)` line:

```python
    # A case is identified by its path. _is_case_directory() already decides
    # this from the directory's own contents via the plugin's declared marker
    # or entrypoint contract, so a case anywhere on disk resolves -- no root
    # required. See docs/superpowers/specs/2026-09-04-a-case-is-a-path-design.md.
    if entry_kind in {None, "case_folder"}:
        candidate = Path(key).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.is_dir() and _is_case_directory(candidate, driver_context):
            case_overrides = dict(incoming_overrides)
            case_overrides["tutorials_root"] = str(candidate.parent)
            case_overrides["case_dir_name"] = candidate.name
            plugin_factory = _get_plugin_tutorials(driver_context).get(
                "make_generic_case_spec",
            )
            factory = (
                plugin_factory
                if plugin_factory is not None
                and driver_context.capabilities.case_compatibility.has_case_marker(
                    CaseCompatibilityRequest(candidate),
                )
                else make_generic_case_spec
            )
            return {
                "resolution": "case_path",
                "requested_name": key,
                "requested_entry_kind": entry_kind,
                "resolved_name": candidate.name,
                "factory": factory,
                "factory_overrides": case_overrides,
                "entry_name": candidate.name,
                "entry_kind": "case_folder",
                "entry_path": str(candidate),
                "is_runnable": True,
                "source_type": "case_path",
                "workflow_family": None,
            }
```

`CaseCompatibilityRequest` is already imported at the top of `resolve_entry`;
`make_generic_case_spec` and `Path` are already module-level imports.

- [ ] **Step 4: Run and confirm all three pass**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver/tests/core/test_case_is_a_path.py -q -p no:cacheprovider
```
Expected: `3 passed`.

- [ ] **Step 5: Confirm the wheel failures drop**

Rebuild the wheel venv (see Global Constraints), then:
```bash
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
```
Expected: fewer than 13 failures. Record the exact number in the commit
message — it is the measure of this task.

- [ ] **Step 6: Full suite**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
```
Expected: **1554 passed** (1551 plus this task's three), 0 failed.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/runtime/registry.py packages/omnidriver/tests/core/test_case_is_a_path.py
git commit -m "feat: resolve a case by its path, not only by name under a root"
```

---

## Task 2: Core stops resolving an ambient root

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/specs/paths.py` (delete
  `tutorials_root_default`; keep `repo_root_default` but see Step 4)
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/registry.py:200,232,353`
- Modify: `packages/omnidriver/src/omnidriver/cli.py` (add the resolution chain)
- Modify: `packages/omnidriver/src/omnidriver/core/specs/common.py` (drop the
  re-export)

**Interfaces:**
- Consumes: Task 1's `case_path` resolution, which never needs a base.
- Produces: `cli.resolve_cases_root(explicit: str | Path | None) -> Path`,
  used by Task 3.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_case_is_a_path.py`:

```python
def test_listing_an_empty_directory_returns_nothing(tmp_path: Path) -> None:
    """Zero results is a legitimate answer to "what cases are here", and must
    not be a RuntimeError. Before this, core walked up from its own __file__
    looking for repository markers and raised when it found none."""
    from omnidriver.core.runtime.registry import list_case_directories

    ctx = driver_context(NeutralEnvironmentPlugin(), source="test:case-path")
    assert list_case_directories(tmp_path, driver_context=ctx) == []


def test_core_exposes_no_ambient_root_default() -> None:
    """core.specs.paths must not offer a function that invents a root."""
    from omnidriver.core.specs import paths

    assert not hasattr(paths, "tutorials_root_default")
```

- [ ] **Step 2: Run and confirm the second fails**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver/tests/core/test_case_is_a_path.py -q -p no:cacheprovider
```
Expected: `test_core_exposes_no_ambient_root_default` FAILS
(`tutorials_root_default` still exists); the listing test passes already in a
checkout. Both must pass by Step 6, and the listing one is what the wheel run
proves.

- [ ] **Step 3: Make the base a required parameter in core**

In `registry.py`, change all three sites so the caller supplies the base and
core never invents one:

`list_case_directories` and `list_entries` (lines ~200 and ~232) — replace
```python
    resolved_root = Path(tutorials_root) if tutorials_root is not None else tutorials_root_default()
```
with
```python
    # No ambient default: core does not know where a caller keeps cases.
    resolved_root = Path.cwd() if tutorials_root is None else Path(tutorials_root)
```

`resolve_entry` (line ~353) — replace
```python
    tutorials_root = Path(incoming_overrides.get("tutorials_root", tutorials_root_default()))
```
with
```python
    tutorials_root = Path(incoming_overrides.get("tutorials_root", Path.cwd()))
```

Then delete the `from omnidriver.core.specs.common import tutorials_root_default`
import at `registry.py:10`.

- [ ] **Step 4: Delete the function and its re-export**

In `packages/omnidriver/src/omnidriver/core/specs/paths.py`, delete
`tutorials_root_default()` entirely and put this in its place:

```python
# No tutorials_root_default() here any more. It returned repo_root_default() /
# "tutorials", so core invented a location for a caller's cases and raised
# outside a checkout -- which is why core could not plan a case from an
# installed wheel. A base is supplied now; see future/ENVIRONMENT_CONTRACT.md
# §12 on supplied-versus-discovered.
```

In `packages/omnidriver/src/omnidriver/core/specs/common.py`, remove
`tutorials_root_default` from both the import list and `__all__`.

`repo_root_default()` STAYS — `capability_seams.architecture_path()` and
`scripts/` legitimately need a checkout. Do not delete it.

- [ ] **Step 5: Add the resolution chain at the public edge**

In `packages/omnidriver/src/omnidriver/cli.py`, add near the other helpers:

```python
def resolve_cases_root(explicit: str | Path | None = None) -> Path:
    """Where to look for cases, resolved at the public edge only.

    explicit -> OMNIDRIVER_CASES_ROOT -> current working directory.

    Three steps, no fourth. The environment variable covers CI, containers and
    HPC without a flag on every invocation; a config-file tier is deliberately
    omitted until there is evidence one is needed
    (future/ENVIRONMENT_CONTRACT.md §12).
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    from_env = os.environ.get("OMNIDRIVER_CASES_ROOT")
    if from_env:
        return Path(from_env).expanduser()
    return Path.cwd()
```

`os` and `Path` are already imported in `cli.py`. At `cli.py:854-857`, replace
```python
    if args.tutorials_root:
```
...with an unconditional assignment so the chain always applies:
```python
    overrides["tutorials_root"] = str(resolve_cases_root(args.tutorials_root))
```
Keep the surrounding lines that set other overrides unchanged.

- [ ] **Step 6: Pin the registered-tutorial guarantee**

This is the constraint the whole design was checked against, and nothing above
tests it. Create
`packages/omnidriver-cardiacfoam/tests/test_registered_tutorials_need_no_repository.py`:

```python
"""Registered tutorials must keep working when core stops inventing a root.

Measured 2026-09-04 before the change: 18 of 26 catalog entries build under an
arbitrary empty base, niederer2012 among them. The other 8 are 4 tutorials
plus case-folded aliases which read pre-existing case content -- one file and
one key, <case>/system/decomposeParDict's numberOfSubdomains -- because a
parallel solve changes the DAG's shape and the rank count cannot be invented.
Those 4 already failed identically before this work, since this repository has
no tutorials/ tree at all.

Both halves are pinned so the distinction stops being rediscovered.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import load_plugin_context

_NEEDS_CASE_CONTENT = {
    "manufacturedbathbidomain",
    "manufacturedbidomain",
    "manufacturedeikonalecg",
    "manufacturedmonodomainpseudoecg",
}


def _factories():
    return load_plugin_context("cardiacfoam").capabilities.tutorials.catalog()[
        "spec_factories"
    ]


def test_niederer2012_builds_under_any_base(tmp_path: Path) -> None:
    spec = _factories()["niederer2012"](tutorials_root=tmp_path)
    assert Path(spec.case_root).is_relative_to(tmp_path)


def test_every_serial_tutorial_builds_under_any_base(tmp_path: Path) -> None:
    failed = []
    built = 0
    for index, (name, factory) in enumerate(sorted(_factories().items())):
        if name.casefold() in _NEEDS_CASE_CONTENT:
            continue
        # Index, not name: the catalog holds case-folded aliases
        # (cable1DCVConvergence and cable1dcvconvergence), which collide as
        # directory names on a case-insensitive filesystem such as macOS APFS.
        base = tmp_path / f"case{index}"
        base.mkdir()
        try:
            factory(tutorials_root=base)
            built += 1
        except Exception as exc:  # noqa: BLE001 -- report, do not mask
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    assert failed == [], "tutorials that stopped building under a plain base:\n" + "\n".join(failed)
    # Measured 2026-09-04. A sweep that silently covered zero tutorials would
    # otherwise assert nothing.
    assert built == 18, f"expected 18 buildable catalog entries, got {built}"


@pytest.mark.parametrize("name", sorted(_NEEDS_CASE_CONTENT))
def test_the_parallel_tutorials_still_ask_for_a_rank_count(name: str, tmp_path: Path) -> None:
    """The contrast is the point: without it, the sweep above would pass even
    if every tutorial had silently become content-dependent."""
    factory = {k.casefold(): v for k, v in _factories().items()}[name]
    with pytest.raises(ValueError, match="num_subdomains"):
        factory(tutorials_root=tmp_path)
```

- [ ] **Step 7: Run the acceptance test**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver-cardiacfoam/tests/test_registered_tutorials_need_no_repository.py -q -p no:cacheprovider
```
Expected: `6 passed` (two builds plus four parametrized refusals). If a
tutorial in the sweep fails, core's default removal broke it — fix the
threading, not the test.

- [ ] **Step 8: Run both suites**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -3
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
```
Expected: **1560 passed** on 3.13 — Task 1's 1554, plus this task's two core
tests and six acceptance tests — and 0 failed. Core-only **684 passed**: the
acceptance test lives in the cardiac package and does not run there.

If a test fails because it relied on the repo-root default, fix the TEST to
pass an explicit root — do not restore the default. That default is the
defect.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: core takes a cases base, it no longer invents one"
```

---

## Task 3: Scratch leaves the repository

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/specs/paths.py`
  (`driverfoam_scratch_root`, `default_sweep_output_dir`)
- Modify: `packages/omnidriver/src/omnidriver/cli.py:459,933,949`

**Interfaces:**
- Consumes: `cli.resolve_cases_root()` from Task 2.
- Produces: `paths.scratch_root(base: Path) -> Path` and
  `paths.default_sweep_output_dir(spec_path, *, base: Path) -> Path`.

- [ ] **Step 1: Write the failing test**

Append to `packages/omnidriver/tests/core/test_case_is_a_path.py`:

```python
def test_scratch_is_workspace_local_not_repository_local(tmp_path: Path) -> None:
    """`.tmp/driverfoam` wrote inside the repository, which fails on a
    read-only install and is solver-branded. It is workspace-local now --
    deliberately NOT the OS temp directory, because sweep outputs default here
    and having the OS reap them would be worse than the old behaviour."""
    from omnidriver.core.specs.paths import default_sweep_output_dir, scratch_root

    assert scratch_root(tmp_path) == tmp_path / ".omnidriver"
    out = default_sweep_output_dir("study.json", base=tmp_path)
    assert out == tmp_path / ".omnidriver" / "sweeps" / "study"


def test_scratch_honours_the_environment_variable(tmp_path: Path, monkeypatch) -> None:
    from omnidriver.core.specs.paths import scratch_root

    monkeypatch.setenv("OMNIDRIVER_SCRATCH_DIR", str(tmp_path / "elsewhere"))
    assert scratch_root(tmp_path) == tmp_path / "elsewhere"
```

- [ ] **Step 2: Run and confirm both fail**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver/tests/core/test_case_is_a_path.py -q -p no:cacheprovider -k scratch
```
Expected: FAIL with `ImportError: cannot import name 'scratch_root'`.

- [ ] **Step 3: Implement**

In `paths.py`, replace `driverfoam_scratch_root()` and
`default_sweep_output_dir()` with:

```python
def scratch_root(base: Path) -> Path:
    """Disposable working data, kept beside the workspace rather than inside
    the installation.

    ``OMNIDRIVER_SCRATCH_DIR`` overrides. Deliberately NOT the OS temp
    directory: sweep outputs default under here, and somewhere the OS reaps
    would be worse than the repository-local `.tmp/driverfoam` this replaces.
    """
    import os

    override = os.environ.get("OMNIDRIVER_SCRATCH_DIR")
    if override:
        return Path(override).expanduser()
    return Path(base) / ".omnidriver"


def default_sweep_output_dir(spec_path: str | Path, *, base: Path) -> Path:
    """Return the standard output location for a sweep specification."""
    return scratch_root(base) / "sweeps" / Path(spec_path).stem
```

In `cli.py`, at line ~459 replace `driverfoam_scratch_root()` with
`scratch_root(resolve_cases_root(args.tutorials_root))`, and at lines ~933 and
~949 replace `default_sweep_output_dir(args.spec)` with
`default_sweep_output_dir(args.spec, base=resolve_cases_root(args.tutorials_root))`.
Update `cli.py`'s import at line 21-22 to name `scratch_root` instead of
`driverfoam_scratch_root`.

- [ ] **Step 4: Run and confirm they pass**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
```
Expected: **1562 passed**, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: scratch and sweep output leave the repository"
```

---

## Task 4: The guard and the CI wheel job

**Files:**
- Modify: `packages/omnidriver/tests/core/test_core_context_is_explicit.py`
- Modify: `.github/workflows/ci.yml` (the `test-wheel` job)

**Interfaces:**
- Consumes: Tasks 1-3 complete.
- Produces: nothing.

- [ ] **Step 1: Extend the static guard**

Append to `packages/omnidriver/tests/core/test_core_context_is_explicit.py`:

```python
# Functions that invent a filesystem location rather than receiving one. Core
# must call none of them: doing so is what made core unable to plan a case
# from a wheel install. Written out explicitly, like
# _CONTEXT_TAKING_PUBLIC_EDGE above, with a companion test that fails if a
# name here stops existing -- a guard naming nothing guards nothing.
_ROOT_INVENTING = {"repo_root_default", "cardiacfoam_monorepo_root"}

# capability_seams.architecture_path() legitimately needs a checkout: it
# points at ARCHITECTURE.md for the seam-table generator, which is dev
# tooling, never a runtime path.
_ROOT_EXEMPT = {_CORE_ROOT / "capability_seams.py", _CORE_ROOT / "specs" / "paths.py"}


def test_the_root_inventing_names_still_exist() -> None:
    from omnidriver.core.specs import paths

    for name in sorted(_ROOT_INVENTING):
        assert hasattr(paths, name), (
            f"{name} is named by _ROOT_INVENTING but no longer exists. Update "
            "the set rather than letting this guard quietly cover nothing."
        )


def test_core_never_invents_a_filesystem_root() -> None:
    offenders: dict[str, list[int]] = {}
    for path in sorted(_CORE_ROOT.rglob("*.py")):
        if path in _ROOT_EXEMPT or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in _ROOT_INVENTING
        ]
        if hits:
            offenders[str(path.relative_to(_CORE_ROOT))] = hits

    assert offenders == {}, (
        "core/ modules inventing a filesystem root:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nTake the location as a parameter instead."
    )
```

- [ ] **Step 2: Run the guard**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/omnidriver/tests/core/test_core_context_is_explicit.py -q -p no:cacheprovider
```
Expected: PASS. If it fails, it has found a real caller Tasks 2-3 missed —
fix the caller, not the guard.

- [ ] **Step 3: Confirm the whole point of the work**

Rebuild the wheel venv (see Global Constraints), then:
```bash
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
```
Expected: **0 failed.** This is the plan's success criterion. If failures
remain, stop and report them individually rather than skipping them — a skip
here would hide exactly the defect this plan exists to remove.

- [ ] **Step 4: Upgrade the CI wheel job to run the suite**

In `.github/workflows/ci.yml`, in the `test-wheel` job, after the existing
"Verify the installed artifact runs standalone" step, add:

```yaml
      - name: Run core's suite against the installed wheel
        run: |
          /tmp/wheelenv/bin/pip install pytest
          /tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```

Keep the artifact-gate step: it checks things the suite does not, including
that `python -m omnidriver --help` exits 0.

- [ ] **Step 5: Full verification on both floors**

Run:
```bash
/tmp/od_all/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od311b/bin/python -m pytest packages/ -q -m "not slow" -p no:cacheprovider 2>&1 | tail -2
/tmp/od_core/bin/python -m pytest packages/omnidriver/tests -q -p no:cacheprovider 2>&1 | tail -2
/tmp/od_all/bin/python scripts/check-import-boundaries.py
/tmp/od_all/bin/python scripts/export-capability-seams.py --check
```
Expected: **1564 passed** on 3.13 and 3.11; core-only **686 passed**; both gates green.

- [ ] **Step 6: Update the record**

In `GITHUB_MIGRATION.md`, add to the CI row: the `test-wheel` job now runs
core's suite against the installed wheel, not only the artifact gate. In
`docs/superpowers/specs/2026-09-04-a-case-is-a-path-design.md`, mark the
Success Criteria section as met, dated 2026-09-04, with the measured numbers.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "test: guard against inventing a root, and run the suite against the wheel"
```

---

## Deferred, with reasons

- **Renaming `tutorials_root` to `cases_root`** (397 occurrences). The spec
  approved the rename; this plan does not do it. The threading above fixes the
  defect and is verified by the wheel suite going green; the rename is
  mechanical and verified by the suite being unchanged. Landing them together
  would make review harder and a revert all-or-nothing. It is its own plan.
- **`resolve_run_script_path`'s three-candidate fallback**
  (`specs/paths.py:136`) still calls `repo_root_default()`. It is in
  `_ROOT_EXEMPT` above because it lives in `paths.py`. Task 4's guard therefore
  does not cover it — flagged in the spec's Risks as the likeliest surprise,
  and it needs its own decision about what a run script is relative to.
- **The four parallel tutorials** still need their case on disk or an explicit
  `num_subdomains`; see `future/ENVIRONMENT_CONTRACT.md` §12.
