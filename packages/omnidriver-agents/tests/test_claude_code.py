from pathlib import Path

from omnidriver_agents.adapters.claude_code import ClaudeCodeAdapter, parse_stream

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
