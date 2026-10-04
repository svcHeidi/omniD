"""The cardiacFoam implementation of the SolverPlugin interface."""

from __future__ import annotations

from typing import TYPE_CHECKING
from functools import lru_cache
from pathlib import Path

from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS
from omnidriver.cardiacfoam.common_dict_entries import (
    PHYSICS_PROPERTY_ENTRIES,
    PRE_PACING_PROPERTY_ENTRIES,
)
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.openfoam.control_dict import CONTROL_DICT_ENTRIES

if TYPE_CHECKING:
    from omnidriver.core.contracts.dictionary import DictEntry
    from omnidriver.core.runtime.models import TutorialSpec, DataArtifact


class CardiacFoamPlugin:
    """
    Plugin implementation for cardiacFoam.
    Provides domain-specific dictionaries, tutorials, and capabilities
    to the generic omnidriver engine.
    """
    
    @property
    def plugin_name(self) -> str:
        return "cardiacFoam"

    @property
    def plugin_id(self) -> str:
        return "org.cardiacfoam"

    @property
    def plugin_version(self) -> str:
        return "0.1.0"

    @property
    def plugin_api_version(self) -> str:
        return "3"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        from omnidriver.core.plugin_profile import load_plugin_profile

        return load_plugin_profile(Path(__file__).parent / "plugin.yaml")

    def get_configured_environment(self, env, driver_context):
        """Apply this plugin's declared backend and build-manifest contract.

        `provider_stack.py` classifies ``get_configured_environment`` as
        ``chain``, so when this provider is composed with
        openfoam-environment's, that provider's (generic, no-op)
        contribution runs first and this one runs on its result -- no
        back-channel required.
        """
        del driver_context
        from omnidriver.cardiacfoam.runtime_profile import (
            configure_runtime_environment,
        )

        configured_env, _error = configure_runtime_environment(env)
        return configured_env

    def get_dict_entries(self) -> tuple[DictEntry, ...]:
        """The same entries :meth:`get_dictionary_catalog` holds, flat."""
        entries: list[DictEntry] = list(PHYSICS_PROPERTY_ENTRIES)
        entries.extend(CONTROL_DICT_ENTRIES)
        entries.extend(PRE_PACING_PROPERTY_ENTRIES)
        for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
            entries.extend(group)
        return tuple(entries)

    @staticmethod
    @lru_cache(maxsize=1)
    def get_dictionary_catalog() -> DictionaryCatalog:
        electro_entries: list[DictEntry] = []
        for group in ELECTRO_PROPERTY_ENTRY_GROUPS.values():
            electro_entries.extend(group)
        return DictionaryCatalog({
            "electroProperties": tuple(electro_entries),
            "physicsProperties": PHYSICS_PROPERTY_ENTRIES,
            "controlDict": CONTROL_DICT_ENTRIES,
            "prePacingProperties": PRE_PACING_PROPERTY_ENTRIES,
        })

    def resolve_case_models(self, case_root: Path) -> dict:
        """Best-effort ``{"solver", "ionic_model", "active_tension"}`` from a
        case's ``constant/electroProperties``. Never raises."""
        from omnidriver.cardiacfoam.case_introspection import (
            resolve_case_models,
        )

        return resolve_case_models(case_root)

    def get_samplable_fields(self, resolved: dict) -> dict:
        """Field names the resolved cardiac model exposes, by region."""
        from omnidriver.cardiacfoam.case_introspection import (
            samplable_fields,
        )

        return samplable_fields(resolved)

    def get_solve_step_commands(self) -> frozenset:
        """Commands that actually run the solver, for telemetry collection."""
        from omnidriver.cardiacfoam.runtime_evidence import (
            solve_step_commands,
        )

        return solve_step_commands()

    def get_extra_provenance_paths(self, case_root) -> tuple:
        """Extra inputs the provenance snapshot must digest beyond system/ and constant/."""
        from omnidriver.cardiacfoam.runtime_evidence import (
            extra_provenance_paths,
        )

        return extra_provenance_paths(case_root)

    def get_artifact_value_reader(self, artifact_format: str):
        """Reader for a cardiac artifact format, or None if unsupported."""
        from omnidriver.cardiacfoam.runtime_evidence import (
            artifact_value_reader,
        )

        return artifact_value_reader(artifact_format)

    def get_supported_mutation_modes(self) -> "frozenset[str]":
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request, *, driver_context):
        """The shared OpenFOAM layer resolves an edit to an existing case."""
        del driver_context
        from omnidriver.openfoam.case_rendering import patch_mutation

        return patch_mutation(request, owner_id=self.plugin_id)

    def get_generated_output_globs(self, case_root, resolved_case) -> tuple:
        """Fixed mesh-diagnostic outputs nothing in src/ or applications/ reads."""
        from omnidriver.cardiacfoam.case_provenance import (
            generated_output_globs,
        )

        return generated_output_globs(case_root, resolved_case)

    @staticmethod
    def get_owned_documents() -> frozenset[str]:
        return frozenset({"electroProperties", "physicsProperties", "prePacingProperties"})

    def get_named_catalogs(self) -> dict:
        """This plugin's own catalogs -- ionic models and active-tension
        models -- namespaced under introspection's generic
        ``plugin_catalogs`` key instead of core-hardcoded field names."""
        from omnidriver.cardiacfoam.named_catalogs import (
            named_catalogs,
        )

        return named_catalogs()

    def get_record_key_validator(self):
        """See ``record_key_validation.py`` for the three rules it implements."""
        from omnidriver.cardiacfoam.record_key_validation import record_key_validator

        return record_key_validator

    def get_record_key_catalog(self, case_root) -> tuple:
        """Every key a study may name for the case at ``case_root``: the
        same rules ``get_record_key_validator`` refuses by
        (``record_key_validation.record_key_catalog``; conformance C10)."""
        from omnidriver.cardiacfoam.record_key_validation import record_key_catalog

        return record_key_catalog(case_root)

    def select_applicable_record_keys(self, keys, case_root) -> tuple:
        """``keys`` less those the case's solver rules out
        (``record_key_validation.applicable_record_keys``)."""
        from omnidriver.cardiacfoam.record_key_validation import applicable_record_keys

        return applicable_record_keys(keys, case_root)

    def get_agent_guidance(self) -> tuple:
        """What this stack's validator and catalogues enforce, and the
        pre-processing rule, stated for an agent before it writes a study
        (``guidance.md``; conformance C10).
        The case's own README reaches the agent separately, through the
        ``case.documentation`` role the OpenFOAM layer's profile declares."""
        from importlib import resources

        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "cardiacFOAM: how omniD checks a study's keys, and where the mesh comes from", "text": text},)

    def get_tutorial_records(self) -> dict:
        from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS

        return TUTORIAL_RECORDS

    def validate_run_semantics(self, case_root):
        """The catalogue's relations and cardiacFOAM's cross-field rules,
        over the resolved case's ``electroProperties``."""
        from omnidriver.cardiacfoam.validation import case_diagnostics

        return case_diagnostics(case_root, mapping=self.get_profile().cxx_mapping)

    def predict_data_artifacts(self, case_root: Path, spec: TutorialSpec) -> tuple[DataArtifact, ...]:
        from omnidriver.cardiacfoam.artifacts_predictor import predict_cardiac_artifacts
        return predict_cardiac_artifacts(case_root, spec)

    def get_solver_commands(self) -> frozenset[str]:
        """This plugin's artifact-producing solver commands."""
        from omnidriver.cardiacfoam.command_authorization import (
            solver_commands,
        )

        return solver_commands()

    def get_auxiliary_commands(self) -> frozenset[str]:
        """Authorized plugin commands that do not produce the run's artifacts."""
        from omnidriver.cardiacfoam.command_authorization import (
            auxiliary_commands,
        )

        return auxiliary_commands()

    def get_utility_manifests(self) -> dict:
        """This plugin's ``utility.manifest.toml`` sidecars, by command name."""
        from omnidriver.cardiacfoam.command_authorization import (
            utility_manifests,
        )

        # utility_manifests() is cached and returns a read-only view; copy so a
        # caller mutating what it gets back cannot reach the shared cache.
        return dict(utility_manifests())
