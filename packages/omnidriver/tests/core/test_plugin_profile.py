from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_profile import (
    ESCAPE_ROLE_PREFIX,
    KNOWN_ROLES,
    CaseFileRule,
    PluginProfile,
    load_plugin_profile,
)


def test_generic_profile_declares_no_solver_specific_files() -> None:
    """The generic stub declares the structural facts true of any OpenFOAM
    case (system/controlDict, the constant/ directory, and its Allrun
    entrypoint -- see future/ENVIRONMENT_CONTRACT.md) so core can derive
    provenance-walk roots, startFrom/startTime resolution, and entrypoint
    discovery without a plugin present -- but declares nothing solver-specific
    (no plugin.* role, e.g. no electroProperties-style constant/* file)."""
    profile = GenericOpenFOAMPlugin().get_profile()

    assert profile.plugin_id == "org.driverfoam.generic-openfoam"
    assert {rule.path for rule in profile.case_files} == {
        "system/controlDict",
        "constant",
        "Allrun",
    }
    assert all(rule.role.startswith("openfoam.") for rule in profile.case_files)
    assert profile.cxx_mapping is None


def test_profile_rejects_case_path_escape(tmp_path: Path) -> None:
    path = tmp_path / "plugin.yaml"
    path.write_text(
        """schema_version: 1
plugin: {id: example.bad, api_version: '1'}
case_profile:
  dictionaries:
    - path: ../outside
      kind: openfoam_dictionary
      role: plugin.configuration
      required: always
"""
    )

    with pytest.raises(ValueError, match="escapes the case"):
        load_plugin_profile(path)


def test_profile_digest_is_stable_after_payload_mutation() -> None:
    payload = {
        "schema_version": 1,
        "plugin": {"id": "example.profile", "api_version": "1"},
        "case_profile": {"dictionaries": []},
    }
    profile = PluginProfile(
        path=Path("example-plugin.yaml"),
        plugin_id="example.profile",
        api_version="1",
        case_files=(),
        cxx_mapping=None,
        payload=payload,
    )

    digest = profile.digest
    payload["plugin"]["id"] = "example.mutated"

    assert profile.digest == digest


def test_an_unknown_role_is_rejected_at_load(tmp_path) -> None:
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.test\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: control_dict\n"           # missing the openfoam. namespace
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="unknown case-file role 'control_dict'"):
        load_plugin_profile(profile)


def test_a_known_role_loads(tmp_path) -> None:
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.test\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: openfoam.control_dict\n"
        "      required: always\n"
    )
    loaded = load_plugin_profile(profile)
    assert loaded.case_files[0].role == "openfoam.control_dict"


def test_the_generic_profile_uses_only_known_roles() -> None:
    from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin

    for rule in GenericOpenFOAMPlugin.get_profile().case_files:
        assert rule.role in KNOWN_ROLES, rule


def test_the_cardiac_profile_uses_only_known_roles() -> None:
    """Skipped in the core-only CI job, which installs no plugin package.

    Worth asserting anyway: cardiacFoam's profile declares nine of the eleven
    roles, so it is the real drift risk. Core's own declares two.
    """
    cardiacfoam_plugin = pytest.importorskip(
        "omnidriver.cardiacfoam.cardiacfoam_plugin",
        reason="omnidriver-cardiacfoam is not installed",
    )

    rules = cardiacfoam_plugin.CardiacFoamPlugin().get_profile().case_files
    assert rules, "cardiacFoam declares case files; an empty profile is a defect"
    for rule in rules:
        assert rule.role in KNOWN_ROLES, rule


# --- Escape tier: a role for an environment core has no vocabulary for ---
#
# The hard block this closes: get_profile() is a required SolverPlugin
# member, so a plugin whose profile YAML declares e.g. `fenics.mesh_file`
# used to fail at load with `ValueError: unknown case-file role
# 'fenics.mesh_file'` -- nothing about a non-OpenFOAM plugin could even be
# attempted. See future/ENVIRONMENT_CONTRACT.md §10.


def test_an_escape_role_for_a_foreign_environment_loads(tmp_path) -> None:
    """The acceptance test for the hard block: a role naming an environment
    core has never heard of (FEniCS) must load, not raise."""
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.fenics\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: mesh.xml\n"
        "      kind: openfoam_dictionary\n"
        "      role: x-fenics.mesh_file\n"
        "      required: always\n"
    )
    loaded = load_plugin_profile(profile)
    assert loaded.case_files[0].role == "x-fenics.mesh_file"


@pytest.mark.parametrize(
    "bad_role",
    [
        "openfoam.controldict",   # wrong case / missing underscore
        "openfoam.control_dickt",  # misspelled leaf
        "control_dict",            # missing the namespace entirely
    ],
)
def test_a_typo_in_a_known_namespace_still_raises_under_the_escape_tier(
    tmp_path, bad_role: str,
) -> None:
    """The escape tier must not weaken the original Phase 1 Task 2 guarantee:
    a typo against one of the three namespaces core actually validates
    (openfoam./plugin./case.) is still a load-time ValueError, because none
    of these carry the `x-` escape marker."""
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.typo\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        f"      role: {bad_role}\n"
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="unknown case-file role"):
        load_plugin_profile(profile)


@pytest.mark.parametrize(
    "bad_escape_role",
    [
        "x-openfoam.control_dict",  # shadows a reserved namespace
        "x-plugin.configuration",   # shadows a reserved namespace
        "x-case.documentation",     # shadows a reserved namespace
        "x-fenics",                 # no leaf segment at all
        "x-.mesh_file",             # empty namespace
        "x-fenics.",                # empty leaf
    ],
)
def test_a_malformed_or_shadowing_escape_role_still_raises(
    tmp_path, bad_escape_role: str,
) -> None:
    """The `x-` marker is not a blanket bypass: it still requires the
    `x-<namespace>.<leaf>` shape, and a namespace equal to one of the three
    reserved words is refused so the escape hatch cannot be used to dodge
    the closed-enum check on a role that looks like it should be core's."""
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.badescape\n"
        '  api_version: "2"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: some/file\n"
        "      kind: openfoam_dictionary\n"
        f"      role: {bad_escape_role}\n"
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="unknown case-file role"):
        load_plugin_profile(profile)


def test_a_non_openfoam_role_survives_driver_context_end_to_end() -> None:
    """Beyond the loader: a hand-built PluginProfile (as a real plugin's
    get_profile() would return, whether or not it was sourced from YAML)
    carrying an escape-tier role must be accepted by driver_context(...),
    and the rule must come back out of capabilities.case_files intact --
    proving the seam works all the way through, not just at parse time."""
    from omnidriver.core.plugin_interface import driver_context
    from plugins.minimal_plugin import MinimalOpenFOAMPlugin

    fenics_rule = CaseFileRule(
        path="mesh.xml",
        kind="openfoam_dictionary",
        role=f"{ESCAPE_ROLE_PREFIX}fenics.mesh_file",
        required="always",
    )

    class _FenicsLikePlugin(MinimalOpenFOAMPlugin):
        @property
        def plugin_id(self) -> str:
            return "org.example.fenics-e2e"

        def get_profile(self) -> PluginProfile:
            return PluginProfile(
                path=Path(__file__),
                plugin_id=self.plugin_id,
                api_version=self.plugin_api_version,
                case_files=(fenics_rule,),
                cxx_mapping=None,
                payload={
                    "schema_version": 1,
                    "plugin": {"id": self.plugin_id, "api_version": self.plugin_api_version},
                    "case_profile": {
                        "dictionaries": [{
                            "path": fenics_rule.path,
                            "kind": fenics_rule.kind,
                            "role": fenics_rule.role,
                            "required": fenics_rule.required,
                        }]
                    },
                },
            )

    context = driver_context(_FenicsLikePlugin(), source="test")

    assert fenics_rule in context.capabilities.case_files.all_rules()
    assert fenics_rule in context.capabilities.case_files.required_rules()
    # Not reclassified as OpenFOAM-owned by the tutorial_contracts.py split
    # (`role.startswith("openfoam.")`) -- it is neither in KNOWN_ROLES nor
    # under a reserved namespace.
    assert not fenics_rule.role.startswith("openfoam.")
