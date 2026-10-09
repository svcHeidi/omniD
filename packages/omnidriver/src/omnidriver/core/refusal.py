"""The one shape in which a command is refused: ``{"status": "failed", "code": ..., "error": ...}`` on stdout, exit 1.

``code`` is stable: the refusal's own named code where it carries one, else its exception's class name. A refusal
that knows which rules a value broke also carries ``refusals``, one :func:`refusal_record` per rule.
"""
from __future__ import annotations

import argparse
import json
from typing import Any


class Refusal(Exception):
    """A command refused by name; its message is the ``error``."""


class RefusingParser(argparse.ArgumentParser):
    """An argument parser whose usage errors are :class:`Refusal` (``--help`` stays argparse's own)."""

    def error(self, message: str):
        raise Refusal(message)


def refusal_record(*, code: str, document: str | None, key: str | None, rule: Any, message: str) -> dict[str, Any]:
    """One broken rule: ``rule`` maps the declaration's field names to their declared values, or is ``None``
    when the ``code`` alone names the rule."""
    return {"code": code, "document": document or None, "key": key or None, "rule": rule, "message": message}


def diagnostic_refusal(item: Any) -> dict[str, Any]:
    """A plan diagnostic as a :func:`refusal_record`; its rule is the one its ``detail`` names."""
    return refusal_record(
        code=item.code, document=item.source, key=item.field, rule=(item.detail or {}).get("rule"), message=item.message,
    )


def refusal_code(exc: BaseException) -> str:
    return getattr(exc, "code", None) or type(exc).__name__


def refusal_fields(exc: BaseException | None, *, code: str | None = None) -> dict[str, Any]:
    """``code``, and ``refusals`` when ``exc`` carries any: what a refusal adds beside its text."""
    refusals = list(getattr(exc, "refusals", ()))
    return {"code": code or refusal_code(exc), **({"refusals": refusals} if refusals else {})}


def failure(exc: BaseException | None, *, code: str | None = None, error: str | None = None, **extra: Any) -> dict[str, Any]:
    """The refusal payload for ``exc``, or for a refusal with no exception (``code`` and ``error`` given)."""
    return {
        "status": "failed", **extra, **refusal_fields(exc, code=code),
        "error": str(exc) if error is None else error,
    }


def print_refusal(refusal: BaseException, **extra: Any) -> int:
    print(json.dumps(failure(refusal, **extra), indent=2))
    return 1
