import json
from pathlib import Path

import pytest

from omnidriver_agents.task import TaskError, load_task

BASE = {
    "id": "t1", "role": "runner", "brief": "Run the case at {cases}. Write answer.json.",
    "inputs": ["cases"], "programs": ["openCARP"], "wall_seconds": 600,
    "oracle": {"argv": ["python3", "{task_dir}/oracle.py", "{trial}"], "pass_field": "status", "pass_values": ["passed"]},
}


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "task.json"
    path.write_text(json.dumps(data))
    return path


def test_supplied_inputs_fill_the_brief_and_the_oracle(tmp_path):
    task = load_task(_write(tmp_path, BASE), {"cases": "/c"})
    assert task.brief == "Run the case at /c. Write answer.json."
    assert task.oracle.argv == ("python3", f"{tmp_path}/oracle.py", "{trial}")
    assert len(task.digest) == 64


def test_a_missing_input_is_refused_by_name(tmp_path):
    with pytest.raises(TaskError, match="cases"):
        load_task(_write(tmp_path, BASE), {})


def test_an_unknown_key_is_refused(tmp_path):
    with pytest.raises(TaskError, match="budget"):
        load_task(_write(tmp_path, {**BASE, "budget": 3}), {"cases": "/c"})


def test_an_unknown_role_is_refused(tmp_path):
    with pytest.raises(TaskError, match="role"):
        load_task(_write(tmp_path, {**BASE, "role": "pilot"}), {"cases": "/c"})


def test_a_task_carries_no_inputs_field(tmp_path):
    assert not hasattr(load_task(_write(tmp_path, BASE), {"cases": "/c"}), "inputs")
