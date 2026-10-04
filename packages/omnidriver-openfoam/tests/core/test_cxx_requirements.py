"""The keys the supplied C++ requires: the scan's reads of them, and the rule
that judges a case against them."""
from __future__ import annotations

import json
from types import SimpleNamespace

from omnidriver.core.contracts.dictionary import DictEntry
from omnidriver.openfoam import case_rules
from omnidriver.openfoam.case_rules import rule_diagnostics
from omnidriver.openfoam.dict_keys_scanner import DictRead, Scan, _conditional, _guards, required_reads, scan_source

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

# cardiacFOAM src/electroModels/ecgModels/pseudoECGSolver/pseudoECGSolver.C: the registration
# and the constructor, whose reads of the sampling block run only when the block is there.
PSEUDO_ECG_SOLVER = '''defineTypeNameWithName(pseudoECGSolver, "pseudoECG");
defineDebugSwitch(pseudoECGSolver, 0);
addToRunTimeSelectionTable(ecgSolver, pseudoECGSolver, dictionary);


pseudoECGSolver::pseudoECGSolver(const dictionary& dict)
:
    sigmaE_(dict.lookupOrDefault<scalar>("sigmaExtracellular", 0.0)),
    reportedConductivitySource_(false),
    leadVectorsCalculated_(false),
    hasOwnSampling_(false),
    startTime_(0.0),
    endTime_(0.0),
    deltaT_(0.0),
    nextSampleTime_(0.0),
    outputPtr_()
{
    if (const dictionary* samplingDictPtr = dict.findDict("sampling"))
    {
        hasOwnSampling_ = true;

        const dictionary& samplingDict = *samplingDictPtr;
        startTime_ = samplingDict.get<scalar>("start");
        endTime_ = samplingDict.get<scalar>("end");
        deltaT_ = samplingDict.get<scalar>("deltaT");

        if (deltaT_ <= 0.0)
        {
            FatalErrorInFunction
                << "pseudoECG sampling.deltaT must be positive."
                << exit(FatalError);
        }

        nextSampleTime_ = startTime_;
    }
}
'''

ROOT = "param:Solver::Solver:electroProperties"


def _entry(path, **fields):
    return DictEntry(driver_path=path, description="d", **{"value_kind": "word", **fields})


def _read(key, method="get", *, function="Solver::Solver", root=ROOT, selected_as=(), conditional=False):
    return DictRead(
        key=key, method=method, type="word", default=None, scope=(), root=root,
        file="Solver.C", line=3, function=function, selected_as=selected_as, conditional=conditional,
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
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: ({path: reads}, {}, {}, built or {}, set()))
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
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: (
        {path: [_read("depth", selected_as=(("kind", "deep"),))]}, {}, {}, {}, set(),
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


def test_a_read_inside_an_if_is_conditional_and_a_read_in_the_constructor_body_is_not(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "pseudoECGSolver.C").write_text(PSEUDO_ECG_SOLVER)
    (root / "monodomainSolver.C").write_text(MONODOMAIN_SOLVER)
    reads = {r.key: r for r in scan_source(root).reads if r.method in ("get", "lookupOrDefault")}
    assert [reads[k].conditional for k in ("start", "end", "deltaT")] == [True, True, True]
    assert not reads["sigmaExtracellular"].conditional
    assert not reads["sealedHeartBoundary"].conditional


def test_what_runs_only_under_a_condition_of_its_function_is_conditional():
    def conditional(code, marker="X"):
        return _conditional(code, code.index(marker), 0)

    assert conditional("{ if (a) { X } }")
    assert conditional("{ if (a) { } else { X } }")
    assert conditional("{ if (a) { } else if (X) { } }")
    assert conditional("{ if (a) X; }")
    assert conditional("{ switch (a) { case 1: X } }")
    assert conditional("{ for (;;) { X } }")
    assert conditional("{ v = a ? X : 1; }")
    assert conditional("{ ok = a && X; }")
    assert not conditional("{ if (X) { } }")
    assert not conditional("{ if (a) { } X; }")
    assert not conditional("{ { X } }")


def test_a_read_that_runs_only_under_a_branch_is_noted_never_judged_an_error(monkeypatch):
    judge = _facts(monkeypatch, [
        _read("sealedHeartBoundary", selected_as=(("myocardiumSolver", "monodomainSolver"),), conditional=True),
    ])
    (note,) = judge({"myocardiumSolver": "monodomainSolver"})
    assert (note.level, note.code, note.field) == ("info", "cxx_required_key_unjudged", "sealedHeartBoundary")
    assert "only under a condition" in note.message
    assert judge({"myocardiumSolver": "monodomainSolver", "sealedHeartBoundary": "no"}) == []


def test_a_block_builds_a_class_from_its_own_values_not_from_a_sibling_blocks(monkeypatch):
    path = ("$S", "ecgDomains", "<name>", "nBeats")
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: (
        {path: [_read("nBeats", selected_as=(("ecgSolver", "eikonalECG"),))]}, {}, {}, {}, set(),
    ))
    judge = lambda context: [i.field for i in rule_diagnostics((), context, document="doc", mapping=object())]
    both = {"ecgDomains.a.type": "eikonalECG", "ecgDomains.b.type": "pseudoECG"}
    assert judge(both) == ["ecgDomains.a.nBeats"]
    assert judge({"ecgDomains.b.type": "pseudoECG"}) == []
    assert judge({**both, "ecgDomains.a.nBeats": 3}) == []
    assert judge({"ecgDomains.a.type": "pseudoECG", "ecgDomains.b.type": "eikonalECG", "ecgDomains.b.nBeats": 3}) == []


def test_a_required_read_of_the_document_itself_in_a_utilitys_main_is_enforced_whatever_the_case_selects(monkeypatch):
    path = ("fiberField",)
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: (
        {path: [_read("fiberField", function="main", root="document:setCardiacConductivityDict")]}, {}, {}, {}, set(),
    ))
    (found,) = rule_diagnostics((), {}, document="system/setCardiacConductivityDict", mapping=object())
    assert (found.level, found.code, found.field) == ("error", "cxx_required_key", "fiberField")
    assert "the utility reads this document" in found.message
    assert rule_diagnostics((), {"fiberField": "fibers"}, document="system/setCardiacConductivityDict", mapping=object()) == []


def test_a_model_the_cxx_registers_is_accepted_and_one_it_no_longer_registers_is_refused(monkeypatch):
    entry = _entry("$S.ionicModel", value_kind="enum", enum_values=("TNNP", "Retired"))
    registered = {"$S.ionicModel": {"TNNP", "BrandNewModel"}}
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: ({}, registered, {}, {}, set()))

    def judge(value):
        return [i.message for i in rule_diagnostics((entry,), {"ionicModel": value}, document="doc", mapping=object())]

    assert judge("BrandNewModel") == []
    (refused,) = judge("Retired")
    assert "'Retired'" in refused and "the supplied C++ registers" in refused and "BrandNewModel" in refused

    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: ({}, {}, {}, {}, set()))
    assert judge("Retired") == []
    (listed,) = judge("BrandNewModel")
    assert "the catalogue lists" in listed


def test_a_value_the_cxx_compares_is_accepted_beside_the_catalogues_menu(monkeypatch):
    entry = _entry("$S.scheme", value_kind="enum", enum_values=("unweightedHarmonic", "distanceWeightedHarmonic"))
    compared = {"$S.scheme": frozenset({"conormalHarmonic", "unweightedHarmonic"})}
    monkeypatch.setattr(case_rules, "_scan_facts", lambda mapping, entries, document, catalogue: ({}, {}, compared, {}, set()))

    def judge(value):
        return [i.message for i in rule_diagnostics((entry,), {"scheme": value}, document="doc", mapping=object())]

    assert judge("conormalHarmonic") == [] and judge("distanceWeightedHarmonic") == []
    (refused,) = judge("neither")
    assert "the catalogue lists or the supplied C++ compares" in refused and "conormalHarmonic" in refused
