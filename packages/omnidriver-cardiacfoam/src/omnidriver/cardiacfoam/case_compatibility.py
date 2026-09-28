"""Legacy cardiacFoam case-folder detection: a case without ``Allrun`` is
considered runnable when ``electroProperties*`` and the standard OpenFOAM
system dictionaries are present. Applies only while core cannot establish
runnability from an executable ``Allrun`` first.
"""

from __future__ import annotations

from pathlib import Path


_REQUIRED_FILES = (
    "constant/physicsProperties",
    "system/controlDict",
    "system/fvSchemes",
    "system/fvSolution",
)


def has_case_marker(case_root: Path) -> bool:
    constant_root = case_root / "constant"
    if not constant_root.is_dir():
        return False
    return any(
        candidate.is_file() and candidate.name.startswith("electroProperties")
        for candidate in constant_root.rglob("electroProperties*")
    )


def is_runnable_without_workflow(case_root: Path) -> bool:
    return has_case_marker(case_root) and all(
        (case_root / relpath).exists() for relpath in _REQUIRED_FILES
    )
