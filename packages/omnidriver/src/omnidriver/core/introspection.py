from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .plugin_interface import DriverContext

from .capability_manifest import capability_manifest
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


def _plugin_catalogs(driver_context: "DriverContext") -> dict[str, Any]:
    # The catalog names and their contents are plugin vocabulary (e.g. the
    # cardiac plugin's ionic_model_catalog/active_tension_catalog); core only
    # namespaces the whole mapping under this key and serializes it.
    return _serialize(
        dict(driver_context.stack.call("get_named_catalogs"))
    )


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
    arguments per workflow step.
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
        "plugin_catalogs": _plugin_catalogs(driver_context),
        "record_preview": preview,
        "record_surface": surface,
        "capability_manifest": _serialize({
            **capability_manifest(driver_context),
            "plugin_identity": driver_context.identity.to_json(),
        }),
    }
