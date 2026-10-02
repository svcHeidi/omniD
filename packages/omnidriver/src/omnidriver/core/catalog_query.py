"""``omnidriver catalog``: the entries of one dictionary for one solver.

One query over the one canonical key catalogue a record has
(``RecordSurfaceCapability.key_catalog``, what ``describe`` shows as
``record_surface.keys`` and what the record-key validator refuses by), so an
agent can ask for a document or a key without reading all of ``describe``.

When the stack's C++ source root is supplied (``cxx_mapping.source_root``),
the stack's own scanner runs, and every entry whose values the C++ registers
(a runtime-selection table) carries them as ``cxx_values``.
``uncatalogued_query`` lists what the C++ reads and the catalogue lacks, so
an agent can describe it and add it. Core names no solver and no document:
it filters what the plugin lists and attaches what the scanner returns.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .runtime.record_surface import ANY_KEY, key_pattern, lists_key
from .tutorial_records import lookup_record

if TYPE_CHECKING:
    from .plugin_interface import DriverContext
    from .tutorial_records import TutorialRecord


def _matches(entry: Mapping[str, Any], document: str | None, key: str | None) -> bool:
    if document is not None and entry.get("document") != document:
        return False
    if key is None:
        return True
    if document is not None:
        return lists_key(entry, document, key)
    listed = str(entry.get("key", ""))
    return listed != ANY_KEY and (listed == key or key_pattern(listed).fullmatch(key) is not None)


def cxx_evidence(
    driver_context: "DriverContext", environ: Mapping[str, str], *,
    cache_root: Path | None = None, force: bool = False,
) -> dict[str, Any] | None:
    """What the stack's scanner reports for its supplied C++ source, or
    ``None`` for a stack that declares no C++ mapping (openCARP: its catalogue
    is generated from the binary itself)."""
    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    if mapping is None:
        return None
    root = mapping.source_root(environ)
    evidence: dict[str, Any] = {
        "variable": mapping.source_root_variable,
        "relative": mapping.source_root_relative,
        "root": str(root) if root is not None else None,
    }
    if root is None or not root.is_dir():
        evidence["scanned"] = False
        evidence["reason"] = "source root not supplied" if root is None else "not a directory"
        return evidence
    report = driver_context.capabilities.dict_key_scanner.scan(
        root, allowlist_path=mapping.allowlist_path,
        entries=driver_context.capabilities.dictionaries.entries(),
        cache_root=cache_root, force=force,
    ).to_json()
    evidence["scanned"] = True
    evidence.update(report)
    return evidence


def uncatalogued_query(driver_context: "DriverContext", *, cache_root: Path | None) -> dict[str, Any]:
    """``omnidriver catalog --uncatalogued``: every read the C++ makes that
    the catalogue lacks, with its scanned type, default, scope and source
    location, and the reads the scan could not place."""
    cxx = cxx_evidence(driver_context, os.environ, cache_root=cache_root)
    return {
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "cxx_source": {
            key: value for key, value in (cxx or {}).items()
            if key not in ("uncatalogued", "unresolved", "selector_values")
        } if cxx is not None else None,
        "uncatalogued": (cxx or {}).get("uncatalogued", []),
        "unresolved": (cxx or {}).get("unresolved", []),
    }


def catalog_query(
    entry: "str | TutorialRecord",
    *,
    cases_root: Path,
    document: str | None = None,
    key: str | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    record = lookup_record(entry, driver_context=driver_context)
    native_case_root = Path(cases_root) / record.native_case_relpath
    cxx = cxx_evidence(driver_context, os.environ)
    values = (cxx or {}).get("selector_values", {})
    entries = []
    for listed in driver_context.capabilities.record_surface.key_catalog(native_case_root):
        if not _matches(listed, document, key):
            continue
        listed = dict(listed)
        if listed.get("driver_path") in values:
            listed["cxx_values"] = values[listed["driver_path"]]
        entries.append(listed)
    if cxx is not None and cxx["scanned"]:
        cxx.pop("selector_values")
        cxx["uncatalogued"] = len(cxx["uncatalogued"])
        cxx["unresolved"] = len(cxx["unresolved"])
    return {
        "entry": record.name,
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "native_case_root": str(native_case_root),
        "document": document,
        "key": key,
        "cxx_source": cxx,
        "entries": entries,
    }
