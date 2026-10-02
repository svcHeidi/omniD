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
from omnidriver.core.plugin_capabilities import RunSemanticValidationRequest
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
    mapping = driver_context.capabilities.cxx_mapping.profile().cxx_mapping
    source_root = mapping.source_root(env) if mapping is not None else None
    report = _report(driver_context, mapping, source_root, scratch_root)
    catalog = _catalog_diagnostics(driver_context, mapping, source_root, report)
    manifest = driver_context.capabilities.manifest.manifest()
    function_objects = function_object_field_diagnostics(
        case_root, samplable=manifest.get("samplable_fields", {}),
    )
    scanned = (
        _scanned_reader(driver_context, source_root, scratch_root)
        if source_root is not None and source_root.is_dir() else None
    )
    keys = case_dict_key_diagnostics(
        case_root,
        catalogued_paths=catalogued_paths(driver_context.capabilities.dictionaries.entries()),
        dict_relpaths=_owned_dict_relpaths(case_root, driver_context),
        scanned=scanned,
        unread=[slot_key(item["driver_path"]) for item in (report or {}).get("unread", ())],
    )
    rules = tuple(
        item for item in driver_context.capabilities.run_semantic_validator.validate(
            RunSemanticValidationRequest(case_root),
        ) if item.level != "error"
    )
    return catalog + function_objects + keys + rules


def _scanned_reader(driver_context: Any, source_root: Path, scratch_root: Path | None):
    scan = cached_scan(source_root, cache_root=scratch_root)
    catalog = driver_context.capabilities.dictionaries.catalog()
    placed_by_document: dict[str, Any] = {}

    def reads(relpath: str, trail: tuple[str, ...]) -> bool:
        name = relpath.rsplit("/", 1)[-1]
        if name not in placed_by_document:
            placed_by_document[name] = locate(scan, catalog.entries_for(name), document=name)
        return reads_at(scan, placed_by_document[name], trail)

    return reads


def _owned_dict_relpaths(case_root: Path, driver_context: Any) -> tuple[str, ...]:
    """The case dictionaries the catalogue addresses: only those may be
    checked for keys it lacks -- warning about keys in an uncatalogued file
    would be pure noise. Each document the plugin names is matched against
    the profile's declared case-file rules."""
    relpaths: list[str] = []
    documents = driver_context.capabilities.dictionaries.documents()
    rules = driver_context.capabilities.case_files.all_rules()
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


def _report(driver_context: Any, mapping: Any, source_root: Path | None, scratch_root: Path | None) -> dict | None:
    if mapping is None or source_root is None or not source_root.is_dir():
        return None
    return driver_context.capabilities.dict_key_scanner.scan(
        source_root,
        allowlist_path=mapping.allowlist_path,
        entries=driver_context.capabilities.dictionaries.entries(),
        cache_root=scratch_root,
    ).to_json()


def _catalog_diagnostics(
    driver_context: Any, mapping: Any, source_root: Path | None, report: dict | None,
) -> tuple[StrictDiagnostic, ...]:
    """The catalogue compared with the C++, never failing the plan: a warning
    per disagreement, a note per catalogued key the C++ no longer reads and a
    note per uncatalogued read."""
    if mapping is None:
        return ()
    # `source=` names whichever provider actually answered `cxx_mapping`, per
    # `resolutions()` -- `StackIdentity` has no singular id to fall back on.
    cxx_mapping_source = driver_context.identity.resolutions.get("cxx_mapping", "cxx_mapping")
    if source_root is None:
        # Supplied, never discovered: an unsupplied root is reported as info,
        # not a warning, so a plan that needs no C++ scanning isn't flagged.
        return (diagnostic(
            "info",
            "plugin_cxx_source_not_supplied",
            f"C++ source not scanned: source root not supplied (set "
            f"{mapping.source_root_variable}; the source is "
            f"${mapping.source_root_variable}/{mapping.source_root_relative})",
            source=cxx_mapping_source,
        ),)
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
            "info", "plugin_catalog_uncatalogued",
            f"the C++ reads {json.dumps(item, sort_keys=True)}, which the catalogue lacks "
            "(omnidriver catalog --uncatalogued lists every one)",
            source=source,
        )
        for item in report.get("uncatalogued", ())
    )
    return disagreements + unread + notes
