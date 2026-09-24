"""Agent-requested changes to the values the native utilities read.

The catalog guides; it does not gate. Every declared entry is movable,
because the declaration exists to say what `setCardiacConductivity`,
`generatePurkinjeTree` and their siblings actually read -- not to say which
of those an agent is trusted with. Whether a *combination* of values makes
sense is the solver's question, expressed through the entries' own
constraints, not a question of which keys were routed here.

This replaces a ten-row `_TARGETS` allowlist (removed 2026-09-17). Its note
argued that the tree parameters "must stay declared-only", but the reasons
recorded around it were mechanical rather than principled: dynamic `<ventKey>`
segments had nowhere to route, and vector values had no accepted kind. Both
are handled here, the way `omnidriver-cardiacfoam` already handles them --
resolve the location from the path, pass the value through.

One refusal is kept, and it is not a permission: a key absent from the
catalog is one no native utility reads. OpenFOAM ignores an unknown
dictionary entry rather than rejecting it, so writing such a key is a silent
no-op -- the one failure the solver cannot report and this layer can.
"""

from __future__ import annotations

import datetime
import math
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Any

from omnidriver.core.case_write import (
    CaseMutationRequest,
    CaseWritePlan,
    CaseWriteRecord,
    ParameterAssignment,
    ResolvedMutation,
)
from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.openfoam import case_rendering
from omnidriver.openfoam.dict_builder import match_dynamic_entry
from omnidriver.openfoam.mutators import check_dictionary_word_is_safe, update_foam_entry

# ``VENT_KEYS`` is imported for re-export only, and is deliberately not
# used below any more -- see ``VENT_KEY_PLACEHOLDER``'s comment.
from ..catalogs.inputs import CATALOG, DOCUMENTS, VENT_KEYS  # noqa: F401

#: This adapter's identity on every request and resolution it produces.
PLUGIN_ID = "org.omnidriver.cardiaccore"

#: Path segment standing for a ventricle block in a declared path.
#:
#: Kept as documentation of how the placeholder is spelled, and re-exported
#: alongside ``VENT_KEYS`` for callers that already import both from here.
#: **Neither is consulted when matching a path any more** (2026-09-23): the
#: domain a dynamic segment must satisfy comes from the matched entry's own
#: ``allowed_bindings``, so ``<ventKey>`` is checked by the same mechanism as
#: ``<region_id>`` rather than by a constant this module happens to import.
VENT_KEY_PLACEHOLDER = "<ventKey>"


@dataclass(frozen=True)
class InputTarget:
    """Where one declared value lives in a case."""

    file_relpath: str
    key: str
    scope: tuple[str, ...] = ()


def _scope_token(entries: Sequence[Any]) -> str:
    return entries[0].driver_path.split(".", 1)[0]


#: ``$SCOPE`` token -> the case-relative dictionary that declares it. Derived
#: from the catalog rather than maintained by hand, so a new document is
#: reachable as soon as it is declared.
_DOCUMENT_FOR_SCOPE: dict[str, str] = {
    _scope_token(document.entries if hasattr(document, "entries") else document):
        f"system/{name}"
    for name, document in DOCUMENTS.items()
}

_ENTRIES = {entry.driver_path: entry for entry in CATALOG.entries}


def qualified_slot_key(driver_path: str) -> str:
    """The slot key for a declared path, keeping its document scope.

    ``core.specs.validation.slot_key`` strips the ``$SCOPE.`` prefix, which
    makes ``$CARDIAC_SCAR.fiberField`` and ``$CARDIAC_CONDUCTIVITY.fiberField``
    one slot. Which one survives a flatten then depends on catalog iteration
    order, and the surviving value can be ``None`` from a dictionary the case
    does not even have.

    This keeps the whole path, so a slot identifies one parameter in one
    document. Added 2026-09-22 (audit findings S1, S3).

    ``slot_key`` itself is core's and is unchanged: core cannot know that two
    adapter documents share a leaf name, and the unqualified form is still what
    a caller wants when it has already fixed the document.
    """
    return driver_path


def _declared_match(driver_path: str) -> "tuple[Any, dict[str, str]] | None":
    """The declared entry this concrete path instantiates, and what each of
    its placeholders captured -- **without** checking the captures.

    Corrected 2026-09-23: this used to walk the path looking for a segment
    that appeared in ``VENT_KEYS``, which made one placeholder's domain the
    matcher's own hardcoded knowledge. Two things followed. A second
    placeholder -- ``$PURKINJE_SCAR.regions.<region_id>`` -- matched nothing,
    so a legitimate region override was refused as "not declared". And
    ``<ventKey>`` was policed by a constant rather than by its entry, so the
    fix for audit finding S1 protected exactly the one placeholder someone
    had thought about. The match is now positional and domain-blind
    (`omnidriver.openfoam.dict_builder.match_dynamic_entry`, reused rather
    than re-implemented); `validate_dynamic_binding` below is where a capture
    is checked, against the entry's own ``allowed_bindings``.

    Candidates are filtered to the path's own ``$SCOPE`` token first, because
    `match_dynamic_entry` normalises through `slot_key`, which *strips* that
    token -- and this adapter's documents deliberately share leaf names
    (audit finding S3, see `qualified_slot_key`). Filtering first keeps a
    templated match as qualified as a literal one.
    """
    if driver_path in _ENTRIES:
        return _ENTRIES[driver_path], {}
    scope_token = driver_path.partition(".")[0]
    candidates = [
        entry for path, entry in _ENTRIES.items()
        if path.partition(".")[0] == scope_token
    ]
    return match_dynamic_entry(driver_path, candidates)


def validate_dynamic_binding(entry: Any, placeholder: str, bound_value: str) -> None:
    """Refuse a dynamic-path binding the entry's own declaration does not
    sanction. Same three outcomes as ``omnidriver-cardiacfoam``'s
    ``overrides._validate_dynamic_binding``, deliberately:

    - the placeholder is absent from ``allowed_bindings`` -- refused, because
      an *undeclared* placeholder is audit finding S1's hole itself, not a
      stated fact an agent can read;
    - the domain is ``None`` (explicitly open) -- validated as a word, and
      put through `check_dictionary_word_is_safe`, since the binding becomes
      a sub-block *name* and `update_foam_entry`'s own security check only
      ever inspects a written value;
    - the domain is a closed tuple -- membership is checked directly.
    """
    if placeholder not in entry.allowed_bindings:
        raise ValueError(
            f"{entry.driver_path!r} declares no binding domain for "
            f"{placeholder!r}; refusing to accept {bound_value!r} rather than "
            f"silently treating an undeclared placeholder as unconstrained"
        )
    domain = entry.allowed_bindings[placeholder]
    if domain is None:
        reasons = validate_value_shape("word", bound_value)
        if reasons:
            raise ValueError(
                f"input override binds {placeholder!r} to {bound_value!r} in "
                f"{entry.driver_path!r}, which is not a valid word: "
                f"{'; '.join(reasons)}"
            )
        check_dictionary_word_is_safe(bound_value)
        return
    if bound_value not in domain:
        raise ValueError(
            f"input override binds {placeholder!r} to {bound_value!r} where "
            f"{entry.driver_path!r} declares one of {sorted(domain)}"
        )


def _template_for(driver_path: str) -> str | None:
    """The declared path this concrete path instantiates, if any.

    Non-raising by contract: `preprocessing._reject_unstaged` compares the
    result against the paths a workflow stages, and an unmatched path must
    read as "not this workflow's" rather than blowing up there.
    `validate_input_overrides` re-does the match so it can report *why* a
    binding was refused.
    """
    match = _declared_match(driver_path)
    if match is None:
        return None
    entry, binding = match
    for placeholder, bound_value in binding.items():
        try:
            validate_dynamic_binding(entry, placeholder, bound_value)
        except ValueError:
            return None
    return entry.driver_path


def declared_path_template(driver_path: str) -> str | None:
    """The declared entry a concrete path instantiates, or None."""
    return _template_for(driver_path)


def resolve_override_target(driver_path: str) -> InputTarget:
    """Locate ``$SCOPE.a.b.key`` in the case, without a routing table."""
    scope_token, _, remainder = driver_path.partition(".")
    document = _DOCUMENT_FOR_SCOPE.get(scope_token)
    if document is None:
        known = ", ".join(sorted(_DOCUMENT_FOR_SCOPE))
        raise ValueError(
            f"input override {driver_path!r} has no declaring document; "
            f"known dictionaries: {known}"
        )
    if not remainder:
        raise ValueError(f"input override {driver_path!r} names no key")
    parts = remainder.split(".")
    return InputTarget(document, parts[-1], tuple(parts[:-1]))


_VECTOR_TEXT = re.compile(r"^\(\s*(\S+)\s+(\S+)\s+(\S+)\s*\)$")


def _require_finite(driver_path: str, value: Any) -> None:
    if isinstance(value, Real) and not math.isfinite(float(value)):
        raise ValueError(
            f"input override {driver_path!r} must be a finite number, not {value!r}; "
            f"a dictionary accepts the text and the solver fails at read time"
        )


def _check_value(driver_path: str, entry: Any, value: Any) -> None:
    kind = entry.value_kind
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise TypeError(f"input override {driver_path!r} must be a JSON integer")
        _require_finite(driver_path, value)
    elif kind == "scalar":
        if isinstance(value, bool) or not isinstance(value, Real):
            raise TypeError(f"input override {driver_path!r} must be a JSON number")
        _require_finite(driver_path, value)
    elif kind in {"word", "enum"}:
        if not isinstance(value, str) or not value:
            raise TypeError(f"input override {driver_path!r} must be a non-empty JSON string")
    elif kind == "vector3":
        # A dictionary spells a vector "(x y z)"; a caller may hand over
        # either that text or three numbers. Both reach the dictionary
        # unchanged, as they do in omnidriver-cardiacfoam.
        #
        # Corrected 2026-09-22 (audit finding S1): any non-empty string was
        # accepted, so "not a vector at all" was written into a vector entry
        # and failed natively at read time with no reference back to the
        # override that caused it.
        if isinstance(value, str):
            match = _VECTOR_TEXT.match(value.strip())
            if match is None:
                raise TypeError(
                    f"input override {driver_path!r} must be three numbers or a "
                    f"'(x y z)' string, not {value!r}"
                )
            for component in match.groups():
                try:
                    number = float(component)
                except ValueError:
                    raise TypeError(
                        f"input override {driver_path!r} component {component!r} "
                        f"is not a number"
                    ) from None
                _require_finite(driver_path, number)
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            if len(value) != 3 or any(
                isinstance(item, bool) or not isinstance(item, Real) for item in value
            ):
                raise TypeError(
                    f"input override {driver_path!r} must be three numbers or a '(x y z)' string"
                )
            for component in value:
                _require_finite(driver_path, component)
        else:
            raise TypeError(
                f"input override {driver_path!r} must be three numbers or a '(x y z)' string"
            )
    else:
        raise ValueError(
            f"input override {driver_path!r} has unsupported value kind {kind!r}"
        )
    if entry.enum_values and value not in entry.enum_values:
        raise ValueError(
            f"input override {driver_path!r} value {value!r} not in enum {entry.enum_values}"
        )


def validate_input_overrides(
    overrides: Mapping[str, Any] | None,
    *,
    allowed_paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if overrides is None:
        return {}
    if not isinstance(overrides, Mapping):
        raise TypeError("input_overrides must be a JSON object mapping declared paths to values")
    validated: dict[str, Any] = {}
    for driver_path, value in overrides.items():
        if not isinstance(driver_path, str):
            raise TypeError("input override paths must be strings")
        resolve_override_target(driver_path)
        match = _declared_match(driver_path)
        if match is None:
            raise ValueError(
                f"input override {driver_path!r} is not declared; no native utility reads "
                "that key, and OpenFOAM would ignore it rather than report it"
            )
        entry, binding = match
        # A bad binding is reported here, by the reason the entry's own
        # declaration gives, rather than collapsing into the generic "not
        # declared" refusal above -- the path IS declared; what it bound is
        # not. (Before 2026-09-23 this was a hand-rolled probe loop that
        # could only ever re-discover a `<ventKey>`.)
        for placeholder, bound_value in binding.items():
            validate_dynamic_binding(entry, placeholder, bound_value)
        template = entry.driver_path
        if allowed_paths is not None and template not in allowed_paths and driver_path not in allowed_paths:
            known = ", ".join(allowed_paths)
            raise ValueError(
                f"input override {driver_path!r} is not scheduled by this workflow. "
                f"Paths this workflow stages: {known}"
            )
        _check_value(driver_path, _ENTRIES[template], value)
        validated[driver_path] = value
    return validated


def _typed_value(value_kind: str, value: Any) -> Any:
    """Parse rendered text into the typed data a `ParameterAssignment` value
    must be (2026-09-23 decision: never rendered text). ``_check_value``
    already accepted a `vector3` as either a "(x y z)" string or three
    numbers; this is the adapter's job the decision assigns -- it owns what
    the parameter means, so it parses the string form here rather than
    letting it travel into the plan as text."""
    if value_kind == "vector3" and isinstance(value, str):
        match = _VECTOR_TEXT.match(value.strip())
        return tuple(float(component) for component in match.groups())
    if value_kind == "vector3" and isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(float(component) for component in value)
    return value


def _parameters_for(validated: Mapping[str, Any]) -> tuple[ParameterAssignment, ...]:
    """Build one addressed, typed `ParameterAssignment` per validated override."""
    parameters = []
    for driver_path, value in validated.items():
        target = resolve_override_target(driver_path)
        template = _template_for(driver_path)
        entry = _ENTRIES[template]
        key_path = target.scope + (target.key,)
        parameters.append(ParameterAssignment(
            qualified_id=driver_path, owner=PLUGIN_ID,
            document=target.file_relpath, key_path=key_path, binding={},
            value=_typed_value(entry.value_kind, value), value_kind=entry.value_kind,
            source="case",
        ))
    return tuple(parameters)


def resolve_patch_mutation(request: CaseMutationRequest) -> ResolvedMutation:
    """The semantic owner's answer for a `clone_and_patch` request.

    Pure: every parameter this touches was already addressed (document,
    key_path, typed value) when the caller built the request -- see
    `_parameters_for`, this module's only place that resolves a declared
    ``$SCOPE`` path against the catalog. This just repackages that addressing
    into a `ResolvedMutation`; it reads and writes nothing.
    """
    if request.mode != "clone_and_patch":
        raise ValueError(
            f"cardiacCore's overrides workflow resolves clone_and_patch "
            f"requests only, not {request.mode!r}"
        )
    targets = tuple(
        {
            "qualified_id": parameter.qualified_id,
            "document": parameter.document,
            "expanded_key_path": list(parameter.expanded_key_path()),
            "value": parameter.value,
            "format": "openfoam_dictionary",
        }
        for parameter in request.parameters
    )
    expected_effects = tuple(
        f"set {parameter.qualified_id!r} in {parameter.document}"
        for parameter in request.parameters
    )
    return ResolvedMutation(
        request=request, targets=targets, preconditions=(),
        expected_effects=expected_effects, semantic_owner_id=PLUGIN_ID,
    )


def _default_driver_context() -> Any:
    # Deferred: `..plugin` -> `.workflows.preprocessing` -> `.workflows.overrides`
    # is a real import cycle at module scope (this module is imported by
    # `workflows/preprocessing.py`, which `plugin.py` imports); resolving it
    # here, at call time, is what every other caller in this package that
    # needs a composed stack already does (see workflows/run_config.py).
    from omnidriver.core.plugin_interface import driver_context as make_driver_context
    from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

    from ..plugin import CardiacCorePlugin

    return make_driver_context(
        OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(),
        source="adapter:cardiaccore.overrides",
    )


def apply_input_overrides_planned(
    case_root: Path,
    overrides: Mapping[str, Any] | None,
    *,
    driver_context: Any | None = None,
    execution_env: Any | None = None,
) -> CaseWriteRecord | None:
    """Route `apply_input_overrides` through the case-write channel.

    Returns the committed `CaseWriteRecord`, or `None` when there was nothing
    to write -- `clone_and_patch` requires at least one parameter, and an
    override mapping that resolves to nothing is a no-op, not a mutation with
    zero effects.
    """
    from omnidriver.core.case_transaction import commit_case_write

    validated = validate_input_overrides(overrides)
    if not validated:
        return None

    # Made absolute here if it is not already, once, regardless of what the
    # caller passed in: `CaseMutationRequest` now refuses a relative
    # `case_root` outright (R3 blocker 2, 2026-09-23), and this is the one
    # place in this module that constructs one. Only a genuinely relative
    # path is resolved -- an already-absolute `case_root` (the common case)
    # is passed through exactly as given, rather than also normalizing away
    # a symlink nobody asked to have collapsed.
    case_root = Path(case_root)
    if not case_root.is_absolute():
        case_root = case_root.resolve()

    parameters = _parameters_for(validated)
    if driver_context is None:
        driver_context = _default_driver_context()

    request = CaseMutationRequest(
        mode="clone_and_patch", case_root=case_root, adapter_id=PLUGIN_ID,
        workflow="preprocessing", source_artifacts=(), parameters=parameters,
        requested_by="cardiaccore.overrides",
    )
    resolved = driver_context.capabilities.case_writer.resolve(
        request, driver_context=driver_context,
    )
    with tempfile.TemporaryDirectory(prefix="omnidriver-case-render-") as scratch:
        snapshot_root = Path(scratch)
        rendered = driver_context.capabilities.case_writer.render(
            resolved, snapshot_root=snapshot_root, driver_context=driver_context,
            execution_env=execution_env,
        )
        preconditions = resolved.preconditions + case_rendering.patch_preconditions(
            resolved, case_root=Path(case_root), execution_env=execution_env,
        )
        identity = getattr(driver_context, "identity", None)
        stack_identity = (
            identity.capability_digest if identity is not None else "0" * 64
        )
        plan = CaseWritePlan(
            request=request, files=rendered, preconditions=preconditions,
            semantic_owner_id=resolved.semantic_owner_id,
            stack_identity=stack_identity,
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
    return commit_case_write(plan, driver_context=driver_context, execution_env=execution_env)


def apply_input_overrides(case_root: Path, overrides: Mapping[str, Any] | None) -> None:
    apply_input_overrides_planned(case_root, overrides)
    return None


def _enumerate_declared_path(declared_path: str) -> tuple[str, ...]:
    """Every concrete path a declared path stands for, in a case.

    A static path stands for itself. A ``dynamic_path`` entry stands for one
    path per member of each placeholder's declared domain -- which is only
    enumerable when every one of those domains is *closed*.

    An **open** domain has no members to enumerate, so this returns nothing
    rather than the template. Corrected 2026-09-23: the old expansion
    substituted ``VENT_KEYS`` into a ``<ventKey>`` path and left every other
    template alone, so ``$PURKINJE_SCAR.regions.<region_id>.*`` was read
    literally and recorded as a value at a parameter address no case has --
    a placeholder invented as a key. Reporting nothing for a domain whose
    members only the case knows is the supplied-vs-discovered rule
    (``future/ENVIRONMENT_CONTRACT.md`` §12) applied here: this layer has no
    ambient truth about which region IDs a case defines, so it must not
    answer as if it did.
    """
    entry = _ENTRIES.get(declared_path)
    if entry is None or not getattr(entry, "dynamic_path", False):
        return (declared_path,)
    expanded = [declared_path]
    for placeholder, domain in entry.allowed_bindings.items():
        if not domain:  # None (explicitly open) or, defensively, empty
            return ()
        expanded = [
            path.replace(placeholder, member)
            for path in expanded
            for member in domain
        ]
    # An undeclared placeholder leaves its own spelling behind; that is a
    # catalog gap (`test_every_dynamic_entry_declares_a_domain_for_every_placeholder`)
    # and must not be reported as a readable parameter either.
    return tuple(path for path in expanded if "<" not in path)


def read_input_values(
    case_root: Path, *, paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    from omnidriver.openfoam.mutators import read_foam_entry

    selected = tuple(_ENTRIES) if paths is None else paths
    values: dict[str, Any] = {}
    for declared_path in selected:
        # A dynamic path names one value per binding, so it is recorded once
        # per block the case actually defines. read_foam_entry returns None
        # for an absent scope, so a case that declares only one ventricle
        # records only that one rather than inventing the other.
        concrete_paths = _enumerate_declared_path(declared_path)
        is_dynamic = concrete_paths != (declared_path,)
        for driver_path in concrete_paths:
            target = resolve_override_target(driver_path)
            value = read_foam_entry(
                case_root / target.file_relpath, target.key, scope=target.scope or None,
            )
            if value is None and is_dynamic:
                continue
            values[driver_path] = value
    return values
