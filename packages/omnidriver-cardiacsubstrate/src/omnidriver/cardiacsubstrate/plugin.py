"""cardiacSubstrateFOAM as a provider over the OpenFOAM layer: its records, catalogues and utilities."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.plugin_profile import load_plugin_profile
from omnidriver.core.utility_catalog import load_utility_manifests

from .catalogs.inputs import CATALOG
from .catalogs.support_boundary import SUPPORT_BOUNDARY



class CardiacSubstratePlugin:
    """The omniD plugin for cardiacSubstrateFOAM's documented preprocessing records."""

    @property
    def plugin_name(self) -> str:
        return "cardiacSubstrateFOAM"

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.cardiacsubstrate"

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

    def get_dictionary_catalog(self) -> DictionaryCatalog:
        return CATALOG

    def get_owned_documents(self) -> frozenset[str]:
        return frozenset(CATALOG.documents)

    def validate_run_semantics(self, case_root: Path, *, driver_context: Any) -> tuple[Any, ...]:
        """The catalogue's relations over each utility dictionary the resolved
        case holds."""
        from omnidriver.openfoam.case_rules import document_rule_diagnostics

        return document_rule_diagnostics(
            case_root, {f"system/{name}": entries for name, entries in CATALOG.documents.items()},
            mapping=self.get_profile().cxx_mapping, catalogue=CATALOG,
        )

    def get_utility_manifests(self) -> dict[str, Any]:
        return dict(load_utility_manifests(Path(__file__).parent / "utilities"))

    def get_named_catalogs(self) -> dict[str, Any]:
        # Caller annotations must not mutate declarations seen by later agents.
        return deepcopy({"cardiacsubstrate_support_boundary": SUPPORT_BOUNDARY})

    def get_generated_output_globs(self, case_root: Path, resolved_case: dict[str, Any]) -> tuple[str, ...]:
        """What cardiacSubstrateFOAM's utilities write, from their manifests: each writes a new field or set, never an input
        in place. A consuming DAG step still takes precedence, so ``0/Conductivity`` stays an input to
        ``setPurkinjeSlab`` after the preceding utility has generated it."""
        del case_root, resolved_case
        return tuple(sorted({
            produced.path_pattern for manifest in self.get_utility_manifests().values() for produced in manifest.produces
        }))

    # -- Tutorial records -----------------------------------------------------
    def get_tutorial_records(self) -> dict[str, Any]:
        from .records import TUTORIAL_RECORDS

        return TUTORIAL_RECORDS

    def get_record_key_validator(self, *, driver_context: Any):
        from .record_key_validation import record_key_validator

        return record_key_validator

    def get_record_key_catalog(self, case_root: Path, *, driver_context: Any) -> tuple:
        from .record_key_validation import record_key_catalog

        return record_key_catalog(case_root)

    def select_applicable_record_keys(self, keys: tuple, case_root: Path) -> tuple:
        from .record_key_validation import applicable_record_keys

        return applicable_record_keys(keys, case_root)

    def get_agent_guidance(self) -> tuple[dict[str, str], ...]:
        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "cardiacSubstrateFOAM: records, study keys and coordinate conventions", "text": text},)
