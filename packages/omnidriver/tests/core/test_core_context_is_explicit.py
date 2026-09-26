"""core/ and openfoam/ must receive an explicit DriverContext, never resolve
one implicitly.

`resolve_public_driver_context(None)` returns the cardiac context. A core
module that calls it silently becomes cardiacFoam for any plugin that failed
to thread a context through -- and it does so without raising, which is why
this guard is static rather than behavioural.

The cardiac default is legitimate at the public edge (omnidriver/*.py and
cli.py), where "no plugin supplied" genuinely means "the built-in one". It is
not legitimate inside core/ -- nor inside omnidriver-openfoam, whose three
former offenders (apply_overrides.py's `_catalog_entries`/`apply_overrides`,
dict_builder.py's `is_known_override_driver_path`) made a core+openfoam
install without cardiacfoam silently import `omnidriver.cardiacfoam` (Phase 2
Task 6). That is a wrong-direction dependency the import-boundary gate cannot
see, because openfoam imports *core* and core does the cardiac import --
this guard is the only thing standing between openfoam and that regression.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import omnidriver.core
from plugins.minimal_plugin import MinimalTestPlugin

from conftest import skip_without_repo

_CORE_ROOT = pathlib.Path(omnidriver.core.__file__).resolve().parent

_EXEMPT: set[pathlib.Path] = set()

# omnidriver.openfoam is not importable in a core-only venv, so this is
# resolved from the repo layout rather than by importing the package.
# core/__init__.py's ancestors are core, omnidriver, src, omnidriver (the
# package directory), packages -- parents[4] is "packages". parents[3] would
# land on packages/omnidriver/ and silently yield a path that does not
# exist, which would make this guard pass by scanning zero files -- the
# exact false-reassurance failure mode this repository has hit before, so
# _OPENFOAM_ROOT.is_dir() is asserted below rather than assumed.
_OPENFOAM_ROOT = (
    pathlib.Path(omnidriver.core.__file__).resolve().parents[4]
    / "omnidriver-openfoam" / "src" / "omnidriver" / "openfoam"
)


def _calls_resolve_public(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == "resolve_public_driver_context":
            lines.append(node.lineno)
    return lines


def _offenders(root: pathlib.Path, *, exempt: set[pathlib.Path]) -> dict[str, list[int]]:
    offenders: dict[str, list[int]] = {}
    for path in sorted(root.rglob("*.py")):
        if path in exempt or "__pycache__" in path.parts:
            continue
        hits = _calls_resolve_public(path)
        if hits:
            offenders[str(path.relative_to(root))] = hits
    return offenders


def test_core_never_resolves_an_implicit_driver_context() -> None:
    offenders = _offenders(_CORE_ROOT, exempt=_EXEMPT)
    assert offenders == {}, (
        "core/ modules resolving an implicit (cardiac) DriverContext:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nMake driver_context a required parameter instead."
    )


@skip_without_repo
def test_openfoam_never_resolves_an_implicit_driver_context() -> None:
    assert _OPENFOAM_ROOT.is_dir(), (
        f"expected omnidriver-openfoam's source tree at {_OPENFOAM_ROOT}, but "
        "it is not a directory -- a guard that silently scans zero files is "
        "worse than no guard. Fix the path computation rather than letting "
        "this assertion pass by finding nothing."
    )
    offenders = _offenders(_OPENFOAM_ROOT, exempt=set())
    assert offenders == {}, (
        "omnidriver.openfoam modules resolving an implicit (cardiac) "
        "DriverContext:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nMake driver_context a required parameter instead."
    )


# The public-edge functions that accept a DriverContext and resolve the
# implicit default when handed none. A core module may call these -- they are
# the public API -- but it must thread its own context through, or it launders
# the cardiac default past the two guards above: the call itself lives in
# omnidriver/*.py, which _CORE_ROOT does not scan, and nothing in core names
# resolve_public_driver_context.
#
# sweep_runner.py:273 and :449 did exactly that until Part B of
# docs/superpowers/specs/2026-09-02-neutral-default-context-design.md, calling
# materialize_case() with no context one line after route_case_values() was
# given one.
#
# This set is written out rather than inferred. An inferred rule would either
# miss functions or fire on unrelated same-named calls; an explicit list is
# greppable, and _test_the_guarded_names_still_exist below fails loudly if one
# of these stops existing rather than letting the guard quietly shrink.
_CONTEXT_TAKING_PUBLIC_EDGE = {
    "materialize_case": "omnidriver.sweep_materialize",
    "route_case_values": "omnidriver.sweep_routing",
    "get_heterogeneity_models": "omnidriver.dict_entries",
    "get_electro_property_entry_groups": "omnidriver.dict_entries",
    "all_documented_driver_paths": "omnidriver.dict_entries",
}


def _unthreaded_public_edge_calls(path: pathlib.Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name not in _CONTEXT_TAKING_PUBLIC_EDGE:
            continue
        passes_context = any(
            # keyword.arg is None for **kwargs, which does thread a context
            # when the caller forwards one; treat it as threaded rather than
            # guessing, since the behavioural census covers what static
            # analysis cannot see.
            keyword.arg in ("driver_context", None)
            for keyword in node.keywords
        )
        if not passes_context:
            found.append((name, node.lineno))
    return found


def test_the_guarded_names_still_exist() -> None:
    """A guard naming functions that no longer exist guards nothing."""
    import importlib

    for name, module_path in sorted(_CONTEXT_TAKING_PUBLIC_EDGE.items()):
        module = importlib.import_module(module_path)
        assert hasattr(module, name), (
            f"{module_path}.{name} is named by _CONTEXT_TAKING_PUBLIC_EDGE but "
            "no longer exists. Update the set rather than deleting the entry "
            "silently -- the function may have been renamed, not removed."
        )


def test_core_threads_its_context_through_the_public_edge() -> None:
    offenders: dict[str, list[tuple[str, int]]] = {}
    for path in sorted(_CORE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        hits = _unthreaded_public_edge_calls(path)
        if hits:
            offenders[str(path.relative_to(_CORE_ROOT))] = hits

    assert offenders == {}, (
        "core/ modules calling a public-edge function without threading their "
        "DriverContext (each such call silently resolves the built-in "
        "default):\n"
        + "\n".join(
            f"  {f}: " + ", ".join(f"{name}() at line {line}" for name, line in hits)
            for f, hits in sorted(offenders.items())
        )
        + "\nPass driver_context=driver_context."
    )


# Functions that invent a filesystem location rather than receiving one. Core
# must call none of them: doing so is what made core unable to plan a case
# from a wheel install. Written out explicitly, like
# _CONTEXT_TAKING_PUBLIC_EDGE above, with a companion test that fails if a
# name here stops existing -- a guard naming nothing guards nothing.
_ROOT_INVENTING = {"repo_root_default", "cardiacfoam_monorepo_root"}

# capability_seams.architecture_path() legitimately needs a checkout: it
# points at ARCHITECTURE.md for the seam-table generator, which is dev
# tooling, never a runtime path. paths.py is where these are defined.
_ROOT_EXEMPT = {_CORE_ROOT / "capability_seams.py", _CORE_ROOT / "specs" / "paths.py"}


def test_the_root_inventing_names_still_exist() -> None:
    from omnidriver.core.specs import paths

    for name in sorted(_ROOT_INVENTING):
        assert hasattr(paths, name), (
            f"{name} is named by _ROOT_INVENTING but no longer exists. Update "
            "the set rather than letting this guard quietly cover nothing."
        )


def test_core_never_invents_a_filesystem_root() -> None:
    offenders: dict[str, list[int]] = {}
    for path in sorted(_CORE_ROOT.rglob("*.py")):
        if path in _ROOT_EXEMPT or "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        hits = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (getattr(node.func, "id", None) or getattr(node.func, "attr", None))
            in _ROOT_INVENTING
        ]
        if hits:
            offenders[str(path.relative_to(_CORE_ROOT))] = hits

    assert offenders == {}, (
        "core/ modules inventing a filesystem root:\n"
        + "\n".join(f"  {f}: lines {ls}" for f, ls in sorted(offenders.items()))
        + "\nTake the location as a parameter instead."
    )


#: The one scratch resolver (owner decision 2026-09-26). It lives in paths.py,
#: which `test_core_never_invents_a_filesystem_root` exempts, so it is
#: guarded here instead: it must refuse, not default, and nothing in the
#: package may rebuild the `<base>/.omnidriver` default it replaced.
_SCRATCH_RESOLVER = "resolve_scratch_root"
_PACKAGE_ROOT = _CORE_ROOT.parent
#: `case_transaction` journals inside the case it transacts (a staged copy,
#: never the native tree): a per-case directory, not a scratch root.
_DOT_OMNIDRIVER_EXEMPT = {_CORE_ROOT / "case_transaction.py"}


def test_the_scratch_resolver_invents_no_default(tmp_path, monkeypatch) -> None:
    import inspect

    from omnidriver.core.specs import paths

    resolver = getattr(paths, _SCRATCH_RESOLVER)
    assert "base" not in inspect.signature(resolver).parameters, (
        "a `base` parameter is how the <base>/.omnidriver default worked"
    )
    assert not hasattr(paths, "scratch_root"), (
        "scratch_root(base) defaulted under its base; every caller goes "
        f"through {_SCRATCH_RESOLVER} now"
    )
    monkeypatch.delenv(paths.SCRATCH_ENV_VAR, raising=False)
    with pytest.raises(paths.ScratchRootNotSupplied):
        resolver(None, cases_root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_nothing_rebuilds_a_dot_omnidriver_scratch_default() -> None:
    """A bare ``".omnidriver"`` path segment anywhere in the package is the
    old default coming back under another name. (``.omnidriver-attempt.lock``
    and the like are distinct literals and are not matched.)"""
    offenders = {
        str(path.relative_to(_PACKAGE_ROOT)): [
            node.lineno for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
            if isinstance(node, ast.Constant) and node.value == ".omnidriver"
        ]
        for path in sorted(_PACKAGE_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts and path not in _DOT_OMNIDRIVER_EXEMPT
    }
    assert {f: ls for f, ls in offenders.items() if ls} == {}


@pytest.fixture
def two_provider_context():
    """A composed :class:`DriverContext` over two real, installed providers.

    Skips rather than fabricating a stand-in when fewer than two adapters are
    installed -- this fixture exists to prove composition over genuine
    providers, not over test doubles that happen to satisfy the Protocol.

    Deliberately does not wrap ``driver_context_for_installed_plugins``: that
    fixture returns already-built single-plugin ``DriverContext`` objects, and
    `driver_context(*providers, ...)` needs the plugin *instances* themselves.
    Mirrors ``plugin_discovery.load_discovered_plugin``'s
    ``entry_point.load()()`` pattern instead of writing new discovery, since
    ``discover_plugins()`` returns ``EntryPoint`` objects, not classes.
    """
    from omnidriver.core import plugin_discovery
    from omnidriver.core.plugin_interface import driver_context

    discovered = plugin_discovery.discover_plugins()
    environment_name = next(
        (name for name in discovered if "environment" in name), None,
    )
    solver_name = next(
        (name for name in discovered if name != environment_name), None,
    )
    if environment_name is None or solver_name is None:
        pytest.skip(
            "requires the OpenFOAM environment adapter plus at least one "
            "other installed omnidriver.plugins adapter"
        )

    environment_plugin = discovered[environment_name].load()()
    solver_plugin = discovered[solver_name].load()()
    return driver_context(environment_plugin, solver_plugin, source="test")


def test_a_context_holds_an_ordered_stack():
    import dataclasses

    from omnidriver.core.plugin_interface import DriverContext

    fields = {f.name for f in dataclasses.fields(DriverContext)}
    assert "providers" in fields
    assert "plugin" not in fields, (
        "a single `plugin` field is the arity assumption this phase removes"
    )


def test_identity_names_every_provider(two_provider_context):
    payload = two_provider_context.identity.to_json()
    assert len(payload["providers"]) == 2
    assert payload["resolutions"], "the identity must record who answered what"


def test_each_provider_records_its_own_source_not_a_shared_one():
    """Spec 4.4: a provenance record must say which adapter came from where.

    `default_discovered_context()` used to join every selected provider's
    source into one string and pass it as the single shared `source=`, so
    every `ProviderIdentity.source` in the stack recorded the SAME joined
    string instead of each provider's own origin -- silently defeating the
    one reason `StackIdentity` records an identity per provider at all.
    Uses two synthetic, no-case-file providers (not real installed adapters)
    so this is provable independently of Finding 2's real cross-adapter
    case-file conflict, which stops `two_provider_context` above from
    actually composing.

    Deliberately passes providers and sources in an order that does NOT
    match `order_providers`' output (which sorts by plugin_id when nothing
    `requires:` anything else): "zzz" is passed first but sorts last, so a
    fix that merely paired sources positionally against the REORDERED stack,
    rather than tracking each provider's own id, would misattribute them.
    """
    from omnidriver.core.plugin_interface import driver_context

    class _NamedProvider(MinimalTestPlugin):
        """A MinimalTestPlugin whose plugin_id is chosen per instance, so two
        can compose together as distinct providers without a real adapter's
        case files ever entering the picture."""

        def __init__(self, plugin_id: str) -> None:
            super().__init__()
            self._named_plugin_id = plugin_id

        @property
        def plugin_id(self) -> str:
            return self._named_plugin_id

    zzz = _NamedProvider("org.example.zzz")
    aaa = _NamedProvider("org.example.aaa")

    context = driver_context(
        zzz, aaa, source=["source-for-zzz", "source-for-aaa"],
    )

    by_id = {p.id: p.source for p in context.identity.providers}
    assert by_id == {
        "org.example.zzz": "source-for-zzz",
        "org.example.aaa": "source-for-aaa",
    }


def test_a_single_source_string_still_broadcasts_to_every_provider():
    """The common single-provider call shape, and a multi-provider stack that
    genuinely shares one origin, must keep working with one plain string."""
    from omnidriver.core.plugin_interface import driver_context

    class _NamedProvider(MinimalTestPlugin):
        def __init__(self, plugin_id: str) -> None:
            super().__init__()
            self._named_plugin_id = plugin_id

        @property
        def plugin_id(self) -> str:
            return self._named_plugin_id

    solo = driver_context(_NamedProvider("org.example.solo"), source="shared")
    assert solo.identity.providers[0].source == "shared"

    stacked = driver_context(
        _NamedProvider("org.example.one"), _NamedProvider("org.example.two"),
        source="shared",
    )
    assert {p.source for p in stacked.identity.providers} == {"shared"}


def test_source_count_must_match_provider_count():
    from omnidriver.core.plugin_interface import driver_context

    class _NamedProvider(MinimalTestPlugin):
        def __init__(self, plugin_id: str) -> None:
            super().__init__()
            self._named_plugin_id = plugin_id

        @property
        def plugin_id(self) -> str:
            return self._named_plugin_id

    with pytest.raises(TypeError, match="2 provider"):
        driver_context(
            _NamedProvider("org.example.one"), _NamedProvider("org.example.two"),
            source=["only-one-source"],
        )
