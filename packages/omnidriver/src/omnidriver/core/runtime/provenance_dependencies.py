"""Compose ``RuntimeDependency`` declarations into ``ProvenanceComponent``s.

A dependency's resolved path is not under any case root, so each is
fingerprinted relative to its own parent directory and the declared
dependency name is restored as the component's identity -- a library found
via a different search directory must still compare as the same dependency.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..plugin_capabilities import RuntimeDependency
from .provenance import ProvenanceComponent, component_for_path


def component_for_runtime_dependency(dependency: RuntimeDependency) -> ProvenanceComponent:
    """Fingerprint one runtime dependency, present or not."""
    if dependency.path is None:
        return ProvenanceComponent(
            kind="runtime_dependency",
            path=dependency.name,
            role="required_input",
            method="unavailable",
            strength="unavailable",
        )
    component = component_for_path(
        dependency.path,
        kind="runtime_dependency",
        relative_to=dependency.path.parent,
    )
    return replace(component, path=dependency.name)


def component_for_verified_absence(dependency: RuntimeDependency) -> ProvenanceComponent:
    """Fingerprint a declared optional path that inspection observed absent.

    If the path appeared after closure inspection, return its ordinary content
    component instead.  That makes the snapshot differ rather than blessing a
    stale absence.  Any failure to verify the filesystem state remains
    unavailable and therefore non-resumable.
    """
    if dependency.path is None:
        return ProvenanceComponent(
            kind="runtime_dependency",
            path=dependency.name,
            role="optional_input",
            method="unavailable",
            strength="unavailable",
        )
    path = Path(dependency.path)
    try:
        exists = path.exists()
    except OSError:
        exists = None
    if exists is True:
        return replace(
            component_for_runtime_dependency(dependency), role="optional_input",
        )
    if exists is False:
        return ProvenanceComponent(
            kind="runtime_dependency",
            path=dependency.name,
            role="optional_input",
            method="verified_absence",
            strength="absence",
            digest=None,
            size=None,
            mtime_ns=None,
            link_target=None,
        )
    return ProvenanceComponent(
        kind="runtime_dependency",
        path=dependency.name,
        role="optional_input",
        method="unavailable",
        strength="unavailable",
    )
