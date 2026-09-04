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
#     Proves cardiacFoam's generic-case factory still applies the cardiac
#     dictionary mutation, and still addresses electroProperties/
#     physicsProperties, now that neither default lives in core.
#
#     Moved from core's ``tests/core/test_core_generic_case.py`` (Phase 2,
#     Milestone 3), where it proved the *opposite* arrangement: that core's
#     own make_spec defaulted to the cardiac mutation seam when a direct
#     caller supplied no callback. Core no longer has that default -- it
#     imported omnidriver.cardiacfoam to honour it, the last runtime cardiac
#     import in the package. The observable behaviour is unchanged and is
#     asserted here against the plugin's wrapper, which is what supplies both
#     defaults now. Its neutral counterpart,
#     ``test_make_generic_case_spec_applies_no_solver_mutation``, stays in
#     core and proves the dedicated generic entry point never reaches into a
#     plugin's mutator.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

from __future__ import annotations

from pathlib import Path


def _spec(tmp_path: Path, **kwargs):
    from omnidriver.cardiacfoam.tutorials.generic_case import make_spec

    return make_spec(cases_root=tmp_path, case_dir_name="aCase", **kwargs)


def test_bare_make_spec_still_applies_the_cardiac_mutation(tmp_path: Path) -> None:
    """Same observable behaviour as before, supplied by the plugin.

    A caller who names no mutation callback still gets the cardiac one, and
    the file it writes is unchanged. What changed is who supplies it: core
    used to import omnidriver.cardiacfoam to do this. The assertion that no
    compatibility fallback fires at all is the half that would have failed
    before -- it went through legacy_generic_case_mutation.
    """
    from omnidriver.core import compatibility

    case_root = tmp_path / "aCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")

    spec = _spec(tmp_path, dict_file_overrides={"physics": {"type": "electroMechanicalModel"}})
    with compatibility.track_fallback_calls() as calls:
        spec.apply_case(spec.case_root, spec.build_cases()[0])

    assert calls == []
    assert "electroMechanicalModel" in (case_root / "constant" / "physicsProperties").read_text()


def test_the_cardiac_dict_file_relpaths_default_comes_from_the_plugin(
    tmp_path: Path,
) -> None:
    """The electroProperties/physicsProperties pair core used to hardcode.

    Core's make_spec now defaults to no dictionary files at all, so a folder
    with neither file is generic to it. This wrapper restores the historical
    pair -- same values, same insertion order, so electroProperties stays the
    primary marker that makes a folder non-generic.
    """
    assert _spec(tmp_path).metadata["dict_file_relpaths"] == {
        "electro": "constant/electroProperties",
        "physics": "constant/physicsProperties",
    }

    (tmp_path / "aCase" / "constant").mkdir(parents=True)
    (tmp_path / "aCase" / "constant" / "electroProperties").write_text("")
    assert _spec(tmp_path).metadata["generic_case"] is False
