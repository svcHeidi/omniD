"""Which source built what a run uses: content digests, a tree's digest, git identity, and the build record a stack whose binaries cannot identify themselves keeps beside them."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from ..plugin_interface import SolverBuild, SourceIdentity
from .attempt_lease import record_guard
from .provenance import component_for_path

#: The record a stack whose binaries cannot identify themselves keeps beside them.
RECORD_FILENAME = "omnidriver-build.json"
RECORD_VERSION = 1


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
    ``directory/.git``. No parent directory is searched. ``dirty`` is true when tracked files differ
    from ``HEAD``; untracked files are ignored."""
    directory = Path(directory)
    if not (directory / ".git").exists():
        return None
    commit = _git(directory, "rev-parse", "HEAD")
    if not commit:
        return None
    status = _git(directory, "status", "--porcelain", "--untracked-files=no")
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _git(directory: Path, *args: str) -> str | None:
    # An unusable .git makes git discover the enclosing repository; the ceiling stops that, and an
    # inherited GIT_DIR or GIT_WORK_TREE would bypass the directory altogether.
    env = {key: value for key, value in os.environ.items() if key not in ("GIT_DIR", "GIT_WORK_TREE")}
    env["GIT_CEILING_DIRECTORIES"] = str(directory.resolve().parent)
    try:
        proc = subprocess.run(("git", "-C", str(directory), *args), env=env,
                              capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


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
