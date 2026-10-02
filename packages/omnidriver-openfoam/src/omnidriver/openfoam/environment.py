"""OpenFOAM environment adapter with no solver-specific semantics."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from omnidriver.core.plugin_interface import driver_context as make_driver_context

from .case_runtime_conventions import openfoam_case_runtime_conventions
from .command_authorization import is_installed_openfoam_application, openfoam_runtime_commands
from .profile import load_openfoam_profile


def _read_config_value_by_key_path(file_path: Path, key_path):
    """Split a key-path tuple into ``read_foam_entry``'s scope/key pair; a
    bare string is refused rather than iterated character-by-character."""
    from .case_planning import (
        HEX_CELL_COUNTS_KEY_PATH,
        hex_cell_counts_expected_blocks,
        read_hex_cell_counts,
    )
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
    if segments[:1] == HEX_CELL_COUNTS_KEY_PATH:
        # This key path has no single literal dictionary key, so
        # `read_hex_cell_counts` parses the `hex (` grammar directly instead
        # of going through the scope/key split below; the expected block
        # count travels with the key path itself (`hex_cell_counts_expected_blocks`).
        expected_blocks = hex_cell_counts_expected_blocks(segments)
        return read_hex_cell_counts(file_path, expected_blocks=expected_blocks)
    *scope, key = segments
    return read_foam_entry(file_path, key, scope=list(scope) if scope else None)


def _case_value_agree(value_kind: str, requested, current) -> bool:
    """Compares by the requested value's own Python type via
    ``values_agree``; ``value_kind`` is unused, kept only to match the
    comparator's signature."""
    from .literals import values_agree

    del value_kind
    return values_agree(requested, current)


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
        and the same directory in every parallel replica.

        ``conventions`` is the stack's merged declaration, not this plugin's
        own ``openfoam_case_runtime_conventions()``: a plugin stacked on top
        of OpenFOAM that redeclares ``replica_directory_globs`` must have its
        replicas walked here too.

        When ``selected_start_time`` answers ``None`` (no ``system/controlDict``,
        so this is not known to be an OpenFOAM case), this contributes no
        roots at all -- never the literal ``"0"``, which would be
        indistinguishable from a case that genuinely starts at time zero. See
        ``time_selection.selected_start_time``."""
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

    def get_plan_diagnostics(self, case_root, *, workflow_dag, env, scratch_root, driver_context):
        from .plan_diagnostics import plan_diagnostics

        return plan_diagnostics(
            case_root, workflow_dag=workflow_dag, env=env,
            scratch_root=scratch_root, driver_context=driver_context,
        )

    def explain_step_failure(self, log_text, case_root, *, driver_context):
        from .step_failure import missing_entry_diagnostics

        return missing_entry_diagnostics(log_text, case_root, driver_context)

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

    def get_parallel_steps(self, step, *, request, read_value, allocation):
        """A record's solve step in OpenFOAM's parallel form. The solve
        command is the solver plugin's (``get_solve_step_commands``); how
        any OpenFOAM solver runs in parallel is this layer's."""
        from .parallel_execution import parallel_steps_for_record

        return parallel_steps_for_record(step, request=request, read_value=read_value, allocation=allocation)

    def get_dict_key_scanner(self):
        from .dict_keys_scanner import catalog_report

        return catalog_report

    def get_case_runtime_conventions(self):
        return openfoam_case_runtime_conventions()

    def get_rendered_formats(self) -> "frozenset[str]":
        return frozenset({"openfoam_dictionary"})

    def render_case_files(
        self, resolved, *, snapshot_root, driver_context, execution_env=None,
    ):
        """Render this provider's declared format for whichever mode
        ``resolved`` carries."""
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
