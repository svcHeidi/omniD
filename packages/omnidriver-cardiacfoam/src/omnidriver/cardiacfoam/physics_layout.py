"""Where a cardiacFoam case keeps each region's documents, as the case says.

``constant/physicsProperties``'s ``type`` selects a row of
``physics_layout.json``: which region roles that type has, and, for a
region-split type, which entry of which document names each role's region.
A single-region row names its roles directly (``{"roles": ["electro"]}``):
its documents sit under ``constant/``. A region-split row keeps
``names_in``/``model_key``/``regions`` instead of ``roles`` -- its roles are
``regions``'s own keys, and its documents sit under ``constant/<region>/``.
The table never copies a region *name*; the case owns that. Added
2026-09-26 (spec 2026-09-26-core-generality-design.md A7, owner amendment):
the table replaces a one-off lookup, so electromechanics and later FSI are
one row each.

**A case without ``constant/physicsProperties`` is single-region, role
``electro`` only** (R1 fix, finding I1 -- settled by source, not
preference). cardiacFoam's ``physicsModel::New``
(``modules/physicsModel/src/solids4FoamModels/physicsModel/physicsModel.C``)
opens ``physicsProperties`` with ``IOobject::MUST_READ``, so the solver
itself cannot run a case that lacks one. A case without it runs a different
application: ``ionicHeterogeneity``'s ``controlDict`` names ``application
ionicHeterogeneityProbe;``, a utility that reads ``constant
/electroProperties`` directly, with no region split. That is ``_IMPLICIT_LAYOUT``
below -- not a row in the JSON table, since there is no ``type`` to key one
on.

**Refusals are named, never swallowed** (R1 fix, finding I1).
``PhysicsLayoutError`` subclasses ``tutorial_records.TutorialRecordError``,
so an unknown physics type, an unknown region role, or a missing/malformed
coupling document reaches the CLI's existing ``plan --strict`` refusal
handling (``cli._context_from_entry``'s ``except TutorialRecordError``,
around every ``strict_plan`` call) exactly the way any other named refusal
does, instead of becoming a traceback. Only the *detectors'* own parse of
``electroProperties`` (``detection.detect_myocardium_solver_name``, which
raises a plain ``KeyError``) is left for ``planning_policy`` to swallow, as
it did before A7.

For FSI later: cardiacFoam's ``physicsModel::New`` also accepts the aliases
``solid``->``solidModel``, ``fluid``->``fluidModel``,
``fluidSolidInteraction``->``fluidSolidInterface``. None applies to the
current electro rows, and this module does not handle aliases yet.
"""

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
    that is missing or does not resolve that role."""


#: The layout for a case with no ``constant/physicsProperties`` at all (see
#: the module docstring). Not a row in ``physics_layout.json`` -- there is
#: no ``type`` to key it on.
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

    Corrected 2026-09-26 (R1 fix, finding M2): the brief's interface said
    this returned ``None`` for an unknown role too. It now refuses by name
    instead, matching every other refusal in this module -- an unknown role
    is a table/case mismatch, not a legitimate "no such region" answer.
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
