"""What describe tells an agent about a tutorial record, the same for every solver (C10)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

DOCUMENTATION_ROLE = "case.documentation"


def record_surface(record, *, native_case_root: Path, driver_context) -> dict[str, Any]:
    axis_catalog = driver_context.capabilities.axes.catalog() or {}
    axes = [
        {"name": name, "value_kind": axis_catalog[name].value_kind}
        for name in sorted(record.allowed_axes) if name in axis_catalog
    ]
    surface = driver_context.capabilities.record_surface
    documentation = []
    for rule in driver_context.capabilities.case_files.all_rules():
        path = Path(native_case_root) / rule.path
        if rule.role == DOCUMENTATION_ROLE and path.is_file():
            documentation.append({"path": rule.path, "text": path.read_text(errors="replace")})
    return {
        "axes": axes,
        "keys": [dict(entry) for entry in surface.key_catalog(Path(native_case_root))],
        "guidance": [dict(item) for item in surface.guidance()],
        "case_documentation": documentation,
    }
