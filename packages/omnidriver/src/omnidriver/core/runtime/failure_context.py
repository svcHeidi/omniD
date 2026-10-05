from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

DEFAULT_TAIL_LINES = 200
DEFAULT_TAIL_BYTES = 65536  # 64 KiB default cap on the tail read window
#: How much of a child's own output a report quotes.
OUTPUT_TAIL_CHARS = 800


def redact_text(text: str, patterns: Iterable[str]) -> str:
    """Replace every match of each pattern, whole, with ``[REDACTED]``.

    Capture groups are not preserved: a pattern that must keep context
    around the secret uses lookarounds instead, e.g.
    ``(?<=://)[^/\\s@]+(?=@)`` matches only a URL's credential."""
    for pattern in [re.compile(p) for p in patterns]:
        text = pattern.sub(lambda _match: "[REDACTED]", text)
    return text


def why_a_child_stopped(stdout: str, stderr: str, patterns: Iterable[str]) -> str:
    """What a child omnidriver that did not complete said: the error and the error diagnostics its JSON report
    carries, else the tail of its stderr or stdout. Matches of ``patterns`` are redacted."""
    try:
        report = json.loads(stdout)
    except (TypeError, ValueError):
        report = None
    report = report if isinstance(report, dict) else {}
    context = report.get("failure_context")
    diagnostics = [
        d for group in (report.get("environment_diagnostics"), report.get("diagnostics"),
                        context.get("diagnostics") if isinstance(context, dict) else None)
        for d in group or () if isinstance(d, dict) and d.get("level") == "error"
    ]
    said = [str(report["error"])] if report.get("error") else []
    said += [f"{d.get('code')}: {d.get('message')}" for d in diagnostics]
    text = "; ".join(said) or (stderr or "").strip() or (stdout or "").strip()
    return redact_text(text, patterns)[-OUTPUT_TAIL_CHARS:]


def _tail_file(path: str | None, *, max_lines: int, max_bytes: int) -> tuple[str, bool]:
    """(tail_text, truncated), read from the end so a huge log cannot exhaust memory; ("", False) on I/O errors."""
    if not path:
        return "", False
    file_path = Path(path)
    try:
        size = file_path.stat().st_size
        with file_path.open("rb") as handle:
            read_from_start = size <= max_bytes
            if not read_from_start:
                handle.seek(size - max_bytes)
            raw = handle.read()
    except OSError:
        return "", False

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    # After a mid-file seek the first "line" is almost certainly a fragment of a
    # longer log line; drop it so the agent never reads a partial leading line.
    if not read_from_start and lines:
        lines = lines[1:]
    truncated = not read_from_start or len(lines) > max_lines
    return "\n".join(lines[-max_lines:]), truncated


def build_failure_context(
    step_state,
    *,
    max_lines: int = DEFAULT_TAIL_LINES,
    max_bytes: int = DEFAULT_TAIL_BYTES,
) -> dict[str, Any]:
    """Return a self-contained failure bundle for a failed workflow step."""
    stdout_tail, stdout_truncated = _tail_file(
        step_state.stdout_log, max_lines=max_lines, max_bytes=max_bytes
    )
    stderr_tail, stderr_truncated = _tail_file(
        step_state.stderr_log, max_lines=max_lines, max_bytes=max_bytes
    )
    return {
        "step_id": step_state.step_id,
        "attempt": step_state.attempt,
        "exit_code": step_state.exit_code,
        "diagnostics": [dict(diagnostic) for diagnostic in step_state.diagnostics],
        "stdout_log": step_state.stdout_log,
        "stderr_log": step_state.stderr_log,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
