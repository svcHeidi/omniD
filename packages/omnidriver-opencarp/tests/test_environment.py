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


def _binary_reporting(tmp_path, tag, commit="0000"):
    """A stand-in for openCARP that answers ``-buildinfo`` with the header's own shape."""
    binary = tmp_path / "bin" / "openCARP"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text(f"#!/bin/sh\necho '*** GIT tag:            {tag}'\necho '*** GIT hash:           {commit}'\n")
    binary.chmod(0o755)
    return {"PATH": str(binary.parent)}


def _mismatches(tmp_path, tag, commit):
    from omnidriver.opencarp import environment

    found = environment.opencarp_environment_diagnostics(
        {"steps": [{"command": "openCARP"}]}, _binary_reporting(tmp_path, tag, commit),
    )
    return [d for d in found if d.code == "opencarp_version_mismatch"]


def test_a_binary_whose_tag_or_hash_is_not_the_catalogues_is_warned_naming_both(tmp_path):
    from omnidriver.opencarp.catalog import load_catalog

    identity = load_catalog().identity
    tag, commit = identity["tag"], identity["hash"]
    assert not _mismatches(tmp_path, tag, commit)
    (warning,) = _mismatches(tmp_path, "v0.0", commit)
    assert warning.level == "warning" and f"'{tag}'" in warning.message and "'v0.0'" in warning.message
    (warning,) = _mismatches(tmp_path, tag, "0000")
    assert f"'{commit}'" in warning.message and "'0000'" in warning.message
