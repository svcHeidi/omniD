"""Validation for the OpenFOAM adapter's declarative profile vocabulary."""

from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_profile import PluginProfile, load_plugin_profile


OPENFOAM_CASE_FILE_ROLES = frozenset({
    "openfoam.control_dict",
    "openfoam.discretisation",
    "openfoam.solver_settings",
    "openfoam.decomposition",
    "openfoam.mesh_generation",
    "openfoam.case_directory",
    "openfoam.entrypoint",
    "openfoam.cleanup",
})


def load_openfoam_profile(path: str | Path) -> PluginProfile:
    """Load a profile and reject unsupported OpenFOAM role declarations."""
    profile = load_plugin_profile(path)
    unsupported = sorted(
        rule.role
        for rule in profile.case_files
        if rule.role.startswith("openfoam.")
        and rule.role not in OPENFOAM_CASE_FILE_ROLES
    )
    if unsupported:
        raise ValueError(
            f"Unsupported OpenFOAM case-file roles in {profile.path}: "
            + ", ".join(unsupported)
        )
    return profile
