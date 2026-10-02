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


def test_half_a_bidomain_pair_names_every_key_the_utility_also_needs(tmp_path):
    messages = _messages(_case(tmp_path, _COMPLETE + "conductivityIntracellular { df 0.2; }\n"))
    assert "conductivityIntracellular.df requires conductivityExtracellular.dn to be set as well." in messages
    assert len(messages) == 5


def test_a_case_with_no_catalogued_dictionary_breaks_nothing(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text(_HEADER + "application x;\n")
    assert _messages(tmp_path) == []
