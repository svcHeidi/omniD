from __future__ import annotations

import pytest

from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.profile import OPENFOAM_CASE_FILE_ROLES, load_openfoam_profile


def test_environment_profile_uses_only_adapter_supported_roles() -> None:
    profile = OpenFOAMEnvironmentPlugin().get_profile()
    assert profile.plugin_id == "org.omnidriver.openfoam.environment"
    assert all(
        not rule.role.startswith("openfoam.")
        or rule.role in OPENFOAM_CASE_FILE_ROLES
        for rule in profile.case_files
    )


def test_adapter_rejects_an_unsupported_openfoam_role(tmp_path) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin: {id: org.example.openfoam, api_version: '2'}\n"
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/unknownDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: openfoam.unsupported\n"
        "      required: always\n"
    )

    with pytest.raises(ValueError, match="Unsupported OpenFOAM case-file roles"):
        load_openfoam_profile(profile)
