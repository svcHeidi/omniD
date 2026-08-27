from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_profile import (
    KNOWN_ROLES,
    PluginProfile,
    load_plugin_profile,
)


def test_generic_profile_declares_no_solver_specific_files() -> None:
    """The generic stub declares the two structural facts true of any
    OpenFOAM case (system/controlDict, the constant/ directory) so core can
    derive provenance-walk roots and startFrom/startTime resolution without
    a plugin present -- but declares nothing solver-specific (no plugin.*
    role, e.g. no electroProperties-style constant/* file)."""
    profile = GenericOpenFOAMPlugin().get_profile()

    assert profile.plugin_id == "org.driverfoam.generic-openfoam"
    assert {rule.path for rule in profile.case_files} == {
        "system/controlDict",
        "constant",
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
