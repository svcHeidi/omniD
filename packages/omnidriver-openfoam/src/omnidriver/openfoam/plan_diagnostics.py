"""What an OpenFOAM-based stack adds to a strict plan: the catalogue compared
with the solver's own C++, the sampled fields a function object names, the
case keys nothing catalogues, and the notes the rules have for the case."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from omnidriver.core.contracts.catalogue_paths import catalogued_paths, slot_key
from omnidriver.core.capability_manifest import capability_manifest
from omnidriver.core.planning_types import StrictDiagnostic, diagnostic

from .case_dict_keys import case_dict_key_diagnostics
from .dict_keys_scanner import cached_scan, locate, reads_at
from .function_object_fields import function_object_field_diagnostics
from .fv_schemes import fv_schemes_diagnostics
from .scheme_tables import snapshot_diagnostics


def plan_diagnostics(
    case_root: Path,
    *,
    workflow_dag: dict[str, Any] | None,
    env: Mapping[str, str],
    scratch_root: Path | None,
    driver_context: Any,
) -> tuple[StrictDiagnostic, ...]:
    mapping = driver_context.stack.call("get_profile").cxx_mapping
    source_root = mapping.source_root(env) if mapping is not None else None
    report = _report(driver_context, mapping, source_root, scratch_root)
    held = _owned_dict_relpaths(case_root, driver_context)
    catalog = _catalog_diagnostics(
        driver_context, mapping, source_root, report, held={relpath.rsplit("/", 1)[-1] for relpath in held},
    )
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
        dict_relpaths=held,
        scanned=scanned,
        unread=[(item["document"], slot_key(item["driver_path"])) for item in (report or {}).get("unread", ())],
    )
    rules = tuple(
        item for item in driver_context.stack.call("validate_run_semantics", case_root, driver_context=driver_context)
        if item.level != "error"
    )
    schemes = fv_schemes_diagnostics(
        case_root, env=env, scratch_root=scratch_root,
        solver_schemes=(
            cached_scan(source_root, cache_root=scratch_root).schemes
            if source_root is not None and source_root.is_dir() else None
        ),
        solver_root=source_root,
    )
    utilities = _utility_manifest_diagnostics(driver_context, workflow_dag)
    return catalog + function_objects + keys + schemes + snapshot_diagnostics(env) + rules + utilities


def _step_programs(workflow_dag: dict[str, Any] | None) -> set[str]:
    programs: set[str] = set()
    for step in (workflow_dag or {}).get("steps", ()):
        command = step.get("command")
        words = command.split() if isinstance(command, str) else list(command or ())
        if words:
            programs.add(PurePosixPath(str(words[0])).name)
    return programs


def _utility_manifest_diagnostics(driver_context: Any, workflow_dag: dict[str, Any] | None) -> tuple[StrictDiagnostic, ...]:
    """Each manifest of a utility the plan runs compared with the C++ its supplied repository builds it from."""
    from .utility_scanner import utility_manifest_report

    repository = getattr(driver_context, "repository", None)
    manifests = driver_context.stack.call("get_utility_manifests")
    run = _step_programs(workflow_dag) & set(manifests)
    if repository is None or not run:
        return ()
    levels = {"disagreement": "warning", "uncatalogued": "info", "unread": "info"}
    return tuple(
        diagnostic(
            levels[item["kind"]], f"utility_manifest_{item['kind']}",
            f"{item['utility']} {item['flag'] or ''}: "
            + (item.get("note") or f"the C++ declares it ({item['source']}), and the manifest lacks it"),
            source=item.get("source") or str(manifests[item["utility"]].source_path), field=item["flag"] or "",
            detail=item,
        )
        for item in utility_manifest_report(repository.root, manifests, utilities=run)["findings"]
    )


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
    repository = getattr(driver_context, "repository", None)
    placed = repository is not None and Path(repository.source).resolve() == Path(source_root).resolve()
    prefix = {"source_prefix": PurePosixPath(Path(repository.source).relative_to(repository.root).as_posix())} if placed else {}
    return scanner(
        source_root,
        allowlist_path=mapping.allowlist_path,
        catalogue=driver_context.stack.call("get_dictionary_catalog"),
        cache_root=scratch_root,
        **prefix,
    ).to_json()


def _catalog_diagnostics(
    driver_context: Any, mapping: Any, source_root: Path | None, report: dict | None, *, held: set[str],
) -> tuple[StrictDiagnostic, ...]:
    """The catalogue compared with the C++, never failing the plan: warnings for disagreements, notes for unread and
    uncatalogued keys. A note about a dictionary the case does not hold (``held``, by file name), or about a read
    the scan cannot place in one, is left to ``omnidriver catalog``."""
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
        for item in report.get("unread", ()) if item["document"] in held
    )
    notes = tuple(
        diagnostic(
            "info", "plugin_catalog_uncatalogued",
            f"the C++ {'compares' if item.get('kind') == 'compared_value' else 'reads'} {item.get('path')!r}, which the "
            "catalogue lacks (detail: what the scan found; omnidriver catalog --uncatalogued lists every one)",
            source=source, field=item.get("path", ""), detail=item,
        )
        for item in report.get("uncatalogued", ())
        if held.intersection(item.get("documents", ()))
    )
    return disagreements + unread + notes
