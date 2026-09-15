"""OpenFOAM CLI selection with sweep-plan's structural error contract."""

from __future__ import annotations

import json
import subprocess
import sys


def test_malformed_spec_exits_nonzero_under_the_openfoam_adapter(tmp_path) -> None:
    spec_path = tmp_path / "sweep.json"
    spec_path.write_text("{ not json")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "omnidriver",
            "sweep-plan",
            "--plugin",
            "omnidriver.openfoam.environment:OpenFOAMEnvironmentPlugin",
            "--spec",
            str(spec_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, result.stdout
    assert json.loads(result.stdout)["spec_error"]
