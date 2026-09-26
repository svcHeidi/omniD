"""Replica directories are plugin-declared vocabulary
(spec 2026-09-26-core-generality-design.md §2, A2). A stack that declares
none (openCARP) treats a processor0/ like any other directory."""
from __future__ import annotations

from pathlib import Path

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.plugin_profile import is_replica_directory_name
from omnidriver.core.runtime.registry import list_entries
from omnidriver.core.runtime.sweep_runner import _stage_entry_case
from plugins.minimal_plugin import MinimalTestPlugin


class _DeclaresReplicas(MinimalTestPlugin):
    def get_case_runtime_conventions(self):
        return CaseRuntimeConventions(replica_directory_globs=("rank*",))


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    for relpath in ("rank0/f", "processor0/f", "input.txt"):
        (source / relpath).parent.mkdir(parents=True, exist_ok=True)
        (source / relpath).write_text(relpath)
    return source


def test_the_name_rule_is_the_declared_globs():
    assert is_replica_directory_name("processor12", ("processor*",))
    assert not is_replica_directory_name("postProcessing", ("processor*",))
    assert not is_replica_directory_name("processor0", ())


def test_a_stack_that_declares_no_replicas_stages_every_directory(tmp_path):
    staged = tmp_path / "staged"
    _stage_entry_case(_source(tmp_path), staged, driver_context=driver_context(MinimalTestPlugin(), source="test"))
    assert (staged / "processor0" / "f").is_file() and (staged / "rank0" / "f").is_file()


def test_declared_replicas_are_not_staged(tmp_path):
    staged = tmp_path / "staged"
    _stage_entry_case(_source(tmp_path), staged, driver_context=driver_context(_DeclaresReplicas(), source="test"))
    assert not (staged / "rank0").exists()
    assert (staged / "processor0" / "f").is_file()


def test_a_stack_that_declares_no_replicas_discovers_cases_inside_them(tmp_path):
    case_root = tmp_path / "processor0" / "nestedCase"
    case_root.mkdir(parents=True)
    (case_root / "run-case").write_text("")
    ctx = driver_context(MinimalTestPlugin(entrypoint="run-case"), source="test")
    assert list_entries(tmp_path, driver_context=ctx) != []
