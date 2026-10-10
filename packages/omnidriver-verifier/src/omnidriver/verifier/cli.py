"""``omnidriver-verify``: the problem library and its deterministic checks, as JSON."""
from __future__ import annotations

from typing import Sequence

from omnidriver.core.refusal import Refusal, RefusingParser, print_refusal


def _parser() -> RefusingParser:
    parser = RefusingParser(prog="omnidriver-verify", description=__doc__)
    parser.add_subparsers(dest="command", required=True, parser_class=RefusingParser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one ``omnidriver-verify`` command; every answer, and every refusal, is JSON on stdout."""
    try:
        _parser().parse_args(argv)
    except Refusal as refusal:
        return print_refusal(refusal)
    return 0
