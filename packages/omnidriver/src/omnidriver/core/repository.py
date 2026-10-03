"""A solver repository's ``omnidriver.toml``: which plugin drives it and where its tutorials, C++ source and scripts are.

Read only from a place the caller supplies (``--repo``, or the repository of a supplied cases root), never by walking up from the working directory."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

REPOSITORY_FILE = "omnidriver.toml"
_KEYS = {"plugin", "tutorials", "source", "scripts"}


class RepositoryError(ValueError):
    """An ``omnidriver.toml`` that is unreadable, incomplete or unclear."""


@dataclass(frozen=True)
class Repository:
    """A solver repository: ``tutorials``, ``source`` and ``scripts`` are
    absolute, resolved against ``root``."""

    root: Path
    plugin: str
    tutorials: Path
    source: Path
    scripts: Path


def read_repository(root: Path) -> Repository:
    """Read ``<root>/omnidriver.toml``. Every key is required and an unknown
    one is refused; each path must be relative and stay inside ``root``."""
    path = Path(root).resolve() / REPOSITORY_FILE
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RepositoryError(f"cannot read {path}: {exc}") from exc
    if set(data) != _KEYS:
        raise RepositoryError(
            f"{path} must set exactly {sorted(_KEYS)}; "
            f"missing {sorted(_KEYS - set(data))}, unknown {sorted(set(data) - _KEYS)}"
        )
    for key, value in data.items():
        if not isinstance(value, str) or not value:
            raise RepositoryError(f"{path}: {key} must be a non-empty string")
    paths = {}
    for key in ("tutorials", "source", "scripts"):
        resolved = (path.parent / data[key]).resolve()
        if Path(data[key]).is_absolute() or not resolved.is_relative_to(path.parent):
            raise RepositoryError(f"{path}: {key} = {data[key]!r} must be a path inside the repository")
        paths[key] = resolved
    return Repository(root=path.parent, plugin=data["plugin"], **paths)


def repository_of_cases_root(cases_root: Path) -> Repository | None:
    """The repository a supplied cases root belongs to: the cases root itself
    or its parent, whichever holds an ``omnidriver.toml`` whose ``tutorials``
    is that cases root. ``None`` when neither does."""
    cases_root = Path(cases_root).expanduser().resolve()
    for candidate in (cases_root, cases_root.parent):
        if (candidate / REPOSITORY_FILE).is_file():
            repository = read_repository(candidate)
            if repository.tutorials == cases_root:
                return repository
    return None
