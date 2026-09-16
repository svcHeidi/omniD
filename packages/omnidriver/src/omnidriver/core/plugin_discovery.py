"""Discovery of installed omnidriver solver plugins via Python entry-points.

Plugins register themselves in the installing package's ``pyproject.toml``
under the ``[project.entry-points."omnidriver.plugins"]`` group::

    [project.entry-points."omnidriver.plugins"]
    mysolver = "my_package.my_solver_plugin:MySolverPlugin"

The entry-point **name** (``mysolver`` above) is what users pass to
``--plugin`` and what :func:`load_discovered_plugin` resolves.  It must be
unique across all installed distributions; a name claimed by more than one
distribution is reported by :func:`ambiguous_plugin_names` and excluded from
:func:`discover_plugins`.

Discovery is not sandboxed: loading a plugin executes its Python code in the
same process, exactly as the trusted ``module:Class`` form does.

Troubleshooting — plugin not found:
  Verify the entry-point group name is exactly ``omnidriver.plugins``::

      python -c "from importlib.metadata import entry_points; \\
                 print(list(entry_points(group='omnidriver.plugins')))"
"""

from __future__ import annotations

import functools
from importlib.metadata import entry_points
from typing import Any

ENTRY_POINT_GROUP = "omnidriver.plugins"


@functools.lru_cache(maxsize=1)
def _scan_entry_points() -> tuple[Any, ...]:
    """Read and cache the installed plugin entry points for this process."""
    return tuple(entry_points(group=ENTRY_POINT_GROUP))


def _entry_points() -> tuple[Any, ...]:
    """Return entry points through an injectable discovery seam."""
    return _scan_entry_points()


def ambiguous_plugin_names() -> dict[str, tuple[str, ...]]:
    """Return entry-point names claimed by multiple distributions."""
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
    loudly at load time rather than silently resolving to whichever
    distribution happened to be enumerated last.
    """
    ambiguous = set(ambiguous_plugin_names())
    return {
        entry_point.name: entry_point
        for entry_point in _entry_points()
        if entry_point.name not in ambiguous
    }


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
    plugin_class = entry_point.load()
    return driver_context(plugin_class(), source=_entry_point_source(entry_point))


def _entry_point_source(entry_point) -> str:
    """Provenance for a context built from an entry point.

    Records the installing distribution and version so a plan states which
    package supplied the semantics it was built against. Shared by
    :func:`load_discovered_plugin` and :func:`default_discovered_context` so
    the two cannot drift into reporting the same plugin differently.
    """
    dist = getattr(entry_point, "dist", None)
    return (
        f"entry-point:{dist.name}={dist.version}"
        if dist is not None
        else f"entry-point:{entry_point.name}"
    )


@functools.lru_cache(maxsize=8)
def _default_selection(snapshot: tuple[Any, ...]) -> tuple[Any, str] | None:
    """Which plugin answers when a public caller supplies no context.

    Returns ``(plugin_class, source)`` when exactly one adapter is installed.
    Raises ``LookupError`` when no adapter is installed or there is no unique
    answer.  Core never manufactures an environment-specific fallback.

    Cached per entry-point snapshot rather than recomputed. The public edge
    resolves the implicit default once per sweep case, and each recomputation
    reads every installed distribution's metadata; leaving this uncached took
    the test suite from 35 s to 13 min. The cache key is the snapshot itself,
    so a test that patches ``_entry_points`` to return synthetic entries gets a
    different key and a fresh decision -- the seam still works.

    The *context* is deliberately not cached. Core must not retain a
    DriverContext in module state; only the decision about which plugin to
    build one from is stable.
    """
    seen: dict[str, list[Any]] = {}
    for entry_point in snapshot:
        seen.setdefault(entry_point.name, []).append(entry_point)

    unambiguous = {name: eps[0] for name, eps in seen.items() if len(eps) == 1}
    ambiguous = sorted(name for name, eps in seen.items() if len(eps) > 1)

    if len(unambiguous) == 1:
        # One clean answer. An unrelated duplicated name alongside it does not
        # make this one ambiguous -- that name fails loudly on its own if
        # anybody selects it, which is what discover_plugins() excluding it is
        # for.
        entry_point = next(iter(unambiguous.values()))
        return entry_point.load(), _entry_point_source(entry_point)

    if not unambiguous and not ambiguous:
        raise LookupError(
            f"No DriverContext was supplied and no adapter is installed in the "
            f"{ENTRY_POINT_GROUP!r} entry-point group. Select an installed "
            "adapter with --plugin or supply an explicit DriverContext."
        )

    if not unambiguous:
        # Every installed name is contested. Falling through to the generic
        # context here would be the worst outcome available: it answers a
        # question about *which solver* with a context that has no solver
        # semantics, and it does so silently.
        conflicts = "; ".join(
            f"{name} claimed by {', '.join(sorted(_origin(ep) for ep in seen[name]))}"
            for name in ambiguous
        )
        raise LookupError(
            f"No DriverContext was supplied, and every plugin name in the "
            f"{ENTRY_POINT_GROUP!r} entry-point group is claimed by more than "
            f"one installed distribution ({conflicts}), so there is no "
            "unambiguous default. Uninstall one, or select a plugin with "
            "--plugin or an explicit DriverContext."
        )

    raise LookupError(
        f"No DriverContext was supplied, and {len(unambiguous)} plugins are "
        f"installed in the {ENTRY_POINT_GROUP!r} entry-point group "
        f"({', '.join(sorted(unambiguous))}), so there is no single default to "
        "fall back on. Select one with --plugin or an explicit DriverContext."
    )


def _origin(entry_point) -> str:
    dist = getattr(entry_point, "dist", None)
    return f"{dist.name}={dist.version}" if dist is not None else "<unknown>"


def default_discovered_context():
    """Build a fresh context for the implicitly-selected default plugin.

    See :func:`_default_selection` for the selection rule and
    ``compatibility.legacy_default_driver_context`` for why the public edge
    needs one at all.
    """
    from .plugin_interface import driver_context

    selection = _default_selection(_entry_points())
    plugin_class, source = selection
    return driver_context(plugin_class(), source=source)
