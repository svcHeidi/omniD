"""The environment-sourcing flag is --environment-source, opaque to core. --openfoam-bashrc and --environment-bashrc are refused, not aliased."""

from __future__ import annotations

import pytest

from omnidriver.cli import build_parser


def _parse(argv: list[str]):
    return build_parser().parse_args(argv)


def test_the_flag_sets_environment_source() -> None:
    args = _parse(["plan", "--entry", "x", "--environment-source", "anything the plugin reads"])
    assert args.environment_source == "anything the plugin reads"


def test_no_flag_leaves_environment_source_none() -> None:
    assert _parse(["plan", "--entry", "x"]).environment_source is None


@pytest.mark.parametrize("old", ["--environment-bashrc", "--openfoam-bashrc"])
def test_the_old_flag_names_are_not_recognised(old: str) -> None:
    with pytest.raises(SystemExit):
        _parse(["plan", "--entry", "x", old, "/path/to/bashrc"])
