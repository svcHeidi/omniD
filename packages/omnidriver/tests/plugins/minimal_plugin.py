"""A genuine no-domain plugin used by the cross-plugin contract tests."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_profile import CaseFileRule, PluginProfile
from omnidriver.core.contracts.dictionary_catalog import DictionaryCatalog


class MinimalOpenFOAMPlugin:
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

    def __init__(
        self,
        *,
        entrypoint: str | None = None,
        solver_commands: frozenset[str] | set[str] | None = None,
        telemetry_globs: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        """Declare just enough for a test to be non-vacuous.

        `entrypoint` declares an ``openfoam.entrypoint`` case-file rule.

        `solver_commands` and `telemetry_globs` exist because a plugin that
        declares NOTHING makes several core assertions trivially true. Asking
        an empty plugin for an undeclared command's globs and getting ``()``
        proves nothing -- it returns ``()`` for every input. The meaningful
        claim is the CONTRAST: a plugin that declares globs for one command
        still returns ``()`` for another. Same for command authorization,
        where core's suite otherwise never exercises
        ``validate_workflow_commands``'s ``plugin_commands`` branch with a
        non-empty set at all.

        All default to empty, so every existing no-argument construction in
        the suite is unchanged.
        """
        self._entrypoint = entrypoint
        if solver_commands is not None:
            self._solver_commands = frozenset(solver_commands)
        if telemetry_globs is not None:
            self._telemetry_globs = dict(telemetry_globs)

    @property
    def plugin_name(self) -> str:
        return "minimal OpenFOAM test plugin"

    @property
    def plugin_id(self) -> str:
        return "org.driverfoam.test-minimal"

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
                    role="openfoam.entrypoint",
                    required="conditional",
                ),
            )
            dictionaries = [{
                "path": self._entrypoint,
                "kind": "case_script",
                "role": "openfoam.entrypoint",
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

    def get_dict_entries(self):
        return ()

    def get_dictionary_catalog(self):
        return DictionaryCatalog({})

    def get_dict_groups(self):
        return {}

    def get_capabilities(self):
        return {}

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

    def get_override_schema(self, tutorial_name, make_spec_info):
        del tutorial_name, make_spec_info
        return {}

    def get_dict_entry_catalog(self):
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
