from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .plugin_interface import DriverContext

from .capability_manifest import capability_manifest
from .plugin_discovery import discover_plugins
from .scripts import list_scripts
from .tutorial_records import TutorialRecord, TutorialRecordError, lookup_record


def _serialize(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        # frozenset is NOT a subclass of set; without it, DictEntry.phases fell
        # through to repr() and shipped "frozenset({'physics'})" as JSON.
        return sorted(_serialize(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _is_table_of_items(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(isinstance(item, dict) for item in value.values())


def _plugin_catalogs(driver_context: "DriverContext") -> dict[str, Any]:
    """The stack's named catalogs, each table of named items listed by name:
    ``omnidriver catalog --named <catalog> [--item <name>]`` gives the detail.

    The catalog names and their contents are plugin vocabulary (e.g. the
    cardiac plugin's ionic_model_catalog/active_tension_catalog); core only
    namespaces the whole mapping under this key and serializes it."""
    return {
        name: {
            section: sorted(content) if _is_table_of_items(content) else content
            for section, content in catalog.items()
        } if isinstance(catalog, dict) else catalog
        for name, catalog in _serialize(dict(driver_context.stack.call("get_named_catalogs"))).items()
    }


def named_catalog(driver_context: "DriverContext", name: str, item: str | None = None) -> dict[str, Any]:
    """One named catalog in full, or, with ``item``, the entry of that name in each of its tables."""
    catalogs = _serialize(dict(driver_context.stack.call("get_named_catalogs")))
    if name not in catalogs:
        raise TutorialRecordError(f"no named catalog {name!r}; the stack has {sorted(catalogs)}")
    catalog = catalogs[name]
    if item is None:
        return {"catalog": name, "content": catalog}
    found = {
        section: content[item] for section, content in catalog.items()
        if _is_table_of_items(content) and item in content
    } if isinstance(catalog, dict) else {}
    if not found:
        raise TutorialRecordError(f"named catalog {name!r} has no item {item!r}")
    return {"catalog": name, "item": item, "content": found}


def describe_stack(driver_context: "DriverContext") -> dict[str, Any]:
    """What the selected stack offers, for a caller that has not chosen a record:
    its records (with their axes, inputs and whether a run may be parallel), the
    repository's scripts, and the plugin ids installed here (what ``--plugin`` takes)."""
    records = driver_context.stack.call("get_tutorial_records")
    return {
        "plugin": [provider["id"] for provider in driver_context.identity.to_json()["providers"]],
        "records": [
            {
                "name": name,
                "native_case_relpath": record.native_case_relpath,
                "axes": sorted(record.axis_names()),
                "inputs": sorted(input_.name for input_ in record.inputs),
                "serial_only": record.serial_only,
            }
            for name, record in sorted(records.items())
        ],
        "scripts": list_scripts(driver_context),
        "installed_plugins": sorted(discover_plugins()),
    }


def describe_entry(
    entry: "str | TutorialRecord",
    *,
    overrides: dict[str, Any] | None = None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Preview one tutorial record without committing anything.

    ``overrides`` supplies ``cases_root`` (where the record's native case
    lives; no ambient default) and the study values to preview. ``cli_study``
    (``--parallel``) and ``inputs`` (``--input NAME=PATH``) are previewed as
    ``strict_plan`` would plan them.

    ``record_surface`` is what an agent may address and should read first, in
    one shape for every solver: the record's axes with their value kinds, the
    stack's key catalogue for the native case, the stack's agent guidance, and
    the case's own ``case.documentation`` files. ``record_preview`` is each
    patch's document, key, value, status and validated flag, plus the command
    arguments per workflow step. ``scripts`` lists the helper scripts of the
    stack's repository (``DriverContext.repository``) with their usage lines,
    beside ``records``: a record step may run one, and an agent may run one
    by hand.
    """
    from .runtime.record_execution import preview_record_case
    from .runtime.record_surface import record_surface

    record = lookup_record(entry, driver_context=driver_context)
    incoming_overrides = dict(overrides or {})
    cases_root_value = incoming_overrides.pop("cases_root", None)
    if cases_root_value is None:
        # A case root has no ambient truth (CLAUDE.md, "supplied versus
        # discovered"): falling back to the working directory would preview a
        # record against wherever the caller happened to stand.
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot be previewed: 'overrides' "
            "must supply 'cases_root' naming where its native case lives "
            "(there is no ambient cases root to discover)"
        )
    cases_root = Path(cases_root_value)
    preview = preview_record_case(
        record,
        cases_root=cases_root,
        study_by_source={"base": incoming_overrides, "cli": dict(cli_study or {})},
        driver_context=driver_context,
        inputs=inputs,
    )
    surface = record_surface(
        record, native_case_root=cases_root / record.native_case_relpath, driver_context=driver_context,
        supplied=inputs,
    )
    return {
        "entry": {"entry_name": record.name, "entry_path": record.native_case_relpath},
        "records": sorted(driver_context.stack.call("get_tutorial_records")),
        "scripts": list_scripts(driver_context),
        "plugin_catalogs": _plugin_catalogs(driver_context),
        "record_preview": preview,
        "record_surface": surface,
        "capability_manifest": _serialize({
            **capability_manifest(driver_context),
            "plugin_identity": driver_context.identity.to_json(),
        }),
    }
