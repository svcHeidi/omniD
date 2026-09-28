from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, NamedTuple, Sequence

from omnidriver.core.strict_planning import refuse_cli_study_for_non_record, strict_plan, _strict_plan_for_spec
from omnidriver.core.plugin_profile import is_replica_directory_name, replica_directory_globs
from omnidriver.core.sweep.sweep_derivation_catalog import get_derivation
from omnidriver.core.sweep.sweep_expansion import SweepValidationError, check_case_count_cap, expand_sweep
from omnidriver.core.tutorial_records import TutorialRecordError, sort_study_name
from omnidriver.sweep_materialize import materialize_case
from omnidriver.sweep_routing import route_case_values, route_entry_case_values
from .fresh import ensure_fresh_output_dir
from .attempt_lease import acquire_case_staging_lease
from .models import data_artifact_from_json
from .output_collection import collect_new_output_tree, snapshot_output_tree
from .postprocess_phase import CASE_RECORD_FILENAME, build_sweep_context, run_postprocessing_module
from .record_execution import (
    commit_and_build_record_spec,
    _reserved_study_names,
    _serialize_sourced_patch,
)
from .registry import load_entry_spec
from .run_command import omnidriver_run_command
from .run_document_exec import RUN_DOCUMENT_FILENAME, _allowed_runs_root, load_run_document
from .resume import validate_resume
from .workflow_orchestrator import STATE_FILENAME
from .workflow_state import workflow_state_from_json
from .workflow_runner import _terminate_process_group
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


def _run_case_process(
    command: list[str],
    *,
    env: dict[str, str],
    timeout: float | None,
) -> subprocess.CompletedProcess[str]:
    """Run one sweep case, owning its POSIX process group on timeout."""
    if timeout is None:
        return subprocess.run(command, capture_output=True, text=True, env=env)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(
            command, exc.timeout, output=stdout, stderr=stderr,
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _child_reconciliation(stdout: str) -> dict[str, Any] | None:
    """The child ``run --run-document``'s artifact reconciliation, parsed from its stdout."""
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return None
    value = payload.get("artifact_reconciliation") if isinstance(payload, dict) else None
    return value if isinstance(value, dict) else None


def _load_spec(spec_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(spec_path).read_text())


def _entry_name(sweep_spec: dict[str, Any]) -> str | None:
    return sweep_spec.get("base", {}).get("entry")


# A study whose "entry" names a tutorial record dispatches through a
# dedicated path -- staged from the record's native case, then the
# record's own workflow steps run through the same strict-plan/run-
# document/workflow-runner pipeline a factory entry's spec runs through.
# Never tried as a factory entry first and reinterpreted --
# registry.resolve_entry's own explicit dispatch decides which this is,
# once, up front.

#: `entry`/`cases_root` are sweep-dispatch bookkeeping in `base`, not case
#: content, so they are stripped before a record's study values are resolved.
_RECORD_NON_STUDY_BASE_KEYS: frozenset[str] = frozenset({"entry", "cases_root"})


def _sweep_record(
    sweep_spec: dict[str, Any], *, driver_context: "DriverContext",
) -> tuple[Any, Path] | tuple[None, None]:
    """Return ``(record, cases_root)`` when ``base.entry`` names a tutorial
    record, else ``(None, None)`` -- a factory tutorial or no entry at all.

    Classification -- including every record-vs-(factory/case-path/case-
    folder) ambiguity refusal -- is `registry.classify_entry`'s job, the
    same function `registry.resolve_entry` calls.

    A record has no ambient cases root: ``base.cases_root`` must name it
    explicitly whenever ``entry`` resolves to a record, refused by name
    otherwise. When ``cases_root`` is absent, `classify_entry` is still
    called (so the record-vs-factory/record-vs-cwd-case-path ambiguities
    are still caught), just with no root to check the case-folder
    ambiguity against.
    """
    entry = _entry_name(sweep_spec)
    if entry is None:
        return None, None
    from .registry import classify_entry

    base = sweep_spec.get("base", {})
    cases_root_value = base.get("cases_root")
    cases_root = Path(cases_root_value) if cases_root_value is not None else None
    classification = classify_entry(
        entry, entry_kind=None, cases_root=cases_root, driver_context=driver_context,
    )
    if classification.kind != "tutorial_record":
        return None, None
    if cases_root is None:
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be swept: sweep.json's "
            "'base' must supply 'cases_root' naming where its native case "
            "lives (there is no ambient cases root to discover)"
        )
    return classification.record, cases_root


def _record_case_study_by_source(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any],
    cli_study: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """``cli_study`` is the CLI's ``--parallel`` study source, kept apart from
    ``base`` so a disagreement with the sweep file is refused by name, not merged."""
    stripped_base = {
        key: value for key, value in base.items()
        if key not in _RECORD_NON_STUDY_BASE_KEYS
    }
    return {"base": stripped_base, "sweep": dict(resolved_axis_values), "cli": dict(cli_study or {})}


def _validate_record_sweep_upfront(
    record: Any, sweep_spec: dict[str, Any], *, driver_context: "DriverContext",
) -> None:
    """Refuse a missing capability or a bad study name once, up front, for the
    whole sweep -- before any case is staged. Both kinds of refusal are the
    same for every case in one sweep, since the composed stack either has
    these three capabilities or it does not, and a name's shape (a
    ``document:key`` literal vs an axis) never varies across cases even when
    a swept axis's value does.
    """
    if driver_context.capabilities.record_key_validation.validator() is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no record-key validator (get_record_key_validator); a "
            "record case's keys cannot be checked against any catalog"
        )
    if driver_context.capabilities.case_value_comparison.comparator() is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no case-value comparator (get_case_value_comparator); "
            "whether a patch is unchanged cannot be determined"
        )
    if driver_context.capabilities.config_value.reader() is None:
        raise TutorialRecordError(
            f"tutorial record {record.name!r} cannot run: the composed stack "
            "declares no config-value reader (get_config_value_reader); "
            "whether a patch is unchanged cannot be determined"
        )

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
    record: Any, cases_root: Path, sweep_spec: dict[str, Any], *,
    output_dir: Path, case_timeout_s: float | None, task: str,
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """The record-entry counterpart of ``sweep_run``'s factory-entry branch.

    Deliberately narrower than the factory-entry path: every case is
    planned and run fresh, sequentially -- no manifest-based
    resume/retry/skip across separate invocations yet. A manifest is still
    written, so the output directory carries the same bookkeeping shape a
    factory-entry sweep's does.
    """
    _validate_record_sweep_upfront(record, sweep_spec, driver_context=driver_context)
    execution_environment = driver_context.capabilities.environment_preflight.configure(
        os.environ, driver_context,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})

    manifest_path = output_dir / SWEEP_MANIFEST_FILENAME
    spec_hash = compute_spec_hash(sweep_spec)
    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=spec_hash,
        created_at=_now(), updated_at=_now(), cases=[],
    )

    completed_count = 0
    failed_count = 0
    case_summaries: list[dict[str, Any]] = []

    for case in resolved_cases:
        staged_case_root = output_dir / "cases" / case.case_id
        case_dir = output_dir / case.case_id
        run_document_path = case_dir / RUN_DOCUMENT_FILENAME
        workflow_state_path = case_dir / STATE_FILENAME
        case_record_path = case_dir / CASE_RECORD_FILENAME
        study_by_source = _record_case_study_by_source(
            base=base, resolved_axis_values=case.resolved_axis_values, cli_study=cli_study,
        )

        status = "failed"
        materialization_error = None
        plan_error = None
        timeout_error = None
        commit_status = None
        unchanged_patches: list[dict[str, Any]] = []
        artifact_reconciliation = None
        try:
            commit_result, spec = commit_and_build_record_spec(
                record, case_id=case.case_id, cases_root=cases_root,
                staged_case_root=staged_case_root, study_by_source=study_by_source,
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
                plan_error = "strict_plan reported failed status"
            else:
                run_document = payload["run_document"]
                workflow_state_path = _workflow_state_path_from_run_document(run_document)
                run_document_path.parent.mkdir(parents=True, exist_ok=True)
                run_document_path.write_text(json.dumps(run_document, indent=2))
                if workflow_state_path.exists():
                    workflow_state_path.unlink()
                result = _run_case_process(
                    omnidriver_run_command(driver_context, "--run-document", str(run_document_path)),
                    env=execution_environment,
                    timeout=case_timeout_s,
                )
                artifact_reconciliation = _child_reconciliation(result.stdout)
                if workflow_state_path.exists():
                    status = json.loads(workflow_state_path.read_text()).get("status", "pending")
                elif result.returncode != 0:
                    status = "failed"
                else:
                    status = "pending"
        except subprocess.TimeoutExpired as exc:
            timeout_error = (
                f"case exceeded timeout of {case_timeout_s}s and was terminated: {exc}"
            )
        except (OSError, ValueError) as exc:
            materialization_error = str(exc)
        except Exception as exc:
            plan_error = str(exc)

        if status == "completed":
            completed_count += 1
        else:
            failed_count += 1

        case_summary: dict[str, Any] = {
            "case_id": case.case_id,
            "status": status,
            "outcome": "fresh",
            "run_document_path": _relative_or_absolute(run_document_path, output_dir),
            "workflow_state_path": _relative_or_absolute(workflow_state_path, output_dir),
        }
        if commit_status is not None:
            case_summary["record_commit_status"] = commit_status
        if unchanged_patches:
            # A patch that already matched the case is real information
            # about this case -- persisted here, not discarded.
            case_summary["unchanged_patches"] = unchanged_patches
        if materialization_error is not None:
            case_summary["materialization_error"] = materialization_error
        if plan_error is not None:
            case_summary["plan_error"] = plan_error
        if timeout_error is not None:
            case_summary["timeout_error"] = timeout_error
        if artifact_reconciliation is not None:
            case_summary["artifact_reconciliation"] = artifact_reconciliation
        case_summaries.append(case_summary)

        manifest.cases.append(
            CaseManifestEntry(
                case_id=case.case_id,
                resolved_axis_values=case.resolved_axis_values,
                override_hash=compute_override_hash(study_by_source.get("sweep", {})),
                run_document_path=_relative_or_absolute(run_document_path, output_dir),
                workflow_state_path=_relative_or_absolute(workflow_state_path, output_dir),
                status=status,
                outcome="fresh",
                started_at=_now(),
                updated_at=_now(),
                case_record_path=_relative_or_absolute(case_record_path, output_dir),
                unchanged_patches=tuple(unchanged_patches),
            )
        )
        manifest.updated_at = _now()
        write_manifest(manifest_path, manifest)

    context = build_sweep_context(output_dir, persist_case_records=True)
    if failed_count == 0:
        postprocess = run_postprocessing_module(context, task=task).to_json()
    else:
        postprocess = {
            "status": "skipped",
            "message": f"sweep had {failed_count} failed case(s); postprocess not run",
        }

    return {
        "case_count": len(resolved_cases),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "skipped_count": 0,
        "cases": case_summaries,
        "postprocess": postprocess,
    }


def _relative_or_absolute(path: Path, base: Path) -> str:
    """Path relative to `base` when possible, else the absolute path.

    `workflow_state_path` may resolve outside the sweep's `--output-dir` in
    entry mode (it comes from `launch.outputDir`), so this returns the
    absolute path there rather than crash the whole sweep over a manifest
    cosmetic.
    """
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


def _clean_stale_instances(case_root: Path, *, conventions) -> None:
    """Remove prior generated instance directories when the environment declares them.

    Entry-based sweeps reuse one shared case_root across cases; without this,
    a case with no authored initial instance could consume a prior run's
    generated one.
    """
    if conventions.instance_directory_pattern is None or not case_root.is_dir():
        return
    for child in case_root.iterdir():
        if child.is_dir() and _is_declared_generated_instance(child.name, conventions):
            shutil.rmtree(child)


class MaterializedEntry(NamedTuple):
    """The entry and overrides that name one materialized sweep case.

    Plan and run with both. A case-path entry names its case by the path
    itself, so staging it changes the entry, not just the overrides.
    """

    entry: str
    overrides: dict[str, Any]


def _materialize_entry_case(
    entry: str,
    routed: dict[str, Any],
    *,
    staging_root: Path | None = None,
    driver_context=None,
) -> MaterializedEntry:
    """Materialize one entry-based sweep case via the tutorial's own spec.

    Entry-based sweeps target an existing case path or tutorial record whose
    ``case_mutation()`` mutates a case root in place. That root must be a
    disposable staging copy, never the checked-in tutorial or the user's
    case directory. The returned entry and overrides point at that staged
    case so strict planning and execution use exactly the same paths.
    """
    spec = load_entry_spec(entry, overrides=routed, driver_context=driver_context)
    effective_entry = entry
    effective_routed = dict(routed)
    if staging_root is not None and spec.case_root.exists():
        source_case_root = Path(spec.case_root).resolve()
        staged_case_root = Path(staging_root).resolve()
        _stage_entry_case(source_case_root, staged_case_root, driver_context=driver_context)
        if spec.metadata["resolution"] == "case_path":
            # A case path names its case by the path itself; the staged
            # copy becomes the entry so the source case is never mutated.
            effective_entry = str(staged_case_root)
        else:
            # ``make_spec`` resolves case_root as cases_root/case_dir_name.
            # Redirect both values together; changing only cases_root would
            # leave a nested original case_dir_name and recreate the source
            # tree below the scratch directory.
            effective_routed["cases_root"] = str(staged_case_root.parent)
            effective_routed["case_dir_name"] = staged_case_root.name
        # Staging already isolates this case at staged_case_root, so any
        # output_dir_name the sweep spec derived would double-nest output
        # under staged_case_root/<case id>/, a directory the solve step
        # never writes into -- making the workflow's artifact check report
        # real, present output as missing. "." tells resolve_spec_paths
        # there is nothing to append.
        effective_routed["output_dir_name"] = "."
        staged_spec = load_entry_spec(
            effective_entry, overrides=effective_routed, driver_context=driver_context,
        )
        # A real registered factory consumes cases_root/case_dir_name, and a
        # case path resolves to itself, so either returns the staged path.
        # A factory returning its own fixed root instead would mutate the
        # source case below, so that is refused rather than silently
        # falling back to the unstaged overrides.
        if Path(staged_spec.case_root).resolve() != staged_case_root:
            raise ValueError(
                f"entry '{entry}' did not re-resolve to its staged copy "
                f"'{staged_case_root}'; its factory returned "
                f"'{Path(staged_spec.case_root).resolve()}' (source "
                f"'{source_case_root}'). Mutating that would change the source "
                "case, so the factory must build case_root from the "
                "cases_root/case_dir_name it is given."
            )
        spec = staged_spec
    from ..plugin_capabilities import CaseRuntimeConventions

    conventions = (
        driver_context.capabilities.case_runtime_conventions.conventions()
        if driver_context is not None else CaseRuntimeConventions()
    )
    _clean_stale_instances(spec.case_root, conventions=conventions)
    if spec.case_mutation is not None:
        spec.case_mutation(spec.case_root)
    return MaterializedEntry(effective_entry, effective_routed)


def _stage_entry_case(
    source_case_root: Path, staged_case_root: Path, *, driver_context=None,
    excluded_relpaths: frozenset[str] = frozenset(),
    overlays: "Sequence[tuple[Path, str]]" = (),
) -> None:
    """Copy a registered case into scratch storage without old run output.

    Registered tutorial folders contain source dictionaries and scripts next
    to OpenFOAM's generated mesh, time, processor, log, and post-processing
    trees. Copying those generated trees would reintroduce the stale-state
    bug this staging boundary is meant to prevent, so the filter is explicit
    and conservative: keep authored inputs (including ``0/``) and omit only
    known derived artifacts.

    ``excluded_relpaths`` names further case-relative paths (files, or whole
    directories, at any depth) that the caller knows are generated: a
    tutorial record's step outputs. With no ``driver_context`` supplied,
    ``conventions`` below is a bare ``CaseRuntimeConventions()`` that
    carries none of core's own records, so every production caller must
    supply a real ``driver_context``.
    """
    from ..plugin_capabilities import CaseRuntimeConventions

    conventions = (
        driver_context.capabilities.case_runtime_conventions.conventions()
        if driver_context is not None else CaseRuntimeConventions()
    )
    replica_globs = replica_directory_globs(driver_context)
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
            if (
                candidate.is_dir()
                and (
                    is_replica_directory_name(name, replica_globs)
                    or any(name.startswith(prefix) for prefix in conventions.generated_directory_prefixes)
                )
            ):
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
    """Restore a coherent case after a failed sibling-directory promotion.

    If a process dies between the two renames, restoring the prior case
    from its backup is safer than assuming the candidate should run; a
    brand-new case has no backup and promotes its candidate instead.
    """
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
    """Copy one ``(source, destination)`` pair into a staging candidate.

    Always copies real bytes, never a link: a step can write inside its
    input (e.g. ``generatePurkinjeTree`` rewriting
    ``constant/polyMesh/sets/*``), and a link would send that write into
    the supplied bundle or the native tree.
    """
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
    """Copy to a private sibling, apply every overlay, then replace a staged
    case under its lease, so a crash never leaves a half-staged case."""
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

    ``cli_study``: the CLI's own study values (``--parallel``), a record
    sweep's ``"cli"`` source; refused by name for a factory sweep.
    ``inputs`` (``--input NAME=PATH``): a record sweep's inputs, applied
    once to every case; refused by name for a factory sweep.
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

    output_dir = Path(output_dir)

    record, cases_root = _sweep_record(sweep_spec, driver_context=driver_context)
    if record is not None:
        # Resolved to absolute before staging: a relative --output-dir
        # otherwise reaches commit_record_case unresolved (see sweep_run's
        # own record branch).
        return _record_sweep_plan(
            record, cases_root, sweep_spec, output_dir=Path(output_dir).resolve(),
            cli_study=cli_study, inputs=inputs, driver_context=driver_context,
        )
    try:
        refuse_cli_study_for_non_record(str(_entry_name(sweep_spec)), cli_study)
        if inputs:
            raise TutorialRecordError(
                f"--input applies only to a tutorial record's sweep, and "
                f"{_entry_name(sweep_spec)!r} is not one"
            )
    except TutorialRecordError as exc:
        return {"case_count": 0, "cases": [], "spec_error": str(exc)}

    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})
    entry = _entry_name(sweep_spec)

    case_reports = []
    for case in resolved_cases:
        try:
            if entry is not None:
                routed = route_entry_case_values(base=base, resolved_axis_values=case.resolved_axis_values)
                plan_entry, routed = _materialize_entry_case(
                    entry,
                    routed,
                    staging_root=output_dir / "cases" / case.case_id,
                    driver_context=driver_context,
                )
            else:
                routed = route_case_values(
                    base=base,
                    resolved_axis_values=case.resolved_axis_values,
                    driver_context=driver_context,
                )
                materialize_case(
                    case_dir=output_dir / case.case_id,
                    routed=routed,
                    driver_context=driver_context,
                )
        except Exception as exc:
            # Deliberately broad. A sweep's contract is that one bad axis
            # value costs one case, not the command -- and a tutorial factory
            # can raise anything (KeyError for an unknown ionic model, for
            # instance), not just OSError/ValueError. Narrowing this let
            # those escape as a traceback with zero bytes on stdout. The
            # run path's entry-mode branch already catches broadly for the
            # same reason.
            case_reports.append(
                {
                    "case_id": case.case_id,
                    "resolved_axis_values": case.resolved_axis_values,
                    "status": "failed",
                    "materialization_error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        if entry is not None:
            report = strict_plan(plan_entry, overrides=routed, driver_context=driver_context)
        else:
            report = strict_plan(
                case.case_id,
                entry_kind="case_folder",
                overrides={"cases_root": str(output_dir)},
                driver_context=driver_context,
            )
        report_payload = report.to_json()
        case_reports.append(
            {
                "case_id": case.case_id,
                "resolved_axis_values": case.resolved_axis_values,
                "status": report.status,
                "plan": report_payload,
            }
        )

    return {"case_count": len(resolved_cases), "cases": case_reports}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workflow_state_path_from_run_document(run_document: dict[str, Any]) -> Path:
    try:
        output_dir = run_document["launch"]["outputDir"]
    except KeyError as exc:
        raise ValueError("strict_plan run_document is missing launch.outputDir") from exc
    return Path(output_dir) / STATE_FILENAME


def _completed_case_is_reusable(
    prior_entry: CaseManifestEntry | None,
    *,
    output_dir: Path,
    routed: dict[str, Any],
    driver_context: "DriverContext",
    execution_environment: dict[str, str],
) -> tuple[bool, str | None]:
    """Validate a completed sweep case before its manifest may skip it.

    The manifest is a sweep index, not provenance; the saved workflow
    checkpoint and document own the claims about inputs and outputs.
    """
    if prior_entry is None:
        return False, "completed manifest entry is absent"
    if prior_entry.override_hash != compute_override_hash(routed):
        return False, "resolved sweep overrides changed"
    try:
        run_document_path = output_dir / prior_entry.run_document_path
        state_path = output_dir / prior_entry.workflow_state_path
        run_document = load_run_document(run_document_path)
        state = workflow_state_from_json(json.loads(state_path.read_text()))
        if state.status != "completed":
            return False, f"saved workflow state is {state.status!r}, not 'completed'"
        artifacts = tuple(
            data_artifact_from_json(raw) for raw in run_document.expectedArtifacts
        )
        validate_resume(
            state,
            run_document.workflowDag,
            case_root=Path(run_document.launch["caseRoot"]),
            driver_context=driver_context,
            env=execution_environment,
            expected_artifacts=artifacts,
        )
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return False, str(exc)
    return True, None


def sweep_run(
    spec_path: str | Path,
    *,
    output_dir: str | Path,
    max_cases: int = 200,
    retry_failed: bool = False,
    case_timeout_s: float | None = None,
    fresh: bool = False,
    task: str = "summarize",
    cli_study: Mapping[str, Any] | None = None,
    inputs: Mapping[str, str | Path] | None = None,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """Run every case in a sweep spec, then post-process the results.

    ``cli_study``/``inputs``: as :func:`sweep_plan`. `task` plays no part
    in the sweep loop itself -- expanding, routing, materializing, and
    running cases is fully deterministic and has no use for it. It is
    only consumed at the very end, handed to run_postprocessing_module.
    """
    execution_environment = driver_context.capabilities.environment_preflight.configure(
        os.environ,
        driver_context,
    )
    sweep_spec = _load_spec(spec_path)
    check_case_count_cap(sweep_spec, max_cases=max_cases)

    output_dir = Path(output_dir)

    record, cases_root = _sweep_record(sweep_spec, driver_context=driver_context)
    if record is not None:
        # Resolved to absolute before staging, matching the factory
        # branch's own --output-dir (which the CLI already resolves):
        # commit_record_case requires CaseMutationRequest.case_root to be
        # absolute.
        output_dir = Path(output_dir).resolve()
        # No manifest-based resume/retry across separate invocations yet
        # (see _record_sweep_run's own scope note); refused by name rather
        # than silently ignored.
        if retry_failed:
            raise TutorialRecordError(
                "--retry-failed is not yet supported for a tutorial-record "
                "sweep entry"
            )
        fresh_error = ensure_fresh_output_dir(
            output_dir, fresh=fresh, allowed_root=_allowed_runs_root(),
        )
        if fresh_error is not None:
            raise SweepValidationError(fresh_error)
        # A record-entry sweep does not support resume, so an existing
        # manifest here (not cleared by --fresh) is refused by name instead
        # of silently restaged, which would waste prior work and could
        # leave stale case directories if the spec changed. The factory
        # branch's spec-hash check below gives the specific reason when
        # the spec did change.
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
                "and a record-entry sweep does not support resume across "
                "invocations yet -- pass --fresh to start over, or use a new "
                "--output-dir"
            )
        return _record_sweep_run(
            record, cases_root, sweep_spec, output_dir=output_dir,
            case_timeout_s=case_timeout_s, task=task, cli_study=cli_study,
            inputs=inputs, driver_context=driver_context,
        )
    refuse_cli_study_for_non_record(str(_entry_name(sweep_spec)), cli_study)
    if inputs:
        raise TutorialRecordError(
            f"--input applies only to a tutorial record's sweep, and "
            f"{_entry_name(sweep_spec)!r} is not one"
        )

    fresh_error = ensure_fresh_output_dir(
        output_dir, fresh=fresh, allowed_root=_allowed_runs_root(),
    )
    if fresh_error is not None:
        raise SweepValidationError(fresh_error)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / SWEEP_MANIFEST_FILENAME

    spec_hash = compute_spec_hash(sweep_spec)
    existing_status_by_case: dict[str, str] = {}
    existing_entry_by_case = {}
    if manifest_path.exists():
        existing = read_manifest(manifest_path)
        if existing.sweep_spec_hash != spec_hash:
            raise SweepValidationError(
                "sweep.json has changed since this output directory was created "
                f"(hash mismatch: expected {existing.sweep_spec_hash}, got {spec_hash}); "
                "spec changed — use a fresh --output-dir or resolve the mismatch."
            )
        existing_status_by_case = {c.case_id: c.status for c in existing.cases}
        existing_entry_by_case = {c.case_id: c for c in existing.cases}

    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})
    entry = _entry_name(sweep_spec)

    manifest = SweepManifest(
        schema_version="1.0", sweep_spec_hash=spec_hash,
        created_at=_now(), updated_at=_now(), cases=[],
    )

    completed_count = 0
    failed_count = 0
    skipped_count = 0
    case_summaries: list[dict[str, Any]] = []

    for case in resolved_cases:
        case_dir = output_dir / case.case_id
        run_document_path = case_dir / RUN_DOCUMENT_FILENAME
        workflow_state_path = case_dir / STATE_FILENAME
        case_record_path = case_dir / CASE_RECORD_FILENAME

        prior_status = existing_status_by_case.get(case.case_id)
        prior_entry = existing_entry_by_case.get(case.case_id)
        outcome = "fresh"
        materialization_error = None
        plan_error = None
        timeout_error = None
        reuse_error = None

        routing_error: str | None = None
        try:
            if entry is not None:
                routed = route_entry_case_values(base=base, resolved_axis_values=case.resolved_axis_values)
            else:
                routed = route_case_values(
                    base=base,
                    resolved_axis_values=case.resolved_axis_values,
                    driver_context=driver_context,
                )
        except (OSError, ValueError) as exc:
            # An unrecognized/unroutable axis (e.g. "dx") is a per-case
            # failure, not a crash of the whole sweep -- same treatment as a
            # materialize_case failure below.
            routed = {}
            routing_error = str(exc)

        if routing_error is not None:
            status = "failed"
            materialization_error = routing_error
            failed_count += 1
        elif prior_status == "completed":
            reusable, reuse_error = _completed_case_is_reusable(
                prior_entry,
                output_dir=output_dir,
                routed=routed,
                driver_context=driver_context,
                execution_environment=execution_environment,
            )
            if reusable:
                outcome = "skipped"
                skipped_count += 1
                completed_count += 1
                status = "completed"
                workflow_state_path = output_dir / prior_entry.workflow_state_path
                run_document_path = output_dir / prior_entry.run_document_path
            else:
                # Fall through to a new plan and attempt.  The old manifest
                # remains useful evidence in the summary, but never grants a
                # success claim by itself.
                outcome = "invalidated"
                status = "failed"
                try:
                    if entry is not None:
                        plan_entry, routed = _materialize_entry_case(
                            entry,
                            routed,
                            staging_root=output_dir / "cases" / case.case_id,
                            driver_context=driver_context,
                        )
                        report = strict_plan(plan_entry, overrides=routed, driver_context=driver_context)
                    else:
                        materialize_case(case_dir=case_dir, routed=routed, driver_context=driver_context)
                        report = strict_plan(
                            case.case_id, entry_kind="case_folder",
                            overrides={"cases_root": str(output_dir)}, driver_context=driver_context,
                        )
                    payload = report.to_json()
                    if report.status != "ok":
                        plan_error = "strict_plan reported failed status"
                    else:
                        run_document = payload["run_document"]
                        workflow_state_path = _workflow_state_path_from_run_document(run_document)
                        run_document_path.parent.mkdir(parents=True, exist_ok=True)
                        run_document_path.write_text(json.dumps(run_document, indent=2))
                        if workflow_state_path.exists():
                            workflow_state_path.unlink()
                        result = _run_case_process(
                            omnidriver_run_command(driver_context, "--run-document", str(run_document_path)),
                            env=execution_environment,
                            timeout=case_timeout_s,
                        )
                        if workflow_state_path.exists():
                            status = json.loads(workflow_state_path.read_text()).get("status", "pending")
                        elif result.returncode != 0:
                            status = "failed"
                        else:
                            status = "pending"
                except subprocess.TimeoutExpired as exc:
                    timeout_error = f"case exceeded timeout of {case_timeout_s}s and was terminated: {exc}"
                except (OSError, ValueError) as exc:
                    materialization_error = str(exc)
                except Exception as exc:
                    plan_error = str(exc)
                if status == "completed":
                    completed_count += 1
                else:
                    failed_count += 1
        elif prior_status == "failed" and not retry_failed:
            status = "failed"
            failed_count += 1
            if prior_entry is not None:
                workflow_state_path = output_dir / prior_entry.workflow_state_path
                run_document_path = output_dir / prior_entry.run_document_path
        else:
            if prior_status == "failed" and retry_failed:
                outcome = "retried"
            status = "failed"
            try:
                if entry is not None:
                    plan_entry, routed = _materialize_entry_case(
                        entry,
                        routed,
                        staging_root=output_dir / "cases" / case.case_id,
                        driver_context=driver_context,
                    )
                    report = strict_plan(plan_entry, overrides=routed, driver_context=driver_context)
                else:
                    materialize_case(
                        case_dir=case_dir,
                        routed=routed,
                        driver_context=driver_context,
                    )
                    report = strict_plan(
                        case.case_id,
                        entry_kind="case_folder",
                        overrides={"cases_root": str(output_dir)},
                        driver_context=driver_context,
                    )
                payload = report.to_json()
                if report.status != "ok":
                    plan_error = "strict_plan reported failed status"
                else:
                    run_document = payload["run_document"]
                    workflow_state_path = _workflow_state_path_from_run_document(run_document)
                    # In entry mode, case_dir (this sweep's own bookkeeping
                    # location for run_document.json) is unrelated to the
                    # tutorial's real case_root and is never created by
                    # _materialize_entry_case, unlike generic mode's
                    # materialize_case which creates it as a side effect.
                    run_document_path.parent.mkdir(parents=True, exist_ok=True)
                    run_document_path.write_text(json.dumps(run_document, indent=2))
            except (OSError, ValueError) as exc:
                materialization_error = str(exc)
            except Exception as exc:
                plan_error = str(exc)
            else:
                if plan_error is None:
                    # Entry-mode cases can share a case root. The environment
                    # declaration identifies a generated output tree to
                    # snapshot so each case retains only its own changes.
                    conventions = driver_context.capabilities.case_runtime_conventions.conventions()
                    output_relpath = conventions.output_collection_relpath
                    archive_dir_name = (
                        (base.get("archive_dir_name") or "collectedOutput")
                        if entry is not None and output_relpath is not None
                        else None
                    )
                    pp_before: dict[str, tuple[float, int]] = {}
                    if archive_dir_name:
                        case_root_for_archive = Path(run_document["launch"]["caseRoot"])
                        output_root_for_archive = case_root_for_archive / output_relpath
                        pp_before = snapshot_output_tree(output_root_for_archive)
                    try:
                        if workflow_state_path.exists():
                            workflow_state_path.unlink()
                        result = _run_case_process(
                            omnidriver_run_command(driver_context, "--run-document", str(run_document_path)),
                            env=execution_environment,
                            timeout=case_timeout_s,
                        )
                    except subprocess.TimeoutExpired as exc:
                        # A hung case must not block the whole serial sweep: mark
                        # it failed and continue. The manifest stays resumable.
                        status = "failed"
                        timeout_error = (
                            f"case exceeded timeout of {case_timeout_s}s "
                            f"and was terminated: {exc}"
                        )
                    else:
                        if workflow_state_path.exists():
                            state = json.loads(workflow_state_path.read_text())
                            status = state.get("status", "pending")
                        elif result.returncode != 0:
                            status = "failed"
                        else:
                            status = "pending"
                        if archive_dir_name and workflow_state_path.exists():
                            collect_new_output_tree(
                                output_root_for_archive,
                                pp_before,
                                workflow_state_path.parent / archive_dir_name,
                                label=case.case_id,
                            )
            if status == "completed":
                completed_count += 1
            else:
                failed_count += 1

        case_summary = {
            "case_id": case.case_id,
            "status": status,
            "outcome": outcome,
            "run_document_path": str(run_document_path.relative_to(output_dir)),
            "workflow_state_path": _relative_or_absolute(workflow_state_path, output_dir),
        }
        if materialization_error is not None:
            case_summary["materialization_error"] = materialization_error
        if plan_error is not None:
            case_summary["plan_error"] = plan_error
        if timeout_error is not None:
            case_summary["timeout_error"] = timeout_error
        if reuse_error is not None:
            case_summary["reuse_error"] = reuse_error
        case_summaries.append(case_summary)

        manifest.cases.append(
            CaseManifestEntry(
                case_id=case.case_id,
                resolved_axis_values=case.resolved_axis_values,
                override_hash=compute_override_hash(routed),
                run_document_path=str(run_document_path.relative_to(output_dir)),
                workflow_state_path=_relative_or_absolute(workflow_state_path, output_dir),
                status=status,
                outcome=outcome,
                started_at=_now(),
                updated_at=_now(),
                case_record_path=str(case_record_path.relative_to(output_dir)),
            )
        )
        manifest.updated_at = _now()
        write_manifest(manifest_path, manifest)

    context = build_sweep_context(output_dir, persist_case_records=True)
    if failed_count == 0:
        postprocess = run_postprocessing_module(context, task=task).to_json()
    else:
        postprocess = {
            "status": "skipped",
            "message": f"sweep had {failed_count} failed case(s); postprocess not run",
        }

    return {
        "case_count": len(resolved_cases),
        "completed_count": completed_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "cases": case_summaries,
        "postprocess": postprocess,
    }
