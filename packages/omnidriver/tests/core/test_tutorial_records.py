"""Tutorial records, axes, and the record-entry pipeline (step 2a of
docs/superpowers/specs/2026-09-24-tutorials-are-pointers-design.md).

No cardiac or OpenFOAM vocabulary here: the "documents" this test's own
plugin reads and writes are plain JSON files, standing in for whatever
format a real adapter owns. Everything covered maps to a design refusal,
conflict, or reporting rule -- see each test's docstring for which.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.case_write import ParameterAssignment, ResolvedMutation, RenderedFile, _digest_bytes
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime import record_execution, registry
from omnidriver.core.sweep import sweep_expansion
from omnidriver.core.tutorial_records import (
    AxisContract,
    AxisMatch,
    AxisPatch,
    AxisResult,
    DocumentKeyName,
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    WorkflowStep,
    combine_patches,
    patches_to_parameters,
    resolve_case_patches,
    sort_study_name,
    split_unchanged,
)

from plugins.minimal_plugin import MinimalTestPlugin

_FORMAT = "test_json_dictionary"


# ---------------------------------------------------------------------------
# A toy case_writer/config_value/case_value_comparison plugin: JSON documents
# whose leaf values are always written as their str() form (mimicking how a
# real dictionary format renders every value as text), so the "unchanged"
# comparison genuinely needs typed parsing rather than Python ``==``.
# ---------------------------------------------------------------------------


def _deep_set(node: dict, key_path: list[str], value: str) -> None:
    for segment in key_path[:-1]:
        node = node.setdefault(segment, {})
    node[key_path[-1]] = value


def _typed_agree(value_kind: str, requested, current) -> bool:
    if current is None:
        return False
    try:
        if value_kind in ("scalar", "dimensioned_scalar"):
            return float(requested) == float(current)
        if value_kind == "integer":
            return int(requested) == int(current)
        if value_kind == "boolean":
            return bool(requested) == (str(current).strip().lower() in ("true", "yes", "1"))
    except (TypeError, ValueError):
        return False
    return str(requested) == str(current)


def _read_test_value(document_path: Path, dotted_key: str):
    if not document_path.exists():
        return None
    data = json.loads(document_path.read_text())
    node = data
    for segment in dotted_key.split("."):
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node


class _RecordCaseWriterPlugin(MinimalTestPlugin):
    """MinimalTestPlugin plus a toy JSON case_writer, for full-pipeline tests."""

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {
                "qualified_id": p.qualified_id,
                "document": p.document,
                "expanded_key_path": list(p.expanded_key_path()),
                "value": p.value,
                "format": _FORMAT,
            }
            for p in request.parameters
        )
        expected_effects = tuple(
            f"set {p.qualified_id} in {p.document}" for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets, preconditions=(),
            expected_effects=expected_effects, semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        by_document: dict[str, list] = {}
        for target in resolved.targets:
            by_document.setdefault(target["document"], []).append(target)
        rendered = []
        for document, targets in by_document.items():
            path = Path(snapshot_root) / document
            exists_before = path.exists()
            before_digest = _digest_bytes(path.read_bytes()) if exists_before else None
            content_obj = json.loads(path.read_text()) if exists_before else {}
            for target in targets:
                _deep_set(content_obj, target["expanded_key_path"], str(target["value"]))
            content = (json.dumps(content_obj, sort_keys=True) + "\n").encode()
            rendered.append(RenderedFile(
                path=document, content=content, mode=None,
                exists_before=exists_before, before_digest=before_digest,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    def get_config_value_reader(self):
        return _read_test_value

    def get_case_value_comparator(self):
        return _typed_agree


def _known_catalog_validator(document: str, key_path: tuple, value):
    """A toy record-key validator: a closed catalog for one document, and an
    OpenFOAM-owned-key exception (unvalidated, but accepted) for another."""
    catalog = {
        ("constant/electro.json", ("ionicModel",)): "word",
        ("constant/electro.json", ("cellZone",)): "word",
        ("constant/mesh.json", ("cells",)): "integer",
    }
    if (document, key_path) in catalog:
        return catalog[(document, key_path)], True
    if document == "system/unowned.json":
        # The OpenFOAM-owned-key exception (design §5): no catalog for this
        # document yet, written anyway, flagged unvalidated.
        kind = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "scalar" if isinstance(value, float) else "word"
        return kind, False
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this test's catalog")


def _number_cells_axis() -> AxisContract:
    def resolve(value, staged_case_root: Path) -> AxisResult:
        return AxisResult(
            patches=(
                AxisPatch(
                    document="constant/mesh.json", key_path=("cells",),
                    value=int(value), value_kind="integer", validated=True,
                ),
            ),
            command_arguments={"mesh": (f"-N", str(value))},
        )

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


def _record(**overrides) -> TutorialRecord:
    fields = dict(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        allowed_axes=frozenset({"number_cells"}),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("blockMesh",)),),
    )
    fields.update(overrides)
    return TutorialRecord(**fields)


def _native_case(tmp_path: Path, files: dict[str, dict]) -> Path:
    native = tmp_path / "cases" / "toyTutorial"
    native.mkdir(parents=True)
    for relpath, content in files.items():
        target = native / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, sort_keys=True) + "\n")
    return native


# ---------------------------------------------------------------------------
# Name sorting (design §3, §4 step 4)
# ---------------------------------------------------------------------------


def test_sort_study_name_classifies_a_document_key():
    result = sort_study_name(
        "constant/electro.json:a.b", allowed_axes=frozenset(), axis_catalog={},
    )
    assert isinstance(result, DocumentKeyName)
    assert result.document == "constant/electro.json"
    assert result.key_path == ("a", "b")


def test_sort_study_name_classifies_an_allowed_provided_axis():
    axis = _number_cells_axis()
    result = sort_study_name(
        "number_cells", allowed_axes=frozenset({"number_cells"}),
        axis_catalog={"number_cells": axis},
    )
    assert isinstance(result, AxisMatch)
    assert result.axis is axis


def test_sort_study_name_refuses_a_name_that_is_neither():
    with pytest.raises(TutorialRecordError, match="mesh_family"):
        sort_study_name("mesh_family", allowed_axes=frozenset(), axis_catalog={})


def test_sort_study_name_refuses_an_axis_the_record_does_not_allow():
    axis = _number_cells_axis()
    with pytest.raises(TutorialRecordError, match="does not allow"):
        sort_study_name(
            "number_cells", allowed_axes=frozenset(),  # not allowed here
            axis_catalog={"number_cells": axis},
        )


def test_sort_study_name_refuses_an_axis_no_adapter_provides():
    with pytest.raises(TutorialRecordError, match="no composed adapter"):
        sort_study_name(
            "number_cells", allowed_axes=frozenset({"number_cells"}), axis_catalog={},
        )


def test_sort_study_name_refuses_an_unknown_document():
    """An "unknown document" (task item 3): a document that fails core's own
    case-relative shape check -- absolute or escaping the case are the
    structural facts core can check without any cardiac vocabulary."""
    with pytest.raises(ValueError, match="escape"):
        sort_study_name("../outside:a.b", allowed_axes=frozenset(), axis_catalog={})


def test_sort_study_name_refuses_an_empty_key_path_segment():
    with pytest.raises(TutorialRecordError, match="empty segment"):
        sort_study_name("constant/electro.json:a..b", allowed_axes=frozenset(), axis_catalog={})


# ---------------------------------------------------------------------------
# Conflict refusal (design §4 step 6)
# ---------------------------------------------------------------------------


def _sourced(document, key, value, source, validated=True) -> SourcedPatch:
    return SourcedPatch(
        patch=AxisPatch(document=document, key_path=(key,), value=value, value_kind="word", validated=validated),
        source=source,
    )


def test_combine_patches_refuses_two_sources_with_different_values():
    patches = [
        _sourced("constant/a.json", "k", "one", source="base"),
        _sourced("constant/a.json", "k", "two", source="sweep"),
    ]
    with pytest.raises(TutorialRecordError, match="base") as excinfo:
        combine_patches(patches)
    assert "sweep" in str(excinfo.value)


def test_combine_patches_allows_two_sources_agreeing_on_one_value():
    patches = [
        _sourced("constant/a.json", "k", "one", source="base"),
        _sourced("constant/a.json", "k", "one", source="sweep"),
    ]
    combined = combine_patches(patches)
    assert len(combined) == 1
    assert combined[0].patch.value == "one"


def test_combine_patches_prefers_the_validated_agreeing_patch():
    patches = [
        _sourced("constant/a.json", "k", "one", source="base", validated=False),
        _sourced("constant/a.json", "k", "one", source="axis", validated=True),
    ]
    combined = combine_patches(patches)
    assert len(combined) == 1
    assert combined[0].patch.validated is True


# ---------------------------------------------------------------------------
# resolve_case_patches: sorting + axes + direct keys, end to end (pure)
# ---------------------------------------------------------------------------


def test_resolve_case_patches_runs_axes_and_direct_keys_together():
    record = _record()
    axis_catalog = {"number_cells": _number_cells_axis()}
    combined, command_args = resolve_case_patches(
        record,
        study_by_source={
            "base": {"constant/electro.json:ionicModel": "TT06"},
            "sweep": {"number_cells": 5},
        },
        axis_catalog=axis_catalog,
        staged_case_root=Path("/nonexistent"),  # this axis never reads the case
        direct_key_validator=_known_catalog_validator,
    )
    by_slot = {p.slot(): p for p in combined}
    assert by_slot["constant/electro.json::ionicModel"].patch.value == "TT06"
    assert by_slot["constant/mesh.json::cells"].patch.value == 5
    assert command_args["mesh"] == ("-N", "5")


def test_resolve_case_patches_refuses_a_direct_key_absent_from_the_catalog():
    record = _record()
    with pytest.raises(KeyError):
        resolve_case_patches(
            record,
            study_by_source={"base": {"constant/electro.json:unknownKey": "x"}},
            axis_catalog={},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_accepts_an_unvalidated_openfoam_owned_key():
    record = _record()
    combined, _ = resolve_case_patches(
        record,
        study_by_source={"base": {"system/unowned.json:endTime": 0.02}},
        axis_catalog={},
        staged_case_root=Path("/nonexistent"),
        direct_key_validator=_known_catalog_validator,
    )
    assert len(combined) == 1
    assert combined[0].patch.validated is False


def test_resolve_case_patches_refuses_before_running_any_axis():
    """Design §4 step 4: names are sorted BEFORE any axis runs. A bad name
    anywhere in the study must be caught before a well-formed axis's
    resolve() is ever called."""
    calls: list = []

    def _tracking_resolve(value, staged_case_root):
        calls.append(value)
        return AxisResult()

    good_axis = AxisContract(name="good_axis", value_kind="integer", resolve=_tracking_resolve)
    record = _record(allowed_axes=frozenset({"good_axis"}))
    with pytest.raises(TutorialRecordError):
        resolve_case_patches(
            record,
            study_by_source={
                "base": {"good_axis": 1, "not_a_real_axis_or_key": 2},
            },
            axis_catalog={"good_axis": good_axis},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )
    assert calls == []


# ---------------------------------------------------------------------------
# Unchanged reporting (design §4 step 7)
# ---------------------------------------------------------------------------


def test_split_unchanged_separates_changed_from_unchanged():
    def reader(document_path, dotted_key):
        return {"cells": "5", "ionicModel": "TT06"}.get(dotted_key)

    patches = [
        SourcedPatch(patch=AxisPatch("constant/mesh.json", ("cells",), 5, "integer"), source="sweep"),
        SourcedPatch(patch=AxisPatch("constant/electro.json", ("ionicModel",), "LR91", "word"), source="base"),
    ]
    to_write, unchanged = split_unchanged(
        patches, case_root=Path("/whatever"),
        read_current_value=reader, values_agree=_typed_agree,
    )
    assert [p.patch.value for p in unchanged] == [5]
    assert [p.patch.value for p in to_write] == ["LR91"]


def test_split_unchanged_treats_an_undeterminable_patch_as_changed():
    """No reader/comparator (an adapter that declares neither): nothing is
    ever silently reported unchanged."""
    patches = [SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), 1, "integer"), source="base")]
    to_write, unchanged = split_unchanged(
        patches, case_root=Path("/whatever"), read_current_value=None, values_agree=None,
    )
    assert to_write == tuple(patches)
    assert unchanged == ()


# ---------------------------------------------------------------------------
# The validated flag: round trip into ParameterAssignment / CaseWriteRecord
# ---------------------------------------------------------------------------


def test_patches_to_parameters_carries_the_validated_flag_through():
    patches = [
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), "v", "word", validated=True), source="base"),
        SourcedPatch(patch=AxisPatch("system/unowned.json", ("endTime",), 0.02, "scalar", validated=False), source="base"),
    ]
    parameters = patches_to_parameters(patches, owner="org.test")
    assert isinstance(parameters[0], ParameterAssignment)
    assert parameters[0].validated is True
    assert parameters[1].validated is False
    payload = [p.to_json() for p in parameters]
    assert payload[0]["validated"] is True
    assert payload[1]["validated"] is False


def test_parameter_assignment_validated_defaults_true_and_round_trips_json():
    assignment = ParameterAssignment(
        qualified_id="q", owner="org.a", document="constant/a", key_path=("k",),
        binding={}, value=1.0, value_kind="scalar", source="case",
    )
    assert assignment.validated is True
    restored = ParameterAssignment.from_json(assignment.to_json())
    assert restored.validated is True

    unvalidated = ParameterAssignment(
        qualified_id="q2", owner="org.a", document="constant/a", key_path=("k2",),
        binding={}, value=1.0, value_kind="scalar", source="case", validated=False,
    )
    assert ParameterAssignment.from_json(unvalidated.to_json()).validated is False


# ---------------------------------------------------------------------------
# Explicit entry-kind dispatch (registry.resolve_entry)
# ---------------------------------------------------------------------------


def test_resolve_entry_dispatches_a_tutorial_record_explicitly(tmp_path):
    record = _record()
    plugin = MinimalTestPlugin(tutorial_records={"toyTutorial": record})
    context = driver_context(plugin, source="test:records")

    resolution = registry.resolve_entry(
        "toyTutorial", overrides={"cases_root": str(tmp_path)}, driver_context=context,
    )
    assert resolution["resolution"] == "tutorial_record"
    assert resolution["entry_kind"] == "tutorial_record"
    assert resolution["record"] is record


def test_a_record_is_never_resolved_as_a_factory_or_a_case_path(tmp_path):
    record = _record()
    plugin = MinimalTestPlugin(tutorial_records={"toyTutorial": record})
    context = driver_context(plugin, source="test:records")

    with pytest.raises(KeyError):
        registry.resolve_entry(
            "toyTutorial", entry_kind="registered_tutorial",
            overrides={"cases_root": str(tmp_path)}, driver_context=context,
        )
    with pytest.raises(KeyError):
        registry.resolve_entry(
            "toyTutorial", entry_kind="case_folder",
            overrides={"cases_root": str(tmp_path)}, driver_context=context,
        )


def test_a_factory_tutorial_is_never_resolved_as_a_record(tmp_path):
    """The converse: a name registered only as a spec_factory must never
    come back as a tutorial_record resolution."""
    def _factory(**kwargs):
        raise AssertionError("factory should not be invoked by resolve_entry")

    class _FactoryPlugin(MinimalTestPlugin):
        def get_tutorial_catalog(self):
            return {"registered_tutorials": ("factoryOnly",), "spec_factories": {"factoryOnly": _factory}}

    context = driver_context(_FactoryPlugin(), source="test:factory")
    resolution = registry.resolve_entry(
        "factoryOnly", overrides={"cases_root": str(tmp_path)}, driver_context=context,
    )
    assert resolution["resolution"] == "registered"
    assert resolution["entry_kind"] == "registered_tutorial"


def test_resolve_entry_refuses_a_name_registered_as_both_record_and_factory(tmp_path):
    def _factory(**kwargs):
        raise AssertionError("must not be reached")

    record = _record(name="both")

    class _BothPlugin(MinimalTestPlugin):
        def get_tutorial_catalog(self):
            return {"registered_tutorials": ("both",), "spec_factories": {"both": _factory}}

    plugin = _BothPlugin(tutorial_records={"both": record})
    context = driver_context(plugin, source="test:both")
    with pytest.raises(KeyError, match="ambiguous"):
        registry.resolve_entry(
            "both", overrides={"cases_root": str(tmp_path)}, driver_context=context,
        )


# ---------------------------------------------------------------------------
# Full pipeline: preview and commit against a real staged case
# ---------------------------------------------------------------------------


def _context_with_writer(tutorial_records=None, axis_catalog=None):
    plugin = _RecordCaseWriterPlugin(
        tutorial_records=tutorial_records or {},
        axis_catalog=axis_catalog or {},
        record_key_validator=_known_catalog_validator,
    )
    return driver_context(plugin, source="test:pipeline")


def test_preview_record_case_lists_each_patch_with_status_and_validated(tmp_path):
    _native_case(tmp_path, {
        "constant/electro.json": {"ionicModel": "TT06"},
        "constant/mesh.json": {"cells": "5"},
    })
    record = _record()
    context = _context_with_writer(axis_catalog={"number_cells": _number_cells_axis()})

    preview = record_execution.preview_record_case(
        record,
        cases_root=tmp_path / "cases",
        study_by_source={
            "base": {"constant/electro.json:ionicModel": "LR91"},
            "sweep": {"number_cells": 5},
        },
        driver_context=context,
    )
    by_document = {p["document"]: p for p in preview["patches"]}
    assert by_document["constant/electro.json"]["status"] == "changed"
    assert by_document["constant/electro.json"]["validated"] is True
    assert by_document["constant/mesh.json"]["status"] == "unchanged"
    assert preview["command_arguments"]["mesh"] == ["-N", "5"]


def test_commit_record_case_writes_one_case_with_validated_flags_in_the_record(tmp_path):
    _native_case(tmp_path, {"constant/electro.json": {"ionicModel": "TT06"}})
    record = _record(allowed_axes=frozenset())
    context = _context_with_writer()

    write_record, _command_args = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={
            "base": {
                "constant/electro.json:ionicModel": "LR91",
                "system/unowned.json:endTime": 0.02,
            },
        },
        driver_context=context,
    )
    assert write_record is not None
    assert write_record.status == "committed"
    by_qualified_id = {p["qualified_id"]: p for p in write_record.parameters}
    assert by_qualified_id["constant/electro.json::ionicModel"]["validated"] is True
    assert by_qualified_id["system/unowned.json::endTime"]["validated"] is False
    written = json.loads((tmp_path / "staged" / "constant" / "electro.json").read_text())
    assert written["ionicModel"] == "LR91"


def test_commit_record_case_writes_nothing_when_every_patch_is_unchanged(tmp_path):
    _native_case(tmp_path, {"constant/electro.json": {"ionicModel": "TT06"}})
    record = _record(allowed_axes=frozenset())
    context = _context_with_writer()

    write_record, _ = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"constant/electro.json:ionicModel": "TT06"}},
        driver_context=context,
    )
    assert write_record is None


def test_commit_record_case_refuses_when_the_native_case_is_missing(tmp_path):
    record = _record()
    context = _context_with_writer()
    with pytest.raises(TutorialRecordError, match="does not exist"):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",  # never created
            staged_case_root=tmp_path / "staged",
            study_by_source={"base": {}},
            driver_context=context,
        )


def test_commit_record_case_refuses_a_conflict_between_base_and_sweep(tmp_path):
    _native_case(tmp_path, {"constant/electro.json": {"ionicModel": "TT06"}})
    record = _record(allowed_axes=frozenset())
    context = _context_with_writer()
    with pytest.raises(TutorialRecordError):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={
                "base": {"constant/electro.json:ionicModel": "LR91"},
                "sweep": {"constant/electro.json:ionicModel": "TT06"},
            },
            driver_context=context,
        )


# ---------------------------------------------------------------------------
# A sweep over a record entry: one commit per case
# ---------------------------------------------------------------------------


def test_a_sweep_over_a_record_entry_produces_one_commit_per_case(tmp_path):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "1"}})
    record = _record()
    context = _context_with_writer(axis_catalog={"number_cells": _number_cells_axis()})

    sweep_spec = {
        "base": {},
        "sweep": {
            "mode": "cross_product",
            "independent": {"number_cells": [2, 3]},
        },
    }
    resolved_cases = sweep_expansion.expand_sweep(sweep_spec)
    assert len(resolved_cases) == 2

    committed = []
    for case in resolved_cases:
        write_record, _ = record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "sweep_cases" / case.case_id,
            study_by_source={"base": sweep_spec["base"], "sweep": case.resolved_axis_values},
            driver_context=context,
        )
        assert write_record is not None
        committed.append(write_record)

    assert len({r.transaction_id for r in committed}) == 2
    cells_by_case = {
        case.case_id: json.loads(
            (tmp_path / "sweep_cases" / case.case_id / "constant" / "mesh.json").read_text()
        )["cells"]
        for case in resolved_cases
    }
    assert cells_by_case == {"case_0001": "2", "case_0002": "3"}
