"""``omnidriver catalog``: the entries of one dictionary for one solver.

One query over the one canonical key catalogue a record has
(``RecordSurfaceCapability.key_catalog``, what ``describe`` shows as
``record_surface.keys`` and what the record-key validator refuses by), so an
agent can ask for a document or a key without reading all of ``describe``.

When the stack's C++ source root is supplied (``cxx_mapping.source_root``),
the stack's own scanner runs, and every entry whose values the C++ registers
(a runtime-selection table) carries them as ``cxx_values``. Core names no
solver, no document and no scanner schema: it filters what the plugin lists
and attaches what the scanner returns.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from .runtime.record_surface import ANY_KEY, key_pattern, lists_key

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


def _matches(entry: Mapping[str, Any], document: str | None, key: str | None) -> bool:
    if document is not None and entry.get("document") != document:
        return False
    if key is None:
        return True
    if document is not None:
        return lists_key(entry, document, key)
    listed = str(entry.get("key", ""))
    return listed != ANY_KEY and (listed == key or key_pattern(listed).fullmatch(key) is not None)


def cxx_evidence(driver_context: "DriverContext", environ: Mapping[str, str]) -> dict[str, Any] | None:
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
    ).to_json()
    evidence["scanned"] = True
    evidence["status"] = report.get("status")
    evidence["drift"] = {key: items for key, items in report.items() if isinstance(items, list) and items}
    evidence["selector_values"] = report.get("selector_values", {})
    return evidence


def catalog_query(
    entry: str,
    *,
    cases_root: Path,
    document: str | None = None,
    key: str | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    from .runtime.registry import resolve_entry
    from .tutorial_records import TutorialRecordError

    resolution = resolve_entry(entry, overrides={"cases_root": str(cases_root)}, driver_context=driver_context)
    if resolution["resolution"] != "tutorial_record":
        raise TutorialRecordError(
            f"catalog lists a tutorial record's keys, and {entry!r} is not a tutorial record"
        )
    record = resolution["record"]
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
    if cxx is not None:
        cxx.pop("selector_values", None)
    return {
        "entry": entry,
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "native_case_root": str(native_case_root),
        "document": document,
        "key": key,
        "cxx_source": cxx,
        "entries": entries,
    }
