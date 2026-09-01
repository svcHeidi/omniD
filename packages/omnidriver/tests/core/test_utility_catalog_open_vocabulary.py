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
#     test_utility_catalog_open_vocabulary
#
# Description
#     format/argument_kind in utility.manifest.toml are no longer validated
#     against a closed, OpenFOAM-shaped set (Tier 3,
#     future/ENVIRONMENT_CONTRACT.md #10) -- only structural validity
#     (non-empty string) is checked. A plugin's own vocabulary
#     (e.g. a FEniCS utility's "xdmf_sequence") must load without core
#     objecting, while a malformed entry must still fail loudly.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.utility_catalog import (
    _parse_flag,
    _parse_positional_arg,
    _parse_produces_entry,
)

_MANIFEST_PATH = Path("test.manifest.toml")


def test_a_format_string_core_has_never_heard_of_loads_fine() -> None:
    entry = _parse_produces_entry(
        {"artifact_id": "a", "path_pattern": "p", "format": "xdmf_sequence"},
        _MANIFEST_PATH,
    )
    assert entry.format == "xdmf_sequence"


def test_an_empty_format_string_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        _parse_produces_entry(
            {"artifact_id": "a", "path_pattern": "p", "format": ""},
            _MANIFEST_PATH,
        )


def test_a_non_string_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        _parse_produces_entry(
            {"artifact_id": "a", "path_pattern": "p", "format": 7},
            _MANIFEST_PATH,
        )


def test_an_argument_kind_core_has_never_heard_of_loads_fine() -> None:
    arg = _parse_positional_arg(
        {"name": "mesh_file", "argument_kind": "dolfin_mesh", "description": "d"},
        _MANIFEST_PATH,
    )
    assert arg.argument_kind == "dolfin_mesh"


def test_an_empty_positional_argument_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        _parse_positional_arg(
            {"name": "mesh_file", "argument_kind": "", "description": "d"},
            _MANIFEST_PATH,
        )


def test_a_flag_argument_kind_core_has_never_heard_of_loads_fine() -> None:
    flag = _parse_flag(
        {"name": "-scale", "description": "d", "argument_kind": "dolfin_mesh"},
        _MANIFEST_PATH,
    )
    assert flag.argument_kind == "dolfin_mesh"


def test_a_flag_with_no_argument_kind_still_defaults_to_empty() -> None:
    flag = _parse_flag({"name": "-scale", "description": "d"}, _MANIFEST_PATH)
    assert flag.argument_kind == ""


def test_a_non_string_flag_argument_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-string"):
        _parse_flag(
            {"name": "-scale", "description": "d", "argument_kind": 7},
            _MANIFEST_PATH,
        )
