"""What an OpenFOAM-based stack adds to a strict plan: the catalogue compared
with the solver's own C++, the sampled fields a function object names, the
case keys nothing catalogues, and the notes the rules have for the case."""

from __future__ import annotations

import fnmatch
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from omnidriver.core.contracts.catalogue_paths import catalogued_paths, slot_key
from omnidriver.core.capability_manifest import capability_manifest
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .case_dict_keys import case_dict_key_diagnostics
from .dict_keys_scanner import cached_scan, locate, reads_at
from .function_object_fields import function_object_field_diagnostics


def plan_diagnostics(
    case_root: Path,
    *,
    workflow_dag: dict[str, Any] | None,
    env: Mapping[str, str],
    scratch_root: Path | None,
    driver_context: Any,
) -> tuple[StrictDiagnostic, ...]:
    del workflow_dag
    mapping = driver_context.stack.call("get_profile").cxx_mapping
    source_root = mapping.source_root(env) if mapping is not None else None
    report = _report(driver_context, mapping, source_root, scratch_root)
    catalog = _catalog_diagnostics(driver_context, mapping, source_root, report)
    manifest = capability_manifest(driver_context)
    function_objects = function_object_field_diagnostics(
        case_root, samplable=manifest.get("samplable_fields", {}),
    )
    scanned = (
        _scanned_reader(driver_context, source_root, scratch_root)
        if source_root is not None and source_root.is_dir() else None
    )
    keys = case_dict_key_diagnostics(
        case_root,
        catalogued_paths=catalogued_paths(driver_context.stack.call("get_dict_entries")),
        dict_relpaths=_owned_dict_relpaths(case_root, driver_context),
        scanned=scanned,
        unread=[slot_key(item["driver_path"]) for item in (report or {}).get("unread", ())],
    )
    rules = tuple(
        item for item in driver_context.stack.call("validate_run_semantics", case_root)
        if item.level != "error"
    )
    return catalog + function_objects + keys + rules


def _scanned_reader(driver_context: Any, source_root: Path, scratch_root: Path | None):
    scan = cached_scan(source_root, cache_root=scratch_root)
    catalog = driver_context.stack.call("get_dictionary_catalog")
    placed_by_document: dict[str, Any] = {}

    def reads(relpath: str, trail: tuple[str, ...]) -> bool:
        name = relpath.rsplit("/", 1)[-1]
        if name not in placed_by_document:
            placed_by_document[name] = locate(scan, catalog.entries_for(name), document=name)
        return reads_at(scan, placed_by_document[name], trail)

    return reads


def _owned_dict_relpaths(case_root: Path, driver_context: Any) -> tuple[str, ...]:
    """The case dictionaries the catalogue addresses, the only ones checked for keys it lacks."""
    relpaths: list[str] = []
    documents = driver_context.stack.call("get_owned_documents")
    rules = driver_context.stack.call("get_profile").case_files
    for document in documents:
        for rule in rules:
            pattern = str(rule.path)
            if Path(pattern).is_absolute():
                continue
            basename = PurePosixPath(pattern).name
            if not (
                fnmatch.fnmatch(basename, str(document))
                or fnmatch.fnmatch(str(document), basename)
            ):
                continue
            candidates = (
                case_root.glob(pattern)
                if any(char in pattern for char in "*?[")
                else (case_root / pattern,)
            )
            for candidate_path in candidates:
                if candidate_path.is_file():
                    candidate = candidate_path.relative_to(case_root).as_posix()
                    if candidate not in relpaths:
                        relpaths.append(candidate)
    return tuple(relpaths)


def _describe_uncatalogued(item: dict) -> str:
    """One scanned read the catalogue lacks, as a sentence an agent can act on."""
    if item.get("kind") == "compared_value":
        return (
            f"the C++ compares {item['path']!r} against {item['value']!r} at {item['source']}, which the "
            "catalogue's menu lacks; the value is accepted"
        )
    if item.get("kind") != "key":
        return f"the C++ reads {json.dumps(item, sort_keys=True)}, which the catalogue lacks"
    how = "with no default, so it is required" if item["required"] else (
        f"with default {item['default']}" if item.get("default") is not None else "optionally"
    )
    return (
        f"the C++ reads {item['path']!r} as {item['method']}<{item['type'] or 'an unresolved type'}> {how}, at "
        f"{item['source']} ({item['function']}), and the catalogue lacks it; the scan fills "
        f"{json.dumps(item['entry'], sort_keys=True)}"
    )


def cxx_source_not_supplied(mapping: Any, *, source: str) -> StrictDiagnostic:
    """Supplied, never discovered: an unsupplied root is reported as info, not
    a warning, so an operation that needs no C++ scanning isn't flagged."""
    return diagnostic(
        "info",
        "plugin_cxx_source_not_supplied",
        f"C++ source not scanned: source root not supplied (set "
        f"{mapping.source_root_variable}; the source is "
        f"${mapping.source_root_variable}/{mapping.source_root_relative})",
        source=source,
    )


def _report(driver_context: Any, mapping: Any, source_root: Path | None, scratch_root: Path | None) -> dict | None:
    scanner = driver_context.stack.call("get_dict_key_scanner")
    if scanner is None or mapping is None or source_root is None or not source_root.is_dir():
        return None
    return scanner(
        source_root,
        allowlist_path=mapping.allowlist_path,
        catalogue=driver_context.stack.call("get_dictionary_catalog"),
        cache_root=scratch_root,
    ).to_json()


def _catalog_diagnostics(
    driver_context: Any, mapping: Any, source_root: Path | None, report: dict | None,
) -> tuple[StrictDiagnostic, ...]:
    """The catalogue compared with the C++, never failing the plan: warnings for disagreements, notes for unread and uncatalogued keys."""
    if mapping is None:
        return ()
    cxx_mapping_source = driver_context.identity.resolutions["get_profile"]
    if source_root is None:
        return (cxx_source_not_supplied(mapping, source=cxx_mapping_source),)
    if report is None:
        return (diagnostic(
            "error",
            "plugin_cxx_source_unavailable",
            f"{mapping.source_root_variable} is supplied, but its C++ source "
            f"{source_root} is not a directory",
            source=cxx_mapping_source,
        ),)
    source = f"{cxx_mapping_source}:{source_root}"
    disagreements = tuple(
        diagnostic("warning", "plugin_catalog_disagreement", item, source=source)
        for item in report.get("disagreements", ())
    )
    unread = tuple(
        diagnostic(
            "info", "plugin_catalog_unread",
            f"{item['driver_path']}: {item['note']}, so setting it has no effect "
            "(omnidriver catalog --unread lists every one)",
            source=source, field=item["driver_path"],
        )
        for item in report.get("unread", ())
    )
    notes = tuple(
        diagnostic(
            "info", "plugin_catalog_uncatalogued", _describe_uncatalogued(item) +
            " (omnidriver catalog --uncatalogued lists every one)",
            source=source, field=item.get("path", ""),
        )
        for item in report.get("uncatalogued", ())
    )
    return disagreements + unread + notes
