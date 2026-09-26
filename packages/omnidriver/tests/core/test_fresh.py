from pathlib import Path

from omnidriver.core.runtime.fresh import (
    check_fresh_deletion_allowed,
    ensure_fresh_output_dir,
)


def test_allows_deletion_of_nonexistent_directory(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert check_fresh_deletion_allowed(target, allowed_root=None) is None


def test_allows_deletion_of_directory_with_top_level_marker(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "workflow_state.json").write_text("{}")
    assert check_fresh_deletion_allowed(target, allowed_root=None) is None


def test_allows_deletion_when_marker_is_one_level_down(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    case_dir = target / "TNNP"
    case_dir.mkdir(parents=True)
    (case_dir / "run_document.json").write_text("{}")
    assert check_fresh_deletion_allowed(target, allowed_root=None) is None


def test_refuses_directory_with_no_omnidriver_marker(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("do not delete me")
    error = check_fresh_deletion_allowed(target, allowed_root=None)
    assert error is not None
    assert "no recognizable omnidriver artifact" in error


def test_refuses_filesystem_root():
    error = check_fresh_deletion_allowed(Path("/"), allowed_root=None)
    assert error is not None
    assert "filesystem root" in error


def test_refuses_home_directory():
    error = check_fresh_deletion_allowed(Path.home(), allowed_root=None)
    assert error is not None
    assert "home directory" in error


def test_refuses_path_with_two_segments():
    error = check_fresh_deletion_allowed(Path("/a/b"), allowed_root=None)
    assert error is not None
    assert "too shallow" in error


def test_allows_path_with_three_segments():
    assert check_fresh_deletion_allowed(Path("/a/b/c"), allowed_root=None) is None


def test_refuses_path_outside_allowed_root(tmp_path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside = tmp_path / "elsewhere" / "case" / "output"
    outside.mkdir(parents=True)
    (outside / "workflow_state.json").write_text("{}")
    error = check_fresh_deletion_allowed(outside, allowed_root=allowed_root)
    assert error is not None
    assert "OMNIDRIVER_ALLOWED_RUNS_ROOT" in error


def test_allows_path_inside_allowed_root(tmp_path):
    allowed_root = tmp_path / "allowed"
    inside = allowed_root / "case" / "output"
    inside.mkdir(parents=True)
    (inside / "workflow_state.json").write_text("{}")
    assert check_fresh_deletion_allowed(inside, allowed_root=allowed_root) is None


def test_ensure_fresh_output_dir_deletes_when_allowed(tmp_path, capsys):
    target = tmp_path / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "workflow_state.json").write_text('{"status": "completed"}')
    (target / "stale_result.txt").write_text("old")

    error = ensure_fresh_output_dir(target, fresh=True, allowed_root=None)

    assert error is None
    assert not target.exists()
    captured = capsys.readouterr()
    assert "deleting" in captured.err
    assert captured.out == ""


def test_ensure_fresh_output_dir_noop_when_fresh_false(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "workflow_state.json").write_text("{}")

    error = ensure_fresh_output_dir(target, fresh=False, allowed_root=None)

    assert error is None
    assert target.exists()


def test_ensure_fresh_output_dir_leaves_directory_untouched_on_refusal(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("keep me")

    error = ensure_fresh_output_dir(target, fresh=True, allowed_root=None)

    assert error is not None
    assert target.exists()
    assert (target / "notes.txt").read_text() == "keep me"


def test_ensure_fresh_output_dir_noop_when_directory_does_not_exist(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    assert ensure_fresh_output_dir(target, fresh=True, allowed_root=None) is None
    assert not target.exists()


def test_the_legacy_allowed_root_variable_name_is_not_read(monkeypatch, tmp_path):
    """Task 9 close-out (owner decision 3, 2026-09-26): the legacy name,
    ``DRIVERFOAM_ALLOWED_RUNS_ROOT`` (renamed to
    ``OMNIDRIVER_ALLOWED_RUNS_ROOT`` on 2026-09-14), is removed outright --
    it is the project's own former name, not an OpenFOAM- or A1/A2-scoped
    rename, and the owner chose to stop reading it rather than carry it
    forward indefinitely. Only the current name is honoured now."""
    from omnidriver.core.runtime.run_document_exec import _allowed_runs_root

    monkeypatch.delenv("OMNIDRIVER_ALLOWED_RUNS_ROOT", raising=False)
    monkeypatch.setenv("DRIVERFOAM_ALLOWED_RUNS_ROOT", str(tmp_path))
    assert _allowed_runs_root() is None

    current = tmp_path / "current"
    current.mkdir()
    monkeypatch.setenv("OMNIDRIVER_ALLOWED_RUNS_ROOT", str(current))
    assert _allowed_runs_root() == current.resolve()


def test_a_run_document_written_before_the_rename_is_still_driver_owned():
    """`produced_by` was "driverFOAM" before 2026-09-14.

    Artifacts the executor writes are excluded from step responsibility. A
    document holding the retired value must keep that exclusion, or its
    workflow_state/workflow_logs would be charged to the solver step and fail
    it for bookkeeping it never wrote.
    """
    from omnidriver.core.runtime.artifacts import (
        DRIVER_PRODUCED_BY,
        LEGACY_DRIVER_PRODUCED_BY,
    )
    from omnidriver.core.runtime.models import DataArtifact
    from omnidriver.core.runtime.workflow import workflow_output_artifacts

    solver = DataArtifact(
        artifact_id="solver.field", path_pattern="{instance}/Vm",
        format="openfoam_time_dirs", produced_by="someSolver",
    )
    legacy = DataArtifact(
        artifact_id="core.workflow_state", path_pattern="postProcessing/workflow_state.json",
        format="json_summary", produced_by=LEGACY_DRIVER_PRODUCED_BY,
    )
    current = DataArtifact(
        artifact_id="core.workflow_logs", path_pattern="postProcessing/workflow_logs",
        format="log", produced_by=DRIVER_PRODUCED_BY,
    )
    kept = workflow_output_artifacts((solver, legacy, current))
    assert [a.artifact_id for a in kept] == ["solver.field"]
