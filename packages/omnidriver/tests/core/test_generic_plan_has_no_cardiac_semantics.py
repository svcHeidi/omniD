"""A plan produced under --plugin none must contain no cardiacFoam command, field, required-file, utility, or override semantics."""

from __future__ import annotations

import json
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.introspection import describe_entry
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import case_folder_record
from plugins.e2e_record_plugin import E2EFolderPlugin

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
    case = root / "cases" / "case"
    case.mkdir(parents=True)
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\necho generic-case-ran\n")
    return case


def _generic_plan(tmp_path: Path) -> dict:
    """Plan under a test-local, explicitly declared no-domain environment."""
    context = driver_context(E2EFolderPlugin(), source="test")
    record, cases_root = case_folder_record(_minimal_case(tmp_path), driver_context=context)
    return strict_plan(
        record,
        overrides={"cases_root": str(cases_root)},
        scratch_root=tmp_path / "scratch",
        driver_context=context,
    ).to_json()


def test_generic_plan_contains_no_cardiac_semantics(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    blob = json.dumps(_generic_plan(tmp_path))
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"cardiac semantics leaked into a generic plan: {leaked}"


def test_generic_plan_still_produces_a_usable_contract(tmp_path, monkeypatch) -> None:
    """Emptiness is not the goal -- the plan must still be runnable."""
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    payload = _generic_plan(tmp_path)
    assert payload["workflow_dag"]["steps"], "generic plan must have runnable steps"
    assert payload["capability_manifest"]["allowed_commands"]["utilities"] == {}
    assert "cardiacFoam" not in payload["capability_manifest"]["allowed_commands"]["plugin"]


def test_generic_describe_has_no_cardiac_semantics(tmp_path, monkeypatch) -> None:
    """``describe`` carries the key catalogue and the plugin's catalogues; for a stack with none, neither may name a cardiac term."""
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    context = driver_context(E2EFolderPlugin(), source="test")
    record, cases_root = case_folder_record(_minimal_case(tmp_path), driver_context=context)
    payload = describe_entry(record, overrides={"cases_root": str(cases_root)}, driver_context=context)
    blob = json.dumps({
        "record_surface": payload["record_surface"],
        "plugin_catalogs": payload["plugin_catalogs"],
    })
    leaked = [token for token in _CARDIAC_TOKENS if token in blob]
    assert leaked == [], f"cardiac semantics leaked into a generic describe: {leaked}"
