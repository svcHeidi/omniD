from pathlib import Path

import pytest

from omnidriver.core.plugin_interface import driver_context

from omnidriver.cardiaccore.plugin import CardiacCorePlugin
from omnidriver.cardiaccore.tutorials import TUTORIAL_NAME, make_biv_preprocessing_spec


def test_biv_preprocessing_declares_the_native_wrapper_sequence(tmp_path):
    context = driver_context(CardiacCorePlugin(), source="test")
    spec = make_biv_preprocessing_spec(cases_root=tmp_path)

    assert spec.name == TUTORIAL_NAME
    steps = spec.metadata["workflow_dag"]["steps"]
    assert [(step["id"], step["command"]) for step in steps] == [
        ("conductivity", "setCardiacConductivity"),
        ("anatomy", "setCardiacAnatomy"),
        ("purkinje_slab", "setPurkinjeSlab"),
        ("purkinje_morphometry", "setPurkinjeMorphometry"),
    ]
    assert all(step["args"] == ["-case", "."] for step in steps)
    assert set(context.capabilities.command_authorization.utility_manifests()) == {
        step["command"] for step in steps
    }


def test_utility_outputs_are_not_misclassified_as_source_inputs(tmp_path):
    context = driver_context(CardiacCorePlugin(), source="test")

    output_globs = context.capabilities.case_provenance.generated_output_globs(
        tmp_path, {}, "0"
    )

    assert "0/AHA_Segment" in output_globs
    assert "0/PurkinjeTerminalWeightIntramural" in output_globs


def test_initial_input_catalog_is_scoped_to_the_selected_bivcase_workflow():
    context = driver_context(CardiacCorePlugin(), source="test")

    entries = {entry.driver_path: entry for entry in context.capabilities.dictionaries.entries()}
    assert set(entries) == {
        "$CARDIAC_CONDUCTIVITY.df",
        "$CARDIAC_CONDUCTIVITY.ds",
        "$CARDIAC_CONDUCTIVITY.dn",
        "$CARDIAC_CONDUCTIVITY.fiberField",
        "$CARDIAC_CONDUCTIVITY.sheetField",
        "$CARDIAC_ANATOMY.zApicalMid",
        "$CARDIAC_ANATOMY.zMidBasal",
        "$CARDIAC_ANATOMY.zApexCap",
        "$CARDIAC_ANATOMY.grooveMode",
        "$PURKINJE_SLAB.thickness",
        "$PURKINJE_SLAB.multiplier",
        "$PURKINJE_MORPHOMETRY.grooveMode",
    }
    assert entries["$PURKINJE_SLAB.thickness"].constraints
    assert entries["$CARDIAC_ANATOMY.grooveMode"].enum_values == ("auto", "manual")
    assert entries["$CARDIAC_CONDUCTIVITY.df"].value_kind == "scalar"
    assert entries["$CARDIAC_CONDUCTIVITY.df"].unit == ""
    assert entries["$CARDIAC_CONDUCTIVITY.df"].phases == frozenset({"preprocessing"})
    conditional = context.capabilities.named_catalogs.catalogs()["cardiaccore_conditional_inputs"]
    assert conditional["setPurkinjeMorphometryDict"][0]["status"] == "conditional"
    assert conditional["setCardiacConductivityDict"][0]["when"] == (
        "bidomain tensor preprocessing is selected"
    )


def _write_biv_dictionaries(case_root: Path) -> None:
    system = case_root / "system"
    system.mkdir(parents=True)
    (system / "setCardiacConductivityDict").write_text(
        "df 0.1143;\nds 0.052;\ndn 0.016;\nfiberField fiber;\nsheetField sheet;\n"
    )
    (system / "setCardiacAnatomyDict").write_text(
        "zApicalMid 0.3333333;\nzMidBasal 0.6666667;\nzApexCap 0.08;\ngrooveMode auto;\n"
    )
    (system / "setPurkinjeSlabDict").write_text("thickness 0.1;\nmultiplier 3.0;\n")
    (system / "setPurkinjeMorphometryDict").write_text("grooveMode auto;\n")


def test_input_overrides_change_only_the_materialized_case(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_biv_preprocessing_spec(
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

    unsupported = make_biv_preprocessing_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_MORPHOMETRY.subendocardialWeight": 0.4},
    )
    with pytest.raises(ValueError, match="not supported"):
        unsupported.apply_case(case_root, unsupported.build_cases()[0])

    manual = make_biv_preprocessing_spec(
        cases_root=tmp_path,
        input_overrides={"$CARDIAC_ANATOMY.grooveMode": "manual"},
    )
    with pytest.raises(ValueError, match="conditional anteriorGroove"):
        manual.apply_case(case_root, manual.build_cases()[0])


def test_run_document_config_records_the_effective_requested_value(tmp_path):
    case_root = tmp_path / "bivCase"
    _write_biv_dictionaries(case_root)
    spec = make_biv_preprocessing_spec(
        cases_root=tmp_path,
        input_overrides={"$PURKINJE_SLAB.thickness": 0.05},
    )

    config, diagnostics = CardiacCorePlugin().build_run_document_config(spec)

    assert diagnostics == ()
    assert config["preprocessing"]["thickness"] == 0.05
