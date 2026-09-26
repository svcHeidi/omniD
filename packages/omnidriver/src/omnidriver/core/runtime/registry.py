from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from .models import TutorialSpec
from .generic_case import make_generic_case_spec
from omnidriver.core.plugin_profile import (
    is_replica_directory_name,
    replica_directory_globs,
    entrypoint_relpaths,
)

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext















SpecFactory = Callable[..., TutorialSpec]



ENTRY_KIND_VALUES = (
    "registered_tutorial",
    "case_folder",
    "tutorial_record",
)

_entrypoint_relpaths = entrypoint_relpaths


def _has_entrypoint(case_root: Path, driver_context: "DriverContext | None") -> bool:
    return any(
        (case_root / relpath).is_file()
        for relpath in _entrypoint_relpaths(driver_context)
    )


def _is_case_directory(
    path: Path,
    driver_context: "DriverContext",
) -> bool:
    if not path.is_dir() or path.name.startswith(".") or path.name == "__pycache__":
        return False
    from ..plugin_capabilities import CaseCompatibilityRequest

    # Was `has_case_marker(...) or _has_entrypoint(...)`, duplicating logic
    # `case_compatibility.is_case` now composes in one place (marker,
    # entrypoint, and a leftover generated-case marker). Task 10, 2026-09-22.
    return driver_context.capabilities.case_compatibility.is_case(
        CaseCompatibilityRequest(path),
    )


def _case_is_runnable(
    case_root: Path,
    *,
    driver_context: "DriverContext",
) -> bool:
    from ..plugin_capabilities import CaseCompatibilityRequest

    if _has_entrypoint(case_root, driver_context):
        return True
    return driver_context.capabilities.case_compatibility.is_runnable_without_workflow(
        CaseCompatibilityRequest(case_root),
    )


def _iter_case_directories_recursive(
    cases_root: Path,
    driver_context: "DriverContext | None" = None,
) -> list[Path]:
    if not cases_root.exists():
        return []

    discovered: list[Path] = []
    replica_globs = replica_directory_globs(driver_context)
    ignored_directory_names = (
        frozenset(
            driver_context.capabilities.case_runtime_conventions.conventions()
            .case_discovery_ignored_directory_names,
        )
        if driver_context is not None
        else frozenset()
    )
    for current_root, dirnames, _filenames in os.walk(cases_root):
        path = Path(current_root)
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if not dirname.startswith(".")
            and dirname != "__pycache__"
            and not is_replica_directory_name(dirname, replica_globs)
            and dirname not in ignored_directory_names
        ]
        if _is_case_directory(path, driver_context):
            discovered.append(path)
            dirnames[:] = []
    return discovered


def _registered_tutorial_entry(
    tutorial: str,
    cases_root: Path,
    driver_context: "DriverContext | None" = None,
) -> dict[str, object]:
    factory = _normalized_registry(driver_context)[tutorial.casefold()]
    try:
        spec = factory(cases_root=cases_root)
    except Exception:
        # Cataloging is best-effort: describe_entry() derives cases_root
        # from the *queried* entry's own case_root parent (see introspection.
        # describe_entry), which does not necessarily hold every other
        # registered tutorial's case directory -- e.g. singleCell nests one
        # level deeper than the manufactured-solution tutorials. A factory
        # that can't build its spec under this particular root (missing
        # case files, wrong nesting, ...) is simply not runnable from here;
        # that must not crash the listing for every other tutorial.
        return {
            "entry_name": tutorial,
            "entry_kind": "registered_tutorial",
            "entry_path": tutorial,
            "is_runnable": False,
            "source_type": "spec_factory",
            "workflow_family": None,
        }
    case_root = Path(spec.case_root)
    try:
        entry_path = str(case_root.relative_to(cases_root))
    except ValueError:
        entry_path = case_root.name
    return {
        "entry_name": tutorial,
        "entry_kind": "registered_tutorial",
        "entry_path": entry_path,
        "is_runnable": True,
        "source_type": "spec_factory",
        "workflow_family": None,
    }


def _classify_case_entry(
    case_root: Path,
    cases_root: Path,
    driver_context: "DriverContext | None" = None,
) -> dict[str, object]:
    relative_path = str(case_root.relative_to(cases_root))
    return {
        "entry_name": case_root.name,
        "entry_kind": "case_folder",
        "entry_path": relative_path,
        "is_runnable": _case_is_runnable(case_root, driver_context=driver_context),
        "source_type": "filesystem_case",
        "workflow_family": None,
    }


def _tutorial_record_entry(name: str, record: object) -> dict[str, object]:
    return {
        "entry_name": name,
        "entry_kind": "tutorial_record",
        "entry_path": record.native_case_relpath,
        "is_runnable": True,
        "source_type": "tutorial_record",
        "workflow_family": None,
    }


def _entry_catalog_for_root(
    cases_root: Path,
    driver_context: "DriverContext",
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = [
        _registered_tutorial_entry(tutorial, cases_root, driver_context)
        for tutorial in list_tutorials(driver_context)
    ]
    entries.extend(
        _tutorial_record_entry(name, record)
        for name, record in (driver_context.capabilities.tutorial_records.catalog() or {}).items()
    )
    known_registered = {tutorial.casefold() for tutorial in list_tutorials(driver_context)}
    for case_root in _iter_case_directories_recursive(cases_root, driver_context):
        classified = _classify_case_entry(case_root, cases_root, driver_context)
        entries.append(classified)

    return sorted(
        entries,
        key=lambda entry: (
            ENTRY_KIND_VALUES.index(str(entry["entry_kind"])),
            str(entry["entry_name"]).casefold(),
            str(entry["entry_path"]).casefold(),
        ),
    )





def list_case_directories(
    cases_root: Path | None = None,
    *,
    driver_context: "DriverContext | None" = None,
) -> list[str]:
    # No ambient default: core does not know where a caller keeps cases.
    resolved_root = Path.cwd() if cases_root is None else Path(cases_root)
    if not resolved_root.exists():
        return []
    return sorted(
        child.name
        for child in resolved_root.iterdir()
        if _is_case_directory(child, driver_context)
    )


def list_available_tutorials(
    cases_root: Path | None = None,
    *,
    driver_context: "DriverContext | None" = None,
) -> list[str]:
    available = list_tutorials(driver_context)
    known = {name.casefold() for name in available}
    for case_dir in list_case_directories(
        cases_root, driver_context=driver_context,
    ):
        if case_dir.casefold() in known:
            continue
        available.append(case_dir)
        known.add(case_dir.casefold())
    return available


def list_entries(
    cases_root: Path | None = None,
    *,
    driver_context: "DriverContext | None" = None,
) -> list[dict[str, object]]:
    # No ambient default: core does not know where a caller keeps cases.
    resolved_root = Path.cwd() if cases_root is None else Path(cases_root)
    return _entry_catalog_for_root(resolved_root, driver_context)







def load_tutorial_spec(
    name: str,
    overrides: dict | None = None,
    *,
    driver_context: "DriverContext | None" = None,
) -> TutorialSpec:
    resolution = resolve_tutorial(name, overrides=overrides, driver_context=driver_context)
    spec = _materialize_resolved_entry(
        resolution, driver_context=driver_context, consumer="load_tutorial_spec",
    )
    return _with_entry_metadata(spec, resolution, driver_context=driver_context)


def load_entry_spec(
    name: str,
    *,
    entry_kind: str | None = None,
    overrides: dict | None = None,
    driver_context: "DriverContext | None" = None,
) -> TutorialSpec:
    resolution = resolve_entry(
        name,
        entry_kind=entry_kind,
        overrides=overrides,
        driver_context=driver_context,
    )
    spec = _materialize_resolved_entry(
        resolution, driver_context=driver_context, consumer="load_entry_spec",
    )
    return _with_entry_metadata(spec, resolution, driver_context=driver_context)


def _materialize_resolved_entry(
    resolution: dict[str, object],
    *,
    driver_context: "DriverContext | None",
    consumer: str,
) -> TutorialSpec:
    """Build a resolved entry while preserving its environment declaration.

    Review finding B2: a ``tutorial_record`` resolution carries no
    ``factory``/``factory_overrides`` at all (it is inert data, not a
    factory -- design doc §3), so every consumer of a ``resolve_entry``
    result must check the resolution kind EXPLICITLY and refuse by name
    before reaching for either key. Wiring a record through ``describe``/
    sweep is the next step's job (docs/superpowers/specs/2026-09-24-
    tutorials-are-pointers-design.md); this only makes the refusal explicit,
    naming the caller, instead of an opaque ``KeyError('factory_overrides')``.
    """
    if resolution["resolution"] == "tutorial_record":
        from ..tutorial_records import TutorialRecordError

        raise TutorialRecordError(
            f"tutorial records are not yet runnable through {consumer}"
        )

    factory_overrides = dict(resolution["factory_overrides"])
    if resolution["entry_kind"] == "case_folder":
        # A generic case factory builds the execution DAG from the active
        # environment's entrypoint declaration. Passing the context here
        # keeps that operation declaration-led rather than inventing a
        # case-script default in Core.
        factory_overrides["driver_context"] = driver_context
    return resolution["factory"](**factory_overrides)


def _with_entry_metadata(
    spec: TutorialSpec,
    resolution: dict[str, object],
    *,
    driver_context: "DriverContext | None" = None,
) -> TutorialSpec:
    metadata = dict(spec.metadata)
    metadata.update(
        {
            "entry_name": resolution["entry_name"],
            "entry_kind": resolution["entry_kind"],
            "entry_path": resolution["entry_path"],
            "source_type": resolution["source_type"],
            "workflow_family": resolution["workflow_family"],
            "resolution": resolution["resolution"],
        }
    )
    # Plain case folders are owned by their on-disk entrypoint declared by the
    # active environment. If a discovered
    # folder has no entrypoint, do not preserve the generic-spec placeholder DAG.
    if (
        resolution["resolution"] == "case_folder"
        and not _has_entrypoint(Path(spec.case_root), driver_context)
    ):
        metadata["workflow_dag"] = None
    return replace(spec, metadata=metadata)


def _match_entry(
    name: str,
    entry_kind: str | None,
    cases_root: Path,
    driver_context: "DriverContext | None" = None,
) -> dict[str, object] | None:
    normalized_name = name.strip().casefold()
    matches = [
        entry
        for entry in list_entries(cases_root, driver_context=driver_context)
        if (
            # A tutorial-record entry is never a `_match_entry` candidate
            # (review finding B2): it carries no factory of its own, and
            # matching one here (e.g. by its `native_case_relpath`) used to
            # let `resolve_entry` build a "case_folder" resolution out of a
            # dict that also claimed `entry_kind: "tutorial_record"` --
            # neither a record (no `record` key) nor a clean case_folder. A
            # record dispatches ONLY through the explicit tutorial_records
            # catalog check above, never through here.
            str(entry["entry_kind"]) != "tutorial_record"
            and normalized_name in {
                str(entry["entry_name"]).casefold(),
                str(entry["entry_path"]).casefold(),
            }
            and (entry_kind is None or str(entry["entry_kind"]) == entry_kind)
        )
    ]

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    exact_path_matches = [
        entry
        for entry in matches
        if str(entry["entry_path"]).casefold() == normalized_name
    ]
    if len(exact_path_matches) == 1:
        return exact_path_matches[0]

    options = ", ".join(sorted(str(entry["entry_path"]) for entry in matches))
    raise KeyError(
        f"Entry '{name}' is ambiguous. Use a more specific entry path. Matches: {options}"
    )


@dataclass(frozen=True)
class EntryClassification:
    """Which resolution kind an entry name names, with every cross-kind
    ambiguity a tutorial record can have already refused (review findings
    B1/M6).

    ``resolve_entry`` and ``sweep_runner._sweep_record`` both call
    :func:`classify_entry` for this -- there used to be a second, duplicated
    copy of the record-vs-factory refusal living in ``_sweep_record`` alone,
    which caught neither the record-vs-cwd-case-path ambiguity nor the
    record-vs-case-folder-under-cases_root one at all (a sweep over a record
    name that was ALSO shadowed by a real directory silently ran the record,
    never refusing). Both callers now share one answer.

    Exactly one of ``case_path``/``record`` is set, matching ``kind`` when
    ``kind`` is ``"case_path"``/``"tutorial_record"``. ``kind ==
    "unresolved"`` means none of the kinds this function decides among
    matched -- the caller falls through to its own remaining resolution
    (``resolve_entry``'s registered-tutorial/case-folder/generic-alias/
    unknown-entry paths, which this classifier does not reproduce).
    """

    kind: str
    case_path: Path | None = None
    record: object | None = None


def classify_entry(
    name: str,
    *,
    entry_kind: str | None,
    cases_root: Path | None,
    driver_context: "DriverContext",
) -> EntryClassification:
    """Classify ``name`` among a literal case path (relative to cwd), a
    tutorial record, and a registered (factory) tutorial -- refusing, BY
    NAME, every ambiguity a tutorial record can have with each of the other
    two, plus a same-named case folder under ``cases_root`` (design: "a
    record must never be silently shadowed... one name must not name both").

    ``cases_root=None`` skips only the case-folder-under-cases_root check --
    there is no root to search yet (used when a sweep's ``base`` has not
    supplied one; that caller refuses the missing root separately, by name,
    before it can ever treat this as a real ``tutorial_record`` resolution).
    """
    key = name.strip()
    normalized_key = key.casefold()
    normalized_records = {
        record_name.casefold(): record
        for record_name, record in (
            driver_context.capabilities.tutorial_records.catalog() or {}
        ).items()
    }
    # Matches the original per-branch gating this replaces: an explicitly
    # requested entry_kind that is neither None nor "tutorial_record" means
    # the caller is not asking for a record at all, so a same-named record's
    # mere existence must not surface here -- neither as a resolution nor as
    # an ambiguity refusal (there is nothing for it to be ambiguous WITH from
    # this caller's point of view).
    record_applicable = entry_kind in {None, "tutorial_record"}
    is_record = record_applicable and normalized_key in normalized_records
    record = normalized_records.get(normalized_key) if is_record else None

    case_path: Path | None = None
    if entry_kind in {None, "case_folder"}:
        candidate = Path(key).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.is_dir() and _is_case_directory(candidate, driver_context):
            case_path = candidate

    if is_record and case_path is not None:
        raise KeyError(
            f"Entry '{key}' is ambiguous: it is registered as a "
            "tutorial record AND names an existing case path "
            f"({case_path}); one name must not name both"
        )

    normalized_registry = _normalized_registry(driver_context)
    is_factory = normalized_key in normalized_registry
    if is_record and is_factory:
        raise KeyError(
            f"Entry '{key}' is ambiguous: it is registered as both a "
            "tutorial record and a factory tutorial (spec_factories); "
            "one name must not name both"
        )

    if is_record and cases_root is not None:
        matched_case_folder = _match_entry(key, "case_folder", cases_root, driver_context)
        if matched_case_folder is not None:
            matched_path = (cases_root / str(matched_case_folder["entry_path"])).resolve()
            own_native_case = (cases_root / record.native_case_relpath).resolve()
            # A record's OWN native case is routinely ALSO independently
            # recognizable as a plain case_folder (a real adapter's
            # has_case_marker knows its own dictionary format, which the
            # native case obviously has) -- that is not a naming collision
            # with anything, it is the same directory discovered twice by
            # two different catalogs. Only a DIFFERENT directory that
            # happens to share this name is the real ambiguity design means
            # ("one name must not name both").
            if matched_path != own_native_case:
                raise KeyError(
                    f"Entry '{key}' is ambiguous: it is registered as a "
                    "tutorial record AND names an existing case folder "
                    f"under cases_root ({matched_path}); one name must not "
                    "name both"
                )

    if case_path is not None:
        return EntryClassification(kind="case_path", case_path=case_path)
    if is_record:
        return EntryClassification(kind="tutorial_record", record=record)
    return EntryClassification(kind="unresolved")


def resolve_entry(
    name: str,
    *,
    entry_kind: str | None = None,
    overrides: dict | None = None,
    driver_context: "DriverContext",
) -> dict[str, object]:
    from ..plugin_capabilities import CaseCompatibilityRequest

    key = name.strip()
    normalized_key = key.casefold()
    normalized_registry = _normalized_registry(driver_context)
    incoming_overrides = dict(overrides or {})

    if entry_kind is not None and entry_kind not in ENTRY_KIND_VALUES:
        valid = ", ".join(ENTRY_KIND_VALUES)
        raise KeyError(f"Unknown entry_kind '{entry_kind}'. Valid values: {valid}")

    cases_root = Path(incoming_overrides.get("cases_root", Path.cwd()))

    # B1/M6: one shared classifier decides the case-path/tutorial-record
    # ambiguity refusals (see `classify_entry`'s own docstring); everything
    # below it stays exactly as it was.
    classification = classify_entry(
        key, entry_kind=entry_kind, cases_root=cases_root, driver_context=driver_context,
    )

    # A case is identified by its path. _is_case_directory() already decides
    # this from the directory's own contents via the plugin's declared marker
    # or entrypoint contract, so a case anywhere on disk resolves -- no root
    # required. See docs/superpowers/specs/2026-09-04-a-case-is-a-path-design.md.
    if classification.kind == "case_path":
        candidate = classification.case_path
        # The path names the case, so a differing `case_dir_name` is a
        # contradiction. Refuse it rather than overwrite it below: that
        # overwrite silently dropped a `--config` value, and discarded a
        # case-path sweep entry's staged name so _materialize_entry_case
        # mutated the source case (2026-09-24). A value that restates the
        # path's own name is not a conflict.
        supplied_name = incoming_overrides.get("case_dir_name")
        if supplied_name is not None and str(supplied_name) != candidate.name:
            raise ValueError(
                f"Entry '{key}' is a case path, which already names its case "
                f"'{candidate.name}'; the supplied case_dir_name "
                f"'{supplied_name}' contradicts it. Remove case_dir_name, or "
                "pass the path of the case you mean as the entry."
            )
        case_overrides = dict(incoming_overrides)
        case_overrides["cases_root"] = str(candidate.parent)
        case_overrides["case_dir_name"] = candidate.name
        plugin_factory = _get_plugin_tutorials(driver_context).get(
            "make_generic_case_spec",
        )
        factory = (
            plugin_factory
            if plugin_factory is not None
            and driver_context.capabilities.case_compatibility.has_case_marker(
                CaseCompatibilityRequest(candidate),
            )
            else make_generic_case_spec
        )
        return {
            "resolution": "case_path",
            "requested_name": key,
            "requested_entry_kind": entry_kind,
            "resolved_name": candidate.name,
            "factory": factory,
            "factory_overrides": case_overrides,
            "entry_name": candidate.name,
            "entry_kind": "case_folder",
            "entry_path": str(candidate),
            "is_runnable": True,
            "source_type": "case_path",
            "workflow_family": None,
        }

    # Tutorial records (docs/superpowers/specs/2026-09-24-tutorials-are-
    # pointers-design.md §3) are dispatched EXPLICITLY, alongside the factory
    # registry and a bare case path -- never tried as one kind and silently
    # reinterpreted as another. A name registered as both a record and a
    # factory (or a case path, or a case folder) is refused outright rather
    # than picking one by search order -- `classify_entry` already checked
    # that above.
    if classification.kind == "tutorial_record":
        record = classification.record
        return {
            "resolution": "tutorial_record",
            "requested_name": key,
            "requested_entry_kind": entry_kind,
            "resolved_name": record.name,
            "record": record,
            "entry_name": record.name,
            "entry_kind": "tutorial_record",
            "entry_path": record.native_case_relpath,
            "is_runnable": True,
            "source_type": "tutorial_record",
            "workflow_family": None,
        }

    if entry_kind in {None, "registered_tutorial"} and normalized_key in normalized_registry:
        return {
            "resolution": "registered",
            "requested_name": key,
            "requested_entry_kind": entry_kind,
            "resolved_name": key,
            "factory": normalized_registry[normalized_key],
            "factory_overrides": incoming_overrides,
            "entry_name": key,
            "entry_kind": "registered_tutorial",
            "entry_path": _registered_tutorial_entry(key, cases_root, driver_context)["entry_path"],
            "is_runnable": True,
            "source_type": "spec_factory",
            "workflow_family": None,
        }

    matched_entry = _match_entry(key, entry_kind, cases_root, driver_context)
    if matched_entry is not None:
        generic_overrides = dict(incoming_overrides)
        generic_overrides.setdefault("case_dir_name", str(matched_entry["entry_path"]))
        matched_case_root = cases_root / str(matched_entry["entry_path"])
        # Let the selected adapter decide whether the folder has a domain
        # marker. Otherwise use Core's generic case-folder factory.
        generic_factory = (
            _get_plugin_tutorials(driver_context).get("make_generic_case_spec")
            if driver_context.capabilities.case_compatibility.has_case_marker(
                CaseCompatibilityRequest(matched_case_root),
            )
            else make_generic_case_spec
        )
        return {
            "resolution": "case_folder",
            "requested_name": key,
            "requested_entry_kind": entry_kind,
            "resolved_name": str(matched_entry["entry_name"]),
            "factory": generic_factory,
            "factory_overrides": generic_overrides,
            **matched_entry,
        }

    if entry_kind in {None, "case_folder"} and normalized_key in {"genericcase", "randomcase"}:
        if "case_dir_name" not in incoming_overrides:
            raise KeyError(
                f"Entry '{name}' requires a 'case_dir_name' override to select a case folder."
            )
        matched_case_dir = str(incoming_overrides["case_dir_name"])
        return {
            "resolution": "generic_alias",
            "requested_name": key,
            "requested_entry_kind": entry_kind,
            "resolved_name": matched_case_dir,
            "factory": make_generic_case_spec,
            "factory_overrides": incoming_overrides,
            "entry_name": Path(matched_case_dir).name,
            "entry_kind": "case_folder",
            "entry_path": matched_case_dir,
            "is_runnable": False,
            "source_type": "generic_alias",
            "workflow_family": None,
        }

    valid = ", ".join(list_tutorials(driver_context))
    raise KeyError(
        f"Unknown entry '{name}'. Valid registered tutorials: {valid}. "
        "You can also pass any existing tutorial case folder or workflow entry path."
    )


def resolve_tutorial(
    name: str,
    overrides: dict | None = None,
    *,
    driver_context: "DriverContext | None" = None,
) -> dict[str, object]:
    return resolve_entry(name, overrides=overrides, driver_context=driver_context)


def _get_plugin_tutorials(driver_context: "DriverContext"):
    return driver_context.capabilities.tutorials.catalog()

def _normalized_registry(driver_context: "DriverContext | None" = None) -> dict[str, object]:
    spec_factories = _get_plugin_tutorials(driver_context).get("spec_factories", {})
    return {name.casefold(): factory for name, factory in spec_factories.items()}

def list_tutorials(driver_context: "DriverContext | None" = None) -> list[str]:
    registered = _get_plugin_tutorials(driver_context).get("registered_tutorials", ())
    return list(registered)
