import os
import time
from pathlib import Path

from omnidriver_agents.adapters.claude_code import ClaudeCodeAdapter, parse_stream, prepare_env

FIXTURE = Path(__file__).parent / "fixtures/stream.jsonl"


def test_the_result_line_gives_turns_cost_usage_and_text():
    result = parse_stream(FIXTURE.read_text().splitlines())
    assert (result.turns, result.cost_usd, result.final_text, result.is_error) == (4, 0.0123, "done", False)
    assert result.usage["output_tokens"] == 20
    assert len(result.transcript) == 3


def test_a_stream_without_a_result_line_is_an_error():
    result = parse_stream(FIXTURE.read_text().splitlines()[:2])
    assert result.is_error and result.turns == 0


def test_the_command_is_headless_with_the_model_and_the_guidance():
    adapter = ClaudeCodeAdapter(model="sonnet", executable=Path("/x/claude"))
    argv = adapter.command("do it", "GUIDE")
    assert argv[:2] == ["/x/claude", "-p"]
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv and "--no-session-persistence" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == "GUIDE"
    assert "--append-system-prompt" not in adapter.command("do it", None)


def test_a_truncated_last_line_is_counted_and_skipped():
    lines = [*FIXTURE.read_text().splitlines(), '{"type": "assis']
    result = parse_stream(lines)
    assert result.undecodable_lines == 1 and result.turns == 4 and len(result.transcript) == 3


def test_the_init_event_gives_model_plugins_mcp_servers_and_hook_count():
    lines = [
        '{"type": "system", "subtype": "init", "model": "m-1", "plugins": ["p"], "mcp_servers": []}',
        '{"type": "system", "subtype": "hook_started"}',
        '{"type": "system", "subtype": "hook_response"}',
        '{"type": "system", "subtype": "other"}',
    ]
    assert parse_stream(lines).init == {"model": "m-1", "plugins": ["p"], "mcp_servers": [], "hooks_seen": 2}


def test_the_declared_path_is_written_for_the_login_shell_to_source(tmp_path):
    work = tmp_path / "trial" / "work"
    work.mkdir(parents=True)
    env = prepare_env({"PATH": "/a b:/c", "HOME": "/h"}, work)
    assert env["CLAUDE_ENV_FILE"] == str(tmp_path / "trial" / "claude-env.sh")
    assert (tmp_path / "trial" / "claude-env.sh").read_text() == "export PATH='/a b:/c'\n"
    assert env["HOME"] == "/h"


FAKE_CLAUDE = """#!/bin/sh
echo $$ > "$PGID_FILE"
echo '{"type": "system", "subtype": "init", "model": "m"}'
sleep 30 &
sleep 30
"""


def test_a_timeout_kills_the_whole_process_group(tmp_path):
    claude = tmp_path / "claude"
    claude.write_text(FAKE_CLAUDE)
    claude.chmod(0o755)
    work = tmp_path / "trial" / "work"
    work.mkdir(parents=True)
    pgid_file = tmp_path / "pgid"
    start = time.monotonic()
    result = ClaudeCodeAdapter("m", claude).run("p", None, work, {"PATH": "/usr/bin:/bin", "PGID_FILE": str(pgid_file)}, 1)
    assert time.monotonic() - start < 10
    assert result.timed_out and result.is_error and result.init["model"] == "m"
    pgid = int(pgid_file.read_text())
    for _ in range(50):
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    raise AssertionError("the process group survived")
