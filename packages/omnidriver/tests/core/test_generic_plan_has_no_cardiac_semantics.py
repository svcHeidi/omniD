"""Generic plans contain no cardiacFOAM commands, fields, or vocabulary."""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.introspection import describe_entry
from omnidriver.core.strict_planning import strict_plan
from plugins.declared_case_plugin import DeclaredCasePlugin

# Every token that would betray a cardiac assumption leaking into a plan
# produced for a non-cardiac solver.
_CARDIAC_TOKENS = (
    "cardiacFoam",
    "electroProperties",
    "physicsProperties",
    "ELECTRO_MODEL_COEFFS",
    "ionicModel",
    "myocardiumSolver",
    "activationTime",
    "phiE",
    "listCellModelsVariables",
    "bathBidomainInterfaceMetrics",
)


def _minimal_case(root: Path) -> Path:
    """A plain case with this test's explicit entrypoint and no solver files."""
    case = root / "case"
    case.mkdir()
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\necho generic-case-ran\n")
    return case


def _generic_plan(tmp_path: Path) -> dict:
    """Plan under a test-local, explicitly declared no-domain environment."""
    case = _minimal_case(tmp_path)
    return strict_plan(
        str(case.relative_to(tmp_path)),
        overrides={"cases_root": str(tmp_path)},
        driver_context=driver_context(DeclaredCasePlugin(), source="test"),
    ).to_json()


def test_generic_plan_contains_no_cardiac_semantics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    blob = json.dumps(_generic_plan(tmp_path))
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"cardiac semantics leaked into a generic plan: {leaked}"


def test_generic_plan_still_produces_a_usable_contract(tmp_path, monkeypatch) -> None:
    """Emptiness is not the goal -- the plan must still be runnable."""
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    payload = _generic_plan(tmp_path)
    assert payload["workflow_dag"]["steps"], "generic plan must have runnable steps"
    assert payload["capability_manifest"]["allowed_commands"]["utilities"] == {}
    assert "cardiacFoam" not in payload["capability_manifest"]["allowed_commands"]["plugin"]


def test_generic_describe_override_surface_has_no_cardiac_semantics(
    tmp_path, monkeypatch
) -> None:
    """The spec's exit gate names "override semantics", but those live in the
    describe payload (``config_schema``, ``dict_entries``) -- ``strict_plan``
    does not emit them, so gating only on the plan left the one clause naming
    the override surface checked against a payload that cannot contain it."""
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    case = _minimal_case(tmp_path)
    payload = describe_entry(
        str(case.relative_to(tmp_path)),
        overrides={"cases_root": str(tmp_path)},
        driver_context=driver_context(DeclaredCasePlugin(), source="test"),
    )
    override_surface = {
        "config_schema": payload["config_schema"],
        "dict_entries": payload["dict_entries"],
    }
    blob = json.dumps(override_surface)
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"cardiac override semantics leaked: {leaked}"


def test_generic_spec_metadata_names_dict_files_generically(
    tmp_path, monkeypatch
) -> None:
    """Generic case metadata uses plugin-declared dictionary names."""
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    monkeypatch.setenv("SKIP_MESH_DIAGNOSTICS", "1")
    case = _minimal_case(tmp_path)
    payload = describe_entry(
        str(case.relative_to(tmp_path)),
        overrides={"cases_root": str(tmp_path)},
        driver_context=driver_context(DeclaredCasePlugin(), source="test"),
    )
    metadata = payload["spec"]["metadata"]
    assert "electro_properties_relpath" not in metadata
    assert "physics_properties_relpath" not in metadata
    assert "has_default_electro_property_overrides" not in metadata
    assert "has_default_physics_property_overrides" not in metadata
    assert metadata["has_default_dict_file_overrides"] is False
    assert metadata["dict_file_relpaths"] == {}
