from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .plugin_interface import DriverContext


from .runtime.models import CaseConfig, TutorialSpec, invoke_case_mutation
from .runtime.registry import (
    list_entries,
    list_available_tutorials,
    list_case_directories,
    list_tutorials,
    resolve_entry,
)
from .runtime.execution_context import resolve_execution_context
from omnidriver.core.strict_planning import _run_launch_description
from omnidriver.core.tutorial_contracts import describe_tutorial_contract

COMMON_OVERRIDE_KEYS = (
    "case_dir_name",
    "setup_dir_name",
    "output_dir_name",
    "run_script_relpath",
    "dict_file_relpaths",
    "dict_file_overrides",
    "postprocess_strict_artifacts",
)

SPECIAL_TUTORIAL_ALIASES = ("genericCase", "randomCase")


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


def _describe_cases(cases: list[CaseConfig]) -> dict[str, Any]:
    return {
        "count": len(cases),
        "items": [
            {
                "case_id": case.case_id,
                "params": _serialize(case.params),
            }
            for case in cases
        ],
    }


def _describe_spec(spec: TutorialSpec) -> dict[str, Any]:
    cases = spec.build_cases()
    return {
        "name": spec.name,
        "case_root": str(spec.case_root),
        "setup_root": str(spec.setup_root),
        "output_dir": str(spec.output_dir),
        "metadata": _serialize(spec.metadata),
        "cases": _describe_cases(cases),
    }


def _consumed_paths(spec: TutorialSpec) -> tuple[str, ...]:
    """Read dependencies a spec's own declared workflow already names.

    Not a new concept: every `TutorialSpec` with a `workflow_dag` in its
    `metadata` already declares each step's `consumes` list (see
    `cardiaccore/workflows/preprocessing.py`'s specs, or
    `run_workflow`/`validate_workflow_commands`, which already read this same
    structure). Reusing it here is what keeps "consumed" from being a second,
    hand-maintained description of the same facts.
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
    flat, adapter-agnostic `DictEntry` tuple `validate_value_shape` is
    checked against elsewhere. Not `override_schema.dict_entry_catalog()`:
    that capability's own docstring says its shape is adapter-declared and
    nested differently per adapter, so core cannot walk it generically to
    recover qualified ids.

    `source` is drawn from `VALUE_SOURCES` (`core.case_write`) for every
    item: `"case"` when the caller's `overrides` supplies a value for this
    entry, `"template"` when the entry declares a non-empty `typical_value`
    and no override does, otherwise `"call_site_default"` -- this function
    never invents `"effective"` or `"recommendation"`, which describe a
    resolved run's actual value or a solver's own advice, neither of which a
    static catalog entry carries.
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
    """The unmet second payoff's actual seam (Phase 3 Task 9,
    docs/superpowers/plans/2026-09-23-phase3-finish-the-write-channel.md).

    R4 found the gap is that the CLI hands `_write_surface` raw factory
    kwargs (`ionic_model`, `electro_property_overrides`), never
    catalog-shaped qualified ids -- so a naive key match against
    `dictionary_catalog.entries()` (`_mutable_entries`) can only ever see a
    caller sophisticated enough to pass flat qualified ids directly, which
    no real invocation in this codebase does. Both vocabularies are cardiac,
    so core may not hardcode a mapping between them (the plan's own
    constraint).

    **Evaluated, not assumed: reusing `spec.plan_case` beats a declared
    kwarg-to-qualified-id seam.** `spec` here is already the resolved,
    materialized spec `describe_entry` built from the caller's real
    overrides (`_materialize_resolved_entry`) -- `spec.plan_case` is already
    the tutorial's own bound resolution closure, carrying every kwarg the
    caller named. Calling it needs no second, hand-maintained mapping at
    all, and no per-tutorial edit: every migrated tutorial's `plan_case`
    already has this exact two-argument shape (`PlanCaseFn`).

    **The purity question this evaluation had to answer first: what does
    calling it actually touch?** `plan_case` is not a pure resolver -- it
    calls `commit_case_overrides`/`apply_input_overrides_planned`, which
    really commits through `commit_case_write` (journal, atomic replace).
    Calling it against the real `spec.case_root` would be a real, unaudited
    write from a read-only command. So this never passes `spec.case_root`
    itself: it stages a disposable clone in a fresh temporary directory
    (reusing `sweep_runner._stage_entry_case`, the exact mechanism a real
    sweep run already uses to isolate one case before mutating it -- not a
    second copy of that logic) and calls `plan_case` against the clone. The
    real `case_root` is read only by the staging copy step (when it exists
    at all) and is never written; the caller of this function is expected
    to (and this module's own tests do) prove that with a directory
    snapshot, not merely assert it.

    Returns ``(proposed_changes, expected_effects, reason)``:

    - ``proposed_changes`` is ``None`` when this could not be computed --
      ``reason`` names why (no `plan_case`, a sweep that has not collapsed
      to one case, or the staged preview itself raising), the same "state a
      reason, never omit silently" policy `modes` already applies below.
      An empty list is the legitimate, different answer "resolved cleanly,
      and there is nothing to write" (`plan_case` returning `None` -- the
      same no-op contract `commit_case_overrides` documents).
    - ``expected_effects`` is `ResolvedMutation.expected_effects` (Task 1's
      finding: computed by every producer, read by nothing until this) as
      copied onto the committed `CaseWriteRecord`, covering targets with no
      single qualified id at all (a whole-block removal, a hex-line
      rewrite) that `proposed_changes` itself cannot address.
    """
    if spec.plan_case is None:
        return (
            None, (),
            "this spec has no plan_case; only apply_case, which does not "
            "report what it writes (or whether it goes through the case-write "
            "channel at all)",
        )
    try:
        cases = spec.build_cases()
    except Exception as exc:  # noqa: BLE001 -- reported as a reason, not raised
        return None, (), f"spec.build_cases() raised: {exc}"
    if len(cases) != 1:
        return (
            None, (),
            f"build_cases() resolved to {len(cases)} cases; a proposed-changes "
            f"preview needs exactly one case (add enough overrides to collapse "
            f"the sweep to a single case)"
        )
    case = cases[0]

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
            record = invoke_case_mutation(spec, staged_case_root, case)
        except Exception as exc:  # noqa: BLE001 -- reported as a reason, not raised
            return None, (), f"the staged plan_case preview raised: {exc}"

    if record is None:
        # A genuine, legitimate no-op (`commit_case_overrides`'s own
        # contract) -- there is nothing this mutation writes, not a failure
        # to determine what it writes.
        return [], (), ""

    # Read the record's JSON form, not `record.parameters`: the record
    # deep-freezes `parameters` (`case_write._freeze`), so a nested value --
    # a dimensioned tensor's `{"dimensions": ..., "value": ...}` -- is a
    # `MappingProxyType` of tuples there, and `describe`'s `json.dumps`
    # refused it (found 2026-09-24 on cable1DCVConvergence).
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
    """The write channel's complete proposed surface for this entry (Phase 2
    Task 13, docs/superpowers/plans/2026-09-20-phase2-one-write-channel.md).

    Generated from the same contracts validation uses, not a second
    hand-maintained description: `mutable` comes from
    `dictionary_catalog.entries()` (see `_mutable_entries`); `consumed` comes
    from the spec's own declared `workflow_dag` (see `_consumed_paths`);
    `modes` comes from `case_writer.supported_modes()`.

    **`proposed_changes` (Phase 3 Task 9, 2026-09-24): reuses the spec's own
    `plan_case`, run against a disposable staged clone -- see
    `_resolve_proposed_changes`.** When that succeeds, its output -- the
    same validated `ParameterAssignment`s the real channel would write from
    -- replaces the naive key-match below entirely, because it is strictly
    more complete: it carries the actual value, and every `operation`
    (`set`/`ensure`/`remove`), not only a `set` a caller happened to name
    with a catalog-shaped key.

    **The naive match survives as the stated fallback, but only when there is
    no resolver at all.** A spec with no `plan_case` (not yet migrated onto
    the channel) has no resolver to call, so `proposed_changes` falls back to
    the `mutable` entries whose qualified id the caller's raw `overrides`
    happens to name directly -- correct only for a caller sophisticated
    enough to pass catalog-shaped keys, which is the exact limitation Task 9
    closes for every migrated tutorial. `proposed_changes_source` is
    `"supplied_qualified_ids_only"` for this path.

    **A resolver that exists but could not run is `None` (JSON `null`), never
    an empty list (corrected 2026-09-24, found by running `describe` against
    a real fixture through the real CLI, not this module's own tests).** An
    ambiguous sweep (`build_cases()` not resolving to one case) or the staged
    preview itself raising (commonly: no case is materialized at this path
    yet -- `describe` is used before a case exists, not only after) are both
    genuine failures to determine what would change, not "nothing would
    change". Silently falling back to the naive match here would have
    reported `[]` -- correct-looking, and wrong: the naive match's own
    condition (a caller-supplied key that is already a catalog-shaped
    qualified id) is essentially never true for a raw factory-kwargs
    `overrides` dict, so it degrades to an empty list on every such failure,
    indistinguishable from a real no-op. `proposed_changes_source` is
    `"unknown"` for this path, and `describe` still exits 0: it remains a
    best-effort introspection command whose other fields (the catalog,
    `modes`, the config schema, the tutorial contract) are still valid and
    useful when a case does not exist yet, which is an ordinary situation
    for `describe`, not a caller error.

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
        proposed_changes_source = "plan_case_preview"
    elif spec.plan_case is None:
        # The only reason `_resolve_proposed_changes` returns `None` without
        # ever attempting a preview: no resolver exists for this spec at
        # all. The naive key match is the stated, pre-existing scope limit
        # (Phase 2 Task 13's own contract) -- a real, if incomplete, answer,
        # not a failure.
        proposed_changes = [
            {**item, "operation": "set"}
            for item in mutable
            if item["qualified_id"] in supplied and item["qualified_id"] in mutable_ids
        ]
        proposed_changes_source = "supplied_qualified_ids_only"
    else:
        # A resolver exists, but the attempt to run it could not complete
        # (an ambiguous sweep, or the staged preview itself raising --
        # found by running `describe` against a real fixture through the
        # real CLI, 2026-09-24: a missing case document mid-preview reached
        # here and the naive match below coincidentally computed `[]`,
        # which reads as "nothing will change" when the true state is
        # "could not be determined"). `None` here is JSON `null` -- an
        # explicit, distinct third answer a consumer cannot mistake for an
        # empty list of changes.
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
        driver_context.capabilities.override_schema.dict_entry_catalog()
    )


def _plugin_catalogs(driver_context: "DriverContext") -> dict[str, Any]:
    # The catalog names and their contents are plugin vocabulary (e.g. the
    # cardiac plugin's ionic_model_catalog/active_tension_catalog); core only
    # namespaces the whole mapping under this key and serializes it.
    return _serialize(
        dict(driver_context.capabilities.named_catalogs.catalogs())
    )


def _describe_config_schema(
    tutorial_name: str,
    make_spec_info: dict[str, Any],
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Return the plugin-authored config_schema payload for a tutorial.

    The vocabulary (override tokens, examples, document names) is solver
    knowledge and lives in the active plugin; core only routes the request.
    Updated 2026-09-22 (Task 10): when the active plugin has no
    tutorial-specific vocabulary to give, ``override_schema.config_schema``
    itself derives an answer from the validated run-document schema instead
    of an empty one -- still routed here unchanged, but no longer always the
    plugin's own words.
    """
    return driver_context.capabilities.override_schema.config_schema(
        tutorial_name, make_spec_info,
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
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Item 1: describe's own preview of a tutorial_record entry.

    Replaces the B2 refusal ``describe_entry`` used to raise for every
    ``resolve_entry`` kind alike -- for describe only (design doc
    ``docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md``
    §4's own words: "``describe`` performs steps 1-7 without committing:
    that is the preview"). Every other B2 consumer (``load_tutorial_spec``,
    ``load_entry_spec``, and therefore ``strict_plan``/``step``/``run``
    through ``--entry``) still refuses a tutorial_record by name -- there is
    no ``TutorialSpec`` here to build one from, only the record's own
    preview.

    A record has no ``spec``, so most of ``describe_entry``'s spec-derived
    sections (``spec``, ``tutorial_contract``, ``strict_launch``,
    ``config_schema``, ``write_surface``) do not apply and are simply
    absent, never a fabricated empty answer. ``record_preview`` -- each
    patch's document/key/value/status/validated flag, plus the command
    arguments per workflow step -- sits beside where ``write_surface`` would
    be for a factory tutorial.
    """
    from .runtime.record_execution import preview_record_case
    from .tutorial_records import TutorialRecordError

    record = resolution["record"]
    incoming_overrides = dict(overrides or {})
    cases_root_value = incoming_overrides.pop("cases_root", None)
    if cases_root_value is None:
        # M3: no ambient default (CLAUDE.md's "supplied versus discovered"
        # -- a case root has no ambient truth). A bare `Path.cwd()` fallback
        # here used to let `describe` preview a record against whatever
        # directory the caller happened to be standing in, silently -- the
        # same class of defect this design's own record dispatch elsewhere
        # already refuses by name.
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
        study_by_source={"base": incoming_overrides},
        driver_context=driver_context,
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
        "registered_tutorials": list_tutorials(driver_context),
        "special_tutorial_aliases": list(SPECIAL_TUTORIAL_ALIASES),
        "available_tutorials": list_available_tutorials(
            cases_root, driver_context=driver_context,
        ),
        "case_directories": list_case_directories(
            cases_root, driver_context=driver_context,
        ),
        "common_override_keys": list(COMMON_OVERRIDE_KEYS),
        "dict_entries": _dict_entry_catalog(driver_context),
        "plugin_catalogs": _plugin_catalogs(driver_context),
        "record_preview": preview,
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
    driver_context: "DriverContext",
) -> dict[str, Any]:
    resolution = resolve_entry(
        entry,
        entry_kind=entry_kind,
        overrides=overrides,
        driver_context=driver_context,
    )
    if resolution["resolution"] == "tutorial_record":
        return _describe_tutorial_record(
            entry, resolution, overrides=overrides, driver_context=driver_context,
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
        "registered_tutorials": list_tutorials(driver_context),
        "special_tutorial_aliases": list(SPECIAL_TUTORIAL_ALIASES),
        "available_tutorials": list_available_tutorials(
            cases_root, driver_context=driver_context,
        ),
        "case_directories": list_case_directories(
            cases_root, driver_context=driver_context,
        ),
        "common_override_keys": list(COMMON_OVERRIDE_KEYS),
        "make_spec": make_spec_info,
        "factory_overrides": _serialize(resolution["factory_overrides"]),
        "spec": _describe_spec(spec),
        "tutorial_contract": _serialize(
            describe_tutorial_contract(
                spec,
                resolution=resolution["resolution"],
                driver_context=driver_context,
            )
        ),
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
        "config_schema": _describe_config_schema(
            resolution["resolved_name"],
            make_spec_info,
            driver_context,
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
