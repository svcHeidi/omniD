"""OpenFOAM environment adapter with no solver-specific semantics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from omnidriver.core.capability_manifest import build_capability_manifest
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_interface import driver_context as make_driver_context

from .case_runtime_conventions import openfoam_case_runtime_conventions
from .command_authorization import is_installed_openfoam_application, openfoam_runtime_commands
from .profile import load_openfoam_profile


class OpenFOAMEnvironmentPlugin:
    """OpenFOAM conventions, without any solver scientific configuration."""

    @property
    def plugin_name(self) -> str:
        return "OpenFOAM environment"

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.openfoam.environment"

    @property
    def plugin_version(self) -> str:
        return "1"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        return load_openfoam_profile(Path(__file__).with_name("openfoam-environment.yaml"))

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})

    def get_dict_groups(self):
        return {}

    def get_capabilities(self):
        """This provider's own self-description.

        No solver vocabulary: this adapter has no scientific configuration,
        so ``plugin_commands``/``utility_manifests``/``samplable_fields``
        carry the same neutral values core's own compatibility fallbacks
        would supply for an adapter that never implemented those hooks --
        matching :meth:`get_solver_commands` and friends having been removed
        as hollow stubs rather than genuine environment behaviour.
        """
        conventions = self.get_case_runtime_conventions()
        return build_capability_manifest(
            environment_commands=self.get_environment_commands(),
            plugin_commands=frozenset(),
            utility_manifests={},
            samplable_fields={},
            case_script_commands=frozenset(conventions.case_script_commands)
            | frozenset(conventions.case_entrypoints),
        )

    def get_tutorial_catalog(self):
        return {"registered_tutorials": (), "spec_factories": {}}

    def get_tutorial_displays(self):
        return ()

    def validate_configuration(self, spec):
        return ()

    def validate_run_semantics(self, context):
        return ()

    def predict_data_artifacts(self, case_root, spec):
        return ()

    def get_base_mesh_geometry_diagnostics(self, case_root):
        from .mesh_geometry import mesh_geometry_diagnostics

        return mesh_geometry_diagnostics(case_root)

    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, explicit_bashrc=None, driver_context=None,
    ):
        from .environment_preflight import _environment_diagnostics

        return _environment_diagnostics(
            workflow_dag,
            env=env,
            explicit_bashrc=explicit_bashrc,
            driver_context=driver_context,
        )

    def get_configured_environment(self, env, driver_context):
        from .openfoam_environment import configure_plugin_environment

        return configure_plugin_environment(env, driver_context).env

    def get_loaded_environment(self, *, explicit_bashrc=None, driver_context=None):
        from .openfoam_environment import load_openfoam_environment

        return dict(
            load_openfoam_environment(
                explicit_bashrc=explicit_bashrc,
                driver_context=driver_context,
            ).env
        )

    def get_config_value_reader(self):
        from .mutators import read_foam_entry

        return read_foam_entry

    def get_selected_start_time(self, case_root, resolved_case) -> str:
        del resolved_case
        from .mutators import read_foam_entry
        from .time_selection import selected_start_time

        control_dict = next(
            rule.path
            for rule in self.get_profile().case_files
            if rule.role == "openfoam.control_dict"
        )
        return selected_start_time(
            case_root,
            control_dict_relpath=control_dict,
            read_value=read_foam_entry,
        )

    def get_function_object_field_diagnostics(self, case_root, *, samplable):
        from .function_object_fields import function_object_field_diagnostics

        return function_object_field_diagnostics(case_root, samplable=samplable)

    def get_case_dict_key_diagnostics(
        self, case_root, *, catalogued_paths, dict_relpaths,
    ):
        from .case_dict_keys import case_dict_key_diagnostics

        return case_dict_key_diagnostics(
            case_root,
            catalogued_paths=catalogued_paths,
            dict_relpaths=dict_relpaths,
        )

    def apply_overrides(self, overrides, *, case_root, driver_context):
        from .apply_overrides import apply_overrides

        return apply_overrides(
            overrides, case_root=case_root, driver_context=driver_context,
        )

    def get_override_target_paths(self, overrides, *, case_root, driver_context):
        from .apply_overrides import override_target_paths

        return override_target_paths(
            overrides, case_root=case_root, driver_context=driver_context,
        )

    def inspect_effective_configuration(self, *, case_root, execution_env=None):
        from .effective_dictionary import inspect_effective_foam_configuration

        relpaths = tuple(
            rule.path
            for rule in self.get_profile().case_files
            if rule.kind == "openfoam_dictionary"
        )
        return inspect_effective_foam_configuration(
            case_root,
            relpaths,
            env=execution_env,
        )

    def get_environment_commands(self) -> frozenset[str]:
        return openfoam_runtime_commands()

    def is_installed_environment_command(self, command: str) -> bool:
        return is_installed_openfoam_application(command)

    def get_solve_step_commands(self) -> frozenset:
        return frozenset()

    def get_telemetry_source_globs(self, command: str) -> tuple:
        del command
        return ()

    def get_extra_provenance_paths(self, case_root) -> tuple:
        del case_root
        return ()

    def get_artifact_value_reader(self, artifact_format: str):
        del artifact_format
        return None

    def get_named_catalogs(self):
        return {}

    def get_override_scopes(self):
        return ()

    def get_case_runtime_conventions(self):
        return openfoam_case_runtime_conventions()

    def build_run_document_config(self, spec):
        del spec
        return {}, ()


def openfoam_environment_context():
    """Build the explicit OpenFOAM environment context for local callers."""

    return make_driver_context(
        OpenFOAMEnvironmentPlugin(), source="adapter:openfoam-environment"
    )
