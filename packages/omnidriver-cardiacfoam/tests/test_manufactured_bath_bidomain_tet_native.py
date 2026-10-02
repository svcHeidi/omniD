"""``manufacturedBathBidomain``'s tet route, run for real through the record.

Conformance covers the default hex route; this runs the tet route at its
coarsest study level (``tetNumberCells`` 10) with ``endTime`` 0.02.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.conformance import record_run, require_commands
from cardiacfoam_native import native_tutorials_root

pytestmark = pytest.mark.native


def test_the_tet_route_runs_through_the_record(tmp_path: Path) -> None:
    require_commands(
        "gmsh", "gmshToFoam", "checkMesh", "setTorsoOrganConductivityField",
        "cardiacFoam", "bathBidomainInterfaceMetrics",
    )
    run = record_run(
        tmp_path, plugin="cardiacfoam", record="manufacturedBathBidomain", cases_root=native_tutorials_root(),
        sweep={"tetNumberCells": [10]},
        study={"mesh": "tet", "system/controlDict:endTime": 0.02}, timeout_s=600,
    )
    # The verifier names its summary from the tet mesh's own resolution.
    (summary,) = sorted((run.case_root / "postProcessing").glob("3D_*_cells.dat"))
    assert "# fdaBathVariant electrodePair" in summary.read_text()
    assert (run.case_root / "postProcessing/bathBidomainInterfaceMetrics.csv").is_file()
