"""--openfoam-bashrc was renamed to --environment-bashrc (Tier 3,
future/ENVIRONMENT_CONTRACT.md #10) since the concept -- an
environment-sourcing script -- applies to any plugin, not just
OpenFOAM. The deprecated alias was removed outright rather than kept:
this codebase has no external callers to protect yet, so
pre-publication is the moment to drop it, not carry it forward.
"""

from __future__ import annotations

import pytest

from omnidriver.cli import build_parser


def _parse(argv: list[str]):
    parser = build_parser()
    return parser.parse_args(argv)


def test_the_flag_sets_environment_bashrc() -> None:
    args = _parse(["plan", "--entry", "x", "--environment-bashrc", "/path/to/bashrc"])
    assert args.environment_bashrc == "/path/to/bashrc"


def test_no_flag_leaves_environment_bashrc_none() -> None:
    args = _parse(["plan", "--entry", "x"])
    assert args.environment_bashrc is None


def test_the_old_flag_name_is_no_longer_recognised() -> None:
    with pytest.raises(SystemExit):
        _parse(["plan", "--entry", "x", "--openfoam-bashrc", "/path/to/bashrc"])
