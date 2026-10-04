"""The C++ scan on verbatim snippets of the native trees, each named by its
file; ``omnidriver scan`` and ``omnidriver check`` run against the whole trees."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.dict_keys_scanner import cached_scan, catalog_report, scan_source, source_digest
from omnidriver.openfoam.record_key_validation import scanned_key

# cardiacCore src/setPurkinjeSlab/setPurkinjeSlab.C: main, up to its two reads.
SET_PURKINJE_SLAB = '''#include "fvCFD.H"
#include "coordinatesConvention.H"

int main(int argc, char *argv[])
{
    argList::addNote
    (
        "native OpenFOAM utility to define a sub-endocardial Purkinje Slab layer "
        "and scale the conductivity tensor (Conductivity) within it."
    );

    #include "setRootCase.H"
    #include "createTime.H"
    #include "createMesh.H"

    Info<< "Reading system/setPurkinjeSlabDict\\n" << endl;

    IOdictionary slabDict
    (
        IOobject
        (
            "setPurkinjeSlabDict",
            runTime.system(),
            mesh,
            IOobject::MUST_READ,
            IOobject::NO_WRITE
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
    const Foam::TransmuralConvention transmuralConvention =
        Foam::readTransmuralConvention(conventionDict);
    const Foam::CoordinatesConvention coordinatesConvention =
        Foam::readCoordinatesConvention(conventionDict);
    const word& transmuralFieldName = coordinatesConvention.transmuralField;

    const scalar thickness = slabDict.getOrDefault<scalar>("thickness", 0.1);
    const scalar multiplier = slabDict.getOrDefault<scalar>("multiplier", 3.0);
}
'''

# cardiacCore src/coordinatesConvention/coordinatesConvention.H: readCoordinatesConvention.
READ_COORDINATES_CONVENTION = '''inline CoordinatesConvention readCoordinatesConvention
(
    const dictionary& conventionDict
)
{
    const dictionary& coordinates =
        conventionDict.subOrEmptyDict("coordinates");

    return CoordinatesConvention
    {
        coordinates.getOrDefault<word>
        (
            "transmuralField", defaultTransmuralField()
        ),
        coordinates.getOrDefault<word>
        (
            "intraventricularField", defaultIntraventricularField()
        ),
        coordinates.getOrDefault<word>
        (
            "longitudinalField", defaultLongitudinalField()
        )
    };
}
'''

# cardiacFOAM src/genericWriter/stimulusIO.C: its head and singleCellStimulusDict
# (the licence block shortened to its first lines, still a block comment).
STIMULUS_IO = '''/*---------------------------------------------------------------------------*\\
License
    This file is part of cardiacFoam.
\\*---------------------------------------------------------------------------*/

#include "stimulusIO.H"
#include "IOstreams.H"
#include "dimensionedScalar.H"
#include <cmath>

namespace Foam
{
namespace
{
const dictionary* singleCellStimulusDict(const dictionary& dict)
{
    if (!dict.found("singleCellStimulus"))
    {
        return nullptr;
    }

    return &dict.subDict("singleCellStimulus");
}
}
}
'''

# cardiacFOAM src/genericWriter/conductivityFieldIO.C: readConductivityField, to its first read.
READ_CONDUCTIVITY_FIELD = '''tmp<volTensorField> readConductivityField
(
    const fvMesh& solverMesh,
    const fvMesh& supportMesh,
    const fvMeshSubset* meshSubsetPtr,
    const dictionary& coefficients,
    const conductivityFieldSpec& spec
)
{
    word source("uniform");

    if (coefficients.found("conductivitySource"))
    {
        source = word(coefficients.lookup("conductivitySource"));
    }
    else
    {
        WarningInFunction
            << "No conductivitySource specified in " << coefficients.name()
            << "; using the legacy default 'uniform'. Add either "
            << "'conductivitySource uniform;' or 'conductivitySource field;'."
            << endl;
    }
}
'''

# cardiacCore src/generatePurkinjeTree/generatePurkinjeTree.C: main's treeDict and
# two reads of readVentParams.
READ_VENT_PARAMS = '''int main(int argc, char *argv[])
{
    IOdictionary treeDict
    (
        IOobject
        (
            "generatePurkinjeTreeDict", runTime.system(), mesh,
            IOobject::MUST_READ, IOobject::NO_WRITE
        )
    );
    auto readVentParams = [&](const word& ventKey)
    {
        const dictionary& vd = treeDict.subDict(ventKey);
        VentParams p{};
        p.seed        = vd.get<point>("seed");

        if (!vd.found("terminalCount"))
        {
            FatalErrorInFunction
                << "terminalSelectionModel weightedField requires "
                << "terminalCount in " << ventKey << "."
                << exit(FatalError);
        }
        p.terminalCount = vd.get<label>("terminalCount");
    };
}
'''

# cardiacFOAM src/ionicModels/ionicModel/configuredBatchedIonicModel.H:
# configureIonicHeterogeneity, in its class body.
CONFIGURE_HETEROGENEITY = '''class configuredBatchedIonicModel
{
public:

    virtual void configureIonicHeterogeneity
    (
        const scalarField& transmuralDistance,
        const dictionary& heterogeneityDict
    ) override
    {
        const wordList tissues = supportedTissueTypes();
        const bool supportsEndoMCellEpi =
            tissues.found("endocardialCells")
         && tissues.found("mCells")
         && tissues.found("epicardialCells");
    }
};
'''


# cardiacCore src/coordinatesConvention/coordinatesConvention.H: readTransmuralConvention.
READ_TRANSMURAL_CONVENTION = '''inline TransmuralConvention readTransmuralConvention
(
    const dictionary& conventionDict
)
{
    const dictionary& transmural = conventionDict.subDict("transmural");

    return TransmuralConvention
    {
        transmural.get<scalar>("endocardium"),
        transmural.get<scalar>("epicardium")
    };
}
'''


# cardiacFOAM (feat/heart-in-bath) src/electroModels/electroDomains/extracellularPotentialDomain/
# extracellularPotentialDomain.C: the constructor, to the check of the interpolation scheme.
EXTRACELLULAR_CONSTRUCTOR = '''extracellularPotentialDomain::extracellularPotentialDomain
(
    const fvMesh& baseMesh,
    myocardiumDomainInterface& heartDomain,
    const dictionary& dict
)
:
    baseMesh_(baseMesh),
    heartDomain_(heartDomain),
    sigmaTotalPtr_(),
    sigmaIglobalPtr_(),
    sigmaExtracellularfPtr_(),
    interfaceConductivityInterpolation_
    (
        dict.lookupOrDefault<word>
        (
            "interfaceConductivityInterpolation",
            "distanceWeightedHarmonic"
        )
    ),
    phiEPtr_(),
    VmGlobalPtr_(),
    heartCellToBaseCell_(),
    phiEReferencePoint_
    (
        dict.found("phiERefPoint")
      ? dict.get<point>("phiERefPoint")
      : point::zero
    ),
    phiEReferenceValue_(dict.lookupOrDefault<scalar>("phiEReferenceValue", 0.0)),
    hasPhiEReferencePoint_(dict.found("phiERefPoint")),
    bathCellZoneNames_(dict.lookup("bathCellZones")),
    bathConductivityFieldName_
    (
        dict.lookupOrDefault<word>
        (
            "bathConductivityField",
            "bodyAndOrgansConductivity"
        )
    ),
    surfaceCurrentPatchNames_(),
    surfaceCurrentPatchValues_(),
    hasDirichletPatch_(false),
    nNonOrthogonalCorrectors_
    (
        resolveNonOrthogonalCorrectors(baseMesh)
    ),
    sealedHeartBoundary_
    (
        dict.parent().get<Switch>("sealedHeartBoundary")
    )
{
    if
    (
        interfaceConductivityInterpolation_ != "unweightedHarmonic"
     && interfaceConductivityInterpolation_ != "distanceWeightedHarmonic"
     && interfaceConductivityInterpolation_ != "conormalHarmonic"
    )
    {
        FatalErrorInFunction
            << "Unknown interfaceConductivityInterpolation '"
            << interfaceConductivityInterpolation_ << "'. Valid values are "
            << "unweightedHarmonic, distanceWeightedHarmonic and "
            << "conormalHarmonic."
            << exit(FatalError);
    }
}
'''

# cardiacFOAM src/ionicModels/ionicModel/ionicHeterogeneityOrchestrator.C: configureRegionHeterogeneity.
CONFIGURE_REGION_HETEROGENEITY = '''void Foam::ionicHeterogeneityOrchestrator::configureRegionHeterogeneity
(
    const ionicModel& model,
    const scalarField& transmuralDistance,
    const dictionary& heterogeneityDict,
    PtrList<scalarField>& heterogeneousConstants,
    PtrList<scalarField>* heterogeneousInitialStates
)
{
    const auto* statesPtr = model.ioStatesPtr();

    if (statesPtr && transmuralDistance.size() != statesPtr->size())
    {
        FatalErrorInFunction
            << "Transmural distance field has " << transmuralDistance.size()
            << " values, but " << model.type() << " was configured with "
            << statesPtr->size() << " integration points."
            << exit(FatalError);
    }

    if (!heterogeneityDict.found("mode"))
    {
        FatalErrorInFunction
            << "ionicHeterogeneity for ionic model " << model.type()
            << " has no 'mode' entry. 'mode' is required: namedRegions or "
            << "cellZoneRegions."
            << exit(FatalError);
    }

    const word mode(heterogeneityDict.lookup("mode"));

    if (mode == "namedRegions")
    {
        configureNamedRegionHeterogeneity
        (
            model, transmuralDistance, heterogeneityDict, heterogeneousConstants,
            heterogeneousInitialStates
        );
        return;
    }

    if (mode == "cellZoneRegions")
    {
        configureCellZoneRegionHeterogeneity
        (
            model, transmuralDistance, heterogeneityDict, heterogeneousConstants,
            heterogeneousInitialStates
        );
        return;
    }

    FatalErrorInFunction
        << "Unsupported " << model.type() << " ionicHeterogeneity mode '"
        << mode << "'. Supported modes: namedRegions, cellZoneRegions."
        << exit(FatalError);
}
'''

# cardiacFOAM src/ionicModels/ionicModel/ionicHeterogeneityOrchestrator.C:
# configureNamedRegionHeterogeneity, to the check of `smoothing`.
CONFIGURE_NAMED_REGIONS = '''void Foam::ionicHeterogeneityOrchestrator::configureNamedRegionHeterogeneity
(
    const ionicModel& model,
    const scalarField& fieldValues,
    const dictionary& heterogeneityDict,
    PtrList<scalarField>& heterogeneousConstants,
    PtrList<scalarField>* heterogeneousInitialStates
)
{
    if (!heterogeneityDict.found("transitionMode"))
    {
        FatalErrorInFunction
            << "ionicHeterogeneity mode namedRegions requires a "
            << "'transitionMode' entry for ionic model " << model.type()
            << ". Supported: blend, hard."
            << exit(FatalError);
    }

    const word transitionMode(heterogeneityDict.lookup("transitionMode"));

    if (transitionMode != "blend" && transitionMode != "hard")
    {
        FatalErrorInFunction
            << "Unsupported ionicHeterogeneity transitionMode '"
            << transitionMode << "' for mode namedRegions. Supported: "
            << "blend, hard."
            << exit(FatalError);
    }

    word smoothing;
    scalar transitionWidth = 0.0;

    if (transitionMode == "blend")
    {
        if (!heterogeneityDict.found("transitionWidth"))
        {
            FatalErrorInFunction
                << "ionicHeterogeneity mode namedRegions with "
                << "transitionMode blend requires a 'transitionWidth' "
                << "entry for ionic model " << model.type() << "."
                << exit(FatalError);
        }

        if (!heterogeneityDict.found("smoothing"))
        {
            FatalErrorInFunction
                << "ionicHeterogeneity mode namedRegions with "
                << "transitionMode blend requires a 'smoothing' entry "
                << "for ionic model " << model.type() << "."
                << exit(FatalError);
        }

        transitionWidth = heterogeneityDict.get<scalar>("transitionWidth");
        smoothing = word(heterogeneityDict.lookup("smoothing"));

        if (smoothing != "smoothstep")
        {
            FatalErrorInFunction
                << "Unsupported ionicHeterogeneity smoothing '" << smoothing
                << "' for mode namedRegions. Supported: smoothstep."
                << exit(FatalError);
        }
    }
}
'''

# cardiacCore src/coordinatesConvention/coordinatesConvention.H: readCoordinateSystem.
READ_COORDINATE_SYSTEM = '''inline CoordinateSystem readCoordinateSystem
(
    const dictionary& conventionDict
)
{
    const word cs = conventionDict.get<word>("coordinateSystem");
    if (cs == "uvc") return CoordinateSystem::uvc;
    if (cs == "cobiveco") return CoordinateSystem::cobiveco;

    FatalErrorInFunction
        << "coordinateSystem must be 'uvc' or 'cobiveco'; got " << cs
        << exit(FatalError);

    return CoordinateSystem::uvc;
}
'''


def _tree(tmp_path: Path, **files: str) -> Path:
    root = tmp_path / "src"
    for name, text in files.items():
        path = root / name.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def _read(scan, key, method=None):
    (read,) = [r for r in scan.reads if r.key == key and (method is None or r.method == method)]
    return read


def test_a_literal_iodictionary_is_the_document_and_a_default_is_recorded(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB}))
    thickness = _read(scan, "thickness")
    assert (thickness.method, thickness.type, thickness.default) == ("getOrDefault", "scalar", "0.1")
    assert (thickness.root, thickness.scope, thickness.line) == ("document:setPurkinjeSlabDict", (), 44)


def test_a_local_alias_carries_its_subdictionary_scope(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"coordinatesConvention.H": READ_COORDINATES_CONVENTION}))
    field = _read(scan, "transmuralField")
    assert (field.root, field.scope, field.type) == (
        "param:readCoordinatesConvention:conventionDict", ("coordinates",), "word",
    )
    assert _read(scan, "coordinates").method == "subOrEmptyDict"


def test_line_numbers_survive_a_block_comment(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"stimulusIO.C": STIMULUS_IO}))
    subdict = _read(scan, "singleCellStimulus", "subDict")
    assert (subdict.line, subdict.function) == (22, "singleCellStimulusDict")


def test_a_wrapper_gives_a_lookup_its_type(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"conductivityFieldIO.C": READ_CONDUCTIVITY_FIELD}))
    source = _read(scan, "conductivitySource", "lookup")
    assert (source.type, source.root) == ("word", "param:readConductivityField:coefficients")


def test_a_subdictionary_named_by_an_expression_is_any_segment(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"generatePurkinjeTree.C": READ_VENT_PARAMS}))
    count = _read(scan, "terminalCount", "get")
    assert (count.type, count.scope, count.root) == ("label", ("*",), "document:generatePurkinjeTreeDict")


def test_a_receiver_declared_as_another_type_is_not_a_dictionary_read(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"configuredBatchedIonicModel.H": CONFIGURE_HETEROGENEITY}))
    assert scan.reads == ()


def test_the_scan_is_cached_by_the_source_and_the_scanner(tmp_path, monkeypatch):
    from omnidriver.openfoam import rtst_scanner

    root = _tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    cache = tmp_path / "scratch"
    first = cached_scan(root, cache_root=cache)
    cache_file = cache / "cxx-scan" / f"{first.digest}.json"
    assert cache_file.is_file()
    assert cached_scan(root, cache_root=cache) is first
    (root / "setPurkinjeSlab.C").write_text(SET_PURKINJE_SLAB.replace('"multiplier"', '"slabMultiplier"'))
    second = cached_scan(root, cache_root=cache)
    assert second.digest != first.digest
    assert any(read.key == "slabMultiplier" for read in second.reads)
    scanner = tmp_path / "rtst_scanner.py"
    scanner.write_text(Path(rtst_scanner.__file__).read_text() + "\n# changed\n")
    monkeypatch.setattr(rtst_scanner, "__file__", str(scanner))
    assert source_digest(root) != second.digest


def test_an_unreadable_or_altered_cache_is_rescanned(tmp_path):
    from omnidriver.openfoam import dict_keys_scanner

    root = _tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    cache = tmp_path / "scratch"
    scan = cached_scan(root, cache_root=cache)
    cache_file = cache / "cxx-scan" / f"{scan.digest}.json"
    payload = json.loads(cache_file.read_text())
    payload["reads"] = payload["reads"][1:]
    for damaged in (json.dumps(payload), cache_file.read_text()[:100]):
        cache_file.write_text(damaged)
        dict_keys_scanner._MEMO.clear()
        assert len(cached_scan(root, cache_root=cache).reads) == len(scan.reads)
    assert not list(cache_file.parent.glob("*.tmp"))


def _entry(path: str, kind: str = "scalar", **fields) -> DictEntry:
    return DictEntry(driver_path=path, description="", value_kind=kind, **fields)


def _report(tmp_path, entries, reviewed=None, **files):
    root = _tree(tmp_path, **(files or {"setPurkinjeSlab.C": SET_PURKINJE_SLAB}))
    allowlist = tmp_path / "reviewed.json"
    allowlist.write_text(json.dumps(reviewed or {}))
    return catalog_report(root, allowlist_path=allowlist, entries=entries).to_json()


def test_a_read_the_catalogue_lacks_is_uncatalogued_with_what_an_entry_needs(tmp_path):
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.thickness"),))
    assert report["disagreements"] == [] and report["unread"] == []
    (note,) = report["uncatalogued"]
    assert (note["key"], note["value_kind"], note["default"], note["source"], note["required"]) == (
        "multiplier", "scalar", "3.0", "setPurkinjeSlab.C:45", False,
    )
    assert note["entry"] == {
        "driver_path": None, "value_kind": "scalar", "required": False, "typical_value": "3.0",
        "source_refs": ["src/setPurkinjeSlab.C"],
    }


def test_a_read_without_a_default_is_required_unless_the_function_tests_it_first(tmp_path):
    report = _report(tmp_path, (), **{"generatePurkinjeTree.C": READ_VENT_PARAMS})
    by_key = {note["key"]: note for note in report["uncatalogued"]}
    assert by_key["seed"]["required"] is True
    assert by_key["terminalCount"]["required"] is False and by_key["terminalCount"]["method"] == "get"


def test_each_catalogue_claim_the_cxx_refutes_is_reported_with_both_sides_and_fails_nothing(tmp_path):
    cited = ("src/setPurkinjeSlab/setPurkinjeSlab.C",)
    report = _report(tmp_path, (
        _entry("$PURKINJE_SLAB.thickness", "integer", source_refs=cited),
        _entry("$PURKINJE_SLAB.multiplier", "word", source_refs=cited),
        _entry("$PURKINJE_SLAB.depth", required=True),
    ), **{"setPurkinjeSlab__setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    assert [item.split(":")[0] for item in report["disagreements"]] == ["$PURKINJE_SLAB.multiplier"]
    assert "catalogue value_kind 'word'; the C++ reads scalar" in report["disagreements"][0]
    (unread,) = report["unread"]
    assert unread["driver_path"] == "$PURKINJE_SLAB.depth"
    assert unread["note"] == "catalogued; the supplied C++ no longer reads it"
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.thickness", required=True, source_refs=cited),),
                     **{"setPurkinjeSlab__setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    assert "the C++ gives it a default (0.1" in report["disagreements"][0]


def test_a_catalogue_that_calls_optional_a_key_the_cxx_requires_is_reported(tmp_path):
    cited = ("src/generatePurkinjeTree.C",)
    entries = (_entry("$PURKINJE_TREE.<ventKey>.seed", "vector3", source_refs=cited),)
    report = _report(tmp_path, entries, **{"generatePurkinjeTree.C": READ_VENT_PARAMS})
    assert report["disagreements"] == [
        "$PURKINJE_TREE.<ventKey>.seed: catalogue says optional; the C++ reads it with no default (generatePurkinjeTree.C:15)",
    ]


def test_a_same_named_read_elsewhere_disagrees_with_nothing(tmp_path):
    entries = (_entry("$PURKINJE_SLAB.thickness", "integer", required=True),)
    assert _report(tmp_path, entries)["disagreements"] == []
    nested = (_entry("$CONVENTION.coordinates.transmuralField", "scalar"),)
    report = _report(tmp_path, nested, **{"coordinatesConvention.H": READ_COORDINATES_CONVENTION})
    assert report["disagreements"] == [
        "$CONVENTION.coordinates.transmuralField: catalogue value_kind 'scalar'; the C++ reads word "
        "(coordinatesConvention.H:11)",
    ]


def test_an_unseen_read_is_reviewed_and_a_stale_review_is_a_disagreement(tmp_path):
    reviewed = {"unseen_reads": {"read upstream": ["$PURKINJE_SLAB.depth", "$PURKINJE_SLAB.gone"]}}
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.depth"),), reviewed)
    assert report["disagreements"] == [
        "unseen_reads names $PURKINJE_SLAB.gone, which the catalogue does not list",
    ]
    assert report["unread"] == []


def _mapping(tmp_path, monkeypatch, **files):
    from omnidriver.core.plugin_profile import CxxMapping

    root = _tree(tmp_path, **files)
    monkeypatch.setenv("SCANNED_TREE", str(root.parent))
    return CxxMapping(source_root_variable="SCANNED_TREE", source_root_relative="src", allowlist_path=tmp_path)


def test_a_study_may_set_an_uncatalogued_key_the_cxx_reads_at_that_path(tmp_path, monkeypatch):
    mapping = _mapping(tmp_path, monkeypatch, **{"generatePurkinjeTree.C": READ_VENT_PARAMS})
    catalogued = (_entry(
        "$PURKINJE_TREE.<ventKey>.seed", "vector3", source_refs=("src/generatePurkinjeTree.C",),
    ),)
    document = "system/generatePurkinjeTreeDict"
    found = scanned_key(document, ("$PURKINJE_TREE", "lv", "terminalCount"), 3, mapping=mapping, entries=catalogued)
    assert found == ("integer", True)
    with pytest.raises(ValueError, match="read by the C\\+\\+ as label"):
        scanned_key(document, ("$PURKINJE_TREE", "lv", "terminalCount"), 2.5, mapping=mapping, entries=catalogued)
    with pytest.raises(KeyError, match=r"reads 'terminalCount' at \$PURKINJE_TREE\.\*\.terminalCount, not at"):
        scanned_key(document, ("$PURKINJE_TREE", "terminalCount"), 3, mapping=mapping, entries=catalogued)
    with pytest.raises(KeyError, match="reads no key named 'terminalCont'"):
        scanned_key(document, ("$PURKINJE_TREE", "lv", "terminalCont"), 3, mapping=mapping, entries=catalogued)
    with pytest.raises(KeyError, match="cannot place"):
        scanned_key(document, ("$PURKINJE_TREE", "lv", "terminalCount"), 3, mapping=mapping, entries=())
    monkeypatch.delenv("SCANNED_TREE")
    with pytest.raises(KeyError, match="not supplied"):
        scanned_key(document, ("$PURKINJE_TREE", "lv", "terminalCount"), 3, mapping=mapping, entries=catalogued)


def test_a_parameter_is_placed_through_the_calls_that_pass_it_a_dictionary(tmp_path, monkeypatch):
    mapping = _mapping(tmp_path, monkeypatch, **{
        "setPurkinjeSlab.C": SET_PURKINJE_SLAB,
        "coordinatesConvention.H": READ_COORDINATES_CONVENTION + READ_TRANSMURAL_CONVENTION,
    })
    catalogued = (_entry("$CONVENTION.transmural.endocardium"),)
    document = "system/coordinatesConventionDict"
    assert scanned_key(
        document, ("$CONVENTION", "coordinates", "transmuralField"), "uvc_transmural",
        mapping=mapping, entries=catalogued,
    ) == ("word", True)
    with pytest.raises(KeyError, match="not at"):
        scanned_key(document, ("$CONVENTION", "transmuralField"), "uvc_transmural", mapping=mapping, entries=catalogued)


def test_a_value_is_checked_against_the_kind_the_cxx_reads_not_the_one_the_catalogue_claims(tmp_path, monkeypatch):
    from omnidriver.openfoam.dict_keys_scanner import cxx_value_kind
    from omnidriver.openfoam.record_key_validation import CataloguedDocument, make_validator

    cited = ("src/setPurkinjeSlab/setPurkinjeSlab.C",)
    mapping = _mapping(tmp_path, monkeypatch, **{"setPurkinjeSlab__setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    stale = _entry("$PURKINJE_SLAB.thickness", "word", source_refs=cited)
    assert cxx_value_kind(scan_source(tmp_path / "src"), stale) == "scalar"
    assert cxx_value_kind(scan_source(tmp_path / "src"), _entry("$PURKINJE_SLAB.thickness", source_refs=cited)) is None

    document = CataloguedDocument(
        label="slab", entries=lambda: (stale,),
        match=lambda key_path: (stale, {}) if key_path == ("thickness",) else None, scan=lambda key_path: key_path,
    )
    validate = make_validator({"system/setPurkinjeSlabDict": document}, mapping=lambda: mapping, owner="test")
    assert validate("system/setPurkinjeSlabDict", ("thickness",), 0.2) == ("scalar", True)
    with pytest.raises(ValueError, match="value_kind .scalar., which the supplied C\\+\\+ reads it as .the catalogue says .word."):
        validate("system/setPurkinjeSlabDict", ("thickness",), "thick")


def test_a_word_read_into_a_member_is_compared_in_its_constructor_body(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"extracellularPotentialDomain.C": EXTRACELLULAR_CONSTRUCTOR}))
    scheme = _read(scan, "interfaceConductivityInterpolation")
    assert scheme.compared == ("conormalHarmonic", "distanceWeightedHarmonic", "unweightedHarmonic")
    assert scheme.closed
    assert _read(scan, "bathConductivityField").compared == ()


def test_a_local_compared_by_sequential_ifs_before_an_error_is_a_closed_menu(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"ionicHeterogeneityOrchestrator.C": CONFIGURE_REGION_HETEROGENEITY}))
    mode = _read(scan, "mode", "lookup")
    assert (mode.compared, mode.closed) == (("cellZoneRegions", "namedRegions"), True)
    scan = scan_source(_tree(tmp_path, **{"coordinatesConvention.H": READ_COORDINATE_SYSTEM}))
    system = _read(scan, "coordinateSystem")
    assert (system.compared, system.closed) == (("cobiveco", "uvc"), True)


def test_a_check_nested_in_another_branch_names_a_value_without_closing_the_menu(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"ionicHeterogeneityOrchestrator.C": CONFIGURE_NAMED_REGIONS}))
    mode = _read(scan, "transitionMode", "lookup")
    assert (mode.compared, mode.closed) == (("blend", "hard"), True)
    smoothing = _read(scan, "smoothing", "lookup")
    assert (smoothing.compared, smoothing.closed) == (("smoothstep",), False)


def test_a_key_the_function_does_not_compare_has_no_menu(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB}))
    assert all(read.compared == () and not read.closed for read in scan.reads)


_SCHEME = "$ELECTRO_MODEL_COEFFS.bathPotentialDomain.interfaceConductivityInterpolation"


def _scheme_report(tmp_path, listed, **fields):
    entry = _entry(_SCHEME, "enum", enum_values=listed, **fields)
    return _report(tmp_path, (entry,), **{"extracellularPotentialDomain.C": EXTRACELLULAR_CONSTRUCTOR})


def test_a_value_the_cxx_compares_and_the_menu_lacks_is_uncatalogued_not_refuted(tmp_path):
    report = _scheme_report(tmp_path, ("unweightedHarmonic", "distanceWeightedHarmonic"), source_refs=(
        "src/extracellularPotentialDomain.C",
    ))
    assert report["disagreements"] == []
    (note,) = [item for item in report["uncatalogued"] if item["kind"] == "compared_value"]
    assert (note["path"], note["value"], note["source"]) == (_SCHEME, "conormalHarmonic", "extracellularPotentialDomain.C:15")
    assert report["selector_values"][_SCHEME] == ["conormalHarmonic", "distanceWeightedHarmonic", "unweightedHarmonic"]


def test_a_menu_value_a_closed_chain_never_compares_is_a_disagreement(tmp_path):
    cited = ("src/extracellularPotentialDomain.C",)
    report = _scheme_report(tmp_path, (
        "unweightedHarmonic", "distanceWeightedHarmonic", "conormalHarmonic", "gone",
    ), source_refs=cited)
    assert report["disagreements"] == [
        f"{_SCHEME}: menu lists ['gone'], which the C++ never compares the value against; it fails on any "
        "value but ['conormalHarmonic', 'distanceWeightedHarmonic', 'unweightedHarmonic'] "
        "(extracellularPotentialDomain.C:15)",
    ]
    assert [item for item in report["uncatalogued"] if item["kind"] == "compared_value"] == []


def test_a_menu_the_function_leaves_open_is_never_refuted(tmp_path):
    entry = _entry("$HETEROGENEITY.smoothing", "enum", enum_values=("smoothstep", "linear"), source_refs=(
        "src/ionicHeterogeneityOrchestrator.C",
    ))
    report = _report(tmp_path, (entry,), **{"ionicHeterogeneityOrchestrator.C": CONFIGURE_NAMED_REGIONS})
    assert report["disagreements"] == []


def test_an_enum_a_selection_table_backs_takes_its_menu_from_the_table(tmp_path):
    reviewed = {"runtime_selection": {"by_path": {_SCHEME: {"base": "scheme", "mode": "subset"}}}}
    entry = _entry(_SCHEME, "enum", enum_values=("unweightedHarmonic",), source_refs=("src/extracellularPotentialDomain.C",))
    report = _report(tmp_path, (entry,), reviewed, **{"extracellularPotentialDomain.C": EXTRACELLULAR_CONSTRUCTOR})
    assert [item for item in report["uncatalogued"] if item["kind"] == "compared_value"] == []


def test_a_read_is_placed_by_a_sibling_key_when_the_entry_cites_no_file(tmp_path):
    cited = ("src/extracellularPotentialDomain.C",)
    entries = (
        _entry(_SCHEME, "enum", enum_values=("unweightedHarmonic", "distanceWeightedHarmonic")),
        _entry("$ELECTRO_MODEL_COEFFS.bathPotentialDomain.phiEReferenceValue", source_refs=cited),
    )
    report = _report(tmp_path, entries, **{"extracellularPotentialDomain.C": EXTRACELLULAR_CONSTRUCTOR})
    assert [item["value"] for item in report["uncatalogued"] if item["kind"] == "compared_value"] == ["conormalHarmonic"]
