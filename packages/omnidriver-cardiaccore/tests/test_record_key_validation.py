"""cardiacCore's key validator: a study may name a catalogued utility key, a key the utility's C++ reads,
or a key of a document it does not catalogue; nothing else."""
from __future__ import annotations

import pytest

from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.cardiaccore.record_key_validation import record_key_catalog, record_key_validator

DOCUMENT = "system/setCardiacConductivityDict"
ANATOMY_DOCUMENT = "system/setCardiacAnatomyDict"

# cardiacCore applications/utilities/setCardiacAnatomy/setCardiacAnatomy.C at chore/repo-layout:
# main from its head to the read of valveAreaMaskField, closed with a brace.
SET_CARDIAC_ANATOMY_MAIN = r'''int main(int argc, char *argv[])
{
    argList::addNote
    (
        "Tag cells with AHA segment IDs: LV 1-17 and RV free wall 18-26. The "
        "rings are cut on aha_z, the position along each ventricle's cavity, "
        "and the sectors on aha_angle, the short-axis angle in a geometric "
        "{L,S,LxS} frame derived from the LV/RV centroids. Writes AHA_Segment, "
        "aha_angle and aha_z, and, unless auxiliaryFields is false, phiRV, "
        "groove_interface and AHA_ValveArea."
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

    const label rvLocalBands = anatDict.getOrDefault<label>("rvLocalBands", 10);

    // The auxiliary fields (phiRV, groove_interface, AHA_ValveArea) are
    // evidence for the sector assignment; they are written unless this is
    // false. AHA_Segment, aha_angle and aha_z are always written.
    const bool auxiliaryFields =
        anatDict.getOrDefault<bool>("auxiliaryFields", true);

    // ventricularCellZone names a cellZone of ventricular myocardium. Cells
    // outside it are left at AHA_Segment 0, the value for "not a segment".
    // Without it every cell is classified, which assumes the mesh holds
    // ventricles only.
    const word ventricularCellZoneName =
        anatDict.getOrDefault<word>("ventricularCellZone", word::null);
    boolList isVentricular(mesh.nCells(), true);
    if (!ventricularCellZoneName.empty())
    {
        const label zoneID = mesh.cellZones().findZoneID(ventricularCellZoneName);
        if (zoneID < 0)
        {
            FatalErrorInFunction
                << "ventricularCellZone '" << ventricularCellZoneName
                << "' not found among this mesh's cellZones."
                << exit(FatalError);
        }
        isVentricular = false;
        const labelList& zoneCells = mesh.cellZones()[zoneID];
        forAll(zoneCells, i)
        {
            isVentricular[zoneCells[i]] = true;
        }
        Info<< "ventricularCellZone '" << ventricularCellZoneName << "': "
            << zoneCells.size() << " of " << mesh.nCells()
            << " cells classified; the rest get AHA_Segment = 0." << endl;
    }

    // valveAreaMaskField names the mask a valve-aware coordinate solve wrote
    // (fiberFoam's abSolveMask: 1 = solved myocardium, 0 = the basal band
    // around the valve rings). Cells where it is 0 are the valve area: they
    // are flagged in AHA_ValveArea and never set a cavity range. No AHA
    // scheme is defined over valve-adjacent tissue.
    const word valveAreaMaskFieldName =
        anatDict.getOrDefault<word>("valveAreaMaskField", word::null);
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


def test_a_ventricle_block_key_binds_its_placeholder_to_the_ventricles_the_cxx_reads():
    tree = "system/generatePurkinjeTreeDict"
    assert record_key_validator(tree, ("lv", "seed"), [0, 0, 0]) == ("vector3", True)
    with pytest.raises(ValueError, match="not one of \\['lv', 'rv'\\]"):
        record_key_validator(tree, ("banana", "seed"), [0, 0, 0])


def test_an_anatomy_key_is_checked_at_the_type_the_catalogue_gives_it():
    assert record_key_validator(ANATOMY_DOCUMENT, ("ventricularCellZone",), "myocardium") == ("word", True)
    assert record_key_validator(ANATOMY_DOCUMENT, ("auxiliaryFields",), False) == ("boolean", True)
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
    (tmp_path / "system" / "setCardiacConductivityDict").write_text("")
    from omnidriver.core.plugin_interface import load_plugin_context

    context = load_plugin_context("cardiaccore")
    listed = {
        (item["document"], item["key"])
        for item in context.stack.call("get_record_key_catalog", tmp_path, driver_context=context)
    }
    assert {("system/controlDict", "deltaT"), ("system/controlDict", "<any>")} <= listed
    assert ("system/setCardiacConductivityDict", "<any>") not in listed


def test_the_catalogue_lists_every_key_the_validator_accepts(tmp_path):
    listed = {(item["document"], item["key"]) for item in record_key_catalog(tmp_path)}
    assert (DOCUMENT, "fiberField") in listed and (DOCUMENT, "conductivityExtracellular.dn") in listed


def test_the_anatomy_reads_the_scanner_sees_agree_with_the_anatomy_catalogue(tmp_path):
    from omnidriver.cardiaccore.catalogs.inputs import CATALOG
    from omnidriver.openfoam.dict_keys_scanner import scan_source

    utility = tmp_path / "applications" / "utilities" / "setCardiacAnatomy"
    utility.mkdir(parents=True)
    (utility / "setCardiacAnatomy.C").write_text(SET_CARDIAC_ANATOMY_MAIN)
    reads = {read.key: read for read in scan_source(tmp_path).reads if read.function == "main"}
    entries = {entry.driver_path.rpartition(".")[2]: entry for entry in CATALOG.documents["setCardiacAnatomyDict"]}

    assert set(reads) == set(entries)
    for key in ("auxiliaryFields", "rvLocalBands"):
        assert reads[key].default == entries[key].typical_value
    for key in ("ventricularCellZone", "valveAreaMaskField"):
        assert reads[key].type == "word" and entries[key].value_kind == "word"
