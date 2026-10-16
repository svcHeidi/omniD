"""Manufactured-solution axes, resolved per record through the real cardiac stack.

``dimension`` differs per record (bidomain's solver has the key, eikonalECG's does not); ``numberCells`` patches the
blockMeshDicts' top-level ``N``, and a transient record derives ``deltaT`` and ``writeInterval`` as the native
``Allrun`` does, from the stated or staged ``N`` and ``endTime`` (the staged ``controlDict`` and ``blockMeshDict.3D``
are verbatim from cardiacFOAM #59's monodomainPseudoECG: ``endTime 0.2``, ``N 20``)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.core.tutorial_records import TutorialRecordError, resolve_case_patches
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin
from omnidriver.cardiacfoam.records.manufactured_solution_axes import (
    allrun_time_step, dimension_axis, tet_number_cells_axis,
)
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:manufactured-axes")


_FIXTURES = Path(__file__).parent / "fixtures" / "local_includes"


def _resolve(record_name: str, study: dict, tmp_path):
    record = _CTX.stack.call("get_tutorial_records")[record_name]
    (tmp_path / "system").mkdir(exist_ok=True)
    for name in ("controlDict", "blockMeshDict.3D"):
        shutil.copy(_FIXTURES / name, tmp_path / "system" / name)
    combined, command_arguments, _ = resolve_case_patches(
        record, study_by_source={"base": study}, staged_case_root=tmp_path,
        direct_key_validator=_CTX.stack.call("get_record_key_validator", driver_context=_CTX),
    )
    return {sourced.slot(): sourced.patch.value for sourced in combined}, command_arguments


def test_bidomain_dimension_writes_its_solver_coefficient_and_picks_the_mesh_dict(tmp_path):
    patches, command_arguments = _resolve("manufacturedBidomain", {"dimension": "1D"}, tmp_path)
    assert patches == {"constant/electroProperties::bidomainSolverCoeffs.dimension": '"1D"'}
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.1D")}


def test_eikonal_ecg_dimension_picks_the_mesh_dict_and_removes_the_3d_only_ecg(tmp_path):
    """eikonalECG's solver has no ``dimension`` key, so its axis must not borrow bidomain's; its ECG runs in 3D only."""
    patches, command_arguments = _resolve("manufacturedEikonalECG", {"dimension": "2D"}, tmp_path)
    assert patches == {"constant/electroProperties::eikonalSolverCoeffs.ecgDomains": None}
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.2D")}
    assert _resolve("manufacturedEikonalECG", {"dimension": "3D"}, tmp_path)[0] == {}


def test_pseudo_ecg_dimension_writes_both_the_tissue_and_ecg_verifier_dimension(tmp_path):
    """One study value drives both, so a study can never state one without the other."""
    patches, command_arguments = _resolve("manufacturedMonodomainPseudoECG", {"dimension": "3D"}, tmp_path)
    assert patches == {
        "constant/electroProperties::monodomainSolverCoeffs.dimension": '"3D"',
        "constant/electroProperties::monodomainSolverCoeffs.ecgDomains.ECG"
        ".verificationModel.dimension": '"3D"',
    }
    assert command_arguments == {"mesh": ("-dict", "system/blockMeshDict.3D")}


def test_a_1d_pseudo_ecg_removes_the_ecg_with_every_study_key_beneath_it(tmp_path):
    """The native Allrun writes ``#remove ecgDomains`` below everything else the case sets, for 1D and 2D."""
    study = {
        "dimension": "1D",
        "constant/electroProperties:monodomainSolverCoeffs.ecgDomains.ECG.verificationModel.anisotropic": False,
    }
    patches, _ = _resolve("manufacturedMonodomainPseudoECG", study, tmp_path)
    assert patches == {
        "constant/electroProperties::monodomainSolverCoeffs.dimension": '"1D"',
        "constant/electroProperties::monodomainSolverCoeffs.ecgDomains": None,
    }


@pytest.mark.parametrize(
    "record_name",
    ["manufacturedBidomain", "manufacturedEikonalECG", "manufacturedMonodomainPseudoECG"],
)
def test_tet_number_cells_passes_lc_as_one_over_n(record_name, tmp_path):
    patches, command_arguments = _resolve(record_name, {"tetNumberCells": 20}, tmp_path)
    assert patches == ({} if record_name == "manufacturedEikonalECG" else {"system/controlDict::deltaT": 0.2 / 90})
    assert command_arguments == {"gmsh": ("-setnumber", "lc", "0.05")}


@pytest.mark.parametrize(("n", "steps"), [(10, 23), (20, 90), (40, 359), (80, 1434)])
def test_the_time_step_is_the_allruns(n, steps):
    """``endTime/ceil(endTime/(0.00892857*(10/N)^2))``, as the native Allrun's awk computes it for endTime 0.2."""
    assert allrun_time_step(n, 0.2, 0.00892857) == 0.2 / steps


@pytest.mark.parametrize("record_name", ["manufacturedBidomain", "manufacturedMonodomainPseudoECG", "manufacturedBathBidomain"])
def test_number_cells_sets_n_in_every_dimension_and_derives_the_time_step(record_name, tmp_path):
    patches, command_arguments = _resolve(record_name, {"numberCells": 40}, tmp_path)
    assert patches == {
        "system/blockMeshDict.1D::N": 40, "system/blockMeshDict.2D::N": 40, "system/blockMeshDict.3D::N": 40,
        "system/controlDict::deltaT": 0.2 / 359,
    }
    assert command_arguments == {}


def test_a_steady_case_derives_no_time_step(tmp_path):
    patches, _ = _resolve("manufacturedEikonalECG", {"numberCells": 40}, tmp_path)
    assert "system/controlDict::deltaT" not in patches


def test_a_study_time_step_replaces_the_derived_one(tmp_path):
    patches, _ = _resolve("manufacturedBidomain", {"numberCells": 40, "system/controlDict:deltaT": 0.0001}, tmp_path)
    assert patches["system/controlDict::deltaT"] == 0.0001


def test_a_study_end_time_derives_the_step_and_the_write_interval_as_allrun_minus_end_time_does(tmp_path):
    """``Allrun -endTime 0.05`` at the case's N = 20: 0.05/ceil(0.05/0.0022321425) = 0.05/23, writing at 0.05."""
    patches, _ = _resolve("manufacturedBidomain", {"system/controlDict:endTime": 0.05}, tmp_path)
    assert patches["system/controlDict::deltaT"] == 0.05 / 23
    assert patches["system/controlDict::writeInterval"] == 0.05
    patches, _ = _resolve("manufacturedBidomain", {"numberCells": 40, "system/controlDict:endTime": 0.05}, tmp_path)
    assert patches["system/controlDict::deltaT"] == allrun_time_step(40, 0.05, 0.00892857)
    patches, _ = _resolve(
        "manufacturedBidomain",
        {"numberCells": 40, "system/controlDict:endTime": 0.02, "system/controlDict:deltaT": 0.0005}, tmp_path,
    )
    assert (patches["system/controlDict::deltaT"], patches["system/controlDict::writeInterval"]) == (0.0005, 0.02)


def test_one_study_names_one_n(tmp_path):
    with pytest.raises(TutorialRecordError, match="are one Allrun -N"):
        _resolve("manufacturedBidomain", {"numberCells": 40, "tetNumberCells": 20}, tmp_path)


def test_the_dimension_axis_refuses_a_dimension_by_name(tmp_path):
    axis = dimension_axis("dimension")
    with pytest.raises(ValueError, match=r"dimension axis 'dimension': '4D' is not one of"):
        axis.resolve("4D", tmp_path)


@pytest.mark.parametrize("value", [0, -3, True])
def test_the_tet_axis_declares_only_a_positive_cell_count(value):
    """Core refuses what the declaration rules out before ``resolve`` runs."""
    from omnidriver.core.contracts.dictionary import bound_violations, numeric_bounds, validate_value_shape

    axis = tet_number_cells_axis("tetNumberCells")
    assert validate_value_shape(axis.value_kind, value) or bound_violations(numeric_bounds(axis), value)


def test_a_record_refuses_an_axis_only_another_record_declares():
    """``ionicModel`` is restitutionCurves' axis; bidomain refuses it by name rather than borrowing it."""
    from omnidriver.core.tutorial_records import sort_study_name

    catalog = _CTX.stack.call("get_tutorial_records")
    assert "ionicModel" in catalog["restitutionCurves"].axis_names()
    with pytest.raises(TutorialRecordError, match="ionicModel"):
        sort_study_name("ionicModel", axes=catalog["manufacturedBidomain"].axes)


#: eikonalECG's ``dimension`` axis writes no document key: the mesh step's
#: ``-dict`` is its whole effect, so a route that never runs ``blockMesh``
#: refuses it. The other records' axis also writes the solver's ``dimension``,
#: which a tet study states.
_EIKONAL_TET_ROUTES = [
    ("manufacturedEikonalECG", "tet"),
    ("manufacturedEikonalECG", "tet-errorLocalisation"),
]
_TET_ROUTES_WRITING_DIMENSION = [
    ("manufacturedBidomain", "tet"),
    ("manufacturedBathBidomain", "tet"),
    ("manufacturedMonodomainPseudoECG", "tet"),
]


def _resolve_on_route(record_name: str, variant: str, study: dict, tmp_path):
    record = _CTX.stack.call("get_tutorial_records")[record_name]
    return resolve_case_patches(
        record, study_by_source={"base": study}, staged_case_root=tmp_path,
        direct_key_validator=_CTX.stack.call("get_record_key_validator", driver_context=_CTX),
        workflow_step_ids=record.workflow_variants[variant],
    )


@pytest.mark.parametrize(("record_name", "variant"), _EIKONAL_TET_ROUTES)
def test_a_tet_route_refuses_an_axis_whose_only_effect_is_the_blockmesh_dict(record_name, variant, tmp_path):
    """In 3D; in 1D and 2D the axis also removes the ECG."""
    with pytest.raises(TutorialRecordError) as exc:
        _resolve_on_route(record_name, variant, {"dimension": "3D"}, tmp_path)
    for fragment in (record_name, "'dimension'", "'mesh'", "does not run"):
        assert fragment in str(exc.value), (fragment, str(exc.value))


@pytest.mark.parametrize(("record_name", "variant"), _TET_ROUTES_WRITING_DIMENSION)
def test_a_tet_study_may_state_the_solvers_dimension(record_name, variant, tmp_path):
    patches, *_ = _resolve_on_route(record_name, variant, {"dimension": "3D"}, tmp_path)
    assert any(sourced.patch.key_path[-1] == "dimension" for sourced in patches)


@pytest.mark.parametrize("record_name", [
    "manufacturedBidomain", "manufacturedEikonalECG", "manufacturedMonodomainPseudoECG",
])
@pytest.mark.parametrize("dimension", ["1D", "2D", "3D"])
def test_the_hex_route_admits_every_dimension(record_name, dimension, tmp_path):
    _resolve_on_route(record_name, "hex", {"dimension": dimension}, tmp_path)


def _records_with_a_gmsh_step():
    for record in _CTX.stack.call("get_tutorial_records").values():
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
    record = _CTX.stack.call("get_tutorial_records")[record_name]
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


def test_every_axis_of_every_record_says_what_it_sets_and_the_niederer_lengths_are_metres():
    records = _CTX.stack.call("get_tutorial_records")
    for record in records.values():
        for axis in record.axes:
            assert axis.description.strip(), (record.name, axis.name)
    niederer = {axis.name: axis.to_json() for axis in records["niederer2011"].axes}
    for name in ("dx", "tetDx"):
        assert (niederer[name]["unit"], niederer[name]["exclusive_minimum"]) == ("m", 0)
