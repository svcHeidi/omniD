from __future__ import annotations

from typing import Any, Iterable

from .runtime.workflow import (
    CASE_SCRIPT_COMMANDS,
    CORE_NEUTRAL_COMMANDS,
)


def utility_produces(
    utility_manifests: dict[str, Any],
) -> dict[str, tuple[str, ...]]:
    """The plugin utility commands the allowlist accepts, keyed to what they
    produce. Mirrors the acceptance rule in ``validate_workflow_commands``
    (only utilities that declare ``produces`` are accepted).

    Single owner: the advertised accept-surface (this module's manifest) and
    the enforced one (strict planning's artifact coverage) must not drift, so
    both derive from this one function rather than each keeping a copy.
    """

    return {
        command: tuple(produce.artifact_id for produce in manifest.produces)
        for command, manifest in utility_manifests.items()
        if manifest.produces
    }


def _utility_commands(utility_manifests: dict[str, Any]) -> dict[str, list[str]]:
    """JSON-shaped view of :func:`utility_produces` (lists, not tuples)."""

    return {
        command: list(artifacts)
        for command, artifacts in utility_produces(utility_manifests).items()
    }


def build_capability_manifest(
    *,
    environment_commands: Iterable[str] = (),
    plugin_commands: Iterable[str] = (),
    utility_manifests: dict[str, Any] | None = None,
    samplable_fields: dict[str, tuple[str, ...]] | None = None,
    case_script_commands: frozenset[str] = CASE_SCRIPT_COMMANDS,
) -> dict[str, Any]:
    """Return the driver's accept-surface as a plain JSON-able dict.

    ``environment_commands``, ``plugin_commands``, ``utility_manifests``,
    ``samplable_fields``, and ``case_script_commands`` are supplied by the
    active adapter so Core names neither an environment nor a solver here.
    Together with :data:`CORE_NEUTRAL_COMMANDS` the commands reproduce exactly
    what ``validate_workflow_commands`` accepts for that plugin.
    ``case_script_commands`` defaults to the fixed
    Allrun-family set; a plugin whose entrypoint has its own declared name
    passes ``runtime.workflow.case_script_commands(driver_context)`` instead
    (its ``get_capabilities()`` has no ``DriverContext`` to read one from,
    but does have its own ``get_profile()`` -- see
    future/CASE_SCRIPT_COMMANDS_ENTRYPOINT_THREAT_MODEL.md §5).

    ``allowed_commands`` names exactly what a workflow DAG step may invoke;
    ``samplable_fields`` names the fields a function object may sample for the
    resolved model, split by region -- resolving the model and naming its
    fields is entirely the plugin's ``CaseIntrospectionCapability``, not this
    module's concern. A caller with nothing resolved passes ``None`` and gets
    an empty field set rather than this function raising.
    """

    fields = samplable_fields or {}

    return {
        "allowed_commands": {
            "core": sorted(CORE_NEUTRAL_COMMANDS),
            "environment": sorted(environment_commands),
            "plugin": sorted(plugin_commands),
            "case_scripts": sorted(case_script_commands),
            "utilities": _utility_commands(utility_manifests or {}),
            "environment_runtime_note": (
                "The active environment may also authorize discovered runtime "
                "applications through its command contract."
            ),
        },
        "samplable_fields": {
            **{region: sorted(names) for region, names in fields.items()},
            "note": (
                "These are field names the active adapter reports as sampleable "
                "for the resolved model."
            ),
        },
    }
