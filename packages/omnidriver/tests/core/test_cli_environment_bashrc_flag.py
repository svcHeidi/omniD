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
#     OpenFOAM. The old flag is kept working as a deprecated alias. These
#     tests exercise the argparse layer directly, so they need no monorepo
#     tutorials tree (unlike the end-to-end subprocess coverage in
#     test_strict_plan_contract.py, which still uses --openfoam-bashrc on
#     purpose -- that IS the deprecated-alias regression test).
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from omnidriver.cli import _resolve_environment_bashrc, build_parser


def _parse(argv: list[str]):
    parser = build_parser()
    args = parser.parse_args(argv)
    _resolve_environment_bashrc(args)
    return args


def test_the_new_flag_sets_environment_bashrc() -> None:
    args = _parse(["plan", "--entry", "x", "--environment-bashrc", "/path/to/bashrc"])
    assert args.environment_bashrc == "/path/to/bashrc"


def test_the_deprecated_flag_still_sets_environment_bashrc() -> None:
    args = _parse(["plan", "--entry", "x", "--openfoam-bashrc", "/path/to/bashrc"])
    assert args.environment_bashrc == "/path/to/bashrc"


def test_the_deprecated_flag_prints_a_warning(capsys) -> None:
    _parse(["plan", "--entry", "x", "--openfoam-bashrc", "/path/to/bashrc"])
    assert "deprecated" in capsys.readouterr().err


def test_the_new_flag_prints_no_warning(capsys) -> None:
    _parse(["plan", "--entry", "x", "--environment-bashrc", "/path/to/bashrc"])
    assert capsys.readouterr().err == ""


def test_neither_flag_leaves_environment_bashrc_none() -> None:
    args = _parse(["plan", "--entry", "x"])
    assert args.environment_bashrc is None


def test_the_new_flag_wins_when_both_are_given() -> None:
    args = _parse([
        "plan", "--entry", "x",
        "--environment-bashrc", "/new/bashrc",
        "--openfoam-bashrc", "/old/bashrc",
    ])
    assert args.environment_bashrc == "/new/bashrc"
