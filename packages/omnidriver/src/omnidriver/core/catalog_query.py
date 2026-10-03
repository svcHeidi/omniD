"""``omnidriver catalog``: the entries of one dictionary for one solver.

One query over the stack's key catalogue (``get_record_key_catalog``), with ``cxx_values`` from the stack's scanner when the C++ source root is supplied; ``scan_query`` lists what the C++ reads and the catalogue lacks (``uncatalogued``) or no longer reads (``unread``). Core names no solver or document."""
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
    mapping = driver_context.stack.call("get_profile").cxx_mapping
    if mapping is None:
        return None
    root = mapping.source_root(environ)
    evidence: dict[str, Any] = {
        "variable": mapping.source_root_variable,
        "relative": mapping.source_root_relative,
        "root": str(root) if root is not None else None,
    }
    scanner = driver_context.stack.call("get_dict_key_scanner")
    if root is None or not root.is_dir() or scanner is None:
        evidence["scanned"] = False
        evidence["reason"] = (
            "source root not supplied" if root is None
            else "not a directory" if not root.is_dir() else "the stack has no key scanner"
        )
        return evidence
    report = scanner(
        root, allowlist_path=mapping.allowlist_path,
        entries=driver_context.stack.call("get_dict_entries"),
        cache_root=cache_root, force=force,
    ).to_json()
    evidence["scanned"] = True
    evidence.update(report)
    return evidence


_UNCATALOGUED_HOW = (
    "Each uncatalogued key carries `entry`: the DictEntry arguments the scan establishes "
    "(driver_path when its block is placed, value_kind, required, typical_value, source_refs). "
    "Write the description, unit and applicable_when/required_when from the C++ at `source`, "
    "then add the entry to the plugin's catalogue; `selected_as` names the selection-table "
    "class that reads it, and `required` is true when the read has no default and is not "
    "tested first. A `menu_value` or `selection_table` item names a model to add to an enum's "
    "enum_values."
)
_UNREAD_HOW = (
    "Each key is catalogued, and the supplied C++ no longer reads it, so setting it has no "
    "effect. Delete the entry, or correct its driver_path if the C++ moved the key; its "
    "description and source_refs say what it was for."
)


def scan_query(driver_context: "DriverContext", *, cache_root: Path | None, unread: bool = False) -> dict[str, Any]:
    """``omnidriver catalog --uncatalogued`` (every read the C++ makes that the
    catalogue lacks, with its scanned type, default, scope, source location and
    the entry arguments the scan can fill) or, with ``unread``, ``catalog
    --unread`` (every catalogued key the C++ no longer reads)."""
    cxx = cxx_evidence(driver_context, os.environ, cache_root=cache_root)
    listed = ("unread",) if unread else ("uncatalogued", "unresolved")
    return {
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "cxx_source": {
            key: value for key, value in (cxx or {}).items()
            if key not in ("uncatalogued", "unresolved", "unread", "disagreements", "selector_values")
        } if cxx is not None else None,
        "how": _UNREAD_HOW if unread else _UNCATALOGUED_HOW,
        **{name: (cxx or {}).get(name, []) for name in listed},
        **({} if unread else {"disagreements": (cxx or {}).get("disagreements", [])}),
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
    for listed in driver_context.stack.call("get_record_key_catalog", native_case_root):
        if not _matches(listed, document, key):
            continue
        listed = dict(listed)
        if listed.get("driver_path") in values:
            listed["cxx_values"] = values[listed["driver_path"]]
        entries.append(listed)
    if cxx is not None and cxx["scanned"]:
        cxx.pop("selector_values")
        for name in ("uncatalogued", "unresolved", "unread", "disagreements"):
            cxx[name] = len(cxx[name])
    return {
        "entry": record.name,
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "native_case_root": str(native_case_root),
        "document": document,
        "key": key,
        "cxx_source": cxx,
        "entries": entries,
    }
