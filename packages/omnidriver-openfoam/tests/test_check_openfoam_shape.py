"""The vocabulary gate: the OpenFOAM layer gains no cardiac token, in code, data or prose."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _script() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "check-openfoam-shape.py"
        if candidate.is_file():
            return candidate
    pytest.fail("no ancestor of this test holds scripts/check-openfoam-shape.py")


def _gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_script()), *args], capture_output=True, text=True)


def test_the_layer_matches_its_empty_baseline():
    result = _gate()
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_cardiac_token_in_a_docstring_or_a_data_file_is_refused(tmp_path: Path):
    (tmp_path / "terms.py").write_text('"""Examples: ``ddt(Vm)``."""\n')
    (tmp_path / "menus.json").write_text('{"region": "electro", "electrode": 1}\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--src", str(tmp_path), "--baseline", str(baseline))
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "NEW    menus.json: electro x1 -- the OpenFOAM layer must not name a solver's vocabulary",
        "NEW    terms.py: Vm x1 -- the OpenFOAM layer must not name a solver's vocabulary",
    ]
