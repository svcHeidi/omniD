"""Claude Code, run headless with ``claude -p`` and read from its ``stream-json`` output."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from pathlib import Path

from . import AdapterResult


def parse_stream(lines: Iterable[str]) -> AdapterResult:
    """One ``stream-json`` transcript; the ``result`` line carries turns, cost, usage and the final text."""
    transcript = [json.loads(line) for line in lines if line.strip()]
    final = next((e for e in reversed(transcript) if e.get("type") == "result"), None)
    if final is None:
        return AdapterResult(final_text="", transcript=transcript, turns=0, cost_usd=None, is_error=True)
    return AdapterResult(
        final_text=final.get("result", ""), transcript=transcript, turns=final.get("num_turns", 0),
        cost_usd=final.get("total_cost_usd"), usage=final.get("usage", {}), is_error=bool(final.get("is_error")),
    )


class ClaudeCodeAdapter:
    def __init__(self, model: str, executable: Path):
        self.model, self.executable = model, executable
        self.name = f"claude-code:{model}"

    def command(self, prompt: str, system: str | None) -> list[str]:
        argv = [str(self.executable), "-p", prompt, "--model", self.model, "--output-format", "stream-json",
                "--verbose", "--no-session-persistence", "--permission-mode", "bypassPermissions"]
        if system is not None:
            argv += ["--append-system-prompt", system]
        return argv

    def version(self) -> str:
        return subprocess.run([str(self.executable), "--version"], capture_output=True, text=True).stdout.strip()

    def run(self, prompt: str, system: str | None, cwd: Path, env: dict[str, str], wall_seconds: int) -> AdapterResult:
        try:
            done = subprocess.run(self.command(prompt, system), cwd=cwd, env=env, capture_output=True,
                                  text=True, timeout=wall_seconds)
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            result = parse_stream(out.splitlines())
            result.timed_out, result.is_error = True, True
            return result
        return parse_stream(done.stdout.splitlines())
