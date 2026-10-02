"""A minimal, no-domain plugin used by Core contract tests."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile


class MinimalTestPlugin:
    """Implements only the required plugin contract; adds no solver meaning."""

    #: Declared as a CLASS attribute, not only assigned in ``__init__``.
    #: Subclasses in this suite (e.g. ``test_provenance_inputs.py``'s
    #: ``_FakePlugin``) override ``__init__`` without calling ``super()``, so an
    #: instance-only attribute would not exist on them and ``get_profile``
    #: would raise ``AttributeError``. A class default resolves for every
    #: instance, which is what lets ``get_profile`` read ``self._entrypoint``
    #: directly instead of defensively.
    _entrypoint: str | None = None

    #: Class-level defaults for the same reason as ``_entrypoint``: a subclass
    #: that overrides ``__init__`` without calling ``super()`` must still
    #: resolve them.
    _solver_commands: frozenset[str] = frozenset()
    _telemetry_globs: dict[str, tuple[str, ...]] = {}
    #: Tutorial-record test seams. Empty by default: a plugin declaring no
    #: records/validator/comparator is the ordinary case -- this plugin
    #: still implements all three hooks (returning the empty/None defaults
    #: below), so their own adapters see a declared hook and call it, and
    #: most tests never need these constructor arguments at all.
    _tutorial_records: dict = {}
    _record_key_validator = None
    _case_value_comparator = None

    def __init__(
        self,
        *,
        entrypoint: str | None = None,
        solver_commands: frozenset[str] | set[str] | None = None,
        telemetry_globs: dict[str, tuple[str, ...]] | None = None,
        tutorial_records: dict | None = None,
        record_key_validator=None,
        case_value_comparator=None,
    ) -> None:
        """Declare just enough for a test to be non-vacuous."""
        self._entrypoint = entrypoint
        if solver_commands is not None:
            self._solver_commands = frozenset(solver_commands)
        if telemetry_globs is not None:
            self._telemetry_globs = dict(telemetry_globs)
        if tutorial_records is not None:
            self._tutorial_records = dict(tutorial_records)
        if record_key_validator is not None:
            self._record_key_validator = record_key_validator
        if case_value_comparator is not None:
            self._case_value_comparator = case_value_comparator

    @property
    def plugin_name(self) -> str:
        return "minimal test plugin"

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.test-minimal"

    @property
    def plugin_version(self) -> str:
        return "1.0.0"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    def get_profile(self) -> PluginProfile:
        case_files: tuple[CaseFileRule, ...] = ()
        dictionaries: list[dict[str, str]] = []
        if self._entrypoint is not None:
            case_files = (
                CaseFileRule(
                    path=self._entrypoint,
                    kind="case_script",
                    role="x-test.case_script",
                    required="conditional",
                ),
            )
            dictionaries = [{
                "path": self._entrypoint,
                "kind": "case_script",
                "role": "x-test.case_script",
                "required": "conditional",
            }]
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
                "case_profile": {"dictionaries": dictionaries},
            },
        )

    def get_capabilities(self):
        return {}

    def get_case_runtime_conventions(self) -> CaseRuntimeConventions:
        entrypoints = () if self._entrypoint is None else (self._entrypoint,)
        return CaseRuntimeConventions(
            case_entrypoints=entrypoints,
            case_script_commands=entrypoints,
        )

    def validate_configuration(self, spec):
        return ()

    def validate_run_semantics(self, context):
        return ()

    def predict_data_artifacts(self, case_root, spec):
        return ()

    def get_solver_commands(self) -> frozenset[str]:
        return self._solver_commands

    def get_auxiliary_commands(self) -> frozenset[str]:
        return frozenset()

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

    def get_solve_step_commands(self) -> frozenset:
        return frozenset()

    def get_telemetry_source_globs(self, command: str) -> tuple:
        return self._telemetry_globs.get(command, ())

    def get_extra_provenance_paths(self, case_root) -> tuple:
        del case_root
        return ()

    def get_artifact_value_reader(self, artifact_format: str):
        del artifact_format
        return None

    def get_run_document_config_schema(self) -> dict:
        """No solver semantics means no constraint on the config shape."""
        return {"type": "object", "additionalProperties": True}

    def get_tutorial_records(self) -> dict:
        return dict(self._tutorial_records)

    def get_record_key_validator(self):
        return self._record_key_validator

    def get_case_value_comparator(self):
        return self._case_value_comparator


# Compatibility alias for Core tests that have not yet been migrated.  New
# tests must import ``MinimalTestPlugin`` so their fixture does not encode an
# OpenFOAM identity by name.
MinimalOpenFOAMPlugin = MinimalTestPlugin
