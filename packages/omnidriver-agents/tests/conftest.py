import json
from pathlib import Path

import pytest

from omnidriver_agents.adapters import AdapterResult


class FakeAdapter:
    """Plays a script: each step is a shell command run in the trial folder, then a final answer."""

    name = "fake"

    def __init__(self, commands=(), answer=None):
        self.commands, self.answer, self.calls = commands, answer, []

    def version(self):
        return "fake-1"

    def run(self, prompt, system, cwd, env, wall_seconds):
        import subprocess
        self.calls.append({"prompt": prompt, "system": system, "env": env})
        transcript = []
        for command in self.commands:
            out = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
            transcript.append({"type": "user", "message": {"content": [{"type": "tool_result", "content": out.stdout}]}})
        if self.answer is not None:
            (Path(cwd) / "answer.json").write_text(json.dumps(self.answer))
        return AdapterResult(final_text="done", transcript=transcript, turns=len(self.commands) + 1, cost_usd=0.0)


@pytest.fixture
def fake_adapter():
    return FakeAdapter
