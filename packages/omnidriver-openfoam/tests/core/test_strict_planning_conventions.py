"""OpenFOAM strict-planning conventions: adapter-owned mesh-geometry
exemption behaviour."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.runtime.models import TutorialSpec
from omnidriver.core.strict_planning import _mesh_geometry_exempt
from omnidriver.openfoam.environment import openfoam_environment_context


def test_a_plain_entry_is_not_exempt_through_this_adapter(tmp_path: Path) -> None:
    spec = TutorialSpec(
        name="plainCase", case_root=tmp_path,
        metadata={"entry_name": "plainCase", "workflow_family": "plainCase"},
    )
    assert _mesh_geometry_exempt(spec, openfoam_environment_context()) is False
