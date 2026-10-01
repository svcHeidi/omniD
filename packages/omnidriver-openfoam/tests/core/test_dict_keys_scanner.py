"""The C++ scan on verbatim snippets of the native trees, each named by its
file; the whole trees are covered by the ``native`` and
``native_cardiaccore`` tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam.dict_keys_scanner import cached_scan, catalog_report, scan_source
from omnidriver.openfoam.record_key_validation import scanned_key

# cardiacCore src/setPurkinjeSlab/setPurkinjeSlab.C, lines 1-45 and the close.
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

# cardiacCore src/coordinatesConvention/coordinatesConvention.H, lines 88-111.
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

# cardiacFOAM src/genericWriter/stimulusIO.C, lines 1-37 (licence header
# shortened to its first three lines, which keeps it a block comment).
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

# cardiacFOAM src/genericWriter/conductivityFieldIO.C, lines 173-196.
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

# cardiacCore src/generatePurkinjeTree/generatePurkinjeTree.C, lines 1411-1419
# and 1550-1557, inside main.
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

# cardiacFOAM src/ionicModels/ionicModel/configuredBatchedIonicModel.H,
# lines 147-157, in its class body.
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
    assert (thickness.method, thickness.type, thickness.default, thickness.required) == (
        "getOrDefault", "scalar", "0.1", False,
    )
    assert (thickness.root, thickness.scope, thickness.line) == ("document:setPurkinjeSlabDict", (), 44)


def test_a_local_alias_carries_its_subdictionary_scope(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"coordinatesConvention.H": READ_COORDINATES_CONVENTION}))
    field = _read(scan, "transmuralField")
    assert (field.root, field.scope, field.type) == ("conventionDict", ("coordinates",), "word")
    assert _read(scan, "coordinates").method == "subOrEmptyDict"


def test_line_numbers_survive_a_block_comment_and_a_guarded_subdict_is_optional(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"stimulusIO.C": STIMULUS_IO}))
    subdict = _read(scan, "singleCellStimulus", "subDict")
    assert (subdict.line, subdict.required) == (22, False)
    assert subdict.function == "singleCellStimulusDict"


def test_a_found_guard_makes_a_read_optional_and_a_wrapper_gives_its_type(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"conductivityFieldIO.C": READ_CONDUCTIVITY_FIELD}))
    source = _read(scan, "conductivitySource", "lookup")
    assert (source.type, source.required, source.root) == ("word", False, "coefficients")


def test_a_fatal_absence_branch_keeps_a_read_required_and_a_dynamic_segment_is_any(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"generatePurkinjeTree.C": READ_VENT_PARAMS}))
    count = _read(scan, "terminalCount", "get")
    assert (count.required, count.type, count.scope) == (True, "label", ("*",))
    assert count.root == "document:generatePurkinjeTreeDict"


def test_a_receiver_declared_as_another_type_is_not_a_dictionary_read(tmp_path):
    scan = scan_source(_tree(tmp_path, **{"configuredBatchedIonicModel.H": CONFIGURE_HETEROGENEITY}))
    assert scan.reads == ()


def test_the_scan_is_cached_by_content_digest(tmp_path):
    root = _tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    cache = tmp_path / "scratch"
    first = cached_scan(root, cache_root=cache)
    assert (cache / "cxx-scan" / f"{first.digest}.json").is_file()
    assert cached_scan(root, cache_root=cache) is first
    (root / "setPurkinjeSlab.C").write_text(SET_PURKINJE_SLAB.replace('"multiplier"', '"slabMultiplier"'))
    second = cached_scan(root, cache_root=cache)
    assert second.digest != first.digest
    assert any(read.key == "slabMultiplier" for read in second.reads)


def _entry(path: str, kind: str = "scalar", **fields) -> DictEntry:
    return DictEntry(driver_path=path, description="", value_kind=kind, **fields)


def _report(tmp_path, entries, reviewed=None):
    root = _tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB})
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
    report = _report(tmp_path, (
        _entry("$PURKINJE_SLAB.thickness", "integer"),
        _entry("$PURKINJE_SLAB.multiplier", "word"),
        _entry("$PURKINJE_SLAB.depth", required=True),
    ))
    assert report["status"] == "failed"
    assert [item.split(":")[0] for item in report["contradictions"]] == [
        "$PURKINJE_SLAB.multiplier", "$PURKINJE_SLAB.depth",
    ]
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.thickness", required=True),))
    assert "the C++ gives it a default (0.1" in report["contradictions"][0]


def test_an_unseen_read_is_reviewed_and_a_stale_review_is_a_contradiction(tmp_path):
    reviewed = {"unseen_reads": {"read upstream": ["$PURKINJE_SLAB.depth", "$PURKINJE_SLAB.gone"]}}
    report = _report(tmp_path, (_entry("$PURKINJE_SLAB.depth"),), reviewed)
    assert report["contradictions"] == [
        "unseen_reads names $PURKINJE_SLAB.gone, which the catalogue does not list",
    ]


def test_a_study_may_set_an_uncatalogued_key_the_cxx_reads(tmp_path, monkeypatch):
    root = _tree(tmp_path, **{"setPurkinjeSlab.C": SET_PURKINJE_SLAB})
    monkeypatch.setenv("SLAB_TREE", str(root.parent))
    from omnidriver.core.plugin_profile import CxxMapping

    mapping = CxxMapping(source_root_variable="SLAB_TREE", source_root_relative="src", allowlist_path=tmp_path)
    catalogued = (_entry("$PURKINJE_SLAB.thickness"),)
    document = "system/setPurkinjeSlabDict"
    assert scanned_key(document, ("multiplier",), 2.5, mapping=mapping, entries=catalogued) == ("scalar", True)
    with pytest.raises(ValueError, match="reads it as scalar"):
        scanned_key(document, ("multiplier",), "high", mapping=mapping, entries=catalogued)
    assert scanned_key(document, ("multiplyer",), 2.5, mapping=mapping, entries=catalogued) is None
    assert scanned_key("system/otherDict", ("multiplier",), 2.5, mapping=mapping, entries=catalogued) is None
    assert scanned_key(document, ("deep", "thickness"), 2.5, mapping=mapping, entries=catalogued) is None
    monkeypatch.delenv("SLAB_TREE")
    assert scanned_key(document, ("multiplier",), 2.5, mapping=mapping, entries=catalogued) is None
