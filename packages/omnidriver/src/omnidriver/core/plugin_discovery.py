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
    """Read the entry-point group off disk, once per process.

    ``importlib.metadata.entry_points()`` re-reads every installed
    distribution's metadata on each call -- about 6 ms here. That was
    invisible while discovery only ran when ``--plugin`` was passed, but
    ``compatibility.legacy_default_driver_context`` now resolves the implicit
    default through this group, and the public edge calls it once per sweep
    case. Uncached, that took the test suite from 35 s to 13 min.

    Installed distributions do not change inside a running process, so this is
    a cache over something genuinely immutable, not a bet. Tests that need
    synthetic entry points patch ``_entry_points`` below -- which replaces the
    whole function object, cache and all -- so this does not weaken that seam.
    """
    return tuple(entry_points(group=ENTRY_POINT_GROUP))


def _entry_points() -> tuple[Any, ...]:
    """Indirection seam so tests can inject entry points without installing.

    Tests monkeypatch this function to return synthetic entry-point objects,
    avoiding the need for a real ``pip install`` of the plugin under test.
    All public discovery functions call this; none call ``entry_points()``
    directly.
    """
    return _scan_entry_points()


def ambiguous_plugin_names() -> dict[str, tuple[str, ...]]:
    """Entry-point names claimed by more than one installed distribution.

    Two distributions exporting the same name is a packaging conflict, not
    something to resolve by dictionary insertion order -- which distribution
    won would depend on installation order and be invisible in the plan.
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
    loudly at load time rather than silently resolving to whichever
    distribution happened to be enumerated last.
    """
    ambiguous = set(ambiguous_plugin_names())
    return {
        entry_point.name: entry_point
        for entry_point in _entry_points()
        if entry_point.name not in ambiguous
    }


def _find_installed_provider(plugin_id: str):
    """The installed, unambiguous provider answering ``plugin_id``, if any.

    Loads every discovered entry point to read its ``plugin_id`` -- there is
    no id-keyed index, only the name-keyed one ``discover_plugins()``
    returns. Only ever called to resolve a `requires:` declaration, which is
    a CLI-startup-frequency operation, not a hot loop.
    """
    for entry_point in discover_plugins().values():
        plugin_class = entry_point.load()
        candidate = plugin_class()
        if candidate.plugin_id == plugin_id:
            return candidate, _entry_point_source(entry_point)
    return None


def _expand_with_requirements(primary: Any, source: str):
    """Add whichever installed provider answers ``primary``'s `requires:`.

    ``--plugin`` (and the bare discovered-name form) select ONE provider by
    design -- see ``_default_selection``'s docstring: "`--plugin` still
    narrows the implicit stack to one provider". Task 9 gave cardiacCore and
    cardiacFoam their first `requires:` declaration
    (``org.omnidriver.openfoam.environment``), and ``order_providers`` raises
    the instant a declared requirement is unmet -- so without this, selecting
    either by name or by trusted import would refuse to compose at all,
    turning "the environment adapter is now composed in, not hand-embedded"
    into "cardiacCore/cardiacFoam are no longer usable outside a stack the
    caller assembles by hand". Resolving `requires:` against what is already
    installed keeps the single-name ``--plugin`` UX working. One level only
    (no shipped profile declares a chain today); an unmet requirement that
    resolution can't find is left for ``order_providers`` to report, which
    names it more specifically than this function would.
    """
    providers = [primary]
    sources = [source]
    seen_ids = {primary.plugin_id}
    for required_id in primary.get_profile().requires:
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
    plugin_class = entry_point.load()
    providers, sources = _expand_with_requirements(
        plugin_class(), _entry_point_source(entry_point),
    )
    return driver_context(*providers, source=sources)


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
def _default_selection(snapshot: tuple[Any, ...]) -> tuple[tuple[Any, str], ...]:
    """Which providers answer when a public caller supplies no context.

    Returns one ``(plugin_class, source)`` pair per unambiguously installed
    adapter, ordered by entry-point name -- a stable input order, so the same
    installation always resolves to the same stack before
    ``driver_context()`` orders it again by declared ``requires:``. Raises
    ``LookupError`` only when there is nothing to compose at all: no adapter
    installed, or every installed name contested. Core never manufactures an
    environment-specific fallback.

    **Corrected 2026-09-21.** Two or more unambiguous adapters used to be a
    third ``LookupError`` case. That error existed only because
    ``DriverContext`` held a single ``plugin`` and two adapters could not
    coexist in it; composing an ordered stack per capability removes that
    constraint, so several unambiguous adapters are now returned together
    rather than refused. ``--plugin`` still narrows the implicit stack to one
    provider by bypassing this function entirely -- see ``load_plugin_context``.

    Cached per entry-point snapshot rather than recomputed. The public edge
    resolves the implicit default once per sweep case, and each recomputation
    reads every installed distribution's metadata; leaving this uncached took
    the test suite from 35 s to 13 min. The cache key is the snapshot itself,
    so a test that patches ``_entry_points`` to return synthetic entries gets a
    different key and a fresh decision -- the seam still works.

    The *context* is deliberately not cached. Core must not retain a
    DriverContext in module state; only the decision about which plugins to
    build one from is stable.
    """
    seen: dict[str, list[Any]] = {}
    for entry_point in snapshot:
        seen.setdefault(entry_point.name, []).append(entry_point)

    unambiguous = {name: eps[0] for name, eps in seen.items() if len(eps) == 1}
    ambiguous = sorted(name for name, eps in seen.items() if len(eps) > 1)

    if unambiguous:
        # One pair per unambiguous name, in a stable order. An unrelated
        # duplicated name alongside these does not make them ambiguous --
        # that name fails loudly on its own if anybody selects it, which is
        # what discover_plugins() excluding it is for.
        return tuple(
            (entry_point.load(), _entry_point_source(entry_point))
            for _, entry_point in sorted(unambiguous.items())
        )

    if not ambiguous:
        raise LookupError(
            f"No DriverContext was supplied and no adapter is installed in the "
            f"{ENTRY_POINT_GROUP!r} entry-point group. Select an installed "
            "adapter with --plugin or supply an explicit DriverContext."
        )

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


def _origin(entry_point) -> str:
    dist = getattr(entry_point, "dist", None)
    return f"{dist.name}={dist.version}" if dist is not None else "<unknown>"


def default_discovered_context():
    """Build a fresh context for the implicitly-selected default stack.

    See :func:`_default_selection` for the selection rule and
    ``compatibility.legacy_default_driver_context`` for why the public edge
    needs one at all. With several unambiguous adapters installed, all of
    them are instantiated and handed to :func:`~omnidriver.core.plugin_interface.driver_context`
    together, which orders and composes them into one stack -- exactly as if
    a caller had passed several providers explicitly.

    **Corrected 2026-09-21.** This used to join every provider's source into
    one ``"; "``-separated string and pass it as the single shared ``source``
    -- so ``ProviderIdentity.source`` recorded the SAME joined string for
    every provider in a multi-provider stack, rather than each provider's own
    actual origin (e.g. ``entry-point:cardiacfoam=1.0`` vs
    ``entry-point:openfoam-environment=1.0``). That directly defeated the
    reason ``StackIdentity`` records one identity per provider at all: so a
    provenance record can say which adapter came from where. Passing the
    list of each selected entry point's own source, positionally against
    ``providers``, lets :func:`~omnidriver.core.plugin_interface.driver_context`
    attribute each one correctly.
    """
    from .plugin_interface import driver_context

    selection = _default_selection(_entry_points())
    providers = [plugin_class() for plugin_class, _ in selection]
    sources = [source for _, source in selection]
    return driver_context(*providers, source=sources)
