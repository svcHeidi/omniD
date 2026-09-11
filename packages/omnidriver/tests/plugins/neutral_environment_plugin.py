"""Neutral adapter fixture used to prove Core works without sibling adapters.

It supplies explicit environment, diagnostics, and case-file declarations so
tests exercise Core contracts without relying on installed adapter packages.
The fixture deliberately uses a few OpenFOAM-shaped declarations where a test
needs to characterize an adapter contract; its runtime convention is neutral.

``_EnvironmentNeutralHooks`` is split out as a mixin, separate from
``NeutralEnvironmentPlugin`` itself, because two different kinds of core test
need it composed onto two different identities:

- most tests just need *a* plugin, so ``NeutralEnvironmentPlugin`` (this
  mixin plus ``MinimalOpenFOAMPlugin``) is enough.
- a few tests (e.g. ``test_core_generic_case.py``'s
  ``test_plain_allrun_case_works_with_the_no_domain_context``) assert on the
  built-in ``OpenFOAMEnvironmentPlugin``'s identity
  (``report.plugin["id"] == "org.omnidriver.openfoam.environment"``) directly --
  swapping in ``NeutralEnvironmentPlugin`` there would change what the test
  measures, not just how it runs. Those tests instead compose the mixin onto
  ``OpenFOAMEnvironmentPlugin`` locally, keeping the identity assertion intact
  while still avoiding the omnidriver.openfoam import.

``NeutralEnvironmentPlugin`` also declares the same three case-file rules the
built-in ``OpenFOAMEnvironmentPlugin`` declares (``system/controlDict`` ->
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

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from plugins.minimal_plugin import MinimalOpenFOAMPlugin


class _EnvironmentNeutralHooks:
    """Explicit neutral answers for optional environment and diagnostics hooks.

    The fixture keeps these answers local so Core tests do not depend on an
    installed solver adapter or on compatibility behavior from another
    package.
    """

    def get_capabilities(self):
        """A real, if empty, accept-surface -- built through the same
        assembler ``OpenFOAMEnvironmentPlugin`` uses (``core.capability_manifest``,
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
        self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None,
    ) -> tuple:
        """No environment preconditions: this plugin's steps need no sourced
        profile. Returning () is a real answer, not a stub."""
        del workflow_dag, env, explicit_bashrc, driver_context
        return ()

    def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None) -> dict:
        """Use the current process environment; this fixture has no shell profile."""
        del explicit_bashrc, driver_context
        import os

        return dict(os.environ)

    def get_configured_environment(self, env, driver_context) -> dict:
        """Preserve the supplied environment mapping unchanged."""
        del driver_context
        return dict(env)

    def get_function_object_field_diagnostics(self, case_root, *, samplable) -> tuple:
        """This fixture declares no function-object field vocabulary."""
        del case_root, samplable
        return ()

    def get_case_dict_key_diagnostics(
        self, case_root, *, catalogued_paths, dict_relpaths,
    ) -> tuple:
        """This fixture declares no dictionary catalogue, so no drift is reported."""
        del case_root, catalogued_paths, dict_relpaths
        return ()


class NeutralEnvironmentPlugin(_EnvironmentNeutralHooks, MinimalOpenFOAMPlugin):
    """Neutral fixture plus explicit case-file declarations for Core tests."""

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

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        """A deliberately non-OpenFOAM execution contract for Core tests."""
        return CaseRuntimeConventions(
            output_collection_relpath="outputs",
            case_entrypoints=("run-case",),
            case_script_commands=("run-case",),
        )
