"""``record_key_validation.record_key_validator`` against the checked-in catalog
data, with no case on disk; ``test_record_key_validation_native.py`` runs it
against a real native case.
"""

from __future__ import annotations

import pytest

from omnidriver.cardiacfoam.record_key_validation import record_key_validator


# ---------------------------------------------------------------------------
# Rule 1: constant/electroProperties and constant/physicsProperties, checked
# against the catalog.
# ---------------------------------------------------------------------------


def test_catalogued_electro_properties_key_validates_true():
    value_kind, validated = record_key_validator(
        "constant/electroProperties",
        ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude"),
        0.4,
    )
    assert value_kind == "scalar"
    assert validated is True


def test_catalogued_electro_properties_key_via_a_different_solver_coeffs_block():
    """The <solver>Coeffs segment comes from the catalog's myocardiumSolver enum_values."""
    value_kind, validated = record_key_validator(
        "constant/electroProperties",
        ("monodomainSolverCoeffs", "conductivitySource"),
        "uniform",
    )
    assert value_kind == "enum"
    assert validated is True


def test_top_level_myocardium_solver_key_validates_true():
    """A bare top-level key (no <solver>Coeffs scope) matches literally."""
    value_kind, validated = record_key_validator(
        "constant/electroProperties", ("myocardiumSolver",), "singleCellSolver",
    )
    assert value_kind == "enum"
    assert validated is True


def test_catalogued_physics_properties_key_validates_true():
    value_kind, validated = record_key_validator(
        "constant/physicsProperties", ("type",), "electroModel",
    )
    assert value_kind == "enum"
    assert validated is True


def test_misspelled_electro_properties_key_is_refused_by_name():
    with pytest.raises(KeyError) as excinfo:
        record_key_validator(
            "constant/electroProperties",
            ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitud"),
            0.4,
        )
    message = str(excinfo.value)
    assert "constant/electroProperties" in message
    assert "stim_amplitud" in message


def test_a_first_segment_not_in_the_solver_vocabulary_is_refused():
    """Refused, though ``overrides._catalog_entry_for`` would accept it as $ELECTRO_MODEL_COEFFS."""
    with pytest.raises(KeyError):
        record_key_validator(
            "constant/electroProperties",
            ("bogusCoeffs", "singleCellStimulus", "stim_amplitude"),
            0.4,
        )


def test_a_value_of_the_wrong_kind_is_refused():
    with pytest.raises(ValueError) as excinfo:
        record_key_validator(
            "constant/electroProperties",
            ("singleCellSolverCoeffs", "singleCellStimulus", "stim_amplitude"),
            "not-a-number",
        )
    assert "scalar" in str(excinfo.value)


def test_a_dynamic_path_binding_is_checked_against_its_declared_domain():
    """ionicConstantOverrides.<scope> has a closed domain: in-domain validates, out-of-domain refused."""
    value_kind, validated = record_key_validator(
        "constant/electroProperties",
        (
            "monodomainSolverCoeffs", "ionicConstantOverrides", "global",
            "scale", "gNa",
        ),
        1.1,
    )
    assert validated is True
    assert value_kind == "scalar"

    with pytest.raises(ValueError):
        record_key_validator(
            "constant/electroProperties",
            (
                "monodomainSolverCoeffs", "ionicConstantOverrides",
                "not_a_real_scope", "scale", "gNa",
            ),
            1.1,
        )


_BATH = ("bidomainSolverCoeffs", "bathPotentialDomain")


@pytest.mark.parametrize("value", [{"xMax": 0.01}, {"xMin": 0}, {}])
def test_a_whole_patch_map_validates_member_by_member(value):
    """An empty map is real: ``groundPatches {}`` is the native electrodePair state."""
    for name in ("groundPatches", "surfaceCurrentPatches"):
        assert record_key_validator(
            "constant/electroProperties", _BATH + (name,), value,
        ) == ("mapping", True)


def test_a_patch_map_member_of_the_wrong_kind_is_refused_by_name():
    with pytest.raises(ValueError) as excinfo:
        record_key_validator(
            "constant/electroProperties", _BATH + ("groundPatches",), {"xMin": "zero"},
        )
    assert "groundPatches.xMin" in str(excinfo.value)


def test_a_map_at_a_key_with_no_catalogued_members_is_refused():
    with pytest.raises(KeyError) as excinfo:
        record_key_validator(
            "constant/electroProperties", _BATH + ("groundPatchez",), {"xMin": 0},
        )
    assert "groundPatchez" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Rule 2: any other document under system/ -- accepted, validated=False.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected_kind",
    [
        (True, "boolean"),
        (5, "integer"),
        (1e-5, "scalar"),
        # "word" refuses whitespace, so a whitespace-containing string is "string".
        ("80 80 80", "string"),
        ("Gauss linear", "string"),
        ("leastSquares", "word"),
        ((40, 6, 14), "integer_list"),
        ([40, 6, 14], "integer_list"),
        ((1.5, 2.5), "scalar_list"),
    ],
)
def test_system_document_key_accepted_unvalidated(value, expected_kind):
    value_kind, validated = record_key_validator(
        "system/controlDict", ("someKey",), value,
    )
    assert validated is False
    assert value_kind == expected_kind


def test_system_control_dict_delta_t_is_unvalidated():
    value_kind, validated = record_key_validator(
        "system/controlDict", ("deltaT",), 1e-5,
    )
    assert value_kind == "scalar"
    assert validated is False


def test_system_block_mesh_dict_hex_cell_counts_is_unvalidated():
    """A direct ``document:key`` study naming this key with pre-joined text."""
    value_kind, validated = record_key_validator(
        "system/blockMeshDict", ("hex_cell_counts",), "200 30 70",
    )
    assert value_kind == "string"
    assert validated is False


def test_system_block_mesh_dict_hex_cell_counts_tuple_is_unvalidated():
    """The typed shape ``block_mesh_resolution_axis`` produces."""
    value_kind, validated = record_key_validator(
        "system/blockMeshDict", ("hex_cell_counts",), (200, 30, 70),
    )
    assert value_kind == "integer_list"
    assert validated is False


# ---------------------------------------------------------------------------
# Rule 3: anything else -- refused by name, so a typo can never slip through
# as "unvalidated".
# ---------------------------------------------------------------------------


def test_a_near_miss_document_name_is_refused_not_treated_as_unvalidated():
    with pytest.raises(KeyError) as excinfo:
        record_key_validator("constant/electroPropertie", ("myocardiumSolver",), "x")
    message = str(excinfo.value)
    assert "constant/electroPropertie" in message


def test_an_unrelated_document_is_refused():
    with pytest.raises(KeyError):
        record_key_validator("constant/mesh.json", ("cells",), 5)
