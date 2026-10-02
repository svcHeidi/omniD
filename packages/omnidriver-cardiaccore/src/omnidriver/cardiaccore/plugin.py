"""Compose the declared cardiacCore workflows, catalogs and OpenFOAM capabilities."""

from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.core.utility_catalog import load_utility_manifests

from .catalogs.inputs import CATALOG, CONDITIONAL_INPUTS, DOCUMENTS
from .catalogs.support_boundary import FIELD_CONVENTIONS, SUPPORT_BOUNDARY
from .catalogs.operations import OPERATIONS, utility_index
from .catalogs.purkinje import TREE_VALIDATION_CONTRACT


# cardiacFoam's own manifests declare newVtkUnstructuredToFoam and
# 1DgraphToFoam; declaring them here too would collide in the provider stack's
# "map" composition, which refuses duplicate names without an overrides marker.
_UTILITIES_ROOT = Path(__file__).parent / "utilities"


@lru_cache(maxsize=1)
def _utility_manifests() -> Any:
    """Parsed once: loading walks the sidecar tree. Read-only so the shared
    cache cannot be corrupted through a returned mapping."""
    return MappingProxyType(load_utility_manifests(_UTILITIES_ROOT))


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

        ``plugin_capabilities._CapabilityManifestAdapter.manifest`` computes
        the capability manifest directly from the composed
        ``command_authorization``/``case_introspection``/
        ``case_runtime_conventions`` reads over this provider stack.
        cardiacCore's own named catalogues (conditional inputs, tree
        validation, etc.) are exposed through ``get_named_catalogs`` instead.
        """
        return {}

    def validate_configuration(self, spec: Any) -> tuple[Any, ...]:
        """A generic case carries its configuration in its own files."""
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
        return frozenset(_utility_manifests())

    def get_utility_manifests(self) -> dict[str, Any]:
        return dict(_utility_manifests())

    def get_utility_roots(self) -> tuple[Path, ...]:
        return (_UTILITIES_ROOT,)

    def resolve_case_models(self, case_root: Path) -> dict[str, Any]:
        del case_root
        return {}

    def get_samplable_fields(self, resolved: dict[str, Any]) -> dict[str, tuple[str, ...]]:
        del resolved
        return {}

    def get_run_document_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["preprocessing"],
            "properties": {"preprocessing": {"type": "object"}},
            "additionalProperties": False,
        }

    def build_run_document_config(self, spec):
        """Every spec is a generic case: its configuration lives in the case
        files, never in the run document."""
        del spec
        return {}, ()

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
            for manifest in _utility_manifests().values()
            for produced in manifest.produces
        }))

    def get_artifact_value_reader(self, artifact_format: str) -> None:
        del artifact_format
        return None

    # -- Tutorial records -----------------------------------------------------
    def get_tutorial_records(self) -> dict[str, Any]:
        from .records import TUTORIAL_RECORDS

        return TUTORIAL_RECORDS

    def get_record_key_validator(self):
        from .record_key_validation import record_key_validator

        return record_key_validator

    def get_record_key_catalog(self, case_root: Path) -> tuple:
        from .record_key_validation import record_key_catalog

        return record_key_catalog(case_root)

    def get_agent_guidance(self) -> tuple[dict[str, str], ...]:
        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "cardiacCore: records, study keys and coordinate conventions", "text": text},)

    # -- CaseWriterCapability -------------------------------------------------
    def get_supported_mutation_modes(self) -> "frozenset[str]":
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request: Any, *, driver_context: Any) -> Any:
        """Delegate to ``workflows.overrides``, this package's one semantic
        owner of a case mutation."""
        from .workflows.overrides import resolve_patch_mutation

        del driver_context
        return resolve_patch_mutation(request)

