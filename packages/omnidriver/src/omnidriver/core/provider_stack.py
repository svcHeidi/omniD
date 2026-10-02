"""Compose N providers into one stack, and answer a contract member over it.

Core owns composition; a provider never embeds another provider. Every
contract member is optional: :data:`MEMBERS` says how a stack composes the
providers that implement it, and what the stack answers when none does.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from typing import Any


@dataclass(frozen=True)
class Needed:
    """Absence refuses by name: no neutral answer is right for ``operation``."""

    operation: str


class MemberAbsent(ValueError):
    """No provider in the stack implements a member an operation needs."""


def _no_environment_validation() -> tuple:
    from .planning_types import diagnostic

    return (diagnostic(
        "error", "environment_capability_unavailable",
        "The selected adapter does not declare environment validation.",
        source="adapter",
    ),)


def _no_conventions():
    from .plugin_interface import CaseRuntimeConventions

    return CaseRuntimeConventions()


_RECORD = Needed("running a record case")
_WRITE = Needed("writing a case")

#: member -> (shape, absent).
#:
#: Shapes, over the providers that implement the member, least specific first:
#: ``set`` unions; ``map`` merges, refusing a duplicate key unless the more
#: specific entry carries ``overrides: <provider id>`` naming whose entry it
#: replaces; ``catalog`` is ``map`` over a ``DictionaryCatalog``'s documents;
#: ``sequence`` concatenates; ``single`` is the most specific non-``None``
#: answer; ``chain`` threads the first argument through each; ``profile``
#: composes every provider's declarative profile.
#:
#: Absent, when no provider implements the member (or, for ``single``, every
#: implementer answers ``None``): ``None`` answers the
#: shape's empty value (``chain`` returns its first argument); a function
#: answers what it returns; :class:`Needed` refuses by name.
MEMBERS: dict[str, tuple[str, Any]] = {
    "get_profile": ("profile", None),
    "get_capabilities": ("map", None),
    "get_named_catalogs": ("map", None),
    # dictionary vocabulary
    "get_dict_entries": ("sequence", None),
    "get_dictionary_catalog": ("catalog", None),
    "get_dict_groups": ("map", None),
    "get_dict_entry_catalog": ("map", None),
    "get_dict_key_scanner": ("single", None),
    # commands
    "get_solver_commands": ("set", None),
    "get_auxiliary_commands": ("set", None),
    "get_environment_commands": ("set", None),
    "is_installed_environment_command": ("single", None),
    "get_utility_manifests": ("map", None),
    "get_solve_step_commands": ("set", None),
    # planning and validation
    "validate_configuration": ("sequence", None),
    "validate_run_semantics": ("sequence", None),
    "predict_data_artifacts": ("sequence", None),
    "get_plan_diagnostics": ("sequence", None),
    "explain_step_failure": ("sequence", None),
    "inspect_effective_configuration": ("sequence", None),
    # environment
    "get_environment_diagnostics": ("sequence", _no_environment_validation),
    "get_loaded_environment": ("single", lambda: dict(os.environ)),
    "get_configured_environment": ("chain", None),
    "get_case_runtime_conventions": ("single", _no_conventions),
    # provenance
    "resolve_case_models": ("map", None),
    "get_samplable_fields": ("map", None),
    "get_required_inputs": ("sequence", None),
    "get_generated_output_globs": ("sequence", None),
    "get_input_roots": ("sequence", None),
    "get_extra_provenance_paths": ("sequence", None),
    "get_log_redaction_patterns": ("set", None),
    "get_artifact_value_reader": ("single", None),
    # records
    "get_tutorial_records": ("map", None),
    "get_record_key_catalog": ("sequence", None),
    "get_agent_guidance": ("sequence", None),
    "get_record_key_validator": ("single", _RECORD),
    "get_case_value_comparator": ("single", _RECORD),
    "get_config_value_reader": ("single", _RECORD),
    "get_parallel_steps": ("single", Needed("running a record in parallel")),
    # case writing
    "resolve_case_mutation": ("single", _WRITE),
    "get_supported_mutation_modes": ("single", _WRITE),
    "render_case_files": ("sequence", _WRITE),
    "get_rendered_formats": ("set", None),
}

#: Members a provider implements together or not at all: which modes a
#: resolver accepts, and which formats a renderer writes, are that provider's
#: own answers.
_PAIRS = (
    ("resolve_case_mutation", "get_supported_mutation_modes"),
    ("render_case_files", "get_rendered_formats"),
)


def _entry(member: str) -> tuple[str, Any]:
    try:
        return MEMBERS[member]
    except KeyError:
        raise KeyError(f"{member!r} is not a plugin contract member") from None


def provider_profile(provider: Any):
    """A provider's own profile; one that declares none has no case files,
    no C++ mapping, no environment connection and requires nothing."""
    hook = getattr(provider, "get_profile", None)
    if callable(hook):
        return hook()
    from .plugin_profile import PluginProfile

    return PluginProfile(
        path=None, plugin_id=provider.plugin_id, api_version=provider.plugin_api_version,
        case_files=(), cxx_mapping=None, payload={},
    )


def order_providers(providers) -> tuple:
    """Order providers least-specific first, by declared ``requires:``.

    Stable and hash-independent: every node is registered in sorted-id order
    before any edge, so independent providers keep sorted-by-id order, which
    the stack digest hashes. (Passing ``set(requires)`` to
    ``TopologicalSorter`` would follow ``PYTHONHASHSEED``.)
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
            f"depend on discovery order"
        )
    by_id = {provider.plugin_id: provider for provider in providers}
    requirements: dict[str, tuple[str, ...]] = {}
    for plugin_id in sorted(by_id):
        requires = tuple(provider_profile(by_id[plugin_id]).requires)
        missing = sorted(set(requires) - set(by_id))
        if missing:
            raise ValueError(
                f"provider {plugin_id!r} requires {missing}, which "
                f"{'is' if len(missing) == 1 else 'are'} not installed"
            )
        requirements[plugin_id] = tuple(sorted(set(requires)))
    sorter = TopologicalSorter()
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id)
    for plugin_id in sorted(requirements):
        sorter.add(plugin_id, *requirements[plugin_id])
    try:
        ordered = tuple(sorter.static_order())
    except CycleError as exc:
        raise ValueError(f"provider requirements form a cycle: {exc}") from exc
    return tuple(by_id[plugin_id] for plugin_id in ordered)


def _union(implementers, member, args, kwargs):
    merged: set = set()
    for provider in implementers:
        merged |= set(getattr(provider, member)(*args, **kwargs))
    return frozenset(merged)


def _concat(implementers, member, args, kwargs):
    collected: list = []
    for provider in implementers:
        collected.extend(getattr(provider, member)(*args, **kwargs))
    return tuple(collected)


def _override_marker(value):
    try:
        return value.get("overrides")
    except AttributeError:
        return None


def _merge(implementers, member, args, kwargs):
    merged: dict = {}
    declared_by: dict = {}
    for provider in implementers:
        for key, value in dict(getattr(provider, member)(*args, **kwargs)).items():
            marker = _override_marker(value)
            if key in merged:
                if marker is None:
                    raise ValueError(
                        f"providers {declared_by[key]!r} and {provider.plugin_id!r} "
                        f"both declare {key!r} in {member}(); the more specific "
                        f"entry must carry overrides: {declared_by[key]!r} to replace it"
                    )
                if marker != declared_by[key]:
                    raise ValueError(
                        f"provider {provider.plugin_id!r} declares {key!r} in "
                        f"{member}() with overrides: {marker!r}, but "
                        f"{declared_by[key]!r} is what declared that key"
                    )
            elif marker is not None:
                raise ValueError(
                    f"provider {provider.plugin_id!r} declares {key!r} in "
                    f"{member}() with overrides: {marker!r}, which declared no such key"
                )
            merged[key] = value
            declared_by[key] = provider.plugin_id
    return merged


def _merge_catalog(implementers, member, args, kwargs):
    from .contracts.dictionary_catalog import DictionaryCatalog

    documents: dict = {}
    declared_by: dict = {}
    for provider in implementers:
        for name, entries in dict(getattr(provider, member)(*args, **kwargs).documents).items():
            if name in documents:
                raise ValueError(
                    f"providers {declared_by[name]!r} and {provider.plugin_id!r} "
                    f"both declare the dictionary document {name!r}"
                )
            documents[name] = tuple(entries)
            declared_by[name] = provider.plugin_id
    return DictionaryCatalog(documents)


def _first(implementers, member, args, kwargs):
    for provider in reversed(implementers):
        answer = getattr(provider, member)(*args, **kwargs)
        if answer is not None:
            return answer
    return None


def _chain(implementers, member, args, kwargs):
    value, *rest = args
    for provider in implementers:
        value = getattr(provider, member)(value, *rest, **kwargs)
    return value


def _empty_catalog():
    from .contracts.dictionary_catalog import DictionaryCatalog

    return DictionaryCatalog({})


_COMPOSE = {
    "set": _union, "map": _merge, "catalog": _merge_catalog,
    "sequence": _concat, "single": _first, "chain": _chain,
}

_EMPTY = {
    "set": lambda args: frozenset(), "map": lambda args: {},
    "catalog": lambda args: _empty_catalog(), "sequence": lambda args: (),
    "single": lambda args: None, "chain": lambda args: args[0],
}


class _ComposedProfile:
    """Every provider's profile as one: case-file rules concatenated (one
    declarer per path, checked when the stack is built), ``requires``
    unioned, everything else from the most specific provider."""

    def __init__(self, profiles):
        self._profiles = tuple(profiles)
        self._primary = self._profiles[-1]

    @property
    def case_files(self):
        return tuple(rule for profile in self._profiles for rule in profile.case_files)

    @property
    def digest(self) -> str:
        joined = "|".join(profile.digest for profile in self._profiles)
        return "sha256:" + hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.__dict__["_primary"], name)


class ProviderStack:
    """An ordered provider stack, least specific first, that answers every
    contract member through :meth:`call`."""

    def __init__(self, ordered):
        self.providers = tuple(ordered)
        if not self.providers:
            raise ValueError("a provider stack needs at least one provider")
        self._profile = _ComposedProfile(provider_profile(p) for p in self.providers)
        self._check_case_file_declarers()
        self._check_format_declarers()

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(provider.plugin_id for provider in self.providers)

    def implementers(self, member: str) -> tuple:
        """The providers implementing ``member``, least specific first."""
        _entry(member)
        return tuple(p for p in self.providers if callable(getattr(p, member, None)))

    def implements(self, member: str) -> bool:
        return bool(self.implementers(member))

    def call(self, member: str, *args: Any, **kwargs: Any) -> Any:
        """``member`` composed over the providers that implement it, or the
        stack's answer for its absence; raises :class:`MemberAbsent` when an
        operation needs it."""
        shape, absent = _entry(member)
        if shape == "profile":
            return self._profile
        implementers = self.implementers(member)
        if implementers:
            answer = _COMPOSE[shape](implementers, member, args, kwargs)
            if answer is not None or shape != "single":
                return answer
        if isinstance(absent, Needed):
            raise self.refusal(member)
        return absent() if absent is not None else _EMPTY[shape](args)

    def refusal(self, member: str) -> MemberAbsent:
        """The refusal for a needed ``member`` no provider implements."""
        absent = _entry(member)[1]
        operation = absent.operation if isinstance(absent, Needed) else "this operation"
        return MemberAbsent(
            f"the provider stack {list(self.ids)} implements no {member}(), "
            f"which {operation} needs"
        )

    def _check_case_file_declarers(self) -> None:
        declared_by: dict = {}
        for provider in self.providers:
            for rule in provider_profile(provider).case_files:
                if rule.path in declared_by:
                    raise ValueError(
                        f"case file {rule.path!r} is declared by both "
                        f"{declared_by[rule.path]!r} and {provider.plugin_id!r}; "
                        f"one fact has one declarer"
                    )
                declared_by[rule.path] = provider.plugin_id

    def _check_format_declarers(self) -> None:
        declared_by: dict[str, str] = {}
        for provider in self.implementers("get_rendered_formats"):
            for file_format in provider.get_rendered_formats():
                if file_format in declared_by:
                    raise ValueError(
                        f"format {file_format!r} is rendered by both "
                        f"{declared_by[file_format]!r} and {provider.plugin_id!r}; "
                        f"the bytes on disk would depend on composition order"
                    )
                declared_by[file_format] = provider.plugin_id


def check_provider_members(provider: Any) -> list[str]:
    """One problem per malformed member: a public callable the contract does
    not name (a misspelling would otherwise be ignored), a member that is
    neither callable nor ``None``, or half of a pair in :data:`_PAIRS`."""
    from .plugin_interface import IDENTITY_MEMBERS

    problems: list[str] = []
    for name in dir(provider):
        if name.startswith("_") or name in IDENTITY_MEMBERS:
            continue
        value = getattr(provider, name, None)
        if name in MEMBERS:
            # None declares the member absent, as a subclass removing one does.
            if value is not None and not callable(value):
                problems.append(f"{name} must be callable")
        elif callable(value):
            problems.append(f"{name} is not a plugin contract member")
    for first, second in _PAIRS:
        has = (callable(getattr(provider, first, None)), callable(getattr(provider, second, None)))
        if has[0] != has[1]:
            present, missing = (first, second) if has[0] else (second, first)
            problems.append(f"{present}() needs {missing}() from the same provider")
    return problems


#: Recorded in place of a winner when no provider implements a member.
UNCLAIMED = "<unclaimed>"

#: What a member carries instead of a content digest.
RESOLUTION_PLACEHOLDER = "-"

#: Members whose resolved content is hashed into the stack digest.
_DIGESTED = ("get_profile", "get_dict_entries", "get_capabilities")


def content_digest(value) -> str:
    from .plugin_interface import identity_jsonable

    encoded = json.dumps(identity_jsonable(value), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def resolutions(stack: ProviderStack) -> dict[str, tuple[str, str]]:
    """member -> (most specific implementing provider, content digest), the
    input to ``provider_identity.build_stack_identity``."""
    resolved: dict[str, tuple[str, str]] = {}
    for member in MEMBERS:
        implementers = stack.implementers(member)
        if not implementers:
            resolved[member] = (UNCLAIMED, RESOLUTION_PLACEHOLDER)
            continue
        winner = implementers[-1].plugin_id
        if member not in _DIGESTED:
            resolved[member] = (winner, RESOLUTION_PLACEHOLDER)
            continue
        value = stack.call(member)
        resolved[member] = (winner, value.digest if member == "get_profile" else content_digest(value))
    return resolved
