"""Where a cardiacFoam case keeps each region's documents, as the case says.

``constant/physicsProperties``'s ``type`` selects a row of ``physics_layout.json``: its region roles and, for a region-split type, which entry of which document names each role's region."""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from pathlib import Path

from foamlib import FoamFile

from omnidriver.core.tutorial_records import TutorialRecordError


class PhysicsLayoutError(TutorialRecordError):
    """The case names a physics type the layout table does not know, asks
    for a region role that type does not have, or names a coupling document
    that is missing or does not resolve that role.

    A ``TutorialRecordError``, so the CLI refuses a plan by name.
    """


#: The layout for a case with no ``constant/physicsProperties``: single-region,
#: role ``electro``. cardiacFoam's ``physicsModel::New`` reads that file as
#: required, so such a case runs a utility that reads ``electroProperties``
#: directly (``ionicHeterogeneityProbe``). Not a row in ``physics_layout.json``
#: -- there is no ``type`` to key it on.
_IMPLICIT_LAYOUT: dict = {"roles": ["electro"]}


@cache
def _table() -> dict:
    raw = json.loads(files(__package__).joinpath("physics_layout.json").read_text())
    return {key: value for key, value in raw.items() if not key.startswith("_")}


def _physics_properties_path(case_root: Path) -> Path:
    return Path(case_root) / "constant" / "physicsProperties"


def physics_type(case_root: Path) -> str:
    """``constant/physicsProperties``'s ``type``.

    Raises ``PhysicsLayoutError`` (naming the case and the document) when
    the file exists but declares no ``type`` key. Raises
    ``FileNotFoundError`` when the file itself is absent -- ``_layout``
    checks existence first, rather than catching this, because that case is
    handled separately (``_IMPLICIT_LAYOUT``), not as a refusal.
    """
    path = _physics_properties_path(case_root)
    try:
        return str(FoamFile(path)["type"])
    except KeyError as exc:
        raise PhysicsLayoutError(f"{path} declares no 'type' key") from exc


def _type_label(case_root: Path) -> str:
    """A physics type for error messages, including the implicit case."""
    if not _physics_properties_path(case_root).exists():
        return "<no constant/physicsProperties>"
    return physics_type(case_root)


def _roles(layout: dict) -> frozenset[str]:
    if "regions" in layout:
        return frozenset(layout["regions"])
    return frozenset(layout.get("roles", ()))


def _layout(case_root: Path) -> dict:
    if not _physics_properties_path(case_root).exists():
        return _IMPLICIT_LAYOUT
    kind = physics_type(case_root)
    try:
        return _table()[kind]
    except KeyError:
        raise PhysicsLayoutError(
            f"physics type {kind!r} ({_physics_properties_path(case_root)}) is "
            f"not in physics_layout.json; add its row (known: {sorted(_table())})"
        ) from None


def region_of(case_root: Path, role: str) -> str | None:
    """The region the case names for ``role``; ``None`` for a single-region
    type.

    Refuses by name for an unknown role, matching every other refusal in this
    module -- an unknown role is a table/case mismatch, not a legitimate "no
    such region" answer.
    """
    layout = _layout(case_root)
    if role not in _roles(layout):
        raise PhysicsLayoutError(
            f"case {case_root} (physics type {_type_label(case_root)!r}) has "
            f"no region role {role!r} (known: {sorted(_roles(layout))})"
        )
    if "regions" not in layout:
        return None
    entry = layout["regions"][role]
    document_path = Path(case_root) / layout["names_in"]
    try:
        document = FoamFile(document_path)
        model = str(document[layout["model_key"]])
        return str(document[f"{model}Coeffs"][entry])
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise PhysicsLayoutError(
            f"case {case_root} names region role {role!r} via {document_path}, "
            f"but reading it failed: {exc!r}"
        ) from exc


def region_document(case_root: Path, role: str, name: str) -> Path | None:
    """``constant/<region>/<name>`` for a region-split type, or
    ``constant/<name>`` for a single-region one; ``None`` if the resolved
    path does not exist. Raises ``PhysicsLayoutError`` (via ``region_of``)
    for an unknown physics type or an unknown region role."""
    region = region_of(case_root, role)
    base = Path(case_root) / "constant"
    path = base / region / name if region else base / name
    return path if path.exists() else None
