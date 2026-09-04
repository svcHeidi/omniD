"""Where this repository's committed cardiac tutorial content lives.

Reproduces the semantics core's ``tutorials_root_default()`` had before it was
deleted on 2026-09-04: the repository root plus ``tutorials/`` when that
exists, else the root itself. Core must not invent a location for a caller's
cases (future/ENVIRONMENT_CONTRACT.md §12), but these regression tests read
*this* repository's own committed content and legitimately need a checkout --
every caller is already gated by ``skip_without_monorepo``.

Lives inside this package rather than at the tests root, and deliberately not
in ``conftest.py``. ``from conftest import ...`` resolves to *core's* conftest
when the whole repository is collected (both packages' tests directories are
reachable, and core's wins) -- the existing ``from conftest import
monorepo_root`` here only works because core's conftest happens to define the
same name. A plain module at the tests root is not importable in a full-repo
run at all; this package is, since its siblings already import
``regression_equivalence.registry``.
"""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.specs.paths import repo_root_default


def tutorials_root() -> Path:
    root = repo_root_default()
    candidate = root / "tutorials"
    return candidate if candidate.exists() else root
