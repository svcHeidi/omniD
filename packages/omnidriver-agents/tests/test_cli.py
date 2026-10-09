import subprocess

import pytest

from omnidriver_agents.cli import main


def test_run_requires_every_path(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--task", "t.json", "--model", "haiku", "--condition", "omnid", "--repeats", "1"])
    assert exc.value.code == 2
    assert "--output" in capsys.readouterr().err


def _args(tmp_path, repo, *extra):
    return ["run", "--task", str(tmp_path / "t.json"), "--model", "haiku", "--condition", "omnid", "--repeats", "1",
            "--output", str(tmp_path / "out"), "--omnid-repo", str(repo), "--omnidriver", "/x/omnidriver",
            "--claude", "/x/claude", "--agent-python", "/x/python", "--agent-home", str(tmp_path / "home"), *extra]


def test_the_omnid_repo_must_be_a_git_repo(tmp_path):
    with pytest.raises(SystemExit, match="git"):
        main(_args(tmp_path, tmp_path))


def test_the_oracle_env_file_must_be_a_json_object(tmp_path):
    (tmp_path / "env.json").write_text("[1]")
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x",
                    "--allow-empty"], check=True, capture_output=True)
    with pytest.raises(SystemExit, match="oracle-env-file"):
        main(_args(tmp_path, tmp_path, "--oracle-env-file", str(tmp_path / "env.json")))
