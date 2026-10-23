"""cardiacCore's key validator: a study may name a catalogued utility key, a key the utility's C++ reads,
or a key of a document it does not catalogue; nothing else."""
from __future__ import annotations

import pytest

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.cardiaccore.record_key_validation import record_key_catalog, record_key_validator

DOCUMENT = "system/setCardiacConductivityDict"
ANATOMY_DOCUMENT = "system/setCardiacAnatomyDict"

# cardiacCore applications/utilities/setCardiacAnatomy/setCardiacAnatomy.C at chore/repo-layout (a1f9296):
# main from its head to the read of ventricularCellZone, closed with a brace.
SET_CARDIAC_ANATOMY_MAIN = r'''int main(int argc, char *argv[])
{
    argList::addNote
    (
        "Tag LV cells with AHA 17-segment IDs using ventricular coordinates and a "
        "geometric {L,S,LxS} frame derived from LV/RV centroids. Writes the "
        "per-cell short-axis angle as the field 'aha_angle'."
    );

    #include "setRootCase.H"
    #include "createTime.H"
    #include "createMesh.H"

    Info<< "Reading system/setCardiacAnatomyDict\n" << endl;
    IOdictionary anatDict
    (
        IOobject
        (
            "setCardiacAnatomyDict", runTime.system(), mesh,
            IOobject::MUST_READ, IOobject::NO_WRITE
        )
    );
    IOdictionary conventionDict
    (
        IOobject
        (
            "coordinatesConventionDict", runTime.system(), mesh,
            IOobject::MUST_READ, IOobject::NO_WRITE
        )
    );
    const IntraventricularConvention convention =
        readIntraventricularConvention(conventionDict);
    const CoordinatesConvention coordinatesConvention =
        readCoordinatesConvention(conventionDict);

    const word& longFieldName = coordinatesConvention.longitudinalField;
    const word& intravFieldName = coordinatesConvention.intraventricularField;

    const scalar zApicalMid = anatDict.get<scalar>("zApicalMid");
    const scalar zMidBasal  = anatDict.get<scalar>("zMidBasal");
    const scalar zApexCap   = anatDict.get<scalar>("zApexCap");
    const label rvLocalBands = anatDict.getOrDefault<label>("rvLocalBands", 10);

    // Optional: restrict AHA_Segment to a named cell zone (ventricular
    // myocardium only). isLeftVentricle()/isRightVentricle() are a strict
    // either/or over every cell the utility is given -- fine for every
    // case so far, because every one of them was already pre-filtered to
    // ventricles-only mesh content before reaching here (see
    // docs/superpowers/specs/2026-10-21-aha-segmentation-standardization-RESULTS.md).
    // Nothing currently enforces that, though: a mesh carrying atrial or
    // other non-ventricular tissue would silently get a plausible-looking
    // but meaningless 1-26 label on it. When ventricularCellZone names an
    // existing cellZone, cells outside it are left at AHA_Segment's default
    // 0 (the same "not a real segment" sentinel applications/scripts/bullseye.py already
    // uses for AHA_ValveArea) instead of being classified. Omitted (the
    // default): every cell is processed, unchanged from before this guard.
    const word ventricularCellZoneName =
        anatDict.getOrDefault<word>("ventricularCellZone", word::null);
}
'''


def test_a_catalogued_key_is_checked_against_its_value_kind():
    assert record_key_validator(DOCUMENT, ("fiberField",), "fibres") == ("word", True)
    assert record_key_validator(DOCUMENT, ("conductivityIntracellular", "df"), 0.3) == ("scalar", True)
    with pytest.raises(ValueError, match="does not fit catalogued value_kind 'scalar'"):
        record_key_validator(DOCUMENT, ("df",), "notanumber")


def test_a_key_the_catalogue_lacks_is_refused_naming_the_catalogue_and_how_to_list_what_the_cxx_reads():
    with pytest.raises(TutorialRecordError) as refused:
        record_key_validator(DOCUMENT, ("nonsense",), 1)
    assert "not declared by the cardiacCore key catalog" in refused.value.args[0]
    assert "omnidriver catalog --uncatalogued" in refused.value.args[0]
    assert refused.value.code == "unknown_key"


def test_a_key_the_supplied_cxx_reads_is_accepted_at_the_type_it_reads(tmp_path, monkeypatch):
    utility = tmp_path / "tree" / "applications" / "utilities" / "setCardiacAnatomy"
    utility.mkdir(parents=True)
    (utility / "setCardiacAnatomy.C").write_text(SET_CARDIAC_ANATOMY_MAIN)
    monkeypatch.setenv("OMNIDRIVER_CARDIACCORE_TREE", str(tmp_path / "tree"))
    assert record_key_validator(ANATOMY_DOCUMENT, ("ventricularCellZone",), "myocardium") == ("word", True)
    with pytest.raises(ValueError):
        record_key_validator(ANATOMY_DOCUMENT, ("ventricularCellZone",), 2.5)


def test_a_document_the_catalogue_does_not_hold_is_refused_unless_it_is_a_system_file():
    with pytest.raises(TutorialRecordError, match="neither a cardiacCore-catalogued document") as refused:
        record_key_validator("constant/anything", ("a",), 1)
    assert refused.value.code == "unknown_document"
    assert record_key_validator("system/fvSchemes", ("default",), "Gauss linear") == ("string", False)


def test_control_dict_is_validated_as_for_every_openfoam_solver_and_otherwise_open():
    assert record_key_validator("system/controlDict", ("deltaT",), 1e-3) == ("scalar", True)
    with pytest.raises(ValueError, match="must be more than 0"):
        record_key_validator("system/controlDict", ("deltaT",), 0)
    assert record_key_validator("system/controlDict", ("writePrecision",), 8) == ("integer", False)


def test_fv_schemes_is_validated_as_for_every_openfoam_solver_and_otherwise_open():
    assert record_key_validator("system/fvSchemes", ("ddtSchemes", "default"), "backward") == ("string", True)
    assert record_key_validator("system/fvSchemes", ("laplacianSchemes", "laplacian(D,Vm)"), "Gauss linear corrected") == ("string", True)
    assert record_key_validator("system/fvSchemes", ("fluxRequired", "default"), "no")[1] is False


def test_the_catalogue_lists_the_control_dict_keys_beside_the_open_row_when_the_case_holds_one(tmp_path):
    (tmp_path / "system").mkdir()
    (tmp_path / "system" / "controlDict").write_text("")
    listed = {(item["document"], item["key"]) for item in record_key_catalog(tmp_path)}
    assert {("system/controlDict", "deltaT"), ("system/controlDict", "<any>")} <= listed


def test_the_catalogue_lists_every_key_the_validator_accepts(tmp_path):
    listed = {(item["document"], item["key"]) for item in record_key_catalog(tmp_path)}
    assert (DOCUMENT, "fiberField") in listed and (DOCUMENT, "conductivityExtracellular.dn") in listed


def test_an_anatomy_entry_that_cites_a_segment_cites_the_readme_and_the_name_table():
    from omnidriver.cardiaccore.catalogs.inputs import CATALOG

    cited = [entry for entry in CATALOG.documents["setCardiacAnatomyDict"] if "AHA" in entry.description]
    assert {entry.driver_path.rpartition(".")[2] for entry in cited} == {"zApicalMid", "zMidBasal", "zApexCap"}
    for entry in cited:
        assert "applications/utilities/setCardiacAnatomy/README.md" in entry.source_refs
        assert "applications/utilities/setCardiacAnatomy/aha_segment_names.json" in entry.source_refs
