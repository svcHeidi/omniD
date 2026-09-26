"""``manufacturedBathBidomain``'s tet route, run for real through the record
(plan §5b T4; review 54b M2: a tet route is proved by a run, not only
declared). The conformance target covers the default hex route; this is
the one real gmsh -> gmshToFoam -> checkMesh -> setTorsoOrganConductivityField
-> cardiacFoam -> bathBidomainInterfaceMetrics run, at the tet studies'
coarsest level (``tetNumberCells`` 10, ``lc = 0.1``) and ``endTime`` 0.02.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cardiacfoam_native import native_tutorials_root, require_sourced_openfoam

pytestmark = pytest.mark.native


def test_the_tet_route_runs_through_the_record(tmp_path: Path) -> None:
    require_sourced_openfoam(
        "gmsh", "gmshToFoam", "checkMesh", "setTorsoOrganConductivityField",
        "cardiacFoam", "bathBidomainInterfaceMetrics",
    )
    spec = {
        "base": {
            "entry": "manufacturedBathBidomain", "cases_root": str(native_tutorials_root()),
            "mesh": "tet", "dimension": "3D", "system/controlDict:endTime": 0.02,
        },
        "sweep": {"mode": "zip", "independent": {"tetNumberCells": [10]}},
    }
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text(json.dumps(spec))
    output = tmp_path / "sweep"
    proc = subprocess.run(
        [sys.executable, "-m", "omnidriver", "sweep-run", "--plugin", "cardiacfoam",
         "--spec", str(spec_path), "--output-dir", str(output),
         "--scratch-dir", str(tmp_path / "scratch")],
        capture_output=True, text=True, timeout=600,
    )
    payload = json.loads(proc.stdout)
    (case,) = payload["cases"]
    assert case["status"] == "completed", (proc.stdout[-3000:], proc.stderr[-2000:])
    # Every output the tet route declares was found, as C6 counts them.
    artifacts = case["artifact_reconciliation"]["artifacts"]
    missing = [a["artifact_id"] for a in artifacts if a["status"] == "missing" and not a.get("optional")]
    assert artifacts and not missing, missing

    case_root = output / "cases" / case["case_id"]
    # The verifier names its summary from the tet mesh's own resolution.
    (summary,) = sorted((case_root / "postProcessing").glob("3D_*_cells.dat"))
    assert "# fdaBathVariant electrodePair" in summary.read_text()
    assert (case_root / "postProcessing/bathBidomainInterfaceMetrics.csv").is_file()
