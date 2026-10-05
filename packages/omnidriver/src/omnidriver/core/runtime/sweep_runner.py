from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from omnidriver.core.plugin_profile import is_replica_directory_name, replica_directory_globs
from omnidriver.core.strict_planning import _strict_plan_for_spec
from omnidriver.core.sweep.sweep_derivation_catalog import get_derivation
from omnidriver.core.sweep.sweep_expansion import SweepValidationError, check_case_count_cap, expand_sweep
from omnidriver.core.tutorial_records import TutorialRecordError, lookup_record, sort_study_name
from .fresh import ensure_fresh_output_dir
from .attempt_lease import acquire_case_staging_lease
from .case_records import CASE_RECORD_FILENAME, sweep_case_record, write_case_record
from .record_execution import (
    commit_and_build_record_spec,
    record_case_members,
    _reserved_study_names,
    _serialize_sourced_patch,
)
from .run_command import omnidriver_run_command
from .run_document_exec import RUN_DOCUMENT_FILENAME, _allowed_runs_root
from .workflow_orchestrator import STATE_FILENAME
from .process_control import run_child
from .workflow_runner import utc_now
from .sweep_manifest import (
    SWEEP_MANIFEST_FILENAME,
    CaseManifestEntry,
    SweepManifest,
    compute_spec_hash,
    compute_override_hash,
    write_manifest,
    read_manifest,
)

if TYPE_CHECKING:
    from ..plugin_interface import DriverContext


#: What a child ``run --run-document`` says about why it did not complete.
_CHILD_FAILURE_KEYS = ("error", "blocking_reason", "diagnostics", "environment_diagnostics", "failure_context")
_STDERR_TAIL_CHARS = 800


def _child_payload(stdout: str) -> dict[str, Any]:
    """The JSON a child ``run --run-document`` printed, or ``{}`` when it printed none."""
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _child_failure(result: subprocess.CompletedProcess[str], payload: Mapping[str, Any]) -> dict[str, Any]:
    """The reasons a child reported, whole; a child that failed without a report gets its stderr tail."""
    failure = {key: payload[key] for key in _CHILD_FAILURE_KEYS if key in payload}
    if not failure and result.returncode != 0:
        tail = (result.stderr or "").strip()[-_STDERR_TAIL_CHARS:]
        failure["error"] = f"the run exited {result.returncode} without a report" + (f"; stderr tail: {tail}" if tail else "")
    return failure


def _load_spec(spec_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(spec_path).read_text())


#: `entry`/`cases_root` are sweep-dispatch bookkeeping in `base`, not case
#: content, so they are stripped before a record's study values are resolved.
_RECORD_NON_STUDY_BASE_KEYS: frozenset[str] = frozenset({"entry", "cases_root"})


def _sweep_record(
    sweep_spec: dict[str, Any], *, driver_context: "DriverContext",
) -> tuple[Any, Path]:
    """The ``(record, cases_root)`` named by ``base``; a record has no ambient cases root, so both are required.
    A relative ``cases_root`` is read against the root of the repository the stack was selected with
    (``--repo``), and refused by name when there is none."""
    base = sweep_spec.get("base", {})
    entry = base.get("entry")
    if entry is None:
        raise TutorialRecordError(
            "sweep.json's 'base' must name the tutorial record to sweep as 'entry'"
        )
    record = lookup_record(entry, driver_context=driver_context)
    cases_root_value = base.get("cases_root")
    if cases_root_value is None:
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be swept: sweep.json's "
            "'base' must supply 'cases_root' naming where its native "
            "case lives (there is no ambient cases root to discover)"
        )
    cases_root = Path(cases_root_value)
    if not cases_root.is_absolute():
        repository = driver_context.repository
        if repository is None:
            raise TutorialRecordError(
                f"tutorial record {entry!r} cannot be swept: sweep.json's 'cases_root' {cases_root_value!r} "
                "is relative, and a relative path is read against the root of the repository given with "
                "--repo; pass --repo, or write an absolute path"
            )
        cases_root = repository.root / cases_root
    return record, cases_root


def _record_case_study_by_source(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any],
    cli_study: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Study values by source; ``cli_study`` stays apart from ``base`` so a disagreement is refused, not merged."""
    stripped_base = {
        key: value for key, value in base.items()
        if key not in _RECORD_NON_STUDY_BASE_KEYS
    }
    return {"base": stripped_base, "sweep": dict(resolved_axis_values), "cli": dict(cli_study or {})}


def _validate_record_sweep_upfront(
    record: Any, sweep_spec: dict[str, Any], *, driver_context: "DriverContext",
) -> None:
    """Refuse a missing member or a bad study name once for the whole sweep, before any case is staged."""
    record_case_members(record, driver_context)

    reserved = _reserved_study_names(record)
    base = sweep_spec.get("base", {})
    sweep_section = sweep_spec.get("sweep", {})
    independent = sweep_section.get("independent", {}) if isinstance(sweep_section, dict) else {}
    dependent = sweep_section.get("dependent", []) if isinstance(sweep_section, dict) else []
    names = set(base) | set(independent)
    names.update(
        item["name"] for item in dependent
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )
    names -= reserved
    names -= _RECORD_NON_STUDY_BASE_KEYS
    for name in names:
        sort_study_name(name, axes=record.axes)


def _record_sweep_plan(
    record: Any, cases_root: Path, sweep_spec: dict[str, Any], *,
    output_dir: Path, cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    _validate_record_sweep_upfront(record, sweep_spec, driver_context=driver_context)
    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})
    case_reports: list[dict[str, Any]] = []
    for case in resolved_cases:
        staged_case_root = output_dir / "cases" / case.case_id
        study_by_source = _record_case_study_by_source(
            base=base, resolved_axis_values=case.resolved_axis_values, cli_study=cli_study,
        )
        try:
            commit_result, spec = commit_and_build_record_spec(
                record, case_id=case.case_id, cases_root=cases_root,
                staged_case_root=staged_case_root, study_by_source=study_by_source,
                driver_context=driver_context, inputs=inputs,
            )
            report = _strict_plan_for_spec(record.name, spec, driver_context=driver_context)
        except Exception as exc:
            # One bad case costs one case, not the whole command (same
            # broad-catch reasoning as sweep_plan's factory-entry branch).
            case_reports.append({
                "case_id": case.case_id,
                "resolved_axis_values": case.resolved_axis_values,
                "status": "failed",
                "materialization_error": f"{type(exc).__name__}: {exc}",
            })
            continue
        case_reports.append({
            "case_id": case.case_id,
            "resolved_axis_values": case.resolved_axis_values,
            "status": report.status,
            "plan": report.to_json(),
            "record_commit_status": commit_result.status,
            # A patch that already matched the case is real information
            # about this case -- persisted here, not discarded.
            "unchanged_patches": [
                _serialize_sourced_patch(sourced, status="unchanged")
                for sourced in commit_result.unchanged
            ],
        })
    return {"case_count": len(resolved_cases), "cases": case_reports}


def _record_sweep_run(
    record: Any, cases_root: Path, sweep_spec: dict[str, Any], resolved_cases: Sequence[Any], *,
    output_dir: Path, case_timeout_s: float | None,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Plan and run every case of a record sweep fresh and in sequence, writing a manifest; no resume or skip."""
    execution_environment = dict(driver_context.stack.call(
        "get_configured_environment", dict(os.environ), driver_context,
    ))
    output_dir.mkdir(parents=True, exist_ok=True)
    base = sweep_spec.get("base", {})

    manifest_path = output_dir / SWEEP_MANIFEST_FILENAME
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=compute_spec_hash(sweep_spec),
        created_at=utc_now(), updated_at=utc_now(), cases=[],
        base_study={key: value for key, value in base.items() if key not in _RECORD_NON_STUDY_BASE_KEYS},
        cli_study=dict(cli_study or {}),
    )

    completed_count = 0
    failed_count = 0
    case_summaries: list[dict[str, Any]] = []

    for case in resolved_cases:
        # One folder per case: the staged case, its run document, workflow state and record.
        case_root = output_dir / "cases" / case.case_id
        run_document_path = case_root / RUN_DOCUMENT_FILENAME
        workflow_state_path = case_root / STATE_FILENAME
        case_record_path = case_root / CASE_RECORD_FILENAME
        study_by_source = _record_case_study_by_source(
            base=base, resolved_axis_values=case.resolved_axis_values, cli_study=cli_study,
        )
        entry = CaseManifestEntry(
            case_id=case.case_id,
            resolved_axis_values=case.resolved_axis_values,
            override_hash=compute_override_hash(study_by_source.get("sweep", {})),
            run_document_path=_relative_or_absolute(run_document_path, output_dir),
            workflow_state_path=_relative_or_absolute(workflow_state_path, output_dir),
            sweep_outcome="running",
            outcome="fresh",
            started_at=utc_now(),
            updated_at=utc_now(),
            case_record_path=_relative_or_absolute(case_record_path, output_dir),
        )
        manifest.cases.append(entry)
        write_manifest(manifest_path, manifest)

        status = "failed"
        failure: dict[str, Any] = {}
        commit_status = None
        unchanged_patches: list[dict[str, Any]] = []
        artifact_reconciliation = None
        try:
            commit_result, spec = commit_and_build_record_spec(
                record, case_id=case.case_id, cases_root=cases_root,
                staged_case_root=case_root, study_by_source=study_by_source,
                driver_context=driver_context, inputs=inputs,
            )
            commit_status = commit_result.status
            unchanged_patches = [
                _serialize_sourced_patch(sourced, status="unchanged")
                for sourced in commit_result.unchanged
            ]
            report = _strict_plan_for_spec(record.name, spec, driver_context=driver_context)
            payload = report.to_json()
            if report.status != "ok":
                failure["plan_error"] = (
                    "; ".join(report.error_messages()) or f"strict_plan reported {report.status} status"
                )
            else:
                run_document = payload["run_document"]
                workflow_state_path = _workflow_state_path_from_run_document(run_document)
                run_document_path.parent.mkdir(parents=True, exist_ok=True)
                run_document_path.write_text(json.dumps(run_document, indent=2))
                if workflow_state_path.exists():
                    workflow_state_path.unlink()
                write_case_record(case_record_path, sweep_case_record(entry, output_dir))
                result = run_child(
                    omnidriver_run_command(driver_context, "--run-document", str(run_document_path)),
                    env=execution_environment,
                    timeout=case_timeout_s,
                    state_path=workflow_state_path,
                )
                child = _child_payload(result.stdout)
                artifact_reconciliation = child.get("artifact_reconciliation")
                failure.update(_child_failure(result, child))
                if workflow_state_path.exists():
                    status = json.loads(workflow_state_path.read_text()).get("status", "pending")
                elif result.returncode != 0:
                    status = "failed"
                else:
                    status = "pending"
        except subprocess.TimeoutExpired as exc:
            failure["timeout_error"] = (
                f"case exceeded timeout of {case_timeout_s}s and was terminated: {exc}"
            )
        except (OSError, ValueError) as exc:
            failure["materialization_error"] = str(exc)
        except Exception as exc:
            failure["plan_error"] = str(exc)

        if status == "completed":
            completed_count += 1
        else:
            failed_count += 1

        case_summary: dict[str, Any] = {
            "case_id": case.case_id,
            "status": status,
            "outcome": "fresh",
            "run_document_path": entry.run_document_path,
            "workflow_state_path": _relative_or_absolute(workflow_state_path, output_dir),
        }
        if commit_status is not None:
            case_summary["record_commit_status"] = commit_status
        if unchanged_patches:
            # A patch that already matched the case is real information
            # about this case -- persisted here, not discarded.
            case_summary["unchanged_patches"] = unchanged_patches
        if artifact_reconciliation is not None:
            case_summary["artifact_reconciliation"] = artifact_reconciliation
        case_summary.update(failure)
        case_summaries.append(case_summary)

        entry.sweep_outcome = status
        entry.workflow_state_path = case_summary["workflow_state_path"]
        entry.updated_at = utc_now()
        entry.unchanged_patches = tuple(unchanged_patches)
        entry.failure = failure
        manifest.updated_at = entry.updated_at
        write_manifest(manifest_path, manifest)
        write_case_record(case_record_path, sweep_case_record(entry, output_dir))

    return {
        "case_count": len(resolved_cases),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "skipped_count": 0,
        "cases": case_summaries,
    }


def _relative_or_absolute(path: Path, base: Path) -> str:
    """``path`` relative to ``base``, else absolute: a state path may lie outside the sweep's output dir."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _is_declared_generated_instance(name: str, conventions) -> bool:
    """Apply the environment's declared instance-directory rule without naming it."""
    pattern = conventions.instance_directory_pattern
    return (
        pattern is not None
        and name not in conventions.preserved_instance_names
        and re.match(pattern, name) is not None
    )


def _stage_entry_case(
    source_case_root: Path, staged_case_root: Path, *, driver_context=None,
    excluded_relpaths: frozenset[str] = frozenset(),
    overlays: "Sequence[tuple[Path, str]]" = (),
) -> None:
    """Copy a case into scratch without run output; only a ``driver_context`` supplies what counts as generated."""
    from ..plugin_interface import CaseRuntimeConventions
    from ..runtime_records import case_runtime_conventions

    conventions = (
        case_runtime_conventions(driver_context)
        if driver_context is not None else CaseRuntimeConventions()
    )
    replica_globs = replica_directory_globs(driver_context)
    if Path(staged_case_root).is_symlink():
        raise TutorialRecordError(
            f"the staged case root {staged_case_root} is a symlink; staging replaces it, so it "
            "must be a real directory (remove the link, or use another --scratch-dir)"
        )
    source_case_root = Path(source_case_root).resolve()
    staged_case_root = Path(staged_case_root).resolve()

    def ignore_generated(_directory: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        relative_directory = Path(_directory).relative_to(source_case_root)
        for name in names:
            candidate = Path(_directory) / name
            if (relative_directory / name).as_posix() in excluded_relpaths:
                ignored.add(name)
                continue
            # A previous omnidriver case can have a descriptive directory
            # name (e.g. ``gauss_linear_40_*``) rather than a generated
            # time-directory name. Its workflow markers are the reliable
            # boundary between authored tutorial content and generated case
            # content, so omit the whole directory when they are present.
            if candidate.is_dir() and any(
                (candidate / marker).exists()
                for marker in conventions.generated_case_markers
            ):
                ignored.add(name)
                continue
            if name in conventions.generated_directory_names or name in conventions.generated_file_names:
                ignored.add(name)
                continue
            if candidate.is_dir() and is_replica_directory_name(name, replica_globs):
                ignored.add(name)
                continue
            if (
                any(name.startswith(prefix) for prefix in conventions.generated_file_prefixes)
                or (
                    any(name.endswith(suffix) for suffix in conventions.generated_file_suffixes)
                    and not any(
                        name.endswith(suffix)
                        for suffix in conventions.preserved_file_suffixes
                    )
                )
            ):
                ignored.add(name)
                continue
            path = Path(name)
            if _is_declared_generated_instance(path.name, conventions):
                ignored.add(name)
        return ignored

    if not source_case_root.is_dir():
        raise FileNotFoundError(f"Registered case root does not exist: {source_case_root}")
    with acquire_case_staging_lease(staged_case_root):
        _recover_interrupted_case_staging(staged_case_root)
        _copy_and_promote_staged_case(
            source_case_root,
            staged_case_root,
            ignore=ignore_generated,
            overlays=overlays,
        )


def _staging_journal_path(case_root: Path) -> Path:
    return case_root.parent / f".{case_root.name}.omnidriver-staging.json"


def _staging_path(case_root: Path, token: str, role: str) -> Path:
    return case_root.parent / f".{case_root.name}.omnidriver-{role}-{token}"


def _fsync_directory(directory: Path) -> None:
    """Make rename metadata durable where the host filesystem supports it."""
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_staging_journal(path: Path, payload: dict[str, Any]) -> None:
    """Atomically publish enough state to recover a promotion after a crash."""
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _load_staging_journal(case_root: Path) -> dict[str, Any] | None:
    path = _staging_journal_path(case_root)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"staging recovery is required but its journal is unreadable: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"staging recovery journal is malformed: {path}")
    return payload


def _journal_case_path(case_root: Path, payload: dict[str, Any], key: str) -> Path:
    raw = payload.get(key)
    if not isinstance(raw, str):
        raise RuntimeError(f"staging recovery journal omitted {key!r}")
    path = Path(raw)
    if path.parent != case_root.parent or path.name == case_root.name:
        raise RuntimeError(f"staging recovery journal has an unsafe {key!r} path")
    return path


def _recover_interrupted_case_staging(case_root: Path) -> None:
    """Restore the prior case from its backup after an interrupted promotion; a new case promotes its candidate."""
    payload = _load_staging_journal(case_root)
    if payload is None:
        return
    if payload.get("version") != 1 or payload.get("case_root") != str(case_root):
        raise RuntimeError(f"staging recovery journal is incompatible: {_staging_journal_path(case_root)}")
    candidate = _journal_case_path(case_root, payload, "candidate")
    backup = _journal_case_path(case_root, payload, "backup")
    original_exists = payload.get("original_exists")
    if not isinstance(original_exists, bool):
        raise RuntimeError("staging recovery journal omitted original_exists")

    if case_root.exists():
        # Either no rename occurred, or the candidate was already promoted.
        # In both states this path is complete; discard only private siblings.
        if candidate.exists():
            shutil.rmtree(candidate)
        if backup.exists():
            shutil.rmtree(backup)
    elif original_exists:
        if not backup.is_dir():
            raise RuntimeError(
                "staging recovery cannot restore the prior case; manual intervention is required"
            )
        os.replace(backup, case_root)
        if candidate.exists():
            shutil.rmtree(candidate)
    else:
        if not candidate.is_dir():
            raise RuntimeError(
                "staging recovery cannot promote the initial staged case; manual intervention is required"
            )
        os.replace(candidate, case_root)
    _staging_journal_path(case_root).unlink()
    _fsync_directory(case_root.parent)


def _apply_overlay(source: Path, destination: Path) -> None:
    """Copy one overlay into a staging candidate as real bytes, never a link, so a step cannot write into the source."""
    if not source.exists():
        raise FileNotFoundError(f"record input overlay source does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True)
    else:
        shutil.copy2(source, destination)


def _copy_and_promote_staged_case(
    source_case_root: Path,
    staged_case_root: Path,
    *,
    ignore: Any,
    overlays: "Sequence[tuple[Path, str]]" = (),
) -> None:
    """Copy to a private sibling, apply the overlays, then replace the staged case, so a crash leaves no half-staged case."""
    token = uuid.uuid4().hex
    candidate = _staging_path(staged_case_root, token, "candidate")
    backup = _staging_path(staged_case_root, token, "backup")
    original_exists = staged_case_root.exists()
    shutil.copytree(source_case_root, candidate, ignore=ignore, symlinks=True)
    for source, destination in overlays:
        _apply_overlay(Path(source), candidate / destination)
    # From here on the journal deliberately remains after any failure. The
    # next holder restores a coherent tree before it considers replacement.
    _write_staging_journal(
        _staging_journal_path(staged_case_root),
        {
            "version": 1,
            "case_root": str(staged_case_root),
            "candidate": str(candidate),
            "backup": str(backup),
            "original_exists": original_exists,
        },
    )
    if original_exists:
        os.replace(staged_case_root, backup)
        _fsync_directory(staged_case_root.parent)
    os.replace(candidate, staged_case_root)
    _fsync_directory(staged_case_root.parent)
    if backup.exists():
        shutil.rmtree(backup)
    _staging_journal_path(staged_case_root).unlink()
    _fsync_directory(staged_case_root.parent)


def sweep_plan(
    spec_path: str | Path,
    *,
    output_dir: str | Path,
    max_cases: int = 200,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Plan every case in a sweep spec without executing it.

    ``cli_study``: the CLI's own study values (``--parallel``), the sweep's
    ``"cli"`` source. ``inputs`` (``--input NAME=PATH``): the record's inputs,
    applied once to every case.
    """
    try:
        sweep_spec = _load_spec(spec_path)
    except (OSError, ValueError) as exc:
        # A malformed or unreadable spec yields no cases at all, so there is
        # no per-case slot to report it in -- but the caller still parses this
        # document, and a traceback on stderr with nothing on stdout is not an
        # answer. Same shape, zero cases, one explicit reason.
        return {"case_count": 0, "cases": [], "spec_error": str(exc)}
    check_case_count_cap(sweep_spec, max_cases=max_cases)
    record, cases_root = _sweep_record(sweep_spec, driver_context=driver_context)
    # Resolved to absolute before staging: a relative --output-dir otherwise
    # reaches commit_record_case unresolved.
    return _record_sweep_plan(
        record, cases_root, sweep_spec, output_dir=Path(output_dir).resolve(),
        cli_study=cli_study, inputs=inputs, driver_context=driver_context,
    )


def _workflow_state_path_from_run_document(run_document: dict[str, Any]) -> Path:
    try:
        output_dir = run_document["launch"]["outputDir"]
    except KeyError as exc:
        raise ValueError("strict_plan run_document is missing launch.outputDir") from exc
    return Path(output_dir) / STATE_FILENAME


def sweep_run(
    spec_path: str | Path,
    *,
    output_dir: str | Path,
    max_cases: int = 200,
    case_timeout_s: float | None = None,
    fresh: bool = False,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Run every case in a sweep spec and record the sweep.

    ``cli_study``/``inputs``: as :func:`sweep_plan`.
    """
    sweep_spec = _load_spec(spec_path)
    check_case_count_cap(sweep_spec, max_cases=max_cases)
    record, cases_root = _sweep_record(sweep_spec, driver_context=driver_context)
    # Resolved to absolute before staging: commit_record_case requires
    # CaseMutationRequest.case_root to be absolute.
    requested_dir = Path(output_dir)
    output_dir = requested_dir.resolve()
    # The spec is validated before --fresh deletes anything.
    _validate_record_sweep_upfront(record, sweep_spec, driver_context=driver_context)
    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    # The path as given: resolving it first would hide a symlink.
    fresh_error = ensure_fresh_output_dir(
        requested_dir, fresh=fresh, allowed_root=_allowed_runs_root(),
    )
    if fresh_error is not None:
        raise SweepValidationError(fresh_error)
    # A sweep does not resume across invocations, so an existing manifest here
    # (not cleared by --fresh) is refused by name instead of silently
    # restaged, which would waste prior work and could leave stale case
    # directories if the spec changed.
    manifest_path = output_dir / SWEEP_MANIFEST_FILENAME
    if manifest_path.exists():
        existing = read_manifest(manifest_path)
        spec_hash = compute_spec_hash(sweep_spec)
        if existing.sweep_spec_hash != spec_hash:
            raise SweepValidationError(
                "sweep.json has changed since this output directory was "
                f"created (hash mismatch: expected {existing.sweep_spec_hash}, "
                f"got {spec_hash}); spec changed — use a fresh --output-dir "
                "or resolve the mismatch."
            )
        raise TutorialRecordError(
            f"tutorial record {record.name!r} sweep cannot resume: "
            f"{output_dir} already holds a sweep manifest from a prior run "
            "and a sweep does not resume across invocations -- pass --fresh "
            "to start over, or use a new --output-dir"
        )
    return _record_sweep_run(
        record, cases_root, sweep_spec, resolved_cases, output_dir=output_dir,
        case_timeout_s=case_timeout_s, cli_study=cli_study,
        inputs=inputs, driver_context=driver_context,
    )
