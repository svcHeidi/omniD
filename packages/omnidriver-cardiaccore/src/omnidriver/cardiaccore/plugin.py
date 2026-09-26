"""Compose the declared cardiacCore workflows, catalogs and OpenFOAM capabilities."""

from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import load_plugin_profile

from .catalogs.inputs import CATALOG, CONDITIONAL_INPUTS, DOCUMENTS
from .agent_guidance import describe_guidance
from .catalogs.support_boundary import FIELD_CONVENTIONS, SUPPORT_BOUNDARY
from .catalogs.operations import OPERATIONS, utility_index
from .catalogs.purkinje import TREE_VALIDATION_CONTRACT
from .workflows.preprocessing import (
    HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME,
    HUMAN_PURKINJE_SLAB_TUTORIAL_NAME,
    PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME,
    PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME,
    PURKINJE_TREE_INPUT_PATHS,
    make_human_purkinje_endocardial_spec,
    make_human_purkinje_slab_spec,
    make_pig_morphometric_purkinje_spec,
    make_pig_transmural_purkinje_spec,
)
from .catalogs.utilities import UTILITY_MANIFESTS


class CardiacCorePlugin:
    """OmniD API-v2 adapter for a documented cardiacCore preprocessing slice."""

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
        """This provider has no domain catalogue core cannot already compose.

        **Changed by Task 10 (2026-09-22).** This used to build the whole
        manifest itself via ``build_capability_manifest`` and hand it back to
        core, which just returned it unchanged -- duplicating what
        ``plugin_capabilities._CapabilityManifestAdapter.manifest`` now
        computes directly from the composed ``command_authorization``/
        ``case_introspection``/``case_runtime_conventions`` reads over this
        same provider stack. cardiacCore declares no domain vocabulary beyond
        those (its named catalogues -- conditional inputs, tree validation,
        etc. -- are exposed through ``get_named_catalogs`` instead), so there
        is nothing left for this method to add.
        """
        return {}

    def get_tutorial_catalog(self) -> dict[str, Any]:
        return {
            "registered_tutorials": (
                HUMAN_PURKINJE_SLAB_TUTORIAL_NAME,
                HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME,
                PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME,
                PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME,
            ),
            "spec_factories": {
                HUMAN_PURKINJE_SLAB_TUTORIAL_NAME: make_human_purkinje_slab_spec,
                HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME: (
                    make_human_purkinje_endocardial_spec
                ),
                PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME: (
                    make_pig_morphometric_purkinje_spec
                ),
                PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME: (
                    make_pig_transmural_purkinje_spec
                ),
            },
        }

    def get_tutorial_displays(self) -> tuple[Any, ...]:
        return ()

    def validate_configuration(self, spec: Any) -> tuple[Any, ...]:
        """Check this spec's workflow-relevant catalog entries at plan time.

        Wired 2026-09-22 (audit finding S2). This returned ``()``
        unconditionally while a complete implementation sat unreachable in
        ``workflows/run_config.py``, so a co-required pair left half-set in
        the resolved case went unreported until a RunDocument happened to
        expose it at run/step time.
        """
        from .workflows.run_config import validate_configuration

        return validate_configuration(spec, self)

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

    def get_override_schema(self, tutorial_name: str, make_spec_info: dict[str, Any]) -> dict[str, Any]:
        del make_spec_info
        if tutorial_name in {
            HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME,
            PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME,
            PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME,
        }:
            return {
                "input_overrides": {
                    "description": "JSON object mapping reviewed cardiacCore inputs to values. The tree dictionary is fixed in this workflow.",
                    "paths": PURKINJE_TREE_INPUT_PATHS,
                },
            }
        if tutorial_name != HUMAN_PURKINJE_SLAB_TUTORIAL_NAME:
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
        from .workflows.run_config import build_config

        return build_config(spec)

    def get_dict_entry_catalog(self) -> dict[str, Any]:
        return {name: list(entries) for name, entries in DOCUMENTS.items()}

    def get_named_catalogs(self) -> dict[str, Any]:
        # Caller annotations must not mutate declarations seen by later agents.
        return deepcopy({
            "cardiaccore_conditional_inputs": CONDITIONAL_INPUTS,
            "cardiaccore_tree_validation": TREE_VALIDATION_CONTRACT,
            "cardiaccore_field_conventions": FIELD_CONVENTIONS,
            "cardiaccore_python_utilities": utility_index(),
            "cardiaccore_support_boundary": SUPPORT_BOUNDARY,
            "cardiaccore_operations": OPERATIONS,
            "cardiaccore_agent_guidance": describe_guidance(),
        })

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
    ) -> tuple[str, ...]:
        """Exclude utility outputs from source-input provenance.

        A consuming DAG step still takes precedence, so ``0/Conductivity``
        remains an explicit input to ``setPurkinjeSlab`` after the preceding
        utility has generated it.
        """
        del case_root, resolved_case
        return tuple(sorted({
            produced.path_pattern
            for manifest in UTILITY_MANIFESTS.values()
            for produced in manifest.produces
        }))

    def get_artifact_value_reader(self, artifact_format: str) -> None:
        del artifact_format
        return None

    # -- CaseWriterCapability -------------------------------------------------
    def get_supported_mutation_modes(self) -> "frozenset[str]":
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request: Any, *, driver_context: Any) -> Any:
        """Delegate to ``workflows.overrides``, this package's one semantic
        owner of a case mutation (Phase 2 Task 8)."""
        from .workflows.overrides import resolve_patch_mutation

        del driver_context
        return resolve_patch_mutation(request)

