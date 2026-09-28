"""Non-native tests of every ``physics_layout`` refusal path.

Fixtures are tiny synthetic dictionaries exercising this module's own parsing,
not claims about solver behaviour.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.cardiacfoam.physics_layout import (
    PhysicsLayoutError,
    physics_type,
    region_document,
    region_of,
)
from omnidriver.cardiacfoam.planning_policy import is_nondimensional_case
from omnidriver.core.tutorial_records import TutorialRecordError


class _Spec:
    def __init__(self, case_root: Path) -> None:
        self.case_root = case_root


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_physics_layout_error_is_a_tutorial_record_error(tmp_path):
    """So an unknown physics type reaches ``plan --strict``'s refusal handling, not a traceback."""
    assert issubclass(PhysicsLayoutError, TutorialRecordError)


def test_an_unknown_physics_type_is_refused_by_name(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type fsiModel;\n")
    with pytest.raises(PhysicsLayoutError, match="fsiModel"):
        region_of(tmp_path, "electro")


def test_a_physics_properties_without_a_type_key_is_refused_by_name(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "notType electroModel;\n")
    with pytest.raises(PhysicsLayoutError, match="type"):
        physics_type(tmp_path)


def test_a_missing_coupling_document_is_refused_by_name(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type electroMechanicalModel;\n")
    with pytest.raises(PhysicsLayoutError, match="electroMechanicalProperties"):
        region_of(tmp_path, "electro")


def test_a_malformed_coupling_document_is_refused_by_name(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type electroMechanicalModel;\n")
    _write(
        tmp_path / "constant" / "electroMechanicalProperties",
        "electroMechanicalModel sequentialElectroMechanical;\n",
    )
    with pytest.raises(PhysicsLayoutError, match="electroMechanicalProperties"):
        region_of(tmp_path, "electro")


def test_an_unknown_role_is_refused_for_a_region_split_type(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type electroMechanicalModel;\n")
    _write(
        tmp_path / "constant" / "electroMechanicalProperties",
        "\n".join([
            "electroMechanicalModel sequentialElectroMechanical;",
            "sequentialElectroMechanicalCoeffs",
            "{",
            "    electroRegion electro;",
            "    solidRegion solid;",
            "}",
            "",
        ]),
    )
    with pytest.raises(PhysicsLayoutError, match="banana"):
        region_of(tmp_path, "banana")


def test_an_unknown_role_is_refused_for_a_single_region_type(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type electroModel;\n")
    with pytest.raises(PhysicsLayoutError, match="solid"):
        region_of(tmp_path, "solid")


def test_a_case_without_physics_properties_is_single_region(tmp_path):
    _write(tmp_path / "constant" / "electroProperties", "myocardiumSolver monodomainSolver;\n")
    assert region_of(tmp_path, "electro") is None
    assert region_document(tmp_path, "electro", "electroProperties") == (
        tmp_path / "constant" / "electroProperties"
    )


def test_a_case_without_physics_properties_still_refuses_an_unknown_role(tmp_path):
    with pytest.raises(PhysicsLayoutError, match="solid"):
        region_of(tmp_path, "solid")


def test_the_hook_lets_a_physics_layout_error_propagate(tmp_path):
    _write(tmp_path / "constant" / "physicsProperties", "type fsiModel;\n")
    with pytest.raises(PhysicsLayoutError, match="fsiModel"):
        is_nondimensional_case(_Spec(tmp_path))


def test_the_hook_still_swallows_the_detectors_own_parse_failure(tmp_path):
    """A ``KeyError`` from ``detect_myocardium_solver_name`` still answers "not exempt"."""
    _write(tmp_path / "constant" / "electroProperties", "myocardiumSolver monodomainSolver;\n")
    assert is_nondimensional_case(_Spec(tmp_path)) is False
