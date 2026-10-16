"""The build record beside a product: what a stack whose binaries cannot identify themselves keeps."""
from __future__ import annotations

import json

from omnidriver.core.plugin_interface import SolverBuild, SourceIdentity
from omnidriver.core.runtime.build_identity import (
    RECORD_FILENAME, file_digest, recorded_build, write_records,
)

SOURCE = SourceIdentity(repository="/src/a", digest="sha256:" + "a" * 64, git={"commit": "c1", "dirty": False})
OTHER = SourceIdentity(repository="/src/b", digest="sha256:" + "b" * 64, git=None)


def _product(directory, name, content=b"bin"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(content)
    return SolverBuild(name=name, path=path, digest=file_digest(path), known="unknown")


def test_a_recorded_product_is_read_back_with_its_source(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    (written,) = write_records([build], SOURCE).records
    assert written == tmp_path / "bin" / RECORD_FILENAME
    payload = json.loads(written.read_text())
    assert payload["version"] == 1
    assert payload["products"]["mySolver"]["digest"] == build.digest
    assert payload["products"]["mySolver"]["source"] == SOURCE.to_json()

    read = recorded_build("mySolver", build.path)
    assert (read.known, read.digest, read.source) == ("recorded", build.digest, SOURCE)


def test_a_product_rebuilt_after_recording_is_unknown(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    write_records([build], SOURCE)
    build.path.write_bytes(b"rebuilt")
    read = recorded_build("mySolver", build.path)
    assert (read.known, read.source) == ("unknown", None)
    assert read.digest == file_digest(build.path)


def test_no_record_or_no_file_is_unknown(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    assert recorded_build("mySolver", build.path).known == "unknown"
    absent = recorded_build("gone", tmp_path / "bin" / "gone")
    assert (absent.known, absent.digest) == ("unknown", None)
    assert recorded_build("none", None).path is None


def test_a_malformed_record_is_no_record_and_is_replaced(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    (tmp_path / "bin" / RECORD_FILENAME).write_text("{not json")
    assert recorded_build("mySolver", build.path).known == "unknown"
    write_records([build], SOURCE)
    assert recorded_build("mySolver", build.path).known == "recorded"


def test_recording_one_worktree_keeps_the_other_worktrees_entries(tmp_path):
    first = _product(tmp_path / "bin", "solverA", b"a")
    second = _product(tmp_path / "bin", "solverB", b"b")
    write_records([first], SOURCE)
    write_records([second], OTHER)
    assert recorded_build("solverA", first.path).source == SOURCE
    assert recorded_build("solverB", second.path).source == OTHER


def test_products_in_two_directories_get_one_record_each_and_absent_builds_none(tmp_path):
    app = _product(tmp_path / "bin", "mySolver")
    lib = _product(tmp_path / "lib", "libModels.so")
    missing = SolverBuild(name="never", path=None, digest=None, known="unknown")
    written = write_records([app, lib, missing], SOURCE).records
    assert sorted(written) == sorted([tmp_path / "bin" / RECORD_FILENAME, tmp_path / "lib" / RECORD_FILENAME])
    assert not (tmp_path / "bin" / (RECORD_FILENAME + ".tmp")).exists()


def test_a_partial_rebuild_in_another_worktree_keeps_the_products_it_did_not_rebuild(tmp_path):
    solver = _product(tmp_path / "bin", "mySolver", b"solver from a")
    lib = _product(tmp_path / "lib", "libModels", b"lib from a")
    write_records([solver, lib], SOURCE)

    rebuilt_lib = _product(tmp_path / "lib", "libModels", b"lib from b")
    unchanged_solver = SolverBuild(name="mySolver", path=solver.path, digest=file_digest(solver.path), known="unknown")
    result = write_records([unchanged_solver, rebuilt_lib], OTHER)

    assert recorded_build("mySolver", solver.path).source == SOURCE
    assert recorded_build("libModels", lib.path).source == OTHER
    assert [b.name for b in result.recorded] == ["libModels"]
    assert [(b.name, b.source) for b in result.kept] == [("mySolver", SOURCE)]
    assert result.records == (tmp_path / "lib" / RECORD_FILENAME,)


def test_an_entry_whose_source_is_missing_or_malformed_is_no_record(tmp_path):
    build = _product(tmp_path / "bin", "mySolver")
    well_formed = SOURCE.to_json()
    sources = [
        None,
        {**well_formed, "git": {"commit": "c1", "dirty": False, "branch": "main"}},
        {**well_formed, "git": {"commit": 1, "dirty": False}},
        {**well_formed, "git": {"commit": "c1", "dirty": "no"}},
        {**well_formed, "digest": "md5:abc"},
        {**well_formed, "digest": None},
        {**well_formed, "repository": 7},
    ]
    for source in sources:
        entry = {"digest": build.digest, "recordedAt": "2026-10-16T00:00:00+00:00"}
        if source is not None:
            entry["source"] = source
        (tmp_path / "bin" / RECORD_FILENAME).write_text(
            json.dumps({"version": 1, "products": {"mySolver": entry}}))
        read = recorded_build("mySolver", build.path)
        assert (read.known, read.source) == ("unknown", None), source
        assert [b.name for b in write_records([build], SOURCE).recorded] == ["mySolver"]
        assert recorded_build("mySolver", build.path).source == SOURCE
