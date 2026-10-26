from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from foamlib import FoamFile

from omnidriver.core.planning_types import StrictDiagnostic, diagnostic as _diagnostic

# OpenFOAM's name for a case's single mesh (polyMesh::defaultRegion), the
# region a function object samples when it declares none.
DEFAULT_REGION = "region0"


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
        region = subdict.get("region", DEFAULT_REGION)
        if region not in samplable:
            # A region the stack does not describe is skipped, never checked
            # against another region's fields.
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
    """Warn (never error) about ``system/controlDict`` function objects that
    sample a field absent from ``samplable``, a ``{region: fields}`` map keyed
    by mesh region (``region0`` for a single-region case). A function object
    whose region is not a key is skipped. Silent on any parse or IO failure.
    """
    normalized = {region: set(fields) for region, fields in samplable.items()}
    path = Path(case_root) / "system" / "controlDict"
    if not path.is_file():
        return ()
    try:
        return tuple(_diagnostics_for_path(path, normalized, str(path)))
    except Exception:
        # OSError, or foamlib.FoamFileDecodeError (a ValueError subclass):
        # silence rather than a crash or a fabricated warning.
        return ()
