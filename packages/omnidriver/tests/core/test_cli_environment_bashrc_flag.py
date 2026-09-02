#----------------------------------------------------------------------------#
# License
#     This file is part of cardiacFoam.
#
#     cardiacFoam is free software: you can redistribute it and/or modify it
#     under the terms of the GNU General Public License as published by the
#     Free Software Foundation, either version 3 of the License, or (at your
#     option) any later version.
#
#     cardiacFoam is distributed in the hope that it will be useful, but
#     WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with cardiacFoam.  If not, see <http://www.gnu.org/licenses/>.
#
# Module
#     test_cli_environment_bashrc_flag
#
# Description
#     --openfoam-bashrc was renamed to --environment-bashrc (Tier 3,
#     future/ENVIRONMENT_CONTRACT.md #10) since the concept -- an
#     environment-sourcing script -- applies to any plugin, not just
#     OpenFOAM. The deprecated alias was removed outright rather than kept:
#     this codebase has no external callers to protect yet, so
#     pre-publication is the moment to drop it, not carry it forward.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

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
