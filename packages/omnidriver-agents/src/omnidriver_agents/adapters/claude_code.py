"""Claude Code, run headless with ``claude -p`` and read from its ``stream-json`` output."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import signal
import subprocess
from collections.abc import Iterable
from pathlib import Path

from . import AdapterResult


def parse_stream(lines: Iterable[str]) -> AdapterResult:
    """One ``stream-json`` transcript; the ``result`` line carries turns, cost, usage and the final text.

    A line that is not a JSON object (a truncated last line after a kill) is counted, not read.
    """
    transcript, undecodable = [], 0
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = None
        if isinstance(event, dict):
            transcript.append(event)
        else:
            undecodable += 1
    system = [e for e in transcript if e.get("type") == "system"]
    start = next((e for e in system if e.get("subtype") == "init"), {})
    init = {"model": start.get("model"), "plugins": start.get("plugins"), "mcp_servers": start.get("mcp_servers"),
            "hooks_seen": sum(str(e.get("subtype", "")).startswith("hook_") for e in system)} if start else {}
    final = next((e for e in reversed(transcript) if e.get("type") == "result"), None)
    if final is None:
        return AdapterResult(final_text="", transcript=transcript, turns=0, cost_usd=None, is_error=True,
                             undecodable_lines=undecodable, init=init)
    return AdapterResult(
        final_text=final.get("result", ""), transcript=transcript, turns=final.get("num_turns", 0),
        cost_usd=final.get("total_cost_usd"), usage=final.get("usage", {}), is_error=bool(final.get("is_error")),
        undecodable_lines=undecodable, init=init,
    )


def prepare_env(env: dict[str, str], cwd: Path) -> dict[str, str]:
    """``env`` plus ``CLAUDE_ENV_FILE``, which Claude Code sources before each Bash command, restoring the declared PATH."""
    env_file = cwd.parent / "claude-env.sh"
    env_file.write_text(f"export PATH={shlex.quote(env['PATH'])}\n")
    return {**env, "CLAUDE_ENV_FILE": str(env_file)}


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
        proc = subprocess.Popen(self.command(prompt, system), cwd=cwd, env=prepare_env(env, cwd), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=wall_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
        result = parse_stream(out.splitlines())
        if timed_out:
            result.timed_out, result.is_error = True, True
        return result
