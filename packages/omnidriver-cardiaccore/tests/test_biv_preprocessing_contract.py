from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context

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
    context = driver_context(CardiacCorePlugin(), source="test")
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
    context = driver_context(CardiacCorePlugin(), source="test")
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
    context = driver_context(CardiacCorePlugin(), source="test")

    output_globs = context.capabilities.case_provenance.generated_output_globs(
        tmp_path, {}, "0"
    )

    assert "0/AHA_Segment" in output_globs
    assert "0/PurkinjeTerminalWeightIntramural" in output_globs


def test_initial_input_catalog_covers_the_selected_bivcase_workflow():
    # As of the declarative-vocabulary rewrite (see catalogs/inputs.py), the
    # catalog documents the full evidence-backed surface across all 11
    # native utilities, not only the keys the selected bivCase workflow
    # reads, so an exact-set assertion on the catalog is no longer the right
    # guard. The invariant that still matters -- and that this test now
    # asserts EXACTLY, not as a subset -- is that declaring a key did not
    # make it mutable: `_TARGETS` is the routable (overridable) surface, and
    # it must stay exactly these 10 reviewed x values.
    from omnidriver.cardiaccore.workflows.overrides import _TARGETS

    context = driver_context(CardiacCorePlugin(), source="test")

    entries = {entry.driver_path: entry for entry in context.capabilities.dictionaries.entries()}
    reviewed = {
        "$CARDIAC_CONDUCTIVITY.df",
        "$CARDIAC_CONDUCTIVITY.ds",
        "$CARDIAC_CONDUCTIVITY.dn",
        "$CARDIAC_CONDUCTIVITY.fiberField",
        "$CARDIAC_CONDUCTIVITY.sheetField",
        "$CARDIAC_ANATOMY.zApicalMid",
        "$CARDIAC_ANATOMY.zMidBasal",
        "$CARDIAC_ANATOMY.zApexCap",
        "$PURKINJE_SLAB.thickness",
        "$PURKINJE_SLAB.multiplier",
    }
    assert set(_TARGETS) == reviewed
    assert reviewed.issubset(entries)
    assert entries["$PURKINJE_SLAB.thickness"].constraints
    assert entries["$CARDIAC_CONDUCTIVITY.df"].value_kind == "scalar"
    assert entries["$CARDIAC_CONDUCTIVITY.df"].unit == ""
    assert entries["$CARDIAC_CONDUCTIVITY.df"].phases == frozenset({"preprocessing"})
    # The old free-text CONDITIONAL_INPUTS entries for the bidomain pair and
    # subendocardialWeight are now real DictEntry objects (folded into
    # CATALOG above), so the published conditional-inputs catalog is empty --
    # the name stays bound for plugin.py's named-catalog publication.
    conditional = context.capabilities.named_catalogs.catalogs()["cardiaccore_conditional_inputs"]
    assert conditional == {}
    # The bidomain pair's both-or-neither relation is declared, not prose:
    # each of the six names the other five, so any half-set pair is an error.
    assert entries["$CARDIAC_CONDUCTIVITY.conductivityIntracellular.df"].co_required_with == (
        "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.ds",
        "$CARDIAC_CONDUCTIVITY.conductivityIntracellular.dn",
        "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.df",
        "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.ds",
        "$CARDIAC_CONDUCTIVITY.conductivityExtracellular.dn",
    )
    assert entries["$PURKINJE_MORPHOMETRY.subendocardialWeight"].typical_value == "0.56"
    tree_contract = context.capabilities.named_catalogs.catalogs()[
        "cardiaccore_tree_validation"
    ]
    assert tree_contract["seed_placement"]["lv"]["aha_segments"] == (2, 3)
    assert tree_contract["baseline_coverage"]["required_if_endocardium_exists"]["lv"] == tuple(range(7, 18))


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


def test_input_overrides_reject_unreviewed_or_incomplete_modes(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)

    unsupported = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_MORPHOMETRY.subendocardialWeight": 0.4},
    )
    with pytest.raises(ValueError, match="not supported"):
        unsupported.apply_case(case_root, unsupported.build_cases()[0])

    retired_path = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={"$CARDIAC_ANATOMY.grooveMode": "manual"},
    )
    with pytest.raises(ValueError, match="not supported"):
        retired_path.apply_case(case_root, retired_path.build_cases()[0])


def test_human_tree_rejects_unvalidated_tree_overrides(tmp_path):
    spec = make_human_purkinje_endocardial_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_TREE.lv.N_it": 36},
    )

    with pytest.raises(ValueError, match="fixed contract"):
        spec.apply_case(tmp_path / "bivCase", spec.build_cases()[0])


def test_run_document_config_records_the_effective_requested_value(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_human_purkinje_slab_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_SLAB.thickness": 0.05},
    )

    config, diagnostics = CardiacCorePlugin().build_run_document_config(spec)

    assert diagnostics == ()
    assert config["preprocessing"]["thickness"] == 0.05


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
    assert set(config["preprocessing"]) == {
        path.split(".", 1)[1] for path in PURKINJE_TREE_INPUT_PATHS
    }
