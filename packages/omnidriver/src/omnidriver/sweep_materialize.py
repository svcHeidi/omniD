from __future__ import annotations

from pathlib import Path
from typing import Any


def materialize_case(
    *, case_dir: Path, routed: dict[str, Any], driver_context,
) -> None:
    """Materialize via the selected plugin."""

    from .core.plugin_capabilities import SweepMaterializationRequest

    driver_context.capabilities.sweep_materializer.materialize(
        SweepMaterializationRequest(case_dir=case_dir, routed=routed),
    )
