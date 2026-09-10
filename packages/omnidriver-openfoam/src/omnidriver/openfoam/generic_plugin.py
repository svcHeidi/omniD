"""Built-in no-domain plugin for generic OpenFOAM case orchestration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from omnidriver.core.capability_manifest import build_capability_manifest
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import (
    entrypoint_relpaths_from_profile,
    load_plugin_profile,
)
from omnidriver.core.runtime.workflow import CASE_SCRIPT_COMMANDS

from .case_runtime_conventions import openfoam_case_runtime_conventions
from .command_authorization import (
    is_installed_openfoam_application,
    openfoam_runtime_commands,
)


class GenericOpenFOAMPlugin:
    """OpenFOAM execution conventions with no solver-specific semantics."""

    @property
    def plugin_name(self) -> str:
        return "generic OpenFOAM"

    @property
    def plugin_id(self) -> str:
        return "org.driverfoam.generic-openfoam"

    @property
    def plugin_version(self) -> str:
        return "1"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        return load_plugin_profile(Path(__file__).with_name("generic-plugin.yaml"))

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})

    def get_dict_groups(self):
        return {}

    def get_capabilities(self):
        return build_capability_manifest(
            environment_commands=self.get_environment_commands(),
            plugin_commands=(
                self.get_solver_commands() | self.get_auxiliary_commands()
            ),
            utility_manifests=self.get_utility_manifests(),
            samplable_fields=self.get_samplable_fields({}),
            case_script_commands=CASE_SCRIPT_COMMANDS
            | frozenset(entrypoint_relpaths_from_profile(self.get_profile())),
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

    def get_solver_commands(self) -> frozenset[str]:
        return frozenset()

    def get_auxiliary_commands(self) -> frozenset[str]:
        return frozenset()

    def get_environment_commands(self) -> frozenset[str]:
        return openfoam_runtime_commands()

    def is_installed_environment_command(self, command: str) -> bool:
        return is_installed_openfoam_application(command)

    def get_utility_manifests(self) -> dict:
        return {}

    def get_utility_roots(self) -> tuple[Path, ...]:
        return ()

    def resolve_case_models(self, case_root):
        del case_root
        return {}

    def get_samplable_fields(self, resolved):
        del resolved
        return {}

    def get_override_schema(self, tutorial_name, make_spec_info):
        del tutorial_name, make_spec_info
        return {}

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

    def get_dict_entry_catalog(self):
        return {}

    def get_named_catalogs(self):
        return {}

    def get_override_scopes(self):
        return ()

    def get_case_runtime_conventions(self):
        return openfoam_case_runtime_conventions()

    def get_decomposition_dirname_prefix(self) -> str:
        prefix = self.get_case_runtime_conventions().decomposition_directory_prefix
        assert prefix is not None
        return prefix

    def build_run_document_config(self, spec):
        del spec
        return {}, ()

    def get_run_document_config_schema(self) -> dict:
        return {"type": "object", "additionalProperties": True}
