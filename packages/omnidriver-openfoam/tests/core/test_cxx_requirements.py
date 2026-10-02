"""The keys the supplied C++ requires: the scan's reads of them, and the rule
that judges a case against them."""
from __future__ import annotations

import json
from types import SimpleNamespace

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam import case_rules
from omnidriver.openfoam.case_rules import rule_diagnostics
from omnidriver.openfoam.dict_keys_scanner import DictRead, Scan, _guards, required_reads, scan_source

# cardiacFOAM src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C:
# the registration and the constructor.
MONODOMAIN_SOLVER = '''defineTypeNameAndDebug(monodomainSolver, 0);
addToRunTimeSelectionTable
(
    myocardiumSolver,
    monodomainSolver,
    dictionary
);


monodomainSolver::monodomainSolver
(
    const fvMesh& mesh,
    const fvMesh& supportMesh,
    const fvMeshSubset* meshSubsetPtr,
    const dictionary& electroProperties
)
:
    conductivity_
    (
        initialiseConductivity
        (
            mesh,
            supportMesh,
            meshSubsetPtr,
            electroProperties
        )
    ),
    sealedHeartBoundary_
    (
        electroProperties.get<Switch>("sealedHeartBoundary")
    )
{}
'''

# cardiacFOAM src/electroModels/electroDomains/myocardiumDomain/myocardiumSolver.C:
# the selector, which hands its dictionary to the constructor of the class it selects.
MYOCARDIUM_SOLVER_NEW = '''autoPtr<myocardiumSolver> myocardiumSolver::New
(
    const fvMesh& mesh,
    const fvMesh& supportMesh,
    const fvMeshSubset* meshSubsetPtr,
    const word& solverType,
    const dictionary& coeffs
)
{


    auto* ctorPtr = dictionaryConstructorTable(solverType);

    if (!ctorPtr)
    {
        FatalIOErrorInLookup
        (
            coeffs,
            "myocardiumSolver",
            solverType,
            *dictionaryConstructorTablePtr_
        ) << exit(FatalIOError);
    }

    return autoPtr<myocardiumSolver>
    (
        ctorPtr(mesh, supportMesh, meshSubsetPtr, coeffs)
    );
}
'''

# cardiacFOAM src/electroModels/electroDomains/myocardiumDomain/myocardiumDomainInterface.C:
# the selector's head, to the end of the eikonal branch (the function's closing brace added).
MYOCARDIUM_DOMAIN_INTERFACE_NEW = '''autoPtr<myocardiumDomainInterface> myocardiumDomainInterface::New
(
    const fvMesh& mesh,
    const dictionary& electroProperties,
    PtrList<volScalarField>& outFields,
    const wordList& postProcessFieldNames,
    PtrList<volScalarField>& postProcessFields,
    autoPtr<ionicModel>& ionicModelPtr,
    autoPtr<electroVerificationModel>& verificationModelPtr,
    scalar initialDeltaT
)
{
    const word solverType = myocardiumSolverType(electroProperties);

    if (solverType == "eikonalSolver")
    {
        ionicModelPtr.clear();
        verificationModelPtr.clear();

        return autoPtr<myocardiumDomainInterface>
        (
            new eikonalMyocardiumDomain(mesh, electroProperties)
        );
    }
}
'''

# cardiacFOAM src/ionicModels/ionicModel/ionicModel.C: the selector reading its model by
# lookup, a destructor, and utilitiesMode, which tests a key with found() before it reads it.
IONIC_MODEL = '''Foam::autoPtr<Foam::ionicModel> Foam::ionicModel::New(
    const dictionary& dict, const label nIntegrationPoints,
    const scalar initialDeltaT, const Switch solveVmWithinODESolver)
{
    const word modelType(dict.lookup("ionicModel"));
    auto *ctorPtr = dictionaryConstructorTable(modelType);

    if (!ctorPtr)
    {
        FatalIOErrorInLookup(dict, "ionicModel", modelType,
                             *dictionaryConstructorTablePtr_)
            << exit(FatalIOError);
    }

    return autoPtr<ionicModel>
    (
        ctorPtr(dict, nIntegrationPoints, initialDeltaT, solveVmWithinODESolver)
    );
}

// * * * * * * * * * * * * * * * * Destructor  * * * * * * * * * * * * * * * //

Foam::ionicModel::~ionicModel()
{}

// * * * * * * * * * * * * * * * Member Functions  * * * * * * * * * * * * * //


bool Foam::ionicModel::utilitiesMode() const
{
    return dict_.found("utilities")
        && readBool(dict_.lookup("utilities"));
}
'''

ROOT = "param:Solver::Solver:electroProperties"


def _entry(path, **fields):
    return DictEntry(driver_path=path, description="d", **{"value_kind": "word", **fields})


def _read(key, method="get", *, function="Solver::Solver", root=ROOT, selected_as=()):
    return DictRead(
        key=key, method=method, type="word", default=None, scope=(), root=root,
        file="Solver.C", line=3, function=function, selected_as=selected_as,
    )


def test_the_selector_hands_its_dictionary_to_the_constructor_of_every_registered_class(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "monodomainSolver.C").write_text(MONODOMAIN_SOLVER)
    (root / "myocardiumSolver.C").write_text(MYOCARDIUM_SOLVER_NEW)
    scan = scan_source(root)
    assert scan.registrations == {"myocardiumSolver": {"monodomainSolver": "monodomainSolver"}}
    assert ("monodomainSolver::monodomainSolver", 3, 4, "param:myocardiumSolver::New:coeffs", ()) in scan.calls
    (read,) = [r for r in scan.reads if r.key == "sealedHeartBoundary"]
    assert (read.method, read.type, read.selected_as) == ("get", "Switch", (("myocardiumSolver", "monodomainSolver"),))


def test_a_class_built_only_inside_an_if_on_a_literal_is_tied_to_that_literal(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "myocardiumDomainInterface.C").write_text(MYOCARDIUM_DOMAIN_INTERFACE_NEW)
    assert scan_source(root).dispatch == (("eikonalMyocardiumDomain", "eikonalSolver"),)


def test_a_lookup_is_typed_by_its_wrapper_and_a_key_tested_first_is_not_required(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "ionicModel.C").write_text(IONIC_MODEL)
    scan = scan_source(root)
    (model,) = [read for read in scan.reads if read.key == "ionicModel"]
    assert (model.method, model.type, model.default, model.scope) == ("lookup", "word", None, ())
    (utilities,) = [read for read in scan.reads if read.key == "utilities" and read.method == "lookup"]
    assert (utilities.file, utilities.function, utilities.root, utilities.scope, utilities.key) in _guards(scan)


def test_only_a_read_without_a_default_that_nothing_tests_first_is_required():
    reads = (
        _read("state"), _read("tissue", "getOrDefault"), _read("patch"), _read("patch", "found"),
        _read("depth", "get", function="Other::Other"), _read("depth", "found", function="Third::Third"),
    )
    scan = Scan(digest="d", reads=reads, registrations={})
    catalogued = (_entry("$S.state", source_refs=("src/Solver.C",)),)
    assert list(required_reads(scan, catalogued, document="doc")) == [("$S", "depth")]


def _facts(monkeypatch, reads, *, built=None):
    path = ("$S", "sealedHeartBoundary")
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document: ({path: reads}, {}, built or {}, set()))
    return lambda context: rule_diagnostics((), context, document="constant/electroProperties", mapping=object())


def test_a_class_the_case_selects_requires_its_key(monkeypatch):
    judge = _facts(monkeypatch, [_read("sealedHeartBoundary", selected_as=(("myocardiumSolver", "monodomainSolver"),))])
    (found,) = judge({"myocardiumSolver": "monodomainSolver"})
    assert (found.level, found.code, found.field) == ("error", "cxx_required_key", "sealedHeartBoundary")
    for fragment in ("get<word>", "Solver.C:3", "Solver::Solver", "catalogue does not list it"):
        assert fragment in found.message, (fragment, found.message)
    assert judge({"myocardiumSolver": "monodomainSolver", "sealedHeartBoundary": "no"}) == []
    assert judge({"myocardiumSolver": "bidomainSolver"}) == []


def test_a_class_no_table_registers_is_judged_only_when_the_plugin_says_the_case_builds_it(monkeypatch):
    judge = _facts(
        monkeypatch, [_read("sealedHeartBoundary", function="eikonalDomain::eikonalDomain")],
        built={"eikonalDomain": frozenset({"eikonalSolver"})},
    )
    assert [item.field for item in judge({"myocardiumSolver": "eikonalSolver"})] == ["sealedHeartBoundary"]
    assert judge({"myocardiumSolver": "monodomainSolver"}) == []

    unknown = _facts(monkeypatch, [_read("sealedHeartBoundary", function="otherDomain::otherDomain")])
    (note,) = unknown({"myocardiumSolver": "eikonalSolver"})
    assert (note.level, note.code, note.field) == ("info", "cxx_required_key_unjudged", "sealedHeartBoundary")
    assert "cannot tell whether this case builds the class" in note.message
    assert "otherDomain::otherDomain" in note.message
    assert unknown({"myocardiumSolver": "eikonalSolver", "sealedHeartBoundary": "no"}) == []


def test_each_instance_of_a_block_the_case_holds_must_set_the_key(monkeypatch):
    path = ("$S", "domains", "<name>", "depth")
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document: (
        {path: [_read("depth", selected_as=(("kind", "deep"),))]}, {}, {}, set(),
    ))
    context = {"domains.a.kind": "deep", "domains.a.depth": 3, "domains.b.kind": "deep"}
    assert [item.field for item in rule_diagnostics((), context, document="doc", mapping=object())] == ["domains.b.depth"]
    assert rule_diagnostics((), {}, document="doc", mapping=object()) == []


def test_a_catalogued_required_key_the_cxx_no_longer_reads_is_not_demanded_of_a_case(tmp_path, monkeypatch):
    from omnidriver.core.plugin_profile import CxxMapping

    root = tmp_path / "tree" / "src"
    root.mkdir(parents=True)
    (root / "monodomainSolver.C").write_text(MONODOMAIN_SOLVER)
    (tmp_path / "reviewed.json").write_text("{}")
    monkeypatch.setenv("TREE", str(tmp_path / "tree"))
    mapping = CxxMapping(source_root_variable="TREE", source_root_relative="src", allowlist_path=tmp_path / "reviewed.json")
    retired = _entry("$S.retiredKey", required=True)
    assert [item.field for item in rule_diagnostics((retired,), {}, document="doc")] == ["retiredKey"]
    assert rule_diagnostics((retired,), {}, document="doc", mapping=mapping) == []
