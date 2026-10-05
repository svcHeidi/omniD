"""Where a native case is staged so the repository-relative paths its scripts use still resolve."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..repository import Repository


def staged_case_path(native_case: Path, repository: Repository | None, *, staging_root: Path, flat: Path) -> Path:
    """The path to stage ``native_case`` at: its repository-relative depth under
    ``staging_root`` when it lies inside ``repository`` below the repository
    root, so an ``Allrun`` reaching ``$case/../../scripts`` finds the repository's
    layout; otherwise ``flat``."""
    if repository is None:
        return flat
    try:
        relative = Path(native_case).resolve().relative_to(repository.root)
    except ValueError:
        return flat
    return flat if relative == Path(".") else staging_root / relative


def copy_repository_scripts(repository: Repository | None, native_case: Path, *, staging_root: Path) -> None:
    """Make the repository's declared ``scripts`` folder available at its
    repository-relative path under ``staging_root`` as a copy (without
    ``__pycache__``), so no step can write into the native tree. Nothing is copied
    when the case holds the scripts folder, or sits inside it."""
    if repository is None:
        return
    native_case = Path(native_case).resolve()
    if not native_case.is_relative_to(repository.root) or native_case == repository.root:
        return
    if native_case.is_relative_to(repository.scripts) or repository.scripts.is_relative_to(native_case):
        return
    copy = staging_root / repository.scripts.relative_to(repository.root)
    shutil.rmtree(copy, ignore_errors=True)
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repository.scripts, copy, symlinks=True, ignore=shutil.ignore_patterns("__pycache__"))
