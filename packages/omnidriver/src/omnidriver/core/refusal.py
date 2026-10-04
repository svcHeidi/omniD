"""The one shape in which a command a caller got wrong is refused: ``{"status": "failed", "error": ...}`` on stdout, exit 1."""
from __future__ import annotations

import argparse
import json


class Refusal(Exception):
    """A command refused by name; its message is the ``error``."""


class RefusingParser(argparse.ArgumentParser):
    """An argument parser whose usage errors are :class:`Refusal` (``--help`` stays argparse's own)."""

    def error(self, message: str):
        raise Refusal(message)


def print_refusal(refusal: Refusal, **extra: str) -> int:
    print(json.dumps({"status": "failed", **extra, "error": str(refusal)}, indent=2))
    return 1
