"""Guards for the cable restitution spec's two pacing modes.

`cable1DRestitution` sweeps one of two different axes. In `coupling_interval`
mode the swept value is `t(S2 stimulus) - t(last S1 stimulus)`; in
`requested_di90` mode it is a diastolic interval measured from a repolarization
time the protocol supplies. Conflating the two is the specific error that
produced a restitution table whose abscissae were coupling intervals labelled
as DI -- so these tests assert that the modes stay distinguishable in the case
id, in the params, and in the emitted stimulus schedule.

This capability existed in the pre-migration driverFOAM tree and did not
survive the move into OmniD; it was reinstated on 2026-09-14 together with
these tests, which never existed on either side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.cardiacfoam.tutorials.cable_1d_restitution import _build_cases

COMMON = dict(
    ionic_models=["Stewart"],
    ionic_model_tissue_map={"Stewart": ["myocyte"]},
    dt_values=[0.001],
    dx_values=[0.1],
    solvers=["implicit"],
    conductivity_values=["[-1 -3 3 0 0 2 0] (2.3 0 0 2.3 0 2.3)"],
)

REFERENCE_REPOL90_S = 4.304086260869566


def test_coupling_interval_mode_is_the_default_and_is_labelled_S2():
    (case,) = _build_cases(s2_intervals_ms=[500.0], **COMMON)
    assert case.case_id.endswith("_S2500")
    assert case.params["pacingMode"] == "coupling_interval"
    assert case.params["s2Interval"] == 500.0
    # A coupling-interval case must not advertise a DI90 it never measured.
    assert "requestedDI90_ms" not in case.params


def test_di90_mode_is_labelled_RDI90_and_carries_its_reference():
    (case,) = _build_cases(
        s2_intervals_ms=[500.0],
        requested_di90_values_ms=[330.0],
        reference_repolarization90_s=REFERENCE_REPOL90_S,
        **COMMON,
    )
    assert case.case_id.endswith("_RDI90330")
    assert case.params["pacingMode"] == "requested_di90"
    assert case.params["requestedDI90_ms"] == 330.0
    assert case.params["referenceRepolarization90_s"] == REFERENCE_REPOL90_S
    # s2Interval means a coupling interval. Borrowing the name for a diastolic
    # interval is exactly how the axis got mislabelled the first time.
    assert "s2Interval" not in case.params


def test_di90_mode_refuses_to_build_without_a_reference_repolarization():
    with pytest.raises(ValueError, match="reference_repolarization90_s"):
        _build_cases(
            s2_intervals_ms=[500.0],
            requested_di90_values_ms=[330.0],
            reference_repolarization90_s=None,
            **COMMON,
        )


def test_a_case_with_no_S2_is_not_named_after_a_pacing_value_it_never_applies():
    # The automaticity control branch: n_s2 == 0 applies no premature beat, so
    # any spontaneous activation it records is unforced.
    (case,) = _build_cases(s2_intervals_ms=[500.0], n_s2=0, **COMMON)
    assert case.case_id.endswith("_NOS2")


def test_an_empty_pacing_axis_is_rejected_rather_than_silently_building_nothing():
    with pytest.raises(ValueError, match="pacing values cannot be empty"):
        _build_cases(s2_intervals_ms=[], **COMMON)
    with pytest.raises(ValueError, match="pacing values cannot be empty"):
        _build_cases(
            s2_intervals_ms=[500.0],
            requested_di90_values_ms=[],
            reference_repolarization90_s=REFERENCE_REPOL90_S,
            **COMMON,
        )


def test_the_di90_sweep_axis_produces_one_case_per_requested_value():
    boundaries = [0.0, 100.0, 200.0, 300.0, 850.0, 900.0, 950.0]
    cases = _build_cases(
        s2_intervals_ms=[500.0],
        requested_di90_values_ms=boundaries,
        reference_repolarization90_s=REFERENCE_REPOL90_S,
        **COMMON,
    )
    assert len(cases) == len(boundaries)
    assert [c.params["requestedDI90_ms"] for c in cases] == boundaries


#: A real, catalog-valid electroProperties fixture -- byte-for-byte the same
#: shape `test_cable_1d_restitution_write_channel.py` already uses as this
#: tutorial's own write-channel characterization fixture. Needed since
#: 2026-09-23 (Phase 3 Commit 3): `_apply_case` collapsed to a thin wrapper
#: over `_plan_case` (the decision "a parameter asserts a final state, not
#: only a value"), so it now drives a real `commit_case_overrides` channel
#: commit -- monkeypatching `replace_block_mesh_resolutions`/`set_delta_t`/
#: `set_end_time`/`apply_electro_property_overrides` (this test's old
#: mechanism) no longer intercepts anything, since none of those direct
#: writers are called any more. A real fixture is simpler than mocking the
#: channel's own resolver/renderer chain, and it is what this tutorial's own
#: characterization test already proves round-trips correctly.
_ELECTRO_TEXT = "\n".join(
    [
        "myocardiumSolver monodomainSolver;",
        "",
        "monodomainSolverCoeffs",
        "{",
        "    ionicModel Stewart;",
        "    tissue myocyte;",
        "    conductivity [-1 -3 3 0 0 2 0] (0.1 0 0 0.1 0 0.1);",
        "    solutionAlgorithm explicit;",
        "    externalStimulus",
        "    {",
        "        stimulusStartTimeList (0);",
        "        stimulusLocationMinList ((0 0 0));",
        "        stimulusLocationMaxList ((0 0 0));",
        "        stimulusDurationList (0);",
        "        stimulusIntensityList (0);",
        "    }",
        "}",
        "",
    ]
)

_BLOCK_MESH_TEXT = (
    "FoamFile\n{\n    object blockMeshDict;\n}\n"
    "blocks\n(\n"
    "    hex (0 1 2 3 4 5 6 7) (10 1 1) simpleGrading (1 1 1)\n"
    ");\n"
)


def _write_real_case(tmp_path) -> None:
    from write_channel_test_support import write_control_dict, write_physics_properties

    (tmp_path / "constant").mkdir(parents=True, exist_ok=True)
    (tmp_path / "constant" / "electroProperties").write_text(_ELECTRO_TEXT)
    write_physics_properties(tmp_path)
    write_control_dict(tmp_path)
    (tmp_path / "system").mkdir(parents=True, exist_ok=True)
    (tmp_path / "system" / "blockMeshDict").write_text(_BLOCK_MESH_TEXT)


def _apply(tmp_path, case, **kwargs):
    """Drive _apply_case far enough to read back its protocol sidecar."""
    from omnidriver.cardiacfoam.tutorials import cable_1d_restitution as spec

    _write_real_case(tmp_path)
    spec._apply_case(tmp_path, case, **kwargs)
    sidecar = json.loads((tmp_path / ".cardiacfoam_protocol.json").read_text())
    electro_text = (tmp_path / "constant" / "electroProperties").read_text()
    written = {"...externalStimulus.stimulusStartTimeList": _read_stimulus_start_time_list(electro_text)}
    return sidecar, written


def _read_stimulus_start_time_list(electro_text: str) -> str:
    for line in electro_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("stimulusStartTimeList"):
            return stripped.removeprefix("stimulusStartTimeList").strip().rstrip(";").strip()
    raise AssertionError("stimulusStartTimeList not found in rendered electroProperties")


def test_di90_scheduling_places_S2_at_the_reference_plus_the_requested_interval(tmp_path):
    (case,) = _build_cases(
        s2_intervals_ms=[500.0],
        requested_di90_values_ms=[330.0],
        reference_repolarization90_s=REFERENCE_REPOL90_S,
        **COMMON,
    )
    sidecar, _ = _apply(tmp_path, case, n_s1=5, n_s2=1)

    expected_s2 = REFERENCE_REPOL90_S + 0.330
    assert sidecar["pacing_mode"] == "requested_di90"
    assert sidecar["s1_stimulus_times_s"] == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert sidecar["s2_stimulus_times_s"] == pytest.approx([expected_s2], abs=1e-12)
    assert sidecar["requested_di90_s"] == pytest.approx(0.330)
    # Recorded, but explicitly not the swept axis.
    assert sidecar["s2_coupling_interval_s"] == pytest.approx(expected_s2 - 4.0)


def test_the_scheduled_S2_survives_into_the_dictionary_to_sub_timestep_accuracy(tmp_path):
    (case,) = _build_cases(
        s2_intervals_ms=[500.0],
        requested_di90_values_ms=[330.0],
        reference_repolarization90_s=REFERENCE_REPOL90_S,
        **COMMON,
    )
    _, written = _apply(tmp_path, case, n_s1=5, n_s2=1)

    key = next(k for k in written if k.endswith("externalStimulus.stimulusStartTimeList"))
    times = [float(tok) for tok in str(written[key]).strip("()").split()]
    expected_s2 = REFERENCE_REPOL90_S + 0.330
    # Under the old `.6g` formatting this landed 3.74 us away -- nearly four
    # steps at the protocol's deltaT = 1e-6 s.
    assert abs(times[-1] - expected_s2) < 1.0e-9


def test_coupling_interval_scheduling_is_unchanged(tmp_path):
    (case,) = _build_cases(s2_intervals_ms=[500.0], **COMMON)
    sidecar, _ = _apply(tmp_path, case, n_s1=5, n_s2=1)
    assert sidecar["pacing_mode"] == "coupling_interval"
    assert sidecar["stimulus_times_s"] == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0, 4.5])
    assert sidecar["requested_di90_s"] is None
    assert sidecar["reference_repolarization90_s"] is None


def test_a_no_S2_case_schedules_only_the_drive_train(tmp_path):
    (case,) = _build_cases(s2_intervals_ms=[500.0], n_s2=0, **COMMON)
    sidecar, _ = _apply(tmp_path, case, n_s1=5, n_s2=0)
    assert sidecar["s2_stimulus_times_s"] == []
    assert sidecar["stimulus_times_s"] == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    assert sidecar["s2_coupling_interval_s"] is None


def test_di90_mode_rejects_more_than_one_S2(tmp_path):
    (case,) = _build_cases(
        s2_intervals_ms=[500.0],
        requested_di90_values_ms=[330.0],
        reference_repolarization90_s=REFERENCE_REPOL90_S,
        **COMMON,
    )
    with pytest.raises(ValueError, match="n_s2 == 1"):
        _apply(tmp_path, case, n_s1=5, n_s2=2)


def test_every_required_artifact_is_claimed_by_the_step_that_writes_it(tmp_path):
    """An unclaimed expected artifact is charged to the wrong step.

    Core's workflow builder auto-credits any expected artifact that no step
    claims to the last *solver* step (the `unclaimed_artifacts` branch in
    `omnidriver.core.runtime.workflow`), because auxiliary post-processing
    commands are deliberately excluded from artifact credit. Declaring the
    postprocessor's outputs without listing them in `extract_cv`'s `produces`
    therefore fails `run` for not writing files `Allrun` never writes -- which
    is exactly what happened when these artifacts were first reinstated.
    """
    from omnidriver.cardiacfoam.tutorials.cable_1d_restitution import make_spec

    case_dir = tmp_path / "electrophysiologyProtocols/cableProtocol/monodomain1DCableCV"
    case_dir.mkdir(parents=True)
    spec = make_spec(cases_root=tmp_path)

    steps = spec.metadata["workflow_dag"]["steps"]
    claimed = {artifact_id for step in steps for artifact_id in step.get("produces", ())}
    required = {a.artifact_id for a in spec.metadata["expected_artifacts"] if not a.optional}

    unclaimed = required - claimed
    assert not unclaimed, f"expected artifacts claimed by no step: {sorted(unclaimed)}"

    by_step = {step["id"]: set(step.get("produces", ())) for step in steps}
    # The postprocessor's outputs belong to the postprocessing step, not the solver.
    assert {
        "restitution_event_summary",
        "restitution_metrics_csv",
        "restitution_events_csv",
    } <= by_step["extract_cv"]
    assert "restitution_metrics_csv" not in by_step["run"]


def test_postprocessor_artifacts_do_not_use_cores_case_id_placeholder(tmp_path):
    """`{case_id}` means the case *directory*, which is not what names these files.

    Core substitutes `case_root.name` for `{case_id}` -- in a sweep that is the
    staged case directory (`case_0001`). The postprocessor names its output
    after the semantic case id it reads from the `.driverfoam_case_id` sentinel
    (`implicit_Stewart_..._RDI9025`). Two different identifiers share the name
    "case id", so a pattern built with the placeholder can never match. Glob the
    suffix instead; `stale_artifacts` still catches a leftover file, because the
    runner snapshots before and after the step.
    """
    from omnidriver.cardiacfoam.tutorials.cable_1d_restitution import make_spec

    (tmp_path / "electrophysiologyProtocols/cableProtocol/monodomain1DCableCV").mkdir(parents=True)
    spec = make_spec(cases_root=tmp_path)

    postprocessed = {
        "restitution_event_summary",
        "restitution_metrics_csv",
        "restitution_events_csv",
    }
    for artifact in spec.metadata["expected_artifacts"]:
        if artifact.artifact_id in postprocessed:
            assert "{case_id}" not in artifact.path_pattern, artifact.artifact_id
            assert artifact.path_pattern.startswith("postProcessing/"), artifact.artifact_id


def test_the_postprocessor_output_location_is_case_relative_and_mode_invariant(tmp_path):
    """sweep_runner rewrites output_dir_name to "." for a staged case.

    A spec-time absolute `--output-dir` therefore points somewhere the staged
    step never writes, and the artifact check reports present output as missing.
    Passing a case-relative literal keeps `run` and `sweep-run` agreeing.
    """
    from omnidriver.cardiacfoam.tutorials.cable_1d_restitution import make_spec

    (tmp_path / "electrophysiologyProtocols/cableProtocol/monodomain1DCableCV").mkdir(parents=True)
    spec = make_spec(cases_root=tmp_path)

    (step,) = [s for s in spec.metadata["workflow_dag"]["steps"] if s["id"] == "extract_cv"]
    assert step["args"] == ["--output-dir", "postProcessing"]
    # An absolute path here is the defect: it encodes a spec-time directory.
    assert not Path(step["args"][1]).is_absolute()
