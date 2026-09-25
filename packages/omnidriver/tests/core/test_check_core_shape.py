"""The shape gate: core gains no new OpenFOAM layout token, and its recorded debt only shrinks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _script() -> Path:
    """The gate script, found by marker from this test file. Tests always
    run from a checkout (they are not in the wheel), so a miss is a failure."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "scripts" / "check-core-shape.py"
        if candidate.is_file():
            return candidate
    pytest.fail("no ancestor of this test holds scripts/check-core-shape.py")


def _gate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_script()), *args], capture_output=True, text=True)


def test_repository_matches_its_baseline():
    result = _gate()
    assert result.returncode == 0, result.stdout + result.stderr


def test_a_new_token_fails(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('PATH = "system/controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "controlDict" in result.stdout


def test_comments_and_docstrings_do_not_count(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('"""Mentions polyMesh."""\n# and blockMesh\nX = 1\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    assert _gate("--core-src", str(core), "--baseline", str(baseline)).returncode == 0


def test_a_shrunk_count_must_be_recorded(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text("X = 1\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("m.py\tbashrc\t2\ttest debt\n")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "shrank" in result.stdout
