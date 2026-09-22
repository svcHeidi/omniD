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

    Stable and hash-independent: every node is registered in sorted-id order
    before any edge is added, and each node's predecessors are added sorted, so
    `TopologicalSorter` sees one insertion order regardless of `PYTHONHASHSEED`.
    Independent providers therefore keep sorted-by-id order. That matters
    because `build_stack_identity` hashes this order into the stack digest,
    which a reviewed plan is bound to.

    Corrected 2026-09-22 (audit finding C1): the previous implementation passed
    `set(requires)` to `TopologicalSorter`, which registers a node first seen as
    a predecessor in set-iteration order. A three-dependency provider therefore
    composed in four different orders across eight hash seeds.
    """
    providers = tuple(providers)
    seen: dict[str, int] = {}
    for provider in providers:
        seen[provider.plugin_id] = seen.get(provider.plugin_id, 0) + 1
    duplicates = sorted(plugin_id for plugin_id, count in seen.items() if count > 1)
    if duplicates:
        raise ValueError(
            f"provider identities are not unique: {duplicates}; two "
            f"distributions claiming one id make the answering implementation "
            f"depend on discovery order, and the stack digest then records an "
            f"identity that does not identify one implementation"
        )
    by_id = {provider.plugin_id: provider for provider in providers}
    requirements: dict[str, tuple[str, ...]] = {}
    for plugin_id in sorted(by_id):
        requires = tuple(by_id[plugin_id].get_profile().requires)
        missing = sorted(set(requires) - set(by_id))
        if missing:
            raise ValueError(
                f"provider {plugin_id!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not installed"
            )
        requirements[plugin_id] = tuple(sorted(set(requires)))
    sorter = TopologicalSorter()
    # Two passes, both in sorted order: registration first, so no node is ever
    # created by an edge, then the edges themselves.
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id)
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id, *requirements[plugin_id])
    try:
        ordered = tuple(sorter.static_order())
    except Exception as exc:  # graphlib.CycleError
        raise ValueError(
            f"provider requirements form a cycle: {exc}"
        ) from exc
    return tuple(by_id[plugin_id] for plugin_id in ordered)


# ---------------------------------------------------------------------------
# Composition (spec §4.3, as amended 2026-09-20 by the Task 15 spike)
# ---------------------------------------------------------------------------

#: Composition rule per contract member. Spec §4.3 names six shapes; this
#: table is the complete classification of every member every capability
#: adapts, because a member absent here is an error at IMPORT
#: (:func:`_check_classification`) rather than a silent default -- an
#: unclassified member is how a rule gets chosen by accident.
#:
#: ``set``       union of the declared sets.
#: ``map``       merge in stack order; a duplicate key is an error unless the
#:               more specific entry carries ``overrides: <provider id>``
#:               naming whose declaration it replaces, and an ``overrides:``
#:               naming a provider that declared no such key is also an error.
#: ``catalog``   the map rule over a :class:`DictionaryCatalog`'s documents,
#:               rebuilt into a catalog. A catalog is not a mapping, so it
#:               cannot go through ``map`` directly; core owns the type, so
#:               merging it is core's to do rather than a provider's.
#: ``tutorial_catalog`` a second not-actually-a-mapping case, added Task 9:
#:               ``get_tutorial_catalog()`` is ``:status: required``, so
#:               EVERY provider answers it, always with the same fixed keys
#:               (``registered_tutorials``, ``spec_factories``) -- the ``map``
#:               rule's duplicate-key error fires on every two-provider stack
#:               ever composed, not on a genuine collision. Tutorial NAMES,
#:               not those two container keys, are the actual declarations,
#:               so this unions ``registered_tutorials`` and merges
#:               ``spec_factories`` by tutorial name (duplicate name = error,
#:               no override marker needed since names are namespaced by
#:               convention); any other key a provider adds keeps only its
#:               most-specific value, the same as ``single``.
#: ``sequence``  concatenate every implementer's result, in stack order.
#: ``single``    first non-``None``, most-specific provider first.
#: ``chain``     thread the first argument through every implementer, in
#:               stack order.
#: ``exclusive`` exactly one provider may implement; two is an error, zero
#:               leaves the member absent so the capability's declared
#:               fallback refuses by name.
#: ``profile``   the declarative profile: case-file rules concatenated (with
#:               §2.1's one-declarer rule enforced at compose time),
#:               ``provides`` unioned, everything else from the most specific.
_SHAPE: dict[str, str] = {
    # -- set ---------------------------------------------------------------
    "get_solver_commands": "set",
    "get_auxiliary_commands": "set",
    "get_environment_commands": "set",
    "get_solve_step_commands": "set",
    # -- tutorial_catalog ----------------------------------------------------
    "get_tutorial_catalog": "tutorial_catalog",
    # -- map ---------------------------------------------------------------
    "get_dict_groups": "map",
    "get_utility_manifests": "map",
    "get_named_catalogs": "map",
    "get_dict_entry_catalog": "map",
    "get_samplable_fields": "map",
    "resolve_case_models": "map",
    # -- catalog -----------------------------------------------------------
    "get_dictionary_catalog": "catalog",
    # -- sequence ----------------------------------------------------------
    "get_tutorial_displays": "sequence",
    "get_dict_entries": "sequence",
    "get_phases": "sequence",
    "validate_configuration": "sequence",
    "validate_run_semantics": "sequence",
    "predict_data_artifacts": "sequence",
    "get_base_mesh_geometry_diagnostics": "sequence",
    "get_mesh_geometry_diagnostics": "sequence",
    "get_environment_diagnostics": "sequence",
    "get_case_dict_key_diagnostics": "sequence",
    "get_function_object_field_diagnostics": "sequence",
    "get_utility_roots": "sequence",
    "get_extra_provenance_paths": "sequence",
    "get_telemetry_source_globs": "sequence",
    "get_required_inputs": "sequence",
    "get_generated_output_globs": "sequence",
    "get_report_catalog": "sequence",
    "get_regeneration_scopes": "sequence",
    "get_override_scopes": "sequence",
    "inspect_effective_configuration": "sequence",
    # -- single ------------------------------------------------------------
    "get_capabilities": "single",
    "get_selected_start_time": "single",
    "get_config_value_reader": "single",
    "get_dict_key_scanner": "single",
    "get_case_runtime_conventions": "single",
    "get_config_resolution_description": "single",
    "get_override_schema": "single",
    "get_run_document_config_schema": "single",
    "build_run_document_config": "single",
    "get_artifact_value_reader": "single",
    "get_loaded_environment": "single",
    "is_nondimensional_case": "single",
    "has_case_marker": "single",
    "is_case_runnable_without_workflow": "single",
    "is_installed_environment_command": "single",
    # -- chain -------------------------------------------------------------
    "get_configured_environment": "chain",
    # -- exclusive ---------------------------------------------------------
    "materialize_sweep_case": "exclusive",
    "route_sweep_case_values": "exclusive",
    "apply_overrides": "exclusive",
    "get_override_target_paths": "exclusive",
    # -- profile -----------------------------------------------------------
    "get_profile": "profile",
}

#: Members that must be answered by the SAME provider, keyed by the member
#: whose absence the error names. Generalises the single-plugin crash-safety
#: check in ``_OverrideScopeAdapter.target_paths``: a provider that mutates
#: without declaring what it touched is a data-loss risk, and splitting the
#: pair across two providers reintroduces exactly that risk while satisfying
#: "exactly one" for each member on its own. Spike finding #2, 2026-09-20.
_CROSS_MEMBER_PAIRS: tuple[tuple[str, str], ...] = (
    ("apply_overrides", "get_override_target_paths"),
)


def _check_classification() -> None:
    """Fail at import if a contract member carries no composition rule.

    Deliberately import-time and deliberately fatal. A member that reaches
    composition unclassified would have to fall through to some default, and
    whichever default that is would then be a rule nobody chose.
    """
    declared = set(_SHAPE)
    adapted = set()
    for members in capability_members().values():
        adapted |= set(members)
    unclassified = sorted(adapted - declared)
    if unclassified:
        raise ValueError(
            f"contract members {unclassified} are adapted by a capability but "
            f"carry no composition rule in provider_stack._SHAPE"
        )
    unknown = sorted(declared - adapted)
    if unknown:
        raise ValueError(
            f"provider_stack._SHAPE classifies {unknown}, which no capability "
            f"adapts; the seam table and the rule table have drifted"
        )


_check_classification()


def _implementers(ordered, member):
    """Providers exposing ``member``, least-specific first."""
    return tuple(
        provider for provider in ordered
        if callable(getattr(provider, member, None))
    )


def _union(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        merged: set = set()
        for provider in implementers:
            merged |= set(getattr(provider, member)(*args, **kwargs))
        return frozenset(merged)

    return _composed


def _concat(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        collected: list = []
        for provider in implementers:
            collected.extend(getattr(provider, member)(*args, **kwargs))
        return tuple(collected)

    return _composed


def _override_marker(value):
    """The provider id an entry claims to override, or ``None``.

    Silence must never resolve a collision, so the marker is read only from an
    entry that actually carries one; anything else is an unmarked duplicate.
    """
    try:
        return value.get("overrides")
    except AttributeError:
        return None


def _merge_with_override(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        merged: dict = {}
        declared_by: dict = {}
        for provider in implementers:
            for key, value in dict(getattr(provider, member)(*args, **kwargs)).items():
                marker = _override_marker(value)
                if key in merged:
                    if marker is None:
                        raise ValueError(
                            f"providers {declared_by[key]!r} and "
                            f"{provider.plugin_id!r} both declare {key!r} in "
                            f"{member}(); the more specific entry must carry "
                            f"overrides: {declared_by[key]!r} to replace it"
                        )
                    if marker != declared_by[key]:
                        raise ValueError(
                            f"provider {provider.plugin_id!r} declares {key!r} "
                            f"in {member}() with overrides: {marker!r}, but "
                            f"{declared_by[key]!r} is what declared that key"
                        )
                elif marker is not None:
                    raise ValueError(
                        f"provider {provider.plugin_id!r} declares {key!r} in "
                        f"{member}() with overrides: {marker!r}, which declared "
                        f"no such key; the declaration it shadowed is gone"
                    )
                merged[key] = value
                declared_by[key] = provider.plugin_id
        return merged

    return _composed


def _merge_catalog(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        from .contracts.dictionary_catalog import DictionaryCatalog

        documents: dict = {}
        declared_by: dict = {}
        for provider in implementers:
            catalog = getattr(provider, member)(*args, **kwargs)
            for name, entries in dict(catalog.documents).items():
                if name in documents:
                    raise ValueError(
                        f"providers {declared_by[name]!r} and "
                        f"{provider.plugin_id!r} both declare the dictionary "
                        f"document {name!r}"
                    )
                documents[name] = tuple(entries)
                declared_by[name] = provider.plugin_id
        return DictionaryCatalog(documents)

    return _composed


def _merge_tutorial_catalog(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        registered: list = []
        spec_factories: dict = {}
        declared_by: dict = {}
        extra: dict = {}
        for provider in implementers:
            catalog = dict(getattr(provider, member)(*args, **kwargs))
            for name in catalog.get("registered_tutorials", ()) or ():
                if name not in declared_by:
                    registered.append(name)
                    declared_by[name] = provider.plugin_id
            for name, factory in dict(catalog.get("spec_factories", {}) or {}).items():
                if name in spec_factories:
                    raise ValueError(
                        f"providers {spec_factories[name][1]!r} and "
                        f"{provider.plugin_id!r} both register the tutorial "
                        f"{name!r}"
                    )
                spec_factories[name] = (factory, provider.plugin_id)
            for key, value in catalog.items():
                if key in ("registered_tutorials", "spec_factories"):
                    continue
                # Most-specific value wins, same as the `single` shape -- an
                # extra key (e.g. cardiacFoam's `make_generic_case_spec`) is
                # provider-specific data, not a namespaced declaration.
                extra[key] = value
        return {
            "registered_tutorials": tuple(registered),
            "spec_factories": {
                name: factory for name, (factory, _owner) in spec_factories.items()
            },
            **extra,
        }

    return _composed


def _first_non_none(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(*args, **kwargs):
        for provider in reversed(implementers):
            answer = getattr(provider, member)(*args, **kwargs)
            if answer is not None:
                return answer
        return None

    return _composed


#: Recorded in place of a winner when no provider in the stack implements any
#: member of a capability. Naming the most specific provider there asserted an
#: ownership that did not exist; the capability adapter runs its declared
#: fallback, which belongs to no provider. Added 2026-09-22 (audit finding C3).
UNCLAIMED = "<unclaimed>"


def resolve_with_provenance(ordered, member, *args, **kwargs):
    """Run the ``single`` rule and report which provider actually answered.

    Returns ``(value, provider_id)``; ``(None, None)`` when every implementer
    returned ``None``. This is the same traversal :func:`_first_non_none`
    performs -- most specific first -- so the reported provider is the one whose
    value a caller would have received, not the one that merely declared the
    hook.
    """
    for provider in reversed(_implementers(tuple(ordered), member)):
        answer = getattr(provider, member)(*args, **kwargs)
        if answer is not None:
            return answer, provider.plugin_id
    return None, None


def _chain(ordered, implementers, member):
    if not implementers:
        return None

    def _composed(value, *args, **kwargs):
        current = value
        for provider in implementers:
            current = getattr(provider, member)(current, *args, **kwargs)
        return current

    return _composed


def _exactly_one(ordered, implementers, member):
    if not implementers:
        return None
    if len(implementers) > 1:
        raise ValueError(_exclusive_conflict(implementers, member))
    return getattr(implementers[0], member)


def _exclusive_conflict(implementers, member) -> str:
    return (
        f"providers {[p.plugin_id for p in implementers]} all implement "
        f"{member}(); exactly one provider in a stack may implement it, "
        f"because a second implementation would silently shadow the first"
    )


class _ComposedProfile:
    """One profile view over N providers' profiles.

    ``case_files`` is the concatenation -- §2.1's one-declarer rule is checked
    eagerly by :func:`_check_case_file_declarers`, so reaching here means the
    paths are already known to be disjoint. ``provides`` is the union, because
    the stack really does provide everything its members provide. Everything
    else comes from the most specific provider, which is the only honest
    answer for a single-valued field such as ``plugin_id``.
    """

    def __init__(self, profiles):
        self._profiles = tuple(profiles)
        self._primary = self._profiles[-1]

    @property
    def case_files(self):
        collected: list = []
        for profile in self._profiles:
            collected.extend(getattr(profile, "case_files", ()) or ())
        return tuple(collected)

    @property
    def provides(self):
        merged: set = set()
        for profile in self._profiles:
            merged |= set(getattr(profile, "provides", ()) or ())
        return frozenset(merged)

    @property
    def digest(self) -> str:
        import hashlib

        joined = "|".join(
            str(getattr(profile, "digest", "")) for profile in self._profiles
        )
        return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.__dict__["_primary"], name)


def _compose_profile(ordered, implementers, member):
    if not implementers:
        return None

    def _composed():
        return _ComposedProfile(
            tuple(getattr(provider, member)() for provider in implementers)
        )

    return _composed


_COMBINATORS = {
    "set": _union,
    "map": _merge_with_override,
    "catalog": _merge_catalog,
    "tutorial_catalog": _merge_tutorial_catalog,
    "sequence": _concat,
    "single": _first_non_none,
    "chain": _chain,
    "exclusive": _exactly_one,
    "profile": _compose_profile,
}


class _ComposedProvider:
    """One provider-shaped view over an ordered stack.

    Composition happens here, at the *contract member*, and not at the
    capability adapter: the adapters in :mod:`plugin_capabilities` already own
    argument shaping and the declared fallback for every member, and there is
    no second copy of that knowledge. A member no provider in the stack
    implements is deliberately ABSENT from this object, so
    ``adapt_plugin_capabilities`` probes it with ``getattr`` exactly as it does
    for a single plugin and runs the fallback the seam declares -- including
    the refusals that must not be neutral.
    """

    def __init__(self, ordered):
        self._ordered = tuple(ordered)
        self._primary = self._ordered[-1]
        self.plugin_id = self._primary.plugin_id
        for member, shape in _SHAPE.items():
            composed = _COMBINATORS[shape](
                self._ordered, _implementers(self._ordered, member), member,
            )
            if composed is not None:
                setattr(self, member, composed)

    @property
    def providers(self) -> tuple:
        return self._ordered

    def __getattr__(self, name):
        # A classified member absent from __dict__ was absent from every
        # provider. Delegating it to the most specific provider would
        # resurrect a member composition deliberately did not compose.
        if name.startswith("_") or name in _SHAPE:
            raise AttributeError(name)
        return getattr(self.__dict__["_primary"], name)


def _check_exclusive_arity(ordered) -> None:
    conflicts = [
        _exclusive_conflict(implementers, member)
        for member, shape in _SHAPE.items()
        if shape == "exclusive"
        and len(implementers := _implementers(ordered, member)) > 1
    ]
    if conflicts:
        raise ValueError("; ".join(conflicts))


def _check_cross_member_pairs(ordered) -> None:
    """Both halves of a crash-safety pair must come from one provider."""
    for mutator, declarer in _CROSS_MEMBER_PAIRS:
        mutators = _implementers(ordered, mutator)
        declarers = _implementers(ordered, declarer)
        if not mutators or not declarers:
            # Zero declarers with a mutator present is the single-plugin case
            # the capability adapter already refuses, by name, at call time.
            continue
        if mutators[-1] is not declarers[-1]:
            raise ValueError(
                f"provider {mutators[-1].plugin_id!r} implements {mutator}() "
                f"but {declarers[-1].plugin_id!r} implements {declarer}(); "
                f"both must come from the same provider, or the before-images "
                f"rollback restores are computed by a different provider than "
                f"the one mutating"
            )


def _check_case_file_declarers(ordered) -> None:
    """Spec §2.1: exactly one declarer per case-file path, always."""
    declared_by: dict = {}
    for provider in ordered:
        for rule in getattr(provider.get_profile(), "case_files", ()) or ():
            path = getattr(rule, "path", None)
            if path in declared_by:
                raise ValueError(
                    f"case file {path!r} is declared by both "
                    f"{declared_by[path]!r} and {provider.plugin_id!r}; one "
                    f"fact has one declarer, and tolerating two is how two "
                    f"sources of truth are born"
                )
            declared_by[path] = provider.plugin_id


def compose(ordered_providers):
    """Compose an ordered provider stack into one capability bundle.

    ``ordered_providers`` runs least-specific first, as :func:`order_providers`
    returns it. The result is an ordinary
    :class:`~omnidriver.core.plugin_capabilities.PluginCapabilities`, so every
    consumer of a single plugin's capabilities consumes a composed stack
    unchanged.

    The three checks below are eager because their failure is a packaging
    error, not a runtime one: it cannot depend on which capability a run
    happens to touch.
    """
    from .plugin_capabilities import adapt_plugin_capabilities

    ordered = tuple(ordered_providers)
    if not ordered:
        raise ValueError("compose() requires at least one provider")
    _check_exclusive_arity(ordered)
    _check_cross_member_pairs(ordered)
    _check_case_file_declarers(ordered)
    return adapt_plugin_capabilities(_ComposedProvider(ordered))


#: Capabilities whose resolved CONTENT is hashed into the stack digest. Spec
#: §4.4 keeps content digests to the three the single-plugin digest already
#: covered -- profile, dictionary vocabulary, manifest -- and records only the
#: resolution decision for the rest, because materializing all 25 at context
#: construction is what §3.4's uncached re-parsing makes expensive.
_DIGESTED_CAPABILITIES: dict[str, str] = {
    "cxx_mapping": "get_profile",
    "dictionaries": "get_dict_entries",
    "manifest": "get_capabilities",
}

#: What a capability carries instead of a content digest. Not an empty string:
#: a placeholder that reads as a placeholder in a provenance record.
RESOLUTION_PLACEHOLDER = "-"


def _content_digest(value) -> str:
    import hashlib
    import json

    from .plugin_interface import _identity_jsonable

    encoded = json.dumps(
        _identity_jsonable(value), sort_keys=True, separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def resolutions(ordered_providers) -> dict[str, tuple[str, str]]:
    """capability -> (winning provider id, resolved-content digest).

    The input to :func:`~omnidriver.core.provider_identity.build_stack_identity`,
    which hashes the composition RESULT rather than merely its inputs.

    For the three capabilities in :data:`_DIGESTED_CAPABILITIES` whose digested
    member is ``single``-shaped, the winner is the provider whose value the
    ``single`` rule actually used -- :func:`resolve_with_provenance` runs the
    same traversal :func:`_first_non_none` does, so "who answered" and "what
    the composed callable returns" can never disagree. For every other
    capability the winner remains the most specific declaring implementer: it
    is the best available claim, not an assertion about content, and the
    placeholder digest that accompanies it says so.

    Corrected 2026-09-22 (audit finding C3): the winner used to be the most
    specific provider that merely declared a member, for every capability --
    including the three that are actually resolved here. A provider that
    declared a ``single``-shaped hook and returned ``None`` was recorded as the
    source of a value ``_first_non_none`` fell through to a less specific
    provider to find.
    """
    ordered = tuple(ordered_providers)
    if not ordered:
        raise ValueError("resolutions() requires at least one provider")
    composed = _ComposedProvider(ordered)
    members = capability_members()
    resolved: dict[str, tuple[str, str]] = {}
    for capability in members:
        implementers = [
            provider
            for provider in ordered
            if any(
                callable(getattr(provider, member, None))
                for member in members[capability]
            )
        ]
        digested_member = _DIGESTED_CAPABILITIES.get(capability)
        if not implementers:
            resolved[capability] = (UNCLAIMED, RESOLUTION_PLACEHOLDER)
            continue
        if digested_member is None or not callable(
            getattr(composed, digested_member, None)
        ):
            # Not digested, or digested through a member this stack does not
            # implement: the declared most-specific implementer is the best
            # available claim, and the placeholder digest already says the
            # content behind it is not bound. Recorded, not asserted.
            resolved[capability] = (implementers[-1].plugin_id, RESOLUTION_PLACEHOLDER)
            continue
        if _SHAPE.get(digested_member) == "single":
            value, answering_id = resolve_with_provenance(ordered, digested_member)
            winner = answering_id or UNCLAIMED
        else:
            value = getattr(composed, digested_member)()
            winner = implementers[-1].plugin_id
        content = (
            getattr(value, "digest", None)
            if digested_member == "get_profile"
            else _content_digest(value)
        )
        resolved[capability] = (winner, content or RESOLUTION_PLACEHOLDER)
    return resolved
