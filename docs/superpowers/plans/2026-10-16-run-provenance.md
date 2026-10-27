# Run Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every run document lists, per solver, which source built each binary or package the run uses, and `stale_build` compares that source with the supplied repository by digest instead of file times.

**Architecture:** one optional contract member, `get_solver_builds`, answered by each solver plugin in its own way (wmake: a build record written by `omnidriver build-record`; openCARP: `-buildinfo`; TorchCor: the editable package read live). Core owns the dataclasses, git identity, digests, the build record, the run document's `solverProvenance` list and the preflight diagnostics.

**Tech Stack:** Python 3.11+, pytest, jsonschema, git CLI.

**Spec:** `docs/superpowers/specs/2026-10-16-run-provenance-design.md`

## Global Constraints

- Work only in the worktree `/Users/simaocastro/omnidriver/.claude/worktrees/run-provenance`, branch `feat/run-provenance`. Never `cd` to the main checkout.
- Test with the worktree's own venv `/tmp/od-prov` (Task 1, Step 0). `/tmp/od311` imports the main checkout and gives false greens.
- Python floor 3.11.
- House style (`CLAUDE.md`): comments only for the non-obvious, docstrings on the public surface only, no history in code, no commented-out code, no TODOs, name symbols never `file.py:123`.
- Core (`packages/omnidriver`) names no solver and no OpenFOAM layout token (`wmake`, `Make/files`, `FOAM_USER_*`), not even in messages or docstrings; `scripts/check-core-shape.py` gates it.
- Core never invents a filesystem root: no `__file__`, `Path.cwd`, `Path.home`, `os.getcwd` in new core code.
- No contract version bump: `SUPPORTED_PLUGIN_API_VERSIONS` stays `{"3"}`.
- Digests are `sha256:<64 hex>`, the format `ProvenanceComponent.digest` already uses.
- The `known` values are exactly `recorded`, `self_reported`, `live`, `unknown`.
- Diagnostic codes: `stale_build` (warning), `build_source_unknown` (info). New refusal code: `build_products_undeclared`.
- Record file name `omnidriver-build.json`, `version` 1.
- `cardiacFoam.build.json` and `omnidriver/cardiacfoam/runtime_profile.py` are not touched.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A malformed or foreign `omnidriver-build.json` beside a binary: read as no record (`unknown`), never a crash; `build-record` replaces it. Test in Task 2.
2. A binary reached through a symlink on `PATH` (`/usr/local/bin/openCARP` links into the install): `used_paths` and product paths are compared resolved, so it is still listed. Test in Task 5.
3. A `.git` that is not a usable repository (a worktree file pointing nowhere, or no `git` on `PATH`): `git` is `null`, no crash. Test in Task 1.
4. A repository whose `Make/files` declare nothing (cardiacSubstrateFOAM's case tree): no entry, so `build-record` refuses with `build_products_undeclared` instead of reporting an empty success. Test in Task 5.
5. Two worktrees building into one platform folder: recording one keeps the other's entries. Test in Task 2.

---

### Task 1: Contract types, member, git identity and digests

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/plugin_interface.py` (beside `RuntimeDependency`; the protocol's `# -- provenance` section)
- Modify: `packages/omnidriver/src/omnidriver/core/provider_stack.py` (`MEMBERS`, `# provenance` block)
- Create: `packages/omnidriver/src/omnidriver/core/runtime/build_identity.py`
- Test: `packages/omnidriver/tests/core/test_build_identity.py`

**Interfaces:**
- Produces: `SourceIdentity(repository: str | None = None, digest: str | None = None, git: Mapping[str, Any] | None = None)` with `to_json() -> dict`; `SolverBuild(name: str, path: Path | None, digest: str | None, known: str, source: SourceIdentity | None = None)`; `SolverEntry(solver: str, repository: SourceIdentity | None, builds: tuple[SolverBuild, ...], recordable: bool = False)`; `KNOWN = ("recorded", "self_reported", "live", "unknown")`; member `get_solver_builds(env, *, repository, used_paths)` composed as `("sequence", None)`; `build_identity.file_digest(path) -> str | None`, `build_identity.tree_digest(root, files) -> str`, `build_identity.git_identity(directory) -> dict | None`.

- [ ] **Step 0: Build the worktree's venv**

```bash
cd /Users/simaocastro/omnidriver/.claude/worktrees/run-provenance
rm -rf /tmp/od-prov && uv venv -q --python 3.11 /tmp/od-prov && VIRTUAL_ENV=/tmp/od-prov uv pip install -q \
  -e "packages/omnidriver[post]" -e packages/omnidriver-openfoam -e packages/omnidriver-cardiacfoam \
  -e packages/omnidriver-cardiacsubstrate -e packages/omnidriver-opencarp -e packages/omnidriver-torchcor \
  -e packages/omnidriver-agents -e "packages/omnidriver-verifier[symbolic]" pytest
/tmp/od-prov/bin/python -c "import omnidriver.core, sympy; print(omnidriver.core.__file__)"
```
Expected: a path inside `.claude/worktrees/run-provenance/`.

- [ ] **Step 1: Write the failing tests**

```python
"""Which source a build came from: digests, git identity and the contract member."""
from __future__ import annotations

import subprocess
from pathlib import Path

from omnidriver.core import provider_stack
from omnidriver.core.plugin_interface import KNOWN, SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import file_digest, git_identity, tree_digest


def _git(root: Path, *args: str) -> None:
    subprocess.run(("git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args),
                   check=True, capture_output=True)


def test_file_digest_is_the_content_hash_and_none_for_an_absent_file(tmp_path):
    binary = tmp_path / "solver"
    binary.write_bytes(b"one")
    import hashlib
    assert file_digest(binary) == "sha256:" + hashlib.sha256(b"one").hexdigest()
    assert file_digest(tmp_path / "absent") is None


def test_tree_digest_depends_on_paths_and_bytes_not_on_listing_order(tmp_path):
    (tmp_path / "a.C").write_text("a")
    (tmp_path / "b.H").write_text("b")
    files = [tmp_path / "a.C", tmp_path / "b.H"]
    first = tree_digest(tmp_path, files)
    assert first == tree_digest(tmp_path, list(reversed(files)))
    assert first.startswith("sha256:") and len(first) == 7 + 64
    (tmp_path / "b.H").write_text("changed")
    assert tree_digest(tmp_path, files) != first


def test_git_identity_reads_commit_and_dirty_only_at_the_given_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "a.C").write_text("a")
    _git(repo, "add", "a.C")
    _git(repo, "commit", "-q", "-m", "one")
    head = subprocess.run(("git", "-C", str(repo), "rev-parse", "HEAD"), capture_output=True, text=True).stdout.strip()
    assert git_identity(repo) == {"commit": head, "dirty": False}
    (repo / "a.C").write_text("edited")
    assert git_identity(repo) == {"commit": head, "dirty": True}
    (repo / "sub").mkdir()
    assert git_identity(repo / "sub") is None


def test_a_git_file_that_is_no_repository_gives_no_identity(tmp_path):
    (tmp_path / ".git").write_text("gitdir: /nowhere/at/all\n")
    assert git_identity(tmp_path) is None


def test_source_identity_serialises_every_field():
    identity = SourceIdentity(repository="/r", digest="sha256:" + "0" * 64, git={"commit": "abc", "dirty": False})
    assert identity.to_json() == {"repository": "/r", "digest": "sha256:" + "0" * 64,
                                  "git": {"commit": "abc", "dirty": False}}
    assert SourceIdentity().to_json() == {"repository": None, "digest": None, "git": None}


def test_get_solver_builds_is_optional_and_answers_nothing_when_absent():
    assert provider_stack.MEMBERS["get_solver_builds"] == ("sequence", None)

    class _None:
        plugin_id = "org.none"

    stack = provider_stack.ProviderStack(provider_stack.order_providers((_None(),)))
    assert stack.call("get_solver_builds", {}, repository=None, used_paths=None) == ()


def test_solver_entries_compose_as_a_list_over_providers():
    entry = SolverEntry(solver="s", repository=None,
                        builds=(SolverBuild(name="x", path=None, digest=None, known="unknown"),))

    class _One:
        plugin_id = "org.one"

        def get_solver_builds(self, env, *, repository, used_paths):
            return (entry,)

    stack = provider_stack.ProviderStack(provider_stack.order_providers((_One(),)))
    assert stack.call("get_solver_builds", {}, repository=None, used_paths=None) == (entry,)
    assert KNOWN == ("recorded", "self_reported", "live", "unknown")
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_identity.py -q`
Expected: collection error, `ImportError: cannot import name 'KNOWN'`.

- [ ] **Step 3: Add the dataclasses and the protocol member**

In `plugin_interface.py`, after the `RuntimeDependency` class:

```python
#: How a solver build's source is known: a build record beside it, the binary's own report, the
#: editable package read when the plan is made, or nothing.
KNOWN = ("recorded", "self_reported", "live", "unknown")


@dataclass(frozen=True)
class SourceIdentity:
    """Which source a build came from: the tree's digest under its solver's rule, and its git
    identity (``commit``, ``tag``, ``dirty``, each optional) when known."""

    repository: str | None = None
    digest: str | None = None
    git: Mapping[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {"repository": self.repository, "digest": self.digest,
                "git": dict(self.git) if self.git is not None else None}


@dataclass(frozen=True)
class SolverBuild:
    """One product a run uses: where it is, its content digest, and the source it was built from."""

    name: str
    path: Path | None
    digest: str | None
    known: str
    source: SourceIdentity | None = None


@dataclass(frozen=True)
class SolverEntry:
    """One solver's item in a run document's ``solverProvenance`` list. ``recordable`` marks a
    solver whose builds are known only through a build record."""

    solver: str
    repository: SourceIdentity | None
    builds: tuple[SolverBuild, ...]
    recordable: bool = False
```

In the protocol, `# -- provenance` section, after `get_extra_provenance_paths`:

```python
    def get_solver_builds(
        self, env: Mapping[str, str], *, repository: "Repository | None", used_paths: frozenset[Path] | None,
    ) -> tuple[SolverEntry, ...]:
        """At most one entry: which source built each product this solver's plans run.
        ``used_paths`` holds the resolved paths a plan runs; ``None`` asks for every product."""
```

In `provider_stack.py` `MEMBERS`, after `"get_extra_provenance_paths": ("sequence", None),`:

```python
    "get_solver_builds": ("sequence", None),
```

- [ ] **Step 4: Create `core/runtime/build_identity.py` (digests and git only; Task 2 adds the record)**

```python
"""Which source built what a run uses: content digests, a tree's digest, and git identity."""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .provenance import component_for_path


def file_digest(path: Path) -> str | None:
    """``sha256:<hex>`` of ``path``'s bytes, the resume snapshot's content hash; ``None`` when unreadable."""
    path = Path(path)
    component = component_for_path(path, kind="build", relative_to=path.parent)
    return component.digest if component.strength == "content" else None


def tree_digest(root: Path, files: Iterable[Path]) -> str:
    """``sha256:<hex>`` of ``files`` under ``root``, in sorted relative-path order, each as its path and bytes."""
    root = Path(root)
    digest = hashlib.sha256()
    for relative in sorted(Path(path).relative_to(root).as_posix() for path in files):
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def git_identity(directory: Path) -> dict[str, Any] | None:
    """``{"commit", "dirty"}`` of the checkout rooted at ``directory``; ``None`` without a usable
    ``directory/.git``. No parent directory is searched."""
    directory = Path(directory)
    if not (directory / ".git").exists():
        return None
    commit = _git(directory, "rev-parse", "HEAD")
    if not commit:
        return None
    status = _git(directory, "status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _git(directory: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(("git", "-C", str(directory), *args),
                              capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None
```

- [ ] **Step 5: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_identity.py packages/omnidriver/tests/core/test_plugin_contract.py -q`
Expected: all pass (the contract test checks the protocol and `MEMBERS` agree).

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/plugin_interface.py packages/omnidriver/src/omnidriver/core/provider_stack.py \
  packages/omnidriver/src/omnidriver/core/runtime/build_identity.py packages/omnidriver/tests/core/test_build_identity.py
git commit -m "feat(core): get_solver_builds, a solver's build identity, git identity and digests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The build record

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/attempt_lease.py` (rename `_lease_record_guard` to `record_guard`, public)
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/build_identity.py`
- Test: `packages/omnidriver/tests/core/test_build_record.py`

**Interfaces:**
- Consumes: `SolverBuild`, `SourceIdentity`, `file_digest` (Task 1).
- Produces: `RECORD_FILENAME = "omnidriver-build.json"`, `RECORD_VERSION = 1`, `recorded_build(name: str, path: Path | None) -> SolverBuild`, `write_records(builds: Iterable[SolverBuild], source: SourceIdentity) -> tuple[Path, ...]`, `attempt_lease.record_guard(path: Path)` context manager.

- [ ] **Step 1: Write the failing tests**

```python
"""The build record beside a product: what a stack whose binaries cannot identify themselves keeps."""
from __future__ import annotations

import json

from omnidriver.core.plugin_interface import SolverBuild, SourceIdentity
from omnidriver.core.runtime.build_identity import (
    RECORD_FILENAME, file_digest, recorded_build, write_records,
)

SOURCE = SourceIdentity(repository="/src/a", digest="sha256:" + "a" * 64, git={"commit": "c1", "dirty": False})
OTHER = SourceIdentity(repository="/src/b", digest="sha256:" + "b" * 64, git=None)


def _product(directory, name, content=b"bin"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    return SolverBuild(name=name, path=path, digest=file_digest(path), known="unknown")


def test_a_recorded_product_is_read_back_with_its_source(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    (written,) = write_records([build], SOURCE)
    assert written == tmp_path / "bin" / RECORD_FILENAME
    payload = json.loads(written.read_text())
    assert payload["version"] == 1
    assert payload["products"]["mySolver"]["digest"] == build.digest
    assert payload["products"]["mySolver"]["source"] == SOURCE.to_json()

    read = recorded_build("mySolver", build.path)
    assert (read.known, read.digest, read.source) == ("recorded", build.digest, SOURCE)


def test_a_product_rebuilt_after_recording_is_unknown(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    write_records([build], SOURCE)
    build.path.write_bytes(b"rebuilt")
    read = recorded_build("mySolver", build.path)
    assert (read.known, read.source) == ("unknown", None)
    assert read.digest == file_digest(build.path)


def test_no_record_or_no_file_is_unknown(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    assert recorded_build("mySolver", build.path).known == "unknown"
    absent = recorded_build("gone", tmp_path / "bin" / "gone")
    assert (absent.known, absent.digest) == ("unknown", None)
    assert recorded_build("none", None).path is None


def test_a_malformed_record_is_no_record_and_is_replaced(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    (tmp_path / "bin" / RECORD_FILENAME).write_text("{not json")
    assert recorded_build("mySolver", build.path).known == "unknown"
    write_records([build], SOURCE)
    assert recorded_build("mySolver", build.path).known == "recorded"


def test_recording_one_worktree_keeps_the_other_worktrees_entries(tmp_path):
    first = _product(tmp_path / "bin", "solverA", b"a")
    second = _product(tmp_path / "bin", "solverB", b"b")
    write_records([first], SOURCE)
    write_records([second], OTHER)
    assert recorded_build("solverA", first.path).source == SOURCE
    assert recorded_build("solverB", second.path).source == OTHER


def test_products_in_two_directories_get_one_record_each_and_absent_builds_none(tmp_path):
    app = _product(tmp_path / "bin", "mySolver")
    lib = _product(tmp_path / "lib", "libModels.so")
    missing = SolverBuild(name="never", path=None, digest=None, known="unknown")
    written = write_records([app, lib, missing], SOURCE)
    assert sorted(written) == sorted([tmp_path / "bin" / RECORD_FILENAME, tmp_path / "lib" / RECORD_FILENAME])
    assert not (tmp_path / "bin" / (RECORD_FILENAME + ".tmp")).exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_record.py -q`
Expected: `ImportError: cannot import name 'RECORD_FILENAME'`.

- [ ] **Step 3: Make the record guard public**

In `attempt_lease.py`, rename `def _lease_record_guard(path: Path)` to `def record_guard(path: Path)` and its docstring to `"""Serialize access to a record file through a guard file beside it; the guard stays put (deleting it would recreate the read/unlink race)."""`. Update its one caller (`with _lease_record_guard(path):` becomes `with record_guard(path):`). Check none remain:

Run: `grep -rn "_lease_record_guard" packages/`
Expected: no output.

- [ ] **Step 4: Add the record to `build_identity.py`**

Add imports (`json`, `os`, `datetime`, `timezone`, `Mapping`) and these names:

```python
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from ..plugin_interface import SolverBuild, SourceIdentity
from .attempt_lease import record_guard

#: The record a stack whose binaries cannot identify themselves keeps beside them.
RECORD_FILENAME = "omnidriver-build.json"
RECORD_VERSION = 1


def recorded_build(name: str, path: Path | None) -> SolverBuild:
    """``name`` at ``path`` as the record beside it states it: ``recorded`` with the record's
    source when the record names this file's digest, else ``unknown``."""
    if path is None or not Path(path).is_file():
        return SolverBuild(name=name, path=path, digest=None, known="unknown")
    path = Path(path)
    digest = file_digest(path)
    entry = _products(path.parent).get(name)
    if digest is None or not isinstance(entry, Mapping) or entry.get("digest") != digest:
        return SolverBuild(name=name, path=path, digest=digest, known="unknown")
    return SolverBuild(name=name, path=path, digest=digest, known="recorded", source=_identity(entry.get("source")))


def write_records(builds: Iterable[SolverBuild], source: SourceIdentity) -> tuple[Path, ...]:
    """Record each build that exists as built from ``source``, merged into the record beside it;
    the record files written."""
    by_directory: dict[Path, list[SolverBuild]] = {}
    for build in builds:
        if build.path is not None and build.digest is not None:
            by_directory.setdefault(Path(build.path).parent, []).append(build)
    recorded_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    written = []
    for directory, group in sorted(by_directory.items()):
        record = directory / RECORD_FILENAME
        with record_guard(record):
            products = dict(_products(directory))
            for build in group:
                products[build.name] = {"digest": build.digest, "recordedAt": recorded_at, "source": source.to_json()}
            temporary = record.with_name(RECORD_FILENAME + ".tmp")
            temporary.write_text(json.dumps({"version": RECORD_VERSION, "products": products}, indent=2, sort_keys=True) + "\n")
            os.replace(temporary, record)
        written.append(record)
    return tuple(written)


def _products(directory: Path) -> dict[str, Any]:
    try:
        payload = json.loads((Path(directory) / RECORD_FILENAME).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("version") != RECORD_VERSION:
        return {}
    products = payload.get("products")
    return products if isinstance(products, dict) else {}


def _identity(raw: Any) -> SourceIdentity | None:
    if not isinstance(raw, Mapping):
        return None
    git = raw.get("git")
    return SourceIdentity(repository=raw.get("repository"), digest=raw.get("digest"),
                          git=dict(git) if isinstance(git, Mapping) else None)
```

Update the module docstring to: `"""Which source built what a run uses: content digests, a tree's digest, git identity, and the build record a stack whose binaries cannot identify themselves keeps beside them."""`

- [ ] **Step 5: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_record.py packages/omnidriver/tests/core/test_build_identity.py -q && /tmp/od-prov/bin/python -m pytest packages/omnidriver/tests -q -k "lease"`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/runtime/attempt_lease.py packages/omnidriver/src/omnidriver/core/runtime/build_identity.py \
  packages/omnidriver/tests/core/test_build_record.py
git commit -m "feat(core): the build record beside a solver's products

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `solverProvenance` in the run document, and the preflight

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py` (extract `runtime_dependencies` from `enumerate_case_inputs`)
- Create: `packages/omnidriver/src/omnidriver/core/runtime/solver_provenance.py`
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/run_model.py` (`RunDocument`)
- Modify: `packages/omnidriver/src/omnidriver/schemas/run-document.json`
- Modify: `packages/omnidriver/src/omnidriver/core/strict_planning.py` (`_strict_plan_for_spec`)
- Test: `packages/omnidriver/tests/core/test_solver_provenance.py`

**Interfaces:**
- Consumes: `SolverEntry`, `SolverBuild`, `SourceIdentity` (Task 1).
- Produces: `provenance_inputs.runtime_dependencies(case_root, *, workflow_dag, driver_context, env=None, add_case_file=None) -> dict[str, RuntimeDependency]`; `solver_provenance.solver_entries(case_root, *, workflow_dag, driver_context, env) -> tuple[SolverEntry, ...]`; `solver_provenance.to_json(entries) -> list[dict]`; `solver_provenance.matches(build, repository) -> bool | None`; `solver_provenance.provenance_diagnostics(entries) -> tuple[StrictDiagnostic, ...]`; `RunDocument.solverProvenance: list[dict] | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""Each solver's builds a plan uses, as the run document's list, and how the preflight judges them."""
from __future__ import annotations

import stat
from pathlib import Path

from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity, driver_context
from omnidriver.core.runtime.solver_provenance import matches, provenance_diagnostics, to_json
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import case_folder_record

from plugins.toy import E2EFolderPlugin

HERE = SourceIdentity(repository="/src/here", digest="sha256:" + "a" * 64, git={"commit": "aaa", "dirty": False})
THERE = SourceIdentity(repository="/src/there", digest="sha256:" + "b" * 64, git={"commit": "bbb", "dirty": True})
DIGEST = "sha256:" + "c" * 64


def _build(name, known, source=None):
    return SolverBuild(name=name, path=Path(f"/bin/{name}"), digest=DIGEST, known=known, source=source)


def test_matches_compares_digests_and_is_none_without_both():
    assert matches(_build("s", "recorded", HERE), HERE) is True
    assert matches(_build("s", "recorded", THERE), HERE) is False
    assert matches(_build("s", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})), HERE) is None
    assert matches(_build("s", "recorded", HERE), None) is None


def test_the_list_has_one_item_per_solver_with_every_field():
    entries = (
        SolverEntry(solver="wmakeSolver", repository=HERE, builds=(_build("mySolver", "recorded", THERE),), recordable=True),
        SolverEntry(solver="org.binary", repository=None,
                    builds=(_build("bin", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})),)),
    )
    (first, second) = to_json(entries)
    assert first == {
        "solver": "wmakeSolver", "repository": HERE.to_json(),
        "builds": [{"name": "mySolver", "path": "/bin/mySolver", "digest": DIGEST, "known": "recorded",
                    "source": THERE.to_json(), "matchesRepository": False}],
    }
    assert second["repository"] is None and second["builds"][0]["matchesRepository"] is None


def test_a_build_from_other_source_is_a_stale_build_warning_naming_both_sides():
    entry = SolverEntry(solver="wmakeSolver", repository=HERE,
                        builds=(_build("mySolver", "recorded", THERE), _build("libModels", "recorded", THERE),
                                _build("ok", "recorded", HERE)), recordable=True)
    (warning,) = provenance_diagnostics((entry,))
    assert (warning.level, warning.code) == ("warning", "stale_build")
    for fragment in ("mySolver", "libModels", "/src/there", "bbb", "/src/here", "aaa"):
        assert fragment in warning.message, (fragment, warning.message)
    assert "ok," not in warning.message


def test_an_unknown_build_is_one_info_note_and_a_recordable_one_says_how_to_record():
    entry = SolverEntry(solver="wmakeSolver", repository=HERE,
                        builds=(_build("a", "unknown"), _build("b", "unknown")), recordable=True)
    (note,) = provenance_diagnostics((entry,))
    assert (note.level, note.code) == ("info", "build_source_unknown")
    assert "a, b" in note.message and "omnidriver build-record --repo /src/here" in note.message
    live = SolverEntry(solver="pkg", repository=HERE, builds=(_build("p", "unknown"),))
    (plain,) = provenance_diagnostics((live,))
    assert "build-record" not in plain.message


def test_self_reported_live_and_matching_builds_say_nothing():
    entry = SolverEntry(solver="x", repository=HERE, builds=(
        _build("a", "recorded", HERE), _build("b", "live", HERE),
        _build("c", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})),
    ))
    assert provenance_diagnostics((entry,)) == ()


class _ProvenancePlugin(E2EFolderPlugin):
    def get_solver_builds(self, env, *, repository, used_paths):
        return (SolverEntry(solver="toySolver", repository=HERE,
                            builds=(SolverBuild(name="run-test-case", path=None, digest=None, known="unknown"),),
                            recordable=True),)


def test_a_strict_plan_writes_the_list_and_the_note(tmp_path):
    case = tmp_path / "cases" / "myCase"
    (case / "system").mkdir(parents=True)
    (case / "system" / "input.txt").write_text("authored\n")
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\necho done > ran.marker\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    ctx = driver_context(_ProvenancePlugin(), source="test:provenance")
    record, cases_root = case_folder_record(case, driver_context=ctx)

    report = strict_plan(record, overrides={"cases_root": str(cases_root)}, scratch_root=tmp_path / "scratch",
                         driver_context=ctx)

    document = report.run_document.to_json()
    assert document["solverProvenance"][0]["solver"] == "toySolver"
    assert document["solverProvenance"][0]["builds"][0]["known"] == "unknown"
    assert "build_source_unknown" in [d.code for d in report.environment_diagnostics]
    assert report.status == "ok"


def test_a_stack_with_no_solver_builds_writes_no_list(tmp_path):
    case = tmp_path / "cases" / "plain"
    (case / "system").mkdir(parents=True)
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    ctx = driver_context(E2EFolderPlugin(), source="test:provenance")
    record, cases_root = case_folder_record(case, driver_context=ctx)
    report = strict_plan(record, overrides={"cases_root": str(cases_root)}, scratch_root=tmp_path / "scratch",
                         driver_context=ctx)
    assert "solverProvenance" not in report.run_document.to_json()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_solver_provenance.py -q`
Expected: `ModuleNotFoundError: No module named 'omnidriver.core.runtime.solver_provenance'`.

- [ ] **Step 3: Extract `runtime_dependencies` in `provenance_inputs.py`**

Add this function above `enumerate_case_inputs`:

```python
def runtime_dependencies(
    case_root: Path,
    *,
    workflow_dag: dict[str, Any] | None,
    driver_context: "DriverContext",
    env: Mapping[str, str] | None = None,
    add_case_file: "_ComponentAdder | None" = None,
) -> dict[str, RuntimeDependency]:
    """The step executables (an MPI launcher's payload included) and the stack's
    ``get_extra_provenance_paths``, by name; a case-local script goes to ``add_case_file``."""
    case_root = Path(case_root)
    environment = dict(os.environ) if env is None else dict(env)
    add = add_case_file if add_case_file is not None else (lambda component: None)
    dependencies: dict[str, RuntimeDependency] = {}
    for step in (workflow_dag or {}).get("steps", ()):
        parsed = _step_command_and_args(step)
        if parsed is None:
            continue
        command, args = parsed
        resolved_cwd = _resolve_case_cwd(case_root, str(step.get("cwd", ".")))
        _register_step_executable(
            command, resolved_cwd=resolved_cwd, case_root=case_root, env=environment,
            add_case_file=add, dependencies=dependencies, driver_context=driver_context,
        )
        if command in mpi.LAUNCHERS:
            payload = mpi.program(args)
            if payload:
                _register_step_executable(
                    payload, resolved_cwd=resolved_cwd, case_root=case_root, env=environment,
                    add_case_file=add, dependencies=dependencies, driver_context=driver_context,
                )
    for dependency in driver_context.stack.call("get_extra_provenance_paths", case_root):
        dependencies[dependency.name] = dependency
    return dependencies
```

In `enumerate_case_inputs`, replace everything from the `# -- step executables` comment through the `for dependency in stack.call("get_extra_provenance_paths", case_root): dependencies[dependency.name] = dependency` loop with:

```python
    # Step executables and the plugin's declared runtime dependencies (the
    # solver binary and its libraries), deduplicated by name; the plugin's
    # declaration wins over the PATH-only resolution of a step's command.
    dependencies = runtime_dependencies(
        case_root, workflow_dag=workflow_dag, driver_context=driver_context,
        env=environment, add_case_file=add,
    )
```

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests -q -k "provenance or resume"`
Expected: pass (no behaviour change).

- [ ] **Step 4: Create `core/runtime/solver_provenance.py`**

```python
"""Each solver's builds a plan uses, as the run document's ``solverProvenance`` list, and the
preflight that compares their source with the supplied repository."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from ..planning_types import StrictDiagnostic, diagnostic
from ..plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from .provenance_inputs import runtime_dependencies


def solver_entries(
    case_root: Path, *, workflow_dag: dict[str, Any] | None, driver_context: Any, env: Mapping[str, str],
) -> tuple[SolverEntry, ...]:
    """The stack's ``get_solver_builds``, limited to the paths this plan runs."""
    dependencies = runtime_dependencies(case_root, workflow_dag=workflow_dag, driver_context=driver_context, env=env)
    used = frozenset(Path(d.path).resolve() for d in dependencies.values() if d.path is not None)
    return tuple(driver_context.stack.call(
        "get_solver_builds", env, repository=driver_context.repository, used_paths=used,
    ))


def matches(build: SolverBuild, repository: SourceIdentity | None) -> bool | None:
    """Whether ``build`` came from ``repository``, by digest; ``None`` when either digest is unknown."""
    if build.source is None or build.source.digest is None or repository is None or repository.digest is None:
        return None
    return build.source.digest == repository.digest


def to_json(entries: Iterable[SolverEntry]) -> list[dict[str, Any]]:
    return [
        {
            "solver": entry.solver,
            "repository": entry.repository.to_json() if entry.repository is not None else None,
            "builds": [
                {
                    "name": build.name,
                    "path": str(build.path) if build.path is not None else None,
                    "digest": build.digest,
                    "known": build.known,
                    "source": build.source.to_json() if build.source is not None else None,
                    "matchesRepository": matches(build, entry.repository),
                }
                for build in entry.builds
            ],
        }
        for entry in entries
    ]


def provenance_diagnostics(entries: Iterable[SolverEntry]) -> tuple[StrictDiagnostic, ...]:
    """``stale_build`` for builds recorded from other source than the supplied repository, one per
    solver and source; ``build_source_unknown`` for builds nothing identifies, one per solver."""
    found: list[StrictDiagnostic] = []
    for entry in entries:
        elsewhere: dict[tuple[Any, ...], list[SolverBuild]] = {}
        unknown: list[SolverBuild] = []
        for build in entry.builds:
            if build.known == "unknown":
                unknown.append(build)
            elif matches(build, entry.repository) is False:
                key = (build.source.repository, build.source.digest, _commit(build.source))
                elsewhere.setdefault(key, []).append(build)
        for builds in elsewhere.values():
            source = builds[0].source
            found.append(diagnostic(
                "warning", "stale_build",
                f"{entry.solver}: {_names(builds)} {_were(builds)} built from {_describe(source)}, but the plan "
                f"reads {_describe(entry.repository)}: the plan and the scan describe source these builds were "
                "not made from; rebuild from the supplied repository and record the build",
                source="environment", field=builds[0].name,
                detail={"solver": entry.solver, "builds": [b.name for b in builds],
                        "built_from": source.to_json(), "supplied": entry.repository.to_json()},
            ))
        if unknown:
            hint = (
                f"; after building, run `omnidriver build-record --repo {entry.repository.repository}`"
                if entry.recordable and entry.repository is not None and entry.repository.repository else ""
            )
            found.append(diagnostic(
                "info", "build_source_unknown",
                f"{entry.solver}: nothing states which source built {_names(unknown)}{hint}",
                source="environment", field=unknown[0].name,
            ))
    return tuple(found)


def _commit(identity: SourceIdentity) -> str | None:
    return (identity.git or {}).get("commit")


def _describe(identity: SourceIdentity) -> str:
    git = identity.git or {}
    label = git.get("commit") or "no git commit"
    if git.get("dirty"):
        label += ", with uncommitted changes"
    return f"{identity.repository} ({label}; {identity.digest})"


def _names(builds: list[SolverBuild]) -> str:
    return ", ".join(build.name for build in builds)


def _were(builds: list[SolverBuild]) -> str:
    return "was" if len(builds) == 1 else "were"
```

- [ ] **Step 5: Add `solverProvenance` to the run document model and schema**

In `run_model.py` `RunDocument`, after `validation`:

```python
    solverProvenance: list[dict[str, Any]] | None = None
```

In `to_json`, after the `plugin` pop:

```python
        if data.get("solverProvenance") is None:
            data.pop("solverProvenance", None)
```

In `from_json`, add `solverProvenance=data.get("solverProvenance"),` after `validation=...`.

In `schemas/run-document.json`, add to `properties`:

```json
"solverProvenance": {
  "type": "array",
  "description": "One item per solver that answered get_solver_builds: the supplied repository's identity and each build the run uses, with the source it was built from (core.runtime.solver_provenance.to_json).",
  "items": {"$ref": "#/$defs/solverEntry"}
}
```

and to `$defs`:

```json
"sourceIdentity": {
  "type": ["object", "null"],
  "required": ["repository", "digest", "git"],
  "properties": {
    "repository": {"type": ["string", "null"]},
    "digest": {"oneOf": [{"$ref": "#/$defs/sha256Digest"}, {"type": "null"}]},
    "git": {
      "type": ["object", "null"],
      "properties": {
        "commit": {"type": ["string", "null"]},
        "tag": {"type": ["string", "null"]},
        "dirty": {"type": ["boolean", "null"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
},
"solverBuild": {
  "type": "object",
  "required": ["name", "path", "digest", "known", "source", "matchesRepository"],
  "properties": {
    "name": {"type": "string", "minLength": 1},
    "path": {"type": ["string", "null"]},
    "digest": {"oneOf": [{"$ref": "#/$defs/sha256Digest"}, {"type": "null"}]},
    "known": {"enum": ["recorded", "self_reported", "live", "unknown"]},
    "source": {"$ref": "#/$defs/sourceIdentity"},
    "matchesRepository": {"type": ["boolean", "null"]}
  },
  "additionalProperties": false
},
"solverEntry": {
  "type": "object",
  "required": ["solver", "repository", "builds"],
  "properties": {
    "solver": {"type": "string", "minLength": 1},
    "repository": {"$ref": "#/$defs/sourceIdentity"},
    "builds": {"type": "array", "items": {"$ref": "#/$defs/solverBuild"}}
  },
  "additionalProperties": false
}
```

- [ ] **Step 6: Wire it into `_strict_plan_for_spec`**

In `strict_planning.py`, add the import `from .runtime import solver_provenance` with the other runtime imports. Immediately after the `env_diagnostics = driver_context.stack.call("get_environment_diagnostics", ...)` statement, add:

```python
    solvers = solver_provenance.solver_entries(
        Path(spec.case_root), workflow_dag=workflow_dag, driver_context=driver_context, env=os.environ,
    )
    env_diagnostics = tuple(env_diagnostics) + solver_provenance.provenance_diagnostics(solvers)
    if solvers:
        run_document.solverProvenance = solver_provenance.to_json(solvers)
```

- [ ] **Step 7: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_solver_provenance.py -q && /tmp/od-prov/bin/python -m pytest packages/omnidriver/tests -q`
Expected: all pass, 0 failed.

- [ ] **Step 8: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/runtime/provenance_inputs.py packages/omnidriver/src/omnidriver/core/runtime/solver_provenance.py \
  packages/omnidriver/src/omnidriver/core/runtime/run_model.py packages/omnidriver/src/omnidriver/schemas/run-document.json \
  packages/omnidriver/src/omnidriver/core/strict_planning.py packages/omnidriver/tests/core/test_solver_provenance.py
git commit -m "feat(core): the run document lists each solver's builds, and stale_build compares digests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `omnidriver build-record`

**Files:**
- Modify: `packages/omnidriver/src/omnidriver/core/refusal.py` (`CODES`)
- Modify: `packages/omnidriver/src/omnidriver/core/runtime/build_identity.py` (`build_record_report`)
- Modify: `packages/omnidriver/src/omnidriver/cli.py` (`choices`, `_validate_args`, `_dispatch`)
- Test: `packages/omnidriver/tests/core/test_build_record_command.py`

**Interfaces:**
- Consumes: `write_records`, `SolverEntry` (Tasks 1-2).
- Produces: `build_identity.build_record_report(driver_context, env) -> dict` with `status`, `action`, `repository`, `recorded`, `not_built`, `records`; refusal code `build_products_undeclared`.

- [ ] **Step 1: Write the failing tests**

```python
"""`omnidriver build-record`: record what a repository built, for a stack whose binaries cannot identify themselves."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from cli_refusal import refusal
from omnidriver.core import provider_stack
from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import RECORD_FILENAME, build_record_report, file_digest, recorded_build

SOURCE = SourceIdentity(repository="/src/a", digest="sha256:" + "a" * 64, git=None)


def _context(provider, root):
    return SimpleNamespace(
        stack=provider_stack.ProviderStack(provider_stack.order_providers((provider,))),
        repository=SimpleNamespace(root=root, plugin="toySolver"),
    )


def test_a_recordable_stack_records_what_exists_and_lists_what_was_not_built(tmp_path):
    binary = tmp_path / "bin" / "mySolver"
    binary.parent.mkdir()
    binary.write_bytes(b"bin")

    class _Wmake:
        plugin_id = "org.wmake"

        def get_solver_builds(self, env, *, repository, used_paths):
            assert used_paths is None
            return (SolverEntry(solver="toySolver", repository=SOURCE, recordable=True, builds=(
                SolverBuild(name="mySolver", path=binary, digest=file_digest(binary), known="unknown"),
                SolverBuild(name="libGone", path=None, digest=None, known="unknown"),
            )),)

    report = build_record_report(_context(_Wmake(), tmp_path), {})
    assert report["status"] == "ok" and report["action"] == "build-record"
    assert report["repository"] == SOURCE.to_json()
    assert [item["name"] for item in report["recorded"]] == ["mySolver"]
    assert [item["name"] for item in report["not_built"]] == ["libGone"]
    assert report["records"] == [str(tmp_path / "bin" / RECORD_FILENAME)]
    assert recorded_build("mySolver", binary).known == "recorded"


def test_a_stack_with_no_recordable_solver_refuses_by_name(tmp_path):
    class _SelfReporting:
        plugin_id = "org.self"

        def get_solver_builds(self, env, *, repository, used_paths):
            return (SolverEntry(solver="s", repository=None, builds=()),)

    report = build_record_report(_context(_SelfReporting(), tmp_path), {})
    assert (report["status"], report["code"]) == ("failed", "build_products_undeclared")


def test_the_command_needs_a_repository(capsys):
    payload = refusal(capsys, ["build-record", "--plugin", "plugins.toy:ToyStack"])
    assert payload["code"] == "usage" and "--repo" in payload["error"]
```

Check `cli_refusal.refusal`'s signature before running: `grep -n "def refusal" packages/omnidriver/tests/cli_refusal.py` — call it the way its other users do and adjust the last test's call to match.

- [ ] **Step 2: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_record_command.py -q`
Expected: `ImportError: cannot import name 'build_record_report'`.

- [ ] **Step 3: Add the refusal code**

In `refusal.py` `CODES`, after `"cxx_source_not_scanned"`:

```python
    "build_products_undeclared": "the stack lists no build of the repository that only a build record can identify",
```

- [ ] **Step 4: Add `build_record_report` to `build_identity.py`**

```python
def build_record_report(driver_context: Any, env: Mapping[str, str]) -> dict[str, Any]:
    """``build-record``: record every existing build of the stack's recordable solvers as built from
    the supplied repository; the JSON report, or a refusal payload."""
    from ..refusal import failure

    repository = driver_context.repository
    entries = [
        entry for entry in driver_context.stack.call("get_solver_builds", env, repository=repository, used_paths=None)
        if entry.recordable and entry.repository is not None
    ]
    if not entries:
        return failure(
            None, code="build_products_undeclared", action="build-record",
            error=f"nothing in {repository.root} is a build only a record can identify: its solver's builds "
                  "identify themselves, or the stack lists none",
        )
    recorded: list[dict[str, Any]] = []
    not_built: list[dict[str, Any]] = []
    records: set[Path] = set()
    for entry in entries:
        present = [build for build in entry.builds if build.digest is not None]
        records.update(write_records(present, entry.repository))
        recorded += [{"solver": entry.solver, "name": b.name, "path": str(b.path), "digest": b.digest} for b in present]
        not_built += [{"solver": entry.solver, "name": b.name} for b in entry.builds if b.digest is None]
    return {
        "action": "build-record", "status": "ok", "repository": entries[0].repository.to_json(),
        "recorded": recorded, "not_built": not_built, "records": sorted(str(path) for path in records),
    }
```

- [ ] **Step 5: Wire the CLI**

In `cli.py`:
- add `"build-record"` to the action `choices` list after `"scan"`;
- in `_validate_args`, after the `action == "scan"` check, add:

```python
    if args.action == "build-record" and (not args.repo or any((
        args.entry, args.case, args.run_document, args.cases_root, args.spec, args.output_dir,
        args.parallel is not None, args.inputs,
    ))):
        parser.error("action=build-record takes only --repo: it records what that repository built, "
                     "run in the solver's shell after building")
```

- add `"build-record"` to the set of actions that need no `--entry` (the set beginning `"sweep-plan", "sweep-run", "compare", "env", "scan", ...`);
- in `_dispatch`, after the `action == "env"` branch:

```python
    if args.action == "build-record":
        from .core.runtime.build_identity import build_record_report

        report = build_record_report(driver_context, os.environ)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "ok" else 1
```

- [ ] **Step 6: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver/tests/core/test_build_record_command.py packages/omnidriver/tests/core -q -k "refusal or cli or build_record"`
Expected: all pass. A test that lists every refusal code or every CLI action may need the new names; add them there, never remove one.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver/src/omnidriver/core/refusal.py packages/omnidriver/src/omnidriver/core/runtime/build_identity.py \
  packages/omnidriver/src/omnidriver/cli.py packages/omnidriver/tests/core/test_build_record_command.py
git commit -m "feat(cli): omnidriver build-record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The OpenFOAM layer answers for every wmake solver; the file-time check goes

**Files:**
- Create: `packages/omnidriver-openfoam/src/omnidriver/openfoam/build_products.py`
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment.py` (`OpenFOAMEnvironmentPlugin.get_solver_builds`)
- Modify: `packages/omnidriver-openfoam/src/omnidriver/openfoam/environment_preflight.py` (delete the file-time check)
- Modify: `packages/omnidriver-openfoam/tests/core/test_environment_preflight.py` (remove the six `_build_staleness_diagnostics` tests; their cases move to the new file)
- Test: `packages/omnidriver-openfoam/tests/core/test_build_products.py`

**Interfaces:**
- Consumes: `SolverEntry`, `SourceIdentity`, `recorded_build`, `write_records`, `tree_digest`, `git_identity` (core); `solver_provenance.to_json`, `provenance_diagnostics` (tests).
- Produces: `build_products.build_source_files(root) -> list[Path]`, `build_products.source_identity(root) -> SourceIdentity`, `build_products.products(root, env) -> list[tuple[str, Path | None]]`, `build_products.wmake_solver_builds(env, *, repository, used_paths) -> tuple[SolverEntry, ...]`.

- [ ] **Step 1: Write the failing tests**

```python
"""What a wmake repository builds, which files a build reads, and how its builds are judged."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.runtime.build_identity import write_records
from omnidriver.core.runtime.solver_provenance import provenance_diagnostics, to_json
from omnidriver.openfoam.build_products import (
    build_source_files, products, source_identity, wmake_solver_builds,
)


def _repository(root: Path) -> Path:
    (root / "applications" / "solvers" / "myFoam" / "Make").mkdir(parents=True)
    (root / "applications" / "solvers" / "myFoam" / "myFoam.C").write_text("int main() {}\n")
    (root / "applications" / "solvers" / "myFoam" / "Make" / "files").write_text(
        "myFoam.C\n\nEXE = $(FOAM_USER_APPBIN)/myFoam\n")
    (root / "applications" / "solvers" / "myFoam" / "Make" / "options").write_text("EXE_INC =\n")
    (root / "src" / "models" / "Make").mkdir(parents=True)
    (root / "src" / "models" / "model.H").write_text("// model\n")
    (root / "src" / "models" / "Make" / "files").write_text("model.C\n\nLIB = $(FOAM_USER_LIBBIN)/libmodels\n")
    (root / "src" / "models" / "lnInclude").mkdir()
    (root / "src" / "models" / "lnInclude" / "model.H").write_text("// link\n")
    (root / "tutorials" / "case").mkdir(parents=True)
    (root / "tutorials" / "case" / "Allrun").write_text("#!/bin/sh\n")
    return root


def _install(tmp_path: Path) -> dict[str, str]:
    appbin, libbin = tmp_path / "platform" / "bin", tmp_path / "platform" / "lib"
    appbin.mkdir(parents=True)
    libbin.mkdir(parents=True)
    (appbin / "myFoam").write_bytes(b"solver")
    (libbin / "libmodels.dylib").write_bytes(b"library")
    return {"FOAM_USER_APPBIN": str(appbin), "FOAM_USER_LIBBIN": str(libbin), "PATH": str(appbin)}


def _repo(root: Path):
    return SimpleNamespace(root=root, plugin="mySolver")


def test_the_build_reads_sources_and_make_files_but_not_tutorials_or_links(tmp_path):
    root = _repository(tmp_path / "repo")
    relative = sorted(p.relative_to(root).as_posix() for p in build_source_files(root))
    assert relative == [
        "applications/solvers/myFoam/Make/files", "applications/solvers/myFoam/Make/options",
        "applications/solvers/myFoam/myFoam.C", "src/models/Make/files", "src/models/model.H",
    ]


def test_a_tutorial_edit_keeps_the_digest_and_a_build_option_edit_changes_it(tmp_path):
    root = _repository(tmp_path / "repo")
    before = source_identity(root).digest
    (root / "tutorials" / "case" / "Allrun").write_text("#!/bin/sh\necho changed\n")
    assert source_identity(root).digest == before
    (root / "applications" / "solvers" / "myFoam" / "Make" / "options").write_text("EXE_INC = -O3\n")
    assert source_identity(root).digest != before


def test_products_come_from_make_files_and_land_in_the_user_platform(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    assert products(root, env) == [
        ("myFoam", Path(env["FOAM_USER_APPBIN"]) / "myFoam"),
        ("libmodels", Path(env["FOAM_USER_LIBBIN"]) / "libmodels.dylib"),
    ]
    (Path(env["FOAM_USER_APPBIN"]) / "myFoam").unlink()
    assert products(root, env)[0] == ("myFoam", None)


def test_a_recorded_build_from_this_repository_matches_and_says_nothing(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    write_records(entry.builds, entry.repository)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    assert {b.known for b in entry.builds} == {"recorded"}
    assert all(item["matchesRepository"] for item in to_json((entry,))[0]["builds"])
    assert provenance_diagnostics((entry,)) == ()


def test_a_build_recorded_from_another_tree_is_a_stale_build(tmp_path):
    built_from = _repository(tmp_path / "worktree")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(built_from), used_paths=None)
    write_records(entry.builds, entry.repository)
    planned = _repository(tmp_path / "archive")
    (planned / "src" / "models" / "model.H").write_text("// other source\n")
    (entry,) = wmake_solver_builds(env, repository=_repo(planned), used_paths=None)
    (warning,) = provenance_diagnostics((entry,))
    assert warning.code == "stale_build"
    assert str(built_from.resolve()) in warning.message and str(planned.resolve()) in warning.message


def test_an_unrecorded_or_rebuilt_product_is_unknown_with_the_command_to_record_it(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    (note,) = provenance_diagnostics((entry,))
    assert note.code == "build_source_unknown"
    assert f"omnidriver build-record --repo {root.resolve()}" in note.message
    write_records(entry.builds, entry.repository)
    (Path(env["FOAM_USER_APPBIN"]) / "myFoam").write_bytes(b"rebuilt, not recorded")
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    assert {b.name: b.known for b in entry.builds} == {"myFoam": "unknown", "libmodels": "recorded"}


def test_only_products_the_plan_runs_are_listed_even_through_a_symlink_on_path(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    link = tmp_path / "linkbin" / "myFoam"
    link.parent.mkdir()
    link.symlink_to(Path(env["FOAM_USER_APPBIN"]) / "myFoam")
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=frozenset({link.resolve()}))
    assert [b.name for b in entry.builds] == ["myFoam"]
    assert wmake_solver_builds(env, repository=_repo(root), used_paths=frozenset({tmp_path / "blockMesh"})) == ()


def test_no_repository_or_no_make_files_is_no_entry(tmp_path):
    env = _install(tmp_path)
    assert wmake_solver_builds(env, repository=None, used_paths=None) == ()
    (tmp_path / "cases").mkdir()
    assert wmake_solver_builds(env, repository=_repo(tmp_path / "cases"), used_paths=None) == ()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-openfoam/tests/core/test_build_products.py -q`
Expected: `ModuleNotFoundError: No module named 'omnidriver.openfoam.build_products'`.

- [ ] **Step 3: Create `openfoam/build_products.py`**

```python
"""What a wmake repository builds and which of its files a build reads: the OpenFOAM layer's
answer to ``get_solver_builds``, one for every OpenFOAM-based solver."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterator, Mapping

from omnidriver.core.plugin_interface import SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import git_identity, recorded_build, tree_digest

_EXCLUDED = frozenset({"tutorials", "lnInclude", "platforms", ".git"})
_SOURCE_SUFFIXES = frozenset({".C", ".H", ".cu", ".cuh"})
_MAKE_FILES = frozenset({"files", "options"})
_EXE_RULE = re.compile(r"^\s*EXE\s*=\s*\$\(FOAM_USER_APPBIN\)/(\S+)", re.MULTILINE)
_LIB_RULE = re.compile(r"^\s*LIB\s*=\s*\$\(FOAM_USER_LIBBIN\)/(\S+)", re.MULTILINE)
_LIBRARY_SUFFIXES = (".so", ".dylib")


def _walk(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in _EXCLUDED)
        for name in sorted(filenames):
            yield Path(dirpath, name)


def build_source_files(root: Path) -> list[Path]:
    """Every C++/CUDA source and ``Make/files``/``Make/options`` a build of ``root`` reads; tutorials,
    ``lnInclude`` links and platform products are not source."""
    return [
        path for path in _walk(Path(root))
        if path.suffix in _SOURCE_SUFFIXES or (path.parent.name == "Make" and path.name in _MAKE_FILES)
    ]


def source_identity(root: Path) -> SourceIdentity:
    """The repository at ``root``: its build-source digest and git identity."""
    root = Path(root).resolve()
    return SourceIdentity(repository=str(root), digest=tree_digest(root, build_source_files(root)), git=git_identity(root))


def products(root: Path, env: Mapping[str, str]) -> list[tuple[str, Path | None]]:
    """``(name, path)`` for every ``EXE``/``LIB`` a ``Make/files`` under ``root`` builds into the user
    platform folders; ``path`` is ``None`` when the product is not there."""
    appbin, libbin = env.get("FOAM_USER_APPBIN"), env.get("FOAM_USER_LIBBIN")
    found: dict[str, Path | None] = {}
    for make_files in (path for path in _walk(Path(root)) if path.name == "files" and path.parent.name == "Make"):
        text = make_files.read_text(errors="replace")
        for name in _EXE_RULE.findall(text):
            path = Path(appbin, name) if appbin else None
            found.setdefault(name, path if path is not None and path.is_file() else None)
        for lib in _LIB_RULE.findall(text):
            path = next((Path(libbin, lib + suffix) for suffix in _LIBRARY_SUFFIXES
                         if libbin and Path(libbin, lib + suffix).is_file()), None)
            found.setdefault(lib, path)
    return list(found.items())


def wmake_solver_builds(
    env: Mapping[str, str], *, repository: Any, used_paths: frozenset[Path] | None,
) -> tuple[SolverEntry, ...]:
    """The supplied repository's products as their build records state them; nothing without a
    repository, without products, or when the plan runs none of them."""
    if repository is None:
        return ()
    root = Path(repository.root)
    built = products(root, env)
    if not built:
        return ()
    selected = [
        (name, path) for name, path in built
        if used_paths is None or (path is not None and path.resolve() in used_paths)
    ]
    if not selected:
        return ()
    return (SolverEntry(
        solver=repository.plugin, repository=source_identity(root),
        builds=tuple(recorded_build(name, path) for name, path in selected), recordable=True,
    ),)
```

- [ ] **Step 4: Answer the member from the OpenFOAM environment provider**

In `environment.py`, inside `class OpenFOAMEnvironmentPlugin`, after `get_input_roots`:

```python
    def get_solver_builds(self, env, *, repository, used_paths):
        from .build_products import wmake_solver_builds

        return wmake_solver_builds(env, repository=repository, used_paths=used_paths)
```

- [ ] **Step 5: Delete the file-time check**

In `environment_preflight.py` delete `_SOURCE_SUFFIXES`, `_supplied_src_root`, `_LIB_RULE` (and its comment), `_sources`, `_stale_build`, `_build_staleness_diagnostics`, and the final `diagnostics.extend(_build_staleness_diagnostics(...))` call in `_environment_diagnostics`. Then remove imports nothing uses any more:

Run: `grep -n "datetime\|\bre\.\|\bos\." packages/omnidriver-openfoam/src/omnidriver/openfoam/environment_preflight.py`
Expected: no line using `datetime`, `re.` or `os.`; delete each of those imports that has no use left.

In `test_environment_preflight.py`, delete the six tests that import `_build_staleness_diagnostics` (`test_build_staleness_warns_when_user_binary_older_than_source`, `test_build_staleness_silent_when_binary_newer_than_source`, `test_build_staleness_ignores_binaries_outside_user_appbin`, `test_a_stale_build_names_the_binary_and_the_newest_source_file`, `test_a_library_a_make_files_builds_is_stale_against_its_own_sources_only`, `test_build_staleness_no_src_root_is_silent`). Their cases are in `test_build_products.py`: a match, another tree, a system binary not listed, a library from `Make/files`, and no repository.

Run: `grep -rn "_build_staleness_diagnostics\|_supplied_src_root" packages/`
Expected: no output.

- [ ] **Step 6: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-openfoam packages/omnidriver-cardiacfoam packages/omnidriver-cardiacsubstrate -q -m "not slow"`
Expected: 0 failed.

- [ ] **Step 7: Commit**

```bash
git add packages/omnidriver-openfoam
git commit -m "feat(openfoam): every wmake solver's builds by record, and stale_build by digest

The file-time comparison is gone: a git archive sets every file to its commit
time, so it passed a binary built from another tree.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: openCARP reports its own build

**Files:**
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/environment.py` (`buildinfo_identity`, `opencarp_solver_builds`)
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/catalog_generation.py` (`build_identity` reuses `buildinfo_identity`)
- Modify: `packages/omnidriver-opencarp/src/omnidriver/opencarp/plugin.py` (`OpenCARPPlugin.get_solver_builds`)
- Create: `packages/omnidriver-opencarp/tests/fixtures/buildinfo-v18.1.txt`
- Test: `packages/omnidriver-opencarp/tests/test_solver_builds.py`

**Interfaces:**
- Consumes: `SolverBuild`, `SolverEntry`, `SourceIdentity`, `file_digest` (core).
- Produces: `environment.buildinfo_identity(text) -> dict | None` (`{"tag", "commit"}`), `environment.opencarp_solver_builds(env, *, used_paths) -> tuple[SolverEntry, ...]`.

- [ ] **Step 1: Write the fixture**

The installed openCARP v18.1 prints these two lines among others (its repository line embeds a CI token and is never copied). `packages/omnidriver-opencarp/tests/fixtures/buildinfo-v18.1.txt`:

```
*** GIT tag:            v18.1
*** GIT hash:           6eaa147d18b69a6037d05a90b841e23301048a59
```

Check where the package's tests keep fixtures (`ls packages/omnidriver-opencarp/tests`) and put the file beside the others if that folder differs.

- [ ] **Step 2: Write the failing tests**

```python
"""openCARP's build identity comes from the binary itself (-buildinfo's tag and hash)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from omnidriver.opencarp import environment
from omnidriver.opencarp.environment import buildinfo_identity, opencarp_solver_builds

FIXTURE = Path(__file__).parent / "fixtures" / "buildinfo-v18.1.txt"


def test_buildinfo_gives_the_tag_and_the_hash():
    assert buildinfo_identity(FIXTURE.read_text()) == {
        "tag": "v18.1", "commit": "6eaa147d18b69a6037d05a90b841e23301048a59",
    }
    assert buildinfo_identity("dyld: Library not loaded\n") is None


def _solver(tmp_path, monkeypatch, stdout):
    binary = tmp_path / "bin" / "openCARP"
    binary.parent.mkdir()
    binary.write_bytes(b"opencarp")
    binary.chmod(0o755)
    monkeypatch.setattr(environment.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=stdout, stderr=""))
    return binary, {"PATH": str(binary.parent)}


def test_the_solver_is_self_reported_when_it_prints_its_build(tmp_path, monkeypatch):
    binary, env = _solver(tmp_path, monkeypatch, FIXTURE.read_text())
    (entry,) = opencarp_solver_builds(env, used_paths=frozenset({binary.resolve()}))
    (build,) = entry.builds
    assert (entry.solver, entry.repository, entry.recordable) == ("org.omnidriver.opencarp", None, False)
    assert (build.name, build.known) == ("openCARP", "self_reported")
    assert build.source.git == {"tag": "v18.1", "commit": "6eaa147d18b69a6037d05a90b841e23301048a59"}
    assert build.digest.startswith("sha256:")


def test_a_silent_binary_is_unknown_and_an_unused_one_is_not_listed(tmp_path, monkeypatch):
    binary, env = _solver(tmp_path, monkeypatch, "")
    (entry,) = opencarp_solver_builds(env, used_paths=None)
    assert entry.builds[0].known == "unknown"
    assert opencarp_solver_builds(env, used_paths=frozenset({tmp_path / "mesher"})) == ()
    assert opencarp_solver_builds({"PATH": ""}, used_paths=None) == ()
```

- [ ] **Step 3: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-opencarp/tests/test_solver_builds.py -q`
Expected: `ImportError: cannot import name 'buildinfo_identity'`.

- [ ] **Step 4: Implement**

In `environment.py`, add imports `from pathlib import Path` and `from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity`, `from omnidriver.core.runtime.build_identity import file_digest`, and after `_GIT_TAG`:

```python
_GIT_HASH = re.compile(r"GIT hash:\s*(\S+)")
_PLUGIN_ID = "org.omnidriver.opencarp"


def buildinfo_identity(buildinfo: str) -> dict[str, str | None] | None:
    """``-buildinfo``'s tag and hash, or ``None`` when it prints neither; no other line is read."""
    tag, commit = _GIT_TAG.search(buildinfo), _GIT_HASH.search(buildinfo)
    if tag is None and commit is None:
        return None
    return {"tag": tag.group(1) if tag else None, "commit": commit.group(1) if commit else None}


def opencarp_solver_builds(env: Mapping[str, str], *, used_paths: frozenset | None) -> tuple[SolverEntry, ...]:
    """openCARP as its own ``-buildinfo`` reports it, when a plan runs it."""
    solver = shutil.which("openCARP", path=env.get("PATH", ""))
    if solver is None or (used_paths is not None and Path(solver).resolve() not in used_paths):
        return ()
    try:
        identity = buildinfo_identity(subprocess.run(
            [solver, "-buildinfo"], capture_output=True, text=True, env=dict(env), timeout=60,
        ).stdout)
    except (OSError, subprocess.TimeoutExpired):
        identity = None
    build = SolverBuild(
        name="openCARP", path=Path(solver), digest=file_digest(Path(solver)),
        known="self_reported" if identity else "unknown",
        source=SourceIdentity(git=identity) if identity else None,
    )
    return (SolverEntry(solver=_PLUGIN_ID, repository=None, builds=(build,)),)
```

In `catalog_generation.py`, replace the body of `build_identity` with:

```python
    from .environment import buildinfo_identity

    identity = buildinfo_identity(_run(binary, ["-buildinfo"], env))
    if identity is None or None in identity.values():
        raise CatalogError("-buildinfo printed no tag/hash; is DYLD_LIBRARY_PATH set? (A4-A6)")
    return {"tag": identity["tag"], "hash": identity["commit"]}
```

If `environment.py` already imports from `catalog_generation` at module level, keep the local import above to avoid a cycle.

In `plugin.py`, inside `class OpenCARPPlugin`:

```python
    def get_solver_builds(self, env, *, repository, used_paths):
        from .environment import opencarp_solver_builds

        return opencarp_solver_builds(env, used_paths=used_paths)
```

- [ ] **Step 5: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-opencarp -q -m "not slow"`
Expected: 0 failed.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-opencarp
git commit -m "feat(opencarp): openCARP's build identity from its own -buildinfo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: TorchCor's package, read live

**Files:**
- Create: `packages/omnidriver-torchcor/src/omnidriver/torchcor/provenance.py`
- Modify: `packages/omnidriver-torchcor/src/omnidriver/torchcor/plugin.py` (`TorchCorPlugin.get_solver_builds`)
- Test: `packages/omnidriver-torchcor/tests/test_solver_builds.py`

**Interfaces:**
- Consumes: `SolverBuild`, `SolverEntry`, `SourceIdentity`, `git_identity`, `tree_digest` (core).
- Produces: `provenance.torchcor_solver_builds(env, *, repository) -> tuple[SolverEntry, ...]`, `provenance._package_file(python, env) -> Path | None` (monkeypatched in tests).

- [ ] **Step 1: Write the failing tests**

```python
"""TorchCor runs the repository's own package (an editable install), read when the plan is made."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.torchcor import provenance
from omnidriver.torchcor.provenance import torchcor_solver_builds


def _repository(tmp_path):
    source = tmp_path / "cases" / "torchcor"
    (source / "torchcor").mkdir(parents=True)
    (source / "torchcor" / "__init__.py").write_text("")
    (source / "torchcor" / "solver.py").write_text("x = 1\n")
    python = tmp_path / "venv" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n")
    python.chmod(0o755)
    repository = SimpleNamespace(root=tmp_path / "cases", plugin="torchcor", source=source)
    return repository, {"PATH": str(python.parent)}


def test_the_editable_package_inside_the_repository_is_live_and_matches(tmp_path, monkeypatch):
    repository, env = _repository(tmp_path)
    monkeypatch.setattr(provenance, "_package_file", lambda python, env: repository.source / "torchcor" / "__init__.py")
    (entry,) = torchcor_solver_builds(env, repository=repository)
    (build,) = entry.builds
    assert (entry.solver, build.name, build.known) == ("torchcor", "torchcor", "live")
    assert build.source == entry.repository and build.digest == entry.repository.digest


def test_a_package_installed_from_elsewhere_is_unknown(tmp_path, monkeypatch):
    repository, env = _repository(tmp_path)
    monkeypatch.setattr(provenance, "_package_file", lambda python, env: tmp_path / "site" / "torchcor" / "__init__.py")
    (entry,) = torchcor_solver_builds(env, repository=repository)
    assert (entry.builds[0].known, entry.builds[0].source) == ("unknown", None)


def test_no_repository_is_no_entry():
    assert torchcor_solver_builds({"PATH": ""}, repository=None) == ()
```

- [ ] **Step 2: Run them to see them fail**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-torchcor/tests/test_solver_builds.py -q`
Expected: `ImportError: cannot import name 'provenance'`.

- [ ] **Step 3: Create `torchcor/provenance.py`**

```python
"""Which TorchCor a run uses: the repository's own package, installed editable, read when the plan is made."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import git_identity, tree_digest


def torchcor_solver_builds(env: Mapping[str, str], *, repository: Any) -> tuple[SolverEntry, ...]:
    """``live`` when the stack's ``python3`` imports ``torchcor`` from the repository's ``source``,
    else ``unknown``; nothing without a repository."""
    if repository is None:
        return ()
    source = Path(repository.source).resolve()
    identity = SourceIdentity(repository=str(source), digest=tree_digest(source, sorted(source.rglob("*.py"))),
                              git=git_identity(source))
    python = shutil.which("python3", path=env.get("PATH", ""))
    location = _package_file(python, env) if python else None
    if location is not None and location.resolve().is_relative_to(source):
        build = SolverBuild(name="torchcor", path=location.parent, digest=identity.digest, known="live", source=identity)
    else:
        build = SolverBuild(name="torchcor", path=location.parent if location else None, digest=None, known="unknown")
    return (SolverEntry(solver=repository.plugin, repository=identity, builds=(build,)),)


def _package_file(python: str, env: Mapping[str, str]) -> Path | None:
    try:
        proc = subprocess.run((python, "-c", "import torchcor; print(torchcor.__file__)"),
                              capture_output=True, text=True, env=dict(env), timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.strip()
    return Path(out) if proc.returncode == 0 and out else None
```

- [ ] **Step 4: Answer the member**

In `plugin.py`, inside `class TorchCorPlugin`:

```python
    def get_solver_builds(self, env, *, repository, used_paths):
        from .provenance import torchcor_solver_builds

        return torchcor_solver_builds(env, repository=repository)
```

- [ ] **Step 5: Run the tests**

Run: `/tmp/od-prov/bin/python -m pytest packages/omnidriver-torchcor -q -m "not slow"`
Expected: 0 failed.

- [ ] **Step 6: Commit**

```bash
git add packages/omnidriver-torchcor
git commit -m "feat(torchcor): TorchCor's editable package as its build identity

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation and every verification shape

**Files:**
- Modify: `AGENT_GUIDE.md` (the paragraph beginning "Preflight links the binary to this source")
- Modify: `CLAUDE.md` (invariants table)
- Modify: `docs/superpowers/ROADMAP.md` (§5 item 2, "Binary versus source")

- [ ] **Step 1: Rewrite the `AGENT_GUIDE.md` paragraph**

Replace the paragraph beginning "Preflight links the binary to this source" with:

```markdown
Every plan lists, in its run document's `solverProvenance`, each solver it uses
and each build of it the run runs: path, digest, and the source it was built
from. How that source is known is the solver's: a wmake build (cardiacFOAM,
cardiacSubstrateFOAM) through the build record `omnidriver build-record --repo <src>`
writes beside the products after `./Allwmake` (`recorded`); openCARP from its
own `-buildinfo` tag and hash (`self_reported`); TorchCor from the editable
package the stack's `python3` imports (`live`). A build recorded from other
source than the supplied repository gets a `stale_build` warning naming both
repositories, commits and digests; a build nothing identifies gets a
`build_source_unknown` note. Neither blocks a plan.
```

- [ ] **Step 2: Add the `CLAUDE.md` invariant row**

After the row beginning "| a solver's shell is declared in its manifest", add:

```markdown
| a run document lists each solver's builds with the source each was built from, and a plan compares that source with the supplied repository by digest (never by file times) | `test_solver_provenance.py`, `test_build_record.py`, `test_build_identity.py` (core); `test_build_products.py` (openfoam); `test_solver_builds.py` (opencarp, torchcor) |
```

- [ ] **Step 3: Update `ROADMAP.md`**

In §5 item 2, delete the "*Binary versus source.*" bullet. Add to §5 item 9 ("Later"):

```markdown
   - cardiacFOAM's backend inspection (`cardiacFoam.build.json`: full or
     lightweight, the linked libraries) still refreshes itself by file time;
     whether it moves into the build record is open.
```

- [ ] **Step 4: Run every verification shape**

```bash
/tmp/od-prov/bin/python -m pytest packages/ -q -m "not slow" -rs
rm -rf /tmp/odcore-prov && uv venv -q --python 3.11 /tmp/odcore-prov && VIRTUAL_ENV=/tmp/odcore-prov uv pip install -q -e "packages/omnidriver[post]" pytest
/tmp/odcore-prov/bin/python -m pytest packages/omnidriver/tests -q
for s in check-import-boundaries check-case-writes check-core-shape check-benchmark-references; do /tmp/od-prov/bin/python scripts/$s.py; echo "$s rc=$?"; done
rm -rf /tmp/wheeltest /tmp/wheelenv
uvx --from build pyproject-build -q --outdir /tmp/wheeltest packages/omnidriver
uv venv -q --python 3.11 /tmp/wheelenv && VIRTUAL_ENV=/tmp/wheelenv uv pip install -q "$(ls /tmp/wheeltest/omnidriver-*.whl)[post]" pytest
/tmp/wheelenv/bin/python scripts/check-wheel-artifact.py
/tmp/wheelenv/bin/python -m pytest packages/omnidriver/tests -q
```
Expected: 0 failed in every pytest shape; the skips are only the OpenFOAM-bashrc probes (all packages) and the wheel's repository-checkout skips; every gate `rc=0`; the artifact check prints "Wheel artifact OK".

- [ ] **Step 5: Commit**

```bash
git add AGENT_GUIDE.md CLAUDE.md docs/superpowers/ROADMAP.md
git commit -m "docs: run provenance per solver, and stale_build by digest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Live check (only with the owner's approval: it writes `omnidriver-build.json` into the owner's OpenFOAM platform folders)**

From the OpenFOAM shell (`omnidriver env --plugin cardiacfoam` prints it):

```bash
/tmp/od-prov/bin/omnidriver build-record --repo ~/noFrontend_pr
```
Then plan a `git archive` of native main (with `omnidriver.toml` added) as in the 2026-10-16 probe:
`omnidriver plan --strict --repo <archive> --entry singleCell --scratch-dir <scratch>`.
Expected: `stale_build` naming `~/noFrontend_pr` at `04e6bd84` against the archive, and a `solverProvenance` list with `cardiacFoam` `known: recorded`, `matchesRepository: false`.
