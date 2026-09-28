"""This repository's committed cardiac tutorial content: ``tutorials/`` under the repo root, else the root.

A uniquely named module in this package, not conftest: ``from conftest import`` resolves to core's conftest in a full-repo run."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.specs.paths import repo_root_default


def tutorials_root() -> Path:
    root = repo_root_default()
    candidate = root / "tutorials"
    return candidate if candidate.exists() else root
