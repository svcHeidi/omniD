from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Sequence

from foamlib import FoamFile

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic as _diagnostic

# controlDict locations to scan: top-level and the electro sub-region used by
# multi-region electromechanical cases.
_CONTROLDICT_RELPATHS = ("system/controlDict", "system/electro/controlDict")


def _diagnostics_for_path(
    path: Path, samplable: Mapping[str, set[str]], source: str
) -> list[StrictDiagnostic]:
    try:
        functions = FoamFile(path)["functions"]
    except KeyError:
        return []
    diagnostics: list[StrictDiagnostic] = []
    for name in functions.keys():
        subdict = functions[name]
        if not hasattr(subdict, "keys"):
            # A non-dict entry (e.g. #includeFunc) carries no braces and
            # samples nothing of its own.
            continue
        region = subdict.get("region", "electro")
        if region not in samplable:
            # Skip rather than guess: a region absent from samplable (e.g. an
            # uncatalogued bath/torso domain) would otherwise fabricate a
            # warning under "electro".
            continue
        allowed = samplable[region]
        for field_name in subdict.get("fields", []):
            if field_name not in allowed:
                diagnostics.append(
                    _diagnostic(
                        "warning",
                        "unknown_sampled_field",
                        (
                            f"Function object samples field {field_name!r} "
                            f"(region {region!r}) which the resolved model does "
                            "not expose; the solver will silently drop it."
                        ),
                        source=source,
                        field=field_name,
                    )
                )
    return diagnostics


def function_object_field_diagnostics(
    case_root: str | Path,
    *,
    samplable: Mapping[str, Sequence[str] | set[str]],
) -> tuple[StrictDiagnostic, ...]:
    """Warn (never error) about controlDict function objects sampling fields
    absent from ``samplable`` (an open ``{region_name: {field, ...}}`` map,
    typically from :func:`capability_manifest.build_capability_manifest`;
    core imposes no fixed key set). A function object whose ``region`` isn't
    a key in ``samplable`` is skipped rather than checked against a guessed
    bucket.

    Degrades to silence on any parse or IO failure. Honors
    ``SKIP_FUNCTION_OBJECT_DIAGNOSTICS`` to bypass the check entirely.
    """
    if os.environ.get("SKIP_FUNCTION_OBJECT_DIAGNOSTICS"):
        return ()
    normalized = {region: set(fields) for region, fields in samplable.items()}
    root = Path(case_root)
    diagnostics: list[StrictDiagnostic] = []
    for relpath in _CONTROLDICT_RELPATHS:
        path = root / relpath
        if not path.is_file():
            continue
        try:
            diagnostics.extend(_diagnostics_for_path(path, normalized, str(path)))
        except Exception:
            # Degrade to silence on any parse/IO failure (OSError, or
            # foamlib.FoamFileDecodeError, a ValueError subclass) rather
            # than crash or fabricate a warning.
            continue
    return tuple(diagnostics)
