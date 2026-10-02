from __future__ import annotations

from typing import Any, Iterable

from .runtime.workflow import CORE_NEUTRAL_COMMANDS


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
    case_script_commands: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Return the driver's accept-surface as a plain JSON-able dict.

    ``environment_commands``, ``plugin_commands``, ``utility_manifests``,
    ``samplable_fields``, and ``case_script_commands`` are supplied by the
    active adapter so Core names neither an environment nor a solver here.
    Together with :data:`CORE_NEUTRAL_COMMANDS` the commands reproduce exactly
    what ``validate_workflow_commands`` accepts for that plugin.
    ``case_script_commands`` defaults to an empty set. Core calls this through
    :func:`capability_manifest`, from the composed stack.

    ``allowed_commands`` names exactly what a workflow DAG step may invoke;
    ``samplable_fields`` names the fields a function object may sample for the
    resolved model, split by region (the stack's ``get_samplable_fields``). A
    caller with nothing resolved passes ``None`` and gets
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


def capability_manifest(driver_context) -> dict[str, Any]:
    """The stack's accept-surface, plus what only a provider can add
    (``get_capabilities``, a domain catalogue). Rebuilt on every call, so no
    caller shares another's dict."""
    from .runtime_records import case_runtime_conventions

    stack = driver_context.stack
    conventions = case_runtime_conventions(driver_context)
    built = build_capability_manifest(
        environment_commands=stack.call("get_environment_commands"),
        # Both kinds of authorized command; the solver/auxiliary split only
        # governs which may be credited with a run's artifacts.
        plugin_commands=stack.call("get_solver_commands") | stack.call("get_auxiliary_commands"),
        utility_manifests=stack.call("get_utility_manifests"),
        # No case is resolved here, so only the model-independent fields.
        samplable_fields={k: tuple(v) for k, v in stack.call("get_samplable_fields", {}).items()},
        case_script_commands=frozenset(conventions.case_script_commands) | frozenset(conventions.case_entrypoints),
    )
    built.update(stack.call("get_capabilities"))
    return built
