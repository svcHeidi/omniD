"""Shared fixtures for Phase 3 Task 6's per-tutorial byte-parity tests.

Not named ``conftest`` -- CLAUDE.md's own documented trap: both packages'
``tests`` directories are reachable when the whole repo is collected, and
core's ``conftest`` wins, so a package-specific helper needs a uniquely
named, directly-imported module instead (the same convention
``regression_equivalence/tutorials_tree.py`` already uses in the cardiac
tree).

Every fixture body here is deliberately minimal and self-contained (no
monorepo checkout required) -- these tests characterize byte output, which
only needs a plausible document to patch, not a real tutorial's full case
tree.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver monodomainSolver;",
        "",
        "monodomainSolverCoeffs",
        "{",
        "    ionicModel Stewart;",
        "    tissue myocyte;",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "    solutionAlgorithm explicit;",
        "}",
        "",
        "eikonalSolverCoeffs",
        "{",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "}",
        "",
    ]
)

PHYSICS_TEXT = "type electroModel;\n"

CONTROL_DICT_TEXT = "\n".join(
    [
        "FoamFile",
        "{",
        "    object controlDict;",
        "}",
        "",
        "deltaT          1e-06;",
        "endTime         1;",
        "",
    ]
)

BLOCK_MESH_DICT_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 10 10) simpleGrading (1 1 1)\n"
    ");\n"
)

# manufactured_bath_bidomain uses a 3-block mesh (expected_blocks=3).
BLOCK_MESH_DICT_TEXT_3_BLOCKS = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 5 4 8 9 13 12) (10 10 10) simpleGrading (1 1 1)\n"
    "    hex (1 2 6 5 9 10 14 13) (10 10 10) simpleGrading (1 1 1)\n"
    "    hex (2 3 7 6 10 11 15 14) (10 10 10) simpleGrading (1 1 1)\n"
    ");\n"
)


def write_electro_properties(root: Path, relpath: str = "constant/electroProperties") -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ELECTRO_TEXT)
    return path


def write_physics_properties(root: Path, relpath: str = "constant/physicsProperties") -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PHYSICS_TEXT)
    return path


def write_control_dict(root: Path, relpath: str = "system/controlDict") -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CONTROL_DICT_TEXT)
    return path


def write_block_mesh_dict(
    root: Path, relpath: str = "system/blockMeshDict", *, three_blocks: bool = False,
) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(BLOCK_MESH_DICT_TEXT_3_BLOCKS if three_blocks else BLOCK_MESH_DICT_TEXT)
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digests(root: Path, *relpaths: str) -> dict[str, str]:
    return {relpath: digest(root / relpath) for relpath in relpaths}
