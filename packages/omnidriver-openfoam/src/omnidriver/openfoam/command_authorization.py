"""OpenFOAM runtime command declarations.

Core asks the active environment whether a command is authorized; it never infers that from an OpenFOAM variable.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping


_OPENFOAM_RUNTIME_COMMANDS = frozenset(
    {
        "blockMesh",
        "checkMesh",
        "decomposePar",
        "gmsh",
        "gmshToFoam",
        "postProcess",
        "reconstructPar",
        "setExprFields",
        "topoSet",
        "vtkUnstructuredToFoam",
    }
)


def openfoam_runtime_commands() -> frozenset[str]:
    """Commands provided by an ordinary OpenFOAM runtime."""

    return _OPENFOAM_RUNTIME_COMMANDS


def is_installed_openfoam_application(command: str, env: Mapping[str, str]) -> bool:
    """Whether ``command`` resolves, on ``env``'s ``PATH``, under ``env``'s sourced OpenFOAM app roots."""

    roots = tuple(
        Path(value).resolve()
        for name in ("FOAM_APPBIN", "FOAM_USER_APPBIN")
        if (value := env.get(name))
    )
    if not roots:
        return False
    resolved = shutil.which(command, path=env.get("PATH"))
    if resolved is None:
        return False
    resolved_path = Path(resolved).resolve()
    return any(resolved_path.is_relative_to(root) for root in roots)
