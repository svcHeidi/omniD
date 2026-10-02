"""cardiacCore's key validator: a study may name a catalogued utility key, a key the utility's C++ reads,
or a key of a document it does not catalogue; nothing else."""
from __future__ import annotations

import pytest

from omnidriver.cardiaccore.record_key_validation import record_key_catalog, record_key_validator

DOCUMENT = "system/setCardiacConductivityDict"

# cardiacCore src/setCardiacConductivity/setCardiacConductivity.C: main's head, to the first reads of the dictionary.
SET_CARDIAC_CONDUCTIVITY_MAIN = '''int main(int argc, char *argv[])
{
    #include "setRootCase.H"
    #include "createTime.H"
    #include "createMesh.H"

    Info<< "Reading system/setCardiacConductivityDict\\n" << endl;

    IOdictionary diffDict
    (
        IOobject
        (
            "setCardiacConductivityDict",
            runTime.system(),
            mesh,
            IOobject::MUST_READ,
            IOobject::NO_WRITE
        )
    );

    word fiberFieldName = diffDict.get<word>("fiberField");
    word sheetFieldName = diffDict.get<word>("sheetField");
    const scalar anisotropyRatio = diffDict.get<scalar>("anisotropyRatio");
}
'''


def test_a_catalogued_key_is_checked_against_its_value_kind():
    assert record_key_validator(DOCUMENT, ("fiberField",), "fibres") == ("word", True)
    assert record_key_validator(DOCUMENT, ("conductivityIntracellular", "df"), 0.3) == ("scalar", True)
    with pytest.raises(ValueError, match="does not fit catalogued value_kind 'scalar'"):
        record_key_validator(DOCUMENT, ("df",), "notanumber")


def test_a_key_the_catalogue_lacks_is_refused_naming_the_catalogue_and_how_to_list_what_the_cxx_reads():
    with pytest.raises(KeyError) as refused:
        record_key_validator(DOCUMENT, ("nonsense",), 1)
    assert "not declared by the cardiacCore key catalog" in refused.value.args[0]
    assert "omnidriver catalog --uncatalogued" in refused.value.args[0]


def test_a_key_the_supplied_cxx_reads_is_accepted_at_the_type_it_reads(tmp_path, monkeypatch):
    tree = tmp_path / "tree"
    (tree / "src" / "setCardiacConductivity").mkdir(parents=True)
    (tree / "src" / "setCardiacConductivity" / "setCardiacConductivity.C").write_text(SET_CARDIAC_CONDUCTIVITY_MAIN)
    monkeypatch.setenv("OMNIDRIVER_CARDIACCORE_TREE", str(tree))
    assert record_key_validator(DOCUMENT, ("anisotropyRatio",), 2.5) == ("scalar", True)
    with pytest.raises(ValueError):
        record_key_validator(DOCUMENT, ("anisotropyRatio",), "wide")


def test_a_document_the_catalogue_does_not_hold_is_refused_unless_it_is_a_system_file():
    with pytest.raises(KeyError, match="neither a cardiacCore-catalogued document"):
        record_key_validator("constant/anything", ("a",), 1)
    assert record_key_validator("system/controlDict", ("endTime",), 1) == ("integer", False)


def test_the_catalogue_lists_every_key_the_validator_accepts(tmp_path):
    listed = {(item["document"], item["key"]) for item in record_key_catalog(tmp_path)}
    assert (DOCUMENT, "fiberField") in listed and (DOCUMENT, "conductivityExtracellular.dn") in listed
