"""Supplied inputs for a tutorial record."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.case_write import RenderedFile, ResolvedMutation, _digest_bytes
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime import record_execution
from omnidriver.core.tutorial_records import (
    RecordInput,
    RecordInputError,
    RecordInputIncomplete,
    RecordInputNotSupplied,
    TutorialRecord,
    TutorialRecordError,
    WorkflowStep,
    resolve_record_inputs,
)

from plugins.toy import ToyProvider

_FORMAT = "test_record_input_json"


# ---------------------------------------------------------------------------
# RecordInput / TutorialRecord.inputs: shape and cross-step refusals (§2.1)
# ---------------------------------------------------------------------------


def _step(**overrides) -> WorkflowStep:
    fields = dict(step_id="solve", command=("touch", "marker"), consumes=("0/bundle.json",))
    fields.update(overrides)
    return WorkflowStep(**fields)


def test_record_input_refuses_an_empty_name():
    with pytest.raises(TutorialRecordError, match="non-empty"):
        RecordInput(name="", files=(("a", "0/a"),))


def test_record_input_refuses_empty_files():
    with pytest.raises(TutorialRecordError, match="at least one file"):
        RecordInput(name="anatomy", files=())


def test_record_input_refuses_a_bare_string_for_files():
    with pytest.raises(TutorialRecordError, match="bare string"):
        RecordInput(name="anatomy", files="0/a")


def test_record_input_refuses_an_absolute_destination():
    with pytest.raises(ValueError, match="absolute"):
        RecordInput(name="anatomy", files=(("a", "/etc/passwd"),))


def test_record_input_refuses_a_destination_that_escapes_the_case():
    with pytest.raises(ValueError, match="escape"):
        RecordInput(name="anatomy", files=(("a", "../outside"),))


def test_record_input_refuses_the_case_root_as_a_destination():
    with pytest.raises(TutorialRecordError, match="case root"):
        RecordInput(name="anatomy", files=((".", "."),))


def test_record_input_refuses_curly_braces_in_a_destination():
    with pytest.raises(TutorialRecordError, match=r"\{"):
        RecordInput(name="anatomy", files=(("a", "0/{case_id}"),))


def test_record_input_accepts_a_dot_source_as_the_input_itself():
    record_input = RecordInput(name="graph", files=((".", "constant/graph"),))
    assert record_input.destinations() == ("constant/graph",)


def test_a_record_refuses_two_inputs_with_the_same_name():
    inp = RecordInput(name="anatomy", files=(("a", "0/a"),))
    with pytest.raises(TutorialRecordError, match="twice"):
        TutorialRecord(
            name="r", native_case_relpath="r", inputs=(inp, inp),
            workflow_steps=(_step(consumes=("0/a",)),),
        )


def test_a_record_refuses_a_destination_no_step_consumes():
    inp = RecordInput(name="anatomy", files=(("a", "0/a"),))
    with pytest.raises(TutorialRecordError, match="not consumed"):
        TutorialRecord(
            name="r", native_case_relpath="r", inputs=(inp,),
            workflow_steps=(_step(consumes=(), produces=()),),
        )


def test_a_record_refuses_a_destination_produced_before_it_is_consumed():
    """The destination would be generated, not supplied (design §2.1)."""
    inp = RecordInput(name="anatomy", files=(("a", "0/a"),))
    with pytest.raises(TutorialRecordError, match="produced by step"):
        TutorialRecord(
            name="r", native_case_relpath="r", inputs=(inp,),
            workflow_steps=(
                _step(step_id="gen", command=("touch", "0/a"), consumes=(), produces=("0/a",)),
                _step(step_id="use", command=("touch", "marker"), consumes=("0/a",), produces=()),
            ),
        )


def test_a_record_allows_a_step_that_both_produces_and_consumes_a_destination_in_place():
    """A step rewriting its own input in place (setPurkinjeSlab's Conductivity pattern) still counts as consumed-first."""
    inp = RecordInput(name="anatomy", files=(("a", "0/a"),))
    record = TutorialRecord(
        name="r", native_case_relpath="r", inputs=(inp,),
        workflow_steps=(_step(step_id="rewrite", command=("touch", "0/a"), consumes=("0/a",), produces=("0/a",)),),
    )
    assert record.inputs[0].name == "anatomy"


def test_a_record_refuses_two_inputs_with_overlapping_destinations():
    mesh = RecordInput(name="mesh", files=(("m", "constant/polyMesh"),))
    fiber = RecordInput(name="fiber", files=(("f", "constant/polyMesh/boundary"),))
    with pytest.raises(TutorialRecordError, match="overlap"):
        TutorialRecord(
            name="r", native_case_relpath="r", inputs=(mesh, fiber),
            workflow_steps=(_step(consumes=("constant/polyMesh/boundary",)),),
        )


def test_a_directory_destination_is_consumed_when_a_step_consumes_a_path_under_it():
    """The idealized-heart mesh shape (§3): one input pair names a whole directory; steps consume individual files under it."""
    mesh = RecordInput(name="mesh", files=(("m", "constant/polyMesh"),))
    record = TutorialRecord(
        name="r", native_case_relpath="r", inputs=(mesh,),
        workflow_steps=(_step(consumes=("constant/polyMesh/boundary", "constant/polyMesh/points")),),
    )
    assert record.inputs[0].destinations() == ("constant/polyMesh",)


# ---------------------------------------------------------------------------
# resolve_record_inputs (§2.2): supplied wins; else native; else refused (strict)
# ---------------------------------------------------------------------------


def _anatomy_record(*, native_relpath: str | None = None) -> TutorialRecord:
    return TutorialRecord(
        name="humanSlabToy", native_case_relpath="humanSlabToy",
        inputs=(RecordInput(name="anatomy", files=(("fiber", "0/fiber"),), native_relpath=native_relpath),),
        workflow_steps=(_step(consumes=("0/fiber",)),),
    )


def test_resolve_record_inputs_refuses_an_unknown_input_name(tmp_path):
    record = _anatomy_record()
    with pytest.raises(RecordInputError, match="does not declare"):
        resolve_record_inputs(record, {"bogus": str(tmp_path)}, cases_root=tmp_path)


def test_resolve_record_inputs_refuses_when_nothing_is_supplied_and_there_is_no_native_location(tmp_path):
    record = _anatomy_record()
    with pytest.raises(RecordInputNotSupplied, match="anatomy"):
        resolve_record_inputs(record, {}, cases_root=tmp_path)


def test_resolve_record_inputs_refuses_an_incomplete_supplied_directory(tmp_path):
    record = _anatomy_record()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    with pytest.raises(RecordInputIncomplete, match="fiber"):
        resolve_record_inputs(record, {"anatomy": str(bundle)}, cases_root=tmp_path)


def test_resolve_record_inputs_prefers_a_supplied_path_over_the_native_one(tmp_path):
    record = _anatomy_record(native_relpath="native-bundle")
    native = tmp_path / "native-bundle"
    native.mkdir()
    (native / "fiber").write_text("native")
    supplied = tmp_path / "supplied-bundle"
    supplied.mkdir()
    (supplied / "fiber").write_text("supplied")

    resolved = resolve_record_inputs(record, {"anatomy": str(supplied)}, cases_root=tmp_path)
    assert len(resolved) == 1
    assert resolved[0].kind == "supplied"
    assert resolved[0].path == supplied


def test_resolve_record_inputs_uses_the_native_location_when_nothing_is_supplied(tmp_path):
    record = _anatomy_record(native_relpath="native-bundle")
    native = tmp_path / "native-bundle"
    native.mkdir()
    (native / "fiber").write_text("native")

    resolved = resolve_record_inputs(record, {}, cases_root=tmp_path)
    assert resolved[0].kind == "native"
    assert resolved[0].path == native


def test_resolve_record_inputs_non_strict_skips_an_unresolvable_input_rather_than_raising(tmp_path):
    """describe's own posture (§2.2): "describe does not refuse"."""
    record = _anatomy_record()
    resolved = resolve_record_inputs(record, {}, cases_root=tmp_path, strict=False)
    assert resolved == ()


def test_resolve_record_inputs_non_strict_still_refuses_an_unknown_name(tmp_path):
    record = _anatomy_record()
    with pytest.raises(RecordInputError):
        resolve_record_inputs(record, {"bogus": "x"}, cases_root=tmp_path, strict=False)


# ---------------------------------------------------------------------------
# Full pipeline: staging copies, never links, and never from the case folder
# ---------------------------------------------------------------------------


def _typed_agree(value_kind: str, requested, current) -> bool:
    return str(requested) == str(current)


def _read_value(document_path: Path, key_path) -> object | None:
    if not document_path.exists():
        return None
    node = json.loads(document_path.read_text())
    for segment in key_path:
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node


def _validator(document: str, key_path: tuple, value) -> tuple[str, bool]:
    return "word", False


class _InputWriterPlugin(ToyProvider):
    """A toy case_writer, so a record with inputs can be staged and committed end to end -- the "One case, step by step" pipeline, minus any solver vocabulary."""

    def get_supported_mutation_modes(self):
        return frozenset({"clone_and_patch"})

    def resolve_case_mutation(self, request, *, driver_context):
        targets = tuple(
            {"document": p.document, "expanded_key_path": list(p.expanded_key_path()), "value": p.value}
            for p in request.parameters
        )
        return ResolvedMutation(
            request=request, targets=targets, expected_effects=(), semantic_owner_id=self.plugin_id,
        )

    def get_rendered_formats(self):
        return frozenset({_FORMAT})

    def render_case_files(self, resolved, *, snapshot_root, driver_context, execution_env=None):
        rendered = []
        for target in resolved.targets:
            path = Path(snapshot_root) / target["document"]
            exists_before = path.exists()
            content = json.loads(path.read_text()) if exists_before else {}
            node = content
            for segment in target["expanded_key_path"][:-1]:
                node = node.setdefault(segment, {})
            node[target["expanded_key_path"][-1]] = target["value"]
            rendered.append(RenderedFile(
                path=target["document"], content=(json.dumps(content) + "\n").encode(),
                mode=None, exists_before=exists_before,
                before_digest=_digest_bytes(path.read_bytes()) if exists_before else None,
                renderer_id=self.plugin_id, format=_FORMAT,
            ))
        return tuple(rendered)

    def get_config_value_reader(self):
        return _read_value

    def get_case_value_comparator(self):
        return _typed_agree


def _pipeline_context(tutorial_records):
    plugin = _InputWriterPlugin(tutorial_records=tutorial_records, record_key_validator=_validator)
    return driver_context(plugin, source="test:record-inputs")


def test_commit_record_case_stages_a_supplied_input_into_its_destination(tmp_path):
    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    (native / "system" / "controlDict.json").write_text("{}")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "fiber").write_text("fiber bytes\n")

    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})
    staged = tmp_path / "staged"

    record_execution.commit_record_case(
        record, cases_root=tmp_path / "cases", staged_case_root=staged,
        study_by_source={"base": {}}, driver_context=context,
        inputs={"anatomy": str(bundle)},
    )

    assert (staged / "0" / "fiber").read_text() == "fiber bytes\n"
    assert (staged / "system" / "controlDict.json").exists()


def test_staging_never_takes_an_input_destination_from_the_case_folder(tmp_path):
    """Design §2.3: "a destination never comes from the case folder, including a run case being restaged." A stale copy of the destination sitting in the native case (as a prior run would leave one) must not survive staging -- the supplied bundle's own bytes must win."""
    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    (native / "system" / "controlDict.json").write_text("{}")
    (native / "0").mkdir()
    (native / "0" / "fiber").write_text("STALE leftover from a prior run\n")

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "fiber").write_text("fresh supplied bytes\n")

    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})
    staged = tmp_path / "staged"

    record_execution.commit_record_case(
        record, cases_root=tmp_path / "cases", staged_case_root=staged,
        study_by_source={"base": {}}, driver_context=context,
        inputs={"anatomy": str(bundle)},
    )

    assert (staged / "0" / "fiber").read_text() == "fresh supplied bytes\n"


def test_commit_record_case_refuses_by_name_when_the_input_is_not_supplied(tmp_path):
    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})

    with pytest.raises(RecordInputNotSupplied, match="anatomy"):
        record_execution.commit_record_case(
            record, cases_root=tmp_path / "cases", staged_case_root=tmp_path / "staged",
            study_by_source={"base": {}}, driver_context=context,
        )


def test_preview_record_case_does_not_refuse_an_unsupplied_input(tmp_path):
    """§2.2: "describe does not refuse."""
    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})

    preview = record_execution.preview_record_case(
        record, cases_root=tmp_path / "cases",
        study_by_source={"base": {}}, driver_context=context,
    )
    assert preview["entry_name"] == "humanSlabToy"


def test_record_surface_lists_each_input_with_its_supplied_status(tmp_path):
    from omnidriver.core.runtime.record_surface import record_surface

    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})

    surface = record_surface(record, native_case_root=native, driver_context=context, supplied=None)
    assert surface["inputs"] == [
        {"name": "anatomy", "files": [["fiber", "0/fiber"]], "native_location": None, "supplied": False},
    ]

    surface = record_surface(record, native_case_root=native, driver_context=context, supplied={"anatomy": "/x"})
    assert surface["inputs"][0]["supplied"] is True


def test_commit_and_build_record_spec_carries_resolved_inputs_onto_the_spec(tmp_path):
    native = tmp_path / "cases" / "humanSlabToy"
    (native / "system").mkdir(parents=True)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "fiber").write_text("x")

    record = _anatomy_record()
    context = _pipeline_context({"humanSlabToy": record})

    _commit_result, spec = record_execution.commit_and_build_record_spec(
        record, case_id="humanSlabToy", cases_root=tmp_path / "cases",
        staged_case_root=tmp_path / "staged", study_by_source={"base": {}},
        driver_context=context, inputs={"anatomy": str(bundle)},
    )
    assert spec.metadata["inputs"] == [
        {"name": "anatomy", "kind": "supplied", "path": str(bundle), "files": [["fiber", "0/fiber"]]},
    ]


# ---------------------------------------------------------------------------
# CLI: --input NAME=PATH parsing
# ---------------------------------------------------------------------------


def test_cli_parses_repeated_input_flags():
    from omnidriver.cli import build_parser

    parser = build_parser()
    args = parser.parse_args([
        "describe", "--entry", "humanSlab",
        "--input", "anatomy=/some/dir", "--input", "mesh=/other/dir",
    ])
    assert args.inputs == ["anatomy=/some/dir", "mesh=/other/dir"]


def test_cli_refuses_input_with_no_equals_sign(capsys):
    from cli_refusal import refusal

    assert "must be NAME=PATH" in refusal(
        capsys, ["describe", "--plugin", "plugins.toy:ToyStack", "--entry", "toyTutorial", "--input", "anatomy-only-a-dir"],
    )
