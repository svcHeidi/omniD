"""Bounded orchestration for evidence-driven repair experiments.

This layer is intentionally independent of workflow retry. A retry repeats one
execution policy; a repair experiment must bind a new hypothesis and proposal
to the failure evidence that motivated it.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


JOURNAL_DIR = "repair_loops"


@dataclass(frozen=True)
class RepairBudgets:
    max_candidate_executions: int
    max_elapsed_seconds: float | None = None
    max_unchanged_failures: int = 2

    def __post_init__(self) -> None:
        if self.max_candidate_executions < 1:
            raise ValueError("max_candidate_executions must be positive")
        if self.max_elapsed_seconds is not None and self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be positive when supplied")
        if self.max_unchanged_failures < 1:
            raise ValueError("max_unchanged_failures must be positive")


@dataclass(frozen=True, init=False)
class RepairObservation:
    _canonical_json: str = field(repr=False)

    def __init__(self, evidence: Mapping[str, Any]) -> None:
        object.__setattr__(self, "_canonical_json", _canonical_json(dict(evidence)))

    @property
    def evidence(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    @property
    def digest(self) -> str:
        return _digest_json(self._canonical_json)


@dataclass(frozen=True, init=False)
class RepairProposal:
    hypothesis: str
    based_on_observation_digest: str
    _overrides_json: str = field(repr=False)

    def __init__(
        self,
        hypothesis: str,
        overrides: tuple[Mapping[str, Any], ...],
        based_on_observation_digest: str,
    ) -> None:
        object.__setattr__(self, "hypothesis", hypothesis)
        object.__setattr__(self, "based_on_observation_digest", based_on_observation_digest)
        object.__setattr__(
            self, "_overrides_json", _canonical_json([dict(item) for item in overrides]),
        )

    @property
    def overrides(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(self._overrides_json))

    @property
    def digest(self) -> str:
        return _digest({"hypothesis": self.hypothesis, "overrides": self.overrides})


@dataclass(frozen=True)
class RepairExperimentResult:
    status: str
    observation: RepairObservation
    transaction_id: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"succeeded", "failed", "rejected"}:
            raise ValueError(f"invalid repair experiment status: {self.status}")


@dataclass(frozen=True)
class RepairLoopOutcome:
    status: str
    reason: str
    executions: int
    unchanged_failures: int
    observation: RepairObservation
    journal_path: Path


def run_repair_loop(
    initial_observation: RepairObservation,
    *,
    output_dir: Path,
    budgets: RepairBudgets,
    propose: Callable[[RepairObservation], RepairProposal | None],
    execute_candidate: Callable[[RepairProposal], RepairExperimentResult],
    monotonic: Callable[[], float] = time.monotonic,
    loop_id: str | None = None,
) -> RepairLoopOutcome:
    """Run bounded reason/change/compare cycles and durably record each one.

    ``propose`` runs outside execution ownership. ``execute_candidate`` owns the
    full mutation -> effective resolution -> replan -> dispatch transaction and
    must acquire its case/output leases. A reservation is persisted before that
    callback, so a crash cannot silently reuse an execution budget slot.
    """
    loop_id = _validated_loop_id(loop_id or str(uuid.uuid4()))
    path = Path(output_dir) / JOURNAL_DIR / f"{loop_id}.json"
    started = monotonic()
    observation = initial_observation
    executions = 0
    unchanged = 0
    if path.exists():
        journal = _load_journal(path)
        if journal.get("budgets") != asdict(budgets):
            raise ValueError("repair-loop budgets do not match the existing loop")
        if journal.get("initial_observation_digest") != initial_observation.digest:
            raise ValueError("initial observation does not match the existing repair loop")
        experiments = journal.get("experiments")
        if not isinstance(experiments, list):
            raise ValueError("existing repair-loop journal is malformed")
        executions = len(experiments)
        if journal.get("status") != "running":
            final = RepairObservation(journal.get("final_observation", {}))
            return RepairLoopOutcome(
                str(journal["status"]), str(journal["reason"]), executions,
                int(journal.get("unchanged_failures", 0)), final, path,
            )
        if experiments and experiments[-1].get("status") == "reserved":
            experiments[-1].update(status="interrupted", finished_at=_now())
            return _finish(
                path, journal, "failed", "interrupted_candidate_requires_recovery",
                executions, 0, initial_observation,
            )
        if experiments:
            observation = RepairObservation(experiments[-1]["resulting_observation"])
            unchanged = _trailing_unchanged_failures(experiments)
        return _continue_loop(
            path, journal, observation, executions, unchanged, started,
            budgets, propose, execute_candidate, monotonic,
        )
    journal: dict[str, Any] = {
        "schema_version": 1,
        "loop_id": loop_id,
        "status": "running",
        "started_at": _now(),
        "budgets": asdict(budgets),
        "initial_observation_digest": observation.digest,
        "initial_observation": observation.evidence,
        "experiments": [],
    }
    _atomic_write(path, journal)

    return _continue_loop(
        path, journal, observation, executions, unchanged, started,
        budgets, propose, execute_candidate, monotonic,
    )


def _continue_loop(
    path: Path,
    journal: dict[str, Any],
    observation: RepairObservation,
    executions: int,
    unchanged: int,
    started: float,
    budgets: RepairBudgets,
    propose: Callable[[RepairObservation], RepairProposal | None],
    execute_candidate: Callable[[RepairProposal], RepairExperimentResult],
    monotonic: Callable[[], float],
) -> RepairLoopOutcome:

    while True:
        elapsed = monotonic() - started
        if executions >= budgets.max_candidate_executions:
            return _finish(path, journal, "stopped", "execution_budget_exhausted",
                           executions, unchanged, observation)
        if budgets.max_elapsed_seconds is not None and elapsed >= budgets.max_elapsed_seconds:
            return _finish(path, journal, "stopped", "elapsed_budget_exhausted",
                           executions, unchanged, observation)

        try:
            proposal = propose(observation)
        except Exception as exc:
            _finish(path, journal, "failed", "proposer_error",
                    executions, unchanged, observation)
            raise
        if proposal is None:
            return _finish(path, journal, "stopped", "proposer_stopped",
                           executions, unchanged, observation)
        if not proposal.hypothesis.strip():
            _finish(path, journal, "failed", "proposer_contract_error",
                    executions, unchanged, observation)
            raise ValueError("repair hypothesis must not be empty")
        if proposal.based_on_observation_digest != observation.digest:
            _finish(path, journal, "failed", "proposer_contract_error",
                    executions, unchanged, observation)
            raise ValueError("repair proposal is based on stale observation evidence")
        if (
            budgets.max_elapsed_seconds is not None
            and monotonic() - started >= budgets.max_elapsed_seconds
        ):
            return _finish(path, journal, "stopped", "elapsed_budget_exhausted",
                           executions, unchanged, observation)

        executions += 1
        experiment = {
            "execution": executions,
            "status": "reserved",
            "reserved_at": _now(),
            "observation_digest": observation.digest,
            "observation": observation.evidence,
            "hypothesis": proposal.hypothesis,
            "overrides": [dict(item) for item in proposal.overrides],
            "proposal_digest": proposal.digest,
        }
        journal["experiments"].append(experiment)
        _atomic_write(path, journal)

        try:
            result = execute_candidate(proposal)
        except Exception as exc:
            experiment.update(status="error", finished_at=_now(), error=str(exc))
            return _finish(path, journal, "failed", "candidate_executor_error",
                           executions, unchanged, observation)

        next_observation = result.observation
        experiment.update(
            status=result.status,
            finished_at=_now(),
            resulting_observation_digest=next_observation.digest,
            resulting_observation=next_observation.evidence,
            transaction_id=result.transaction_id,
        )
        _atomic_write(path, journal)
        if result.status == "succeeded":
            return _finish(path, journal, "succeeded", "candidate_succeeded",
                           executions, unchanged, next_observation)
        unchanged = unchanged + 1 if next_observation.digest == observation.digest else 0
        observation = next_observation
        if unchanged >= budgets.max_unchanged_failures:
            return _finish(path, journal, "stopped", "repeated_unchanged_failure",
                           executions, unchanged, observation)


def _validated_loop_id(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("repair loop_id must be a UUID") from exc
    if str(parsed) != value:
        raise ValueError("repair loop_id must use canonical UUID text")
    return value


def _load_journal(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"repair-loop journal is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"repair-loop journal is malformed: {path}")
    return payload


def _trailing_unchanged_failures(experiments: list[dict[str, Any]]) -> int:
    count = 0
    for item in reversed(experiments):
        if (
            item.get("status") not in {"failed", "rejected"}
            or item.get("resulting_observation_digest") != item.get("observation_digest")
        ):
            break
        count += 1
    return count


def _finish(path: Path, journal: dict[str, Any], status: str, reason: str,
            executions: int, unchanged: int,
            observation: RepairObservation) -> RepairLoopOutcome:
    journal.update(status=status, reason=reason, finished_at=_now(),
                   executions=executions, unchanged_failures=unchanged,
                   final_observation_digest=observation.digest,
                   final_observation=observation.evidence)
    _atomic_write(path, journal)
    return RepairLoopOutcome(status, reason, executions, unchanged, observation, path)


def _digest(value: Any) -> str:
    return _digest_json(_canonical_json(value))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("repair evidence and overrides must be strict JSON values") from exc


def _digest_json(payload: str) -> str:
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def observation_from_failure_context(
    failure_context: Mapping[str, Any],
) -> RepairObservation:
    """Remove per-attempt locations while retaining comparable failure evidence."""
    stable_keys = (
        "step_id", "exit_code", "diagnostics", "stdout_tail", "stderr_tail",
        "stdout_truncated", "stderr_truncated",
    )
    return RepairObservation({
        key: failure_context[key] for key in stable_keys if key in failure_context
    })


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)
