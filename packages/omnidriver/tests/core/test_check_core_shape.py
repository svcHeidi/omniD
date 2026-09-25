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


# --- C-I1: snake_case / other spellings of the same layout token must count too. ---


def test_snake_case_identifier_spelling_of_a_token_counts(tmp_path: Path):
    """`touch_case_foam` is the same coupling as `case.foam`, spelled as a
    Python identifier (review C-I1's generic_case.py example)."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text("def f(touch_case_foam: bool) -> None:\n    return None\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "case.foam" in result.stdout


def test_snake_case_spelling_of_a_camel_case_token_counts(tmp_path: Path):
    """`block_mesh` is the same coupling as `blockMesh`, just underscore-separated."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text("def run_block_mesh() -> None:\n    return None\n")
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "blockMesh" in result.stdout


def test_foam_underscore_stays_an_unbounded_substring_match(tmp_path: Path):
    """FOAM_ deliberately has no left boundary: it must still catch OPENFOAM_-style
    constants (review: a boundary would stop catching those)."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "OPENFOAM_RUN_ROOT"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "FOAM_" in result.stdout


def test_processor_gets_a_left_boundary(tmp_path: Path):
    """`postprocessor`/`preprocessor` must NOT count as `processor`, but
    `processor_dir` (a real core spelling) must."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text(
        "postprocessor = 1\n"
        "preprocessor = 1\n"
        "processor_dir = 1\n"
    )
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    lines = [line for line in result.stdout.splitlines() if "processor" in line]
    assert len(lines) == 1
    assert "x1" in lines[0]


# --- C-I2: --write-baseline must preserve reasons, and TODO-reason must fail the gate. ---


def test_write_baseline_preserves_reason_for_an_unchanged_pair(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("m.py\tcontrolDict\t1\thand-written reason\n")
    result = _gate("--core-src", str(core), "--baseline", str(baseline), "--write-baseline")
    assert result.returncode == 0
    content = baseline.read_text()
    assert "hand-written reason" in content
    assert "TODO-reason" not in content


def test_write_baseline_marks_a_changed_count_as_todo_reason(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "controlDict controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("m.py\tcontrolDict\t1\thand-written reason\n")
    _gate("--core-src", str(core), "--baseline", str(baseline), "--write-baseline")
    content = baseline.read_text()
    assert "hand-written reason" not in content
    assert "m.py\tcontrolDict\t2\tTODO-reason" in content


def test_write_baseline_marks_a_new_pair_as_todo_reason(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("")
    _gate("--core-src", str(core), "--baseline", str(baseline), "--write-baseline")
    content = baseline.read_text()
    assert "m.py\tcontrolDict\t1\tTODO-reason" in content


def test_check_fails_while_a_todo_reason_remains(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("m.py\tcontrolDict\t1\tTODO-reason\n")
    result = _gate("--core-src", str(core), "--baseline", str(baseline))
    assert result.returncode == 1
    assert "m.py" in result.stdout
    assert "controlDict" in result.stdout


def test_write_baseline_preserves_the_header(tmp_path: Path):
    core = tmp_path / "core"
    core.mkdir()
    (core / "m.py").write_text('X = "controlDict"\n')
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("# a hand-written header comment\nm.py\tcontrolDict\t1\treason\n")
    _gate("--core-src", str(core), "--baseline", str(baseline), "--write-baseline")
    content = baseline.read_text()
    assert content.startswith("# a hand-written header comment")
