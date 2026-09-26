"""Where a cardiacFoam case keeps each region's documents, as the case says.

``constant/physicsProperties`` names the physics ``type``. ``physics_layout.json``
says, per type, which region roles exist and which entry names each role's
region. A single-region type keeps its documents under ``constant/``; a
region-split one under ``constant/<region>/``. Added 2026-09-26 (spec
2026-09-26-core-generality-design.md A7, owner amendment): the table replaces
a one-off lookup, so electromechanics and later FSI are one row each.
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from pathlib import Path

from foamlib import FoamFile


class PhysicsLayoutError(ValueError):
    """The case names a physics type the layout table does not know."""


@cache
def _table() -> dict:
    raw = json.loads(files(__package__).joinpath("physics_layout.json").read_text())
    return {key: value for key, value in raw.items() if not key.startswith("_")}


def physics_type(case_root: Path) -> str:
    return str(FoamFile(Path(case_root) / "constant" / "physicsProperties")["type"])


def _layout(case_root: Path) -> dict:
    kind = physics_type(case_root)
    try:
        return _table()[kind]
    except KeyError:
        raise PhysicsLayoutError(
            f"physics type {kind!r} is not in physics_layout.json; add its row "
            f"(known: {sorted(_table())})"
        ) from None


def region_of(case_root: Path, role: str) -> str | None:
    """The region the case names for ``role``; ``None`` for a single-region type."""
    layout = _layout(case_root)
    if not layout.get("regions"):
        return None
    entry = layout["regions"].get(role)
    if entry is None:
        raise PhysicsLayoutError(
            f"physics type {physics_type(case_root)!r} has no region role {role!r}"
        )
    document = FoamFile(Path(case_root) / layout["names_in"])
    model = str(document[layout["model_key"]])
    return str(document[f"{model}Coeffs"][entry])


def region_document(case_root: Path, role: str, name: str) -> Path | None:
    """``constant/<region>/<name>`` or ``constant/<name>``; ``None`` if absent."""
    region = region_of(case_root, role)
    base = Path(case_root) / "constant"
    path = base / region / name if region else base / name
    return path if path.exists() else None
