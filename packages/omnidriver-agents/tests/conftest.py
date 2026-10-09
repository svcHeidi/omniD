import json
import subprocess
from pathlib import Path

import pytest

from omnidriver_agents.adapters import AdapterResult


class FakeAdapter:
    """Plays a script: each step is a shell command run in the trial folder, then a final answer."""

    name = "fake"

    def __init__(self, commands=(), answer=None, init=None, error=None):
        self.commands, self.answer, self.init, self.error = commands, answer, init or {}, error
        self.calls, self.outputs = [], []

    def version(self):
        return "fake-1"

    def run(self, prompt, system, cwd, env, wall_seconds):
        self.calls.append({"prompt": prompt, "system": system, "env": env})
        if self.error:
            raise self.error
        transcript = []
        for number, command in enumerate(self.commands):
            out = subprocess.run(command, shell=True, cwd=cwd, env=env, capture_output=True, text=True)
            self.outputs.append(out.stdout)
            transcript.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": f"t{number}", "name": "Bash", "input": {"command": command}}]}})
            transcript.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"t{number}", "content": out.stdout}]}})
        if self.answer is not None:
            (Path(cwd) / "answer.json").write_text(json.dumps(self.answer))
        return AdapterResult(final_text="done", transcript=transcript, turns=len(self.commands) + 1, cost_usd=0.0,
                             init=self.init)


@pytest.fixture
def fake_adapter():
    return FakeAdapter
