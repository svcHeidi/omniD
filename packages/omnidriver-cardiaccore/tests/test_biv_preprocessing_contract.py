from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.workflows.preprocessing import (
    HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME,
    HUMAN_PURKINJE_SLAB_TUTORIAL_NAME,
    PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME,
    PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME,
    PURKINJE_TREE_INPUT_PATHS,
    make_human_purkinje_endocardial_spec,
    make_human_purkinje_slab_spec,
    make_pig_morphometric_purkinje_spec,
    make_pig_transmural_purkinje_spec,
)


def test_biv_preprocessing_declares_the_native_wrapper_sequence(tmp_path):
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
    spec = make_human_purkinje_slab_spec(cases_root=tmp_path)

    assert spec.name == HUMAN_PURKINJE_SLAB_TUTORIAL_NAME
    steps = spec.metadata["workflow_dag"]["steps"]
    assert [(step["id"], step["command"]) for step in steps] == [
        ("conductivity", "setCardiacConductivity"),
        ("anatomy", "setCardiacAnatomy"),
        ("purkinje_slab", "setPurkinjeSlab"),
        ("purkinje_morphometry", "setPurkinjeMorphometry"),
    ]
    assert all(step["args"] == ["-case", "."] for step in steps)
    assert {step["command"] for step in steps}.issubset(
        context.capabilities.command_authorization.utility_manifests()
    )


def test_human_tree_declares_the_native_case_local_generator_contract(tmp_path):
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
    spec = make_human_purkinje_endocardial_spec(cases_root=tmp_path)

    assert spec.name == HUMAN_PURKINJE_ENDOCARDIAL_TUTORIAL_NAME
    steps = spec.metadata["workflow_dag"]["steps"]
    assert [(step["id"], step["command"]) for step in steps] == [
        ("conductivity", "setCardiacConductivity"),
        ("anatomy", "setCardiacAnatomy"),
        ("purkinje_tree", "generatePurkinjeTree"),
    ]
    assert steps[-1]["depends_on"] == ["conductivity", "anatomy"]
    assert steps[-1]["args"] == ["-case", "."]
    assert spec.metadata["active_input_paths"] == PURKINJE_TREE_INPUT_PATHS

    manifest = context.capabilities.command_authorization.utility_manifests()[
        "generatePurkinjeTree"
    ]
    assert {
        output.path_pattern for output in manifest.produces
    } >= {
        "constant/polyMesh/sets/LVEndoFaces",
        "postProcessing/generatePurkinjeTree/purkinje.vtk",
    }


def test_pig_workflows_differ_only_in_lv_weight_consumption(tmp_path):
    morphometric = make_pig_morphometric_purkinje_spec(cases_root=tmp_path)
    transmural = make_pig_transmural_purkinje_spec(cases_root=tmp_path)

    assert morphometric.name == PIG_MORPHOMETRIC_PURKINJE_TUTORIAL_NAME
    assert transmural.name == PIG_TRANSMURAL_PURKINJE_TUTORIAL_NAME
    assert morphometric.metadata["active_input_paths"] == PURKINJE_TREE_INPUT_PATHS
    assert transmural.metadata["active_input_paths"] == PURKINJE_TREE_INPUT_PATHS
    morphometric_steps = morphometric.metadata["workflow_dag"]["steps"]
    transmural_steps = transmural.metadata["workflow_dag"]["steps"]
    expected_steps = [
        ("conductivity", "setCardiacConductivity"),
        ("anatomy", "setCardiacAnatomy"),
        ("purkinje_morphometry", "setPurkinjeMorphometry"),
        ("purkinje_tree", "generatePurkinjeTree"),
    ]
    assert [
        (step["id"], step["command"]) for step in morphometric_steps
    ] == expected_steps
    assert [
        (step["id"], step["command"]) for step in transmural_steps
    ] == expected_steps
    assert morphometric_steps[-1]["depends_on"] == [
        "conductivity",
        "anatomy",
        "purkinje_morphometry",
    ]
    weight_fields = {
        "0/PurkinjeTerminalWeightSubendocardial",
        "0/PurkinjeTerminalWeightIntramural",
    }
    assert weight_fields.issubset(morphometric_steps[-1]["consumes"])
    assert weight_fields.isdisjoint(transmural_steps[-1]["consumes"])


def test_utility_outputs_are_not_misclassified_as_source_inputs(tmp_path):
    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")

    output_globs = context.capabilities.case_provenance.generated_output_globs(
        tmp_path, {}
    )

    assert "0/AHA_Segment" in output_globs
    assert "0/PurkinjeTerminalWeightIntramural" in output_globs


def _write_biv_dictionaries(case_root: Path) -> None:
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1143;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3333333;\nzMidBasal 0.6666667;\nzApexCap 0.08;\n"
    )
    (system / "setPurkinjeSlabDict").write_text("thickness 0.1;\nmultiplier 3.0;\n")
    (system / "setPurkinjeMorphometryDict").write_text("")
    (system / "generatePurkinjeTreeDict").write_text(
        "growthModel surfaceFollow;\n"
        "hisBundleSeed (0.014 0.022 -0.007);\n"
        "lv\n{\n    seed (0.011 0.019 -0.002);\n    N_it 24;\n}\n"
        "rv\n{\n    seed (0.016 0.025 -0.012);\n    N_it 32;\n}\n"
    )


def test_input_overrides_change_only_the_materialized_case(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={
            "$CARDIAC_CONDUCTIVITY.df": 0.2,
            "$PURKINJE_SLAB.thickness": 0.05,
        },
    )

    spec.apply_case(case_root, spec.build_cases()[0])

    assert "df    0.2;" in (case_root / "system/setCardiacConductivityDict").read_text()
    assert "thickness    0.05;" in (case_root / "system/setPurkinjeSlabDict").read_text()


def test_run_document_config_records_the_effective_requested_value(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_SLAB.thickness": 0.05},
    )

    config, diagnostics = CardiacCorePlugin().build_run_document_config(spec)

    assert diagnostics == ()
    # Corrected 2026-09-22 (audit finding S3, batch G0-C): `preprocessing`
    # slice keys are now qualified by
    # `overrides.qualified_slot_key`/`run_config.resolve_workflow_inputs`, so
    # a leaf name declared by two documents occupies two slots instead of
    # colliding. This assertion previously read the unqualified `"thickness"`
    # key.
    assert config["preprocessing"]["$PURKINJE_SLAB.thickness"] == 0.05


def test_human_tree_config_uses_only_the_shared_utility_inputs(tmp_path):
    case_root = tmp_path / "bivCase"
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1143;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3333333;\nzMidBasal 0.6666667;\nzApexCap 0.08;\n"
    )
    spec = make_human_purkinje_endocardial_spec(cases_root=tmp_path)

    config, diagnostics = CardiacCorePlugin().build_run_document_config(spec)

    assert diagnostics == ()
    # This case writes only the conductivity and anatomy dictionaries -- no
    # Purkinje-tree dictionary exists at all, `<ventKey>` or otherwise -- so
    # only entries declared by a document actually present resolve to a real
    # value. Keys are qualified (kept scope token) rather than stripped.
    #
    # Corrected 2026-09-22 (audit finding S3, batch G0-C): before
    # `resolve_workflow_inputs` filtered out every `None` value,
    # `build_config` kept every path in `active_input_paths` as a key
    # regardless of whether its document existed, so this assertion held for
    # a different reason -- it excluded only the `<ventKey>` paths because
    # *those alone* were filtered (by `read_input_values`'s own vent-block
    # skip), not because an unresolved path was filtered at all. Now every
    # unresolved path is filtered, `<ventKey>` or not, which is why the
    # non-`<ventKey>` Purkinje-tree entries (`growthModel`, `hisBundleSeed`)
    # are absent here too.
    assert set(config["preprocessing"]) == {
        path for path in PURKINJE_TREE_INPUT_PATHS
        if path.startswith("$CARDIAC_CONDUCTIVITY.")
        or path.startswith("$CARDIAC_ANATOMY.")
    }


def test_every_declared_value_is_reachable(tmp_path):
    """Declaring a key now makes it movable; it used to make it visible only.

    A ten-row routing table decided what an agent could set, so 77 of the 87
    declared entries were unreachable -- guidance the agent could read and
    not act on. Resolution now comes from the declaring document, so the two
    sets cannot drift apart.
    """
    from omnidriver.cardiaccore.workflows.overrides import resolve_override_target

    context = driver_context(OpenFOAMEnvironmentPlugin(), CardiacCorePlugin(), source="test")
    for entry in context.capabilities.dictionaries.entries():
        path = entry.driver_path.replace("<ventKey>", "lv")
        assert resolve_override_target(path).key


def test_tree_parameters_are_movable_and_land_in_the_case(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_human_purkinje_endocardial_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_TREE.lv.N_it": 36},
    )
    spec.apply_case(case_root, spec.build_cases()[0])

    from omnidriver.openfoam.mutators import read_foam_entry
    assert int(read_foam_entry(
        case_root / "system" / "generatePurkinjeTreeDict", "N_it", scope=("lv",),
    )) == 36


def test_a_key_no_native_utility_reads_is_still_refused(tmp_path):
    """Not a permission: setCardiacAnatomy detects grooves unconditionally.

    OpenFOAM ignores an unknown dictionary entry, so writing grooveMode would
    be a silent no-op the solver cannot report.
    """
    spec = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={"$CARDIAC_ANATOMY.grooveMode": "manual"},
    )
    with pytest.raises(ValueError, match="not declared"):
        spec.apply_case(tmp_path / "bivCase", spec.build_cases()[0])
