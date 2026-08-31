"""A plugin that answers the environment hooks itself, with no OpenFOAM.

core's compatibility fallbacks for these hooks import omnidriver.openfoam
unconditionally -- a documented default (future/ENVIRONMENT_CONTRACT.md §4),
not a defect. But it means a core test that omits them is not testing core, it
is testing core-plus-OpenFOAM. This double is what lets core's own suite prove
core runs without a sibling package installed.

``_EnvironmentNeutralHooks`` is split out as a mixin, separate from
``NeutralEnvironmentPlugin`` itself, because two different kinds of core test
need it composed onto two different identities:

- most tests just need *a* plugin, so ``NeutralEnvironmentPlugin`` (this
  mixin plus ``MinimalOpenFOAMPlugin``) is enough.
- a few tests (e.g. ``test_core_generic_case.py``'s
  ``test_plain_allrun_case_works_with_the_no_domain_context``) assert on the
  built-in ``GenericOpenFOAMPlugin``'s identity
  (``report.plugin["id"] == "org.driverfoam.generic-openfoam"``) directly --
  swapping in ``NeutralEnvironmentPlugin`` there would change what the test
  measures, not just how it runs. Those tests instead compose the mixin onto
  ``GenericOpenFOAMPlugin`` locally, keeping the identity assertion intact
  while still avoiding the omnidriver.openfoam import.

``NeutralEnvironmentPlugin`` also declares the same three case-file rules the
built-in ``GenericOpenFOAMPlugin`` declares (``system/controlDict`` ->
``openfoam.control_dict``, ``constant`` -> ``openfoam.case_directory``,
``Allrun`` -> ``openfoam.entrypoint``). Those role bindings are core's own
declarative vocabulary (ENVIRONMENT_CONTRACT.md §4) -- plain data read by
``core/runtime/provenance_inputs.py``, not a call into ``omnidriver.openfoam``
-- so declaring them does not reintroduce the dependency this double exists to
avoid. Without them, core cannot find ``constant/`` during a provenance walk
or resolve ``startFrom latestTime``, and a test asserting on that behaviour
would have no way to pass without weakening its assertion.
"""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


class _EnvironmentNeutralHooks:
    """Mixin implementing every hook whose fallback reaches
    ``omnidriver.openfoam`` when a plugin exercises the full ``strict_plan``/
    ``describe_entry`` pipeline: config-value reads, environment preflight,
    function-object field warnings, and case dict-key drift warnings. Each
    answer is a genuine "nothing to report" for a plugin with no OpenFOAM
    vocabulary of its own, not a stub standing in for unwritten behaviour."""

    def get_capabilities(self):
        """A real, if empty, accept-surface -- built through the same
        assembler ``GenericOpenFOAMPlugin`` uses (``core.capability_manifest``,
        no ``omnidriver.openfoam`` involved), rather than
        ``MinimalOpenFOAMPlugin``'s bare ``{}``. A caller inspecting
        ``allowed_commands`` (as ``strict_plan``'s capability manifest does)
        needs the real shape, not an absent key."""
        from omnidriver.core.capability_manifest import build_capability_manifest

        return build_capability_manifest(
            plugin_commands=self.get_solver_commands() | self.get_auxiliary_commands(),
            utility_manifests=self.get_utility_manifests(),
            samplable_fields=self.get_samplable_fields({}),
        )

    def get_config_value_reader(self):
        """A reader for a trivial ``key value`` line format -- deliberately
        NOT OpenFOAM syntax, so a test passing this plugin proves core never
        assumed one."""
        def _read(path: Path, key: str) -> str | None:
            try:
                for line in Path(path).read_text().splitlines():
                    name, _, value = line.strip().partition(" ")
                    if name == key:
                        return value.strip().rstrip(";") or None
            except OSError:
                return None
            return None

        return _read

    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, openfoam_bashrc=None, driver_context=None,
    ) -> tuple:
        """No environment preconditions: this plugin's steps need no sourced
        profile. Returning () is a real answer, not a stub."""
        del workflow_dag, env, openfoam_bashrc, driver_context
        return ()

    def get_function_object_field_diagnostics(self, case_root, *, samplable) -> tuple:
        """No function-object/samplable-field vocabulary of its own, so no
        warnings to raise. Same ungated-fallback reasoning as the hook
        above -- ``legacy_function_object_field_diagnostics`` also imports
        ``omnidriver.openfoam`` unconditionally when a plugin omits this."""
        del case_root, samplable
        return ()

    def get_case_dict_key_diagnostics(
        self, case_root, *, catalogued_paths, dict_relpaths,
    ) -> tuple:
        """No dict catalogue of its own, so no key drift to detect. Same
        ungated-fallback reasoning: ``legacy_case_dict_key_diagnostics`` also
        imports ``omnidriver.openfoam`` unconditionally when absent."""
        del case_root, catalogued_paths, dict_relpaths
        return ()


class NeutralEnvironmentPlugin(_EnvironmentNeutralHooks, MinimalOpenFOAMPlugin):
    """``MinimalOpenFOAMPlugin`` plus every hook whose fallback reaches
    ``omnidriver.openfoam``, and the case-file rules a bare OpenFOAM-shaped
    case needs those hooks to actually be exercised against (see module
    docstring)."""

    @property
    def plugin_id(self) -> str:
        return "org.driverfoam.test-neutral-environment"

    def get_profile(self) -> PluginProfile:
        case_files = (
            CaseFileRule(
                path="system/controlDict",
                kind="openfoam_dictionary",
                role="openfoam.control_dict",
                required="always",
            ),
            CaseFileRule(
                path="constant",
                kind="openfoam_dictionary",
                role="openfoam.case_directory",
                required="always",
            ),
            CaseFileRule(
                path="Allrun",
                kind="case_script",
                role="openfoam.entrypoint",
                required="conditional",
            ),
        )
        return PluginProfile(
            path=Path(__file__),
            plugin_id=self.plugin_id,
            api_version=self.plugin_api_version,
            case_files=case_files,
            cxx_mapping=None,
            payload={
                "schema_version": 1,
                "plugin": {
                    "id": self.plugin_id,
                    "api_version": self.plugin_api_version,
                },
                "case_profile": {
                    "dictionaries": [
                        {
                            "path": rule.path,
                            "kind": rule.kind,
                            "role": rule.role,
                            "required": rule.required,
                        }
                        for rule in case_files
                    ]
                },
            },
        )
