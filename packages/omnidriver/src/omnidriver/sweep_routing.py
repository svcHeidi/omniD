from __future__ import annotations

from typing import Any

_NON_ROUTABLE_KEYS: frozenset[str] = frozenset({"caseId"})


def route_case_values(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any], driver_context=None,
) -> dict[str, Any]:
    """Route through the selected plugin while preserving the public API."""

    from .core.compatibility import resolve_public_driver_context
    from .core.plugin_capabilities import SweepRoutingRequest

    driver_context = resolve_public_driver_context(driver_context)
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

    Entry-based sweeps target an existing registered tutorial's own
    make_spec(**kwargs) (e.g. niederer_2012.py's dx_values/dt_values/
    end_time_by_dx), which already validates its own keyword arguments --
    unlike route_case_values's build_and_launch target, there is no fixed
    vocabulary to classify values into here. `base` carries kwargs fixed
    across every case in the sweep (e.g. solvers, end_time_by_dx); per-case
    resolved_axis_values are merged on top, winning on conflict. Every value
    passes straight through except sweep_expansion's bookkeeping keys and
    "entry" itself (sweep_runner's own dispatch key, not a make_spec kwarg).
    """
    merged = {**base, **resolved_axis_values}
    return {
        key: value
        for key, value in merged.items()
        if key not in _ENTRY_NON_ROUTABLE_KEYS
    }
