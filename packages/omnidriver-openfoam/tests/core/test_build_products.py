"""What a wmake repository builds, which files a build reads, and how its builds are judged."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from omnidriver.core.runtime.build_identity import write_records
from omnidriver.core.runtime.solver_provenance import provenance_diagnostics, to_json
from omnidriver.openfoam.build_products import (
    build_source_files, products, source_identity, wmake_solver_builds,
)


def _repository(root: Path) -> Path:
    (root / "applications" / "solvers" / "myFoam" / "Make").mkdir(parents=True)
    (root / "applications" / "solvers" / "myFoam" / "myFoam.C").write_text("int main() {}\n")
    (root / "applications" / "solvers" / "myFoam" / "Make" / "files").write_text(
        "myFoam.C\n\nEXE = $(FOAM_USER_APPBIN)/myFoam\n")
    (root / "applications" / "solvers" / "myFoam" / "Make" / "options").write_text("EXE_INC =\n")
    (root / "src" / "models" / "Make").mkdir(parents=True)
    (root / "src" / "models" / "model.H").write_text("// model\n")
    (root / "src" / "models" / "Make" / "files").write_text("model.C\n\nLIB = $(FOAM_USER_LIBBIN)/libmodels\n")
    (root / "src" / "models" / "lnInclude").mkdir()
    (root / "src" / "models" / "lnInclude" / "model.H").write_text("// link\n")
    (root / "tutorials" / "case").mkdir(parents=True)
    (root / "tutorials" / "case" / "Allrun").write_text("#!/bin/sh\n")
    return root


def _install(tmp_path: Path) -> dict[str, str]:
    appbin, libbin = tmp_path / "platform" / "bin", tmp_path / "platform" / "lib"
    appbin.mkdir(parents=True)
    libbin.mkdir(parents=True)
    (appbin / "myFoam").write_bytes(b"solver")
    (libbin / "libmodels.dylib").write_bytes(b"library")
    return {"FOAM_USER_APPBIN": str(appbin), "FOAM_USER_LIBBIN": str(libbin), "PATH": str(appbin)}


def _repo(root: Path):
    return SimpleNamespace(root=root, plugin="mySolver")


def test_the_build_reads_sources_and_make_files_but_not_tutorials_or_links(tmp_path):
    root = _repository(tmp_path / "repo")
    relative = sorted(p.relative_to(root).as_posix() for p in build_source_files(root))
    assert relative == [
        "applications/solvers/myFoam/Make/files", "applications/solvers/myFoam/Make/options",
        "applications/solvers/myFoam/myFoam.C", "src/models/Make/files", "src/models/model.H",
    ]


def test_a_tutorial_edit_keeps_the_digest_and_a_build_option_edit_changes_it(tmp_path):
    root = _repository(tmp_path / "repo")
    before = source_identity(root).digest
    (root / "tutorials" / "case" / "Allrun").write_text("#!/bin/sh\necho changed\n")
    assert source_identity(root).digest == before
    (root / "applications" / "solvers" / "myFoam" / "Make" / "options").write_text("EXE_INC = -O3\n")
    assert source_identity(root).digest != before


def test_products_come_from_make_files_and_land_in_the_user_platform(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    assert products(root, env) == [
        ("myFoam", Path(env["FOAM_USER_APPBIN"]) / "myFoam"),
        ("libmodels", Path(env["FOAM_USER_LIBBIN"]) / "libmodels.dylib"),
    ]
    (Path(env["FOAM_USER_APPBIN"]) / "myFoam").unlink()
    assert products(root, env)[0] == ("myFoam", None)


def test_a_recorded_build_from_this_repository_matches_and_says_nothing(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    write_records(entry.builds, entry.repository)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    assert {b.known for b in entry.builds} == {"recorded"}
    assert all(item["matchesRepository"] for item in to_json((entry,))[0]["builds"])
    assert provenance_diagnostics((entry,)) == ()


def test_a_build_recorded_from_another_tree_is_a_stale_build(tmp_path):
    built_from = _repository(tmp_path / "worktree")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(built_from), used_paths=None)
    write_records(entry.builds, entry.repository)
    planned = _repository(tmp_path / "archive")
    (planned / "src" / "models" / "model.H").write_text("// other source\n")
    (entry,) = wmake_solver_builds(env, repository=_repo(planned), used_paths=None)
    (warning,) = provenance_diagnostics((entry,))
    assert warning.code == "stale_build"
    assert str(built_from.resolve()) in warning.message and str(planned.resolve()) in warning.message


def test_an_unrecorded_or_rebuilt_product_is_unknown_with_the_command_to_record_it(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    (note,) = provenance_diagnostics((entry,))
    assert note.code == "build_source_unknown"
    assert f"omnidriver build-record --repo {root.resolve()}" in note.message
    write_records(entry.builds, entry.repository)
    (Path(env["FOAM_USER_APPBIN"]) / "myFoam").write_bytes(b"rebuilt, not recorded")
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=None)
    assert {b.name: b.known for b in entry.builds} == {"myFoam": "unknown", "libmodels": "recorded"}


def test_only_products_the_plan_runs_are_listed_even_through_a_symlink_on_path(tmp_path):
    root = _repository(tmp_path / "repo")
    env = _install(tmp_path)
    link = tmp_path / "linkbin" / "myFoam"
    link.parent.mkdir()
    link.symlink_to(Path(env["FOAM_USER_APPBIN"]) / "myFoam")
    (entry,) = wmake_solver_builds(env, repository=_repo(root), used_paths=frozenset({link.resolve()}))
    assert [b.name for b in entry.builds] == ["myFoam"]
    assert wmake_solver_builds(env, repository=_repo(root), used_paths=frozenset({tmp_path / "blockMesh"})) == ()


def test_no_repository_or_no_make_files_is_no_entry(tmp_path):
    env = _install(tmp_path)
    assert wmake_solver_builds(env, repository=None, used_paths=None) == ()
    (tmp_path / "cases").mkdir()
    assert wmake_solver_builds(env, repository=_repo(tmp_path / "cases"), used_paths=None) == ()
