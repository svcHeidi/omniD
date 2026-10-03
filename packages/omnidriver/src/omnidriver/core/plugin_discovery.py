"""Discovery of installed omnidriver solver plugins via the ``omnidriver.plugins`` entry-point group.

Loading executes the plugin's Python code in-process, same as the trusted ``module:Class`` form.
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

ENTRY_POINT_GROUP = "omnidriver.plugins"


def _entry_points() -> tuple[Any, ...]:
    """Indirection seam so tests can inject entry points without installing."""
    return tuple(entry_points(group=ENTRY_POINT_GROUP))


def ambiguous_plugin_names() -> dict[str, tuple[str, ...]]:
    """Entry-point names claimed by more than one installed distribution.

    Two distributions exporting the same name is a packaging conflict, not
    something to resolve by dictionary insertion order.
    """
    seen: dict[str, list[str]] = {}
    for entry_point in _entry_points():
        dist = getattr(entry_point, "dist", None)
        origin = f"{dist.name}={dist.version}" if dist is not None else "<unknown>"
        seen.setdefault(entry_point.name, []).append(origin)
    return {
        name: tuple(sorted(origins))
        for name, origins in seen.items()
        if len(origins) > 1
    }


def discover_plugins() -> dict[str, Any]:
    """Return unambiguously installed plugin entry points keyed by name.

    Never raises: a broken third-party distribution must not make the CLI
    unusable for everyone else. A name claimed by several distributions is
    omitted here and reported by :func:`ambiguous_plugin_names`, so it fails
    loudly at load time rather than silently picking whichever distribution
    was enumerated last.
    """
    ambiguous = set(ambiguous_plugin_names())
    return {
        entry_point.name: entry_point
        for entry_point in _entry_points()
        if entry_point.name not in ambiguous
    }


class BrokenPluginError(LookupError):
    """An installed entry point whose target cannot be imported or built.

    Raised by name (entry-point name, distribution, ``module:Class`` target,
    underlying error) rather than skipped: a broken entry may be the very
    provider the caller meant, so dropping it silently could change which
    stack resolves.
    """


def _describe_entry_point(entry_point) -> str:
    return (
        f"{entry_point.name!r} ({_origin(entry_point)}, "
        f"target {getattr(entry_point, 'value', '<unknown>')!r})"
    )


def _instantiate(entry_point):
    """Load and build the plugin, or raise :class:`BrokenPluginError`; third-party code can raise anything, so all of it is caught."""
    try:
        return entry_point.load()()
    except Exception as exc:
        raise BrokenPluginError(
            f"omnidriver plugin entry point {_describe_entry_point(entry_point)} "
            f"in group {ENTRY_POINT_GROUP!r} cannot be loaded: "
            f"{type(exc).__name__}: {exc}"
        ) from exc


def _find_installed_provider(plugin_id: str):
    """The installed provider answering ``plugin_id``; load failures are collected so the answer does not depend on enumeration order."""
    broken: list[BrokenPluginError] = []
    for entry_point in discover_plugins().values():
        try:
            candidate = _instantiate(entry_point)
        except BrokenPluginError as exc:
            broken.append(exc)
            continue
        if candidate.plugin_id == plugin_id:
            return candidate, _entry_point_source(entry_point)
    if broken:
        raise BrokenPluginError(
            f"no loadable installed plugin provides the required id {plugin_id!r}, "
            "and these entry points, which might, cannot be loaded: "
            + "; ".join(str(exc) for exc in broken)
        )
    return None


def _expand_with_requirements(primary: Any, source: str):
    """Add the installed providers answering ``primary``'s `requires:`, one level; an unmet one is left for ``order_providers`` to report."""
    from .provider_stack import provider_profile

    providers = [primary]
    sources = [source]
    seen_ids = {primary.plugin_id}
    for required_id in provider_profile(primary).requires:
        if required_id in seen_ids:
            continue
        found = _find_installed_provider(required_id)
        if found is None:
            continue
        provider, provider_source = found
        providers.append(provider)
        sources.append(provider_source)
        seen_ids.add(required_id)
    return providers, sources


def load_discovered_plugin(name: str):
    """Load and validate a discovered plugin by entry-point name.

    Loading executes the plugin's Python code. Identity provenance records the
    installing distribution's name and version so a plan states which package
    supplied the semantics it was built against.
    """
    from .plugin_interface import driver_context

    ambiguous = ambiguous_plugin_names().get(name)
    if ambiguous is not None:
        raise KeyError(
            f"omnidriver plugin name {name!r} is claimed by more than one "
            f"installed distribution ({', '.join(ambiguous)}); uninstall one "
            "or select it with the module:Class form"
        )
    entry_point = discover_plugins().get(name)
    if entry_point is None:
        raise KeyError(
            f"No installed omnidriver plugin named {name!r} in entry-point "
            f"group {ENTRY_POINT_GROUP!r}"
        )
    providers, sources = _expand_with_requirements(
        _instantiate(entry_point), _entry_point_source(entry_point),
    )
    return driver_context(*providers, source=sources, plugin_selector=name)


def _entry_point_source(entry_point) -> str:
    """Provenance string for a context built from an entry point."""
    dist = getattr(entry_point, "dist", None)
    return (
        f"entry-point:{dist.name}={dist.version}"
        if dist is not None
        else f"entry-point:{entry_point.name}"
    )


def _origin(entry_point) -> str:
    dist = getattr(entry_point, "dist", None)
    return f"{dist.name}={dist.version}" if dist is not None else "<unknown>"
