"""What every agent adapter returns, and the one method it implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class AdapterResult:
    final_text: str
    transcript: list[dict]
    turns: int
    cost_usd: float | None
    usage: dict = field(default_factory=dict)
    is_error: bool = False
    timed_out: bool = False
    undecodable_lines: int = 0
    init: dict = field(default_factory=dict)


class Adapter(Protocol):
    name: str

    def version(self) -> str: ...

    def run(self, prompt: str, system: str | None, cwd: Path, env: dict[str, str], wall_seconds: int) -> AdapterResult: ...
