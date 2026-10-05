"""Tutorial records, axes, and the record-entry pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.runtime.attempt_lease import acquire_case_lease

from omnidriver.core.case_write import CaseKeyNotFound, ParameterAssignment, ResolvedMutation, RenderedFile, _digest_bytes
from omnidriver.core.planning_types import diagnostic
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime import record_execution
from omnidriver.core.sweep import sweep_expansion
from omnidriver.core.tutorial_records import (
    AxisContract,
    AxisMatch,
    AxisPatch,
    AxisResult,
    DefaultArgument,
    DocumentKeyName,
    SourcedPatch,
    TutorialRecord,
    TutorialRecordError,
    WorkflowStep,
    build_tutorial_record_catalog,
    combine_patches,
    lookup_record,
    patches_to_parameters,
    resolve_case_patches,
    resolve_variant_selector,
    sort_study_name,
    split_unchanged,
)

from plugins.toy import ToyProvider

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


def _read_test_value(document_path: Path, key: str, *, scope: list[str] | None = None):
    """Mirrors the real reader's contract exactly: a plain leaf `key` plus a separate `scope`, matching `omnidriver.openfoam.mutators.read_foam_entry`'s own signature."""
    if not document_path.exists():
        return None
    node = json.loads(document_path.read_text())
    for segment in scope or ():
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    if not isinstance(node, dict) or key not in node:
        return None
    return node[key]


def _read_test_value_by_key_path(document_path: Path, key_path):
    """The adapter half of the contract: core always calls the capability's reader with a KEY-PATH TUPLE (never a dotted string); the adapter itself splits that into ``scope``/``key``, exactly as ``omnidriver.openfoam.environment._read_config_value_by_key_path`` does for the real OpenFOAM reader."""
    segments = tuple(key_path)
    if not segments:
        raise ValueError("a config value read needs a non-empty key path")
    *scope, key = segments
    return _read_test_value(document_path, key, scope=scope or None)


class _RecordCaseWriterPlugin(ToyProvider):
    """ToyProvider plus a toy JSON case_writer, for full-pipeline tests."""

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
            request=request, targets=targets, expected_effects=expected_effects, semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        # A real renderer (omnidriver.openfoam.case_rendering) reads the real
        # case ONLY to seed a copy under `snapshot_root` -- the two must never
        # be the same directory, or its seeding copy becomes a copy of a file
        # onto itself (`shutil.SameFileError`). This toy renderer reads from
        # snapshot_root and would not notice, so this assertion pins that
        # `commit_record_case` passes distinct directories.
        case_root = Path(resolved.request.case_root)
        assert Path(snapshot_root) != case_root, (
            f"render_case_files was called with snapshot_root == case_root "
            f"({case_root}); a renderer must seed a copy under a directory "
            "distinct from the real case"
        )
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
        return _read_test_value_by_key_path

    def get_case_value_comparator(self):
        return _typed_agree


def _known_catalog_validator(document: str, key_path: tuple, value):
    """A toy record-key validator: a closed catalog for one document, and an environment-owned-key exception (unvalidated, but accepted) for another."""
    catalog = {
        ("constant/physics.json", ("modelName",)): "word",
        ("constant/physics.json", ("cellZone",)): "word",
        ("constant/mesh.json", ("cells",)): "integer",
    }
    if (document, key_path) in catalog:
        return catalog[(document, key_path)], True
    if document == "system/unowned.json":
        # The environment-owned-key exception (design §5): no catalog for
        # this document yet, written anyway, flagged unvalidated.
        kind = "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "scalar" if isinstance(value, float) else "word"
        return kind, False
    raise KeyError(f"{document}:{'.'.join(key_path)} is not in this test's catalog")


def _number_cells_axis() -> AxisContract:
    def resolve(value, staged_case_root: Path) -> AxisResult:
        return AxisResult(
            patches=(
                AxisPatch(
                    document="constant/mesh.json", key_path=("cells",),
                    value=int(value), value_kind="integer",
                ),
            ),
            command_arguments={"mesh": (f"-N", str(value))},
        )

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


def _record(**overrides) -> TutorialRecord:
    fields = dict(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        axes=(_number_cells_axis(),),
        workflow_steps=(WorkflowStep(step_id="mesh", command=("generate-mesh",)),),
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
# TutorialRecord construction (native_case_relpath is case-relative)
# ---------------------------------------------------------------------------


def test_tutorial_record_refuses_an_absolute_native_case_relpath():
    with pytest.raises(ValueError, match="absolute"):
        _record(native_case_relpath="/etc")


def test_tutorial_record_refuses_a_native_case_relpath_that_escapes_the_case():
    with pytest.raises(ValueError, match="escape"):
        _record(native_case_relpath="../outside")


# ---------------------------------------------------------------------------
# Record-scoped axes: an axis belongs to the record that uses
# it, so one name can mean different things in two records, and two axes of
# one record can never share a name silently.
# ---------------------------------------------------------------------------


def _patch_axis(name: str, document: str) -> AxisContract:
    def resolve(value, staged_case_root):
        del staged_case_root
        return AxisResult(patches=(AxisPatch(document, ("cells",), int(value), "integer"),))

    return AxisContract(name=name, value_kind="integer", resolve=resolve)


def test_a_record_refuses_two_axes_under_one_name():
    with pytest.raises(TutorialRecordError, match=r"'toyTutorial' declares axis 'number_cells' twice"):
        _record(axes=(_number_cells_axis(), _patch_axis("number_cells", "constant/other.json")))


def test_a_record_refuses_axes_given_as_a_name_mapping():
    """A ``name -> contract`` dict restates each contract's own name, and a literal with one key twice keeps only the last value -- the silent clash this guard exists to refuse."""
    with pytest.raises(TutorialRecordError, match="sequence of AxisContract, not dict"):
        _record(axes={"number_cells": _number_cells_axis()})


def test_a_record_refuses_an_axis_that_is_not_an_axis_contract():
    with pytest.raises(TutorialRecordError, match="'number_cells', which is not an AxisContract"):
        _record(axes=("number_cells",))


def test_one_axis_name_resolves_within_each_record_that_declares_it():
    """Two records each declare ``number_cells`` with a different meaning; each study resolves the name against its own record, never the other's (the manufacturedBidomain/manufacturedEikonalECG ``dimension`` defect)."""
    first = _record(name="first", axes=(_patch_axis("number_cells", "constant/first.json"),))
    second = _record(name="second", axes=(_patch_axis("number_cells", "constant/second.json"),))

    def validator(document, key_path, value):
        return "integer", True

    for record, document in ((first, "constant/first.json"), (second, "constant/second.json")):
        combined, _ = resolve_case_patches(
            record, study_by_source={"base": {"number_cells": 4}},
            staged_case_root=Path("/nonexistent"), direct_key_validator=validator,
        )
        assert [sourced.patch.document for sourced in combined] == [document]


def test_workflow_step_refuses_an_empty_command():
    """A step with no command has nothing to run -- refused at construction, not later as an IndexError on `argv[0]`."""
    with pytest.raises(TutorialRecordError, match="non-empty command"):
        WorkflowStep(step_id="s", command=())


def test_workflow_step_refuses_an_empty_step_id():
    with pytest.raises(TutorialRecordError, match="non-empty step_id"):
        WorkflowStep(step_id="", command=("x",))


# ---------------------------------------------------------------------------
# Name sorting
# ---------------------------------------------------------------------------


def test_sort_study_name_classifies_a_document_key():
    result = sort_study_name(
        "constant/physics.json:a.b", axes=(),
    )
    assert isinstance(result, DocumentKeyName)
    assert result.document == "constant/physics.json"
    assert result.key_path == ("a", "b")


def test_sort_study_name_classifies_an_axis_the_entry_declares():
    axis = _number_cells_axis()
    result = sort_study_name("number_cells", axes=(axis,))
    assert isinstance(result, AxisMatch)
    assert result.axis is axis


def test_sort_study_name_refuses_a_name_that_is_neither():
    with pytest.raises(TutorialRecordError, match="mesh_family"):
        sort_study_name("mesh_family", axes=())


def test_sort_study_name_refuses_a_bare_name_the_entry_declares_no_axis_for():
    """A bare name resolves against the entry's own axes only, and the refusal names the ones it has."""
    with pytest.raises(TutorialRecordError, match=r"'mesh_family'.*declared axes: \['number_cells'\]"):
        sort_study_name("mesh_family", axes=(_number_cells_axis(),))


def test_sort_study_name_refuses_an_unknown_document():
    """An "unknown document": a document that fails core's own case-relative shape check -- absolute or escaping the case are the structural facts core can check without knowing any solver's vocabulary."""
    with pytest.raises(ValueError, match="escape"):
        sort_study_name("../outside:a.b", axes=())


def test_sort_study_name_refuses_an_empty_key_path_segment():
    with pytest.raises(TutorialRecordError, match="empty segment"):
        sort_study_name("constant/physics.json:a..b", axes=())


# ---------------------------------------------------------------------------
# Conflict refusal
# ---------------------------------------------------------------------------


def _sourced(document, key, value, source, validated=True) -> SourcedPatch:
    return SourcedPatch(
        patch=AxisPatch(document=document, key_path=(key,), value=value, value_kind="word"),
        source=source,
        validated=validated,
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


def test_combine_patches_keeps_the_first_agreeing_patch_regardless_of_validated_flag():
    """There is no "prefer the validated agreeing patch" tie-break."""
    patches = [
        _sourced("constant/a.json", "k", "one", source="base", validated=False),
        _sourced("constant/a.json", "k", "one", source="axis", validated=True),
    ]
    combined = combine_patches(patches)
    assert len(combined) == 1
    assert combined[0].source == "base"
    assert combined[0].validated is False


def test_combine_patches_refuses_a_value_kind_mismatch_even_when_values_are_equal():
    """A slot two sources disagree on the KIND of is a conflict even when Python happens to consider the values equal (int 1 == float 1.0)."""
    patches = [
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), 1, "integer"), source="base", validated=True),
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), 1.0, "scalar"), source="axis", validated=True),
    ]
    with pytest.raises(TutorialRecordError):
        combine_patches(patches)


def test_combine_patches_refuses_int_and_bool_as_a_conflict():
    """Strict same-type equality -- 1 vs True is a conflict, not an agreement, even though Python's `1 == True`."""
    patches = [
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), 1, "integer"), source="base", validated=True),
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), True, "integer"), source="axis", validated=True),
    ]
    with pytest.raises(TutorialRecordError):
        combine_patches(patches)


# ---------------------------------------------------------------------------
# resolve_case_patches: sorting + axes + direct keys, end to end (pure)
# ---------------------------------------------------------------------------


def test_resolve_case_patches_runs_axes_and_direct_keys_together():
    record = _record()
    combined, command_args = resolve_case_patches(
        record,
        study_by_source={
            "base": {"constant/physics.json:modelName": "modelAlpha"},
            "sweep": {"number_cells": 5},
        },
        staged_case_root=Path("/nonexistent"),  # this axis never reads the case
        direct_key_validator=_known_catalog_validator,
    )
    by_slot = {p.slot(): p for p in combined}
    assert by_slot["constant/physics.json::modelName"].patch.value == "modelAlpha"
    assert by_slot["constant/mesh.json::cells"].patch.value == 5
    assert command_args["mesh"] == ("-N", "5")


def test_resolve_case_patches_refuses_a_direct_key_absent_from_the_catalog():
    """The validator's own KeyError is wrapped in a TutorialRecordError naming the key -- never surfaced as a bare KeyError whose message may or may not mention it."""
    record = _record()
    with pytest.raises(TutorialRecordError, match="unknownKey"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"constant/physics.json:unknownKey": "x"}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_accepts_an_unvalidated_environment_owned_key():
    record = _record()
    combined, _ = resolve_case_patches(
        record,
        study_by_source={"base": {"system/unowned.json:endTime": 0.02}},
        staged_case_root=Path("/nonexistent"),
        direct_key_validator=_known_catalog_validator,
    )
    assert len(combined) == 1
    assert combined[0].validated is False


def test_resolve_case_patches_validates_axis_produced_patches_too():
    """Every combined patch, direct key or axis output, goes through record_key_validation.validate before commit -- an axis is not a back door around the catalog."""
    def rogue(value, staged_case_root):
        return AxisResult(
            patches=(AxisPatch("constant/physics.json", ("notInCatalog",), value, "word"),),
        )

    axis = AxisContract(name="rogue", value_kind="word", resolve=rogue)
    record = _record(axes=(axis,))
    with pytest.raises(TutorialRecordError, match="notInCatalog"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"rogue": "x"}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_refuses_a_value_that_does_not_fit_the_axis_value_kind():
    """AxisContract.value_kind is checked against the study's value before resolve runs, and a misfit is a TutorialRecordError naming the axis, not whatever exception the axis's own resolve raises coercing it."""
    def resolve(value, staged_case_root):
        return AxisResult(patches=(
            AxisPatch("constant/mesh.json", ("cells",), int(value), "integer"),
        ))

    axis = AxisContract(name="number_cells", value_kind="integer", resolve=resolve)
    record = _record(axes=(axis,))
    with pytest.raises(TutorialRecordError, match="number_cells"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"number_cells": "not-a-number"}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_refuses_an_axis_that_writes_the_staged_case(tmp_path):
    """Axis purity enforced at RUNTIME, not merely documented."""
    staged_case_root = tmp_path / "staged"
    staged_case_root.mkdir()

    def rogue(value, case_root: Path):
        (case_root / "sneaky.txt").write_text("not through the channel")
        return AxisResult()

    axis = AxisContract(name="rogue", value_kind="word", resolve=rogue)
    record = _record(axes=(axis,))
    with pytest.raises(TutorialRecordError, match="rogue.*not pure"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"rogue": "x"}},
            staged_case_root=staged_case_root,
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_validates_all_direct_keys_before_any_axis_runs():
    """A direct key that the catalog will refuse must be caught before any axis (even a well-formed, allowed one) is given a chance to run -- not merely before OTHER bad names, which test_resolve_case_patches_refuses_before_running_any_axis already covers."""
    calls: list = []

    def tracking_resolve(value, staged_case_root):
        calls.append(value)
        return AxisResult()

    axis = AxisContract(name="number_cells", value_kind="integer", resolve=tracking_resolve)
    record = _record()
    with pytest.raises(TutorialRecordError):
        resolve_case_patches(
            record,
            study_by_source={
                "sweep": {"number_cells": 3},
                "base": {"constant/physics.json:unknownKey": "x"},
            },
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )
    assert calls == []


def test_resolve_case_patches_refuses_command_arguments_for_an_undeclared_step():
    """An axis contributing command arguments to a step id the record does not declare in its `workflow_steps` is refused by name -- the record's `workflow_steps` is the only place step ids come from."""
    def rogue(value, staged_case_root):
        return AxisResult(command_arguments={"not_a_real_step": ("-x",)})

    axis = AxisContract(name="rogue_step", value_kind="integer", resolve=rogue)
    record = _record(axes=(axis,))
    with pytest.raises(TutorialRecordError, match="not_a_real_step"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"rogue_step": 1}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def test_resolve_case_patches_refuses_conflicting_command_arguments_for_one_step():
    """Two axes contributing DIFFERENT arguments to the SAME declared step is refused by name -- no concatenation, no later-wins."""
    def axis_one(value, staged_case_root):
        return AxisResult(command_arguments={"mesh": ("-N", "5")})

    def axis_two(value, staged_case_root):
        return AxisResult(command_arguments={"mesh": ("-N", "9")})

    record = _record(axes=(
        AxisContract(name="one", value_kind="integer", resolve=axis_one),
        AxisContract(name="two", value_kind="integer", resolve=axis_two),
    ))
    with pytest.raises(TutorialRecordError, match="mesh"):
        resolve_case_patches(
            record,
            study_by_source={"base": {"one": 1, "two": 2}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )


def _record_with_a_default_argument(axis: AxisContract) -> TutorialRecord:
    return _record(
        axes=(axis,),
        workflow_steps=(
            WorkflowStep(
                step_id="mesh", command=("generate-mesh",),
                default_arguments=(DefaultArgument(key=("-dict",), values=("system/meshDict.3D",)),),
            ),
        ),
    )


def _mesh_file_axis(*arguments: str) -> AxisContract:
    def resolve(value, staged_case_root):
        return AxisResult(command_arguments={"mesh": arguments})

    return AxisContract(name="meshFile", value_kind="word", resolve=resolve)


def test_resolve_case_patches_refuses_an_axis_that_passes_a_default_key_twice():
    """An axis replaces a default argument by passing its key once."""
    with pytest.raises(TutorialRecordError) as exc:
        resolve_case_patches(
            _record_with_a_default_argument(_mesh_file_axis("-dict", "a", "-dict", "b")),
            study_by_source={"base": {"meshFile": "x"}},
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )
    message = str(exc.value)
    assert "'meshFile'" in message and "'mesh'" in message and "['-dict']" in message


def test_preview_shows_each_selected_steps_command_with_its_default_argument(tmp_path):
    """With no study values the step runs its default argument; ``record_preview.workflow_commands`` shows the argv that will run."""
    _native_case(tmp_path, {})
    preview = record_execution.preview_record_case(
        _record_with_a_default_argument(_mesh_file_axis("-dict", "x")), cases_root=tmp_path / "cases",
        study_by_source={"base": {}},
        driver_context=_context_with_writer(),
    )
    assert preview["workflow_commands"] == {"mesh": ["generate-mesh", "-dict", "system/meshDict.3D"]}
    assert preview["command_arguments"] == {}


def test_preview_shows_the_axis_argument_in_place_of_the_default(tmp_path):
    _native_case(tmp_path, {})
    preview = record_execution.preview_record_case(
        _record_with_a_default_argument(_mesh_file_axis("-dict", "system/meshDict.1D")),
        cases_root=tmp_path / "cases",
        study_by_source={"base": {"meshFile": "1D"}},
        driver_context=_context_with_writer(),
    )
    assert preview["workflow_commands"] == {"mesh": ["generate-mesh", "-dict", "system/meshDict.1D"]}
    assert preview["command_arguments"] == {"mesh": ["-dict", "system/meshDict.1D"]}


def test_resolve_case_patches_allows_identical_command_arguments_for_one_step():
    """Two axes contributing the SAME arguments to the same step agree, and the arguments are not concatenated (duplicated) either."""
    def axis_one(value, staged_case_root):
        return AxisResult(command_arguments={"mesh": ("-N", "5")})

    def axis_two(value, staged_case_root):
        return AxisResult(command_arguments={"mesh": ("-N", "5")})

    record = _record(axes=(
        AxisContract(name="one", value_kind="integer", resolve=axis_one),
        AxisContract(name="two", value_kind="integer", resolve=axis_two),
    ))
    _, command_args = resolve_case_patches(
        record,
        study_by_source={"base": {"one": 1, "two": 2}},
        staged_case_root=Path("/nonexistent"),
        direct_key_validator=_known_catalog_validator,
    )
    assert command_args["mesh"] == ("-N", "5")


def test_resolve_case_patches_refuses_before_running_any_axis():
    """Names are sorted BEFORE any axis runs."""
    calls: list = []

    def _tracking_resolve(value, staged_case_root):
        calls.append(value)
        return AxisResult()

    good_axis = AxisContract(name="good_axis", value_kind="integer", resolve=_tracking_resolve)
    record = _record(axes=(good_axis,))
    with pytest.raises(TutorialRecordError):
        resolve_case_patches(
            record,
            study_by_source={
                "base": {"good_axis": 1, "not_a_real_axis_or_key": 2},
            },
            staged_case_root=Path("/nonexistent"),
            direct_key_validator=_known_catalog_validator,
        )
    assert calls == []


# ---------------------------------------------------------------------------
# The variant selector: picks a workflow_variant, produces no patches. Not an
# axis -- refused by name when unknown, and refused when the record declares no
# variants at all. The selector's NAME is declared by the record itself
# (`variant_selector`), never a core-owned constant.
# ---------------------------------------------------------------------------


def test_resolve_variant_selector_picks_a_declared_variant():
    record = _record(
        workflow_steps=(
            WorkflowStep(step_id="meshA", command=("toolA",)),
            WorkflowStep(step_id="meshB", command=("toolB",)),
            WorkflowStep(step_id="solve", command=("solverBinary",)),
        ),
        workflow_variants={
            "variantA": ("meshA", "solve"),
            "variantB": ("meshB", "solve"),
        },
        variant_selector="variant",
        default_variant="variantA",
    )
    assert resolve_variant_selector(record, "variantA") == ("meshA", "solve")
    assert resolve_variant_selector(record, "variantB") == ("meshB", "solve")


def test_resolve_variant_selector_refuses_an_unknown_variant_by_name():
    record = _record(
        workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
        workflow_variants={"variantA": ("meshA",)},
        variant_selector="variant",
        default_variant="variantA",
    )
    with pytest.raises(TutorialRecordError, match="unknownVariant"):
        resolve_variant_selector(record, "unknownVariant")


def test_resolve_variant_selector_refuses_a_null_value():
    """A null selector value is refused, never silently coerced into the string ``"None"`` (which could spuriously match a variant literally named that)."""
    record = _record(
        workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
        workflow_variants={"variantA": ("meshA",)},
        variant_selector="variant",
        default_variant="variantA",
    )
    with pytest.raises(TutorialRecordError, match="null"):
        resolve_variant_selector(record, None)


def test_resolve_variant_selector_does_not_coerce_the_value_with_str():
    """No str() coercion -- an integer 1 must not silently match a variant literally named "1", nor True one named "True"."""
    record = _record(
        workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
        workflow_variants={"1": ("meshA",), "True": ("meshA",)},
        variant_selector="variant",
        default_variant="1",
    )
    with pytest.raises(TutorialRecordError, match="not a workflow variant"):
        resolve_variant_selector(record, 1)
    with pytest.raises(TutorialRecordError, match="not a workflow variant"):
        resolve_variant_selector(record, True)


def test_resolve_variant_selector_refuses_a_record_with_no_variants():
    record = _record()  # no workflow_variants declared
    with pytest.raises(TutorialRecordError, match="no workflow_variants"):
        resolve_variant_selector(record, "variantA")


def test_tutorial_record_refuses_workflow_variants_without_a_variant_selector():
    """A record declaring workflow_variants but no variant_selector name has nothing that could ever select among them -- refused at construction, not discovered later as a silently-unreachable variant."""
    with pytest.raises(TutorialRecordError, match="variant_selector"):
        _record(
            workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
            workflow_variants={"variantA": ("meshA",)},
        )


def test_tutorial_record_refuses_workflow_variants_without_a_default_variant():
    """A record with routes names the one its native case runs (``default_variant``)."""
    with pytest.raises(TutorialRecordError, match="default_variant") as exc:
        _record(
            workflow_steps=(
                WorkflowStep(step_id="meshA", command=("toolA",)),
                WorkflowStep(step_id="meshB", command=("toolB",)),
            ),
            workflow_variants={"variantA": ("meshA",), "variantB": ("meshB",)},
            variant_selector="variant",
        )
    assert "variantA" in str(exc.value) and "variantB" in str(exc.value)


def test_tutorial_record_refuses_a_default_variant_it_does_not_declare():
    with pytest.raises(TutorialRecordError, match="'variantC'") as exc:
        _record(
            workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
            workflow_variants={"variantA": ("meshA",)},
            variant_selector="variant",
            default_variant="variantC",
        )
    assert "default_variant" in str(exc.value)
    assert "variantA" in str(exc.value)


def test_tutorial_record_refuses_a_default_variant_it_does_not_coerce():
    """The default is compared exactly, like a study's selector value: an integer ``1`` does not name a variant called ``"1"``."""
    with pytest.raises(TutorialRecordError, match="default_variant"):
        _record(
            workflow_steps=(WorkflowStep(step_id="meshA", command=("toolA",)),),
            workflow_variants={"1": ("meshA",)},
            variant_selector="variant",
            default_variant=1,
        )


def test_tutorial_record_refuses_a_default_variant_without_workflow_variants():
    with pytest.raises(TutorialRecordError, match="default_variant"):
        _record(default_variant="variantA")


# ---------------------------------------------------------------------------
# Unchanged reporting
# ---------------------------------------------------------------------------


def test_split_unchanged_separates_changed_from_unchanged():
    def reader(document_path, key_path):
        # Contract: key_path is always a tuple, as a real reader expects.
        assert isinstance(key_path, tuple)
        return {"cells": "5", "modelName": "modelAlpha"}.get(key_path[-1])

    patches = [
        SourcedPatch(patch=AxisPatch("constant/mesh.json", ("cells",), 5, "integer"), source="sweep", validated=True),
        SourcedPatch(patch=AxisPatch("constant/physics.json", ("modelName",), "modelBeta", "word"), source="base", validated=True),
    ]
    to_write, unchanged = split_unchanged(
        patches, case_root=Path("/whatever"),
        read_current_value=reader, values_agree=_typed_agree,
    )
    assert [p.patch.value for p in unchanged] == [5]
    assert [p.patch.value for p in to_write] == ["modelBeta"]


def test_split_unchanged_treats_an_undeterminable_patch_as_changed():
    """No reader/comparator (an adapter that declares neither): nothing is ever silently reported unchanged."""
    patches = [SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), 1, "integer"), source="base", validated=True)]
    to_write, unchanged = split_unchanged(
        patches, case_root=Path("/whatever"), read_current_value=None, values_agree=None,
    )
    assert to_write == tuple(patches)
    assert unchanged == ()


# ---------------------------------------------------------------------------
# The validated flag: carried into ParameterAssignment and the commit's record
# ---------------------------------------------------------------------------


def test_patches_to_parameters_carries_the_validated_flag_through():
    patches = [
        SourcedPatch(patch=AxisPatch("constant/a.json", ("k",), "v", "word"), source="base", validated=True),
        SourcedPatch(patch=AxisPatch("system/unowned.json", ("endTime",), 0.02, "scalar"), source="base", validated=False),
    ]
    parameters = patches_to_parameters(patches, owner="org.test")
    assert isinstance(parameters[0], ParameterAssignment)
    assert parameters[0].validated is True
    assert parameters[1].validated is False


def test_parameter_assignment_validated_is_tri_state():
    """`None` means "not stated", distinct from `False` ("checked, and found unvalidated")."""
    def assignment(validated):
        return ParameterAssignment(
            qualified_id="q", owner="org.a", document="constant/a", key_path=("k",),
            value=1.0, value_kind="scalar", source="case", validated=validated,
        )

    assert ParameterAssignment(
        qualified_id="q", owner="org.a", document="constant/a", key_path=("k",),
        value=1.0, value_kind="scalar", source="case",
    ).validated is None
    assert assignment(False).validated is False
    assert assignment(True).validated is True


def test_parameter_assignment_refuses_a_string_for_validated():
    """Type-checked (task's own wording): the STRING "false" must be refused, not silently accepted as a truthy non-empty string."""
    with pytest.raises((TypeError, ValueError)):
        ParameterAssignment(
            qualified_id="q", owner="org.a", document="constant/a", key_path=("k",),
            value=1.0, value_kind="scalar", source="case",
            validated="false",
        )


# ---------------------------------------------------------------------------
# Resolving a record by name
# ---------------------------------------------------------------------------


def test_lookup_record_resolves_a_registered_name_case_insensitively():
    record = _record()
    context = driver_context(ToyProvider(tutorial_records={"toyTutorial": record}), source="test:records")

    assert lookup_record("toyTutorial", driver_context=context) is record
    assert lookup_record(" TOYTUTORIAL ", driver_context=context) is record
    assert lookup_record(record, driver_context=context) is record


def test_lookup_record_refuses_an_unregistered_name_listing_the_registered_ones():
    context = driver_context(ToyProvider(tutorial_records={"toyTutorial": _record()}), source="test:records")

    with pytest.raises(TutorialRecordError, match=r"unknown tutorial record 'natives/toy'.*toyTutorial"):
        lookup_record("natives/toy", driver_context=context)


def test_describe_entry_previews_a_tutorial_record_instead_of_refusing(tmp_path):
    """describe_entry gives a record a real preview through record_execution.preview_record_case."""
    from omnidriver.core.introspection import describe_entry

    _native_case(tmp_path, {
        "constant/physics.json": {"modelName": "modelAlpha"},
        "constant/mesh.json": {"cells": "5"},
    })
    record = _record()
    plugin = _RecordCaseWriterPlugin(
        tutorial_records={"toyTutorial": record},
        record_key_validator=_known_catalog_validator,
    )
    context = driver_context(plugin, source="test:describe-record")

    described = describe_entry(
        "toyTutorial",
        overrides={
            "cases_root": str(tmp_path / "cases"),
            "constant/physics.json:modelName": "modelBeta",
            "number_cells": 5,
        },
        driver_context=context,
    )
    assert described["entry"] == {"entry_name": "toyTutorial", "entry_path": record.native_case_relpath}
    assert described["records"] == ["toyTutorial"]
    preview = described["record_preview"]
    by_document = {p["document"]: p for p in preview["patches"]}
    assert by_document["constant/physics.json"]["value"] == "modelBeta"
    assert by_document["constant/physics.json"]["status"] == "changed"
    assert by_document["constant/physics.json"]["validated"] is True
    assert by_document["constant/mesh.json"]["status"] == "unchanged"
    assert preview["command_arguments"]["mesh"] == ["-N", "5"]


def test_describe_entry_refuses_a_tutorial_record_preview_without_cases_root(tmp_path):
    """No `Path.cwd()` default -- a case root has no ambient truth (CLAUDE.md's "supplied versus discovered")."""
    from omnidriver.core.introspection import describe_entry

    record = _record()
    plugin = _RecordCaseWriterPlugin(
        tutorial_records={"toyTutorial": record},
        record_key_validator=_known_catalog_validator,
    )
    context = driver_context(plugin, source="test:describe-record-no-root")

    with pytest.raises(TutorialRecordError, match="cases_root"):
        describe_entry("toyTutorial", overrides={}, driver_context=context)


# ---------------------------------------------------------------------------
# Full pipeline: preview and commit against a real staged case
# ---------------------------------------------------------------------------


def _context_with_writer(tutorial_records=None):
    plugin = _RecordCaseWriterPlugin(
        tutorial_records=tutorial_records or {},
        record_key_validator=_known_catalog_validator,
    )
    return driver_context(plugin, source="test:pipeline")


def test_preview_record_case_lists_each_patch_with_status_and_validated(tmp_path):
    _native_case(tmp_path, {
        "constant/physics.json": {"modelName": "modelAlpha"},
        "constant/mesh.json": {"cells": "5"},
    })
    record = _record()
    context = _context_with_writer()

    preview = record_execution.preview_record_case(
        record,
        cases_root=tmp_path / "cases",
        study_by_source={
            "base": {"constant/physics.json:modelName": "modelBeta"},
            "sweep": {"number_cells": 5},
        },
        driver_context=context,
    )
    by_document = {p["document"]: p for p in preview["patches"]}
    assert by_document["constant/physics.json"]["status"] == "changed"
    assert by_document["constant/physics.json"]["validated"] is True
    assert by_document["constant/mesh.json"]["status"] == "unchanged"
    assert preview["command_arguments"]["mesh"] == ["-N", "5"]


def test_preview_record_case_ignores_sweep_naming_output_keys(tmp_path):
    """`caseId`/`output_dir_name` (sweep.dependent's own naming derivations) are sweep-naming bookkeeping, never case content and never an axis -- they must not reach `sort_study_name` and be refused as an unrecognized bare name."""
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "1"}})
    record = _record()
    context = _context_with_writer()

    preview = record_execution.preview_record_case(
        record,
        cases_root=tmp_path / "cases",
        study_by_source={
            "base": {},
            "sweep": {
                "number_cells": 5,
                "caseId": "case_0001",
                "output_dir_name": "case_0001",
            },
        },
        driver_context=context,
    )
    documents = {p["document"] for p in preview["patches"]}
    assert documents == {"constant/mesh.json"}


def test_extract_reserved_names_refuses_a_conflicting_value_across_sources():
    """`reserved_conflict_later_wins` mutation: two sources naming the SAME reserved name with different values must be refused, never silently resolved by "later source wins"."""
    from omnidriver.core.runtime.record_execution import _extract_reserved_names

    with pytest.raises(TutorialRecordError, match="caseId"):
        _extract_reserved_names(
            {"base": {"caseId": 1}, "sweep": {"caseId": True}},
            reserved_names=frozenset({"caseId"}),
        )


def test_extract_reserved_names_allows_the_same_value_restated_across_sources():
    from omnidriver.core.runtime.record_execution import _extract_reserved_names

    stripped, reserved = _extract_reserved_names(
        {"base": {"caseId": "case_0001"}, "sweep": {"caseId": "case_0001", "x": 1}},
        reserved_names=frozenset({"caseId"}),
    )
    assert reserved == {"caseId": "case_0001"}
    assert stripped == {"base": {}, "sweep": {"x": 1}}


# ---------------------------------------------------------------------------
# The `mesh` selector, wired end to end through preview/commit
# ---------------------------------------------------------------------------


def _record_with_variants(**overrides) -> TutorialRecord:
    fields = dict(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        axes=(),
        workflow_steps=(
            WorkflowStep(step_id="meshA", command=("toolA",)),
            WorkflowStep(step_id="meshB", command=("toolB",)),
            WorkflowStep(step_id="solve", command=("solverBinary",)),
        ),
        workflow_variants={
            "variantA": ("meshA", "solve"),
            "variantB": ("meshB", "solve"),
        },
        variant_selector="mesh",
        default_variant="variantA",
    )
    fields.update(overrides)
    return TutorialRecord(**fields)


def test_preview_record_case_reports_the_selected_variants_steps(tmp_path):
    _native_case(tmp_path, {})
    record = _record_with_variants()
    context = _context_with_writer()

    preview = record_execution.preview_record_case(
        record,
        cases_root=tmp_path / "cases",
        study_by_source={"base": {"mesh": "variantB"}},
        driver_context=context,
    )
    assert preview["workflow_step_ids"] == ["meshB", "solve"]
    assert preview["workflow_variant"] == {
        "selector": "mesh", "selected": "variantB", "source": "study",
        "default": "variantA", "declared": ["variantA", "variantB"],
    }


def test_preview_record_case_refuses_an_unknown_mesh_variant(tmp_path):
    _native_case(tmp_path, {})
    record = _record_with_variants()
    context = _context_with_writer()
    with pytest.raises(TutorialRecordError, match="unknownVariant"):
        record_execution.preview_record_case(
            record,
            cases_root=tmp_path / "cases",
            study_by_source={"base": {"mesh": "unknownVariant"}},
            driver_context=context,
        )


def test_preview_record_case_runs_the_default_variant_when_the_study_names_none(tmp_path):
    """A record with routes runs its default variant when the study names none."""
    _native_case(tmp_path, {})
    record = _record_with_variants()
    context = _context_with_writer()
    preview = record_execution.preview_record_case(
        record,
        cases_root=tmp_path / "cases",
        study_by_source={"base": {}},
        driver_context=context,
    )
    assert preview["workflow_step_ids"] == ["meshA", "solve"]
    assert preview["workflow_variant"] == {
        "selector": "mesh", "selected": "variantA", "source": "default",
        "default": "variantA", "declared": ["variantA", "variantB"],
    }


def test_preview_record_case_refuses_a_null_selector_rather_than_defaulting(tmp_path):
    """A study that names the selector with a null value made a choice that is not a route; it is refused, never read as "no choice" and defaulted."""
    _native_case(tmp_path, {})
    record = _record_with_variants()
    context = _context_with_writer()
    with pytest.raises(TutorialRecordError, match="null"):
        record_execution.preview_record_case(
            record,
            cases_root=tmp_path / "cases",
            study_by_source={"base": {"mesh": None}},
            driver_context=context,
        )


def test_preview_of_a_record_without_variants_reports_no_variant(tmp_path):
    _native_case(tmp_path, {})
    preview = record_execution.preview_record_case(
        _record(axes=()), cases_root=tmp_path / "cases",
        study_by_source={"base": {}}, driver_context=_context_with_writer(),
    )
    assert preview["workflow_variant"] is None


def test_commit_record_case_runs_the_default_variant_when_the_study_names_none(tmp_path):
    _native_case(tmp_path, {})
    result = record_execution.commit_record_case(
        _record_with_variants(),
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={"base": {}},
        driver_context=_context_with_writer(),
    )
    assert result.workflow_step_ids == ("meshA", "solve")


def test_commit_record_case_reports_the_selected_variants_steps(tmp_path):
    _native_case(tmp_path, {})
    record = _record_with_variants()
    context = _context_with_writer()

    result = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"mesh": "variantA"}},
        driver_context=context,
    )
    assert result.workflow_step_ids == ("meshA", "solve")


# ---------------------------------------------------------------------------
# A contribution to a step the selected route does not run is refused by name.
# ---------------------------------------------------------------------------


def _meshA_axis() -> AxisContract:
    """A toy axis whose only effect is a command argument for ``meshA``, a step only ``variantA`` runs."""
    def resolve(value, staged_case_root: Path) -> AxisResult:
        del staged_case_root
        return AxisResult(command_arguments={"meshA": ("--cells", str(value))})

    return AxisContract(name="number_cells", value_kind="integer", resolve=resolve)


def _preview(tmp_path, study):
    _native_case(tmp_path, {})
    return record_execution.preview_record_case(
        _record_with_variants(axes=(_meshA_axis(),)), cases_root=tmp_path / "cases",
        study_by_source={"base": study}, driver_context=_context_with_writer(),
    )


def test_an_axis_for_a_step_the_selected_route_does_not_run_is_refused(tmp_path):
    with pytest.raises(TutorialRecordError) as exc:
        _preview(tmp_path, {"mesh": "variantB", "number_cells": 7})
    message = str(exc.value)
    for fragment in ("'number_cells'", "'meshA'", "'toyTutorial'", "['meshB', 'solve']"):
        assert fragment in message, (fragment, message)


def test_an_axis_that_also_writes_the_case_is_not_refused_for_a_step_the_route_skips(tmp_path):
    def resolve(value, staged_case_root: Path) -> AxisResult:
        del staged_case_root
        return AxisResult(
            patches=(AxisPatch(
                document="constant/mesh.json", key_path=("cells",), value=int(value), value_kind="integer",
            ),),
            command_arguments={"meshA": ("--cells", str(value))},
        )

    _native_case(tmp_path, {"constant/mesh.json": {"cells": "5"}})
    preview = record_execution.preview_record_case(
        _record_with_variants(axes=(AxisContract(name="number_cells", value_kind="integer", resolve=resolve),)),
        cases_root=tmp_path / "cases", study_by_source={"base": {"mesh": "variantB", "number_cells": 7}},
        driver_context=_context_with_writer(),
    )
    assert preview["workflow_step_ids"] == ["meshB", "solve"]
    assert preview["workflow_commands"]["meshB"] == ["toolB"]


def test_an_axis_for_a_step_the_default_route_runs_is_admitted(tmp_path):
    preview = _preview(tmp_path, {"number_cells": 7})
    assert preview["command_arguments"] == {"meshA": ["--cells", "7"]}


def test_the_refusal_comes_before_a_commit_writes_anything(tmp_path):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "5"}})
    with pytest.raises(TutorialRecordError, match="'number_cells'"):
        record_execution.commit_record_case(
            _record_with_variants(axes=(_meshA_axis(),)), cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"mesh": "variantB", "number_cells": 7}},
            driver_context=_context_with_writer(),
        )
    staged_mesh = tmp_path / "staged" / "constant" / "mesh.json"
    assert not staged_mesh.exists() or json.loads(staged_mesh.read_text()) == {"cells": "5"}


# ---------------------------------------------------------------------------
# The resolved case passes the stack's rules before anything runs.
# ---------------------------------------------------------------------------


class _RuleCheckingPlugin(_RecordCaseWriterPlugin):
    """A stack whose one rule says a case holds at most 10 cells, and warns above 5."""

    def validate_run_semantics(self, case_root):
        cells = json.loads((Path(case_root) / "constant" / "mesh.json").read_text())["cells"]
        found = []
        if int(cells) > 10:
            found.append(diagnostic("error", "too_many_cells", f"{cells} cells exceed 10", field="cells"))
        if int(cells) > 5:
            found.append(diagnostic("warning", "many_cells", f"{cells} cells", field="cells"))
        return tuple(found)


def _commit(tmp_path, cells):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": str(cells)}})
    return record_execution.commit_record_case(
        _record(), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"number_cells": 7}},
        driver_context=driver_context(
            _RuleCheckingPlugin(tutorial_records={}, record_key_validator=_known_catalog_validator),
            source="test:rules",
        ),
    )


def test_a_resolved_case_that_breaks_a_rule_is_refused_with_the_rules_own_message(tmp_path):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "5"}})
    with pytest.raises(TutorialRecordError) as exc:
        record_execution.commit_record_case(
            _record(), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"number_cells": 12}},
            driver_context=driver_context(
                _RuleCheckingPlugin(tutorial_records={}, record_key_validator=_known_catalog_validator),
                source="test:rules",
            ),
        )
    message = str(exc.value)
    for fragment in ("'toyTutorial'", "cells: 12 cells exceed 10"):
        assert fragment in message, (fragment, message)
    assert "many_cells" not in message


def test_a_warning_does_not_refuse_the_case(tmp_path):
    assert _commit(tmp_path, 5).status == "committed"


def test_an_unchanged_case_is_checked_too(tmp_path):
    """A case that needs no patch is the native case as it stands, and the rules judge it all the same."""
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "12"}})
    with pytest.raises(TutorialRecordError, match="12 cells exceed 10"):
        record_execution.commit_record_case(
            _record(), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
            study_by_source={"base": {}},
            driver_context=driver_context(
                _RuleCheckingPlugin(tutorial_records={}, record_key_validator=_known_catalog_validator),
                source="test:rules",
            ),
        )


def test_an_applied_edit_that_breaks_a_rule_is_refused_and_rolled_back(tmp_path):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "5"}})
    context = driver_context(
        _RuleCheckingPlugin(tutorial_records={}, record_key_validator=_known_catalog_validator),
        source="test:rules",
    )
    record_execution.commit_record_case(
        _record(), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
        study_by_source={"base": {}}, driver_context=context,
    )
    with acquire_case_lease(tmp_path / "staged"), pytest.raises(
        TutorialRecordError, match="12 cells exceed 10.*as it was before the edit",
    ):
        record_execution.apply_record_study(
            _record(), case_root=tmp_path / "staged",
            study={"constant/mesh.json:cells": 12}, driver_context=context,
        )
    assert json.loads((tmp_path / "staged" / "constant" / "mesh.json").read_text())["cells"] == "5"


def test_commit_record_case_writes_one_case_with_validated_flags_in_the_record(tmp_path):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = _context_with_writer()

    result = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={
            "base": {
                "constant/physics.json:modelName": "modelBeta",
                "system/unowned.json:endTime": 0.02,
            },
        },
        driver_context=context,
    )
    assert result.status == "committed"
    assert result.unchanged == ()
    write_record = result.write_record
    assert write_record is not None
    by_qualified_id = {p.qualified_id: p for p in write_record.parameters}
    assert by_qualified_id["constant/physics.json::modelName"].validated is True
    assert by_qualified_id["system/unowned.json::endTime"].validated is False
    # The owner is the provider that resolves the stack's mutations.
    assert (
        by_qualified_id["constant/physics.json::modelName"].owner
        == context.identity.resolutions["resolve_case_mutation"]
    )
    written = json.loads((tmp_path / "staged" / "constant" / "physics.json").read_text())
    assert written["modelName"] == "modelBeta"


def test_a_renderer_refusal_names_the_document_by_its_case_path_not_the_render_scratch(tmp_path, monkeypatch):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})

    def refuse(driver_context, resolved, *, snapshot_root, execution_env):
        raise CaseKeyNotFound(f"Key 'modelNme' not found in {snapshot_root}/constant/physics.json")

    monkeypatch.setattr(record_execution, "render_mutation", refuse)
    with pytest.raises(TutorialRecordError) as excinfo:
        record_execution.commit_record_case(
            _record(axes=()), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"constant/physics.json:modelName": "modelBeta"}},
            driver_context=_context_with_writer(),
        )
    message = str(excinfo.value)
    assert "Key 'modelNme' not found in constant/physics.json" in message
    assert "omnidriver-record-render" not in message


def test_a_key_error_that_is_not_the_writers_lookup_miss_is_a_defect_and_propagates(tmp_path, monkeypatch):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})

    def defect(driver_context, resolved, *, snapshot_root, execution_env):
        raise KeyError("a bug in a renderer")

    monkeypatch.setattr(record_execution, "render_mutation", defect)
    with pytest.raises(KeyError, match="a bug in a renderer") as excinfo:
        record_execution.commit_record_case(
            _record(axes=()), cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"constant/physics.json:modelName": "modelBeta"}},
            driver_context=_context_with_writer(),
        )
    assert not isinstance(excinfo.value, TutorialRecordError)


def test_commit_record_case_preserves_sibling_keys_in_a_multi_key_document(tmp_path):
    """The renderer reads the case's existing documents from `snapshot_root`, so a patch to one key keeps its siblings."""
    _native_case(tmp_path, {
        "constant/mesh.json": {"cells": "1", "material": "myocardium"},
    })
    record = _record()
    context = _context_with_writer()

    result = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={"base": {}, "sweep": {"number_cells": 7}},
        driver_context=context,
    )

    assert result.status == "committed"
    written = json.loads((tmp_path / "staged" / "constant" / "mesh.json").read_text())
    assert written["cells"] == "7"
    assert written["material"] == "myocardium"


def test_commit_record_case_writes_nothing_when_every_patch_is_unchanged(tmp_path):
    """The result states "everything was unchanged" explicitly, with the unchanged patches, rather than a bare None."""
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = _context_with_writer()

    result = record_execution.commit_record_case(
        record,
        cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged",
        study_by_source={"base": {"constant/physics.json:modelName": "modelAlpha"}},
        driver_context=context,
    )
    assert result.write_record is None
    assert result.status == "unchanged"
    assert [p.patch.value for p in result.unchanged] == ["modelAlpha"]


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
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = _context_with_writer()
    with pytest.raises(TutorialRecordError):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={
                "base": {"constant/physics.json:modelName": "modelBeta"},
                "sweep": {"constant/physics.json:modelName": "modelAlpha"},
            },
            driver_context=context,
        )


# ---------------------------------------------------------------------------
# A stack with no key validator, value comparator or config reader REFUSES a
# record case rather than running it unchecked (or reporting every no-op as
# "changed").
# ---------------------------------------------------------------------------


class _NoValidatorPlugin(_RecordCaseWriterPlugin):
    get_record_key_validator = None


class _NoComparatorPlugin(_RecordCaseWriterPlugin):
    get_case_value_comparator = None


class _NoReaderPlugin(_RecordCaseWriterPlugin):
    get_config_value_reader = None


def test_commit_record_case_refuses_when_the_stack_has_no_record_key_validator(tmp_path):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = driver_context(_NoValidatorPlugin(), source="test:no-validator")
    with pytest.raises(TutorialRecordError, match="get_record_key_validator"):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"constant/physics.json:modelName": "modelBeta"}},
            driver_context=context,
        )


def test_preview_record_case_refuses_when_the_stack_has_no_record_key_validator(tmp_path):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = driver_context(_NoValidatorPlugin(), source="test:no-validator")
    with pytest.raises(TutorialRecordError, match="get_record_key_validator"):
        record_execution.preview_record_case(
            record,
            cases_root=tmp_path / "cases",
            study_by_source={"base": {"constant/physics.json:modelName": "modelBeta"}},
            driver_context=context,
        )


def test_commit_record_case_refuses_when_the_stack_has_no_case_value_comparator(tmp_path):
    """Without a comparator every patch, including a genuine no-op, would be reported 'changed' and committed."""
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = driver_context(
        _NoComparatorPlugin(record_key_validator=_known_catalog_validator),
        source="test:no-comparator",
    )
    with pytest.raises(TutorialRecordError, match="get_case_value_comparator"):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"constant/physics.json:modelName": "modelAlpha"}},
            driver_context=context,
        )


def test_commit_record_case_refuses_when_the_stack_has_no_config_value_reader(tmp_path):
    """Without a reader every patch would be reported "changed" and committed."""
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = driver_context(
        _NoReaderPlugin(record_key_validator=_known_catalog_validator),
        source="test:no-reader",
    )
    with pytest.raises(TutorialRecordError, match="get_config_value_reader"):
        record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "staged",
            study_by_source={"base": {"constant/physics.json:modelName": "modelAlpha"}},
            driver_context=context,
        )


def test_preview_record_case_refuses_when_the_stack_has_no_config_value_reader(tmp_path):
    _native_case(tmp_path, {"constant/physics.json": {"modelName": "modelAlpha"}})
    record = _record(axes=())
    context = driver_context(
        _NoReaderPlugin(record_key_validator=_known_catalog_validator),
        source="test:no-reader",
    )
    with pytest.raises(TutorialRecordError, match="get_config_value_reader"):
        record_execution.preview_record_case(
            record,
            cases_root=tmp_path / "cases",
            study_by_source={"base": {"constant/physics.json:modelName": "modelAlpha"}},
            driver_context=context,
        )


# ---------------------------------------------------------------------------
# `strict_plan` handles a tutorial_record resolution directly (stage + commit +
# spec, the same shared sequence a sweep case uses). The CLI end-to-end path
# lives in `test_cli_plan_strict_tutorial_record.py`; these are the direct,
# in-process unit tests of `strict_plan` itself.
# ---------------------------------------------------------------------------


def test_strict_plan_over_a_tutorial_record_refuses_without_cases_root():
    """A record has no ambient cases root (CLAUDE.md's "supplied versus discovered") -- the same refusal `sweep_runner._sweep_record` already raises for a swept record."""
    from omnidriver.core.strict_planning import strict_plan

    record = _record()
    context = _context_with_writer(
        tutorial_records={"toyTutorial": record},
    )
    with pytest.raises(TutorialRecordError, match="cases_root"):
        strict_plan("toyTutorial", driver_context=context)


def test_strict_plan_over_a_tutorial_record_commits_and_plans_with_a_working_run_document(
    tmp_path,
):
    """`plan --strict --entry <record>`'s own pipeline, in process: commits the record's case (the same thing `sweep-plan` over a record entry already does at plan time), and persists a `run_document.json` at the exact path its own advertised `run --run-document <path>` command names."""
    from omnidriver.core.plugin_interface import driver_context as _dc
    from omnidriver.core.strict_planning import strict_plan
    from plugins.toy import ToyStack

    native = tmp_path / "cases" / "toyTutorial" / "constant"
    native.mkdir(parents=True)
    (native / "mesh.json").write_text(json.dumps({"cells": "1"}))
    context = _dc(ToyStack(), source="test:strict-plan-record")

    report = strict_plan(
        "toyTutorial",
        overrides={
            "cases_root": str(tmp_path / "cases"),
            "constant/mesh.json:cells": 7,
        },
        scratch_root=tmp_path / "scratch",
        driver_context=context,
    )

    assert report.status == "ok", report.to_json()
    command = report.launch["command"]
    assert "--run-document" in command
    assert "--strict" not in command
    run_document_path = Path(command[command.index("--run-document") + 1])
    assert run_document_path.is_file()
    persisted = json.loads(run_document_path.read_text())
    assert persisted == report.run_document.to_json()
    case_root = Path(report.launch["case_root"])
    assert json.loads((case_root / "constant" / "mesh.json").read_text())["cells"] == "7"


# ---------------------------------------------------------------------------
# A sweep over a record entry: one commit per case
# ---------------------------------------------------------------------------


def test_a_sweep_over_a_record_entry_produces_one_commit_per_case(tmp_path):
    _native_case(tmp_path, {"constant/mesh.json": {"cells": "1"}})
    record = _record()
    context = _context_with_writer()

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
        result = record_execution.commit_record_case(
            record,
            cases_root=tmp_path / "cases",
            staged_case_root=tmp_path / "sweep_cases" / case.case_id,
            study_by_source={"base": sweep_spec["base"], "sweep": case.resolved_axis_values},
            driver_context=context,
        )
        assert result.write_record is not None
        committed.append(result.write_record)

    assert all(r.committed for r in committed)
    cells_by_case = {
        case.case_id: json.loads(
            (tmp_path / "sweep_cases" / case.case_id / "constant" / "mesh.json").read_text()
        )["cells"]
        for case in resolved_cases
    }
    assert cells_by_case == {"case_0001": "2", "case_0002": "3"}


# ---------------------------------------------------------------------------
# record_case_spec: mapping a committed record case onto the same
# workflow_dag shape a factory tutorial's spec carries.
# ---------------------------------------------------------------------------


def test_record_case_spec_builds_the_generic_workflow_dag_shape(tmp_path):
    record = TutorialRecord(
        name="toyTutorial",
        native_case_relpath="toyTutorial",
        axes=(),
        workflow_steps=(
            WorkflowStep(step_id="mesh", command=("toolA", "-dict")),
            WorkflowStep(step_id="solve", command=("solverBinary",)),
        ),
    )
    staged = tmp_path / "case"
    staged.mkdir()
    spec = record_execution.record_case_spec(
        record,
        case_id="case_0001",
        staged_case_root=staged,
        workflow_step_ids=("mesh", "solve"),
        command_arguments={"mesh": ("-N", "20")},
    )
    assert spec.name == "case_0001"
    assert spec.case_root == staged
    assert spec.metadata["entry_name"] == "toyTutorial"
    workflow_dag = spec.metadata["workflow_dag"]
    assert workflow_dag == {
        "steps": [
            {
                "id": "mesh", "command": "toolA", "args": ["-dict", "-N", "20"],
                "depends_on": [], "produces": [], "consumes": [],
            },
            {
                "id": "solve", "command": "solverBinary", "args": [],
                "depends_on": ["mesh"], "produces": [], "consumes": [],
            },
        ]
    }


# ---------------------------------------------------------------------------
# build_tutorial_record_catalog: a plugin's TUTORIAL_RECORDS is a reduction
# of a tuple of records to a name -> record dict, and a plain dict
# comprehension silently drops a duplicate name. This is the same guard
# TutorialRecord.__post_init__ already gives two axes sharing a name inside
# one record, applied across a plugin's own record tuple.
# ---------------------------------------------------------------------------


def test_build_tutorial_record_catalog_keys_by_name():
    first = _record(name="alpha", native_case_relpath="alpha")
    second = _record(name="beta", native_case_relpath="beta")
    catalog = build_tutorial_record_catalog((first, second))
    assert catalog == {"alpha": first, "beta": second}


def test_build_tutorial_record_catalog_refuses_a_duplicate_name():
    first = _record(name="dup", native_case_relpath="caseOne")
    second = _record(name="dup", native_case_relpath="caseTwo")
    with pytest.raises(TutorialRecordError, match="duplicate tutorial record name 'dup'"):
        build_tutorial_record_catalog((first, second))


def test_a_catalog_gives_each_record_its_conformance_study_and_refuses_a_stranger(tmp_path):
    from omnidriver.core.conformance_study import ConformanceStudy

    study = ConformanceStudy(
        base_study={}, patch=("a:b", 1), untouched=("a", ("c",)), sweep_name="n", sweep_values=(1, 2), unknown_name="x",
    )
    catalog = build_tutorial_record_catalog((_record(),), conformance={"toyTutorial": study})
    assert catalog["toyTutorial"].conformance is study
    with pytest.raises(TutorialRecordError, match="no record of this catalog"):
        build_tutorial_record_catalog((_record(),), conformance={"other": study})
