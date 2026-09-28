from __future__ import annotations

from typing import Any

_NON_ROUTABLE_KEYS: frozenset[str] = frozenset({"caseId"})


def route_case_values(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any], driver_context,
) -> dict[str, Any]:
    """Route through the selected plugin."""

    from .core.plugin_capabilities import SweepRoutingRequest

    return driver_context.capabilities.sweep_materializer.route(
        SweepRoutingRequest(
            base=base,
            resolved_axis_values=resolved_axis_values,
        ),
        driver_context=driver_context,
    )


_ENTRY_NON_ROUTABLE_KEYS: frozenset[str] = _NON_ROUTABLE_KEYS | frozenset(
    {"entry", "archive_dir_name"}
)


def route_entry_case_values(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any],
) -> dict[str, Any]:
    """Route a resolved entry-based sweep case's values to make_spec kwargs.

    ``resolved_axis_values`` are merged onto ``base``, winning on conflict.
    Everything passes through except sweep_expansion's bookkeeping keys and
    ``"entry"`` itself (sweep_runner's own dispatch key, not a make_spec kwarg).
    """
    merged = {**base, **resolved_axis_values}
    return {
        key: value
        for key, value in merged.items()
        if key not in _ENTRY_NON_ROUTABLE_KEYS
    }
