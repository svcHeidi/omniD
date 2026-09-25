"""openCARP's preflight diagnostics, without the binary."""
from __future__ import annotations

from omnidriver.opencarp.environment import opencarp_environment_diagnostics


def test_a_missing_command_is_quoted_so_c9_can_find_it_S_I2(tmp_path):
    """C9 requires the solver command as a quoted token once the echoed PATH
    is removed (final review S-I2). The PATH here holds the solver's name,
    as ``~/openCARP-runs`` would."""
    empty = tmp_path / "openCARP-runs" / "empty"
    empty.mkdir(parents=True)
    dag = {"steps": [{"command": "mesher"}, {"command": "openCARP"}]}
    messages = [d.message.replace(str(empty), "")
                for d in opencarp_environment_diagnostics(dag, {"PATH": str(empty)}) if d.level == "error"]
    assert any("'openCARP'" in m for m in messages), messages
    assert any("'mesher'" in m for m in messages), messages
