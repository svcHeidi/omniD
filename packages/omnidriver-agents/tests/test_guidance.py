import hashlib

import pytest

from omnidriver_agents.guidance import GuidanceError, load_guidance


def _repo(tmp_path, runner_required=("agent-handbook/runner.md",)):
    (tmp_path / "agent-handbook").mkdir()
    (tmp_path / "AGENTS.md").write_text("router\n")
    (tmp_path / "agent-handbook/runner.md").write_text("runner\n")
    required = "\n".join(f"      - {p}" for p in runner_required)
    (tmp_path / "agent-handbook/guidance-manifest.yaml").write_text(
        f"version: 1\ncommon:\n  - AGENTS.md\nroles:\n  runner:\n    required:\n{required}\n"
    )
    return tmp_path


def test_common_then_required_files_with_their_hashes(tmp_path):
    guidance = load_guidance(_repo(tmp_path), "runner")
    assert [p for p, _ in guidance.files] == ["AGENTS.md", "agent-handbook/runner.md"]
    assert guidance.files[0][1] == hashlib.sha256(b"router\n").hexdigest()
    assert guidance.text.index("router") < guidance.text.index("runner")


def test_a_missing_listed_file_fails(tmp_path):
    with pytest.raises(GuidanceError, match="nope.md"):
        load_guidance(_repo(tmp_path, ("agent-handbook/nope.md",)), "runner")


def test_an_unknown_role_fails(tmp_path):
    with pytest.raises(GuidanceError, match="pilot"):
        load_guidance(_repo(tmp_path), "pilot")
