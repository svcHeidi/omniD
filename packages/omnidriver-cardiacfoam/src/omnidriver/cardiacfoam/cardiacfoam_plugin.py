"""The cardiacFoam implementation of the SolverPlugin interface."""

from __future__ import annotations

from typing import TYPE_CHECKING
from functools import lru_cache
from pathlib import Path
from omnidriver.core.plugin_interface import SolverPlugin, CapabilityManifest

from omnidriver.cardiacfoam.dict_entries_catalog import ELECTRO_PROPERTY_ENTRY_GROUPS, HETEROGENEITY_MODELS
from omnidriver.cardiacfoam.common_dict_entries import (
    CONTROL_DICT_ENTRIES,
    PHYSICS_PROPERTY_ENTRIES,
)
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

if TYPE_CHECKING:
    from omnidriver.core.runtime.models import TutorialSpec, DataArtifact
    from pathlib import Path


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
        return "2"

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

    def get_dict_groups(self) -> dict[str, tuple[DictEntry, ...]]:
        """
        Return the dictionary entries organized by logical group.
        """
        return ELECTRO_PROPERTY_ENTRY_GROUPS

    def get_dict_entries(self) -> tuple[DictEntry, ...]:
        """
        Aggregate and return all dictionary entries specific to cardiacFoam.

        Must stay in step with :meth:`get_dictionary_catalog` -- both are
        ``DictionaryCatalogCapability`` accessors over the same catalogue, so
        every source folded into the catalog (``PHYSICS_PROPERTY_ENTRIES``,
        each electro-property group, and ``CONTROL_DICT_ENTRIES``) must be
        folded in here too.
        """
        entries: list[DictEntry] = list(PHYSICS_PROPERTY_ENTRIES)
        entries.extend(CONTROL_DICT_ENTRIES)
        for group in self.get_dict_groups().values():
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
        })

    def get_capabilities(self) -> CapabilityManifest:
        """Return what only cardiacFoam can add to the capability manifest.

        Core builds the base capability manifest itself, composing
        ``command_authorization``/``case_introspection``/
        ``case_runtime_conventions`` over the same provider stack. The model
        catalogues are not here: ``describe`` carries them once, as
        ``plugin_catalogs`` (:meth:`get_named_catalogs`).
        """
        return {"heterogeneity_models": HETEROGENEITY_MODELS}

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

    def get_telemetry_source_globs(self, command: str) -> tuple:
        """Where this command's solver log lands beyond captured stdout."""
        from omnidriver.cardiacfoam.runtime_evidence import (
            telemetry_source_globs,
        )

        return telemetry_source_globs(command)

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

    # -- CaseWriterCapability --------------------------------------------
    def get_supported_mutation_modes(self) -> "frozenset[str]":
        return frozenset({"synthesize", "clone_and_patch"})

    def resolve_case_mutation(self, request, *, driver_context):
        """``dict_builder`` resolves a from-scratch case synthesis; the shared
        OpenFOAM layer resolves an edit to a case that already exists."""
        del driver_context
        if request.mode == "synthesize":
            from omnidriver.cardiacfoam.dict_builder import resolve_synthesis_mutation

            return resolve_synthesis_mutation(request)
        if request.mode == "clone_and_patch":
            from omnidriver.openfoam.case_rendering import patch_mutation

            return patch_mutation(request, owner_id=self.plugin_id)
        raise ValueError(
            f"cardiacFoam resolves synthesize and clone_and_patch requests "
            f"only, not {request.mode!r}"
        )

    def get_required_inputs(self, case_root, resolved_case) -> tuple:
        """Model-dependent required inputs (CaseProvenanceCapability). See
        ``case_provenance.py`` for why this defers to the safe default."""
        from omnidriver.cardiacfoam.case_provenance import (
            required_inputs,
        )

        return required_inputs(case_root, resolved_case)

    def get_generated_output_globs(self, case_root, resolved_case) -> tuple:
        """Fixed mesh-diagnostic outputs nothing in src/ or applications/ reads."""
        from omnidriver.cardiacfoam.case_provenance import (
            generated_output_globs,
        )

        return generated_output_globs(case_root, resolved_case)

    def get_dict_entry_catalog(self) -> dict:
        """Dictionary entries arranged by cardiacFoam's own document names.

        ``physicsProperties`` is a flat sequence while ``electroProperties``
        is grouped: that mirrors the two OpenFOAM dictionaries this solver
        reads and is deliberately not a core convention."""
        return {
            "physicsProperties": list(self.get_dictionary_catalog().entries_for("physicsProperties")),
            "electroProperties": {
                group_name: list(entries) for group_name, entries in self.get_dict_groups().items()
            },
        }

    def get_report_catalog(self) -> tuple:
        """Post-run reports this plugin offers. Core owns the machinery; the
        catalog is plugin data."""
        from omnidriver.cardiacfoam.reports import CARDIAC_REPORTS

        return CARDIAC_REPORTS

    def get_named_catalogs(self) -> dict:
        """This plugin's own catalogs -- ionic models and active-tension
        models -- namespaced under introspection's generic
        ``plugin_catalogs`` key instead of core-hardcoded field names."""
        from omnidriver.cardiacfoam.named_catalogs import (
            named_catalogs,
        )

        return named_catalogs()

    def get_record_key_validator(self):
        """This plugin's one ``RecordKeyValidationCapability`` answer for a
        cardiac stack. See ``record_key_validation.py``'s module docstring
        for the three rules it implements."""
        from omnidriver.cardiacfoam.record_key_validation import record_key_validator

        return record_key_validator

    def get_record_key_catalog(self, case_root) -> tuple:
        """Every key a study may name for the case at ``case_root``: the
        same rules ``get_record_key_validator`` refuses by
        (``record_key_validation.record_key_catalog``; conformance C10)."""
        from omnidriver.cardiacfoam.record_key_validation import record_key_catalog

        return record_key_catalog(case_root)

    def get_agent_guidance(self) -> tuple:
        """What this stack's validator and catalogues enforce, and the
        pre-processing rule, stated for an agent before it writes a study
        (``guidance.md``; conformance C10).
        The case's own README reaches the agent separately, through the
        ``case.documentation`` role this plugin's profile declares."""
        from importlib import resources

        text = resources.files(__package__).joinpath("guidance.md").read_text()
        return ({"title": "cardiacFOAM: how omniD checks a study's keys, and where the mesh comes from", "text": text},)

    def get_tutorial_records(self) -> dict:
        """This plugin's ``TutorialRecordCapability`` answer: every record
        this package registers, aggregated by ``records/__init__.py``."""
        from omnidriver.cardiacfoam.records import TUTORIAL_RECORDS

        return TUTORIAL_RECORDS

    def validate_configuration(self, spec: TutorialSpec) -> tuple[StrictDiagnostic, ...]:
        from pathlib import Path
        from omnidriver.cardiacfoam.detection import detect_myocardium_solver_name
        from omnidriver.core.planning_types import diagnostic as _diagnostic

        diagnostics = []
        case_root = Path(spec.case_root)
        electro_path = case_root / "constant" / "electroProperties"

        if electro_path.exists():
            try:
                detect_myocardium_solver_name(electro_path)
            except KeyError as exc:
                diagnostics.append(_diagnostic("error", "missing_solver", str(exc), source=str(electro_path)))

        return tuple(diagnostics)

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

    def get_utility_roots(self) -> tuple[Path, ...]:
        """Roots searched for this plugin's utility manifests."""
        from omnidriver.cardiacfoam.command_authorization import (
            utility_roots,
        )

        return utility_roots()
