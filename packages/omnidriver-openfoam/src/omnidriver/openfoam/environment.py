"""OpenFOAM environment adapter with no solver-specific semantics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as make_driver_context

from .case_runtime_conventions import openfoam_case_runtime_conventions
from .command_authorization import is_installed_openfoam_application, openfoam_runtime_commands
from .profile import load_openfoam_profile


def _read_config_value_by_key_path(file_path: Path, key_path):
    """Adapt core's ``ConfigValueCapability`` contract to ``read_foam_entry``.

    Core (``tutorial_records.split_unchanged``) always calls this with a
    KEY-PATH TUPLE -- never a dotted string -- e.g.
    ``("bidomainSolverCoeffs", "conductivitySource")`` for a nested key, or a
    one-element tuple such as ``("myocardiumSolver",)`` for a top-level one.
    ``read_foam_entry(file_path, key, *, scope=None)`` itself takes a plain
    leaf key plus a separate scope, so this is the split: every segment but
    the last is the scope, the last is the key.

    Before this existed, ``get_config_value_reader()`` handed back
    ``read_foam_entry`` unwrapped, so a caller passing a tuple silently
    handed it a ``key`` that was never a string at all (review finding B1).

    **Refuses a bare string outright (minor), rather than splitting it into
    characters.** ``tuple("myKey")`` silently produces
    ``('m', 'y', 'K', 'e', 'y')`` -- a caller that passed a single string
    instead of a one-element tuple would have every character treated as
    its own nested scope segment, reading nothing and returning ``None``
    with no error at all. The contract requires a tuple; a string (which
    Python happily iterates character-by-character) is refused by name
    instead of silently misinterpreted.
    """
    from .case_planning import HEX_CELL_COUNTS_KEY_PATH, read_hex_cell_counts
    from .mutators import read_foam_entry

    if isinstance(key_path, str):
        raise TypeError(
            f"a config value read needs a key-path TUPLE, not a bare string "
            f"({key_path!r}) -- iterating a string yields one scope segment "
            "per CHARACTER, which is never what a caller means"
        )
    segments = tuple(key_path)
    if not segments:
        raise ValueError("a config value read needs a non-empty key path")
    if segments == HEX_CELL_COUNTS_KEY_PATH:
        # The one synthetic key path this reader answers specially (step 4a,
        # 2026-09-25): `plan_block_mesh_resolution`'s own target shape has no
        # single literal dictionary key (module docstring), so
        # `read_hex_cell_counts` parses the `hex (` grammar directly rather
        # than going through `read_foam_entry`'s scope/key split below.
        return read_hex_cell_counts(file_path)
    *scope, key = segments
    return read_foam_entry(file_path, key, scope=list(scope) if scope else None)


def _case_value_agree(value_kind: str, requested, current) -> bool:
    """``CaseValueComparisonCapability``'s one answer for a whole OpenFOAM-
    owned stack (design doc
    ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
    §5, step 4a).

    ``get_case_value_comparator`` is a ``single``-shape composed member
    (``provider_stack._SHAPE["get_case_value_comparator"] == "single"``):
    this is the ONLY implementation on a real stack today (no cardiacFOAM
    plugin declares its own), so it must be correct for every
    ``value_kind`` a study might name, cardiac or OpenFOAM-owned alike --
    and it is, because it does not attempt to dispatch on ``value_kind`` at
    all. ``effective_values_agree`` (``apply_overrides.py``) already
    dispatches purely on the REQUESTED value's own Python type (a bool
    compares as a bool, a number as a float, a list/tuple/parenthesised
    vector as a tuple of floats, anything else as text) -- exactly the
    "typed, not string equality" comparison design step 4a asks for, reused
    rather than re-implemented. ``value_kind`` is accepted only to satisfy
    the capability's own contract (``(value_kind, requested, current) ->
    bool``); nothing here branches on it.
    """
    from .apply_overrides import effective_values_agree

    del value_kind
    return effective_values_agree(requested, current)


class OpenFOAMEnvironmentPlugin:
    """OpenFOAM conventions, without any solver scientific configuration."""

    @property
    def plugin_name(self) -> str:
        return "OpenFOAM environment"

    @property
    def plugin_id(self) -> str:
        return "org.omnidriver.openfoam.environment"

    @property
    def plugin_version(self) -> str:
        return "1"

    @property
    def plugin_api_version(self) -> str:
        return "2"

    @staticmethod
    @lru_cache(maxsize=1)
    def get_profile():
        return load_openfoam_profile(Path(__file__).with_name("openfoam-environment.yaml"))

    def get_capabilities(self):
        """This provider has no domain catalogue core cannot already compose.

        **Changed 2026-09-22 (final whole-branch review, bundled Minor).**
        This used to build the whole manifest itself via
        ``build_capability_manifest`` -- the exact plugin-assembles-its-own-
        manifest pattern Task 10 removed from ``CardiacFoamPlugin``/
        ``CardiacCorePlugin`` (see ``build_capability_manifest``'s own
        docstring and ``CardiacCorePlugin.get_capabilities``). Harmless in
        practice today, since ``get_capabilities`` is a ``single``-shape
        composed member and this environment provider is never the most
        specific in a composed stack, so this answer never won -- but
        inconsistent with Task 10's rule and a latent risk if that stopped
        holding. ``plugin_capabilities._CapabilityManifestAdapter.manifest``
        already builds ``allowed_commands``/``samplable_fields`` from the
        composed ``command_authorization``/``case_introspection``/
        ``case_runtime_conventions`` reads (which include this provider's
        own ``get_environment_commands``/``get_case_runtime_conventions``,
        standalone or composed), so there is nothing left for this method to
        add -- same as ``CardiacCorePlugin.get_capabilities()``.
        """
        return {}

    def get_tutorial_catalog(self):
        return {"registered_tutorials": (), "spec_factories": {}}

    def validate_configuration(self, spec):
        return ()

    def validate_run_semantics(self, context):
        return ()

    def predict_data_artifacts(self, case_root, spec):
        return ()

    def get_base_mesh_geometry_diagnostics(self, case_root):
        from .mesh_geometry import mesh_geometry_diagnostics

        return mesh_geometry_diagnostics(case_root)

    def get_environment_diagnostics(
        self, workflow_dag, *, env=None, environment_source=None, driver_context=None,
    ):
        """``environment_source`` is, for OpenFOAM, a bashrc to source."""
        from .environment_preflight import _environment_diagnostics

        return _environment_diagnostics(
            workflow_dag,
            env=env,
            bashrc_path=environment_source,
            driver_context=driver_context,
        )

    def get_configured_environment(self, env, driver_context):
        from .openfoam_environment import configure_plugin_environment

        return configure_plugin_environment(env, driver_context).env

    def get_loaded_environment(self, *, environment_source=None, driver_context=None):
        """``environment_source`` is, for OpenFOAM, a bashrc to source."""
        from .openfoam_environment import load_openfoam_environment

        return dict(
            load_openfoam_environment(
                bashrc_path=environment_source,
                driver_context=driver_context,
            ).env
        )

    def get_config_value_reader(self):
        return _read_config_value_by_key_path

    def get_case_value_comparator(self):
        return _case_value_agree

    def get_input_roots(self, case_root, resolved_case, *, conventions) -> tuple[str, ...]:
        """The state a run resumes from: the selected start-time directory,
        and the same directory in every parallel replica (I9). OpenFOAM's
        convention, moved here 2026-09-26 from core's provenance walk (spec
        2026-09-26-core-generality-design.md §2, A2); core no longer knows
        "start time" or replicas.

        ``conventions`` is the STACK's merged declaration -- the same value
        staging/discovery read -- not this plugin's own
        ``openfoam_case_runtime_conventions()`` (R2 fix, finding I2): a
        plugin stacked on top of OpenFOAM that redeclares
        ``replica_directory_globs`` must have its replicas walked here too,
        not just by staging.

        **Corrected 2026-09-26 (owner decision).** When ``selected_start_time``
        answers ``None`` -- no ``system/controlDict`` at all, so this is not
        (or not yet known to be) an OpenFOAM case by the owner's rule
        ("controlDict is how we know an OpenFOAM case exists") -- this
        contributes **no roots at all**: not a start folder, and not any
        replica's start folder either. Previously this named the literal
        string ``"0"`` in that case, indistinguishable from a real case that
        deliberately starts at time zero. See ``time_selection
        .selected_start_time``'s own docstring for the full rule and why
        `omnidriver-cardiaccore`'s Allrun-only,
        controlDict-less test case still needs exactly this answer."""
        del resolved_case
        from omnidriver.core.plugin_profile import is_replica_directory_name

        from .mutators import read_foam_entry
        from .time_selection import selected_start_time

        control_dict = next(
            rule.path
            for rule in self.get_profile().case_files
            if rule.role == "openfoam.control_dict"
        )
        start = selected_start_time(
            case_root,
            control_dict_relpath=control_dict,
            read_value=read_foam_entry,
            instance_directory_pattern=conventions.instance_directory_pattern,
        )
        if start is None:
            return ()
        globs = conventions.replica_directory_globs
        replicas = sorted(
            child.name for child in Path(case_root).iterdir()
            if child.is_dir() and is_replica_directory_name(child.name, globs)
        ) if Path(case_root).is_dir() else []
        return (start, *(f"{name}/{start}" for name in replicas))

    def get_function_object_field_diagnostics(self, case_root, *, samplable):
        from .function_object_fields import function_object_field_diagnostics

        return function_object_field_diagnostics(case_root, samplable=samplable)

    def get_case_dict_key_diagnostics(
        self, case_root, *, catalogued_paths, dict_relpaths,
    ):
        from .case_dict_keys import case_dict_key_diagnostics

        return case_dict_key_diagnostics(
            case_root,
            catalogued_paths=catalogued_paths,
            dict_relpaths=dict_relpaths,
        )

    def apply_overrides(
        self, overrides, *, case_root, driver_context, execution_env=None,
    ):
        from .apply_overrides import apply_overrides

        return apply_overrides(
            overrides, case_root=case_root, driver_context=driver_context,
            execution_env=execution_env,
        )

    def get_override_target_paths(self, overrides, *, case_root, driver_context):
        from .apply_overrides import override_target_paths

        return override_target_paths(
            overrides, case_root=case_root, driver_context=driver_context,
        )

    def inspect_effective_configuration(self, *, case_root, execution_env=None):
        from .effective_dictionary import inspect_effective_foam_configuration

        relpaths = tuple(
            rule.path
            for rule in self.get_profile().case_files
            if rule.kind == "openfoam_dictionary"
        )
        return inspect_effective_foam_configuration(
            case_root,
            relpaths,
            env=execution_env,
        )

    def get_environment_commands(self) -> frozenset[str]:
        return openfoam_runtime_commands()

    def is_installed_environment_command(self, command: str) -> bool:
        return is_installed_openfoam_application(command)

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

    def get_named_catalogs(self):
        return {}

    def get_override_scopes(self):
        return ()

    def get_dict_key_scanner(self):
        from .dict_keys_scanner import strict_dict_key_report

        return strict_dict_key_report

    def get_case_runtime_conventions(self):
        return openfoam_case_runtime_conventions()

    def build_run_document_config(self, spec):
        del spec
        return {}, ()

    # -- CaseWriterCapability: format ownership -------------------------------
    def get_rendered_formats(self) -> "frozenset[str]":
        return frozenset({"openfoam_dictionary"})

    def render_case_files(
        self, resolved, *, snapshot_root, driver_context, execution_env=None,
    ):
        """Render this provider's declared format for whichever mode
        ``resolved`` carries. ``clone_and_patch`` is Task 8; ``synthesize``
        is Task 9."""
        mode = resolved.request.mode
        if mode == "clone_and_patch":
            from .case_rendering import render_patch_case_files

            return render_patch_case_files(
                resolved, snapshot_root=snapshot_root, driver_context=driver_context,
                execution_env=execution_env, renderer_id=self.plugin_id,
            )
        if mode == "synthesize":
            from .case_rendering import render_synthesis_case_files

            return render_synthesis_case_files(
                resolved, snapshot_root=snapshot_root, driver_context=driver_context,
                execution_env=execution_env, renderer_id=self.plugin_id,
            )
        raise ValueError(
            f"OpenFOAM environment renders no case files for creation mode {mode!r}"
        )


def openfoam_environment_context():
    """Build the explicit OpenFOAM environment context for local callers."""

    return make_driver_context(
        OpenFOAMEnvironmentPlugin(), source="adapter:openfoam-environment"
    )
