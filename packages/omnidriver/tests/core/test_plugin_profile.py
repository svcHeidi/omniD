from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_profile import (
    CaseFileRule,
    PluginProfile,
    load_plugin_profile,
)


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
        '  api_version: "3"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: control_dict\n"           # missing the openfoam. namespace
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="invalid case-file role 'control_dict'"):
        load_plugin_profile(profile)


def test_a_core_role_loads(tmp_path) -> None:
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.test\n"
        '  api_version: "3"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        "      role: plugin.configuration\n"
        "      required: always\n"
    )
    loaded = load_plugin_profile(profile)
    assert loaded.case_files[0].role == "plugin.configuration"


# --- An environment's own role namespace ---
#
# get_profile() is a required SolverPlugin member, so a plugin whose profile
# YAML declares e.g. `fenics.mesh_file` must load.


def test_a_role_in_a_foreign_environments_namespace_loads(tmp_path) -> None:
    """A role naming an environment core has never heard of (FEniCS) loads."""
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.fenics\n"
        '  api_version: "3"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: mesh.xml\n"
        "      kind: openfoam_dictionary\n"
        "      role: fenics.mesh_file\n"
        "      required: always\n"
    )
    loaded = load_plugin_profile(profile)
    assert loaded.case_files[0].role == "fenics.mesh_file"


@pytest.mark.parametrize(
    "bad_role",
    [
        "plugin.configuraton",     # misspelled Core-owned role
        "case.regression",         # unknown Core-owned role
        "control_dict",            # missing the namespace entirely
        "fenics",                  # no leaf segment at all
        ".mesh_file",              # empty namespace
        "fenics.",                 # empty leaf
    ],
)
def test_a_malformed_role_or_a_typo_in_a_core_namespace_raises(
    tmp_path, bad_role: str,
) -> None:
    """Core-owned role namespaces remain closed at load time."""
    profile = tmp_path / "plugin.yaml"
    profile.write_text(
        "schema_version: 1\n"
        "plugin:\n"
        "  id: org.example.typo\n"
        '  api_version: "3"\n'
        "case_profile:\n"
        "  dictionaries:\n"
        "    - path: system/controlDict\n"
        "      kind: openfoam_dictionary\n"
        f"      role: {bad_role}\n"
        "      required: always\n"
    )
    with pytest.raises(ValueError, match="invalid case-file role"):
        load_plugin_profile(profile)


def test_a_non_openfoam_role_survives_driver_context_end_to_end() -> None:
    """Beyond the loader: a hand-built PluginProfile (as a real plugin's get_profile() would return, whether or not it was sourced from YAML) carrying a foreign-namespace role must be accepted by driver_context(...), and the rule must come back out of the stack's profile intact -- proving the seam works all the way through, not just at parse time."""
    from omnidriver.core.plugin_interface import driver_context
    from plugins.toy import ToyProvider

    fenics_rule = CaseFileRule(
        path="mesh.xml",
        kind="openfoam_dictionary",
        role="fenics.mesh_file",
        required="always",
    )

    class _FenicsLikePlugin(ToyProvider):
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

    assert fenics_rule in context.stack.call("get_profile").case_files
    assert not fenics_rule.role.startswith("openfoam.")
