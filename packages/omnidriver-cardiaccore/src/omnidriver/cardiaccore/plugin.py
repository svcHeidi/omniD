"""Source-backed cardiacCore adapter.

The supported vertical slice is deliberately small: the four preprocessing
utilities invoked by ``cases/bivCase/Allrun``. Reviewed x values can be
supplied through ``input_overrides`` in a run or sweep JSON; no extra solver
or utility is claimed until it has equivalent source evidence.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from omnidriver.core.capability_manifest import build_capability_manifest
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

from .input_catalog import CATALOG, CONDITIONAL_INPUTS, DOCUMENTS
from .tree_validation import TREE_VALIDATION_CONTRACT
from .tutorials import (
    HUMAN_TREE_TUTORIAL_NAME,
    PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME,
    TUTORIAL_NAME,
    make_biv_preprocessing_spec,
    make_human_endocardial_tree_spec,
    make_pig_morphometric_tree_spec,
)
from .utility_manifests import UTILITY_MANIFESTS


class CardiacCorePlugin:
    """OmniD API-v2 adapter for a documented cardiacCore preprocessing slice."""

    _openfoam = OpenFOAMEnvironmentPlugin()

    @property
    def plugin_name(self) -> str:
        return "cardiacCore"

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.cardiaccore"

    @property
    def plugin_version(self) -> str:
        return "0.0.1"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        return load_plugin_profile(Path(__file__).with_name("plugin.yaml"))

    def get_dict_entries(self) -> tuple[Any, ...]:
        return CATALOG.entries

    def get_phases(self) -> tuple[str, ...]:
        """The selected workflow has one utility-preprocessing configuration phase."""
        return ("preprocessing",)

    def get_dictionary_catalog(self) -> DictionaryCatalog:
        return CATALOG

    def get_dict_groups(self) -> dict[str, tuple[Any, ...]]:
        return DOCUMENTS

    def get_capabilities(self) -> dict[str, Any]:
        conventions = self.get_case_runtime_conventions()
        return build_capability_manifest(
            environment_commands=self._openfoam.get_environment_commands(),
            plugin_commands=self.get_solver_commands() | self.get_auxiliary_commands(),
            utility_manifests=self.get_utility_manifests(),
            samplable_fields=self.get_samplable_fields({}),
            case_script_commands=frozenset(conventions.case_script_commands)
            | frozenset(conventions.case_entrypoints),
        )

    def get_tutorial_catalog(self) -> dict[str, Any]:
        return {
            "registered_tutorials": (
                TUTORIAL_NAME,
                HUMAN_TREE_TUTORIAL_NAME,
                PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME,
            ),
            "spec_factories": {
                TUTORIAL_NAME: make_biv_preprocessing_spec,
                HUMAN_TREE_TUTORIAL_NAME: make_human_endocardial_tree_spec,
                PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME: make_pig_morphometric_tree_spec,
            },
        }

    def get_tutorial_displays(self) -> tuple[Any, ...]:
        return ()

    def get_case_runtime_conventions(self):
        return self._openfoam.get_case_runtime_conventions()

    def validate_configuration(self, spec: Any) -> tuple[Any, ...]:
        del spec
        return ()

    def validate_run_semantics(self, context: dict[str, Any]) -> tuple[Any, ...]:
        del context
        return ()

    def predict_data_artifacts(self, case_root: Path, spec: Any) -> tuple[Any, ...]:
        del case_root, spec
        return ()

    def get_solver_commands(self) -> frozenset[str]:
        return frozenset()

    def get_auxiliary_commands(self) -> frozenset[str]:
        return frozenset(UTILITY_MANIFESTS)

    def get_utility_manifests(self) -> dict[str, Any]:
        return UTILITY_MANIFESTS

    def get_utility_roots(self) -> tuple[Path, ...]:
        return ()

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        del case_root
        return {}

    def get_samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        del resolved
        return {}

    def get_selected_start_time(self, case_root: Path, resolved_case: dict[str, Any]) -> str:
        return self._openfoam.get_selected_start_time(case_root, resolved_case)

    def get_override_schema(self, tutorial_name: str, make_spec_info: dict[str, Any]) -> dict[str, Any]:
        del make_spec_info
        if tutorial_name in {
            HUMAN_TREE_TUTORIAL_NAME,
            PIG_MORPHOMETRIC_TREE_TUTORIAL_NAME,
        }:
            from .tutorials import (
                HUMAN_TREE_INPUT_PATHS,
                PIG_MORPHOMETRIC_TREE_INPUT_PATHS,
            )

            paths = (
                HUMAN_TREE_INPUT_PATHS
                if tutorial_name == HUMAN_TREE_TUTORIAL_NAME
                else PIG_MORPHOMETRIC_TREE_INPUT_PATHS
            )

            return {
                "input_overrides": {
                    "description": "JSON object mapping reviewed cardiacCore inputs to values. The tree dictionary is fixed in this workflow.",
                    "paths": paths,
                },
            }
        if tutorial_name != TUTORIAL_NAME:
            return {}
        return {
            "input_overrides": {
                "description": "JSON object mapping reviewed cardiacCore input paths to values.",
                "paths": tuple(entry.driver_path for entry in CATALOG.entries),
            },
        }

    def get_run_document_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["preprocessing"],
            "properties": {"preprocessing": {"type": "object"}},
            "additionalProperties": False,
        }

    def build_run_document_config(self, spec):
        from .run_document_config import build_config

        return build_config(spec)

    def get_dict_entry_catalog(self) -> dict[str, Any]:
        return {name: list(entries) for name, entries in DOCUMENTS.items()}

    def get_named_catalogs(self) -> dict[str, Any]:
        return {
            "cardiaccore_conditional_inputs": CONDITIONAL_INPUTS,
            "cardiaccore_tree_validation": TREE_VALIDATION_CONTRACT,
        }

    def get_solve_step_commands(self) -> frozenset[str]:
        return frozenset()

    def get_telemetry_source_globs(self, command: str) -> tuple[str, ...]:
        del command
        return ()

    def get_extra_provenance_paths(self, case_root: Path) -> tuple[Any, ...]:
        del case_root
        return ()

    def get_generated_output_globs(
        self,
        case_root: Path,
        resolved_case: dict[str, Any],
        selected_start_time: str,
    ) -> tuple[str, ...]:
        """Exclude utility outputs from source-input provenance.

        A consuming DAG step still takes precedence, so ``0/Conductivity``
        remains an explicit input to ``setPurkinjeSlab`` after the preceding
        utility has generated it.
        """
        del case_root, resolved_case, selected_start_time
        return tuple(sorted({
            produced.path_pattern
            for manifest in UTILITY_MANIFESTS.values()
            for produced in manifest.produces
        }))

    def get_artifact_value_reader(self, artifact_format: str) -> None:
        del artifact_format
        return None

    def get_environment_diagnostics(
        self,
        workflow_dag: dict[str, Any] | None,
        *,
        env: dict[str, str] | None = None,
        explicit_bashrc: str | None = None,
        driver_context: Any | None = None,
    ) -> tuple[Any, ...]:
        return self._openfoam.get_environment_diagnostics(
            workflow_dag,
            env=env,
            explicit_bashrc=explicit_bashrc,
            driver_context=driver_context,
        )

    def get_loaded_environment(
        self, *, explicit_bashrc: str | None = None, driver_context: Any | None = None,
    ) -> dict[str, str]:
        return self._openfoam.get_loaded_environment(
            explicit_bashrc=explicit_bashrc,
            driver_context=driver_context,
        )

    def get_configured_environment(
        self, env: dict[str, str], driver_context: Any | None,
    ) -> dict[str, str]:
        return self._openfoam.get_configured_environment(env, driver_context)

    def get_function_object_field_diagnostics(
        self, case_root: Path, *, samplable: dict[str, Any],
    ) -> tuple[Any, ...]:
        return self._openfoam.get_function_object_field_diagnostics(
            case_root, samplable=samplable,
        )

    def get_case_dict_key_diagnostics(
        self,
        case_root: Path,
        *,
        catalogued_paths: tuple[str, ...],
        dict_relpaths: tuple[str, ...],
    ) -> tuple[Any, ...]:
        return self._openfoam.get_case_dict_key_diagnostics(
            case_root,
            catalogued_paths=catalogued_paths,
            dict_relpaths=dict_relpaths,
        )
