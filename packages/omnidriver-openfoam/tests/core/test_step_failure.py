"""What a solver's missing-entry fatal tells an agent: the key, the dictionary, and whether the
binary was built from the source that was scanned."""
from __future__ import annotations

from types import SimpleNamespace

from omnidriver.core.plugin_profile import CxxMapping
from omnidriver.openfoam.step_failure import REBUILD_HINT, missing_entry_diagnostics

# cardiacFoam (built from a branch that reads sealedHeartBoundary) on a case whose electroProperties
# lacks the key: the end of the step's stderr.
ABSOLUTE = '''

--> FOAM FATAL IO ERROR: (openfoam-2412)
Entry 'sealedHeartBoundary' not found in dictionary "{case}/constant/electroProperties/monodomainSolverCoeffs"


file: constant/electroProperties/monodomainSolverCoeffs at line 22 to 57.

    From bool Foam::dictionary::readEntry(const word &, T &, enum keyType::option, IOobjectOption::readOption) const [T = Foam::Switch]
    in file /Volumes/OpenFOAM-v2412/src/OpenFOAM/lnInclude/dictionaryTemplates.C at line 327.

FOAM exiting
'''

# The same solver on a case that lacks ionicModel, which it reads with lookup: the dictionary is
# printed relative to the case.
RELATIVE = '''
--> FOAM FATAL IO ERROR: (openfoam-2412)
Entry 'ionicModel' not found in dictionary "constant/electroProperties/monodomainSolverCoeffs"


file: constant/electroProperties/monodomainSolverCoeffs at line 22 to 58.

    From const Foam::entry &Foam::dictionary::lookupEntry(const word &, enum keyType::option) const
    in file db/dictionary/dictionary.C at line 363.

FOAM exiting
'''

# cardiacFOAM src/electroModels/myocardiumModels/monodomainSolver/monodomainSolver.C: the constructor.
SCANNED = '''defineTypeNameAndDebug(monodomainSolver, 0);
monodomainSolver::monodomainSolver(const dictionary& electroProperties)
:
    sealedWall_(electroProperties.get<word>("sealedWallTrace"))
{}
'''


def _context(mapping):
    return SimpleNamespace(capabilities=SimpleNamespace(
        cxx_mapping=SimpleNamespace(profile=lambda: SimpleNamespace(cxx_mapping=mapping)),
    ))


def _mapping(tmp_path, monkeypatch, source):
    tree = tmp_path / "tree"
    (tree / "src").mkdir(parents=True)
    if source:
        (tree / "src" / "monodomainSolver.C").write_text(source)
    (tmp_path / "reviewed.json").write_text("{}")
    monkeypatch.setenv("TREE", str(tree))
    return CxxMapping(source_root_variable="TREE", source_root_relative="src", allowlist_path=tmp_path / "reviewed.json")


def _case(tmp_path):
    case = tmp_path / "case"
    (case / "constant").mkdir(parents=True)
    (case / "constant" / "electroProperties").write_text("monodomainSolverCoeffs {}\n")
    return case


def test_the_key_and_the_dictionary_are_named_and_a_key_the_scanned_source_never_reads_says_the_binary_is_from_other_source(
    tmp_path, monkeypatch,
):
    case = _case(tmp_path)
    (found,) = missing_entry_diagnostics(
        ABSOLUTE.format(case=case.resolve()), case, _context(_mapping(tmp_path, monkeypatch, SCANNED)),
    )
    assert (found.level, found.code, found.field, found.source) == (
        "error", "solver_entry_missing", "sealedHeartBoundary", "constant/electroProperties",
    )
    assert "sealedHeartBoundary is missing from monodomainSolverCoeffs in constant/electroProperties" in found.message
    assert found.message.endswith(f"{REBUILD_HINT}.")
    assert "the solver binary reads keys the scanned source does not" in found.message


def test_a_key_the_scanned_source_reads_carries_no_claim_about_the_build(tmp_path, monkeypatch):
    case = _case(tmp_path)
    (found,) = missing_entry_diagnostics(
        RELATIVE.replace("ionicModel", "sealedWallTrace"), case, _context(_mapping(tmp_path, monkeypatch, SCANNED)),
    )
    assert "sealedWallTrace is missing from monodomainSolverCoeffs in constant/electroProperties" in found.message
    assert "built from different source" not in found.message


def test_without_a_supplied_source_the_key_and_dictionary_are_named_and_the_build_is_not_judged(tmp_path, monkeypatch):
    case = _case(tmp_path)
    (found,) = missing_entry_diagnostics(RELATIVE, case, _context(None))
    assert "ionicModel is missing from monodomainSolverCoeffs in constant/electroProperties" in found.message
    assert "built from different source" not in found.message


def test_a_keyword_undefined_fatal_is_read_the_same_way(tmp_path):
    case = _case(tmp_path)
    text = 'keyword nBeats is undefined in dictionary "constant/electroProperties/monodomainSolverCoeffs/ecgDomains/ECG"\n'
    (found,) = missing_entry_diagnostics(text, case, _context(None))
    assert found.field == "nBeats"
    assert "missing from monodomainSolverCoeffs.ecgDomains.ECG in constant/electroProperties" in found.message


def test_a_log_with_no_missing_entry_says_nothing(tmp_path):
    assert missing_entry_diagnostics("Floating point exception\n", _case(tmp_path), _context(None)) == ()
