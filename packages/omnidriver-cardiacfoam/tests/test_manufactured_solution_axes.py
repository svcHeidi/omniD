"""The manufactured-solution axes, one builder for every record that uses
them (``records/manufactured_solution_axes.py``), and record-scoped
resolution through the real cardiac stack (2026-09-26).

``manufacturedBidomain`` and ``manufacturedEikonalECG`` both declare
``dimension``, and the two mean different things: bidomain's native
``bidomainSolverCoeffs`` has a ``dimension`` key, eikonalECG's
``eikonalSolverCoeffs`` does not. With one stack-wide axis catalog the
record registered last won, and a 1D bidomain case kept ``dimension "3D"``.
These tests resolve each record's own axes through core, from the records
the composed stack itself registers.

The ``dimension`` and ``tetNumberCells`` axes read nothing from the staged
case, so an empty staged directory is enough: no geometry is invented here.
The hex ``numberCells`` axis reads each ``blockMeshDict.<dim>``; it is
checked against the real native case by the before/after ``sweep-plan``
comparison and the native conformance suite, not here.
"""

from __future__ import annotations

import pytest

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.tutorial_records import TutorialRecordError, resolve_case_patches
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.records.manufactured_solution_axes import (
    dimension_axis, tet_number_cells_axis,
)
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:manufactured-axes")


def _resolve(record_name: str, study: dict, tmp_path):
    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    combined, command_arguments = resolve_case_patches(
        record, study_by_source={"base": study}, staged_case_root=tmp_path,
        direct_key_validator=_CTX.capabilities.record_key_validation.validator(),
    )
    return {sourced.slot(): sourced.patch.value for sourced in combined}, command_arguments


def test_bidomain_dimension_writes_its_solver_coefficient_and_picks_the_mesh_dict(tmp_path):
    patches, command_arguments = _resolve("manufacturedBidomain", {"dimension": "1D"}, tmp_path)
    assert patches == {"constant/electroProperties::bidomainSolverCoeffs.dimension": '"1D"'}
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.1D")}


def test_eikonal_ecg_dimension_only_picks_the_mesh_dict(tmp_path):
    """eikonalECG's solver has no ``dimension`` key: its axis of the same
    name writes nothing, and resolving it must not borrow bidomain's."""
    patches, command_arguments = _resolve("manufacturedEikonalECG", {"dimension": "2D"}, tmp_path)
    assert patches == {}
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.2D")}


@pytest.mark.parametrize("record_name", ["manufacturedBidomain", "manufacturedEikonalECG"])
def test_tet_number_cells_passes_lc_as_one_over_n(record_name, tmp_path):
    patches, command_arguments = _resolve(record_name, {"tetNumberCells": 20}, tmp_path)
    assert patches == {}
    assert command_arguments == {"gmsh": ("-setnumber", "lc", "0.05")}


def test_the_dimension_axis_refuses_a_dimension_by_name(tmp_path):
    axis = dimension_axis("dimension")
    with pytest.raises(ValueError, match=r"dimension axis 'dimension': '4D' is not one of"):
        axis.resolve("4D", tmp_path)


@pytest.mark.parametrize("value", [0, -3, True])
def test_the_tet_axis_refuses_a_cell_count_that_is_not_positive(value, tmp_path):
    axis = tet_number_cells_axis("tetNumberCells")
    with pytest.raises(ValueError, match="N must be a positive integer"):
        axis.resolve(value, tmp_path)


def test_every_cardiac_record_resolves_each_of_its_axis_names_to_its_own_contract():
    """Every record the cardiac stack registers: each bare axis name a study
    may use resolves, through core, to that record's own contract. The
    one-name-one-contract rule itself is ``TutorialRecord``'s, at load."""
    from omnidriver.core.tutorial_records import sort_study_name

    for record in _CTX.capabilities.tutorial_records.catalog().values():
        for axis in record.axes:
            assert sort_study_name(axis.name, axes=record.axes).axis is axis
    with pytest.raises(TutorialRecordError, match="ionicModel"):
        sort_study_name(
            "ionicModel", axes=_CTX.capabilities.tutorial_records.catalog()["manufacturedBidomain"].axes,
        )


#: Every tet route of every record that has a ``dimension`` axis. The old
#: pseudo-ECG and eikonalECG ``make_spec`` refused ``mesh_family='tet'``
#: with any dimension but ``3D`` ("the unit-cube tet mesh has no 1D/2D
#: variant"); review 54b I3 found the records had lost that refusal.
_TET_ROUTES = [
    ("manufacturedBidomain", "tet"),
    ("manufacturedEikonalECG", "tet"),
    ("manufacturedEikonalECG", "tet-errorLocalisation"),
    ("manufacturedEikonalECG", "tet-gradientReconstruction"),
]


@pytest.mark.parametrize(("record_name", "variant"), _TET_ROUTES)
@pytest.mark.parametrize("dimension", ["1D", "2D"])
def test_a_tet_route_refuses_a_dimension_its_3d_template_cannot_build(record_name, variant, dimension):
    from omnidriver.core.tutorial_records import check_variant_constraints

    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    with pytest.raises(TutorialRecordError) as exc:
        check_variant_constraints(record, variant, {"base": {"dimension": dimension}})
    for fragment in (record_name, repr(variant), "'dimension'", "'3D'", repr(dimension)):
        assert fragment in str(exc.value), (fragment, str(exc.value))


@pytest.mark.parametrize(("record_name", "variant"), _TET_ROUTES)
def test_a_tet_route_admits_3d_or_no_dimension(record_name, variant):
    from omnidriver.core.tutorial_records import check_variant_constraints

    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    check_variant_constraints(record, variant, {"base": {"dimension": "3D"}})
    check_variant_constraints(record, variant, {"base": {}})


@pytest.mark.parametrize("record_name", ["manufacturedBidomain", "manufacturedEikonalECG"])
@pytest.mark.parametrize("dimension", ["1D", "2D", "3D"])
def test_the_hex_route_admits_every_dimension(record_name, dimension):
    from omnidriver.core.tutorial_records import check_variant_constraints

    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    check_variant_constraints(record, "hex", {"base": {"dimension": dimension}})


def test_every_route_that_skips_the_mesh_step_constrains_dimension():
    """The relation behind the constraint, checked for every record the
    stack registers, so a new tet route (bath, pseudo-ECG) cannot forget it:
    ``dimension`` chooses the blockMesh dictionary, so a route without the
    ``mesh`` step builds its own geometry, and must admit only the one its
    template builds."""
    for record in _CTX.capabilities.tutorial_records.catalog().values():
        if "dimension" not in record.axis_names():
            continue
        for variant, steps in record.workflow_variants.items():
            if "mesh" in steps:
                continue
            assert record.variant_constraints.get(variant, {}).get("dimension") == ("3D",), (
                record.name, variant,
            )
