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
#     test_sweep_routing
#
# Description
#     Tests routing of resolved sweep values to build_and_launch parameters.
#
# Author
#     Simao Nieto de Castro, UCD.
#----------------------------------------------------------------------------#

import pytest

from omnidriver.core.sweep.sweep_expansion import SweepValidationError
from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.sweep_routing import route_case_values

# Supplied, not discovered: the ambient default is ambiguous once a second adapter is installed.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:sweep_routing")


def test_selector_keys_route_to_electro_selectors():
    routed = route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"ionicModel": "TNNP", "tissue": "epicardialCells"})
    assert routed["electro_selectors"] == {"ionicModel": "TNNP", "tissue": "epicardialCells"}
    assert routed["electro_overrides"] == {}


def test_type_routes_to_physics_selectors():
    routed = route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"type": "electroModel"})
    assert routed["physics_selectors"] == {"type": "electroModel"}


def test_delta_t_and_end_time_route_to_dedicated_kwargs():
    routed = route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"deltaT": 1e-6, "endTime": 0.5})
    assert routed["delta_t"] == 1e-6
    assert routed["end_time"] == 0.5


def test_other_keys_route_to_electro_overrides():
    routed = route_case_values(
        driver_context=_CTX,
        base={},
        resolved_axis_values={"$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude": "80"},
    )
    assert routed["electro_overrides"] == {"$ELECTRO_MODEL_COEFFS.singleCellStimulus.stim_amplitude": "80"}


def test_base_selectors_are_preserved_and_extended():
    routed = route_case_values(
        driver_context=_CTX,
        base={"electro_selectors": {"myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells"},
              "physics_selectors": {"type": "electroModel"}},
        resolved_axis_values={"ionicModel": "TNNP"},
    )
    assert routed["electro_selectors"] == {
        "myocardiumSolver": "singleCellSolver", "tissue": "epicardialCells", "ionicModel": "TNNP",
    }
    assert routed["physics_selectors"] == {"type": "electroModel"}


def test_derived_extra_keys_do_not_break_routing():
    # caseId is a bookkeeping value the expander adds; it must not be routed anywhere.
    routed = route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"ionicModel": "TNNP", "caseId": "TNNP-label"})
    assert "caseId" not in routed["electro_selectors"]
    assert "caseId" not in routed["electro_overrides"]


def test_unsupported_control_dict_axis_is_rejected():
    # build_and_launch exposes only delta_t/end_time; other controlDict entries must not become electro overrides.
    with pytest.raises(SweepValidationError, match="startTime|controlDict"):
        route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"startTime": 0.0})


def test_unrecognized_axis_is_rejected_instead_of_silently_ignored():
    # Falling through to electro_overrides would make an unknown key a silent no-op.
    with pytest.raises(SweepValidationError, match="bogusAxis"):
        route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"bogusAxis": 0.5})


def test_dx_routes_to_its_own_dedicated_kwarg():
    # dx sizes the default blockMeshDict and is not a catalog driver_path.
    routed = route_case_values(driver_context=_CTX, base={}, resolved_axis_values={"dx": 0.2})
    assert routed["dx"] == 0.2


def test_dx_base_value_is_preserved_when_not_swept():
    routed = route_case_values(driver_context=_CTX, base={"dx": 0.5}, resolved_axis_values={"ionicModel": "TNNP"})
    assert routed["dx"] == 0.5


def test_cellzone_routes_under_the_solver_coeffs_prefix():
    """cellZone is read from the resolved <solver>Coeffs block (myocardiumDomain.C), not the electroProperties root."""
    routed = route_case_values(
        driver_context=_CTX,
        base={},
        resolved_axis_values={"$ELECTRO_MODEL_COEFFS.cellZone": "epicardium"},
    )
    assert routed["electro_overrides"] == {
        "$ELECTRO_MODEL_COEFFS.cellZone": "epicardium"
    }


def test_bare_cellzone_axis_still_routes_as_a_backward_compatible_alias():
    """Catalog matching is prefix-agnostic, so the bare spelling still routes."""
    routed = route_case_values(
        driver_context=_CTX, base={}, resolved_axis_values={"cellZone": "epicardium"},
    )
    assert routed["electro_overrides"] == {"cellZone": "epicardium"}


def test_cellzone_override_lands_inside_the_solver_coeffs_block():
    """At the root, ``found("cellZone")`` is false and the run silently uses the whole mesh, bath included."""
    from omnidriver.cardiacfoam.dict_builder import build_electro_properties

    text = build_electro_properties(
        selectors={
            "myocardiumSolver": "monodomainSolver",
            "ionicModel": "TNNP",
            "tissue": "epicardialCells",
        },
        overrides={"$ELECTRO_MODEL_COEFFS.cellZone": "myocardium"},
    )
    coeffs_at = text.index("monodomainSolverCoeffs")
    zone_at = text.index("cellZone")
    assert zone_at > coeffs_at, (
        "cellZone was emitted before the coeffs block -- i.e. at the "
        "electroProperties root, where the solver never reads it:\n" + text[:400]
    )
