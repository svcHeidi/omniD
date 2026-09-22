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

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from numbers import Integral, Real
from pathlib import Path
from typing import Any

from omnidriver.openfoam.mutators import update_foam_entry

from ..catalogs.inputs import CATALOG, DOCUMENTS, VENT_KEYS

#: Path segment standing for a ventricle block in a declared path.
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


def _template_for(driver_path: str) -> str | None:
    """The declared path this concrete path instantiates, if any.

    A declared ``<ventKey>`` entry covers every key in ``VENT_KEYS``, so the
    concrete path is matched back to its template to find the declaration that
    describes it.

    Corrected 2026-09-22 (audit finding S1): the segment was previously
    substituted without being checked, so ``$PURKINJE_TREE.banana.seed`` matched
    ``$PURKINJE_TREE.<ventKey>.seed`` and was written into a ``banana`` block no
    native utility reads. A dynamic segment is now valid only when it is one of
    the bindings the placeholder declares.
    """
    if driver_path in _ENTRIES:
        return driver_path
    parts = driver_path.split(".")
    for index in range(1, len(parts)):
        if parts[index] not in VENT_KEYS:
            continue
        candidate = ".".join(
            [*parts[:index], VENT_KEY_PLACEHOLDER, *parts[index + 1:]]
        )
        if candidate in _ENTRIES:
            return candidate
    return None


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
        template = _template_for(driver_path)
        if template is None:
            parts = driver_path.split(".")
            for index in range(1, len(parts)):
                probe = ".".join(
                    [*parts[:index], VENT_KEY_PLACEHOLDER, *parts[index + 1:]]
                )
                if probe in _ENTRIES:
                    raise ValueError(
                        f"input override {driver_path!r} binds "
                        f"{parts[index]!r} where {probe!r} declares one of "
                        f"{sorted(VENT_KEYS)}"
                    )
            raise ValueError(
                f"input override {driver_path!r} is not declared; no native utility reads "
                "that key, and OpenFOAM would ignore it rather than report it"
            )
        if allowed_paths is not None and template not in allowed_paths and driver_path not in allowed_paths:
            known = ", ".join(allowed_paths)
            raise ValueError(
                f"input override {driver_path!r} is not scheduled by this workflow. "
                f"Paths this workflow stages: {known}"
            )
        _check_value(driver_path, _ENTRIES[template], value)
        validated[driver_path] = value
    return validated


def apply_input_overrides(case_root: Path, overrides: Mapping[str, Any] | None) -> None:
    for driver_path, value in validate_input_overrides(overrides).items():
        target = resolve_override_target(driver_path)
        # A declared key the selected case leaves unset relies on the
        # compiled default; setting it means writing it in. The declaration
        # is what makes this safe -- the key is one a native utility reads.
        update_foam_entry(
            case_root / target.file_relpath, target.key, value,
            scope=target.scope or None, add_if_missing=True,
        )


def read_input_values(
    case_root: Path, *, paths: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    from omnidriver.openfoam.mutators import read_foam_entry

    selected = tuple(_ENTRIES) if paths is None else paths
    values: dict[str, Any] = {}
    for declared_path in selected:
        # A <ventKey> path names one value per ventricle, so it is recorded
        # once per block the case actually defines. read_foam_entry returns
        # None for an absent scope, so a case that declares only one
        # ventricle records only that one rather than inventing the other.
        concrete_paths = (
            tuple(declared_path.replace(VENT_KEY_PLACEHOLDER, vent) for vent in VENT_KEYS)
            if VENT_KEY_PLACEHOLDER in declared_path
            else (declared_path,)
        )
        for driver_path in concrete_paths:
            target = resolve_override_target(driver_path)
            value = read_foam_entry(
                case_root / target.file_relpath, target.key, scope=target.scope or None,
            )
            if value is None and VENT_KEY_PLACEHOLDER in declared_path:
                continue
            values[driver_path] = value
    return values
