from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from omnidriver.core.strict_planning import strict_plan, _strict_plan_for_spec
from omnidriver.core.plugin_profile import decomposition_dirname_prefix
from omnidriver.core.sweep.sweep_derivation_catalog import get_derivation
from omnidriver.core.sweep.sweep_expansion import SweepValidationError, check_case_count_cap, expand_sweep
from omnidriver.core.tutorial_records import TutorialRecordError
from omnidriver.sweep_materialize import materialize_case
from omnidriver.sweep_routing import route_case_values, route_entry_case_values
from .fresh import ensure_fresh_output_dir
from .attempt_lease import acquire_case_staging_lease
from .models import data_artifact_from_json, invoke_case_mutation
from .output_collection import collect_new_output_tree, snapshot_output_tree
from .postprocess_phase import build_sweep_context, run_postprocessing_module
from .record_execution import commit_record_case, record_case_spec
from .registry import load_entry_spec
from .run_document_exec import _allowed_runs_root, load_run_document
from .resume import validate_resume
from .workflow_state import workflow_state_from_json
from .workflow_runner import _terminate_process_group
from .sweep_manifest import (
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


def _load_spec(spec_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(spec_path).read_text())


def _entry_name(sweep_spec: dict[str, Any]) -> str | None:
    return sweep_spec.get("base", {}).get("entry")


# ---------------------------------------------------------------------------
# Item 2: a study whose "entry" names a tutorial_record dispatches through a
# dedicated path -- staged from the record's native case, one
# commit_record_case per case, then the record's own workflow steps run
# through the SAME strict-plan/run-document/workflow-runner pipeline a
# factory entry's spec runs through (record_execution.record_case_spec maps
# the record onto the same workflow_dag shape). Never tried as a factory
# entry first and reinterpreted -- resolve_entry's own explicit dispatch
# (design §3/registry.resolve_entry) decides which this is, once, up front.
# ---------------------------------------------------------------------------

#: `entry`/`cases_root` are sweep-dispatch bookkeeping in `base`, not case
#: content, a document key, or an axis -- stripped before a record's study
#: values are resolved, the same treatment `sweep_routing
#: ._ENTRY_NON_ROUTABLE_KEYS` already gives `entry`/`archive_dir_name` for a
#: factory entry's own routing.
_RECORD_NON_STUDY_BASE_KEYS: frozenset[str] = frozenset({"entry", "cases_root"})


def _sweep_record(
    sweep_spec: dict[str, Any], *, driver_context: "DriverContext",
) -> tuple[Any, Path] | tuple[None, None]:
    """Return ``(record, cases_root)`` when ``base.entry`` names a tutorial
    record, else ``(None, None)`` -- a factory tutorial or no entry at all.

    Checks the ``tutorial_records`` catalog directly (the same one
    ``registry.resolve_entry``'s own record branch consults), rather than
    calling ``resolve_entry`` itself: that function also probes ``entry``
    against the filesystem as a possible case path (design's own case-path
    resolution, ``registry.resolve_entry``'s ``case_folder`` branch) before
    it ever reaches the record branch -- a probe every EXISTING factory-
    entry sweep would now pay for and, in a test that mocks
    ``load_entry_spec``/``strict_plan`` directly without registering a real
    factory, spuriously fail. A bare tutorial-record lookup needs none of
    that; the ambiguity refusal between a record and a same-named factory
    (design's "one name must not name both") is reproduced here directly
    instead, matching ``resolve_entry``'s own precedence.

    A record has no ambient cases root (CLAUDE.md's "supplied versus
    discovered"): ``base.cases_root`` must name it explicitly whenever
    ``entry`` resolves to a record, refused by name otherwise.
    """
    entry = _entry_name(sweep_spec)
    if entry is None:
        return None, None
    normalized_key = entry.strip().casefold()
    catalog = driver_context.capabilities.tutorial_records.catalog() or {}
    normalized_records = {name.casefold(): rec for name, rec in catalog.items()}
    record = normalized_records.get(normalized_key)
    if record is None:
        return None, None
    from .registry import _normalized_registry

    if normalized_key in _normalized_registry(driver_context):
        raise KeyError(
            f"Entry '{entry}' is ambiguous: it is registered as both a "
            "tutorial record and a factory tutorial (spec_factories); "
            "one name must not name both"
        )
    base = sweep_spec.get("base", {})
    cases_root_value = base.get("cases_root")
    if cases_root_value is None:
        raise TutorialRecordError(
            f"tutorial record {entry!r} cannot be swept: sweep.json's "
            "'base' must supply 'cases_root' naming where its native case "
            "lives (there is no ambient cases root to discover)"
        )
    return record, Path(cases_root_value)


def _record_case_study_by_source(
    *, base: dict[str, Any], resolved_axis_values: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    stripped_base = {
        key: value for key, value in base.items()
        if key not in _RECORD_NON_STUDY_BASE_KEYS
    }
    return {"base": stripped_base, "sweep": dict(resolved_axis_values)}


def _record_sweep_plan(
    record: Any, cases_root: Path, sweep_spec: dict[str, Any], *,
    output_dir: Path, driver_context: "DriverContext",
) -> dict[str, Any]:
    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})
    case_reports: list[dict[str, Any]] = []
    for case in resolved_cases:
        staged_case_root = output_dir / "cases" / case.case_id
        study_by_source = _record_case_study_by_source(
            base=base, resolved_axis_values=case.resolved_axis_values,
        )
        try:
            commit_result = commit_record_case(
                record, cases_root=cases_root, staged_case_root=staged_case_root,
                study_by_source=study_by_source, driver_context=driver_context,
            )
            spec = record_case_spec(
                record, case_id=case.case_id, staged_case_root=staged_case_root,
                workflow_step_ids=commit_result.workflow_step_ids,
                command_arguments=commit_result.command_arguments,
            )
            report = _strict_plan_for_spec(record.name, spec, driver_context=driver_context)
        except Exception as exc:
            # Same broad-catch reasoning sweep_plan's factory-entry branch
            # already uses just below: one bad case costs one case, not the
            # whole command.
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
        })
    return {"case_count": len(resolved_cases), "cases": case_reports}


def _record_sweep_run(
    record: Any, cases_root: Path, sweep_spec: dict[str, Any], *,
    output_dir: Path, case_timeout_s: float | None, task: str,
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """The record-entry counterpart of ``sweep_run``'s factory-entry branch.

    Scope, deliberately narrower than the factory-entry path for this first
    cut: every case is planned and run fresh, sequentially -- no manifest-
    based resume/retry/skip across separate invocations yet (each of those
    reads a prior run's SAVED workflow checkpoint, which a record case does
    not yet have a settled shape for). A manifest is still written, so the
    output directory carries the same bookkeeping shape a factory-entry
    sweep's does.
    """
    execution_environment = driver_context.capabilities.environment_preflight.configure(
        os.environ, driver_context,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})

    manifest_path = output_dir / "sweep_manifest.json"
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
        run_document_path = case_dir / "run_document.json"
        workflow_state_path = case_dir / "workflow_state.json"
        case_record_path = case_dir / "case_record.json"
        study_by_source = _record_case_study_by_source(
            base=base, resolved_axis_values=case.resolved_axis_values,
        )

        status = "failed"
        materialization_error = None
        plan_error = None
        timeout_error = None
        commit_status = None
        try:
            commit_result = commit_record_case(
                record, cases_root=cases_root, staged_case_root=staged_case_root,
                study_by_source=study_by_source, driver_context=driver_context,
            )
            commit_status = commit_result.status
            spec = record_case_spec(
                record, case_id=case.case_id, staged_case_root=staged_case_root,
                workflow_step_ids=commit_result.workflow_step_ids,
                command_arguments=commit_result.command_arguments,
            )
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
                    [sys.executable, "-m", "omnidriver", "run", "--run-document", str(run_document_path)],
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
        if materialization_error is not None:
            case_summary["materialization_error"] = materialization_error
        if plan_error is not None:
            case_summary["plan_error"] = plan_error
        if timeout_error is not None:
            case_summary["timeout_error"] = timeout_error
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

    `run_document_path` is always written under the sweep's own
    `--output-dir` (safe to make relative). `workflow_state_path` is not:
    in entry mode it comes from `launch.outputDir`, which resolves to the
    target tutorial's own case_root/output_dir_name -- a directory tree
    entirely unrelated to the sweep's --output-dir (confirmed via a real,
    non-mocked sweep-run: Path.relative_to raised ValueError there). Record
    the absolute path in that case rather than crash the whole sweep over a
    manifest cosmetic.
    """
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _is_declared_generated_time_directory(name: str, conventions) -> bool:
    """Apply the environment's declared time-directory rule without naming it."""
    pattern = conventions.time_directory_name_pattern
    return (
        pattern is not None
        and name not in conventions.preserved_time_directory_names
        and re.match(pattern, name) is not None
    )


def _clean_stale_time_directories(case_root: Path, *, conventions) -> None:
    """Remove prior generated time directories when the environment declares them.

    Entry-based sweeps reuse one shared case_root across cases (see
    _materialize_entry_case's docstring). A case with no authored initial
    directory can otherwise consume a prior run's generated time directory.
    Clearing declared generated directories before materialization prevents
    that stale-state reuse.
    """
    if conventions.time_directory_name_pattern is None or not case_root.is_dir():
        return
    for child in case_root.iterdir():
        if child.is_dir() and _is_declared_generated_time_directory(child.name, conventions):
            shutil.rmtree(child)


def _materialize_entry_case(
    entry: str,
    routed: dict[str, Any],
    *,
    staging_root: Path | None = None,
    driver_context=None,
) -> dict[str, Any]:
    """Materialize one entry-based sweep case via the tutorial's own spec.

    Entry-based sweeps target an existing registered tutorial whose
    apply_case()/build_cases() mutate a case root in place.  That root must be
    a disposable staging copy, never the checked-in tutorial directory.  The
    returned overrides point the entry at that staged case so strict planning
    and execution use exactly the same paths.

    ``staging_root`` is optional for compatibility with low-level callers and
    tests that provide an already-isolated fake spec.  Real sweep callers
    always pass it.

    Raises ValueError if the resolved overrides don't collapse to exactly one
    case -- the sweep model is one case per resolved axis combination.
    """
    spec = load_entry_spec(entry, overrides=routed, driver_context=driver_context)
    effective_routed = dict(routed)
    if staging_root is not None and spec.case_root.exists():
        source_case_root = Path(spec.case_root).resolve()
        staged_case_root = Path(staging_root).resolve()
        _stage_entry_case(source_case_root, staged_case_root, driver_context=driver_context)
        # ``make_spec`` resolves case_root as cases_root/case_dir_name.
        # Redirect both values together; changing only cases_root would
        # leave a nested original case_dir_name and recreate the source tree
        # below the scratch directory.
        effective_routed["cases_root"] = str(staged_case_root.parent)
        effective_routed["case_dir_name"] = staged_case_root.name
        # Staging already isolates this one case at staged_case_root, so
        # whatever output_dir_name the sweep spec's own "dependent" template
        # derived (typically the case id again, e.g. for per-case archiving
        # under a *shared* case_root) has nothing left to distinguish here --
        # every sweep case already gets its own staged_case_root. Leaving it
        # in place double-nests output_dir under
        # staged_case_root/<that same case id>/, a directory the solve step
        # never writes into (it writes generated output straight into
        # staged_case_root under its environment convention), which then
        # makes the workflow's artifact check report real, present output as
        # missing. "." tells resolve_spec_paths there is nothing to append.
        effective_routed["output_dir_name"] = "."
        staged_spec = load_entry_spec(
            entry, overrides=effective_routed, driver_context=driver_context,
        )
        # A real registered factory consumes cases_root/case_dir_name and
        # therefore returns the staged path.  Keep compatibility with test
        # doubles and third-party factories that intentionally return their
        # own fixed spec regardless of overrides.
        if Path(staged_spec.case_root).resolve() != staged_case_root:
            effective_routed = dict(routed)
        else:
            spec = staged_spec
    cases = spec.build_cases()
    if len(cases) != 1:
        raise ValueError(
            f"entry-based sweep axis combination resolved to {len(cases)} cases "
            f"for entry '{entry}'; expected exactly 1 -- add enough constraining "
            "overrides (e.g. 'solvers') to collapse this combination to a single case"
        )
    from ..plugin_capabilities import CaseRuntimeConventions

    conventions = (
        driver_context.capabilities.case_runtime_conventions.conventions()
        if driver_context is not None else CaseRuntimeConventions()
    )
    _clean_stale_time_directories(spec.case_root, conventions=conventions)
    invoke_case_mutation(spec, spec.case_root, cases[0])
    return effective_routed


def _stage_entry_case(
    source_case_root: Path, staged_case_root: Path, *, driver_context=None,
) -> None:
    """Copy a registered case into scratch storage without old run output.

    Registered tutorial folders contain source dictionaries and scripts next
    to OpenFOAM's generated mesh, time, processor, log, and post-processing
    trees.  Copying those generated trees would reintroduce the stale-state
    bug this staging boundary is meant to prevent, so the filter is explicit
    and conservative: keep authored inputs (including ``0/``) and omit only
    known derived artifacts.
    """
    from ..plugin_capabilities import CaseRuntimeConventions

    conventions = (
        driver_context.capabilities.case_runtime_conventions.conventions()
        if driver_context is not None else CaseRuntimeConventions()
    )
    decomposition_prefix = (
        decomposition_dirname_prefix(driver_context)
        if driver_context is not None else None
    )

    def ignore_generated(_directory: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        for name in names:
            candidate = Path(_directory) / name
            # A previous driverFOAM case can have a descriptive directory name
            # (for example ``gauss_linear_40_*``) rather than a numeric
            # generated numeric-time name. Its workflow markers are the reliable
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
                    (decomposition_prefix is not None and name.startswith(decomposition_prefix))
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
            if _is_declared_generated_time_directory(path.name, conventions):
                ignored.add(name)
        return ignored

    source_case_root = Path(source_case_root).resolve()
    staged_case_root = Path(staged_case_root).resolve()
    if not source_case_root.is_dir():
        raise FileNotFoundError(f"Registered case root does not exist: {source_case_root}")
    with acquire_case_staging_lease(staged_case_root):
        _recover_interrupted_case_staging(staged_case_root)
        _copy_and_promote_staged_case(
            source_case_root,
            staged_case_root,
            ignore=ignore_generated,
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

    The normal promotion never exposes a partial copy: the candidate is copied
    under a private sibling and renamed only once complete.  If a process dies
    between the two renames, preserving the prior live case is safer than
    guessing that the candidate should run, so an existing case is restored
    from its backup.  A brand-new case has no prior case to restore and may
    promote its fully copied candidate.
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


def _copy_and_promote_staged_case(
    source_case_root: Path,
    staged_case_root: Path,
    *,
    ignore: Any,
) -> None:
    """Copy to a private sibling, then replace a staged case under its lease."""
    token = uuid.uuid4().hex
    candidate = _staging_path(staged_case_root, token, "candidate")
    backup = _staging_path(staged_case_root, token, "backup")
    original_exists = staged_case_root.exists()
    shutil.copytree(source_case_root, candidate, ignore=ignore, symlinks=True)
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
    driver_context: "DriverContext",
) -> dict[str, Any]:
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
        return _record_sweep_plan(
            record, cases_root, sweep_spec, output_dir=output_dir,
            driver_context=driver_context,
        )

    resolved_cases = expand_sweep(sweep_spec, get_derivation=get_derivation)
    base = sweep_spec.get("base", {})
    entry = _entry_name(sweep_spec)

    case_reports = []
    for case in resolved_cases:
        try:
            if entry is not None:
                routed = route_entry_case_values(base=base, resolved_axis_values=case.resolved_axis_values)
                routed = _materialize_entry_case(
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
            report = strict_plan(entry, overrides=routed, driver_context=driver_context)
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
    return Path(output_dir) / "workflow_state.json"


def _completed_case_is_reusable(
    prior_entry: CaseManifestEntry | None,
    *,
    output_dir: Path,
    routed: dict[str, Any],
    driver_context: "DriverContext",
    execution_environment: dict[str, str],
) -> tuple[bool, str | None]:
    """Validate a completed sweep case before its manifest may skip it.

    The manifest is a sweep index, not provenance.  It is insufficient to
    establish that the case still has the same inputs or its required outputs.
    Those claims remain owned by the saved workflow checkpoint and document.
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
    driver_context: "DriverContext",
) -> dict[str, Any]:
    """`task` plays no part in the sweep loop itself -- expanding, routing,
    materializing, and running cases is fully deterministic and has no use
    for it. It is only consumed at the very end, handed to
    run_postprocessing_module: the sweep is task(sweep), no reasoning
    involved; the postprocess hand-off is where a task actually matters.
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
        # Scope, item 2 (see _record_sweep_run's own docstring): no
        # manifest-based resume/retry across separate invocations yet.
        # Refused BY NAME rather than silently ignored -- CLAUDE.md's
        # "explicitly-contexted operation never falls back to the default".
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
        return _record_sweep_run(
            record, cases_root, sweep_spec, output_dir=output_dir,
            case_timeout_s=case_timeout_s, task=task, driver_context=driver_context,
        )

    fresh_error = ensure_fresh_output_dir(
        output_dir, fresh=fresh, allowed_root=_allowed_runs_root(),
    )
    if fresh_error is not None:
        raise SweepValidationError(fresh_error)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "sweep_manifest.json"

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
        run_document_path = case_dir / "run_document.json"
        workflow_state_path = case_dir / "workflow_state.json"
        case_record_path = case_dir / "case_record.json"

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
                        routed = _materialize_entry_case(
                            entry,
                            routed,
                            staging_root=output_dir / "cases" / case.case_id,
                            driver_context=driver_context,
                        )
                        report = strict_plan(entry, overrides=routed, driver_context=driver_context)
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
                            [sys.executable, "-m", "omnidriver", "run", "--run-document", str(run_document_path)],
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
                    routed = _materialize_entry_case(
                        entry,
                        routed,
                        staging_root=output_dir / "cases" / case.case_id,
                        driver_context=driver_context,
                    )
                    report = strict_plan(entry, overrides=routed, driver_context=driver_context)
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
                            [sys.executable, "-m", "omnidriver", "run", "--run-document", str(run_document_path)],
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
