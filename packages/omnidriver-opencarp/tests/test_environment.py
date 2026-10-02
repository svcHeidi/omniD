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


def _binary_reporting(tmp_path, tag):
    """A stand-in for openCARP that answers ``-buildinfo`` with the header's own shape."""
    binary = tmp_path / "bin" / "openCARP"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text(f"#!/bin/sh\necho '*** GIT tag:            {tag}'\necho '*** GIT hash:           0000'\n")
    binary.chmod(0o755)
    return {"PATH": str(binary.parent)}


def test_a_binary_whose_tag_is_not_the_catalogues_is_warned_naming_both(tmp_path):
    from omnidriver.opencarp import environment
    from omnidriver.opencarp.catalog import load_catalog

    dag = {"steps": [{"command": "openCARP"}]}
    tag = load_catalog().identity["tag"]
    assert not [
        d for d in environment.opencarp_environment_diagnostics(dag, _binary_reporting(tmp_path, tag))
        if d.code == "opencarp_version_mismatch"
    ]
    (warning,) = [
        d for d in environment.opencarp_environment_diagnostics(dag, _binary_reporting(tmp_path, "v0.0"))
        if d.code == "opencarp_version_mismatch"
    ]
    assert warning.level == "warning" and f"'{tag}'" in warning.message and "'v0.0'" in warning.message
