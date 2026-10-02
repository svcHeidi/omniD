"""openCARP's preflight diagnostics, without the binary."""
from __future__ import annotations

from omnidriver.opencarp.environment import opencarp_environment_diagnostics


def test_a_missing_command_is_quoted_so_c9_can_find_it_S_I2(tmp_path):
    """The PATH here holds the solver's name, as ``~/openCARP-runs`` would."""
    empty = tmp_path / "openCARP-runs" / "empty"
    empty.mkdir(parents=True)
    dag = {"steps": [{"command": "mesher"}, {"command": "openCARP"}]}
    messages = [d.message.replace(str(empty), "")
                for d in opencarp_environment_diagnostics(dag, {"PATH": str(empty)}) if d.level == "error"]
    assert any("'openCARP'" in m for m in messages), messages
    assert any("'mesher'" in m for m in messages), messages


def test_the_credential_in_the_build_headers_repository_line_is_all_that_is_redacted():
    import re

    from omnidriver.opencarp.environment import REDACTION_PATTERNS

    # The shape of `openCARP -buildinfo`'s repository line; the token is a placeholder.
    header = "*** GIT repo:           https://gitlab-ci-token:placeholder@git.opencarp.org/openCARP/openCARP.git"
    for pattern in REDACTION_PATTERNS:
        header = re.sub(pattern, "[REDACTED]", header)
    assert header == "*** GIT repo:           https://[REDACTED]@git.opencarp.org/openCARP/openCARP.git"
