from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .runtime.models import DataArtifact


@dataclass(frozen=True)
class StrictDiagnostic:
    level: str
    code: str
    message: str
    source: str = ""
    field: str = ""
    #: What the message states, as data: ``rule`` names the declared rule a refusal broke;
    #: a scan note carries its scan record.
    detail: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class SimulationAuditItem:
    stage: str
    status: str
    points: int
    max_points: int
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


def diagnostic(
    level: str,
    code: str,
    message: str,
    *,
    source: str = "",
    field: str = "",
    detail: Mapping[str, Any] | None = None,
) -> StrictDiagnostic:
    return StrictDiagnostic(level=level, code=code, message=message, source=source, field=field, detail=detail)


def has_error(diagnostics: tuple[StrictDiagnostic, ...]) -> bool:
    return any(diagnostic.level == "error" for diagnostic in diagnostics)


def has_warning(diagnostics: tuple[StrictDiagnostic, ...]) -> bool:
    return any(diagnostic.level == "warning" for diagnostic in diagnostics)


def artifact_to_json(artifact: DataArtifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload["variables"] = list(artifact.variables)
    return payload

