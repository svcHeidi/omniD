from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.generic_plugin import GenericOpenFOAMPlugin
from omnidriver.core.plugin_profile import PluginProfile, load_plugin_profile


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
