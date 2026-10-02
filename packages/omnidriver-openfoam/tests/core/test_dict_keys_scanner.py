"""The C++ scan on verbatim snippets of the native trees, each named by its
file; the whole trees are covered by the ``native`` and
``native_cardiaccore`` tests."""
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


def test_a_read_the_catalogue_lacks_is_uncatalogued_never_a_contradiction(tmp_path):
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.thickness"),))
    assert report["status"] == "ok" and report["contradictions"] == []
    (note,) = report["uncatalogued"]
    assert (note["key"], note["value_kind"], note["default"], note["source"]) == (
        "multiplier", "scalar", "3.0", "setPurkinjeSlab.C:45",
    )


def test_each_catalogue_claim_the_cxx_refutes_is_a_contradiction(tmp_path):
    cited = ("src/setPurkinjeSlab/setPurkinjeSlab.C",)
    report = _report(tmp_path, (
        _entry("$PURKINJE_SLAB.thickness", "integer", source_refs=cited),
        _entry("$PURKINJE_SLAB.multiplier", "word", source_refs=cited),
        _entry("$PURKINJE_SLAB.depth", required=True),
    ), **{"setPurkinjeSlab__setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    assert report["status"] == "failed"
    assert [item.split(":")[0] for item in report["contradictions"]] == [
        "$PURKINJE_SLAB.multiplier", "$PURKINJE_SLAB.depth",
    ]
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.thickness", required=True, source_refs=cited),),
                     **{"setPurkinjeSlab__setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    assert "the C++ gives it a default (0.1" in report["contradictions"][0]


def test_a_same_named_read_elsewhere_contradicts_nothing(tmp_path):
    entries = (_entry("$PURKINJE_SLAB.thickness", "integer", required=True),)
    assert _report(tmp_path, entries)["contradictions"] == []
    nested = (_entry("$CONVENTION.coordinates.transmuralField", "scalar"),)
    report = _report(tmp_path, nested, **{"coordinatesConvention.H": READ_COORDINATES_CONVENTION})
    assert report["contradictions"] == [
        "$CONVENTION.coordinates.transmuralField: catalogue value_kind 'scalar'; the C++ reads word "
        "(coordinatesConvention.H:11)",
    ]


def test_an_unseen_read_is_reviewed_and_a_stale_review_is_a_contradiction(tmp_path):
    reviewed = {"unseen_reads": {"read upstream": ["$PURKINJE_SLAB.depth", "$PURKINJE_SLAB.gone"]}}
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.depth"),), reviewed)
    assert report["contradictions"] == [
        "unseen_reads names $PURKINJE_SLAB.gone, which the catalogue does not list",
    ]


def _mapping(tmp_path, monkeypatch, **files):
    from omnidriver.core.plugin_profile import CxxMapping

    root = _tree(tmp_path, **files)
    monkeypatch.setenv("SCANNED_TREE", str(root.parent))
    return CxxMapping(source_root_variable="SCANNED_TREE", source_root_relative="src", allowlist_path=tmp_path)


def test_a_study_may_set_an_uncatalogued_key_the_cxx_reads_at_that_path(tmp_path, monkeypatch):
    mapping = _mapping(tmp_path, monkeypatch, **{"generatePurkinjeTree.C": READ_VENT_PARAMS})
    catalogued = (_entry(
        "$PURKINJE_TREE.<ventKey>.seed", "vector3", dynamic_path=True, source_refs=("src/generatePurkinjeTree.C",),
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
