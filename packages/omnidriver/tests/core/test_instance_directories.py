"""Instance directories are plugin-declared vocabulary
(spec 2026-09-26-core-generality-design.md §2, A2). A stack that declares
none (openCARP) has none; a stack that declares a pattern gets exactly
what that pattern matches."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnidriver.core.plugin_capabilities import CaseRuntimeConventions
from omnidriver.core.plugin_interface import driver_context
from omnidriver.core.runtime.models import DataArtifact, expand_path_pattern
from omnidriver.core.runtime.reconciler import declared_instance_names, reconcile_artifacts
from omnidriver.core.runtime.sweep_runner import _clean_stale_instances
from plugins.minimal_plugin import MinimalTestPlugin

_DECLARED = CaseRuntimeConventions(instance_directory_pattern=r"^step-\d+$", preserved_instance_names=("step-0",))


class _DeclaresInstances(MinimalTestPlugin):
    def get_case_runtime_conventions(self):
        return _DECLARED


def _dirs(root: Path, *names: str) -> None:
    for name in names:
        (root / name).mkdir(parents=True)
        (root / name / "out.dat").write_text(name)


_ARTIFACT = DataArtifact(artifact_id="a", path_pattern="{instance}/out.dat", format="x", instance_indexed=True)


def test_a_stack_that_declares_no_instances_has_none(tmp_path):
    _dirs(tmp_path, "0", "0.5", "step-1")
    ctx = driver_context(MinimalTestPlugin(), source="test")
    names = declared_instance_names(tmp_path, driver_context=ctx)
    assert names == ()
    assert reconcile_artifacts(tmp_path, (_ARTIFACT,), instance_names=names).missing_count == 1


def test_declared_instances_are_exactly_what_the_plugins_pattern_matches(tmp_path):
    _dirs(tmp_path, "0", "step-0", "step-1", "step-x")
    ctx = driver_context(_DeclaresInstances(), source="test")
    names = declared_instance_names(tmp_path, driver_context=ctx)
    assert names == ("step-0", "step-1")
    report = reconcile_artifacts(tmp_path, (_ARTIFACT,), instance_names=names)
    assert sorted(Path(m["path"]).parent.name for m in report.artifacts[0]["matched_files"]) == ["step-0", "step-1"]


def test_cleaning_removes_generated_instances_and_keeps_preserved_ones(tmp_path):
    _dirs(tmp_path, "step-0", "step-1", "0.5")
    _clean_stale_instances(tmp_path, conventions=_DECLARED)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["0.5", "step-0"]


def test_a_stack_that_declares_no_instances_cleans_nothing(tmp_path):
    _dirs(tmp_path, "0", "0.5")
    _clean_stale_instances(tmp_path, conventions=CaseRuntimeConventions())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["0", "0.5"]


def test_the_time_vocabulary_is_gone():
    with pytest.raises(ValueError, match="time"):
        DataArtifact(artifact_id="a", path_pattern="{time}/x", format="x")
    assert expand_path_pattern("{instance}/x", instance="7") == "7/x"
    assert not hasattr(DataArtifact(artifact_id="a", path_pattern="x", format="x"), "time_indexed")
    assert not hasattr(CaseRuntimeConventions(), "time_directory_name_pattern")


def test_a_bare_string_preserved_instance_names_is_refused_by_name():
    """R2 fix, finding I3: a bare ``str`` here would give substring
    membership (``name not in "0"``) instead of exact-name membership --
    the same migration mistake as ``replica_directory_globs``, refused the
    same way."""
    with pytest.raises(TypeError, match="preserved_instance_names.*tuple of name strings.*str"):
        CaseRuntimeConventions(preserved_instance_names="0")


def test_a_non_string_item_in_preserved_instance_names_is_refused_by_name():
    with pytest.raises(TypeError, match="preserved_instance_names"):
        CaseRuntimeConventions(preserved_instance_names=("0", 1))


def test_an_invalid_instance_directory_pattern_is_refused_at_construction():
    """R2 fix, finding I3: an invalid regex used to fail with a raw
    ``re.error`` mid-staging, wherever the pattern was first compiled --
    refused at construction instead."""
    with pytest.raises(ValueError, match="instance_directory_pattern"):
        CaseRuntimeConventions(instance_directory_pattern="[unclosed")


def test_a_non_string_instance_directory_pattern_is_refused_by_name():
    with pytest.raises(TypeError, match="instance_directory_pattern"):
        CaseRuntimeConventions(instance_directory_pattern=123)
