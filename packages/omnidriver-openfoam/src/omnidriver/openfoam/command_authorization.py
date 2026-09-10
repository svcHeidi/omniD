"""OpenFOAM runtime command declarations.

These commands and the ``FOAM_*`` executable locations are OpenFOAM runtime
conventions.  Core asks an active environment whether it authorizes a command;
it never infers that answer from an OpenFOAM-specific environment variable.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


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


def is_installed_openfoam_application(command: str) -> bool:
    """Whether ``command`` resolves under the sourced OpenFOAM app roots."""

    roots = tuple(
        Path(value).resolve()
        for name in ("FOAM_APPBIN", "FOAM_USER_APPBIN")
        if (value := os.environ.get(name))
    )
    if not roots:
        return False
    resolved = shutil.which(command)
    if resolved is None:
        return False
    resolved_path = Path(resolved).resolve()
    return any(resolved_path.is_relative_to(root) for root in roots)
