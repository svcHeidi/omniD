"""Compose N providers into one capability view.

Core owns composition; a provider never embeds another provider. Before this
module, each solver plugin embedded the environment adapter by hand -- and the
two did it differently, so `get_config_value_reader` returned a different
callable from each and `get_selected_start_time` was copy-pasted into both.

This module implements one piece of that: the declared-vs-implemented guard.
``ENVIRONMENT_CONTRACT.md`` §12 draws the line -- intent is supplied, the
method set is discovered. ``PluginProfile.provides`` (Task 1) is the supplied
intent; :func:`implemented_capabilities` is the discovery; :func:`check_provides`
is where they are compared, so a misspelled hook name becomes a reported error
instead of a silent fallback route.
"""

from __future__ import annotations

from graphlib import TopologicalSorter
from typing import Any

from .capability_seams import adapts_members, collect_seams


def capability_members() -> dict[str, frozenset[str]]:
    """Map each capability name to the contract members it adapts.

    Reuses :func:`capability_seams.adapts_members`, the single parser for a
    seam's ``:adapts:`` field -- this does not re-split the text itself.
    """
    return {seam.field: adapts_members(seam) for seam in collect_seams()}


def implemented_capabilities(provider: Any) -> frozenset[str]:
    """Capabilities whose every member this provider actually implements.

    Discovery, not intent: a capability appears here purely because the
    provider object exposes a callable of that name for each member the
    capability adapts, regardless of what the provider's profile declares.
    """
    return frozenset(
        capability
        for capability, members in capability_members().items()
        if all(callable(getattr(provider, member, None)) for member in members)
    )


def check_provides(provider: Any) -> list[str]:
    """Return one problem per capability declared but not fully implemented.

    Declared-but-absent is the error this catches -- it is how a misspelled
    hook name becomes visible instead of silently routing to a fallback.
    Implemented-but-undeclared is NOT an error: a provider may implement a
    member for its own use without offering it to the stack.
    """
    declared = provider.get_profile().provides
    members = capability_members()
    problems: list[str] = []
    for capability in sorted(declared):
        missing = sorted(
            member
            for member in members.get(capability, ())
            if not callable(getattr(provider, member, None))
        )
        if missing:
            problems.append(
                f"provider declares provides: {capability!r} but does not "
                f"implement {missing}"
            )
    return problems


def order_providers(providers) -> tuple:
    """Order providers least-specific first, by declared `requires:`.

    Stable: independent providers keep sorted-by-id order, so the same
    installation always composes identically. That matters because the stack
    digest hashes this order.
    """
    by_id = {provider.plugin_id: provider for provider in providers}
    graph: dict[str, set[str]] = {}
    for plugin_id, provider in sorted(by_id.items()):
        requires = tuple(provider.get_profile().requires)
        missing = sorted(set(requires) - set(by_id))
        if missing:
            raise ValueError(
                f"provider {plugin_id!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not installed"
            )
        graph[plugin_id] = set(requires)
    try:
        ordered = tuple(TopologicalSorter(graph).static_order())
    except Exception as exc:  # graphlib.CycleError
        raise ValueError(
            f"provider requirements form a cycle: {exc}"
        ) from exc
    return tuple(by_id[plugin_id] for plugin_id in ordered)
