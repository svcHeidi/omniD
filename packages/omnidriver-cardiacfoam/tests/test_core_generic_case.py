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
#     Proves core's generic-case factory (``omnidriver.core.runtime.
#     generic_case.make_spec``) still defaults to the legacy cardiac
#     mutation seam when a direct caller supplies no mutation callback.
#
#     Moved from core's ``tests/core/test_core_generic_case.py`` (Phase 2,
#     Milestone 3): this test's entire stated purpose is proving the
#     *cardiac* default fires when ``make_spec`` gets no callback -- swapping
#     the plugin would defeat the test. Its neutral counterpart,
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
    from omnidriver.core.runtime.generic_case import make_spec

    return make_spec(tutorials_root=tmp_path, case_dir_name="aCase", **kwargs)


def test_bare_make_spec_still_defaults_to_the_legacy_cardiac_mutation(
    tmp_path: Path,
) -> None:
    """The other half of the same contract: a direct make_spec caller with no
    callback keeps the historical behaviour via the named seam."""
    from omnidriver.core import compatibility

    case_root = tmp_path / "aCase"
    (case_root / "constant").mkdir(parents=True)
    (case_root / "constant" / "physicsProperties").write_text("type electroModel;\n")

    spec = _spec(tmp_path, dict_file_overrides={"physics": {"type": "electroMechanicalModel"}})
    with compatibility.track_fallback_calls() as calls:
        spec.apply_case(spec.case_root, spec.build_cases()[0])

    assert "legacy_generic_case_mutation" in calls
    assert "electroMechanicalModel" in (case_root / "constant" / "physicsProperties").read_text()
