"""What a solver's missing-entry fatal tells an agent: the key, the dictionary, and whether the
binary was built from the source that was scanned."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.plugin_profile import CxxMapping
from omnidriver.openfoam.environment import OpenFOAMEnvironmentPlugin
from omnidriver.openfoam.step_failure import REBUILD_HINT, _document_and_scope, fatal_error_diagnostics

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


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _context(mapping, owned=("electroProperties",)):
    answers = {"get_profile": SimpleNamespace(cxx_mapping=mapping), "get_owned_documents": frozenset(owned)}
    return SimpleNamespace(stack=SimpleNamespace(call=answers.__getitem__))


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
    (found,) = fatal_error_diagnostics(
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
    (found,) = fatal_error_diagnostics(
        RELATIVE.replace("ionicModel", "sealedWallTrace"), case, _context(_mapping(tmp_path, monkeypatch, SCANNED)),
    )
    assert "sealedWallTrace is missing from monodomainSolverCoeffs in constant/electroProperties" in found.message
    assert "built from different source" not in found.message


def test_without_a_supplied_source_the_key_and_dictionary_are_named_and_the_build_is_not_judged(tmp_path, monkeypatch):
    case = _case(tmp_path)
    (found,) = fatal_error_diagnostics(RELATIVE, case, _context(None))
    assert "ionicModel is missing from monodomainSolverCoeffs in constant/electroProperties" in found.message
    assert "built from different source" not in found.message


def test_a_keyword_undefined_fatal_is_read_the_same_way(tmp_path):
    case = _case(tmp_path)
    text = (
        "--> FOAM FATAL IO ERROR: (openfoam-2412)\n"
        'keyword nBeats is undefined in dictionary "constant/electroProperties/monodomainSolverCoeffs/ecgDomains/ECG"\n'
        "\nFOAM exiting\n"
    )
    (found,) = fatal_error_diagnostics(text, case, _context(None))
    assert found.field == "nBeats"
    assert "missing from monodomainSolverCoeffs.ecgDomains.ECG in constant/electroProperties" in found.message


def test_a_log_with_no_fatal_says_nothing(tmp_path):
    assert fatal_error_diagnostics("Floating point exception\n", _case(tmp_path), _context(None)) == ()


NO_FILE = '''
--> FOAM FATAL ERROR: (openfoam-2412)
cannot find file "/case/constant/polyMesh/points"

    From virtual Foam::autoPtr<Foam::ISstream> Foam::fileOperations::uncollatedFileOperation::readStream()
    in file global/fileOperations/uncollatedFileOperation/uncollatedFileOperation.C at line 541.

FOAM exiting
'''


def test_a_fatal_that_is_no_missing_entry_is_carried_whole_and_collapsed_to_one_line(tmp_path):
    (found,) = fatal_error_diagnostics("starting\n" + NO_FILE, _case(tmp_path), _context(None))
    assert found.code == "solver_fatal_error"
    assert 'cannot find file "/case/constant/polyMesh/points"' in found.message
    assert "\n" not in found.message and "FOAM exiting" not in found.message


def test_a_missing_entry_fatal_keeps_its_own_explanation(tmp_path):
    (found,) = fatal_error_diagnostics(RELATIVE, _case(tmp_path), _context(None))
    assert found.code == "solver_entry_missing"


def test_a_log_with_no_fatal_says_nothing_at_all(tmp_path):
    assert fatal_error_diagnostics("Courant Number mean: 0.1\nEnd\n", _case(tmp_path), _context(None)) == ()


def test_the_solver_logs_of_a_step_are_the_log_files_in_its_directory(tmp_path):
    (tmp_path / "log.cardiacFoam").write_text("")
    (tmp_path / "log.blockMesh").write_text("")
    (tmp_path / "Allrun").write_text("")
    assert set(OpenFOAMEnvironmentPlugin().get_step_log_files(tmp_path)) == {
        tmp_path / "log.blockMesh", tmp_path / "log.cardiacFoam",
    }


def _fixture(name):
    return (FIXTURES / f"solver_log.{name}").read_text()


def test_a_function_object_warning_about_a_missing_entry_is_no_failure(tmp_path):
    text = _fixture("function_object_warning")
    assert "Entry 'probeLocations' not found" in text
    assert fatal_error_diagnostics(text, _case(tmp_path), _context(None)) == ()


def test_a_fatal_printed_inside_a_warning_that_ends_in_end_is_no_failure(tmp_path):
    text = _fixture("fatal_inside_warning")
    assert "--> FOAM FATAL IO ERROR" in text and text.rstrip().endswith("End")
    assert fatal_error_diagnostics(text, _case(tmp_path), _context(None)) == ()


def test_the_fatal_a_real_solver_exited_on_is_found_in_its_log(tmp_path):
    case = _case(tmp_path)
    (found,) = fatal_error_diagnostics(_fixture("niederer_fatal"), case, _context(None))
    assert (found.code, found.field) == ("solver_entry_missing", "sealedHeartBoundary")
    assert "missing from monodomainSolverCoeffs in " in found.message and found.source.endswith("constant/electroProperties")


def test_a_warning_before_the_fatal_does_not_hide_it(tmp_path):
    text = _fixture("function_object_warning") + NO_FILE
    (found,) = fatal_error_diagnostics(text, _case(tmp_path), _context(None))
    assert found.code == "solver_fatal_error" and "polyMesh/points" in found.message


def test_a_key_outside_the_documents_a_provider_owns_gets_no_claim_about_the_build(tmp_path, monkeypatch):
    case = _case(tmp_path)
    text = RELATIVE.replace("constant/electroProperties/monodomainSolverCoeffs", "system/controlDict/functions/probes")
    (found,) = fatal_error_diagnostics(text, case, _context(_mapping(tmp_path, monkeypatch, SCANNED)))
    assert found.code == "solver_entry_missing"
    assert "scanned source" not in found.message


PARALLEL = '''
[1] 
[1] 
[1] --> FOAM FATAL ERROR: (openfoam-2412)
[1] cannot find file "/case/processor1/constant/polyMesh/points"
[1] 
[1] FOAM parallel run exiting
[1] 
'''


def test_a_parallel_fatal_is_read_without_its_rank_prefixes(tmp_path):
    (found,) = fatal_error_diagnostics(PARALLEL, _case(tmp_path), _context(None))
    assert found.message.endswith('cannot find file "/case/processor1/constant/polyMesh/points"')
    assert "[1]" not in found.message


def test_a_log_naming_a_case_that_has_moved_is_read_against_this_case(tmp_path):
    moved = "/elsewhere/records/x/constant/electroProperties/monodomainSolverCoeffs"
    assert _document_and_scope(moved, _case(tmp_path)) == ("constant/electroProperties", ["monodomainSolverCoeffs"])
