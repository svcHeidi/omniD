"""Manufactured-solution axes, resolved per record through the real cardiac stack.

``dimension`` differs per record (bidomain's solver has the key, eikonalECG's does not); the hex ``numberCells`` axis reads real blockMeshDicts, so native conformance checks it."""

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
    """eikonalECG's solver has no ``dimension`` key, so its axis writes nothing and must not borrow bidomain's."""
    patches, command_arguments = _resolve("manufacturedEikonalECG", {"dimension": "2D"}, tmp_path)
    assert patches == {}
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.2D")}


def test_pseudo_ecg_dimension_writes_both_the_tissue_and_ecg_verifier_dimension(tmp_path):
    """One study value drives both, so a study can never state one without the other."""
    patches, command_arguments = _resolve("manufacturedMonodomainPseudoECG", {"dimension": "1D"}, tmp_path)
    assert patches == {
        "constant/electroProperties::monodomainSolverCoeffs.dimension": '"1D"',
        "constant/electroProperties::monodomainSolverCoeffs.ecgDomains.ECG"
        ".verificationModel.dimension": '"1D"',
    }
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.1D")}


@pytest.mark.parametrize(
    "record_name",
    ["manufacturedBidomain", "manufacturedEikonalECG", "manufacturedMonodomainPseudoECG"],
)
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


def test_a_record_refuses_an_axis_only_another_record_declares():
    """``ionicModel`` is restitutionCurves' axis; bidomain refuses it by name rather than borrowing it."""
    from omnidriver.core.tutorial_records import sort_study_name

    catalog = _CTX.capabilities.tutorial_records.catalog()
    assert "ionicModel" in catalog["restitutionCurves"].axis_names()
    with pytest.raises(TutorialRecordError, match="ionicModel"):
        sort_study_name("ionicModel", axes=catalog["manufacturedBidomain"].axes)


#: Every tet route of every record that has a ``dimension`` axis; the
#: unit-cube tet mesh has no 1D/2D variant.
_TET_ROUTES = [
    ("manufacturedBidomain", "tet"),
    ("manufacturedEikonalECG", "tet"),
    ("manufacturedEikonalECG", "tet-errorLocalisation"),
    ("manufacturedEikonalECG", "tet-gradientReconstruction"),
    ("manufacturedMonodomainPseudoECG", "tet"),
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


@pytest.mark.parametrize(
    "record_name",
    ["manufacturedBidomain", "manufacturedEikonalECG", "manufacturedMonodomainPseudoECG"],
)
@pytest.mark.parametrize("dimension", ["1D", "2D", "3D"])
def test_the_hex_route_admits_every_dimension(record_name, dimension):
    from omnidriver.core.tutorial_records import check_variant_constraints

    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    check_variant_constraints(record, "hex", {"base": {"dimension": dimension}})


def test_every_route_that_skips_the_mesh_step_constrains_dimension():
    """``dimension`` picks the blockMesh dict, so a route without ``mesh`` must admit only its template's 3D."""
    for record in _CTX.capabilities.tutorial_records.catalog().values():
        if "dimension" not in record.axis_names():
            continue
        for variant, steps in record.workflow_variants.items():
            if "mesh" in steps:
                continue
            assert record.variant_constraints.get(variant, {}).get("dimension") == ("3D",), (
                record.name, variant,
            )


def _records_with_a_gmsh_step():
    for record in _CTX.capabilities.tutorial_records.catalog().values():
        steps = {step.step_id: step for step in record.workflow_steps}
        if "gmsh" in steps:
            yield record, steps


def test_no_gmsh_step_restates_its_templates_lc_default():
    """With no study value gmsh runs without ``-setnumber``, so the template's own DefineConstant default applies."""
    records = list(_records_with_a_gmsh_step())
    assert {record.name for record, _ in records} >= {
        "manufacturedBidomain", "manufacturedEikonalECG", "niederer2011",
    }
    for record, steps in records:
        assert steps["gmsh"].default_arguments == (), record.name
        assert "-setnumber" not in steps["gmsh"].argv(()), record.name


@pytest.mark.parametrize(("record_name", "study", "lc"), [
    ("manufacturedBidomain", {"tetNumberCells": 20}, "0.05"),
    ("manufacturedEikonalECG", {"tetNumberCells": 20}, "0.05"),
    ("manufacturedMonodomainPseudoECG", {"tetNumberCells": 20}, "0.05"),
    ("niederer2011", {"tetDx": 0.0002}, "0.0002"),
])
def test_a_tet_axis_adds_lc_to_the_gmsh_command_line(record_name, study, lc, tmp_path):
    record = _CTX.capabilities.tutorial_records.catalog()[record_name]
    _, command_arguments = _resolve(record_name, study, tmp_path)
    gmsh = next(step for step in record.workflow_steps if step.step_id == "gmsh")
    argv = gmsh.argv(command_arguments["gmsh"])
    assert argv[-3:] == ("-setnumber", "lc", lc)
    assert argv.count("-setnumber") == 1


def test_every_gmsh_route_hands_its_mesh_file_from_gmsh_to_gmsh_to_foam():
    """The file gmsh writes (its ``-o`` argument) is what gmshToFoam consumes, declared on both sides."""
    for record, steps in _records_with_a_gmsh_step():
        gmsh, to_foam = steps["gmsh"], steps["gmshToFoam"]
        msh = gmsh.command[gmsh.command.index("-o") + 1]
        assert msh in gmsh.produces, record.name
        assert msh in to_foam.consumes, record.name
        assert to_foam.command == ("gmshToFoam", msh), record.name


def test_every_gmsh_to_foam_step_declares_the_zone_files_it_writes():
    """A real gmshToFoam writes three zone files and a cell set beyond the hex six (see docs/solver-learning/cardiacfoam.md)."""
    for record, steps in _records_with_a_gmsh_step():
        produced = set(steps["gmshToFoam"].produces)
        assert {
            "constant/polyMesh/cellZones", "constant/polyMesh/faceZones",
            "constant/polyMesh/pointZones",
        } <= produced, record.name
        # One cell set per Physical Volume; its name is the template's own
        # (`internal` for these three, others for a multi-volume template).
        assert any(path.startswith("constant/polyMesh/sets/") for path in produced), record.name
