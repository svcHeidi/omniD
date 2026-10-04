"""The tutorial-record key validator shared by every OpenFOAM-based plugin.

A plugin supplies how a key path finds its catalogue entry (:class:`CataloguedDocument`).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from omnidriver.core.contracts.dictionary import validate_value_shape
from omnidriver.core.runtime.record_surface import ANY_KEY

from .dict_keys_scanner import cxx_value_kind, document_scans, supplied_scan

from .mutators import check_dictionary_word_is_safe


def infer_unvalidated_value_kind(value: Any) -> str:
    """Best-effort, purely descriptive shape tag for an OpenFOAM-owned key no
    plugin catalogs; never checked against anything.

    `bool` is checked before `int` because `bool` is an `int` subclass.
    """
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "scalar"
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return "integer_list"
        return "scalar_list"
    if isinstance(value, str) and value.split() != [value]:
        return "string"
    return "word"


def _listed_relation(relation: Mapping[str, Any]) -> dict[str, Any]:
    return {name: list(value) if isinstance(value, tuple) else value for name, value in relation.items()}


def listed_entry(document: str, key: str, entry: Any) -> dict[str, Any]:
    """One key-catalogue listing (`record_surface`'s grammar) for a
    catalogued `DictEntry`: what `describe` and `omnidriver catalog` show
    for it, including the relations ``case_rules`` judges a case by, so an
    agent reads a rule before a plan refuses it. A `typical_value` is what a
    built case writes; a `default` is stated only for a selector whose absence
    the rules read as that value. A field the entry leaves empty is not
    listed."""
    listing = {
        "document": document, "key": key, "driver_path": entry.driver_path,
        "value_kind": entry.value_kind, "unit": entry.unit,
        "description": entry.description, "menu": list(entry.enum_values),
        "typical_value": entry.typical_value,
        "applicable_when": _listed_relation(entry.applicable_when),
        "source_refs": list(entry.source_refs),
    }
    extras = {
        "required": entry.required,
        "required_when": _listed_relation(entry.required_when),
        "forbidden_when": _listed_relation(entry.forbidden_when),
        "mutually_exclusive_with": list(entry.mutually_exclusive_with),
        "co_required_with": list(entry.co_required_with),
        "required_one_of": list(entry.required_one_of),
        "default": entry.default,
        "allowed_bindings": {name: None if domain is None else list(domain) for name, domain in entry.allowed_bindings.items()},
        "constraints": list(entry.constraints),
        "examples": list(entry.examples),
        "notes": entry.notes,
    }
    return {**listing, **{name: value for name, value in extras.items() if value}}


def scanned_key(
    document: str, catalog_path: "tuple[str, ...]", value: Any, *, mapping: Any, entries: Iterable[Any],
) -> "tuple[str, bool]":
    """``(value_kind, True)`` for a key the catalogue lacks that the
    plugin's supplied C++ reads at exactly ``catalog_path``: a read whose
    root ``dict_keys_scanner.locate`` places in ``document`` (catalogued by
    ``entries``) so that place, its scope and its key spell that path.
    ``catalog_path`` is in the catalogue's spelling (a ``$TOKEN`` first
    segment for a scoped block). Raises ``KeyError`` saying why when no read
    matches, and ``ValueError`` when the value does not fit the scanned
    type."""
    from .dict_keys_scanner import _segment_matches, locate, value_kind_of

    scan = supplied_scan(mapping)
    if scan is None:
        variable = mapping.source_root_variable if mapping is not None else "the source root"
        raise KeyError(f"the C++ source is not supplied ({variable}), so no uncatalogued key can be checked")
    name = document.rsplit("/", 1)[-1]
    reads = [
        read for read in scan.reads
        if read.value_read and read.key == catalog_path[-1]
        and (not read.root.startswith("document:") or read.root == f"document:{name}")
    ]
    if not reads:
        raise KeyError(f"the supplied C++ reads no key named {catalog_path[-1]!r}")
    placed = locate(scan, entries, document=name)
    spelled = [
        (read, place + read.scope + (read.key,)) for read in reads for place in placed.get(read.root, ())
    ]
    matching = [
        read for read, path in spelled
        if len(path) == len(catalog_path) and all(_segment_matches(key, listed) for listed, key in zip(path, catalog_path))
    ]
    if not matching:
        if spelled:
            raise KeyError(
                f"the supplied C++ reads {catalog_path[-1]!r} at "
                f"{', '.join(sorted({'.'.join(path) for _read, path in spelled}))}, not at {'.'.join(catalog_path)}"
            )
        raise KeyError(
            f"the supplied C++ reads {catalog_path[-1]!r} only through dictionaries the scan cannot place ("
            + ", ".join(sorted({f"{read.file}:{read.line}" for read in reads})) + ")"
        )
    kinds = {value_kind_of(read.type) for read in matching} - {None}
    if len(kinds) != 1:
        return infer_unvalidated_value_kind(value), True
    (kind,) = kinds
    reasons = validate_value_shape(kind, value)
    if reasons:
        raise ValueError(
            f"this uncatalogued key is read by the C++ as "
            f"{matching[0].type} ({matching[0].file}:{matching[0].line}): {'; '.join(reasons)}"
        )
    return kind, True


def check_binding(entry: Any, placeholder: str, bound_value: str) -> None:
    """Refuse a dynamic-path binding the entry's own ``allowed_bindings``
    does not sanction: an undeclared placeholder, an open domain whose value
    is not a safe word (it becomes a dictionary key), or a value outside a
    closed domain."""
    if placeholder not in entry.allowed_bindings:
        raise ValueError(
            f"{entry.driver_path!r} declares no binding domain for {placeholder!r}; "
            f"refusing to accept {bound_value!r} rather than treating an undeclared "
            "placeholder as unconstrained"
        )
    domain = entry.allowed_bindings[placeholder]
    if domain is None:
        reasons = validate_value_shape("word", bound_value)
        if reasons:
            raise ValueError(
                f"{placeholder!r} bound to {bound_value!r} in {entry.driver_path!r}, "
                f"which is not a valid word: {'; '.join(reasons)}"
            )
        check_dictionary_word_is_safe(bound_value)
    elif bound_value not in domain:
        raise ValueError(
            f"{placeholder!r} bound to {bound_value!r} in {entry.driver_path!r}, "
            f"which is not one of {list(domain)}"
        )


@dataclass(frozen=True)
class CataloguedDocument:
    """How one catalogued document resolves a key path.

    ``match`` returns the ``(entry, binding)`` a key path addresses, or
    ``None``. ``scan`` returns the catalogue spelling the C++ scan is asked
    about (a ``$TOKEN`` first segment for a scoped block). ``members`` says
    whether the catalogue declares a path's members as one dynamic segment,
    which a whole mapping value then fills.
    """

    label: str
    entries: Callable[[], Iterable[Any]]
    match: Callable[[tuple[str, ...]], "tuple[Any, dict[str, str]] | None"]
    scan: Callable[[tuple[str, ...]], tuple[str, ...]]
    members: Callable[[tuple[str, ...]], bool] = lambda key_path: False


def make_validator(
    documents: Mapping[str, CataloguedDocument], *, mapping: Callable[[], Any], owner: str,
) -> Callable[[str, "tuple[str, ...]", Any], "tuple[str, bool]"]:
    """The ``get_record_key_validator`` answer for a plugin whose
    catalogued ``documents`` are given. ``mapping`` returns the plugin's
    ``cxx_mapping``; ``owner`` names the plugin in refusals."""

    # A key of a catalogued document is checked against its entry's ``value_kind``;
    # a key the catalogue lacks passes only when the plugin's C++ reads it there
    # (``scanned_key``). Any other ``system/`` document is written as asked,
    # ``validated=False``, tagged by an inferred shape; anything else is refused.
    views: dict[str, Any] = {}

    def validate(document: str, key_path: "tuple[str, ...]", value: Any) -> "tuple[str, bool]":
        dotted = ".".join(key_path)
        catalogued = documents.get(document)
        if catalogued is not None:
            match = catalogued.match(key_path)
            if match is None and isinstance(value, Mapping) and catalogued.members(key_path):
                for member, member_value in value.items():
                    validate(document, key_path + (str(member),), member_value)
                return "mapping", True
            if match is None:
                try:
                    return scanned_key(
                        document, catalogued.scan(key_path), value,
                        mapping=mapping(), entries=catalogued.entries(),
                    )
                except KeyError as exc:
                    raise KeyError(
                        f"{document}:{dotted} is not declared by the {catalogued.label} key catalog, and "
                        f"{exc.args[0]} (omnidriver catalog --uncatalogued lists what it reads)"
                    ) from None
            entry, binding = match
            for placeholder, bound_value in binding.items():
                check_binding(entry, placeholder, bound_value)
            scan = supplied_scan(mapping())
            if scan is not None and scan.digest not in views:
                views[scan.digest] = document_scans(scan, {
                    name.rsplit("/", 1)[-1]: listed.entries() for name, listed in documents.items()
                })
            kind = (
                scan is not None and cxx_value_kind(views[scan.digest][document.rsplit("/", 1)[-1]].scan, entry)
            ) or entry.value_kind
            reasons = validate_value_shape(kind, value)
            if reasons:
                raise ValueError(
                    f"{document}:{dotted} does not fit "
                    + (
                        f"value_kind {kind!r}, which the supplied C++ reads it as (the catalogue says {entry.value_kind!r})"
                        if kind != entry.value_kind else f"catalogued value_kind {entry.value_kind!r}"
                    )
                    + f": {'; '.join(reasons)}"
                )
            return kind, True
        if document.startswith("system/"):
            return infer_unvalidated_value_kind(value), False
        raise KeyError(
            f"{document}:{dotted} is neither a {owner}-catalogued document ({', '.join(sorted(documents))}) "
            "nor an OpenFOAM-owned 'system/' document; refusing rather than silently treating an "
            "unrecognised document as an unvalidated OpenFOAM key"
        )

    return validate


def open_system_documents(case_root: Path, *, exclude: Iterable[str] = ()) -> "tuple[dict[str, Any], ...]":
    """Every ``system/`` file of the case, listed once as an open document
    (any key, ``validated: False``) in ``record_surface``'s grammar, except
    the catalogued ones in ``exclude``."""
    case_root = Path(case_root)
    skipped = set(exclude)
    return tuple(
        {"document": path.relative_to(case_root).as_posix(), "key": ANY_KEY, "validated": False}
        for path in sorted((case_root / "system").rglob("*"))
        if path.is_file() and path.relative_to(case_root).as_posix() not in skipped
    )
