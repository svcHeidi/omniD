"""Each solver's builds a plan uses, as the run document's list, and how the preflight judges them."""
from __future__ import annotations

import stat
from pathlib import Path

from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity, driver_context
from omnidriver.core.runtime.solver_provenance import matches, provenance_diagnostics, to_json
from omnidriver.core.strict_planning import strict_plan
from omnidriver.core.tutorial_records import case_folder_record

from plugins.toy import E2EFolderPlugin

HERE = SourceIdentity(repository="/src/here", digest="sha256:" + "a" * 64, git={"commit": "aaa", "dirty": False})
THERE = SourceIdentity(repository="/src/there", digest="sha256:" + "b" * 64, git={"commit": "bbb", "dirty": True})
DIGEST = "sha256:" + "c" * 64


def _build(name, known, source=None):
    return SolverBuild(name=name, path=Path(f"/bin/{name}"), digest=DIGEST, known=known, source=source)


def test_matches_compares_digests_and_is_none_without_both():
    assert matches(_build("s", "recorded", HERE), HERE) is True
    assert matches(_build("s", "recorded", THERE), HERE) is False
    assert matches(_build("s", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})), HERE) is None
    assert matches(_build("s", "recorded", HERE), None) is None


def test_the_list_has_one_item_per_solver_with_every_field():
    entries = (
        SolverEntry(solver="wmakeSolver", repository=HERE, builds=(_build("mySolver", "recorded", THERE),), recordable=True),
        SolverEntry(solver="org.binary", repository=None,
                    builds=(_build("bin", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})),)),
    )
    (first, second) = to_json(entries)
    assert first == {
        "solver": "wmakeSolver", "repository": HERE.to_json(),
        "builds": [{"name": "mySolver", "path": "/bin/mySolver", "digest": DIGEST, "known": "recorded",
                    "source": THERE.to_json(), "matchesRepository": False}],
    }
    assert second["repository"] is None and second["builds"][0]["matchesRepository"] is None


def test_a_build_from_other_source_is_a_stale_build_warning_naming_both_sides():
    entry = SolverEntry(solver="wmakeSolver", repository=HERE,
                        builds=(_build("mySolver", "recorded", THERE), _build("libModels", "recorded", THERE),
                                _build("ok", "recorded", HERE)), recordable=True)
    (warning,) = provenance_diagnostics((entry,))
    assert (warning.level, warning.code) == ("warning", "stale_build")
    for fragment in ("mySolver", "libModels", "/src/there", "bbb", "/src/here", "aaa"):
        assert fragment in warning.message, (fragment, warning.message)
    assert "ok," not in warning.message


def test_an_unknown_build_is_one_info_note_and_a_recordable_one_says_how_to_record():
    entry = SolverEntry(solver="wmakeSolver", repository=HERE,
                        builds=(_build("a", "unknown"), _build("b", "unknown")), recordable=True)
    (note,) = provenance_diagnostics((entry,))
    assert (note.level, note.code) == ("info", "build_source_unknown")
    assert "a, b" in note.message and "omnidriver build-record --repo /src/here" in note.message
    live = SolverEntry(solver="pkg", repository=HERE, builds=(_build("p", "unknown"),))
    (plain,) = provenance_diagnostics((live,))
    assert "build-record" not in plain.message


def test_self_reported_live_and_matching_builds_say_nothing():
    entry = SolverEntry(solver="x", repository=HERE, builds=(
        _build("a", "recorded", HERE), _build("b", "live", HERE),
        _build("c", "self_reported", SourceIdentity(git={"tag": "v1", "commit": "x"})),
    ))
    assert provenance_diagnostics((entry,)) == ()


class _ProvenancePlugin(E2EFolderPlugin):
    def get_solver_builds(self, env, *, repository, used_paths):
        return (SolverEntry(solver="toySolver", repository=HERE,
                            builds=(SolverBuild(name="run-test-case", path=None, digest=None, known="unknown"),),
                            recordable=True),)


def test_a_strict_plan_writes_the_list_and_the_note(tmp_path):
    case = tmp_path / "cases" / "myCase"
    (case / "system").mkdir(parents=True)
    (case / "system" / "input.txt").write_text("authored\n")
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\necho done > ran.marker\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    ctx = driver_context(_ProvenancePlugin(), source="test:provenance")
    record, cases_root = case_folder_record(case, driver_context=ctx)

    report = strict_plan(record, overrides={"cases_root": str(cases_root)}, scratch_root=tmp_path / "scratch",
                         driver_context=ctx)

    document = report.run_document.to_json()
    assert document["solverProvenance"][0]["solver"] == "toySolver"
    assert document["solverProvenance"][0]["builds"][0]["known"] == "unknown"
    assert "build_source_unknown" in [d.code for d in report.environment_diagnostics]
    assert report.status == "ok"


def test_a_stack_with_no_solver_builds_writes_no_list(tmp_path):
    case = tmp_path / "cases" / "plain"
    (case / "system").mkdir(parents=True)
    script = case / "run-test-case"
    script.write_text("#!/bin/sh\n")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    ctx = driver_context(E2EFolderPlugin(), source="test:provenance")
    record, cases_root = case_folder_record(case, driver_context=ctx)
    report = strict_plan(record, overrides={"cases_root": str(cases_root)}, scratch_root=tmp_path / "scratch",
                         driver_context=ctx)
    assert "solverProvenance" not in report.run_document.to_json()
