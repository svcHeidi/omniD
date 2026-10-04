"""One refusal shape: every command a caller gets wrong prints ``{"status": "failed", "error": ...}`` and exits 1."""
from __future__ import annotations

import json

from omnidriver.cli import main


def refusal(capsys, argv: list[str]) -> str:
    """Run ``argv`` and return the refusal's ``error`` text, after checking the shape."""
    code = main(argv)
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 and payload["status"] == "failed", payload
    return payload["error"]
