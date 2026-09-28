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
#     test_core_generic_case
#
# Description
#     Proves cardiacFoam's generic-case factory applies the cardiac
#     dictionary mutation and addresses electroProperties/physicsProperties
#     by default; core supplies neither default.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path


def _spec(tmp_path: Path, **kwargs):
    from omnidriver.cardiacfoam.generic_case import make_spec

    return make_spec(cases_root=tmp_path, case_dir_name="aCase", **kwargs)


def test_bare_make_spec_still_applies_the_cardiac_mutation(tmp_path: Path) -> None:
    """A caller naming no mutation callback gets the cardiac one, and no compatibility fallback fires."""
    from omnidriver.core import compatibility

    case_root = tmp_path / "aCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")

    spec = _spec(tmp_path, dict_file_overrides={"physics": {"type": "electroMechanicalModel"}})
    with compatibility.track_fallback_calls() as calls:
        spec.case_mutation(spec.case_root)

    assert calls == []
    assert "electroMechanicalModel" in (case_root / "constant" / "physicsProperties").read_text()


def test_the_cardiac_dict_file_relpaths_default_comes_from_the_plugin(
    tmp_path: Path,
) -> None:
    """Insertion order keeps electroProperties the primary marker that makes a folder non-generic."""
    assert _spec(tmp_path).metadata["dict_file_relpaths"] == {
        "electro": "constant/electroProperties",
        "physics": "constant/physicsProperties",
    }

    (tmp_path / "aCase" / "constant").mkdir(parents=True)
    (tmp_path / "aCase" / "constant" / "electroProperties").write_text("")
    assert _spec(tmp_path).metadata["generic_case"] is False
