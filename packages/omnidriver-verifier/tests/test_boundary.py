import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_import_gate_passes_and_rules_this_package():
    gate = REPO / "scripts/check-import-boundaries.py"
    assert "VERIFIER_SRC" in gate.read_text()
    result = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_the_console_script_is_declared():
    pyproject = (REPO / "packages/omnidriver-verifier/pyproject.toml").read_text()
    assert 'omnidriver-verify = "omnidriver.verifier.cli:main"' in pyproject
