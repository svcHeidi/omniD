"""``record_key_validation.record_key_validator`` -- step 4a of
``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md`` §5.

Unit-level: exercises the catalog-matching logic directly against
``dict_entries_catalog``/``common_dict_entries``'s real (checked-in) Python
data, with no filesystem case involved -- see
``test_record_key_validation_native.py`` for the same validator against the
REAL ``restitutionCurves_s1s2Protocol`` case's own files.
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
    """The <solver>Coeffs first segment is derived from the catalog's own
    myocardiumSolver enum_values, not hard-coded to one solver."""
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
    """'bogusCoeffs' is not any real <solver>Coeffs spelling the catalog's
    own myocardiumSolver enum_values sanctions -- refused rather than
    silently standing in for $ELECTRO_MODEL_COEFFS the way
    overrides._catalog_entry_for's own (differently-trusted) caller would
    accept it."""
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
    """$ELECTRO_MODEL_COEFFS.ionicConstantOverrides.<scope>.scale.<constant_name>
    declares a closed domain for <scope>; an out-of-domain binding is
    refused, an in-domain one validates."""
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


# ---------------------------------------------------------------------------
# Rule 2: any other document under system/ -- accepted, validated=False.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected_kind",
    [
        (True, "boolean"),
        (5, "integer"),
        (1e-5, "scalar"),
        ("80 80 80", "word"),
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
    value_kind, validated = record_key_validator(
        "system/blockMeshDict", ("hex_cell_counts",), "200 30 70",
    )
    assert value_kind == "word"
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
