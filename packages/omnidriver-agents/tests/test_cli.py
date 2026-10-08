import pytest

from omnidriver_agents.cli import main


def test_run_requires_every_path(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["run", "--task", "t.json", "--model", "haiku", "--condition", "omnid", "--repeats", "1"])
    assert exc.value.code == 2
    assert "--output" in capsys.readouterr().err
