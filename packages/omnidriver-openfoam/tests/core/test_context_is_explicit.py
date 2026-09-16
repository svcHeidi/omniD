"""OpenFOAM adapter internals never resolve a default solver context."""

from __future__ import annotations

import ast
from pathlib import Path

import omnidriver.openfoam


def test_openfoam_never_resolves_an_implicit_driver_context() -> None:
    source_root = Path(omnidriver.openfoam.__file__).resolve().parent
    offenders: dict[str, list[int]] = {}
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name == "resolve_public_driver_context":
                hits.append(node.lineno)
        if hits:
            offenders[str(path.relative_to(source_root))] = hits

    assert offenders == {}, (
        "OpenFOAM adapter modules resolving a default DriverContext:\n"
        + "\n".join(f"  {path}: lines {lines}" for path, lines in offenders.items())
        + "\nThread the selected DriverContext into the adapter instead."
    )
