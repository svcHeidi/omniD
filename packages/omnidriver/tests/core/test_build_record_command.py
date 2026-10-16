"""`omnidriver build-record`: record what a repository built, for a stack whose binaries cannot identify themselves."""
from __future__ import annotations

from types import SimpleNamespace

from cli_refusal import refusal
from omnidriver.core import provider_stack
from omnidriver.core.plugin_interface import SolverBuild, SolverEntry, SourceIdentity
from omnidriver.core.runtime.build_identity import (
    RECORD_FILENAME, build_record_report, file_digest, recorded_build, write_records,
)

SOURCE = SourceIdentity(repository="/src/a", digest="sha256:" + "a" * 64, git=None)


def _context(provider, root):
    return SimpleNamespace(
        stack=provider_stack.ProviderStack(provider_stack.order_providers((provider,))),
        repository=SimpleNamespace(root=root, plugin="toySolver"),
    )


def test_a_recordable_stack_records_what_exists_and_lists_what_was_not_built(tmp_path):
    binary = tmp_path / "bin" / "mySolver"
    binary.parent.mkdir()
    binary.write_bytes(b"bin")

    class _Wmake:
        plugin_id = "org.wmake"
        plugin_api_version = "3"

        def get_solver_builds(self, env, *, repository, used_paths):
            assert used_paths is None
            return (SolverEntry(solver="toySolver", repository=SOURCE, recordable=True, builds=(
                SolverBuild(name="mySolver", path=binary, digest=file_digest(binary), known="unknown"),
                SolverBuild(name="libGone", path=None, digest=None, known="unknown"),
            )),)

    report = build_record_report(_context(_Wmake(), tmp_path), {})
    assert report["status"] == "ok" and report["action"] == "build-record"
    assert report["repository"] == SOURCE.to_json()
    assert [item["name"] for item in report["recorded"]] == ["mySolver"]
    assert [item["name"] for item in report["not_built"]] == ["libGone"]
    assert report["records"] == [str(tmp_path / "bin" / RECORD_FILENAME)]
    assert recorded_build("mySolver", binary).known == "recorded"
    assert report["kept"] == []


def test_a_product_not_rebuilt_since_another_repository_recorded_it_is_kept_and_reported(tmp_path):
    binary = tmp_path / "bin" / "mySolver"
    binary.parent.mkdir()
    binary.write_bytes(b"bin")
    elsewhere = SourceIdentity(repository="/src/b", digest="sha256:" + "b" * 64, git=None)
    write_records([SolverBuild(name="mySolver", path=binary, digest=file_digest(binary), known="unknown")], elsewhere)

    class _Wmake:
        plugin_id = "org.wmake"
        plugin_api_version = "3"

        def get_solver_builds(self, env, *, repository, used_paths):
            return (SolverEntry(solver="toySolver", repository=SOURCE, recordable=True,
                                builds=(recorded_build("mySolver", binary),)),)

    report = build_record_report(_context(_Wmake(), tmp_path), {})
    assert report["status"] == "ok" and report["recorded"] == []
    assert report["kept"] == [{"solver": "toySolver", "name": "mySolver", "path": str(binary), "repository": "/src/b"}]
    assert recorded_build("mySolver", binary).source == elsewhere


def test_a_stack_with_no_recordable_solver_refuses_by_name(tmp_path):
    class _SelfReporting:
        plugin_id = "org.self"
        plugin_api_version = "3"

        def get_solver_builds(self, env, *, repository, used_paths):
            return (SolverEntry(solver="s", repository=None, builds=()),)

    report = build_record_report(_context(_SelfReporting(), tmp_path), {})
    assert (report["status"], report["code"]) == ("failed", "build_products_undeclared")


def test_the_command_needs_a_repository(capsys):
    assert "--repo" in refusal(capsys, ["build-record", "--plugin", "plugins.toy:ToyStack"])
