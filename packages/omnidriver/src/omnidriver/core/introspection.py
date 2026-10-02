from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


from .runtime.models import TutorialSpec
from .runtime.registry import (
    list_entries,
    list_case_directories,
    resolve_entry,
)
from .runtime.execution_context import resolve_execution_context
from .plugin_profile import is_environment_role
from omnidriver.core.strict_planning import _run_launch_description

COMMON_OVERRIDE_KEYS = (
    "case_dir_name",
    "setup_dir_name",
    "output_dir_name",
    "run_script_relpath",
    "dict_file_relpaths",
    "dict_file_overrides",
    "postprocess_strict_artifacts",
)


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


def _annotation_to_string(annotation: Any) -> str | None:
    if annotation is inspect.Signature.empty:
        return None
    if isinstance(annotation, str):
        return annotation
    return repr(annotation).replace("typing.", "")


def _describe_parameter(parameter: inspect.Parameter) -> dict[str, Any]:
    payload = {
        "kind": parameter.kind.name.lower(),
        "required": parameter.default is inspect.Signature.empty,
    }
    annotation = _annotation_to_string(parameter.annotation)
    if annotation is not None:
        payload["annotation"] = annotation
    if parameter.default is not inspect.Signature.empty:
        payload["default"] = _serialize(parameter.default)
    return payload


def _describe_factory(factory: object) -> dict[str, Any]:
    if not callable(factory):
        raise TypeError(f"Factory is not callable: {factory!r}")
    signature = inspect.signature(factory)
    return {
        "callable": f"{factory.__module__}.{factory.__name__}",
        "parameters": {
            name: _describe_parameter(parameter)
            for name, parameter in signature.parameters.items()
        },
    }


def _describe_spec(spec: TutorialSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "case_root": str(spec.case_root),
        "setup_root": str(spec.metadata.get("setup_root", spec.case_root)),
        "output_dir": str(spec.metadata.get("output_dir", spec.case_root)),
        "metadata": _serialize(spec.metadata),
    }


def _existing_relpaths(case_root: Path, candidates: tuple[str, ...]) -> list[str]:
    return [relpath for relpath in candidates if (case_root / relpath).exists()]


def _declared_case_files(
    spec: TutorialSpec, *, driver_context: "DriverContext",
) -> dict[str, Any]:
    """Which of the profile's declared case files this case actually has,
    split core's own (``plugin``/``case`` namespaces) from the active
    environment's (every other namespace).

    Split on the profile's own ``role``, not on a path prefix: a prefix would
    make core re-derive plugin semantics from a string, and would misfile a
    plugin-owned dictionary that happens to live under system/ (or a required
    initial-condition file that does not). ``is_environment_role`` rather
    than a literal ``openfoam.`` prefix admits other environments too -- a
    FEniCS plugin's ``x-fenics.mesh_file`` is environment-owned in exactly
    the sense this split means.
    """
    case_root = spec.case_root
    required_rules = driver_context.capabilities.case_files.required_rules()
    core_required_files = tuple(
        rule.path for rule in required_rules if not is_environment_role(rule.role)
    )
    solver_required_files = tuple(
        rule.path for rule in required_rules if is_environment_role(rule.role)
    )
    conditional_files = tuple(driver_context.capabilities.case_files.conditional_files())
    declared_files = tuple(
        rule.path for rule in driver_context.capabilities.case_files.all_rules()
    )
    return {
        "core_required_files": _existing_relpaths(case_root, core_required_files),
        "solver_required_files": _existing_relpaths(case_root, solver_required_files),
        "conditional_files": _existing_relpaths(case_root, conditional_files),
        "declared_files": _existing_relpaths(case_root, declared_files),
    }


def _consumed_paths(spec: TutorialSpec) -> tuple[str, ...]:
    """Read dependencies a spec's own declared workflow already names.

    Reuses each step's `consumes` list from `metadata["workflow_dag"]` --
    the same structure `run_workflow`/`validate_workflow_commands` read --
    rather than maintaining a second description of the same facts.
    """
    steps = spec.metadata.get("workflow_dag", {}).get("steps", [])
    if not isinstance(steps, list):
        return ()
    consumed: set[str] = set()
    for step in steps:
        if isinstance(step, dict):
            consumed.update(str(path) for path in step.get("consumes", ()))
    return tuple(sorted(consumed))


def _mutable_entries(
    catalog_entries: tuple[Any, ...], overrides: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """One item per entry `dictionary_catalog.entries()` declares -- the same
    flat, adapter-agnostic `DictEntry` tuple `validate_value_shape` checks
    against elsewhere. Not `dictionaries.documents()`, whose
    shape is adapter-declared and nested differently per adapter, so core
    cannot walk it generically to recover qualified ids.

    `source` is one of `VALUE_SOURCES` (`core.case_write`): `"case"` when
    `overrides` supplies a value for this entry, `"template"` when the entry
    declares a non-empty `typical_value` and no override does, otherwise
    `"call_site_default"`. Never `"effective"` or `"recommendation"`: those
    describe a resolved run's actual value or a solver's own advice, neither
    of which a static catalog entry carries.
    """
    supplied = dict(overrides or {})
    items = []
    for entry in catalog_entries:
        driver_path = getattr(entry, "driver_path", None)
        if driver_path is None:
            continue
        if driver_path in supplied:
            source = "case"
        elif getattr(entry, "typical_value", ""):
            source = "template"
        else:
            source = "call_site_default"
        items.append({
            "qualified_id": driver_path,
            "value_kind": getattr(entry, "value_kind", ""),
            "unit": getattr(entry, "unit", ""),
            "source": source,
        })
    return items


def _resolve_proposed_changes(
    *,
    driver_context: "DriverContext",
    spec: TutorialSpec,
) -> tuple[list[dict[str, Any]] | None, tuple[str, ...], str]:
    """Preview what a spec's `case_mutation` would write, without writing it.

    A naive key match against `dictionary_catalog.entries()`
    (`_mutable_entries`) only ever sees a caller sophisticated enough to
    pass flat, catalog-shaped qualified ids -- but callers actually hand
    `_write_surface` raw factory kwargs (`ionic_model`,
    `electro_property_overrides`), in a cardiac vocabulary core may not
    hardcode a mapping for. `spec.case_mutation` is already the tutorial's
    own bound resolution closure over those same kwargs
    (`CaseMutationFn`, one argument, one case), so calling it needs no
    second, hand-maintained mapping.

    `case_mutation` is not pure -- it commits through `commit_case_write`
    (journal, atomic replace) -- so it is never called against the real
    `spec.case_root`. Instead this stages a disposable clone in a fresh
    temporary directory (reusing `sweep_runner._stage_entry_case`, the same
    mechanism a real sweep run uses to isolate a case before mutating it)
    and calls `case_mutation` against the clone; the real `case_root` is
    only ever read, never written.

    Returns ``(proposed_changes, expected_effects, reason)``:

    - ``proposed_changes`` is ``None`` when this could not be computed --
      ``reason`` names why (no `case_mutation`, or the staged preview
      raising). An empty list is the different, legitimate answer "resolved
      cleanly, and there is nothing to write" (`case_mutation` returning
      `None`, the same no-op contract `commit_case_overrides` documents).
    - ``expected_effects`` is `ResolvedMutation.expected_effects` copied onto
      the committed `CaseWriteRecord`, covering targets with no single
      qualified id at all (a whole-block removal, a hex-line rewrite) that
      `proposed_changes` itself cannot address.
    """
    if spec.case_mutation is None:
        return (
            None, (),
            "this spec has no case_mutation; there is nothing to preview",
        )

    import tempfile

    with tempfile.TemporaryDirectory(prefix="omnidriver-describe-preview-") as scratch:
        staged_case_root = Path(scratch) / "case"
        try:
            if Path(spec.case_root).exists():
                from .runtime.sweep_runner import _stage_entry_case

                _stage_entry_case(
                    Path(spec.case_root), staged_case_root, driver_context=driver_context,
                )
            else:
                staged_case_root.mkdir(parents=True, exist_ok=True)
            record = spec.case_mutation(staged_case_root)
        except Exception as exc:  # noqa: BLE001 -- reported as a reason, not raised
            return None, (), f"the staged case_mutation preview raised: {exc}"

    if record is None:
        # A genuine, legitimate no-op (`commit_case_overrides`'s own
        # contract) -- there is nothing this mutation writes, not a failure
        # to determine what it writes.
        return [], (), ""

    # Read the record's JSON form, not `record.parameters`: the record
    # deep-freezes `parameters` (`case_write._freeze`), so a nested value --
    # a dimensioned tensor's `{"dimensions": ..., "value": ...}` -- is a
    # `MappingProxyType` of tuples there, which `json.dumps` refuses.
    # `CaseWriteRecord.to_json` is the record's own unfreeze.
    proposed_changes = [
        {
            "qualified_id": item["qualified_id"],
            "document": item["document"],
            "value": item.get("value"),
            "source": item["source"],
            "operation": item.get("operation", "set"),
        }
        for item in record.to_json()["parameters"]
    ]
    return proposed_changes, record.expected_effects, ""


def _write_surface(
    *,
    driver_context: "DriverContext",
    spec: TutorialSpec,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    """The write channel's complete proposed surface for this entry.

    Generated from the same contracts validation uses, not a second
    hand-maintained description: `mutable` comes from
    `dictionary_catalog.entries()` (see `_mutable_entries`); `consumed` comes
    from the spec's own declared `workflow_dag` (see `_consumed_paths`);
    `modes` comes from `case_writer.supported_modes()`.

    `proposed_changes` prefers `_resolve_proposed_changes`'s staged
    `case_mutation` preview when a resolver exists: it is strictly more
    complete than a naive key match, carrying the actual value and every
    `operation` (`set`/`ensure`/`remove`), not only a `set` a caller happened
    to name with a catalog-shaped key. The naive match survives as a
    fallback only when there is no resolver at all (`proposed_changes_source
    = "supplied_qualified_ids_only"`).

    A resolver that exists but could not run yields `None` (JSON `null`),
    never an empty list: the staged preview raising (commonly because no
    case is materialized yet) is a genuine failure to determine what would
    change, not "nothing would change" -- and the naive match's own
    condition is essentially never true for raw factory kwargs, so falling
    back to it here would misreport a real failure as a no-op
    (`proposed_changes_source = "unknown"`). `describe` still exits 0 in
    that case: it stays a best-effort introspection command whose other
    fields remain valid when a case does not exist yet.

    `proposed_changes_reason` states which path produced the result and why,
    in all three cases, rather than leaving a reader to guess.
    """
    from .case_write import MUTATION_MODES

    catalog_entries = tuple(driver_context.capabilities.dictionaries.entries())
    mutable = _mutable_entries(catalog_entries, overrides)
    mutable_ids = {item["qualified_id"] for item in mutable}

    try:
        supported = driver_context.capabilities.case_writer.supported_modes()
        modes_error: str | None = None
    except Exception as exc:  # noqa: BLE001 -- reported as a reason, not raised
        supported = frozenset()
        modes_error = str(exc)

    modes: dict[str, Any] = {}
    for mode in sorted(MUTATION_MODES):
        is_supported = mode in supported
        if is_supported:
            reason = ""
        elif modes_error is not None:
            reason = (
                f"case_writer.supported_modes() could not be read: {modes_error}"
            )
        else:
            reason = (
                f"{mode!r} is not reported by this stack's "
                f"CaseWriterCapability.supported_modes() "
                f"({sorted(supported)!r}); no resolver for it is composed "
                f"into this stack"
            )
        modes[mode] = {"supported": is_supported, "reason": reason}

    supplied = dict(overrides or {})
    resolved_changes, expected_effects, reason = _resolve_proposed_changes(
        driver_context=driver_context, spec=spec,
    )
    if resolved_changes is not None:
        proposed_changes = resolved_changes
        proposed_changes_source = "case_mutation_preview"
    elif spec.case_mutation is None:
        # No resolver exists for this spec at all, so fall back to the naive
        # key match -- a real, if incomplete, answer, not a failure.
        proposed_changes = [
            {**item, "operation": "set"}
            for item in mutable
            if item["qualified_id"] in supplied and item["qualified_id"] in mutable_ids
        ]
        proposed_changes_source = "supplied_qualified_ids_only"
    else:
        # A resolver exists, but the staged preview itself raised. `None`
        # here is an explicit third answer, distinct from an empty list of
        # changes: falling back to the naive match would misreport "could
        # not be determined" as "nothing will change".
        proposed_changes = None
        proposed_changes_source = "unknown"

    return {
        "mutable": mutable,
        "consumed": list(_consumed_paths(spec)),
        "modes": modes,
        "proposed_changes": proposed_changes,
        "proposed_changes_source": proposed_changes_source,
        "proposed_changes_reason": reason,
        "expected_effects": list(expected_effects),
    }


def _dict_entry_catalog(driver_context: "DriverContext") -> dict[str, Any]:
    # The document names and their shape are plugin vocabulary; core only
    # serializes whatever structure the plugin declares.
    return _serialize(
        driver_context.capabilities.dictionaries.documents()
    )


def _plugin_catalogs(driver_context: "DriverContext") -> dict[str, Any]:
    # The catalog names and their contents are plugin vocabulary (e.g. the
    # cardiac plugin's ionic_model_catalog/active_tension_catalog); core only
    # namespaces the whole mapping under this key and serializes it.
    return _serialize(
        dict(driver_context.capabilities.named_catalogs.catalogs())
    )


def _run_state_schema() -> dict[str, Any]:
    """Static schema description for workflow_state.json."""
    return {
        "description": (
            "workflow_state.json is the run-state source of truth. It is "
            "written to output_dir/workflow_state.json by the strict workflow "
            "orchestrator and updated after every workflow step. Poll this "
            "file to track run progress."
        ),
        "schema_version": "3.0",
        "file_location": (
            "output_dir/workflow_state.json  (see launch.<action>.workflowStatePath)"
        ),
        "polling_guidance": (
            "Poll every 15-30 seconds. Read status and current_step_id; each "
            "step carries its own status, attempts, exit code, and log path. "
            "Stop when status is a terminal state."
        ),
    }


def _workflow_catalog(
    cases_root: Path,
    entry_catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for entry in entry_catalog:
        workflow_family = entry.get("workflow_family")
        if not workflow_family:
            continue
        family_name = str(workflow_family)
        families.setdefault(
            family_name,
            {
                "workflow_family": family_name,
                "template_entry": None,
                "reference_cases": [],
                "workflow_templates": [],
            },
        )

    return sorted(families.values(), key=lambda item: item["workflow_family"].casefold())


def _matching_workflow(
    workflow_catalog: list[dict[str, Any]],
    workflow_family: str | None,
) -> dict[str, Any] | None:
    if not workflow_family:
        return None
    for family in workflow_catalog:
        if family["workflow_family"] == workflow_family:
            return family
    return None


def _describe_tutorial_record(
    entry: str,
    resolution: dict[str, Any],
    *,
    overrides: dict[str, Any] | None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """describe's own preview of a tutorial_record entry, without committing.

    Every other resolution kind (``load_tutorial_spec``, ``load_entry_spec``,
    and therefore ``strict_plan``/``step``/``run`` through ``--entry``)
    still refuses a tutorial_record by name -- there is no ``TutorialSpec``
    to build one from, only the record's own preview, which is what this
    function returns.

    A record has no ``spec``, so most of ``describe_entry``'s spec-derived
    sections (``spec``, ``tutorial_contract``, ``strict_launch``,
    ``write_surface``) do not apply and are simply
    absent, never a fabricated empty answer. ``record_preview`` -- each
    patch's document/key/value/status/validated flag, plus the command
    arguments per workflow step -- sits beside where ``write_surface`` would
    be for a factory tutorial.

    ``record_surface`` is what an agent may address and should read first,
    in one shape for every solver: the record's axes with their value kinds,
    the stack's key catalogue for the native case, the stack's agent
    guidance, and the case's own ``case.documentation`` files
    (``runtime.record_surface.record_surface``).

    A record's keys live in ``record_surface.keys`` only -- not duplicated
    into a whole-catalogue ``dict_entries`` beside it, which would be a
    second, differently shaped answer to "which keys may I name". A
    case-folder entry keeps ``dict_entries``, the only other entry kind.
    """
    from .runtime.record_execution import preview_record_case
    from .runtime.record_surface import record_surface
    from .tutorial_records import TutorialRecordError

    record = resolution["record"]
    incoming_overrides = dict(overrides or {})
    cases_root_value = incoming_overrides.pop("cases_root", None)
    if cases_root_value is None:
        # No ambient default (CLAUDE.md's "supplied versus discovered" -- a
        # case root has no ambient truth): silently falling back to
        # `Path.cwd()` would preview a record against whatever directory the
        # caller happened to be standing in.
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be previewed: 'overrides' "
            "must supply 'cases_root' naming where its native case lives "
            "(there is no ambient cases root to discover)"
        )
    cases_root = Path(cases_root_value)
    entry_catalog = list_entries(cases_root, driver_context=driver_context)
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
        "requested_entry": entry,
        "resolution": resolution["resolution"],
        "resolved_name": resolution["resolved_name"],
        "entry": {
            "entry_name": resolution["entry_name"],
            "entry_kind": resolution["entry_kind"],
            "entry_path": resolution["entry_path"],
            "is_runnable": resolution["is_runnable"],
            "source_type": resolution["source_type"],
            "workflow_family": resolution["workflow_family"],
        },
        "entry_kind": resolution["entry_kind"],
        "entry_catalog": _serialize(entry_catalog),
        "is_runnable": resolution["is_runnable"],
        "case_directories": list_case_directories(
            cases_root, driver_context=driver_context,
        ),
        "common_override_keys": list(COMMON_OVERRIDE_KEYS),
        "plugin_catalogs": _plugin_catalogs(driver_context),
        "record_preview": preview,
        "record_surface": surface,
        "capability_manifest": _serialize({
            **dict(driver_context.capabilities.manifest.manifest()),
            "plugin_identity": driver_context.identity.to_json(),
        }),
    }


def describe_entry(
    entry: str,
    *,
    entry_kind: str | None = None,
    overrides: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """``cli_study``: the CLI's own study values (``--parallel``), previewed
    as a record study's ``"cli"`` source, as ``strict_plan`` plans them;
    refused by name for an entry that is not a record. ``inputs``
    (``--input NAME=PATH``): the same refusal, for the same reason."""
    resolution = resolve_entry(
        entry,
        entry_kind=entry_kind,
        overrides=overrides,
        driver_context=driver_context,
    )
    if resolution["resolution"] == "tutorial_record":
        return _describe_tutorial_record(
            entry, resolution, overrides=overrides, cli_study=cli_study,
            inputs=inputs, driver_context=driver_context,
        )
    from .strict_planning import refuse_cli_study_for_non_record
    from .tutorial_records import TutorialRecordError

    refuse_cli_study_for_non_record(entry, cli_study)
    if inputs:
        raise TutorialRecordError(
            f"--input applies only to a tutorial record's run, and {entry!r} is not a "
            "tutorial record"
        )
    from .runtime.registry import _materialize_resolved_entry

    spec = _materialize_resolved_entry(
        resolution, driver_context=driver_context, consumer="describe_entry",
    )
    cases_root = Path(
        resolution["factory_overrides"].get("cases_root", spec.case_root.parent)
    )
    entry_catalog = list_entries(cases_root, driver_context=driver_context)
    workflow_catalog = _workflow_catalog(cases_root, entry_catalog)

    make_spec_info = _describe_factory(resolution["factory"])
    return {
        "requested_entry": entry,
        "resolution": resolution["resolution"],
        "resolved_name": resolution["resolved_name"],
        "entry": {
            "entry_name": resolution["entry_name"],
            "entry_kind": resolution["entry_kind"],
            "entry_path": resolution["entry_path"],
            "is_runnable": resolution["is_runnable"],
            "source_type": resolution["source_type"],
            "workflow_family": resolution["workflow_family"],
        },
        "entry_kind": resolution["entry_kind"],
        "entry_catalog": _serialize(entry_catalog),
        "workflow": _serialize(
            _matching_workflow(workflow_catalog, resolution["workflow_family"])
        ),
        "workflow_catalog": _serialize(workflow_catalog),
        "is_runnable": resolution["is_runnable"],
        "case_directories": list_case_directories(
            cases_root, driver_context=driver_context,
        ),
        "common_override_keys": list(COMMON_OVERRIDE_KEYS),
        "make_spec": make_spec_info,
        "factory_overrides": _serialize(resolution["factory_overrides"]),
        "spec": _describe_spec(spec),
        "tutorial_contract": _declared_case_files(spec, driver_context=driver_context),
        "dict_entries": _dict_entry_catalog(driver_context),
        "plugin_catalogs": _plugin_catalogs(driver_context),
        "write_surface": _write_surface(
            driver_context=driver_context, spec=spec, overrides=overrides,
        ),
        "strict_launch": _run_launch_description(
            resolution["resolved_name"],
            resolve_execution_context(spec),
            driver_context=driver_context,
            entry_kind=resolution["entry_kind"],
            config_path=config_path,
        ),
        "run_state_schema": _run_state_schema(),
        "capability_manifest": _serialize({
            **dict(driver_context.capabilities.manifest.manifest()),
            "plugin_identity": driver_context.identity.to_json(),
        }),
    }


def describe_tutorial(
    tutorial: str,
    *,
    overrides: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    driver_context: "DriverContext | None" = None,
) -> dict[str, Any]:
    return describe_entry(
        tutorial,
        overrides=overrides,
        config_path=config_path,
        driver_context=driver_context,
    )
