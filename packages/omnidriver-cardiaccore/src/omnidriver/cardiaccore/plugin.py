"""cardiacCore as a provider over the OpenFOAM layer: its records, catalogues and utilities."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any

from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.core.utility_catalog import load_utility_manifests

from .catalogs.inputs import CATALOG, CONDITIONAL_INPUTS
from .catalogs.support_boundary import FIELD_CONVENTIONS, SUPPORT_BOUNDARY


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
        return "3"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        return load_plugin_profile(Path(__file__).with_name("plugin.yaml"))

    def get_dict_entries(self) -> tuple[Any, ...]:
        return CATALOG.entries

    def get_dictionary_catalog(self) -> DictionaryCatalog:
        return CATALOG

    def get_owned_documents(self) -> frozenset[str]:
        return frozenset(CATALOG.documents)

    def validate_run_semantics(self, case_root: Path) -> tuple[Any, ...]:
        """The catalogue's relations over each utility dictionary the resolved
        case holds."""
        from .case_rules import case_diagnostics

        return case_diagnostics(case_root, mapping=self.get_profile().cxx_mapping)

    def get_auxiliary_commands(self) -> frozenset[str]:
        return frozenset(_utility_manifests())

    def get_utility_manifests(self) -> dict[str, Any]:
        return dict(_utility_manifests())

    def get_named_catalogs(self) -> dict[str, Any]:
        # Caller annotations must not mutate declarations seen by later agents.
        return deepcopy({
            "cardiaccore_conditional_inputs": CONDITIONAL_INPUTS,
            "cardiaccore_field_conventions": FIELD_CONVENTIONS,
            "cardiaccore_support_boundary": SUPPORT_BOUNDARY,
        })

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

    def get_supported_mutation_modes(self) -> "frozenset[str]":
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request: Any, *, driver_context: Any) -> Any:
        """The shared OpenFOAM layer resolves every edit to an existing case."""
        from omnidriver.openfoam.case_rendering import patch_mutation

        del driver_context
        return patch_mutation(request, owner_id=self.plugin_id)

