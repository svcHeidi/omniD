import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_import_gate_passes_and_knows_this_package():
    gate = REPO / "scripts/check-import-boundaries.py"
    assert "omnidriver_agents" in gate.read_text()
    result = subprocess.run([sys.executable, str(gate)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout
