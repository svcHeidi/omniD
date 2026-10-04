"""cardiacCore's catalogue relations, run over the utility dictionaries a case holds."""
from __future__ import annotations

from omnidriver.cardiaccore.plugin import CardiacCorePlugin

_HEADER = "FoamFile { version 2.0; format ascii; class dictionary; object d; }\n"


def _case(tmp_path, body: str):
    system = tmp_path / "system"
    system.mkdir()
    (system / "setCardiacConductivityDict").write_text(_HEADER + body)
    return tmp_path


_COMPLETE = 'df 0.1; ds 0.05; dn 0.02; fiberField "fiber"; sheetField "sheet";\n'


def _messages(case_root):
    return sorted(item.message for item in CardiacCorePlugin().validate_run_semantics(case_root))


def test_a_complete_dictionary_breaks_no_relation(tmp_path):
    assert _messages(_case(tmp_path, _COMPLETE)) == []


def test_a_missing_required_key_is_named(tmp_path):
    assert _messages(_case(tmp_path, 'ds 0.05; dn 0.02; fiberField "fiber"; sheetField "sheet";\n')) == [
        "df is required.",
    ]


def test_half_a_bidomain_pair_names_the_other_block(tmp_path):
    assert _messages(_case(tmp_path, _COMPLETE + "conductivityIntracellular { df 0.2; ds 0.1; dn 0.05; }\n")) == [
        "conductivityIntracellular.df requires conductivityExtracellular.df to be set as well.",
        "conductivityIntracellular.dn requires conductivityExtracellular.dn to be set as well.",
        "conductivityIntracellular.dn requires conductivityExtracellular.ds to be set as well.",
        "conductivityIntracellular.ds requires conductivityExtracellular.dn to be set as well.",
        "conductivityIntracellular.ds requires conductivityExtracellular.ds to be set as well.",
    ]


def test_a_dictionary_without_sheetField_breaks_no_relation_with_df_and_dt(tmp_path):
    assert _messages(_case(tmp_path, 'df 0.1; dt 0.03; fiberField "fiber";\n')) == []


def test_a_fibre_only_bidomain_pair_breaks_no_relation(tmp_path):
    body = (
        'df 0.1; dt 0.03; fiberField "fiber";\n'
        "conductivityIntracellular { df 0.2; dt 0.02; }\n"
        "conductivityExtracellular { df 0.3; dt 0.06; }\n"
    )
    assert _messages(_case(tmp_path, body)) == []


def test_sheetField_without_ds_and_dn_is_named(tmp_path):
    assert _messages(_case(tmp_path, 'df 0.1; fiberField "fiber"; sheetField "sheet";\n')) == [
        "sheetField requires dn to be set as well.",
        "sheetField requires ds to be set as well.",
    ]


def test_ds_and_dn_without_sheetField_are_named_because_the_fibre_only_branch_never_reads_them(tmp_path):
    assert _messages(_case(tmp_path, 'df 0.1; ds 0.05; dn 0.02; dt 0.03; fiberField "fiber";\n')) == [
        "dn requires sheetField to be set as well.",
        "ds requires sheetField to be set as well.",
    ]


def test_dt_beside_sheetField_is_named_because_the_sheet_branch_never_reads_it(tmp_path):
    assert _messages(_case(tmp_path, _COMPLETE + "dt 0.03;\n")) == ["dt is mutually exclusive with sheetField."]


def test_a_case_with_no_catalogued_dictionary_breaks_nothing(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text(_HEADER + "application x;\n")
    assert _messages(tmp_path) == []
