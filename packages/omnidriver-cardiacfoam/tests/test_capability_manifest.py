"""Tests for the capability manifest — the machine-readable surface of what the
driver will accept (allowed commands + samplable field names)."""

from omnidriver.core.capability_manifest import build_capability_manifest

from omnidriver.cardiacfoam.case_introspection import (
    samplable_fields as _samplable_fields,
)
from omnidriver.cardiacfoam.command_authorization import (
    CARDIAC_AUXILIARY_COMMANDS,
    CARDIAC_SOLVER_COMMANDS,
    utility_manifests,
)
from omnidriver.openfoam.command_authorization import openfoam_runtime_commands
from omnidriver.openfoam.case_runtime_conventions import openfoam_case_runtime_conventions
import functools

# The manifest advertises the accept-surface, which is the union of both kinds
# of authorized plugin command -- matching CardiacFoamPlugin.get_capabilities.
CARDIAC_AUTHORIZED_COMMANDS = CARDIAC_SOLVER_COMMANDS | CARDIAC_AUXILIARY_COMMANDS

build_capability_manifest = functools.partial(
    build_capability_manifest,
    environment_commands=openfoam_runtime_commands(),
    plugin_commands=CARDIAC_AUTHORIZED_COMMANDS,
    utility_manifests=dict(utility_manifests()),
    case_script_commands=frozenset(
        openfoam_case_runtime_conventions().case_script_commands
    ),
)


def _resolved(
    *,
    solver: str | None = None,
    ionic_model: str | None = None,
    active_tension: str | None = None,
):
    """Field names the cardiac plugin's own case_introspection module names
    for a resolved model -- what CardiacFoamPlugin.get_samplable_fields would
    produce, without going through the filesystem."""

    return _samplable_fields(
        {"solver": solver, "ionic_model": ionic_model, "active_tension": active_tension}
    )


from omnidriver.core.plugin_interface import driver_context as _driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.cardiacfoam.cardiacfoam_plugin import CardiacFoamPlugin

# Two adapters are installed side by side, so there is no ambient default
# left to discover. A test that means cardiacFoam says so.
_CTX = _driver_context(OpenFOAMEnvironmentPlugin(), CardiacFoamPlugin(), source="test:capability_manifest")
from omnidriver.core.runtime.workflow import (
    CORE_NEUTRAL_COMMANDS,
    validate_workflow_commands,
)


def test_core_commands_match_enforcer():
    manifest = build_capability_manifest()
    assert set(manifest["allowed_commands"]["core"]) == set(CORE_NEUTRAL_COMMANDS)
    assert set(manifest["allowed_commands"]["environment"]) == set(
        openfoam_runtime_commands(),
    )
    assert set(manifest["allowed_commands"]["plugin"]) == set(
        CARDIAC_AUTHORIZED_COMMANDS,
    )
    assert set(manifest["allowed_commands"]["case_scripts"]) == set(
        openfoam_case_runtime_conventions().case_script_commands
    )


def test_manifest_utilities_are_accepted_by_validator():
    manifest = build_capability_manifest()
    context = _CTX
    for cmd in manifest["allowed_commands"]["utilities"]:
        dag = {"steps": [{"id": "s", "command": cmd}]}
        errors = [
            d for d in validate_workflow_commands(dag, driver_context=context)
            if d.level == "error"
        ]
        assert errors == [], f"utility {cmd!r} in manifest but rejected by validator: {errors}"


def test_samplable_fields_for_tnnp_single_cell():
    manifest = build_capability_manifest(
        samplable_fields=_resolved(solver="singleCellSolver", ionic_model="TNNP")
    )
    electro = manifest["samplable_fields"]["electro"]
    assert "membrane_V" in electro
    assert "Vm" in electro
    assert "bananas" not in electro
    # single-cell has no mechanics region
    assert manifest["samplable_fields"]["solid"] == []


def test_species_labels_are_not_samplable_fields():
    manifest = build_capability_manifest(
        samplable_fields=_resolved(solver="monodomainSolver", ionic_model="TNNP")
    )
    electro = manifest["samplable_fields"]["electro"]
    assert "human" not in electro
    assert "pig" not in electro
    assert "generic" not in electro


def test_plain_spatial_ep_has_no_solid_region():
    for solver in ("monodomainSolver", "bidomainSolver", "eikonalSolver"):
        manifest = build_capability_manifest(samplable_fields=_resolved(solver=solver))
        assert manifest["samplable_fields"]["solid"] == []


def test_single_cell_active_tension_does_not_imply_solid_region():
    manifest = build_capability_manifest(
        samplable_fields=_resolved(
            solver="singleCellSolver", active_tension="LandNiederer"
        )
    )
    assert manifest["samplable_fields"]["solid"] == []


def test_samplable_fields_multi_region_tags_solid():
    manifest = build_capability_manifest(
        samplable_fields=_resolved(
            solver="monodomainSolver",
            ionic_model="TNNP",
            active_tension="LandNiederer",
        )
    )
    solid = manifest["samplable_fields"]["solid"]
    assert "Ta" in solid
    assert "lambda" in solid
    # active-tension state variables are included
    assert "XW" in solid


def test_unknown_model_is_not_an_error():
    # An unresolved / unknown model just yields the fixed solver fields, no crash.
    manifest = build_capability_manifest(
        samplable_fields=_resolved(ionic_model="NotARealModel")
    )
    assert "Vm" in manifest["samplable_fields"]["electro"]


def test_describe_entry_includes_capability_manifest():
    from omnidriver.core.introspection import describe_entry

    payload = describe_entry("singleCell", driver_context=_CTX)
    manifest = payload["capability_manifest"]
    assert "cardiacFoam" in manifest["allowed_commands"]["plugin"]
    assert "electro" in manifest["samplable_fields"]


def test_strict_plan_carries_capability_manifest(monkeypatch):
    monkeypatch.setenv("SKIP_ENV_DIAGNOSTICS", "1")
    from omnidriver.core.strict_planning import strict_plan

    report = strict_plan(
        "singleCell", driver_context=_CTX,
    ).to_json()
    assert "cardiacFoam" in report["capability_manifest"]["allowed_commands"]["plugin"]
